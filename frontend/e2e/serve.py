"""Start a throwaway LifeGather server for the browser end-to-end checks.

Run from frontend/ (Playwright does this through playwright.config.ts):

    uv run --project ../backend --locked python e2e/serve.py

It creates a fresh PostgreSQL database on the server named by
LIFEGATHER_E2E_DATABASE_URL (falling back to LIFEGATHER_TEST_DATABASE_URL),
a temporary data directory, and one synthetic local account, then serves the
built UI from frontend/dist with uvicorn. Everything is removed on exit.

With LIFEGATHER_E2E_TWO_ACCOUNTS=true it also provisions a second synthetic
account. uvicorn runs as a child process: creating the file named by
restart_marker() stops it and starts a new one on the same database and data
directory, and the file is removed once the new process has started.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import FrameType

import psycopg
from sqlalchemy.engine import make_url

PORT = int(os.environ.get("LIFEGATHER_E2E_PORT", "8797"))
# Synthetic credentials; this account exists only inside the throwaway database.
NAME = "E2E Tester"
EMAIL = "e2e.tester@example.test"
PASSWORD = "synthetic-e2e-password-1"
SECOND_NAME = "E2E Second Tester"
SECOND_EMAIL = "e2e.second@example.test"
SECOND_PASSWORD = "synthetic-e2e-password-2"


def restart_marker() -> Path:
    # Matches restartInstallation() in e2e/support.ts.
    return Path(tempfile.gettempdir()) / f"lifegather-e2e-{PORT}.restart"


def start_server() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "lifegather.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ]
    )


def stop_server(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


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
    email = EmailAuth(store, None, settings.public_url)
    email.provision_local_account(NAME, EMAIL, PASSWORD, now=int(time.time()))
    if os.environ.get("LIFEGATHER_E2E_TWO_ACCOUNTS") == "true":
        email.provision_local_account(
            SECOND_NAME, SECOND_EMAIL, SECOND_PASSWORD, now=int(time.time())
        )

    def stop(signum: int, frame: FrameType | None) -> None:
        # Playwright signals the whole process group, so uv may pass on a second
        # SIGTERM; ignore it so the cleanup below is not interrupted.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    marker = restart_marker()
    marker.unlink(missing_ok=True)
    process = start_server()
    try:
        while process.poll() is None:
            if marker.exists():
                stop_server(process)
                process = start_server()
                marker.unlink(missing_ok=True)
            time.sleep(0.2)
        sys.exit(f"The LifeGather server exited with status {process.returncode}")
    except KeyboardInterrupt:
        pass
    finally:
        stop_server(process)
        marker.unlink(missing_ok=True)
        shutil.rmtree(data, ignore_errors=True)
        with psycopg.connect(plain, autocommit=True) as connection:
            connection.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


if __name__ == "__main__":
    main()
