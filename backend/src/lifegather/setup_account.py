"""Interactive server-owner account provisioning; never exposed over HTTP."""

import argparse
import sys
import time
import warnings
from getpass import GetPassWarning, getpass

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from lifegather.auth.email_service import EmailAuth
from lifegather.auth.email_validation import EmailAuthError, email_key, password_value
from lifegather.auth.store import AuthStore
from lifegather.config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a private local sign-in account"
    )
    parser.parse_args(argv)  # No password arguments or environment-variable shortcuts.
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        print(
            "Use an interactive terminal (docker exec -it or docker compose exec).",
            file=sys.stderr,
        )
        return 1
    store: AuthStore | None = None
    try:
        settings = Settings()
        print(
            "Create a private account. "
            "The server owner accepts the email without verification."
        )
        name = input("Display name: ")
        email = email_key(input("Email: "))
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            password = getpass("Password (15–128 characters): ")
            confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise EmailAuthError("Passwords do not match; no account was created")
        password_value(password)
        store = AuthStore(settings.database())
        store.migrate()
        EmailAuth(store, None, settings.public_url).provision_local_account(
            name, email, password, now=int(time.time())
        )
        print(
            "Account created. Open LifeGather and sign in with your email and password."
        )
        return 0
    except EmailAuthError as exc:
        print(str(exc), file=sys.stderr)
    except (EOFError, KeyboardInterrupt):
        print("Setup cancelled.", file=sys.stderr)
    except GetPassWarning:
        print(
            "Cannot hide password input; use an interactive terminal.", file=sys.stderr
        )
    except (ValidationError, SQLAlchemyError, OSError):
        print(
            "Setup failed. Check installation configuration and data-directory access.",
            file=sys.stderr,
        )
    finally:
        if store is not None:
            store.engine.dispose()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
