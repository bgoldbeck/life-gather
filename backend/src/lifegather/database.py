"""PostgreSQL engine, transaction modes and column types kept from SQLite."""

from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import (
    Column,
    Connection,
    Engine,
    Integer,
    String,
    create_engine,
    text,
)
from sqlalchemy.engine import make_url
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

DRIVER = "postgresql+psycopg"
# One application-wide writer lock keeps SQLite's single-writer guarantees.
WRITER_LOCK = 0x4C47_5752  # "LGWR"
DETERMINISTIC_COLLATIONS = frozenset({"C", "C.UTF-8", "C.utf8", "POSIX", "ucs_basic"})


class DatabaseConfigurationError(ValueError):
    pass


# Integers previously stored in SQLite were 64-bit and text was unbounded. Keep
# the same storage contract so existing values (microsecond timestamps, long
# identifiers) migrate unchanged; Pydantic validation bounds new input. Only
# column definitions change: casts in queries keep their declared types.
@compiles(Integer, "postgresql")
def _integer(element: Integer, compiler: Any, **kw: Any) -> str:
    if isinstance(kw.get("type_expression"), Column):
        return "BIGINT"
    return str(compiler.visit_integer(element, **kw))


@compiles(String, "postgresql")
def _string(element: String, compiler: Any, **kw: Any) -> str:
    if isinstance(kw.get("type_expression"), Column):
        return "TEXT"
    return str(compiler.visit_string(element, **kw))


def database_url(value: str) -> str:
    """Validate a PostgreSQL URL and select the psycopg driver."""
    value = value.strip()
    scheme = urlsplit(value).scheme
    if scheme not in {"postgresql", "postgres", DRIVER}:
        raise DatabaseConfigurationError(
            "Set LIFEGATHER_DATABASE_URL to a postgresql:// connection URL"
        )
    url = make_url(value).set(drivername=DRIVER)
    if not url.database:
        raise DatabaseConfigurationError("The database URL must name a database")
    return url.render_as_string(hide_password=False)


def create_database_engine(url: str) -> Engine:
    return create_engine(
        database_url(url),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={"connect_timeout": 15, "application_name": "lifegather"},
    )


def check_collation(connection: Connection) -> None:
    """Refuse locale collations: cursors and ordering rely on byte order."""
    collation = connection.scalar(
        text("SELECT datcollate FROM pg_database WHERE datname = current_database()")
    )
    if collation not in DETERMINISTIC_COLLATIONS:
        raise DatabaseConfigurationError(
            "Create the LifeGather database with the C collation "
            "(for example: CREATE DATABASE lifegather TEMPLATE template0 "
            "ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C')"
        )


def begin_snapshot(db: Session | Connection) -> None:
    """Start a consistent read: every statement sees the same committed data."""
    connection = db.connection() if isinstance(db, Session) else db
    connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")


def begin_serialized(db: Session | Connection) -> None:
    """Start a write that waits for, then excludes, other serialized writers."""
    connection = db.connection() if isinstance(db, Session) else db
    connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": WRITER_LOCK})
