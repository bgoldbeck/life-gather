"""Explicit local operator commands. Never starts or replaces an installation."""

import argparse
import getpass
import json
import secrets
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from lifegather.auth.deletion_ledger import (
    LedgerEntry,
    ledger_entries,
    read_ledger,
    write_ledger,
)
from lifegather.config import Settings
from lifegather.database import create_database_engine
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
    backup_retention_days: int = Field(default=35, ge=1, le=3650)


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


def _export_deletions(output: Path) -> int:
    engine = create_database_engine(Settings().database())
    try:
        entries = ledger_entries(engine)
    finally:
        engine.dispose()
    target = output.parent.resolve() / output.name
    if target.exists() or target.is_symlink():
        raise RecoveryError("Choose a new file for the deleted-account list")
    write_ledger(target, entries)
    print(json.dumps({"operation": "export-deletions", "accounts": len(entries)}))
    return 0


def _drill(
    service: RecoveryService,
    args: argparse.Namespace,
    password: bytes,
    target: str,
    deleted: list[LedgerEntry],
    storage: _RecoveryStorage,
) -> int:
    if not (0 < args.rpo_hours <= 24 * 3650 and 0 < args.rto_minutes <= 60 * 24 * 30):
        raise RecoveryError("Choose positive RPO and RTO targets")
    report = service.drill(
        args.bundle,
        password,
        target,
        rpo_target_seconds=round(args.rpo_hours * 3600),
        rto_target_seconds=round(args.rto_minutes * 60),
        retention_days=storage.backup_retention_days,
        deleted_accounts=deleted,
    )
    raw = json.dumps({"operation": "drill", **asdict(report)}, sort_keys=True)
    if args.report is not None:
        report_path = args.report.parent.resolve() / args.report.name
        if report_path.exists() or report_path.is_symlink():
            raise RecoveryError("Choose a new file for the drill report")
        with report_path.open("x", encoding="utf-8") as output:
            output.write(raw + "\n")
    print(raw)
    if not report.passed:
        print("Restore drill missed its RPO or RTO target", file=sys.stderr)
    return 0 if report.passed else 1


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
    drill = commands.add_parser(
        "drill",
        help="Time a full restore into a throwaway directory and empty database",
        allow_abbrev=False,
    )
    drill.add_argument("bundle", type=Path)
    drill.add_argument("--rpo-hours", type=float, default=24.0)
    drill.add_argument("--rto-minutes", type=float, default=60.0)
    drill.add_argument(
        "--report", type=Path, help="Also write the JSON report to this new file"
    )
    for command in (restore, drill):
        command.add_argument(
            "--deleted-accounts",
            type=Path,
            help="Erase accounts listed by export-deletions from the restored copy",
        )
    export = commands.add_parser(
        "export-deletions",
        help="Write the live installation's deleted-account ids to a new file",
        allow_abbrev=False,
    )
    export.add_argument("output", type=Path)
    for command in (backup, verify, restore, drill):
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
        if args.command == "export-deletions":
            return _export_deletions(args.output)
        deleted: list[LedgerEntry] = []
        if getattr(args, "deleted_accounts", None) is not None:
            try:
                deleted = read_ledger(args.deleted_accounts)
            except ValidationError:
                raise RecoveryError("Invalid deleted-accounts file") from None
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
            storage = _RecoveryStorage()
            target = storage.database_url.get_secret_value()
            if not target:
                raise RecoveryError(
                    "Set LIFEGATHER_DATABASE_URL to the new, empty PostgreSQL database"
                )
            if args.command == "drill":
                return _drill(service, args, password, target, deleted, storage)
            info = service.restore(
                args.bundle,
                args.destination,
                password,
                target,
                deleted_accounts=deleted,
            )
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
