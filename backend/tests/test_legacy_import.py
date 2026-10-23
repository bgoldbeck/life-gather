import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from database_support import database
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session
from stored_files import files

from lifegather import legacy_import
from lifegather.auth.models import User
from lifegather.auth.store import Account, AuthStore
from lifegather.config import Settings
from lifegather.credentials.models import Credential
from lifegather.credentials.service import PrivateSettings
from lifegather.legacy_import import LegacyImportError, import_legacy, main
from lifegather.main import create_app
from lifegather.memory.service import MemoryService
from lifegather.photos.models import Photo
from lifegather.photos.service import PhotoService
from lifegather.recovery.bundle import RecoveryService
from lifegather.recovery.database import validate_database
from lifegather.storage import LocalStorage

pytestmark = pytest.mark.usefixtures("configured_database")

FIXTURES = Path(__file__).parent / "fixtures"
PASSPHRASE = b"synthetic legacy passphrase"


def legacy_copy(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    target = data / "auth.sqlite3"
    shutil.copy(FIXTURES / "legacy-0027.sqlite3", target)
    return target


def owner(store: AuthStore, email: str) -> Account:
    with Session(store.engine) as db:
        user = db.scalars(select(User).where(User.email == email)).one()
        return Account(user.id, user.email, user.name)


def check_imported(
    store: AuthStore, release: str = "0027", storage: LocalStorage | None = None
) -> None:
    storage = storage or files(store.engine)
    key = (FIXTURES / f"legacy-{release}.key").read_bytes()
    summary = validate_database(store.engine, key, storage)
    assert (summary.users, summary.credentials, summary.photos, summary.documents) == (
        2,
        1,
        1,
        1,
    )
    alice, bob = (owner(store, f"{name}@example.test") for name in ("alice", "bob"))
    memory = MemoryService(store.engine)
    assert [item["kind"] for item in memory.search(bob, "GARAGE shelf")] == ["source"]
    assert memory.search(alice, "garage shelf") == []
    with Session(store.engine) as db:
        photo = db.scalars(select(Photo)).one()
        credential = db.scalars(select(Credential)).one()
    assert len(
        PhotoService(store.engine, storage).binary(alice, photo.id, True)[0]
    ) == (photo.size)
    vault = PrivateSettings(store.engine, key)
    assert vault.read_secret(alice, credential.id) == "synthetic recovery credential"
    # New rows after the import must not collide with copied serial keys.
    store.login("carol", "carol@example.test", "Carol", now=10)


def test_import_copies_every_row_and_rebuilds_search(tmp_path: Path) -> None:
    source = legacy_copy(tmp_path)
    before = source.read_bytes()
    store = AuthStore(database(tmp_path / "target", empty=True))
    counts = import_legacy(source, store.engine)
    assert counts is not None and counts["users"] == 2 and counts["memory_fts"] > 0
    store.migrate()
    check_imported(store)
    assert import_legacy(source, store.engine) is None
    assert source.read_bytes() == before
    store.engine.dispose()


def test_first_start_imports_automatically_and_later_starts_ignore_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy_copy(tmp_path)
    url = database(tmp_path / "app", empty=True)
    monkeypatch.setenv("LIFEGATHER_DATABASE_URL", url)
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
    store = AuthStore(url)
    # The first start also moved the imported originals into `/data/files`.
    check_imported(store, storage=LocalStorage(tmp_path / "data" / "files"))
    with Session(store.engine) as db:
        assert db.scalar(text("SELECT count(*) FROM photos WHERE original IS NULL"))
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
    with Session(store.engine) as db:
        assert db.scalar(text("SELECT count(*) FROM users")) == 3
    store.engine.dispose()


def test_unsupported_or_damaged_sqlite_is_refused_and_leaves_postgresql_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = legacy_copy(tmp_path)
    store = AuthStore(database(tmp_path / "target", empty=True))
    with closing(sqlite3.connect(source)) as db:
        db.execute("UPDATE alembic_version SET version_num='0026_asset_types'")
        db.commit()
    with pytest.raises(LegacyImportError, match="Start LifeGather"):
        import_legacy(source, store.engine)
    source = legacy_copy(tmp_path)

    def broken(*args: object) -> dict[str, int]:
        raise LegacyImportError("Synthetic failure while loading")

    monkeypatch.setattr(legacy_import, "load_tables", broken)
    with pytest.raises(LegacyImportError, match="Synthetic"):
        import_legacy(source, store.engine)
    with store.engine.connect() as connection:
        assert inspect(connection).get_table_names() == []
    store.engine.dispose()


def test_command_imports_into_the_configured_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = legacy_copy(tmp_path)
    url = database(tmp_path / "target", empty=True)
    monkeypatch.setenv("LIFEGATHER_DATABASE_URL", url)
    assert main([str(source)]) == 0
    assert "Imported" in capsys.readouterr().out
    assert main([str(source)]) == 1
    assert "already has" in capsys.readouterr().err
    assert main([str(tmp_path / "missing.sqlite3")]) == 1


def test_sqlite_era_recovery_bundle_restores_into_postgresql(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "staging")
    (tmp_path / "staging").mkdir()
    service = RecoveryService(settings)
    bundle = FIXTURES / "legacy-0027.lgbackup"
    info = service.verify(bundle, PASSPHRASE)
    assert info.database.migration == "0027_forest_dark_theme"
    assert info.database.users == 2
    destination = tmp_path / "restored"
    url = database(destination, empty=True)
    assert service.restore(bundle, destination, PASSPHRASE, url) == info
    store = AuthStore(url)
    store.migrate()
    check_imported(store)
    store.engine.dispose()


def test_070_installation_keeps_its_stored_files_through_the_first_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    shutil.copytree(FIXTURES / "legacy-0029", data)
    stored = sorted(path for path in (data / "files").rglob("*") if path.is_file())
    url = database(tmp_path / "postgresql", empty=True)
    monkeypatch.setenv("LIFEGATHER_DATA_DIR", str(data))
    monkeypatch.setenv("LIFEGATHER_DATABASE_URL", url)
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
    store = AuthStore(url)
    with Session(store.engine) as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == (
            "0040_deleted_accounts"
        )
        assert (
            db.scalar(
                text("SELECT count(*) FROM photos WHERE original_key IS NOT NULL")
            )
            == 1
        )
    assert sorted(path for path in (data / "files").rglob("*") if path.is_file()) == (
        stored
    )
    check_imported(store, "0029", LocalStorage(data / "files"))
    store.engine.dispose()


def test_070_recovery_bundle_restores_into_postgresql(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "staging")
    (tmp_path / "staging").mkdir()
    service = RecoveryService(settings)
    bundle = FIXTURES / "legacy-0029.lgbackup"
    info = service.verify(bundle, PASSPHRASE)
    assert info.database.migration == "0029_receipt_detail_basis"
    destination = tmp_path / "restored"
    url = database(destination / "data", empty=True)
    assert service.restore(bundle, destination, PASSPHRASE, url) == info
    store = AuthStore(url)
    store.migrate()
    check_imported(store, "0029")
    store.engine.dispose()
