"""Test helper: the app's default local file storage beside a test database."""

from pathlib import Path

from sqlalchemy import Engine

from lifegather.storage import LocalStorage


def files(engine: Engine) -> LocalStorage:
    # Matches the default `<data_dir>/files` next to `<data_dir>/auth.sqlite3`.
    database = engine.url.database
    assert database
    return LocalStorage(Path(database).parent / "files")
