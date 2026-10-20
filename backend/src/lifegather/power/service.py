"""Read-only local diagnostics. Never decrypt credentials or contact providers."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from lifegather.auth.store import Account
from lifegather.chat.models import ChatPreference, Usage
from lifegather.chat.provider_names import SUPPORTED_PROVIDERS
from lifegather.chat.service import DAILY_REQUESTS
from lifegather.credentials.models import Credential, UserSettings
from lifegather.mailboxes.models import Mailbox
from lifegather.scans.models import ScanRun, ScanSchedule

State = Literal["ready", "unknown", "stale", "blocked", "disabled", "failed", "planned"]
Destination = Literal[
    "Settings", "Scans", "Documents", "Assets", "Maintenance", "Memories"
]
OBSERVATION_SECONDS = 86400
DATA_SECONDS = 7 * 86400


class PowerRead(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Capability(BaseModel):
    id: str
    title: str
    weight: int
    state: State
    reason: str
    action: Destination
    available_to_request: bool = False


class SourceStatus(BaseModel):
    id: str
    title: str
    category: Literal["local", "ai", "email", "planned"]
    configured: bool
    state: State
    reason: str
    capabilities: list[str]
    action: Destination
    last_success: int | None = None
    last_run_id: str | None = None
    freshness: Literal["current", "stale", "unknown"] = "unknown"
    scope: str = ""


class Issue(BaseModel):
    id: str
    title: str
    reason: str
    action: Destination
    state: State
    run_id: str | None = None


class PowerSnapshot(BaseModel):
    checked_at: int
    expires_at: int
    scoring_version: str = "1"
    score: int | None
    minimum_score: int
    maximum_score: int
    capabilities: list[Capability]
    sources: list[SourceStatus]
    issues: list[Issue]
    issues_truncated: bool
    connected_sources: int
    completed_scans_7d: int
    imported_messages_7d: int
    period_start: int
    ai_requests: int
    ai_limit: int = DAILY_REQUESTS
    ai_resets_at: int
    paused_schedules: int


def observed_state(last_success: int | None, now: int) -> State:
    if last_success is None:
        return "unknown"
    return "ready" if 0 <= now - last_success <= OBSERVATION_SECONDS else "stale"


class PowerCenter:
    def __init__(
        self,
        engine: Engine,
        *,
        vault_enabled: bool,
        gmail_enabled: bool,
        handlers: set[str],
        clock: Callable[[], int] | None = None,
    ) -> None:
        self.engine = engine
        self.vault_enabled = vault_enabled
        self.gmail_enabled = gmail_enabled
        self.handlers = handlers
        self.clock = clock or (lambda: int(time.time()))

    def read(self, actor: Account) -> PowerSnapshot:
        now = self.clock()
        with Session(self.engine) as db:
            db.connection().exec_driver_sql("BEGIN")
            return self._read(db, actor, now)

    def _read(self, db: Session, actor: Account, now: int) -> PowerSnapshot:
        day = datetime.fromtimestamp(now, UTC).date().isoformat()
        usage = db.get(Usage, (actor.id, day))
        requests = usage.requests if usage else 0
        preferences = db.get(UserSettings, actor.id)
        consent = bool(preferences and preferences.allow_external_ai)
        choice = db.get(ChatPreference, actor.id)
        # Metadata only. Nonces, ciphertext, secrets and raw scan errors stay private.
        credentials = list(
            db.execute(
                select(Credential.id, Credential.kind, Credential.provider)
                .where(Credential.user_id == actor.id)
                .order_by(Credential.id)
                .limit(101)
            )
        )
        ai = {
            c.id: c.provider
            for c in credentials
            if c.kind == "ai" and c.provider in SUPPORTED_PROVIDERS
        }
        mail_credentials = {
            c.id for c in credentials if c.kind == "email" and c.provider == "gmail"
        }
        selected = bool(choice and choice.credential_id in ai and choice.model)
        ai_reason = (
            "Configure encrypted credential storage in Settings."
            if not self.vault_enabled
            else "External AI is disabled. Enable it for provider processing."
            if not consent
            else "Add a supported AI connection in Settings."
            if not ai
            else "Daily AI request limit reached; wait for the next UTC day."
            if requests >= DAILY_REQUESTS
            else "Save a connection and model in Chat to establish your default."
            if not selected
            else "Connection and model configured; model availability is unverified. "
            "Use Ask AI for a requested, budgeted check."
        )
        ai_state: State = (
            "blocked"
            if not self.vault_enabled
            else "disabled"
            if not consent
            else "blocked"
            if not ai or requests >= DAILY_REQUESTS or not selected
            else "unknown"
        )
        capabilities = [
            Capability(
                id=key,
                title=title,
                weight=weight,
                state="ready",
                reason=reason,
                action=cast(Destination, action),
            )
            for key, title, weight, reason, action in (
                (
                    "evidence",
                    "Capture and recall local evidence",
                    20,
                    "Manual notes, photos and supported documents work without AI.",
                    "Documents",
                ),
                (
                    "inventory",
                    "Inventory and sourced corrections",
                    15,
                    "Add/correct items, inspect evidence and resolve identity review.",
                    "Assets",
                ),
                (
                    "maintenance",
                    "Stated maintenance tasks",
                    10,
                    "Manual tasks, dates and history; automatic reminders are planned.",
                    "Maintenance",
                ),
                (
                    "archive",
                    "Private records and original downloads",
                    10,
                    "Download records and originals in Settings; import is planned.",
                    "Settings",
                ),
            )
        ]
        capabilities.extend(
            [
                Capability(
                    id="ai_recall",
                    title="Sourced AI answers",
                    weight=15,
                    state=ai_state,
                    reason=ai_reason,
                    action="Settings",
                ),
                Capability(
                    id="photo_reading",
                    title="Requested photo and receipt reading",
                    weight=10,
                    state=ai_state,
                    reason=ai_reason + " A vision-capable model is required.",
                    action="Settings",
                ),
            ]
        )
        sources = [
            SourceStatus(
                id="local",
                title="Private workspace",
                category="local",
                configured=True,
                state="ready",
                reason="Local evidence and correction services are available.",
                capabilities=["evidence", "inventory", "maintenance", "archive"],
                action="Documents",
                scope="Manual uploads and saved records. No folder watcher or OCR.",
            )
        ]
        for provider, title in (
            ("openai", "OpenAI"),
            ("anthropic", "Claude"),
            ("google", "Gemini"),
        ):
            count = sum(value == provider for value in ai.values())
            sources.append(
                SourceStatus(
                    id=provider,
                    title=title,
                    category="ai",
                    configured=bool(count),
                    state="unknown"
                    if count and self.vault_enabled and consent
                    else "blocked"
                    if not count or not self.vault_enabled
                    else "disabled",
                    reason=(
                        f"{count} saved connection(s). Model health is unverified."
                        if count
                        else "Add a connection to enable requested AI processing."
                    )
                    + (" External AI permission is disabled." if not consent else ""),
                    capabilities=["ai_recall", "photo_reading", "gmail_discovery"],
                    action="Settings",
                    scope="Requested AI work may cost money. Local checks are free.",
                )
            )
        mailboxes = list(
            db.scalars(
                select(Mailbox)
                .where(Mailbox.user_id == actor.id)
                .order_by(Mailbox.id)
                .limit(11)
            )
        )
        mail_states: list[State] = []
        connected = 0
        for mailbox in mailboxes[:10]:
            configured = mailbox.credential_id in mail_credentials
            connected += int(configured)
            available = configured and self.vault_enabled and self.gmail_enabled
            # Reconnecting invalidates old-grant observations, even in the same second.
            scope = (
                ScanRun.user_id == actor.id,
                ScanRun.resource_key == "gmail:" + mailbox.id,
                func.json_extract(ScanRun.config_json, "$.mailbox_revision")
                == mailbox.revision,
            )
            success = db.scalar(
                select(ScanRun)
                .where(*scope, ScanRun.state == "completed")
                .order_by(ScanRun.completed_at.desc(), ScanRun.id)
                .limit(1)
            )
            latest = db.scalar(
                select(ScanRun)
                .where(*scope, ScanRun.state.in_(("completed", "failed")))
                .order_by(
                    ScanRun.updated_at.desc(),
                    (ScanRun.state == "failed").desc(),
                    ScanRun.created_at.desc(),
                    ScanRun.id.desc(),
                )
                .limit(1)
            )
            expired = db.scalar(
                select(ScanRun.id)
                .where(
                    *scope,
                    ScanRun.state == "running",
                    func.coalesce(ScanRun.lease_until, 0) <= now,
                )
                .limit(1)
            )
            last = success.completed_at if success else None
            state: State = observed_state(last, now) if available else "blocked"
            reason = (
                "Recent successful scan of this grant; coverage is scope-limited."
                if state == "ready"
                else "Last successful scan is older than 24 hours."
                if state == "stale"
                else "No successful scan observed for this grant."
                if available
                else "Reconnect Gmail or restore installation OAuth/vault setup."
            )
            if available and latest and latest.state == "failed":
                state, reason = (
                    "failed",
                    "Latest scan failed. Inspect it; reconnect if access was revoked.",
                )
            if available and expired:
                state, reason = (
                    "failed",
                    "Scan lease expired; inspect worker recovery in Scans.",
                )
            if available:
                mail_states.append(state)
            sources.append(
                SourceStatus(
                    id=mailbox.id,
                    title=mailbox.address,
                    category="email",
                    configured=configured,
                    state=state,
                    reason=reason,
                    capabilities=["gmail_import", "gmail_discovery"],
                    action="Scans" if available else "Settings",
                    last_success=last,
                    last_run_id=success.id if success else None,
                    freshness="unknown"
                    if last is None
                    else "current"
                    if 0 <= now - last <= DATA_SECONDS
                    else "stale",
                    scope=(
                        f"Last successful scope: {success.handler_key}; "
                        f"{success.scanned} messages checked; bounded query/date range."
                        if success
                        else "Gmail read-only consent. No arrival-triggered ingestion."
                    ),
                )
            )
        if not mailboxes:
            sources.append(
                SourceStatus(
                    id="gmail",
                    title="Gmail",
                    category="email",
                    configured=False,
                    state="blocked",
                    reason="Connect Gmail separately from sign-in. No scan starts.",
                    capabilities=["gmail_import", "gmail_discovery"],
                    action="Settings",
                    scope="Requested/scheduled read-only text scans; no attachments.",
                )
            )
        mail_state: State = next(
            (s for s in ("ready", "unknown", "stale", "failed") if s in mail_states),
            "blocked",
        )
        for key, title, weight in (
            ("gmail_import", "Requested Gmail text evidence", 10),
            ("gmail_discovery", "Requested Gmail purchase discovery", 10),
        ):
            state = mail_state
            reason = "Connect Gmail and configure the installation before scanning."
            if mail_states:
                reason = "Explicitly request a bounded scan or configure a schedule. "
                reason += "Other mailboxes may still need attention."
            if key not in self.handlers:
                state, reason = (
                    "blocked",
                    "The scan handler is unavailable in this installation.",
                )
            elif key == "gmail_discovery" and mail_states:
                if not consent or not ai or requests >= DAILY_REQUESTS:
                    state, reason = "disabled" if not consent else "blocked", ai_reason
                elif state != "failed":
                    state, reason = (
                        "unknown",
                        "Select an AI connection/model when requesting discovery. "
                        "Unverified model health; permission and daily limits apply.",
                    )
            capabilities.append(
                Capability(
                    id=key,
                    title=title,
                    weight=weight,
                    state=state,
                    reason=reason,
                    action="Scans" if mail_states else "Settings",
                )
            )
        sources.extend(
            SourceStatus(
                id=key,
                title=title,
                category="planned",
                configured=False,
                state="planned",
                reason=reason,
                capabilities=[],
                action="Settings",
            )
            for key, title, reason in (
                (
                    "banking",
                    "Bank and card syncing",
                    "Planned. Saved bank credentials do not enable financial imports.",
                ),
                (
                    "other_sources",
                    "More connected sources",
                    "Outlook, cloud files and folder watchers are planned.",
                ),
            )
        )
        issues = [
            Issue(
                id=s.id, title=s.title, reason=s.reason, action=s.action, state=s.state
            )
            for s in sources
            if s.configured and s.state != "ready"
        ]
        if ai_state != "unknown":
            issues.append(
                Issue(
                    id="ai_setup",
                    title="AI readiness",
                    reason=ai_reason,
                    action="Settings",
                    state=ai_state,
                )
            )
        troubled = list(
            db.scalars(
                select(ScanRun)
                .where(
                    ScanRun.user_id == actor.id,
                    (
                        (ScanRun.state == "failed")
                        & (ScanRun.updated_at >= now - DATA_SECONDS)
                    )
                    | (
                        (ScanRun.state == "running")
                        & (func.coalesce(ScanRun.lease_until, 0) <= now)
                    ),
                )
                .order_by(ScanRun.updated_at.desc(), ScanRun.id)
                .limit(11)
            )
        )
        for run in troubled[:10]:
            issues.append(
                Issue(
                    id=run.id,
                    title="Expired scan lease"
                    if run.state == "running"
                    else "Failed scan",
                    reason="Inspect the run and retry or reconnect as needed. "
                    "Completed evidence remains saved.",
                    action="Scans",
                    state="failed",
                    run_id=run.id,
                )
            )
        schedules = list(
            db.scalars(
                select(ScanSchedule)
                .where(ScanSchedule.user_id == actor.id)
                .order_by(ScanSchedule.id)
                .limit(6)
            )
        )
        for schedule in schedules[:5]:
            if schedule.enabled and (
                schedule.last_status == "blocked" or schedule.next_run < now - 300
            ):
                issues.append(
                    Issue(
                        id=schedule.id,
                        title="Schedule needs attention",
                        reason="Inspect schedule setup or overdue dispatch in Scans.",
                        action="Scans",
                        state="blocked",
                    )
                )
        count, imported = db.execute(
            select(func.count(), func.coalesce(func.sum(ScanRun.imported), 0)).where(
                ScanRun.user_id == actor.id,
                ScanRun.state == "completed",
                ScanRun.completed_at >= now - DATA_SECONDS,
            )
        ).one()
        minimum = sum(c.weight for c in capabilities if c.state == "ready")
        maximum = minimum + sum(
            c.weight for c in capabilities if c.state in {"unknown", "stale"}
        )
        for capability in capabilities:
            capability.available_to_request = capability.state in {
                "ready",
                "unknown",
                "stale",
            }
        return PowerSnapshot(
            checked_at=now,
            expires_at=now + 300,
            score=minimum if minimum == maximum else None,
            minimum_score=minimum,
            maximum_score=maximum,
            capabilities=capabilities,
            sources=sources,
            issues=issues,
            issues_truncated=len(troubled) > 10
            or len(mailboxes) > 10
            or len(credentials) > 100
            or len(schedules) > 5,
            connected_sources=connected + len(set(ai.values())),
            completed_scans_7d=count,
            imported_messages_7d=imported,
            period_start=now - DATA_SECONDS,
            ai_requests=requests,
            ai_resets_at=(now // 86400 + 1) * 86400,
            paused_schedules=sum(not s.enabled for s in schedules),
        )
