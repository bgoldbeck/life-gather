import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient
from test_asset_actions import change
from test_evidence_batch import batch
from test_mcp_http import rpc, signed_headers
from test_reconciliation import discovery
from test_replacements import replacement
from test_unit_corrections import prepared

from lifegather.assets.actions import ActionService
from lifegather.assets.batch import EvidenceRestore
from lifegather.assets.replacements import (
    ReplacementRecord,
    ReplacementService,
    ReplacementWithdraw,
)
from lifegather.chat.provider import Completion
from lifegather.chat.recall import RecallPlan, RecallTools
from lifegather.chat.service import ChatService
from lifegather.main import create_app
from lifegather.memory.schemas import EntityInput, SourceInput
from lifegather.memory.service import MemoryService
from lifegather.reconciliation.service import ReconciliationService


def plan(name: str) -> RecallPlan:
    return RecallPlan(
        query="unmatchableword", entity_names=[name], include_connections=False
    )


def test_named_recall_includes_incoming_batch_and_current_reversal_state(
    tmp_path: Path,
) -> None:
    auth, actor, bob, _, _, _, _, target, _, service, _, move = batch(tmp_path)
    result = service.move(actor, move)
    tools = RecallTools(ChatService(auth.engine))
    context = tools.collect(actor, plan(target.name))
    record = context["records"][0]
    assert record["in_inventory"] is True
    assert record["corrections"][0]["action_id"] == result["id"]
    assert record["corrections"][0]["direction"] == "incoming"
    source = next(
        row for row in context["evidence"] if row["id"] == result["source_id"]
    )
    assert source["asset_context"]["association_versions_current"] == 2
    assert len(record["purchases"]) == 2
    assert any(trace["tool"] == "asset_detail" for trace in context["read_trace"])
    service.restore(
        actor,
        EvidenceRestore(
            action_id=result["id"],
            request_id="recall-restore",
            note="Restore these associations.",
        ),
    )
    context = tools.collect(actor, plan(target.name))
    assert not context["records"][0]["in_inventory"]
    assert not context["records"][0]["purchases"]
    original = next(
        row for row in context["evidence"] if row["id"] == result["source_id"]
    )
    assert original["asset_context"]["association_versions_current"] == 0
    assert original["asset_context"]["association_versions_total"] == 2
    assert not tools.collect(bob, plan(target.name))["records"]


def test_keyword_recall_finds_unnamed_incoming_moves_and_preserves_other_targets(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile, receipt, line, target, request = prepared(
        tmp_path
    )
    source_id = line["asset_ids"][0]
    other = receipt["result"]["lines"][1]
    reconcile.resolve(actor, other["id"], other["decision_id"], asset_ids=[source_id])
    actions = ActionService(auth.engine)
    first = actions.apply(
        actor, request.model_copy(update={"note": "It belongs here."})
    )
    source = memory.ingest(actor, SourceInput(text="A separate synthetic destination."))
    second_target = memory.create_entity(
        actor,
        EntityInput(
            name="Other destination",
            kind="asset",
            source_id=source.id,
            operation_key="other-target",
        ),
    )
    actions.apply(
        actor,
        request.model_copy(
            update={
                "request_id": "other-move",
                "decision_id": reconcile.get(actor, other["id"]).decision_id,
                "target_asset_id": second_target.id,
                "expected_action_id": first["id"],
                "note": "This other evidence belongs there.",
            }
        ),
    )
    assert actions.related_sources(actor, [], [target.id]) == [first["source_id"]]
    rows = ChatService(auth.engine).evidence(actor, target.name)
    assert any(
        row["id"] == first["source_id"] and row["text"] == "It belongs here."
        for row in rows
    )


def test_recall_distinguishes_superseded_ownership_from_current_inventory(
    tmp_path: Path,
) -> None:
    auth, actor, _, _, _, _, line, _, _ = prepared(tmp_path)
    identifier = line["asset_ids"][0]
    actions = ActionService(auth.engine)
    sold = actions.apply(actor, change(identifier))
    owned = actions.apply(
        actor,
        change(
            identifier,
            expected_action_id=sold["id"],
            request_id="buyback",
            status="owned",
            event_date="2025-01-02",
            note="I bought this item back.",
        ),
    )
    sold_context = actions.source_context(actor, sold["source_id"])
    owned_context = actions.source_context(actor, owned["source_id"])
    assert sold_context is not None and owned_context is not None
    assert sold_context["ownership_statement_current_version"] is False
    assert owned_context["ownership_statement_current_version"] is True
    context = RecallTools(ChatService(auth.engine)).collect(actor, plan("Drill"))
    record = next(
        row for row in context["records"] if row["entity"]["id"] == identifier
    )
    assert record["in_inventory"] is True
    assert "not verified" in record["inventory_status"]
    assert {row["action_id"] for row in record["corrections"]} == {
        sold["id"],
        owned["id"],
    }


def test_replacement_withdrawal_metadata_applies_to_named_and_keyword_sources(
    tmp_path: Path,
) -> None:
    auth, actor, bob, _, _, _, target, service, request = replacement(tmp_path)
    result = service.change(actor, request)
    withdrawn = service.change(
        actor,
        ReplacementWithdraw(
            action_id=result["id"],
            request_id="withdraw",
            note="Wrong record was selected.",
        ),
    )
    context = RecallTools(ChatService(auth.engine)).collect(actor, plan(target.name))
    assert {row["action_id"] for row in context["records"][0]["corrections"]} == {
        result["id"],
        withdrawn["id"],
    }
    for identifier in (result["source_id"], withdrawn["source_id"]):
        source = next(row for row in context["evidence"] if row["id"] == identifier)
        assert source["asset_context"]["replacement_statement_current_version"] is False
        assert source["asset_context"]["replacement_event_date"] == "2025-01-02"
    assert not ActionService(auth.engine).related_sources(
        bob, [], [request.asset_id, target.id]
    )


def test_correction_recall_remains_bounded_and_does_not_leave_uncited_entries(
    tmp_path: Path,
) -> None:
    auth, actor, _, _, _, _, _, _, _, service, _, move = batch(tmp_path)
    service.move(actor, move)
    actions = ActionService(auth.engine)
    head = ""
    for index in range(4):
        result = actions.apply(
            actor,
            change(
                move.target_asset_id,
                expected_action_id=head,
                request_id=f"long-{index}",
                status="owned" if index % 2 else "sold",
                event_date=None,
                note="🧰" * 2000,
            ),
        )
        head = result["id"]
    tools = RecallTools(ChatService(auth.engine))
    for budget in (1200, 2400, 5000, 24000):
        context = tools.collect(actor, plan("Existing replacement"), max_bytes=budget)
        assert len(json.dumps(context, ensure_ascii=False).encode()) <= budget
        assert len(context["evidence"]) <= 8
        identifiers = {source["id"] for source in context["evidence"]}
        for record in context["records"]:
            assert len(record["corrections"]) <= 3
            assert record["corrections_limited"] is True
            assert all(row["source_id"] in identifiers for row in record["corrections"])


def test_private_source_metadata_and_two_call_answer_contract() -> None:
    app = create_app()

    class Fake:
        calls = 0

        async def complete(
            self,
            secret: str,
            model: str,
            instruction: str,
            payload: dict[str, Any],
            schema: Any,
        ) -> Completion:
            self.calls += 1
            if schema is RecallPlan:
                return Completion(plan("Replacement drill").model_dump(), 5, 5)
            assert "superseded ownership or replacement" in instruction
            assert "never merges items" in instruction
            record = payload["records"][0]
            assert record["corrections"][0]["direction"] == "incoming"
            correction = next(
                row
                for row in payload["evidence"]
                if row.get("asset_context", {}).get("operation")
                == "replacement_withdrawn"
            )
            assert (
                correction["asset_context"]["replacement_statement_current_version"]
                is False
            )
            return Completion(
                {
                    "text": "The earlier replacement statement was withdrawn; "
                    "no current replacement is established.",
                    "source_ids": [correction["id"]],
                },
                5,
                5,
            )

    with TestClient(app) as client:
        headers, actor = signed_headers(app, "recall-owner")
        foreign_headers, _ = signed_headers(app, "recall-foreign")
        engine = app.state.auth_store.engine
        memory = MemoryService(engine)
        original = ReconciliationService(engine).discover(
            actor, discovery(memory, actor)
        )
        target = memory.create_entity(
            actor,
            EntityInput(
                name="Replacement drill",
                kind="asset",
                source_id=discovery(memory, actor, key="target").source_id,
                operation_key="target",
            ),
        )
        service = ReplacementService(engine)
        result = service.change(
            actor,
            ReplacementRecord(
                asset_id=original.asset_ids[0],
                target_asset_id=target.id,
                request_id="replace",
                note="It replaced this one.",
            ),
        )
        withdrawn = service.change(
            actor,
            ReplacementWithdraw(
                action_id=result["id"], request_id="withdraw", note="Wrong item."
            ),
        )
        source = client.get(
            "/api/chat/sources/" + result["source_id"], headers=headers
        ).json()
        assert source["asset_context"]["replacement_statement_current_version"] is False
        assert (
            client.get(
                "/api/chat/sources/" + result["source_id"], headers=foreign_headers
            ).status_code
            == 400
        )
        through_mcp = rpc(
            client, headers, "memory_source", {"source_id": result["source_id"]}
        ).json()["result"]["structuredContent"]
        assert through_mcp["asset_context"] == source["asset_context"]
        vault = app.state.private_settings
        vault.cipher = AESGCM(bytes(32))
        credential = vault.save(actor, "ai", "openai", "Synthetic", "synthetic")
        vault.set_preferences(actor, True)
        fake = Fake()
        app.state.chat_provider = fake
        conversation = client.post("/api/chat/conversations", headers=headers).json()[
            "id"
        ]
        turn = client.post(
            f"/api/chat/conversations/{conversation}/turns",
            headers=headers,
            json={
                "mode": "ask",
                "request_id": "question",
                "text": "What replaced the original?",
                "model": "synthetic",
                "credential_id": credential.id,
            },
        ).json()
        assert turn["state"] == "complete", turn
        assert fake.calls == 2
        assert turn["result"]["sources"][0]["id"] == withdrawn["source_id"]
