from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_ai_assistant import Case, ScriptedProvider, step
from test_mcp_http import signed_headers

from lifegather.chat.assistant_scans import midnight
from lifegather.chat.service import ChatService
from lifegather.credentials.keygen import generate
from lifegather.credentials.models import UserSettings
from lifegather.mailboxes.provider import GmailGrant
from lifegather.mailboxes.service import Mailboxes
from lifegather.main import create_app
from lifegather.scans.models import ScanRun
from lifegather.scans.worker import ScanWorker

TODAY = datetime.now(UTC).date()
START = TODAY - timedelta(days=10)
END = TODAY - timedelta(days=3)


def scan(mailbox: str, **values: Any) -> dict[str, Any]:
    return {
        "mailbox_id": mailbox,
        "purpose": "discover_purchases",
        "purpose_quote": "purchases",
        "from_date": START.isoformat(),
        "until_date": END.isoformat(),
        "period_quote": "last week",
        "max_messages": 20,
        **values,
    }


class ScanCase(Case):
    app: Any = None

    def mailbox(self, address: str, actor: Any = None) -> str:
        return str(
            Mailboxes(self.engine, self.app.state.private_settings).connect(
                actor or self.actor,
                GmailGrant(address=address, refresh_token=SecretStr("synthetic")),
            )["id"]
        )

    def runs(self) -> list[ScanRun]:
        with Session(self.engine) as db:
            return list(db.scalars(select(ScanRun).order_by(ScanRun.created_at)))


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ScanCase]:
    async def idle(self: ScanWorker) -> None:
        import asyncio

        await asyncio.Event().wait()

    monkeypatch.setattr(ScanWorker, "serve", idle)
    key = tmp_path / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()
    provider = ScriptedProvider()
    app.state.chat_provider = provider
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        bob, other_actor = signed_headers(app, "bob")
        credential = client.post(
            "/api/credentials",
            headers=alice,
            json={
                "kind": "ai",
                "provider": "openai",
                "label": "Test",
                "secret": "synthetic-key",
            },
        ).json()["id"]
        client.put("/api/settings", headers=alice, json={"allow_external_ai": True})
        result = ScanCase(
            client,
            alice,
            actor,
            bob,
            other_actor,
            provider,
            credential,
            app.state.auth_store.engine,
        )
        result.app = app
        yield result


def test_discovery_scan_is_queued_with_scope_and_replay_is_stable(
    case: ScanCase,
) -> None:
    mailbox = case.mailbox("owner@example.test")
    conversation = case.conversation()
    text = "Look through my Gmail for purchases from last week."
    seen: list[dict[str, Any]] = []

    def plan(payload: dict[str, Any]) -> dict[str, Any]:
        seen.append(payload)
        listed = payload["steps"][0]["result"]["mailboxes"]
        assert listed == [{"id": mailbox, "address": "owner@example.test"}]
        return step("start_email_scan", email_scan=scan(mailbox))

    queued = case.send(conversation, "scan", text, step("list_mailboxes"), plan)
    result = queued["result"]
    assert queued["state"] == "complete"
    assert seen[0]["today"] == TODAY.isoformat()
    assert result["text"].startswith(
        "Started a purchase discovery scan of owner@example.test for "
        f"{START.isoformat()} to {END.isoformat()} (UTC), up to 20 emails"
    )
    assert result["scan_scope"] == {
        "mailbox_id": mailbox,
        "from_timestamp": midnight(START),
        "until_timestamp": midnight(END + timedelta(days=1)),
        "max_messages": 20,
    }
    assert result["read_trace"] == [{"tool": "list_mailboxes"}]
    [run] = case.runs()
    assert run.id == result["scan_run_id"]
    assert run.handler_key == "gmail_discovery"
    assert run.state == "queued"
    assert '"model": "fixture-model"' in run.config_json
    assert case.credential in run.config_json

    replay = case.send(conversation, "scan", text)
    assert replay["result"] == result
    assert len(case.runs()) == 1


def test_evidence_only_scan_needs_no_ai_discovery(case: ScanCase) -> None:
    mailbox = case.mailbox("owner@example.test")
    queued = case.send(
        case.conversation(),
        "evidence",
        "Import my email text from yesterday, up to 5 messages, as evidence only.",
        step("list_mailboxes"),
        step(
            "start_email_scan",
            email_scan=scan(
                mailbox,
                purpose="import_evidence",
                purpose_quote="as evidence only",
                period_quote="yesterday",
                from_date=(TODAY - timedelta(days=1)).isoformat(),
                until_date=(TODAY - timedelta(days=1)).isoformat(),
                max_messages=5,
            ),
        ),
    )
    assert "no AI reads these emails" in queued["result"]["text"]
    assert "up to 5 emails" in queued["result"]["text"]
    [run] = case.runs()
    assert run.handler_key == "gmail_import"
    assert "credential_id" not in run.config_json


@pytest.mark.parametrize(
    ("values", "error"),
    [
        ({"purpose_quote": "receipts"}, "purpose_quote"),
        ({"period_quote": "in March"}, "period_quote"),
        ({"max_messages": 40}, "max_messages"),
        ({"until_date": (TODAY + timedelta(days=1)).isoformat()}, "past days"),
        ({"from_date": (TODAY - timedelta(days=40)).isoformat()}, "31 days"),
        ({"from_date": "2026-02-30"}, "real YYYY-MM-DD"),
        ({"mailbox_id": "invented"}, "Unknown mailbox"),
    ],
)
def test_unsupported_scope_queues_nothing(
    case: ScanCase, values: dict[str, Any], error: str
) -> None:
    mailbox = case.mailbox("owner@example.test")
    seen: list[str] = []

    def answer(payload: dict[str, Any]) -> dict[str, Any]:
        seen.append(payload["steps"][-1]["error"])
        return step("answer", message="I need a clearer request.")

    replied = case.send(
        case.conversation(),
        "refused",
        "Find purchases in my email from last week.",
        step("list_mailboxes"),
        step("start_email_scan", email_scan=scan(mailbox, **values)),
        answer,
    )
    assert error in seen[0]
    assert replied["result"]["text"].endswith("No changes were saved.")
    assert case.runs() == []


def test_foreign_mailbox_and_unnamed_choice_ask_first(case: ScanCase) -> None:
    foreign = case.mailbox("bob@example.test", case.other_actor)
    work = case.mailbox("work@example.test")
    case.mailbox("home@example.test")
    conversation = case.conversation()
    errors: list[str] = []

    def ask(payload: dict[str, Any]) -> dict[str, Any]:
        errors.extend(s["error"] for s in payload["steps"] if "error" in s)
        listed = payload["steps"][0]["result"]["mailboxes"]
        assert {m["address"] for m in listed} == {
            "work@example.test",
            "home@example.test",
        }
        return step("clarify", message="Which mailbox should I scan?")

    question = case.send(
        conversation,
        "ask",
        "Find purchases in my email from last week.",
        step("list_mailboxes"),
        step("start_email_scan", email_scan=scan(foreign)),
        step("start_email_scan", email_scan=scan(work)),
        ask,
    )
    assert "Unknown mailbox" in errors[0]
    assert "Several mailboxes" in errors[1]
    assert question["result"]["assistant_pending"]["kind"] == "clarify"
    assert case.runs() == []

    # The answer names the address; the period quote comes from the origin turn.
    answered = case.send(
        conversation,
        "answer",
        "work@example.test",
        step("list_mailboxes"),
        step("start_email_scan", email_scan=scan(work)),
    )
    assert answered["result"]["scan_run_id"]
    [run] = case.runs()
    assert work in run.config_json


def test_busy_mailbox_permission_and_cancel_queue_nothing_more(
    case: ScanCase,
) -> None:
    mailbox = case.mailbox("owner@example.test")
    conversation = case.conversation()
    text = "Find purchases in my email from last week."
    case.send(
        conversation,
        "first",
        text,
        step("list_mailboxes"),
        step("start_email_scan", email_scan=scan(mailbox)),
    )
    busy = case.send(
        conversation,
        "second",
        text,
        step("list_mailboxes"),
        step("start_email_scan", email_scan=scan(mailbox)),
    )
    assert "already queued or running" in busy["result"]["text"]
    assert len(case.runs()) == 1
    with Session(case.engine) as db:
        db.get(ScanRun, case.runs()[0].id).state = "completed"  # type: ignore[union-attr]
        db.commit()

    def cancel(payload: dict[str, Any]) -> dict[str, Any]:
        ChatService(case.engine).cancel(case.actor, "stopped")
        return step("start_email_scan", email_scan=scan(mailbox))

    stopped = case.send(conversation, "stopped", text, step("list_mailboxes"), cancel)
    assert stopped["state"] == "canceled"
    assert len(case.runs()) == 1

    def revoke(payload: dict[str, Any]) -> dict[str, Any]:
        with Session(case.engine) as db:
            consent = db.get(UserSettings, case.actor.id)
            assert consent is not None
            consent.allow_external_ai = False
            db.commit()
        return step("start_email_scan", email_scan=scan(mailbox))

    refused = case.send(conversation, "revoked", text, step("list_mailboxes"), revoke)
    assert refused["result"]["text"] == (
        "Choose an available AI connection and enable external AI. "
        "No changes were saved."
    )
    assert "scan_run_id" not in refused["result"]
    assert len(case.runs()) == 1
