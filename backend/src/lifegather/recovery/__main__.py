"""Explicit local operator commands. Never starts or replaces an installation."""

import argparse
import getpass
import json
import secrets
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from lifegather.config import Settings
from lifegather.recovery.bundle import RecoveryService
from lifegather.recovery.envelope import RecoveryError


class _RecoveryStorage(BaseSettings):
    """Keep local path guards without requiring the lost app configuration."""

    model_config = SettingsConfigDict(
        env_prefix="LIFEGATHER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )
    data_dir: Path = Path("data")
    static_dir: Path | None = None
    # Restore target: an empty PostgreSQL database, never a command argument.
    database_url: SecretStr = SecretStr("")


def _verification_settings() -> Settings:
    # Supply every application field explicitly so unrelated environment values
    # cannot override defaults or trigger login/mail validation during recovery.
    # Only storage paths retain normal environment/dotenv precedence and guards.
    arguments: dict[str, Any] = {
        name: field.get_default(call_default_factory=True)
        for name, field in Settings.model_fields.items()
    }
    storage = _RecoveryStorage()
    arguments.update(data_dir=storage.data_dir, static_dir=storage.static_dir)
    arguments["_env_file"] = None
    return Settings(**arguments)


def _password(path: Path | None, *, confirm: bool) -> bytes:
    if path is not None:
        if not path.is_file():
            raise RecoveryError("Choose a regular private passphrase file")
        with path.open("rb") as source:
            value = source.read(1027)
        if value.endswith(b"\r\n"):
            value = value[:-2]
        elif value.endswith(b"\n"):
            value = value[:-1]
        if b"\n" in value or b"\r" in value:
            raise RecoveryError("The passphrase file must contain one UTF-8 line")
        try:
            value.decode("utf-8")
        except UnicodeError:
            raise RecoveryError("Use a UTF-8 passphrase file") from None
    else:
        if not sys.stdin.isatty():
            raise RecoveryError(
                "Use --passphrase-file when interactive input is unavailable"
            )
        value = getpass.getpass("Recovery passphrase: ").encode("utf-8")
        if confirm:
            repeated = getpass.getpass("Repeat recovery passphrase: ").encode("utf-8")
            if not secrets.compare_digest(value, repeated):
                raise RecoveryError("Passphrases do not match")
    if not 12 <= len(value) <= 1024:
        raise RecoveryError("Use a passphrase containing 12 to 1024 UTF-8 bytes")
    return value


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="python -m lifegather.recovery",
        description=(
            "Operator-only encrypted installation recovery. Includes every user's "
            "records, original files, authentication state and private credentials. "
            "Restore creates a new directory, loads an empty PostgreSQL database "
            "named by LIFEGATHER_DATABASE_URL, and never starts the app."
        ),
        allow_abbrev=False,
    )
    commands = result.add_subparsers(dest="command", required=True)
    backup = commands.add_parser(
        "backup", help="Create a new encrypted bundle", allow_abbrev=False
    )
    backup.add_argument("output", type=Path)
    backup.add_argument("--data-dir", type=Path)
    backup.add_argument("--configuration-file", type=Path)
    verify = commands.add_parser(
        "verify", help="Authenticate and validate a bundle", allow_abbrev=False
    )
    verify.add_argument("bundle", type=Path)
    restore = commands.add_parser(
        "restore", help="Recover into a new private directory", allow_abbrev=False
    )
    restore.add_argument("bundle", type=Path)
    restore.add_argument("destination", type=Path)
    for command in (backup, verify, restore):
        command.add_argument(
            "--staging-dir",
            type=Path,
            help="Use an existing private directory for temporary plaintext staging",
        )
        command.add_argument(
            "--passphrase-file",
            type=Path,
            help=(
                "Read a private UTF-8 file instead of prompting; "
                "never put a passphrase in arguments"
            ),
        )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "backup":
            overrides: dict[str, Any] = {}
            if args.data_dir is not None:
                overrides["data_dir"] = args.data_dir
            if args.configuration_file is not None:
                overrides["configuration_file"] = args.configuration_file
            settings = Settings(**overrides)
        else:
            # Verification/recovery must work when the original JSON file is lost.
            settings = _verification_settings()
        service = RecoveryService(settings, staging_dir=args.staging_dir)
        password = _password(args.passphrase_file, confirm=args.command == "backup")
        if args.command == "backup":
            info = service.create(args.output, password)
        elif args.command == "verify":
            info = service.verify(args.bundle, password)
        else:
            target = _RecoveryStorage().database_url.get_secret_value()
            if not target:
                raise RecoveryError(
                    "Set LIFEGATHER_DATABASE_URL to the new, empty PostgreSQL database"
                )
            info = service.restore(args.bundle, args.destination, password, target)
        summary = {"operation": args.command, **asdict(info)}
        if args.command == "restore":
            summary["configuration_file"] = str(
                (args.destination / "installation.json").resolve()
            )
        print(json.dumps(summary, sort_keys=True))
        return 0
    except RecoveryError as error:
        print("Recovery failed: " + str(error), file=sys.stderr)
        return 1
    except (ValueError, OSError):
        print(
            "Recovery failed: unable to read configuration or recovery files",
            file=sys.stderr,
        )
        return 1
    except KeyboardInterrupt:
        print("Recovery cancelled", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
