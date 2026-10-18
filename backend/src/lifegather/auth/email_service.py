"""Verified native identities, single-use recovery and persistent throttling."""

import logging
import secrets
from threading import BoundedSemaphore
from typing import Literal
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from lifegather.auth.email_models import AuthAttempt, EmailChallenge, EmailCredential
from lifegather.auth.email_validation import EmailAuthError as EmailAuthError
from lifegather.auth.email_validation import email_key, password_value
from lifegather.auth.mail import MailSender
from lifegather.auth.models import LoginSession, User
from lifegather.auth.store import Account, AuthStore, SignedIn, digest

logger = logging.getLogger(__name__)

HASHER = PasswordHasher()
HASH_SLOTS = BoundedSemaphore(2)
DUMMY_HASH = HASHER.hash("public dummy value for constant-work sign-in")
Purpose = Literal["signup", "reset", "link"]


def hash_password(password: str) -> str:
    password_value(password)
    if not HASH_SLOTS.acquire(blocking=False):
        raise EmailAuthError("Sign-in busy; try again shortly", 503)
    try:
        return HASHER.hash(password)
    finally:
        HASH_SLOTS.release()


def verify_password(hashed: str, password: str) -> bool:
    if not HASH_SLOTS.acquire(blocking=False):
        raise EmailAuthError("Sign-in busy; try again shortly", 503)
    try:
        try:
            return HASHER.verify(hashed, password)
        except (InvalidHashError, VerificationError):
            return False
    finally:
        HASH_SLOTS.release()


class EmailAuth:
    def __init__(
        self, store: AuthStore, sender: MailSender | None, public_url: str
    ) -> None:
        self.store, self.sender, self.public_url = store, sender, public_url

    @property
    def delivery_enabled(self) -> bool:
        return self.sender is not None

    def _limits(self, action: str, client: str, account: str | None, now: int) -> bool:
        mail = action == "mail"
        seconds = 3600 if mail else 900
        limits = [
            (
                digest(action + ":client:" + client[:200]),
                20 if mail else 50 if action == "login" else 30,
            )
        ]
        if account is not None:
            limits.append((digest(action + ":account:" + account), 3 if mail else 10))
        account_allowed = True
        with Session(self.store.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            expired = (
                select(AuthAttempt.key).where(AuthAttempt.expires_at <= now).limit(200)
            )
            db.execute(delete(AuthAttempt).where(AuthAttempt.key.in_(expired)))
            for key, cap in limits:
                row = db.get(AuthAttempt, key)
                if row is None:
                    if (
                        db.scalar(select(func.count()).select_from(AuthAttempt)) or 0
                    ) >= 10000:
                        db.commit()
                        raise EmailAuthError("Too many requests; try again later", 429)
                    row = AuthAttempt(key=key, count=0, expires_at=now + seconds)
                    db.add(row)
                if row.expires_at <= now:
                    row.count, row.expires_at = 0, now + seconds
                row.count = min(row.count + 1, cap + 1)
                if row.count > cap:
                    account_allowed = False
            db.commit()
        if not account_allowed and not mail:
            raise EmailAuthError("Too many attempts; try again later", 429)
        return account_allowed

    @staticmethod
    def _collision(db: Session, email: str) -> bool:
        return (
            db.scalar(select(User.id).where(func.lower(User.email) == email).limit(1))
            is not None
            or db.scalar(
                select(EmailCredential.user_id)
                .where(EmailCredential.email_key == email)
                .limit(1)
            )
            is not None
        )

    def _delivery(self) -> MailSender:
        if self.sender is None:
            raise EmailAuthError(
                "Email delivery is not configured by the installation owner", 503
            )
        return self.sender

    def _send_challenge(
        self,
        purpose: Purpose,
        email: str,
        name: str,
        user_id: str | None,
        generation: str | None,
        now: int,
    ) -> None:
        sender = self._delivery()
        token = secrets.token_urlsafe(32)
        key = digest(token)
        with Session(self.store.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            expired = (
                select(EmailChallenge.token_hash)
                .where(
                    or_(
                        EmailChallenge.expires_at <= now,
                        EmailChallenge.consumed_at.is_not(None),
                    )
                )
                .limit(100)
            )
            db.execute(
                delete(EmailChallenge).where(EmailChallenge.token_hash.in_(expired))
            )
            if (
                db.scalar(select(func.count()).select_from(EmailChallenge)) or 0
            ) >= 10000:
                db.commit()
                return
            db.add(
                EmailChallenge(
                    token_hash=key,
                    purpose=purpose,
                    user_id=user_id,
                    email_key=email,
                    name=name,
                    generation=generation,
                    created_at=now,
                    expires_at=now + (1800 if purpose == "reset" else 86400),
                    consumed_at=None,
                )
            )
            db.commit()
        subject = (
            "Reset your LifeGather password"
            if purpose == "reset"
            else "Verify your LifeGather email"
        )
        link = f"{self.public_url}/#auth={purpose}&token={token}"
        body = (
            f"{subject}. Open this link and choose your password:\n\n{link}\n\n"
            "If you did not request this, ignore this email. This link is single-use."
        )
        try:
            sender.send(email, subject, body)
        except (OSError, ValueError):
            logger.warning(
                "Account email delivery failed; check installation SMTP settings"
            )
            with Session(self.store.engine) as db, db.begin():
                db.execute(
                    delete(EmailChallenge).where(EmailChallenge.token_hash == key)
                )

    def signup(self, name: str, email: str, *, client: str, now: int) -> None:
        self._delivery()
        key = email_key(email)
        if not name.strip() or len(name) > 100 or any(ord(c) < 32 for c in name):
            raise EmailAuthError("Enter a name between 1 and 100 characters")
        if not self._limits("mail", client, key, now):
            return
        with Session(self.store.engine) as db:
            if self._collision(db, key):
                return
        self._send_challenge("signup", key, name.strip(), None, None, now)

    def request_reset(self, email: str, *, client: str, now: int) -> None:
        self._delivery()
        key = email_key(email)
        if not self._limits("mail", client, key, now):
            return
        with Session(self.store.engine) as db:
            credential = db.scalar(
                select(EmailCredential).where(EmailCredential.email_key == key).limit(1)
            )
            if credential is None:
                return
            user = db.get(User, credential.user_id)
            assert user is not None
            user_id, name, generation = user.id, user.name, credential.generation
        self._send_challenge("reset", key, name, user_id, generation, now)

    def request_setup(self, actor: Account, *, client: str, now: int) -> None:
        self._delivery()
        key = email_key(actor.email)
        if not self._limits("mail", client, key, now):
            return
        with Session(self.store.engine) as db:
            user = db.get(User, actor.id)
            if (
                user is None
                or email_key(user.email) != key
                or db.get(EmailCredential, actor.id) is not None
            ):
                raise EmailAuthError(
                    "Password setup is unavailable; use password reset "
                    "for an existing password"
                )
            taken = db.scalar(
                select(EmailCredential.user_id)
                .where(EmailCredential.email_key == key)
                .limit(1)
            )
            if taken is not None:
                raise EmailAuthError("Password setup is unavailable")
        self._send_challenge("link", key, actor.name, actor.id, None, now)

    def login(
        self, email: str, password: str, *, client: str, now: int, old_token: str = ""
    ) -> SignedIn:
        key = email_key(email)
        self._limits("login", client, key, now)
        if len(password) > 128 or len(password.encode("utf-8")) > 512:
            raise EmailAuthError("Email or password is incorrect", 401)
        with Session(self.store.engine) as db:
            credential = db.scalar(
                select(EmailCredential).where(EmailCredential.email_key == key).limit(1)
            )
            hashed = credential.password_hash if credential else DUMMY_HASH
        valid = verify_password(hashed, password)
        if not valid or credential is None:
            raise EmailAuthError("Email or password is incorrect", 401)
        upgraded = (
            hash_password(password) if HASHER.check_needs_rehash(hashed) else hashed
        )
        with Session(self.store.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            current = db.get(EmailCredential, credential.user_id)
            if current is None or current.password_hash != hashed:
                raise EmailAuthError("Email or password is incorrect", 401)
            current.password_hash = upgraded
            user = db.get(User, current.user_id)
            assert user is not None
            self.store._cleanup(db, now)
            if old_token:
                db.execute(
                    delete(LoginSession).where(
                        LoginSession.token_hash == digest(old_token)
                    )
                )
            signed = self.store.issue_session(db, user, now)
            db.commit()
            return signed

    def complete(
        self,
        purpose: Purpose,
        token: str,
        password: str,
        *,
        client: str,
        now: int,
        actor: Account | None = None,
    ) -> None:
        self._limits("consume", client, None, now)
        if purpose not in {"signup", "reset", "link"} or not 20 <= len(token) <= 100:
            raise EmailAuthError("This link is invalid or expired")
        hashed = hash_password(password)
        with Session(self.store.engine) as db:
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
            challenge = db.get(EmailChallenge, digest(token))
            if (
                challenge is None
                or challenge.purpose != purpose
                or challenge.expires_at <= now
                or challenge.consumed_at is not None
            ):
                raise EmailAuthError("This link is invalid or expired")
            if purpose == "signup":
                if self._collision(db, challenge.email_key):
                    raise EmailAuthError(
                        "Sign in using your existing method or request another link"
                    )
                user_id = str(uuid4())
                user = User(
                    id=user_id,
                    issuer="lifegather:email",
                    subject=user_id,
                    email=challenge.email_key,
                    name=challenge.name,
                    created_at=now,
                )
                db.add(user)
                db.flush()
                credential = EmailCredential(
                    user_id=user_id,
                    email_key=challenge.email_key,
                    password_hash=hashed,
                    generation=str(uuid4()),
                    verified_at=now,
                )
                db.add(credential)
            elif purpose == "link":
                linked_user = db.get(User, challenge.user_id)
                if (
                    actor is None
                    or linked_user is None
                    or actor.id != linked_user.id
                    or email_key(linked_user.email) != challenge.email_key
                ):
                    raise EmailAuthError(
                        "Sign in to the account that requested password setup", 403
                    )
                if (
                    db.get(EmailCredential, actor.id) is not None
                    or db.scalar(
                        select(EmailCredential.user_id)
                        .where(EmailCredential.email_key == challenge.email_key)
                        .limit(1)
                    )
                    is not None
                ):
                    raise EmailAuthError("Password setup is unavailable")
                user_id = actor.id
                db.add(
                    EmailCredential(
                        user_id=user_id,
                        email_key=challenge.email_key,
                        password_hash=hashed,
                        generation=str(uuid4()),
                        verified_at=now,
                    )
                )
            else:
                reset_credential = db.get(EmailCredential, challenge.user_id)
                if (
                    reset_credential is None
                    or reset_credential.email_key != challenge.email_key
                    or reset_credential.generation != challenge.generation
                ):
                    raise EmailAuthError("This link is invalid or expired")
                user_id = reset_credential.user_id
                reset_credential.password_hash, reset_credential.generation = (
                    hashed,
                    str(uuid4()),
                )
            notification_email = challenge.email_key
            challenge.consumed_at = now
            db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
            db.execute(
                delete(EmailChallenge).where(
                    or_(
                        EmailChallenge.user_id == user_id,
                        EmailChallenge.email_key == challenge.email_key,
                    ),
                    EmailChallenge.token_hash != challenge.token_hash,
                )
            )
            db.commit()
        if purpose in {"link", "reset"} and self.sender is not None:
            try:
                self.sender.send(
                    notification_email,
                    "Your LifeGather password changed",
                    "Your LifeGather password changed. "
                    "Existing sessions were signed out. "
                    "If this was not you, contact your installation owner.",
                )
            except (OSError, ValueError):
                logger.warning("Password-change notification delivery failed")
