"""Optional sign-up bot checks and the terms-of-use gate (Phase 5.5)."""

import json
import time
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_email_auth import Mailbox
from test_mcp_http import rpc, signed_headers

from lifegather.auth.bot_check import TurnstileCheck
from lifegather.auth.models import User
from lifegather.auth.routes import SESSION_COOKIE
from lifegather.config import Settings
from lifegather.main import create_app

pytestmark = pytest.mark.usefixtures("configured_database")

ORIGIN = "http://127.0.0.1:8787"


class FakeCheck:
    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    def verify(self, token: str, remote_ip: str) -> bool:
        self.seen.append((token, remote_ip))
        return token == "passed"


def sign_in(client: TestClient, subject: str) -> tuple[dict[str, str], str]:
    store = client.app.state.auth_store  # type: ignore[attr-defined]
    signed = store.login(
        subject, subject + "@example.test", subject.title(), now=int(time.time())
    )
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, signed.token)
    csrf = client.get("/auth/session").json()["csrf_token"]
    return {"origin": ORIGIN, "x-csrf-token": csrf}, signed.user.id


def acceptance(app: Any, user_id: str) -> tuple[str | None, int | None]:
    with app.state.auth_store.engine.connect() as connection:
        row = connection.execute(
            text("SELECT terms_version, terms_accepted_at FROM users WHERE id = :u"),
            {"u": user_id},
        ).one()
    return row[0], row[1]


def test_protections_are_off_by_default() -> None:
    mail = Mailbox()
    app = create_app(mail_sender=mail)
    assert app.state.bot_check is None
    with TestClient(app) as client:
        anonymous = client.get("/auth/session").json()
        assert anonymous["bot_check_site_key"] is None
        assert anonymous["terms"] is None
        assert client.get("/auth/terms").status_code == 404
        response = client.post(
            "/auth/email/request/signup",
            json={"email": "a@example.test", "name": "Alice"},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 202 and mail.token()
        _, _ = sign_in(client, "alice")
        assert client.get("/api/assets").status_code == 200


def test_bot_check_guards_signup_and_reset_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_TURNSTILE_SITE_KEY", "0x4AAAAAAAsynthetic")
    monkeypatch.setenv("LIFEGATHER_TURNSTILE_SECRET_KEY", "synthetic-secret")
    mail = Mailbox()
    app = create_app(mail_sender=mail)
    assert isinstance(app.state.bot_check, TurnstileCheck)
    check = FakeCheck()
    app.state.bot_check = check
    with TestClient(app) as client:
        assert (
            client.get("/auth/session").json()["bot_check_site_key"]
            == "0x4AAAAAAAsynthetic"
        )
        for action, body in (
            ("signup", {"email": "a@example.test", "name": "Alice"}),
            ("reset", {"email": "a@example.test"}),
        ):
            for token in ("", "failed"):
                refused = client.post(
                    f"/auth/email/request/{action}",
                    json={**body, "bot_token": token},
                    headers={"Origin": ORIGIN},
                )
                assert refused.status_code == 400
                assert refused.json()["detail"] == (
                    "Complete the bot check and try again"
                )
            assert not mail.messages
        response = client.post(
            "/auth/email/request/signup",
            json={"email": "a@example.test", "name": "Alice", "bot_token": "passed"},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 202 and mail.token()
        assert check.seen[-1] == ("passed", "testclient")
        # Password sign-in is unchanged: limited per address, no widget.
        assert (
            client.post(
                "/auth/email/login",
                json={"email": "a@example.test", "password": "wrong"},
                headers={"Origin": ORIGIN},
            ).status_code
            == 401
        )


def test_bot_check_settings_need_both_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIFEGATHER_TURNSTILE_SITE_KEY", "0x4AAAAAAAsynthetic")
    with pytest.raises(ValidationError, match="Turnstile"):
        Settings()


def test_turnstile_verification_fails_closed() -> None:
    sent: list[bytes] = []

    def answer(success: bool | None, status: int = 200) -> Any:
        def handler(request: httpx2.Request) -> httpx2.Response:
            sent.append(request.content)
            if success is None:
                raise httpx2.ConnectError("offline")
            return httpx2.Response(status, json={"success": success})

        return httpx2.MockTransport(handler)

    assert TurnstileCheck("secret", answer(True)).verify("token", "192.0.2.1")
    assert b"secret=secret" in sent[-1] and b"remoteip=192.0.2.1" in sent[-1]
    assert not TurnstileCheck("secret", answer(False)).verify("token", "192.0.2.1")
    assert not TurnstileCheck("secret", answer(True, 500)).verify("t", "192.0.2.1")
    assert not TurnstileCheck("secret", answer(None)).verify("token", "192.0.2.1")
    count = len(sent)
    assert not TurnstileCheck("secret", answer(True)).verify("", "192.0.2.1")
    assert len(sent) == count


def test_terms_gate_blocks_the_app_until_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_TERMS_VERSION", "2026-10-23")
    app = create_app()
    with TestClient(app) as client:
        anonymous = client.get("/auth/session").json()
        assert anonymous["terms"] == {"version": "2026-10-23", "accepted": False}
        terms = client.get("/auth/terms").json()
        assert terms["version"] == "2026-10-23"
        assert terms["text"].startswith("PLACEHOLDER TERMS OF USE")

        headers, user_id = sign_in(client, "alice")
        session = client.get("/auth/session").json()
        assert session["user"]["id"] == user_id
        assert session["terms"] == {"version": "2026-10-23", "accepted": False}
        blocked = client.get("/api/assets")
        assert blocked.status_code == 403
        assert blocked.json()["detail"] == "Accept the terms of use to continue"
        assert client.get("/api/me").status_code == 403

        assert (
            client.post(
                "/auth/terms/accept", json={"version": "2026-01-01"}, headers=headers
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/auth/terms/accept",
                json={"version": "2026-10-23"},
                headers={"origin": ORIGIN},
            ).status_code
            == 403
        )
        accepted = client.post(
            "/auth/terms/accept", json={"version": "2026-10-23"}, headers=headers
        )
        assert accepted.status_code == 204
        assert client.get("/auth/session").json()["terms"]["accepted"] is True
        assert client.get("/api/assets").status_code == 200
        first = acceptance(app, user_id)
        assert first[0] == "2026-10-23" and first[1] is not None
        # Accepting again keeps the original acceptance time.
        client.post(
            "/auth/terms/accept", json={"version": "2026-10-23"}, headers=headers
        )
        assert acceptance(app, user_id) == first

    # A new version asks again; the old acceptance stays recorded.
    monkeypatch.setenv("LIFEGATHER_TERMS_VERSION", "2026-11-01")
    app = create_app()
    with TestClient(app) as client:
        headers, same_id = sign_in(client, "alice")
        assert same_id == user_id
        assert client.get("/auth/session").json()["terms"]["accepted"] is False
        assert client.get("/api/assets").status_code == 403
        assert acceptance(app, user_id) == first


def test_pending_terms_still_allow_sign_out_and_deletion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_TERMS_VERSION", "v1")
    app = create_app()
    with TestClient(app) as client:
        headers, user_id = sign_in(client, "leaver")
        deleted = client.post(
            "/api/account/delete",
            json={"email": "leaver@example.test"},
            headers=headers,
        )
        assert deleted.status_code == 200 and deleted.json()["deleted"] is True
        with Session(app.state.auth_store.engine) as db:
            assert db.get(User, user_id) is None

        headers, _ = sign_in(client, "quitter")
        assert client.post("/auth/logout", headers=headers).status_code == 204
        assert client.get("/auth/session").json()["user"] is None


def test_pending_terms_block_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIFEGATHER_TERMS_VERSION", "v1")
    app = create_app()
    with TestClient(app) as client:
        headers, user = signed_headers(app, "mcp-alice")
        response = rpc(client, headers, "memory_find_entities", {"name": "x"})
        assert response.status_code == 403
        assert "terms of use" in json.dumps(response.json())
        app.state.auth_store.accept_terms(user.id, "v1", now=int(time.time()))
        allowed = rpc(client, headers, "memory_find_entities", {"name": "x"})
        assert allowed.status_code == 200
        assert not allowed.json()["result"].get("isError")


def test_custom_terms_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    terms = tmp_path / "terms.md"
    terms.write_text("Synthetic installation terms <b>not html</b>")
    monkeypatch.setenv("LIFEGATHER_TERMS_VERSION", "v2")
    monkeypatch.setenv("LIFEGATHER_TERMS_FILE", str(terms))
    with TestClient(create_app()) as client:
        assert client.get("/auth/terms").json() == {
            "version": "v2",
            "text": "Synthetic installation terms <b>not html</b>",
        }
        terms.unlink()
        assert client.get("/auth/terms").status_code == 503
