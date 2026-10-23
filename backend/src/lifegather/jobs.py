"""Background scan wiring and the one-shot tick: python -m lifegather.jobs.

With LIFEGATHER_BACKGROUND_MODE=external the app starts no scan loop; a scheduler
outside the process (system cron, a Cloudflare Cron Trigger) runs due schedules
and queued scans through this command or POST /internal/jobs/tick. Both use the
same lease-guarded worker as the in-process loop, so overlapping ticks are safe.
"""

import argparse
import asyncio
import sys

from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from lifegather.auth.mail import smtp_sender
from lifegather.auth.store import AuthStore
from lifegather.chat.claude import ClaudeProvider
from lifegather.chat.google import GeminiProvider
from lifegather.chat.provider import OpenAIProvider, Provider
from lifegather.config import Settings
from lifegather.credentials.service import PrivateSettings, VaultError, read_keyring
from lifegather.database import DatabaseConfigurationError
from lifegather.documents.service import DocumentService
from lifegather.mailboxes.attachments import GmailAttachmentHandler
from lifegather.mailboxes.discovery import GmailDiscoveryHandler
from lifegather.mailboxes.provider import GmailProvider
from lifegather.mailboxes.scan import GmailImportHandler
from lifegather.operations.logs import configure_logging
from lifegather.operations.monitor import OperationsMonitor
from lifegather.photos.service import PhotoService
from lifegather.scans.registry import ScanRegistry
from lifegather.scans.schedules import ScheduleService
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker, TickReport
from lifegather.startup import schema_current
from lifegather.storage.base import ObjectStorage, StorageError
from lifegather.storage.settings import storage_from_settings

DEFAULT_TICK_SECONDS = 50
MAX_TICK_SECONDS = 300


def scan_service(
    engine: Engine,
    vault: PrivateSettings,
    gmail: GmailProvider,
    storage: ObjectStorage,
    providers: dict[str, Provider],
) -> ScanService:
    return ScanService(
        engine,
        ScanRegistry(
            [
                GmailImportHandler(engine, vault, gmail),
                GmailAttachmentHandler(
                    engine,
                    vault,
                    gmail,
                    DocumentService(engine, storage),
                    PhotoService(engine, storage),
                ),
                GmailDiscoveryHandler(engine, vault, gmail, providers),
            ]
        ),
    )


def scan_worker(scans: ScanService) -> ScanWorker:
    return ScanWorker(scans, ScheduleService(scans).dispatch)


def report_text(report: TickReport) -> str:
    return (
        f"Queued {report.dispatched} scheduled scans, finished {report.ran}, "
        f"paused {report.paused} at the time limit."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m lifegather.jobs",
        description="Run due scan schedules and queued scans once, then exit.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--seconds",
        type=int,
        default=DEFAULT_TICK_SECONDS,
        choices=range(1, MAX_TICK_SECONDS + 1),
        metavar=f"1-{MAX_TICK_SECONDS}",
        help=f"time limit for starting work (default {DEFAULT_TICK_SECONDS})",
    )
    seconds = parser.parse_args(argv).seconds
    configure_logging()
    store: AuthStore | None = None
    try:
        settings = Settings()
        keyring = read_keyring(settings)
        storage = storage_from_settings(settings)
        store = AuthStore(settings.database())
        if not schema_current(store.engine):
            print(
                "Tick failed: the database needs upgrading: "
                "run python -m lifegather.migrate",
                file=sys.stderr,
            )
            return 1
        vault = PrivateSettings(
            store.engine, keyring.active if keyring is not None else None
        )
        scans = scan_service(
            store.engine,
            vault,
            GmailProvider(settings),
            storage,
            {
                "openai": OpenAIProvider(),
                "anthropic": ClaudeProvider(),
                "google": GeminiProvider(),
            },
        )
        report = asyncio.run(scan_worker(scans).tick(seconds))
        monitor = OperationsMonitor(store.engine, settings, smtp_sender(settings))
        monitor.check_jobs()
        monitor.flush()
    except (
        ValidationError,
        DatabaseConfigurationError,
        VaultError,
        StorageError,
        ValueError,
        SQLAlchemyError,
        OSError,
    ) as error:
        # Messages are fixed strings; settings errors hide their input values.
        reason = (
            "invalid settings"
            if isinstance(error, ValidationError)
            else "database error"
            if isinstance(error, SQLAlchemyError)
            else str(error)
        )
        print(f"Tick failed: {reason}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.engine.dispose()
    print(report_text(report), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
