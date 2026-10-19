from pathlib import Path

import pytest
from test_unit_corrections import prepared

from lifegather.assets.actions import ActionService, AssetChange
from lifegather.assets.service import AssetRead, AssetService
from lifegather.memory.service import MemoryError


def test_incoming_correction_history_keeps_own_write_head_and_private_paging(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, _, _, line, target, request = prepared(tmp_path)
    actions = ActionService(auth.engine)
    assets = AssetService(auth.engine)
    moved = actions.apply(actor, request)
    incoming = assets.get(actor, AssetRead(asset_id=target.id))
    assert incoming["action_head"] == ""
    assert incoming["actions"][0]["id"] == moved["id"]
    assert incoming["actions"][0]["direction"] == "incoming"
    assert incoming["actions"][0]["asset_id"] == line["asset_ids"][0]
    assert incoming["actions"][0]["target_asset_id"] == target.id
    assert incoming["actions"][0]["note"] == request.note
    context = actions.source_context(actor, moved["source_id"])
    assert context is not None
    assert context["target_asset_name"] == target.name
    assert actions.source_context(bob, moved["source_id"]) is None
    sold = actions.apply(
        actor,
        AssetChange(
            asset_id=target.id,
            request_id="sold-target",
            operation="ownership",
            status="sold",
            note="Sold the receiving item.",
        ),
    )
    page = assets.get(actor, AssetRead(asset_id=target.id, limit=1))
    assert page["action_head"] == sold["id"] and page["actions"][0]["id"] == sold["id"]
    previous = assets.get(
        actor,
        AssetRead(
            asset_id=target.id, action_cursor=page["next_action_cursor"], limit=1
        ),
    )
    assert previous["actions"][0]["id"] == moved["id"]
    assert previous["action_head"] == sold["id"]
    with pytest.raises(MemoryError):
        assets.get(bob, AssetRead(asset_id=target.id, action_cursor=moved["id"]))
    with pytest.raises(MemoryError):
        assets.get(
            actor, AssetRead(asset_id=line["asset_ids"][1], action_cursor=moved["id"])
        )
    assert memory.get_source(actor, moved["source_id"]).text == request.note


def test_new_single_item_target_is_recorded_for_future_incoming_history(
    tmp_path: Path,
) -> None:
    from test_asset_actions import prepared as single

    auth, actor, _, _, _, discovery, actions = single(tmp_path)
    original = discovery["asset_ids"][0]
    result = actions.apply(
        actor,
        AssetChange(
            asset_id=original,
            request_id="move-new",
            operation="reassociate",
            decision_id=discovery["decision_id"],
            note="This evidence belongs to a different physical item.",
        ),
    )
    target = result["decision"]["asset_ids"][0]
    assert target != original
    history = AssetService(auth.engine).get(actor, AssetRead(asset_id=target))[
        "actions"
    ]
    assert history[0]["id"] == result["id"] and history[0]["direction"] == "incoming"
