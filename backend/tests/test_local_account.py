from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from lifegather.auth.email_models import EmailCredential
from lifegather.auth.email_service import EmailAuth, EmailAuthError
from lifegather.auth.models import User
from lifegather.auth.store import AuthStore

PASSWORD = "a private local testing passphrase!"


def test_concurrent_setup_creates_only_one_account(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.migrate()
    auth = EmailAuth(store, None, "http://127.0.0.1:8787")

    def attempt(_: int) -> bool:
        try:
            auth.provision_local_account(
                "Tester", "test@example.test", PASSWORD, now=100
            )
            return True
        except EmailAuthError as exc:
            assert exc.status == 409
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(attempt, range(2))) == 1
    with Session(store.engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(EmailCredential)) == 1


def test_local_account_uses_normal_login_without_mail(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.migrate()
    auth = EmailAuth(store, None, "http://127.0.0.1:8787")
    account = auth.provision_local_account(
        "Tester", "Tester@example.test", PASSWORD, now=100
    )
    signed = auth.login("tester@example.test", PASSWORD, client="test", now=101)
    assert signed.user.id == account.id
    assert store.authenticate(signed.token, now=102) is not None
    with Session(store.engine) as db:
        credential = db.get(EmailCredential, account.id)
        assert credential is not None
        assert credential.password_hash.startswith("$argon2id$")
        assert PASSWORD not in credential.password_hash
    with pytest.raises(EmailAuthError, match="already exists"):
        auth.provision_local_account(
            "Replacement", "TESTER@example.test", PASSWORD + "new", now=103
        )
    assert auth.login("tester@example.test", PASSWORD, client="test", now=104)


def test_local_account_does_not_claim_existing_google_identity(tmp_path: Path) -> None:
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.migrate()
    with Session(store.engine) as db, db.begin():
        db.add(
            User(
                id="google-user",
                issuer="https://accounts.google.com",
                subject="google-sub",
                email="Tester@example.test",
                name="Google user",
                created_at=1,
            )
        )
    auth = EmailAuth(store, None, "http://127.0.0.1:8787")
    with pytest.raises(EmailAuthError, match="already exists"):
        auth.provision_local_account("Tester", "tester@example.test", PASSWORD, now=100)
    with Session(store.engine) as db:
        assert db.scalar(select(func.count()).select_from(EmailCredential)) == 0


@pytest.mark.parametrize(
    "name,email,password",
    [
        ("", "a@example.test", PASSWORD),
        ("Tester", "invalid", PASSWORD),
        ("Tester", "a@example.test", "short"),
    ],
)
def test_invalid_local_account_leaves_no_user(
    tmp_path: Path, name: str, email: str, password: str
) -> None:
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.migrate()
    with pytest.raises(EmailAuthError):
        EmailAuth(store, None, "http://127.0.0.1:8787").provision_local_account(
            name, email, password, now=100
        )
    with Session(store.engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
