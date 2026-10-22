from pathlib import Path

import pytest
from database_support import database
from fastapi.testclient import TestClient

from lifegather.main import create_app


@pytest.mark.usefixtures("legacy_audit_writer")
def test_chat_preference_migration_preserves_existing_settings(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config

    import lifegather
    from lifegather.auth.store import AuthStore
    from lifegather.chat.preferences import ChatPreferences
    from lifegather.credentials.service import PrivateSettings
    from lifegather.memory.schemas import SourceInput
    from lifegather.memory.service import MemoryService

    store = AuthStore(database(tmp_path / "legacy", empty=True))
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with store.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0011_appearance")
    actor = store.login("legacy", "legacy@example.test", "Legacy", now=100).user
    settings = PrivateSettings(store.engine, None)
    settings.set_theme(actor, "dark")
    settings.set_preferences(actor, True)
    memory = MemoryService(store.engine)
    original = memory.ingest(actor, SourceInput(text="Synthetic preexisting memory"))
    store.migrate()
    assert settings.theme(actor) == "forest-dark"
    assert settings.preferences(actor) is True
    assert ChatPreferences(store.engine).get(actor).model == ""
    assert memory.get_source(actor, original.id).text == original.text


def test_chat_choices_are_private_validated_and_do_not_enable_ai() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/chat/preferences").status_code == 401
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "alice@example.test", "Alice", now=2000000000)
        bob = store.login("bob", "bob@example.test", "Bob", now=2000000000)
        vault = client.app.state.private_settings  # type: ignore[attr-defined]
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        vault.cipher = AESGCM(bytes(32))
        credential = vault.save(
            alice.user, "ai", "openai", "Synthetic", "synthetic-key"
        )
        foreign = vault.save(bob.user, "ai", "anthropic", "Other", "other-key")
        client.cookies.set("lifegather_session", alice.token)
        headers = {
            "Origin": "http://127.0.0.1:8787",
            "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"],
        }
        choice = {"credential_id": credential.id, "model": "synthetic-model"}
        assert client.get("/api/chat/preferences").json() == {
            "credential_id": "",
            "model": "",
        }
        assert client.put("/api/chat/preferences", json=choice).status_code == 403
        assert (
            client.put(
                "/api/chat/preferences", json=choice, headers=headers
            ).status_code
            == 204
        )
        assert client.get("/api/chat/preferences").json() == choice
        assert client.get("/api/settings").json()["allow_external_ai"] is False
        assert (
            client.put(
                "/api/chat/preferences",
                json={**choice, "credential_id": foreign.id},
                headers=headers,
            ).status_code
            == 404
        )
        assert (
            client.put(
                "/api/chat/preferences",
                json={**choice, "model": "https://evil.test"},
                headers=headers,
            ).status_code
            == 422
        )
        client.cookies.set("lifegather_session", bob.token)
        assert client.get("/api/chat/preferences").json() == {
            "credential_id": "",
            "model": "",
        }
        vault.remove(alice.user, credential.id)
        client.cookies.set("lifegather_session", alice.token)
        assert client.get("/api/chat/preferences").json() == {
            "credential_id": "",
            "model": "",
        }
