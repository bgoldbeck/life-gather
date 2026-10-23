"""Assistant-requested Gmail scans over the existing private scan queue."""

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from lifegather.mailboxes.models import Mailbox
from lifegather.mailboxes.service import Mailboxes
from lifegather.memory.service import MemoryError, fingerprint
from lifegather.scans.service import ScanService

if TYPE_CHECKING:
    from lifegather.chat.assistant import AssistantRunner

MAX_WINDOW_DAYS = 31
DEFAULT_MESSAGES = 20
DATE = r"^\d{4}-\d{2}-\d{2}$"
HANDLERS = {
    "discover_purchases": "gmail_discovery",
    "import_evidence": "gmail_import",
    "import_attachments": "gmail_attachments",
}
# Attachment downloads are slower and fill file storage; keep them smaller.
MAX_MESSAGES = {"gmail_attachments": 10}


class EmailScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mailbox_id: str = Field(min_length=1, max_length=36)
    purpose: Literal["discover_purchases", "import_evidence", "import_attachments"]
    purpose_quote: str = Field(min_length=1, max_length=200)
    from_date: str = Field(pattern=DATE)
    until_date: str = Field(pattern=DATE)
    period_quote: str = Field(min_length=1, max_length=200)
    max_messages: int = Field(ge=1, le=50)


def today() -> date:
    return datetime.now(UTC).date()


def midnight(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())


class AssistantScans:
    """List mailboxes and enqueue one scan; the queue and handlers re-authorize."""

    def __init__(
        self, runner: "AssistantRunner", scans: ScanService | None, credential_id: str
    ) -> None:
        self.runner = runner
        self.scans = scans
        self.credential_id = credential_id
        # Host-owned mailbox IDs the model may reference, with addresses.
        self.mailboxes: dict[str, str] = {}

    def list(self) -> dict[str, Any]:
        from lifegather.chat.assistant import StepError

        if self.scans is None:
            raise StepError("Email scans are unavailable on this server; answer")
        with Session(self.runner.engine) as db:
            items = [
                Mailboxes.view(row)
                for row in db.scalars(
                    select(Mailbox)
                    .where(
                        Mailbox.user_id == self.runner.actor.id,
                        Mailbox.credential_id.is_not(None),
                    )
                    .order_by(Mailbox.created_at, Mailbox.id)
                    .limit(10)
                )
            ]
        self.mailboxes = {item["id"]: item["address"] for item in items}
        return {"mailboxes": [{"id": i["id"], "address": i["address"]} for i in items]}

    def _window(self, item: EmailScanRequest) -> tuple[int, int, date, date]:
        from lifegather.chat.assistant import StepError

        try:
            start = date.fromisoformat(item.from_date)
            end = date.fromisoformat(item.until_date)
        except ValueError:
            raise StepError("Dates must be real YYYY-MM-DD dates") from None
        current = today()
        if end < start:
            raise StepError("from_date must not be after until_date")
        if end > current:
            raise StepError("Scans cover past days only; end no later than today")
        if (end - start).days + 1 > MAX_WINDOW_DAYS:
            raise StepError(
                "A scan covers at most 31 days. Ask the user to choose a shorter "
                "period, one scan at a time."
            )
        until = min(
            midnight(end + timedelta(days=1)), int(datetime.now(UTC).timestamp())
        )
        return midnight(start), until, start, end

    def start(self, item: EmailScanRequest | None) -> dict[str, Any]:
        from lifegather.chat.assistant import StepError, mentions

        runner = self.runner
        if item is None:
            raise StepError("start_email_scan needs email_scan")
        if self.scans is None or self.scans.engine is not runner.engine:
            raise MemoryError("Email scans are unavailable on this server")
        if item.mailbox_id not in self.mailboxes:
            raise StepError("Unknown mailbox ID. List the user's mailboxes first.")
        address = self.mailboxes[item.mailbox_id]
        if len(self.mailboxes) > 1 and not mentions(runner.evidence, address):
            raise StepError(
                "Several mailboxes are connected and the user did not name this "
                "address. Ask which mailbox to scan."
            )
        if not mentions(runner.evidence, item.purpose_quote):
            raise StepError(
                "purpose_quote is not the user's words. Ask whether to look for "
                "purchases or only import email evidence."
            )
        if not mentions(runner.evidence, item.period_quote):
            raise StepError(
                "period_quote is not the user's words. Ask which days to scan."
            )
        handler = HANDLERS[item.purpose]
        default = MAX_MESSAGES.get(handler, DEFAULT_MESSAGES)
        if item.max_messages != default and str(item.max_messages) not in (
            runner.evidence
        ):
            raise StepError(
                f"Use max_messages {default} unless the user stated a limit"
            )
        since, until, start, end = self._window(item)
        config: dict[str, Any] = {
            "mailbox_id": item.mailbox_id,
            "from_timestamp": since,
            "until_timestamp": until,
            "query": "",
            "max_messages": item.max_messages,
        }
        if handler == "gmail_discovery":
            config |= {"credential_id": self.credential_id, "model": runner.model}
        try:
            self.scans.registry.get(handler).config_model.model_validate(config)
        except ValidationError:
            raise StepError("Invalid scan scope; ask the user") from None
        runner.active()
        with runner.manual.memory._write() as db:
            row = runner._turn(db)
            run = self.scans.enqueue_in(
                db,
                runner.actor,
                handler,
                config,
                "assistant:" + fingerprint([runner.request_id]),
            )
            result = self._receipt(run, handler, address, start, end, config)
            runner._commit(db, row, result)
            return result

    def _receipt(
        self,
        run: dict[str, Any],
        handler: str,
        address: str,
        start: date,
        end: date,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        runner = self.runner
        period = (
            start.isoformat()
            if start == end
            else f"{start.isoformat()} to {end.isoformat()}"
        )
        scope = f"{address} for {period} (UTC), up to {config['max_messages']} emails"
        if handler == "gmail_discovery":
            text = (
                f"Started a purchase discovery scan of {scope}, using this AI "
                "connection and model. Email text is saved as evidence; clear "
                "purchases may be added as inferred inventory you can review and "
                "correct. Attachments are omitted."
            )
        elif handler == "gmail_attachments":
            text = (
                f"Started an attachment import of {scope}. Supported documents "
                "(PDF, Word, Excel, CSV, text; up to 4 MiB) and photos (JPEG, "
                "PNG, WebP; up to 8 MiB), three per email, are saved privately "
                "in Documents and Photos with a link to their email. No AI "
                "reads them and no item is created; review each document's text "
                "before it becomes evidence. Other files are listed but not "
                "downloaded."
            )
        else:
            text = (
                f"Started an email evidence scan of {scope}. It imports original "
                "email text only: no AI reads these emails and no inventory is "
                "created. Attachments are omitted."
            )
        text += " It continues in the background; view the scan to follow or cancel it."
        return {
            "text": text,
            "provider": runner.provider,
            "model": runner.model,
            "scan_run_id": run["id"],
            "scan_scope": {
                key: config[key]
                for key in (
                    "mailbox_id",
                    "from_timestamp",
                    "until_timestamp",
                    "max_messages",
                )
            },
            "assistant": {
                "operation": "scan",
                "handler_key": handler,
                "scan_run_id": run["id"],
                "mailbox_address": address,
                "from_date": start.isoformat(),
                "until_date": end.isoformat(),
            },
            "read_trace": runner.trace,
        }
