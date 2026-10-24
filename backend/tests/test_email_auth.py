from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from database_support import database
from sqlalchemy import func, select

from lifegather.auth.email_models import EmailCredential
from lifegather.auth.email_service import EmailAuth, EmailAuthError
from lifegather.auth.email_validation import password_value
from lifegather.auth.models import User
from lifegather.auth.store import AuthStore

PASSWORD = "a very long test passphrase 42!"


class Mailbox:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []
        self.fail = False

    def send(self, recipient: str, subject: str, body: str) -> None:
        if self.fail:
            raise OSError("secret provider error")
        self.messages.append((recipient, subject, body))

    def token(self) -> str:
        link = next(
            word for word in self.messages[-1][2].split() if word.startswith("http")
        )
        return parse_qs(urlsplit(link).fragment)["token"][0]


def setup(tmp_path: Path) -> tuple[AuthStore, EmailAuth, Mailbox]:
    store = AuthStore(database(tmp_path))
    store.migrate()
    mailbox = Mailbox()
    return store, EmailAuth(store, mailbox, "http://127.0.0.1:8787"), mailbox


def test_signup_verification_and_password_session(tmp_path: Path) -> None:
    store, auth, mail = setup(tmp_path)
    auth.signup("Alice", "Alice@example.test", client="ip", now=100)
    token = mail.token()
    with store.engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(User)) == 0
    with pytest.raises(EmailAuthError):
        auth.login("alice@example.test", PASSWORD, client="ip", now=101)
    auth.complete("signup", token, PASSWORD, client="ip", now=102)
    signed = auth.login("ALICE@example.test", PASSWORD, client="ip", now=103)
    current = store.authenticate(signed.token, now=104)
    assert current is not None and current.user.id == signed.user.id
    with store.engine.connect() as connection:
        hashed = connection.scalar(select(EmailCredential.password_hash))
        assert isinstance(hashed, str)
        assert hashed.startswith("$argon2id$") and PASSWORD not in hashed
    with pytest.raises(EmailAuthError):
        auth.complete("signup", token, PASSWORD, client="ip", now=105)


def test_reset_revokes_sessions_tokens_and_requires_native_identity(
    tmp_path: Path,
) -> None:
    store, auth, mail = setup(tmp_path)
    auth.signup("Alice", "a@example.test", client="ip", now=100)
    auth.complete("signup", mail.token(), PASSWORD, client="ip", now=101)
    signed = auth.login("a@example.test", PASSWORD, client="ip", now=102)
    auth.request_reset("a@example.test", client="ip", now=200)
    token = mail.token()
    auth.complete("reset", token, PASSWORD + " new", client="ip", now=201)
    assert store.authenticate(signed.token, now=202) is None
    with pytest.raises(EmailAuthError):
        auth.login("a@example.test", PASSWORD, client="ip", now=203)
    assert (
        auth.login("a@example.test", PASSWORD + " new", client="ip", now=204).user.id
        == signed.user.id
    )
    google = store.login("google", "google@example.test", "G", now=300)
    count = len(mail.messages)
    auth.request_reset(google.user.email, client="ip", now=301)
    auth.request_reset("absent@example.test", client="ip", now=302)
    assert len(mail.messages) == count


def test_google_linking_is_explicit_and_same_account_only(tmp_path: Path) -> None:
    store, auth, mail = setup(tmp_path)
    google = store.login("one", "a@example.test", "A", now=100).user
    other = store.login("two", "b@example.test", "B", now=100).user
    auth.signup("New", google.email, client="ip", now=101)
    assert mail.messages == []
    auth.request_setup(google, client="ip", now=102)
    token = mail.token()
    with pytest.raises(EmailAuthError):
        auth.complete("link", token, PASSWORD, client="ip", now=103, actor=other)
    auth.complete("link", token, PASSWORD, client="ip", now=104, actor=google)
    assert auth.login(google.email, PASSWORD, client="ip", now=105).user.id == google.id
    assert store.login("one", google.email, "A", now=106).user.id == google.id


def test_expiry_purpose_failed_delivery_and_concurrent_consumption(
    tmp_path: Path,
) -> None:
    _, auth, mail = setup(tmp_path)
    auth.signup("A", "a@example.test", client="ip", now=100)
    token = mail.token()
    with pytest.raises(EmailAuthError):
        auth.complete("reset", token, PASSWORD, client="ip", now=101)
    with pytest.raises(EmailAuthError):
        auth.complete("signup", token, PASSWORD, client="ip", now=100 + 86400)
    auth.signup("B", "b@example.test", client="ip", now=200)
    token = mail.token()

    def finish(_: int) -> bool:
        try:
            auth.complete("signup", token, PASSWORD, client="ip", now=201)
            return True
        except EmailAuthError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sum(pool.map(finish, range(2))) == 1
    mail.fail = True
    auth.signup("C", "c@example.test", client="ip", now=300)
    with pytest.raises(EmailAuthError):
        auth.login("c@example.test", PASSWORD, client="ip", now=301)


def test_persistent_throttles_and_unconfigured_delivery(tmp_path: Path) -> None:
    store, auth, mail = setup(tmp_path)
    for _ in range(5):
        auth.signup("A", "a@example.test", client="ip", now=100)
    assert len(mail.messages) == 3
    for _ in range(10):
        with pytest.raises(EmailAuthError):
            auth.login("missing@example.test", PASSWORD, client="ip", now=200)
    reopened = EmailAuth(store, mail, "http://127.0.0.1:8787")
    with pytest.raises(EmailAuthError, match="Too many"):
        reopened.login("missing@example.test", PASSWORD, client="ip", now=201)
    disabled = EmailAuth(store, None, "http://127.0.0.1:8787")
    with pytest.raises(EmailAuthError, match="delivery"):
        disabled.signup("A", "a@example.test", client="ip", now=5000)


def test_no_automatic_google_linking_and_other_reset_tokens_are_invalidated(
    tmp_path: Path,
) -> None:
    from lifegather.auth.store import InvalidFlow

    store, auth, mail = setup(tmp_path)
    auth.signup("A", "a@example.test", client="ip", now=100)
    auth.complete("signup", mail.token(), PASSWORD, client="ip", now=101)
    with pytest.raises(InvalidFlow):
        store.login("unlinked-google", "a@example.test", "A", now=102)
    auth.request_reset("a@example.test", client="ip", now=4000)
    first = mail.token()
    auth.request_reset("a@example.test", client="ip", now=4001)
    second = mail.token()
    auth.complete("reset", second, PASSWORD + " newer", client="ip", now=4002)
    with pytest.raises(EmailAuthError):
        auth.complete("reset", first, PASSWORD, client="ip", now=4003)


@pytest.mark.parametrize("implicit", [False, True])
def test_smtp_uses_verified_tls_before_credentials(implicit: bool) -> None:
    from unittest.mock import patch

    from lifegather.auth.mail import SmtpSender

    target = "lifegather.auth.mail.smtplib." + ("SMTP_SSL" if implicit else "SMTP")
    with patch(target) as factory:
        client = factory.return_value.__enter__.return_value
        sender = SmtpSender(
            "smtp.example.test",
            465 if implicit else 587,
            "fixture-user",
            "fixture-secret",
            "sender@example.test",
            implicit,
        )
        sender.send("a@example.test", "Fixture subject", "Fixture body")
        client.login.assert_called_once_with("fixture-user", "fixture-secret")
        client.send_message.assert_called_once()
        if implicit:
            assert factory.call_args.kwargs["context"].check_hostname is True
        else:
            assert client.starttls.call_args.kwargs["context"].check_hostname is True
            assert [call[0] for call in client.method_calls].index("starttls") < [
                call[0] for call in client.method_calls
            ].index("login")
            client.reset_mock()
            client.starttls.side_effect = OSError("TLS failed")
            with pytest.raises(OSError):
                sender.send("a@example.test", "Fixture subject", "Fixture body")
            client.login.assert_not_called()


def test_password_length_policy_allows_twelve_characters() -> None:
    assert password_value("twelve-chars") == "twelve-chars"
    with pytest.raises(EmailAuthError, match="between 12 and 128"):
        password_value("eleven-char")
    with pytest.raises(EmailAuthError, match="between 12 and 128"):
        password_value("x" * 129)
    with pytest.raises(EmailAuthError, match="less common"):
        password_value("123456789012")
