from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from lifegather.auth.store import AuthStore
from lifegather.credentials.keygen import generate
from lifegather.main import create_app


def login(client: TestClient, subject: str) -> dict[str, str]:
    store: AuthStore = client.app.state.auth_store  # type: ignore[attr-defined]
    signed = store.login(subject, subject + "@example.test", subject, now=2000000000)
    client.cookies.clear()
    client.cookies.set("lifegather_session", signed.token)
    csrf = client.get("/auth/session").json()["csrf_token"]
    return {"origin": "http://127.0.0.1:8787", "x-csrf-token": csrf}


def test_private_api_isolation_and_no_secret_echo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = tmp_path / "secrets" / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    with TestClient(create_app()) as client:
        assert client.get("/api/settings").status_code == 401
        assert client.get("/api/credentials").status_code == 401
        alice_headers = login(client, "alice")
        payload = {
            "kind": "ai",
            "provider": "example",
            "label": "Mine",
            "secret": "synthetic-sensitive-token",
        }
        assert client.post("/api/credentials", json=payload).status_code == 403
        created = client.post("/api/credentials", json=payload, headers=alice_headers)
        assert created.status_code == 201
        entry = created.json()
        assert "secret" not in entry and "ciphertext" not in entry
        assert payload["secret"] not in created.text
        assert client.get("/api/credentials").json()["items"] == [entry]
        assert client.get("/api/credentials").headers["cache-control"] == "no-store"
        assert (
            client.put(
                "/api/settings", json={"allow_external_ai": True}, headers=alice_headers
            ).status_code
            == 204
        )
        bob_headers = login(client, "bob")
        assert client.get("/api/settings").json()["allow_external_ai"] is False
        assert client.get("/api/credentials?user_id=alice").json()["items"] == []
        path = "/api/credentials/" + entry["id"]
        assert client.get(path).status_code in {404, 405}
        assert (
            client.put(path, json={"secret": "attack"}, headers=bob_headers).status_code
            == 404
        )
        assert client.delete(path, headers=bob_headers).status_code == 404
        # A different session's CSRF token cannot authorize writes.
        assert (
            client.post(
                "/api/credentials", json=payload, headers=alice_headers
            ).status_code
            == 403
        )
        forged = client.post(
            "/api/credentials",
            json={**payload, "user_id": "alice"},
            headers=bob_headers,
        )
        assert forged.status_code == 422
        assert payload["secret"] not in forged.text
        invalid = client.post(
            "/api/credentials",
            json={**payload, "provider": "../invalid"},
            headers=bob_headers,
        )
        assert invalid.status_code == 422
        assert payload["secret"] not in invalid.text
        oversized = client.post(
            "/api/credentials", content=b"x" * 32769, headers=bob_headers
        )
        assert oversized.status_code == 413
        alice_headers = login(client, "alice")
        assert client.get("/api/settings").json()["allow_external_ai"] is True
        assert (
            client.put(
                path, json={"secret": "replacement"}, headers=alice_headers
            ).status_code
            == 200
        )
        assert client.delete(path, headers=alice_headers).status_code == 204
        assert client.get("/api/credentials").json()["items"] == []


def test_missing_key_and_generation_safety(tmp_path: Path) -> None:
    key = tmp_path / "vault.key"
    generate(key)
    original = key.read_bytes()
    assert len(original) == 32
    with pytest.raises(FileExistsError):
        generate(key)
    assert key.read_bytes() == original
    with TestClient(create_app()) as client:
        headers = login(client, "alice")
        assert client.get("/api/settings").json()["vault_configured"] is False
        assert (
            client.post(
                "/api/credentials",
                json={
                    "kind": "ai",
                    "provider": "example",
                    "label": "Mine",
                    "secret": "fake",
                },
                headers=headers,
            ).status_code
            == 503
        )


def test_migration_preserves_existing_accounts(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    import lifegather

    store = AuthStore(tmp_path / "existing.sqlite3")
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with store.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001_accounts")
    from sqlalchemy.orm import Session

    from lifegather.auth.models import User

    with Session(store.engine) as db, db.begin():
        legacy = User(
            id="legacy-user",
            issuer="https://accounts.google.com",
            subject="existing",
            email="a@example.test",
            name="Existing",
            created_at=100,
        )
        db.add(legacy)
        db.flush()
        session = store.issue_session(db, legacy, 100)
    store.migrate()
    assert store.authenticate(session.token, now=101) is not None
    with store.engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0016_receipt_currencies"
        )
