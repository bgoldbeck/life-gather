from pathlib import Path

from fastapi.testclient import TestClient

from lifegather.auth.store import AuthStore
from lifegather.credentials.service import PrivateSettings
from lifegather.main import create_app


def test_appearance_migration_preserves_existing_ai_consent(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    import lifegather

    store = AuthStore(tmp_path / "legacy.sqlite3")
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with store.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0010_private_photos")
    signed = store.login("legacy", "legacy@example.test", "Legacy", now=100)
    with store.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO user_settings(user_id,allow_external_ai) VALUES (:id,1)"),
            {"id": signed.user.id},
        )
    store.migrate()
    settings = PrivateSettings(store.engine, None)
    assert settings.theme(signed.user) == "system"
    assert settings.preferences(signed.user) is True


def test_appearance_is_private_persistent_and_preserves_consent() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/appearance").status_code == 401
        store: AuthStore = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "alice@example.test", "Alice", now=2000000000)
        bob = store.login("bob", "bob@example.test", "Bob", now=2000000000)
        client.cookies.set("lifegather_session", alice.token)
        headers = {
            "origin": "http://127.0.0.1:8787",
            "x-csrf-token": client.get("/auth/session").json()["csrf_token"],
        }
        assert client.get("/api/appearance").json() == {"theme": "system"}
        assert client.put("/api/appearance", json={"theme": "dark"}).status_code == 403
        assert (
            client.put(
                "/api/settings", json={"allow_external_ai": True}, headers=headers
            ).status_code
            == 204
        )
        assert (
            client.put(
                "/api/appearance", json={"theme": "dark"}, headers=headers
            ).status_code
            == 204
        )
        assert client.get("/api/settings").json()["allow_external_ai"] is True
        assert client.get("/auth/session").json()["appearance"] == "dark"
        assert (
            client.put(
                "/api/settings", json={"allow_external_ai": False}, headers=headers
            ).status_code
            == 204
        )
        assert client.get("/api/appearance").json() == {"theme": "dark"}
        assert (
            client.put(
                "/api/appearance", json={"theme": "unknown"}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.put(
                "/api/appearance",
                json={"theme": "light", "user_id": bob.user.id},
                headers=headers,
            ).status_code
            == 422
        )
        client.cookies.set("lifegather_session", bob.token)
        assert client.get("/api/appearance").json() == {"theme": "system"}
        client.cookies.set("lifegather_session", alice.token)
        assert client.get("/api/appearance").json() == {"theme": "dark"}
