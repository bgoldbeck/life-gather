from pathlib import Path

import pytest
from test_asset_consolidation import prepared
from test_maintenance import change, plan

from lifegather.assets.consolidation import ReverseConsolidation
from lifegather.maintenance.schemas import MaintenancePage
from lifegather.maintenance.service import MaintenanceService
from lifegather.memory.service import MemoryError


def test_tasks_follow_identity_and_preserve_links_and_reversal_guards(
    tmp_path: Path,
) -> None:
    store, alice, _, _, _, records, consolidation, request = prepared(tmp_path)
    original_preview = request()
    maintenance = MaintenanceService(store.engine)
    created = maintenance.create(alice, plan(records[1].id))
    original = maintenance.get(alice, created["id"])
    # New domain records must invalidate an earlier complete-record preview.
    with pytest.raises(MemoryError, match="changed"):
        consolidation.apply(alice, original_preview)
    preview = consolidation.preview(alice, records[0].id, records[1].id)
    summary = preview["comparison"]["sections"]["maintenance"]
    assert len(summary) == 1 and summary[0]["asset_id"] == records[1].id
    assert summary[0]["source_id"] == original["revision"]["source_id"]
    joined = consolidation.apply(alice, request())
    merged = maintenance.get(alice, created["id"])
    assert merged["entity_id"] == records[1].id
    assert merged["target"]["id"] == records[0].id
    assert merged["revision"] == original["revision"]
    context = maintenance.source_context(alice, original["revision"]["source_id"])
    assert context is not None
    assert context["entity_id"] == records[1].id
    assert context["target"]["id"] == records[0].id
    assert (
        maintenance.list(alice, MaintenancePage(entity_id=records[0].id))["items"][0][
            "id"
        ]
        == created["id"]
    )
    assert (
        maintenance.list(alice, MaintenancePage(entity_id=records[1].id))["items"][0][
            "id"
        ]
        == created["id"]
    )
    with pytest.raises(MemoryError, match="changed"):
        maintenance.revise(alice, change(original, "stale-before-merge"))
    consolidation.reverse(
        alice,
        ReverseConsolidation(
            consolidation_id=joined["id"],
            request_id="reverse",
            note="Keep the original records separate.",
        ),
    )
    assert maintenance.get(alice, created["id"])["target"]["id"] == records[1].id
    context = maintenance.source_context(alice, original["revision"]["source_id"])
    assert context is not None and context["target"]["id"] == records[1].id
    with pytest.raises(MemoryError, match="changed"):
        maintenance.revise(alice, change(merged, "stale-after-reverse"))
    again = consolidation.apply(
        alice, request().model_copy(update={"request_id": "join-again"})
    )
    maintenance.revise(
        alice,
        change(
            maintenance.get(alice, created["id"]),
            "complete-after-merge",
            state="completed",
        ),
    )
    with pytest.raises(MemoryError, match="changed"):
        consolidation.reverse(
            alice,
            ReverseConsolidation(
                consolidation_id=again["id"],
                request_id="blocked-reversal",
                note="Must inspect the intervening task revision.",
            ),
        )
    store.engine.dispose()


def test_comparison_refuses_partial_maintenance_and_keeps_empty_legacy_contract(
    tmp_path: Path,
) -> None:
    store, alice, _, _, _, records, consolidation, _ = prepared(tmp_path)
    before = consolidation.preview(alice, records[0].id, records[1].id)["comparison"]
    assert "maintenance" not in before["sections"]
    assert (
        "maintenance" not in before["limits"] and "maintenance" not in before["counts"]
    )
    maintenance = MaintenanceService(store.engine)
    for index in range(21):
        maintenance.create(alice, plan(records[0].id, request_id=f"bounded-{index}"))
    with pytest.raises(MemoryError, match="limits"):
        consolidation.preview(alice, records[0].id, records[1].id)
    from lifegather.assets.comparison import RecordComparison, RecordComparisonService

    result = RecordComparisonService(store.engine).get(
        alice, RecordComparison(asset_id=records[0].id, target_asset_id=records[1].id)
    )
    assert not result["complete"] and result["sections"] == {}
    assert result["counts"]["maintenance"] == 21
    assert "maintenance" in result["limited_sections"]
    store.engine.dispose()
