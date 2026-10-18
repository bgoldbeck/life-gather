import time

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_email_auth import PASSWORD, Mailbox

from lifegather.auth.email_models import EmailChallenge
from lifegather.auth.store import SESSION_SECONDS
from lifegather.main import create_app

ORIGIN = {"Origin": "http://127.0.0.1:8787"}


def test_http_signup_login_and_reset_revocation() -> None:
    mail = Mailbox()
    app = create_app(mail_sender=mail)
    with TestClient(app) as client:
        payload = {"email": "a@example.test", "name": "Alice"}
        assert (
            client.post("/auth/email/request/signup", json=payload).status_code == 403
        )
        response = client.post(
            "/auth/email/request/signup", json=payload, headers=ORIGIN
        )
        assert response.status_code == 202 and "token" not in response.text
        token = mail.token()
        assert client.get("/auth/session").json()["user"] is None
        with app.state.auth_store.engine.connect() as connection:
            assert connection.scalar(select(EmailChallenge.token_hash)) != token
        response = client.post(
            "/auth/email/complete",
            json={"purpose": "signup", "token": token, "password": PASSWORD},
            headers=ORIGIN,
        )
        assert response.status_code == 204
        assert client.get("/auth/session").json()["user"] is None
        response = client.post(
            "/auth/email/login",
            json={"email": "a@example.test", "password": PASSWORD},
            headers=ORIGIN,
        )
        assert response.status_code == 204
        assert (
            "HttpOnly" in response.headers["set-cookie"]
            and "SameSite=lax" in response.headers["set-cookie"]
        )
        session = client.get("/auth/session").json()
        assert session["email_password_enabled"] is True
        assert client.get("/api/me").json()["id"] == session["user"]["id"]
        old_cookie = client.cookies.get("lifegather_session")
        known = client.post(
            "/auth/email/request/reset",
            json={"email": "a@example.test"},
            headers=ORIGIN,
        )
        unknown = client.post(
            "/auth/email/request/reset",
            json={"email": "missing@example.test"},
            headers=ORIGIN,
        )
        assert (
            known.status_code == unknown.status_code == 202
            and known.json() == unknown.json()
        )
        reset_token = mail.token()
        response = client.post(
            "/auth/email/complete",
            json={
                "purpose": "reset",
                "token": reset_token,
                "password": PASSWORD + " new",
            },
            headers=ORIGIN,
        )
        assert response.status_code == 204
        assert (
            app.state.auth_store.authenticate(old_cookie, now=int(time.time())) is None
        )
        assert client.get("/api/me").status_code == 401


def test_http_redaction_body_limits_and_unavailable_mail() -> None:
    app = create_app()
    with TestClient(app) as client:
        assert (
            client.post(
                "/auth/email/request/signup",
                json={"email": "a@example.test", "name": "A"},
                headers=ORIGIN,
            ).status_code
            == 503
        )
        assert client.get("/auth/session").json()["email_delivery_enabled"] is False
        secret = "private-password-that-must-not-echo"
        response = client.post(
            "/auth/email/login",
            json={"email": "a@example.test", "password": secret, "user_id": "injected"},
            headers=ORIGIN,
        )
        assert response.status_code == 422 and secret not in response.text
        assert (
            client.post(
                "/auth/email/login",
                content=b"x" * 16385,
                headers={**ORIGIN, "Content-Type": "application/json"},
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/auth/email/login",
                json={"email": "a@example.test", "password": secret},
                headers={**ORIGIN, "Sec-Fetch-Site": "cross-site"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/auth/email/login", content="email=x", headers=ORIGIN
            ).status_code
            == 415
        )
        response = client.post(
            "/auth/email/login",
            json={"email": "a@example.test", "password": secret},
            headers=ORIGIN,
        )
        assert response.status_code == 401 and secret not in response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["referrer-policy"] == "no-referrer"


def test_signed_in_setup_is_csrf_protected_and_preserves_workspace() -> None:
    mail = Mailbox()
    app = create_app(mail_sender=mail)
    with TestClient(app) as client:
        store = app.state.auth_store
        signed = store.login(
            "google-user", "g@example.test", "Google", now=int(time.time())
        )
        client.cookies.set("lifegather_session", signed.token)
        session = client.get("/auth/session").json()
        assert (
            client.post("/auth/email/setup", json={}, headers=ORIGIN).status_code == 403
        )
        headers = {**ORIGIN, "X-CSRF-Token": session["csrf_token"]}
        assert (
            client.post("/auth/email/setup", json={}, headers=headers).status_code
            == 202
        )
        token = mail.token()
        request = {"purpose": "link", "token": token, "password": PASSWORD}
        assert (
            client.post(
                "/auth/email/complete", json=request, headers=ORIGIN
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/auth/email/complete", json=request, headers=headers
            ).status_code
            == 204
        )
        client.cookies.clear()
        assert (
            client.post(
                "/auth/email/login",
                json={"email": "g@example.test", "password": PASSWORD},
                headers=ORIGIN,
            ).status_code
            == 204
        )
        assert client.get("/api/me").json()["id"] == signed.user.id
        app.state.email_auth.sender = None
        assert (
            client.post(
                "/auth/email/login",
                json={"email": "g@example.test", "password": PASSWORD},
                headers=ORIGIN,
            ).status_code
            == 204
        )
        assert client.get("/api/me").json()["id"] == signed.user.id


def test_migration_backfills_google_identities_preserving_sessions_and_settings() -> (
    None
):
    # The existing migration fixtures exercise 0001 and 0003 -> head. Here also
    # verify a pre-existing Google identity remains stable after reopening.
    app = create_app()
    with TestClient(app):
        store = app.state.auth_store
        before = store.login("subject", "g@example.test", "G", now=100)
        store.migrate()
        assert (
            store.login("subject", "changed@example.test", "G", now=101).user.id
            == before.user.id
        )
        assert (
            store.authenticate(before.token, now=100 + SESSION_SECONDS - 1) is not None
        )
