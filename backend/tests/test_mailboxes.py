import asyncio
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from pydantic import SecretStr
from test_reconciliation import setup

from lifegather.config import Settings
from lifegather.credentials.service import PrivateSettings
from lifegather.mailboxes.provider import (
    READ_SCOPE,
    GmailGrant,
    GmailProvider,
    MailboxFailure,
)
from lifegather.mailboxes.service import Mailboxes
from lifegather.memory.notes import NoteConflict
from lifegather.memory.service import MemoryError


def provider(transport: httpx2.AsyncBaseTransport | None = None) -> GmailProvider:
    return GmailProvider(
        Settings(
            google_client_id="synthetic-client",
            google_client_secret=SecretStr("synthetic-secret"),
        ),
        transport,
    )


def test_gmail_flow_is_separate_readonly_pkce_and_bounded_fixed_endpoints() -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx2.Response(
                200,
                json={
                    "access_token": "synthetic-access",
                    "refresh_token": "synthetic-refresh",
                    "scope": READ_SCOPE,
                },
            )
        return httpx2.Response(200, json={"emailAddress": "Mailbox@Example.test"})

    client = provider(httpx2.MockTransport(respond))
    url = client.authorization_url("synthetic-state", "v" * 64)
    query = parse_qs(urlsplit(url).query)
    assert urlsplit(url).netloc == "accounts.google.com"
    assert query["scope"] == [READ_SCOPE]
    assert query["access_type"] == ["offline"]
    assert query["redirect_uri"] == ["http://127.0.0.1:8787/auth/gmail/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert "synthetic-secret" not in url and "v" * 64 not in url
    grant = asyncio.run(client.exchange("synthetic-code", "v" * 64))
    assert grant.address == "mailbox@example.test"
    assert grant.refresh_token.get_secret_value() == "synthetic-refresh"
    assert seen[0].url == "https://oauth2.googleapis.com/token"
    assert seen[1].url == "https://gmail.googleapis.com/gmail/v1/users/me/profile"
    assert seen[1].headers["authorization"] == "Bearer synthetic-access"
    assert "synthetic-refresh" not in repr(grant)


@pytest.mark.parametrize(
    "reply",
    [
        {"access_token": "x", "refresh_token": "r", "scope": "openid email"},
        {"access_token": "x", "scope": READ_SCOPE},
        {"error": "invalid_grant", "secret": "must-not-leak"},
    ],
)
def test_gmail_denied_or_incomplete_grants_are_redacted(reply: dict[str, str]) -> None:
    client = provider(httpx2.MockTransport(lambda _: httpx2.Response(200, json=reply)))
    with pytest.raises(MailboxFailure) as caught:
        asyncio.run(client.exchange("code", "v" * 64))
    assert "must-not-leak" not in str(caught.value)


def test_mailbox_session_bound_flow_private_vault_reconnect_and_disconnect(
    tmp_path: Path,
) -> None:
    auth, alice, bob, _, _ = setup(tmp_path)
    vault = PrivateSettings(auth.engine, b"s" * 32)
    service = Mailboxes(auth.engine, vault, clock=lambda: 100)
    state, verifier = service.begin(alice, "session-a", "browser-a")
    assert len(verifier) >= 43
    for actor, session, browser in [
        (bob, "session-a", "browser-a"),
        (alice, "wrong", "browser-a"),
        (alice, "session-a", "wrong"),
    ]:
        with pytest.raises(MemoryError):
            service.consume(actor, session, browser, state)
    assert service.consume(alice, "session-a", "browser-a", state) == verifier
    with pytest.raises(MemoryError):
        service.consume(alice, "session-a", "browser-a", state)
    grant = GmailGrant(
        address="mailbox@example.test", refresh_token=SecretStr("synthetic-refresh")
    )
    first = service.connect(alice, grant)
    assert len(service.list(alice)) == 1 and service.list(bob) == []
    assert "synthetic-refresh" not in str(first)
    with pytest.raises(MemoryError):
        service.disconnect(bob, first["id"], first["revision"])
    assert b"synthetic-refresh" not in auth.path.read_bytes()
    removed = service.disconnect(alice, first["id"], first["revision"])
    assert not removed["connected"]
    assert service.disconnect(alice, first["id"], first["revision"]) == removed
    next_row = service.connect(alice, grant)
    assert next_row["id"] == first["id"] and next_row["revision"] > first["revision"]
    with pytest.raises(NoteConflict):
        service.disconnect(alice, first["id"], first["revision"])
    auth.engine.dispose()


def test_flow_expiry_and_pending_flow_limit(tmp_path: Path) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    now = [100]
    service = Mailboxes(
        auth.engine, PrivateSettings(auth.engine, b"s" * 32), clock=lambda: now[0]
    )
    first, _ = service.begin(actor, "session", "browser")
    for _ in range(4):
        service.begin(actor, "session", "browser")
    with pytest.raises(MemoryError, match="Too many"):
        service.begin(actor, "session", "browser")
    now[0] = 700
    with pytest.raises(MemoryError):
        service.consume(actor, "session", "browser", first)
    service.begin(actor, "session", "browser")
    auth.engine.dispose()


def test_refresh_uses_fixed_token_endpoint_and_rejects_redirects() -> None:
    seen: list[httpx2.Request] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"access_token": "synthetic-access"})

    value = asyncio.run(
        provider(httpx2.MockTransport(respond)).access("synthetic-refresh")
    )
    assert value == "synthetic-access"
    assert seen[0].url == "https://oauth2.googleapis.com/token"
    assert b"refresh_token=synthetic-refresh" in seen[0].content
    bad = provider(
        httpx2.MockTransport(
            lambda _: httpx2.Response(
                302, headers={"Location": "https://untrusted.invalid"}
            )
        )
    )
    with pytest.raises(MailboxFailure):
        asyncio.run(bad.access("synthetic-refresh"))


def test_mailbox_snapshot_and_generic_vault_revocation(tmp_path: Path) -> None:
    from sqlalchemy.orm import Session

    from lifegather.auth.store import AuthStore
    from lifegather.mailboxes.models import Mailbox
    from lifegather.memory.backup import operator_snapshot

    auth, actor, _, _, _ = setup(tmp_path)
    vault = PrivateSettings(auth.engine, b"s" * 32)
    service = Mailboxes(auth.engine, vault)
    row = service.connect(
        actor,
        GmailGrant(
            address="synthetic@example.test",
            refresh_token=SecretStr("synthetic-refresh"),
        ),
    )
    snapshot = tmp_path / "snapshot.sqlite3"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(snapshot)
    restored.migrate()
    copied = Mailboxes(restored.engine, PrivateSettings(restored.engine, b"s" * 32))
    assert copied.list(actor) == service.list(actor)
    with Session(auth.engine) as db:
        mailbox = db.get(Mailbox, row["id"])
        assert mailbox is not None and mailbox.credential_id is not None
        identifier = mailbox.credential_id
    assert vault.read_secret(actor, identifier) == "synthetic-refresh"
    vault.remove(actor, identifier)
    assert service.list(actor)[0]["connected"] is False
    assert copied.list(actor)[0]["connected"] is True
    restored.engine.dispose()
    auth.engine.dispose()


def test_mailbox_http_consent_is_owned_and_single_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient
    from test_mcp_http import signed_headers

    from lifegather.mailboxes.routes import FLOW_COOKIE
    from lifegather.main import create_app

    key = tmp_path / "synthetic-vault.key"
    key.write_bytes(b"s" * 32)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_SECRET", "synthetic-secret")
    calls: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        calls.append(str(request.url))
        if request.url.host == "oauth2.googleapis.com":
            return httpx2.Response(
                200,
                json={
                    "access_token": "synthetic-access",
                    "refresh_token": "synthetic-refresh",
                    "scope": READ_SCOPE,
                },
            )
        return httpx2.Response(200, json={"emailAddress": "mailbox@example.test"})

    app = create_app()
    app.state.gmail_provider = provider(httpx2.MockTransport(respond))
    with TestClient(app) as client:
        alice, _ = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        assert client.get("/api/mailboxes").status_code == 401
        assert (
            client.post(
                "/api/mailboxes/google/start",
                headers={"Cookie": alice["Cookie"]},
                json={},
            ).status_code
            == 403
        )
        start = client.post("/api/mailboxes/google/start", headers=alice, json={})
        assert start.status_code == 200
        assert "httponly" in start.headers["set-cookie"].lower()
        state = parse_qs(urlsplit(start.json()["url"]).query)["state"][0]
        browser = client.cookies.get(FLOW_COOKIE)
        callback_headers = {
            **alice,
            "Cookie": alice["Cookie"] + "; " + FLOW_COOKIE + "=" + str(browser),
        }
        response = client.get(
            "/auth/gmail/callback",
            params={"state": state, "code": "synthetic"},
            headers=callback_headers,
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/?mailbox=connected"
        assert len(calls) == 2
        client.get(
            "/auth/gmail/callback",
            params={"state": state, "code": "synthetic"},
            headers=callback_headers,
            follow_redirects=False,
        )
        assert len(calls) == 2
        own = client.get("/api/mailboxes", headers=alice)
        assert own.headers["cache-control"] == "no-store"
        assert "synthetic-refresh" not in own.text
        assert "credential_id" not in own.text
        row = own.json()["items"][0]
        assert row["address"] == "mailbox@example.test"
        assert client.get("/api/mailboxes", headers=bob).json()["items"] == []
        body = {"mailbox_id": row["id"], "expected_revision": row["revision"]}
        assert (
            client.post("/api/mailboxes/disconnect", headers=bob, json=body).status_code
            == 400
        )
        assert (
            client.post("/api/mailboxes/disconnect", headers=alice, json=body).json()[
                "connected"
            ]
            is False
        )
        assert (
            client.post("/api/mailboxes/disconnect", content=b" " * 32769).status_code
            == 413
        )
