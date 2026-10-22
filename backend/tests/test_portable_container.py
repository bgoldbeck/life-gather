import base64
import threading
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from database_support import database
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from lifegather import migrate
from lifegather.auth.store import AuthStore
from lifegather.config import Settings
from lifegather.credentials.service import (
    PrivateSettings,
    VaultError,
    VaultKeyring,
    read_keyring,
    rotate_vault_key,
)
from lifegather.main import create_app
from lifegather.startup import StartupError, run_startup_tasks, schema_current
from lifegather.storage.local import LocalStorage


def encoded(key: bytes) -> str:
    return base64.b64encode(key).decode()


def test_vault_keys_from_environment_with_ids(tmp_path: Path) -> None:
    first, second = AESGCM.generate_key(256), AESGCM.generate_key(256)
    keyring = read_keyring(
        Settings(
            vault_keys=SecretStr(f"2026-10:{encoded(first)}, old:{encoded(second)}")
        )
    )
    assert keyring is not None
    assert keyring.active_id == "2026-10" and keyring.active == first
    assert [key_id for key_id, _ in keyring.keys] == ["2026-10", "old"]
    # A key file alone stays the active key; beside env keys it is a previous one.
    path = tmp_path / "secrets" / "vault.key"
    path.parent.mkdir()
    path.write_bytes(second)
    alone = read_keyring(Settings(vault_key_file=path))
    assert alone is not None and alone.keys == (("file", second),)
    both = read_keyring(
        Settings(vault_keys=SecretStr(f"new:{encoded(first)}"), vault_key_file=path)
    )
    assert both is not None and both.keys == (("new", first), ("file", second))
    assert read_keyring(Settings()) is None
    for bad in (
        encoded(first),
        f"id:{encoded(first[:16])}",
        "id:not base64!",
        f"bad id:{encoded(first)}",
        f"a:{encoded(first)},a:{encoded(second)}",
        f"a:{encoded(first)},b:{encoded(first)}",
    ):
        with pytest.raises(ValueError) as error:
            read_keyring(Settings(vault_keys=SecretStr(bad)))
        assert encoded(first) not in str(error.value)


def test_rotation_reencrypts_and_stale_instances_refuse_writes(
    tmp_path: Path,
) -> None:
    auth = AuthStore(database(tmp_path))
    auth.migrate()
    alice = auth.login("alice", "a@example.test", "A", now=1).user
    old, new = AESGCM.generate_key(256), AESGCM.generate_key(256)
    stale = PrivateSettings(auth.engine, old)
    entry = stale.save(alice, "ai", "example", "Personal", "synthetic-secret")

    keyring = VaultKeyring((("new", new), ("old", old)))
    assert rotate_vault_key(auth.engine, keyring)
    assert not rotate_vault_key(auth.engine, keyring)

    current = PrivateSettings(auth.engine, new)
    assert current.read_secret(alice, entry.id) == "synthetic-secret"
    with pytest.raises(VaultError) as error:
        stale.replace(alice, entry.id, "written-under-old-key")
    assert error.value.status == 503
    with pytest.raises(VaultError):
        stale.save(alice, "ai", "example", "Second", "another")
    with pytest.raises(VaultError):
        PrivateSettings(auth.engine, old)
    assert current.read_secret(alice, entry.id) == "synthetic-secret"
    with pytest.raises(VaultError):
        rotate_vault_key(
            auth.engine,
            VaultKeyring((("other", AESGCM.generate_key(256)), ("old", old))),
        )


def test_concurrent_startups_serialize(tmp_path: Path) -> None:
    url = database(tmp_path, empty=True)
    stores = [AuthStore(url), AuthStore(url)]
    errors: list[BaseException] = []

    def start(store: AuthStore) -> None:
        try:
            run_startup_tasks(store, LocalStorage(tmp_path / "files"), tmp_path, None)
        except BaseException as error:  # pragma: no cover - reported below
            errors.append(error)

    threads = [threading.Thread(target=start, args=(store,)) for store in stores]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert schema_current(stores[0].engine)
    for store in stores:
        store.engine.dispose()


def test_migrate_job_then_app_without_startup_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = database(tmp_path / "job", empty=True)
    monkeypatch.setenv("LIFEGATHER_DATABASE_URL", url)
    monkeypatch.setenv("LIFEGATHER_MIGRATE_ON_START", "false")
    key = AESGCM.generate_key(256)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEYS", f"k1:{encoded(key)}")

    with pytest.raises(StartupError):
        with TestClient(create_app()):
            pass

    assert migrate.main([]) == 0
    with TestClient(create_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json() == {"status": "ready"}
        assert ready.headers["cache-control"] == "no-store"
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        with store.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='0001'"))
        assert client.get("/health/ready").status_code == 503
        assert client.app.state.private_settings.enabled  # type: ignore[attr-defined]


def test_rotation_runs_at_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old, new = AESGCM.generate_key(256), AESGCM.generate_key(256)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEYS", f"old:{encoded(old)}")
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "a@example.test", "A", now=1).user
        vault = client.app.state.private_settings  # type: ignore[attr-defined]
        entry = vault.save(alice, "ai", "example", "Personal", "synthetic-secret")
    monkeypatch.setenv(
        "LIFEGATHER_VAULT_KEYS", f"new:{encoded(new)},old:{encoded(old)}"
    )
    with TestClient(create_app()) as client:
        vault = client.app.state.private_settings  # type: ignore[attr-defined]
        assert vault.read_secret(alice, entry.id) == "synthetic-secret"
    monkeypatch.setenv("LIFEGATHER_VAULT_KEYS", f"new:{encoded(new)}")
    with TestClient(create_app()) as client:
        vault = client.app.state.private_settings  # type: ignore[attr-defined]
        assert vault.read_secret(alice, entry.id) == "synthetic-secret"


def peer(app: object) -> None:
    def echo(request: Request) -> dict[str, str | None]:
        return {
            "client": request.client.host if request.client else None,
            "scheme": request.url.scheme,
        }

    app.add_api_route("/echo", echo)  # type: ignore[attr-defined]


def test_forwarded_headers_only_from_trusted_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    forwarded = {"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Proto": "https"}
    app = create_app()
    peer(app)
    with TestClient(app, client=("10.0.0.5", 50000)) as client:
        assert client.get("/echo", headers=forwarded).json() == {
            "client": "10.0.0.5",
            "scheme": "http",
        }

    monkeypatch.setenv("LIFEGATHER_TRUSTED_PROXIES", "10.0.0.0/24, 192.0.2.1")
    app = create_app()
    peer(app)
    with TestClient(app, client=("10.0.0.5", 50000)) as client:
        assert client.get("/echo", headers=forwarded).json() == {
            "client": "203.0.113.9",
            "scheme": "https",
        }
    app = create_app()
    peer(app)
    with TestClient(app, client=("198.51.100.7", 50000)) as client:
        assert client.get("/echo", headers=forwarded).json() == {
            "client": "198.51.100.7",
            "scheme": "http",
        }

    with pytest.raises(ValueError):
        Settings(trusted_proxies="*")
