"""Start a throwaway LifeGather server for the browser end-to-end checks.

Run from frontend/ (Playwright does this through playwright.config.ts):

    uv run --project ../backend --locked python e2e/serve.py

It creates a fresh PostgreSQL database on the server named by
LIFEGATHER_E2E_DATABASE_URL (falling back to LIFEGATHER_TEST_DATABASE_URL),
a temporary data directory, and one synthetic local account, then serves the
built UI from frontend/dist with uvicorn. Everything is removed on exit.
"""

import os
import shutil
import signal
import sys
import tempfile
import time
from pathlib import Path
from types import FrameType

import psycopg
import uvicorn
from sqlalchemy.engine import make_url

PORT = int(os.environ.get("LIFEGATHER_E2E_PORT", "8797"))
# Synthetic credentials; this account exists only inside the throwaway database.
NAME = "E2E Tester"
EMAIL = "e2e.tester@example.test"
PASSWORD = "synthetic-e2e-password-1"


def admin_url() -> str:
    url = os.environ.get("LIFEGATHER_E2E_DATABASE_URL") or os.environ.get(
        "LIFEGATHER_TEST_DATABASE_URL"
    )
    if not url:
        sys.exit(
            "Set LIFEGATHER_E2E_DATABASE_URL (or LIFEGATHER_TEST_DATABASE_URL) to a "
            "PostgreSQL server URL whose user may create databases."
        )
    return url


def main() -> None:
    frontend = Path(__file__).resolve().parent.parent
    static = frontend / "dist"
    if not (static / "index.html").is_file():
        sys.exit("Build the UI first: npm run build")

    server = make_url(admin_url())
    name = f"lifegather_e2e_{os.getpid()}"
    plain = server.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(plain, autocommit=True) as connection:
        connection.execute(f'DROP DATABASE IF EXISTS "{name}"')
        connection.execute(f'CREATE DATABASE "{name}" TEMPLATE template0')
    database = server.set(drivername="postgresql+psycopg", database=name)
    data = Path(tempfile.mkdtemp(prefix="lifegather-e2e-"))

    os.environ.update(
        {
            "LIFEGATHER_DATA_DIR": str(data),
            "LIFEGATHER_DATABASE_URL": database.render_as_string(hide_password=False),
            "LIFEGATHER_STATIC_DIR": str(static),
            "LIFEGATHER_PUBLIC_URL": f"http://127.0.0.1:{PORT}",
            "LIFEGATHER_TEST_LOGIN_ENABLED": "false",
            "LIFEGATHER_MIGRATE_ON_START": "true",
            "LIFEGATHER_GOOGLE_CLIENT_ID": "",
            "LIFEGATHER_GOOGLE_CLIENT_SECRET": "",
            "LIFEGATHER_CONFIGURATION_FILE": "",
        }
    )

    from lifegather.auth.email_service import EmailAuth
    from lifegather.auth.store import AuthStore
    from lifegather.config import Settings

    settings = Settings()
    store = AuthStore(settings.database())
    store.migrate()
    EmailAuth(store, None, settings.public_url).provision_local_account(
        NAME, EMAIL, PASSWORD, now=int(time.time())
    )

    def stop(signum: int, frame: FrameType | None) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        uvicorn.run(
            "lifegather.main:create_app",
            factory=True,
            host="127.0.0.1",
            port=PORT,
            log_level="warning",
        )
    finally:
        shutil.rmtree(data, ignore_errors=True)
        with psycopg.connect(plain, autocommit=True) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


if __name__ == "__main__":
    main()
