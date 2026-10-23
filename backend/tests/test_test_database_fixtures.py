import os
from pathlib import Path

import database_support
from sqlalchemy.engine import make_url


def test_service_allocates_only_its_requested_database(tmp_path: Path) -> None:
    value = database_support.database(tmp_path)
    assert database_support._created == [make_url(value).database]


def test_configured_database_is_explicit_and_test_local(
    configured_database: str,
) -> None:
    assert os.environ["LIFEGATHER_DATABASE_URL"] == configured_database
    assert database_support._created == [make_url(configured_database).database]
