"""Throwaway PostgreSQL databases for the backend tests.

Set LIFEGATHER_TEST_DATABASE_URL to a server URL whose user may create
databases (for example postgresql://postgres:secret@127.0.0.1:5432/postgres).
Without it, the suite starts a private temporary cluster when PostgreSQL's
`initdb` is installed. Each test path gets its own database.
"""

import atexit
import hashlib
import os
import shutil
import socket
import subprocess
import tempfile
import time
from glob import glob
from pathlib import Path

import psycopg
from sqlalchemy.engine import URL, make_url

# Per process, so concurrent test runs on one server never share a template.
TEMPLATE = f"lifegather_test_template_{os.getpid()}"
CREATE = "TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C'"

_server: URL | None = None
_created: list[str] = []


def _binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    candidates = sorted(glob(f"/usr/lib/postgresql/*/bin/{name}"))
    return candidates[-1] if candidates else None


def _launch() -> URL:
    initdb, pg_ctl = _binary("initdb"), _binary("pg_ctl")
    if not initdb or not pg_ctl or (hasattr(os, "geteuid") and os.geteuid() == 0):
        raise RuntimeError(
            "Set LIFEGATHER_TEST_DATABASE_URL to a PostgreSQL server for tests "
            "(or install PostgreSQL and run the tests as a non-root user)"
        )
    root = Path(tempfile.mkdtemp(prefix="lifegather-pg-"))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    subprocess.run(
        [initdb, "-D", str(root / "data"), "-A", "trust", "-U", "postgres"],
        check=True,
        capture_output=True,
    )
    options = (
        f"-p {port} -c listen_addresses=127.0.0.1 -k {root} -c fsync=off "
        "-c synchronous_commit=off -c full_page_writes=off -c max_connections=200"
    )
    subprocess.run(
        [pg_ctl, "-D", str(root / "data"), "-o", options, "-w", "start"],
        check=True,
        capture_output=True,
    )

    def stop() -> None:
        subprocess.run(
            [pg_ctl, "-D", str(root / "data"), "-m", "immediate", "stop"],
            capture_output=True,
        )
        shutil.rmtree(root, ignore_errors=True)

    atexit.register(stop)
    return make_url(f"postgresql+psycopg://postgres@127.0.0.1:{port}/postgres")


def _admin(statement: str) -> None:
    assert _server is not None
    with psycopg.connect(
        _server.set(drivername="postgresql").render_as_string(hide_password=False),
        autocommit=True,
    ) as connection:
        connection.execute(statement)


def url(name: str) -> str:
    assert _server is not None
    return _server.set(drivername="postgresql+psycopg", database=name).render_as_string(
        hide_password=False
    )


def start() -> None:
    """Connect to the test server and build one migrated template database."""
    global _server
    if _server is not None:
        return
    configured = os.environ.get("LIFEGATHER_TEST_DATABASE_URL", "").strip()
    _server = make_url(configured) if configured else _launch()
    for _ in range(50):
        try:
            _admin("SELECT 1")
            break
        except psycopg.OperationalError:
            time.sleep(0.2)
    _admin(f"DROP DATABASE IF EXISTS {TEMPLATE} WITH (FORCE)")
    _admin(f"CREATE DATABASE {TEMPLATE} {CREATE}")
    from lifegather.auth.store import AuthStore

    store = AuthStore(url(TEMPLATE))
    try:
        store.migrate()
    finally:
        store.engine.dispose()


# Database name -> the test path it stands for (its stand-in data directory).
paths: dict[str, Path] = {}


def database(path: Path, *, empty: bool = False) -> str:
    """A database owned by this test path: migrated to head unless `empty`."""
    name = "lg_" + hashlib.sha256(str(path.absolute()).encode()).hexdigest()[:24]
    if name not in _created:
        start()
        _admin(
            f"CREATE DATABASE {name} " + (CREATE if empty else f"TEMPLATE {TEMPLATE}")
        )
        _created.append(name)
    paths[name] = path
    return url(name)


def drop_created() -> None:
    while _created:
        _admin(f"DROP DATABASE IF EXISTS {_created.pop()} WITH (FORCE)")


def finish() -> None:
    if _server is not None:
        drop_created()
        _admin(f"DROP DATABASE IF EXISTS {TEMPLATE} WITH (FORCE)")


def restore_copy(snapshot: Path) -> str:
    """Restore an operator snapshot into a new database for this path."""
    from sqlalchemy import create_engine, make_url

    from lifegather.memory.backup import restore_snapshot

    target = database(snapshot, empty=True)
    # Like a SQLite snapshot file, the copy shares its directory's `files/`.
    paths[str(make_url(target).database)] = snapshot.parent
    engine = create_engine(target)
    try:
        with snapshot.open("rb") as source:
            restore_snapshot(source, engine)
    finally:
        engine.dispose()
    return target
