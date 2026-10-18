import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, delete, event, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from lifegather.auth.email_models import EmailCredential, ExternalIdentity
from lifegather.auth.models import LoginFlow, LoginSession, User

ISSUER = "https://accounts.google.com"
TEST_ISSUER = "lifegather:test"
SESSION_SECONDS = 604800
FLOW_SECONDS = 600


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class InvalidFlow(ValueError):
    pass


@dataclass(frozen=True)
class Account:
    id: str
    email: str
    name: str


@dataclass(frozen=True)
class CurrentSession:
    user: Account
    csrf_token: str


@dataclass(frozen=True)
class SignedIn:
    user: Account
    token: str


@dataclass(frozen=True)
class Flow:
    nonce: str
    verifier: str


class AuthStore:
    """Framework-independent identity and opaque session storage."""

    def __init__(self, path: Path, *, test_login_enabled: bool = False) -> None:
        self.path = path
        self.test_login_enabled = test_login_enabled
        self.engine = create_engine(
            "sqlite:///" + path.resolve().as_posix(),
            connect_args={"check_same_thread": False, "timeout": 15},
        )

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection: object, _: object) -> None:
            # SQLAlchemy's DBAPI callback is intentionally driver-specific.
            from sqlite3 import Connection

            assert isinstance(connection, Connection)
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")

    def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            self.path.chmod(0o600)
        else:
            os.close(descriptor)
        config = Config()
        location = Path(__file__).parents[1] / "migrations"
        config.set_main_option("script_location", str(location))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        self.path.chmod(0o600)

    def _cleanup(self, db: Session, now: int) -> None:
        # Bound cleanup work; expiry is enforced even for rows not yet removed.
        for model, column in (
            (LoginFlow, LoginFlow.browser_hash),
            (LoginSession, LoginSession.token_hash),
        ):
            expired = select(column).where(model.expires_at <= now).limit(100)
            db.execute(delete(model).where(column.in_(expired)))

    def begin_flow(
        self, browser: str, state: str, nonce: str, verifier: str, *, now: int
    ) -> None:
        with Session(self.engine) as db, db.begin():
            self._cleanup(db, now)
            db.execute(
                insert(LoginFlow)
                .values(
                    browser_hash=digest(browser),
                    state_hash=digest(state),
                    nonce=nonce,
                    verifier=verifier,
                    expires_at=now + FLOW_SECONDS,
                )
                .on_conflict_do_update(
                    index_elements=["browser_hash"],
                    set_={
                        "state_hash": digest(state),
                        "nonce": nonce,
                        "verifier": verifier,
                        "expires_at": now + FLOW_SECONDS,
                    },
                )
            )

    def consume_flow(self, browser: str, state: str, *, now: int) -> Flow:
        with Session(self.engine) as db, db.begin():
            row = db.execute(
                delete(LoginFlow)
                .where(
                    LoginFlow.browser_hash == digest(browser),
                    LoginFlow.state_hash == digest(state),
                    LoginFlow.expires_at > now,
                )
                .returning(LoginFlow.nonce, LoginFlow.verifier)
            ).first()
            if row is None:
                raise InvalidFlow("Invalid, expired, or already used sign-in")
            return Flow(nonce=row[0], verifier=row[1])

    @staticmethod
    def issue_session(db: Session, user: User, now: int) -> SignedIn:
        token = secrets.token_urlsafe(32)
        db.add(
            LoginSession(
                token_hash=digest(token),
                user_id=user.id,
                csrf_token=secrets.token_urlsafe(32),
                expires_at=now + SESSION_SECONDS,
            )
        )
        return SignedIn(Account(user.id, user.email, user.name), token)

    def login(self, subject: str, email: str, name: str, *, now: int) -> SignedIn:
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            self._cleanup(db, now)
            user = db.scalar(
                select(User)
                .join(ExternalIdentity, ExternalIdentity.user_id == User.id)
                .where(
                    ExternalIdentity.issuer == ISSUER,
                    ExternalIdentity.subject == subject,
                )
                .limit(1)
            )
            if user is None:
                if db.scalar(
                    select(EmailCredential.user_id)
                    .where(EmailCredential.email_key == email.strip().casefold())
                    .limit(1)
                ):
                    raise InvalidFlow(
                        "Sign in with your existing method; "
                        "automatic linking is disabled"
                    )
                user = User(
                    id=str(uuid4()),
                    issuer=ISSUER,
                    subject=subject,
                    email=email,
                    name=name,
                    created_at=now,
                )
                db.add(user)
                db.flush()
                db.add(
                    ExternalIdentity(
                        id=str(uuid4()), user_id=user.id, issuer=ISSUER, subject=subject
                    )
                )
            else:
                user.email, user.name = email, name
            signed = self.issue_session(db, user, now)
            db.commit()
            return signed

    def test_login(self, *, now: int, old_token: str = "") -> SignedIn:
        """An explicit installation opt-in grants access to one shared test user."""
        if not self.test_login_enabled:
            raise InvalidFlow("Test login is disabled")
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            self._cleanup(db, now)
            user = db.scalar(
                select(User)
                .where(User.issuer == TEST_ISSUER, User.subject == "test-workspace")
                .limit(1)
            )
            if user is None:
                user = User(
                    id=str(uuid4()),
                    issuer=TEST_ISSUER,
                    subject="test-workspace",
                    name="Test user",
                    email="test@lifegather.invalid",
                    created_at=now,
                )
                db.add(user)
                db.flush()
            if old_token:
                db.execute(
                    delete(LoginSession).where(
                        LoginSession.token_hash == digest(old_token)
                    )
                )
            signed = self.issue_session(db, user, now)
            db.commit()
            return signed

    def authenticate(self, token: str, *, now: int) -> CurrentSession | None:
        with Session(self.engine) as db:
            row = db.execute(
                select(User, LoginSession)
                .join(LoginSession, LoginSession.user_id == User.id)
                .where(
                    LoginSession.token_hash == digest(token),
                    LoginSession.expires_at > now,
                )
                .limit(1)
            ).first()
            if row is None:
                return None
            user, session = row
            if user.issuer == TEST_ISSUER and not self.test_login_enabled:
                return None
            return CurrentSession(
                Account(user.id, user.email, user.name), session.csrf_token
            )

    def logout(self, token: str) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(
                delete(LoginSession).where(LoginSession.token_hash == digest(token))
            )
