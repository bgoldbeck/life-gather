from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_asset_actions import prepared

from lifegather.assets.actions import AssetChange
from lifegather.assets.models import AssetAction
from lifegather.memory.schemas import EntityInput


@pytest.mark.parametrize("operation", ["undo", "reassociate", "reassociate_new"])
def test_individual_correction_source_and_effect_share_recorded_time(
    tmp_path: Path, operation: str
) -> None:
    auth, actor, _, memory, original, discovery, actions = prepared(tmp_path)
    asset_id = discovery["asset_ids"][0]
    target = memory.create_entity(
        actor,
        EntityInput(
            name="Synthetic destination",
            kind="asset",
            source_id=original.id,
            operation_key="clock-target",
        ),
    )
    anchor = actions.reconcile.get(actor, discovery["id"]).recorded_at
    actions.memory.clock = lambda: anchor - 1_000_000
    actions.reconcile.memory.clock = lambda: anchor + 1_000_000
    request = AssetChange(
        asset_id=asset_id,
        request_id="clock-correction",
        note="Correct this evidence.",
        operation="undo" if operation == "undo" else "reassociate",
        decision_id=discovery["decision_id"],
        target_asset_id=target.id if operation == "reassociate" else None,
    )
    result = actions.apply(actor, request)
    with Session(auth.engine) as db:
        row = db.scalar(select(AssetAction).where(AssetAction.id == result["id"]))
        assert row is not None
        source = memory.get_source(actor, row.source_id)
        assert (
            row.recorded_at == source.recorded_at == result["decision"]["recorded_at"]
        )
        assert row.recorded_at > anchor
        for identifier in [asset_id, *result["decision"]["asset_ids"]]:
            assert [
                f.id for f in memory.facts(actor, identifier, known_at=row.recorded_at)
            ] == [f.id for f in memory.facts(actor, identifier)]
    assert actions.apply(actor, request) == result
