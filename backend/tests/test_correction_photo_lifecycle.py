"""Composed correction, photo reuse, replacement, recall and recovery regression."""

from pathlib import Path

import pytest
from stored_files import files
from test_asset_actions import change
from test_evidence_batch import batch
from test_photos import image_bytes

from lifegather.assets.actions import ActionService
from lifegather.assets.batch import EvidenceBatchService, EvidenceRestore
from lifegather.assets.purchases import AssetPurchases, AssetPurchasesRead
from lifegather.assets.replacements import (
    ReplacementRecord,
    ReplacementService,
    ReplacementWithdraw,
)
from lifegather.auth.store import AuthStore
from lifegather.chat.recall import RecallPlan, RecallTools
from lifegather.chat.service import ChatService
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.notes import NoteConflict
from lifegather.memory.schemas import EntityInput, SourceInput
from lifegather.photos.service import PhotoAttach, PhotoList, PhotoService


def test_evidence_and_photo_reuse_replacement_manual_recovery_and_private_recall(
    tmp_path: Path,
) -> None:
    auth, actor, foreign, memory, reconcile, _, line, target, _, batches, _, move = (
        batch(tmp_path)
    )
    photos = PhotoService(auth.engine, files(auth.engine))
    original = photos.upload(
        actor, image_bytes(), "synthetic.jpg", "receipt", move.asset_id
    )
    moved = batches.move(actor, move)
    photo_request = PhotoAttach(
        photo_id=original["id"],
        asset_id=target.id,
        expected_updated_at=original["updated_at"],
    )
    linked = photos.link(actor, photo_request)
    source = memory.ingest(
        actor, SourceInput(text="A distinct synthetic replacement item.")
    )
    replacement = memory.create_entity(
        actor,
        EntityInput(
            name="Third distinct item",
            kind="asset",
            source_id=source.id,
            operation_key="third-item",
        ),
    )
    replacements = ReplacementService(auth.engine)
    replacement_request = ReplacementRecord(
        asset_id=target.id,
        target_asset_id=replacement.id,
        request_id="lifecycle-replacement",
        note="The third item replaced this distinct item.",
        event_date="2025-01-02",
    )
    recorded = replacements.change(actor, replacement_request)
    withdrawn_request = ReplacementWithdraw(
        action_id=recorded["id"],
        request_id="lifecycle-withdraw",
        note="The selected replacement was mistaken.",
    )
    withdrawn = replacements.change(actor, withdrawn_request)
    before = memory.export_page(actor, "sources")
    with pytest.raises(NoteConflict):
        batches.restore(
            actor,
            EvidenceRestore(
                action_id=moved["id"],
                request_id="blocked-restore",
                note="Later correction history must be preserved.",
            ),
        )
    assert memory.export_page(actor, "sources") == before

    # Explicit individual correction remains possible after later history blocks
    # the stricter batch reversal, without undoing a photo link or replacement.
    actions = ActionService(auth.engine)
    head = withdrawn["id"]
    for index, entry in enumerate(moved["entries"]):
        recovered = actions.apply(
            actor,
            change(
                target.id,
                request_id=f"manual-recover-{index}",
                expected_action_id=head,
                operation="reassociate",
                status=None,
                event_date=None,
                decision_id=entry["moved_decision_id"],
                target_asset_id=move.asset_id,
                note="Explicitly restore this source unit to its earlier record.",
            ),
        )
        head = recovered["id"]
    assert reconcile.get(actor, line["id"]).asset_ids == line["asset_ids"]
    purchases = AssetPurchases(auth.engine)
    assert not purchases.get(actor, AssetPurchasesRead(asset_id=target.id))["items"]
    old_claims = purchases.get(actor, AssetPurchasesRead(asset_id=move.asset_id))[
        "items"
    ]
    assert len(old_claims) == 2 and any(
        row["claim"] and row["claim"]["total_minor"] == 4990 for row in old_claims
    )
    for identifier in (move.asset_id, target.id):
        assert (
            photos.list(actor, PhotoList(asset_id=identifier))["items"][0]["id"]
            == original["id"]
        )
    assert photos.binary(actor, original["id"], True)[0] == image_bytes()

    snapshot = tmp_path / "lifecycle.sqlite3"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(snapshot)
    restored.migrate()
    assert EvidenceBatchService(restored.engine).move(actor, move) == moved
    assert (
        ReplacementService(restored.engine).change(actor, replacement_request)
        == recorded
    )
    assert (
        ReplacementService(restored.engine).change(actor, withdrawn_request)
        == withdrawn
    )
    assert (
        PhotoService(restored.engine, files(restored.engine)).link(actor, photo_request)
        == linked
    )
    context = RecallTools(ChatService(restored.engine)).collect(
        actor,
        RecallPlan(
            query="unmatchableword",
            entity_names=[target.name],
            include_connections=True,
        ),
    )
    assert not context["records"][0]["in_inventory"]
    assert not context["records"][0]["purchases"]
    assert not context["records"][0]["connections"]
    assert context["records"][0]["corrections_limited"]
    assert not RecallTools(ChatService(restored.engine)).collect(
        foreign,
        RecallPlan(
            query="unmatchableword",
            entity_names=[target.name],
            include_connections=True,
        ),
    )["records"]
