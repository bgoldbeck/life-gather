"""PostgreSQL engine, transaction modes and column types kept from SQLite."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import (
    Column,
    Connection,
    Engine,
    Integer,
    String,
    create_engine,
    event,
    text,
)
from sqlalchemy.engine import make_url
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

DRIVER = "postgresql+psycopg"
# One application-wide writer lock keeps SQLite's single-writer guarantees.
WRITER_LOCK = 0x4C47_5752  # "LGWR"
DETERMINISTIC_COLLATIONS = frozenset({"C", "C.UTF-8", "C.utf8", "POSIX", "ucs_basic"})


# Row-level security (migration 0033) shows this role only the rows whose owner
# matches `lifegather.account_id`. The connecting user stays unrestricted.
ACCOUNT_ROLE = "lifegather_account"
# The account a request or job acts for; None is the trusted system context
# (startup, migrations, schedulers, sweeps and operator recovery).
ACTING_ACCOUNT: ContextVar[str | None] = ContextVar("acting_account", default=None)


class DatabaseConfigurationError(ValueError):
    pass


def bind_account(user_id: str) -> None:
    """Bind the rest of this request's context to one account."""
    ACTING_ACCOUNT.set(user_id)


@contextmanager
def account_scope(user_id: str | None) -> Iterator[None]:
    """Act for one account (or the system for None) until the block ends."""
    token = ACTING_ACCOUNT.set(user_id)
    try:
        yield
    finally:
        ACTING_ACCOUNT.reset(token)


_UNBOUND = object()


def _scope_connection(dbapi_connection: Any, record: Any, proxy: Any) -> None:
    """Switch each checked-out connection to the acting account, or back."""
    account = ACTING_ACCOUNT.get()
    if record.info.get("account", _UNBOUND) == account:
        return
    with dbapi_connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config('role', %s, false), "
            "set_config('lifegather.account_id', %s, false)",
            (ACCOUNT_ROLE if account is not None else "none", account or ""),
        )
    # Session-level settings survive the commit; later transactions can still
    # choose their isolation level first.
    dbapi_connection.commit()
    record.info["account"] = account


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
    engine = create_engine(
        database_url(url),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args={"connect_timeout": 15, "application_name": "lifegather"},
    )
    event.listen(engine, "checkout", _scope_connection)
    return engine


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
