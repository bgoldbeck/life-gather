"""Test helper: the app's default local file storage beside a test database."""

from database_support import paths
from sqlalchemy import Engine

from lifegather.storage import LocalStorage


def files(engine: Engine) -> LocalStorage:
    # Matches the default `<data_dir>/files` for the test path behind the database.
    database = engine.url.database
    assert database
    return LocalStorage(paths[database] / "files")
