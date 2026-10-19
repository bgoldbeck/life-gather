import asyncio
import base64
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx2
import pytest
from pydantic import BaseModel, SecretStr
from test_mailboxes import provider
from test_reconciliation import setup

from lifegather.auth.store import Account, AuthStore
from lifegather.chat.provider import Completion
from lifegather.credentials.service import PrivateSettings
from lifegather.mailboxes.discovery import GmailDiscoveryHandler
from lifegather.mailboxes.provider import GmailGrant
from lifegather.mailboxes.service import Mailboxes
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.queue import ReviewPage, ReviewService
from lifegather.reconciliation.schemas import DiscoveryInput
from lifegather.reconciliation.service import ReconciliationService
from lifegather.scans.registry import ScanContext, ScanRegistry
from lifegather.scans.schedules import ScheduleInput, ScheduleService
from lifegather.scans.service import ScanCanceled, ScanService
from lifegather.scans.worker import ScanWorker

TEXT = "Purchase receipt: Home Depot order HD-101 line SKU-42 Husqvarna trimmer Qty: 1"


class AI:
    def __init__(self) -> None:
        self.calls = 0
        self.change: Any = None
        self.value: dict[str, Any] = {
            "event": "purchase",
            "items": [
                {
                    "name": "trimmer",
                    "manufacturer": "Husqvarna",
                    "model": None,
                    "serial": None,
                    "kind": "mention",
                    "quote": TEXT,
                    "quantity": 1,
                    "quantity_quote": "Qty: 1",
                    "order": {
                        "retailer": "Home Depot",
                        "order_id": "HD-101",
                        "line_id": "SKU-42",
                    },
                }
            ],
            "explanation": "Synthetic purchase receipt",
        }

    async def complete(
        self,
        secret: str,
        model: str,
        instruction: str,
        payload: dict[str, Any],
        schema: type[BaseModel],
    ) -> Completion:
        self.calls += 1
        assert secret == "synthetic-ai" and "No tools" in instruction
        assert "synthetic-ai" not in str(payload)
        if self.change:
            self.change()
        return Completion(self.value, 10, 5)


def harness(
    tmp_path: Path,
    provider_name: str = "openai",
) -> tuple[
    AuthStore,
    Account,
    Account,
    MemoryService,
    ReconciliationService,
    PrivateSettings,
    AI,
    ScanService,
    dict[str, Any],
]:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    vault = PrivateSettings(auth.engine, b"x" * 32)
    vault.set_preferences(actor, True)
    credential = vault.save(actor, "ai", provider_name, "Synthetic AI", "synthetic-ai")
    mailbox = Mailboxes(auth.engine, vault).connect(
        actor,
        GmailGrant(
            address="owner@example.test", refresh_token=SecretStr("synthetic-mail")
        ),
    )

    def respond(request: httpx2.Request) -> httpx2.Response:
        data: dict[str, Any]
        if request.url.host == "oauth2.googleapis.com":
            data = {"access_token": "synthetic"}
        elif request.url.path.endswith("profile"):
            data = {"emailAddress": "owner@example.test"}
        elif request.url.path.endswith("messages"):
            data = {"messages": [{"id": "message1"}, {"id": "message2"}]}
        else:
            data = {
                "id": request.url.path.rsplit("/", 1)[1],
                "internalDate": "150000",
                "payload": {
                    "mimeType": "text/plain",
                    "body": {"data": base64.urlsafe_b64encode(TEXT.encode()).decode()},
                },
            }
        return httpx2.Response(200, json=data)

    ai = AI()
    handler = GmailDiscoveryHandler(
        auth.engine, vault, provider(httpx2.MockTransport(respond)), {provider_name: ai}
    )
    scans = ScanService(auth.engine, ScanRegistry([handler]))
    config = {
        "mailbox_id": mailbox["id"],
        "from_timestamp": 100,
        "until_timestamp": 200,
        "credential_id": credential.id,
        "model": "synthetic-model",
    }
    return auth, actor, bob, memory, reconcile, vault, ai, scans, config


def test_email_discovery_groups_order_evidence_and_reuses_completed_extraction(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, reconcile, _, ai, scans, config = harness(tmp_path)
    run = scans.enqueue(actor, "gmail_discovery", config, "first")
    asyncio.run(ScanWorker(scans).run_once())
    result = scans.get(actor, run["id"])
    assert result["state"] == "completed"
    assert len(reconcile.inventory(actor)) == 1
    assert len(memory.export_page(actor, "sources")["items"]) == 2
    assert result["items"][0]["metadata"]["created"] == 1
    assert result["items"][1]["metadata"]["enriched"] == 1
    assert reconcile.inventory(bob) == []
    repeat = scans.enqueue(actor, "gmail_discovery", config, "repeat")
    asyncio.run(ScanWorker(scans).run_once())
    assert scans.get(actor, repeat["id"])["state"] == "completed"
    assert ai.calls == 2 and len(reconcile.inventory(actor)) == 1
    auth.engine.dispose()


@pytest.mark.parametrize("event", ["shipment", "cancellation", "other"])
def test_non_purchase_email_never_creates_inventory(tmp_path: Path, event: str) -> None:
    auth, actor, _, _, reconcile, _, ai, scans, config = harness(tmp_path)
    ai.value["event"] = event
    run = scans.enqueue(actor, "gmail_discovery", config, "nonpurchase")
    asyncio.run(ScanWorker(scans).run_once())
    assert scans.get(actor, run["id"])["state"] == "completed"
    assert reconcile.inventory(actor) == []
    auth.engine.dispose()


def test_permission_revoked_during_model_call_rolls_back_evidence_and_assets(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile, vault, ai, scans, config = harness(tmp_path)
    ai.change = lambda: vault.set_preferences(actor, False)
    run = scans.enqueue(actor, "gmail_discovery", config, "revoke")
    asyncio.run(ScanWorker(scans).run_once())
    assert scans.get(actor, run["id"])["state"] == "failed"
    assert reconcile.inventory(actor) == []
    assert memory.export_page(actor, "sources")["items"] == []
    auth.engine.dispose()


@pytest.mark.parametrize(
    "bad",
    ["quote", "order_prefix", "line_number", "quantity", "ownership", "extra_line"],
)
def test_invalid_extraction_rolls_back_whole_email(tmp_path: Path, bad: str) -> None:
    auth, actor, _, memory, reconcile, _, ai, scans, config = harness(tmp_path)
    line = ai.value["items"][0]
    if bad == "quote":
        line["quote"] += " invented"
    elif bad == "order_prefix":
        line["order"]["order_id"] = "HD-10"
    elif bad == "line_number":
        line["order"]["line_id"] = "1"
    elif bad == "quantity":
        line["quantity"] = 2
    elif bad == "ownership":
        line["kind"] = "possession"
    else:
        ai.value["items"].append({**line, "quote": "invented second line"})
    run = scans.enqueue(actor, "gmail_discovery", config, "invalid")
    asyncio.run(ScanWorker(scans).run_once())
    result = scans.get(actor, run["id"])
    assert result["state"] == "failed" and result["scanned"] == 0
    assert memory.export_page(actor, "sources")["items"] == []
    assert reconcile.inventory(actor) == []
    auth.engine.dispose()


def test_name_similarity_routes_to_existing_review_queue(tmp_path: Path) -> None:
    auth, actor, _, memory, reconcile, _, _, scans, config = harness(tmp_path)
    source = memory.ingest(actor, SourceInput(text="I own a trimmer"))
    reconcile.discover(
        actor,
        DiscoveryInput(
            source_id=source.id,
            item_key="manual",
            quantity=1,
            name="trimmer",
            kind="possession",
            quote=source.text,
        ),
    )
    run = scans.enqueue(actor, "gmail_discovery", config, "weak")
    asyncio.run(ScanWorker(scans).run_once())
    assert scans.get(actor, run["id"])["state"] == "completed"
    assert len(reconcile.inventory(actor)) == 1
    assert len(ReviewService(auth.engine).list(actor, ReviewPage())["items"]) == 2
    auth.engine.dispose()


@pytest.mark.parametrize("change", ["cancel", "credential", "source"])
def test_checkpoint_rechecks_cancellation_credential_and_source(
    tmp_path: Path, change: str
) -> None:
    auth, actor, _, memory, reconcile, vault, _, scans, config = harness(tmp_path)
    run = scans.enqueue(actor, "gmail_discovery", config, "checkpoint")
    claim = scans.claim()
    assert claim is not None
    context = ScanContext(
        actor, claim.id, lambda: scans.heartbeat(claim.id, claim.token)
    )
    batch = asyncio.run(
        scans.registry.get(claim.handler_key).step(context, claim.config, {})
    )
    if change == "cancel":
        scans.cancel(actor, run["id"])
    elif change == "credential":
        vault.replace(actor, config["credential_id"], "replacement-ai")
    else:
        assert batch.items[0].source is not None
        source = memory.ingest(actor, batch.items[0].source)
        NoteService(auth.engine).correct(
            actor,
            CorrectionInput(
                source_id=source.id,
                text="This purchase was for someone else",
                request_id="correction",
            ),
        )
    with pytest.raises((MemoryError, ScanCanceled)):
        scans.commit_batch(claim, batch)
    assert reconcile.inventory(actor) == []
    assert scans.get(actor, run["id"])["scanned"] == 0
    auth.engine.dispose()


def test_empty_extraction_is_cached_and_credentials_are_owner_scoped(
    tmp_path: Path,
) -> None:
    auth, actor, bob, _, reconcile, _, ai, scans, config = harness(tmp_path)
    with pytest.raises(MemoryError):
        scans.enqueue(bob, "gmail_discovery", config, "foreign")
    ai.value.update(event="other", items=[])
    for key in ["empty", "repeat"]:
        run = scans.enqueue(actor, "gmail_discovery", config, key)
        asyncio.run(ScanWorker(scans).run_once())
        assert scans.get(actor, run["id"])["state"] == "completed"
    assert ai.calls == 2 and reconcile.inventory(actor) == []
    auth.engine.dispose()


@pytest.mark.parametrize("provider_name", ["openai", "anthropic", "google"])
def test_discovery_selects_adapter_and_preserves_inferred_ownership(
    tmp_path: Path, provider_name: str
) -> None:
    auth, actor, _, memory, reconcile, _, _, scans, config = harness(
        tmp_path, provider_name
    )
    run = scans.enqueue(actor, "gmail_discovery", config, "provider")
    asyncio.run(ScanWorker(scans).run_once())
    assert scans.get(actor, run["id"])["state"] == "completed"
    assert len(reconcile.inventory(actor)) == 1
    owned = [
        fact
        for fact in memory.export_page(actor, "facts")["items"]
        if fact["predicate"] == "owned"
    ]
    assert owned and all(fact["status"] == "inferred" for fact in owned)
    auth.engine.dispose()


def test_discovery_schedule_pauses_after_ai_credential_rotation(tmp_path: Path) -> None:
    auth, actor, _, _, _, vault, _, scans, config = harness(tmp_path)
    scheduler = ScheduleService(scans)
    schedule = scheduler.create(
        actor,
        ScheduleInput(
            label="Synthetic discovery",
            handler_key="gmail_discovery",
            config={
                key: value
                for key, value in config.items()
                if key not in {"from_timestamp", "until_timestamp"}
            },
            timezone="UTC",
            cadence="daily",
            local_time="09:00",
            lookback_days=7,
            request_id="schedule",
        ),
    )
    vault.replace(actor, config["credential_id"], "replacement")
    scans.clock = lambda: schedule["next_run"]
    assert scheduler.dispatch() == 1
    changed = scheduler.list(actor)["items"][0]
    assert not changed["enabled"] and changed["last_status"] == "blocked"
    assert scans.list(actor)["items"] == []
    auth.engine.dispose()


def test_discovery_budget_blocks_outbound_call(tmp_path: Path) -> None:
    auth, actor, _, _, reconcile, vault, ai, scans, config = harness(tmp_path)
    handler = scans.registry.get("gmail_discovery")
    assert isinstance(handler, GmailDiscoveryHandler)
    for _ in range(20):
        handler.chat.reserve(actor, vault, config["credential_id"])
    run = scans.enqueue(actor, "gmail_discovery", config, "budget")
    asyncio.run(ScanWorker(scans).run_once())
    assert scans.get(actor, run["id"])["state"] == "failed"
    assert ai.calls == 0 and reconcile.inventory(actor) == []
    auth.engine.dispose()


def test_truncated_receipt_needs_review_and_stale_source_is_not_sent_to_ai(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile, _, ai, scans, config = harness(tmp_path)
    run = scans.enqueue(actor, "gmail_discovery", config, "truncated")
    claim = scans.claim()
    assert claim is not None
    context = ScanContext(
        actor, run["id"], lambda: scans.heartbeat(claim.id, claim.token)
    )
    handler = scans.registry.get("gmail_discovery")
    batch = asyncio.run(handler.step(context, claim.config, {}))
    item = batch.items[0]
    scans.commit_batch(
        claim, replace(batch, items=[replace(item, metadata={"truncated": True})])
    )
    assert reconcile.inventory(actor) == []
    assert scans.get(actor, run["id"])["items"][0]["metadata"]["review"] == 1
    assert item.source is not None
    source = memory.ingest(actor, item.source)
    NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=source.id,
            text="The receipt was cancelled",
            request_id="correct-truncated",
        ),
    )
    with pytest.raises(MemoryError, match="changed"):
        asyncio.run(handler.step(context, claim.config, {}))
    assert ai.calls == 1
    auth.engine.dispose()
