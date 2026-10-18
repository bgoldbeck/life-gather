from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_mcp_http import rpc, signed_headers
from test_reconciliation import setup

from lifegather.assets.actions import ActionService, AssetChange
from lifegather.assets.service import AssetList, AssetRead, AssetService
from lifegather.main import create_app
from lifegather.memory.schemas import FactInput, SourceInput
from lifegather.memory.service import MemoryService
from lifegather.reconciliation.schemas import DiscoveryInput
from lifegather.reconciliation.service import ReconciliationService


def item(memory, reconcile, actor, key="first"):
    source = memory.ingest(
        actor,
        SourceInput(
            text="Synthetic Acme Drill serial S1",
            external_id=key,
            namespace="inventory-test",
        ),
    )
    return reconcile.discover(
        actor,
        DiscoveryInput(
            source_id=source.id,
            item_key=key,
            name="Drill",
            manufacturer="Acme",
            serial="S1",
            quantity=1,
            kind="purchase",
            quote=source.text,
        ),
    )


@pytest.mark.parametrize("status", ["sold", "returned", "no_longer_owned"])
def test_negative_ownership_excludes_current_discovery_inventory_and_buyback_restores(
    tmp_path: Path, status: str
) -> None:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    original = item(memory, reconcile, actor)
    asset = original.asset_ids[0]
    actions = ActionService(auth.engine)
    sold = actions.apply(
        actor,
        AssetChange.model_validate(
            dict(
                asset_id=asset,
                request_id="excluded",
                operation="ownership",
                status=status,
                note="Synthetic negative ownership statement.",
            )
        ),
    )
    assert reconcile.inventory(actor) == []
    assert AssetService(auth.engine).list(actor, AssetList())["items"] == []
    historical = AssetService(auth.engine).get(actor, AssetRead(asset_id=asset))
    assert historical["decisions"][0]["id"] == original.decision_id
    assert reconcile.inventory(bob) == []
    actions.apply(
        actor,
        AssetChange(
            asset_id=asset,
            request_id="buyback",
            expected_action_id=sold["id"],
            operation="ownership",
            status="owned",
            note="I bought this synthetic item back.",
        ),
    )
    assert reconcile.inventory(actor) == [asset]


@pytest.mark.parametrize(
    "interval,expected",
    [
        ("current", "review"),
        ("future", "enrich"),
        ("past", "enrich"),
        ("future_open", "enrich"),
        ("starts_today", "review"),
        ("ends_today", "enrich"),
    ],
)
def test_matcher_uses_current_world_date_for_finite_negative_intervals(
    tmp_path: Path, interval: str, expected: str
) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    first = item(memory, reconcile, actor)
    today = datetime.now(UTC).date()
    offsets = {
        "current": (-1, 1),
        "future": (1, 2),
        "past": (-2, -1),
        "future_open": (1, None),
        "starts_today": (0, 1),
        "ends_today": (-1, 0),
    }
    start, end = offsets[interval]
    source = memory.ingest(
        actor, SourceInput(text="Synthetic dated negative statement.")
    )
    memory.assert_fact(
        actor,
        FactInput(
            subject_id=first.asset_ids[0],
            predicate="owned",
            value=False,
            status="stated",
            source_id=source.id,
            quote=source.text,
            valid_from=today + timedelta(days=start),
            valid_to=today + timedelta(days=end) if end is not None else None,
            operation_key="interval",
        ),
    )
    outcome = item(memory, reconcile, actor, "second")
    assert outcome.outcome == expected
    listed = reconcile.inventory(actor)
    assert listed == ([] if expected == "review" else first.asset_ids)


def test_mcp_inventory_filters_negative_ownership_before_paging() -> None:
    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "inventory-owner")
        foreign, _ = signed_headers(app, "inventory-foreign")
        engine = app.state.auth_store.engine
        memory = MemoryService(engine)
        reconcile = ReconciliationService(engine)
        first = item(memory, reconcile, actor)
        ActionService(engine).apply(
            actor,
            AssetChange(
                asset_id=first.asset_ids[0],
                request_id="sold",
                operation="ownership",
                status="sold",
                note="Sold synthetic item.",
            ),
        )
        result = rpc(client, headers, "discovery_inventory", {"limit": 1}).json()[
            "result"
        ]["structuredContent"]
        assert result == {"items": [], "next_cursor": None}
        assert (
            rpc(client, foreign, "discovery_inventory", {}).json()["result"][
                "structuredContent"
            ]["items"]
            == []
        )
        # Exclusions are applied before the database limit, so a sold row cannot
        # consume the first slot and hide later current items.
        others = []
        for index in range(3):
            source = memory.ingest(
                actor, SourceInput(text=f"I own synthetic item {index}.")
            )
            record = reconcile.discover(
                actor,
                DiscoveryInput(
                    source_id=source.id,
                    item_key=str(index),
                    name=f"synthetic item {index}",
                    quantity=1,
                    kind="possession",
                    quote=source.text,
                ),
            )
            others.extend(record.asset_ids)
        others.sort()
        ActionService(engine).apply(
            actor,
            AssetChange(
                asset_id=others[0],
                request_id="sold-first",
                operation="ownership",
                status="sold",
                note="Sold the first item in UUID order.",
            ),
        )
        page = rpc(client, headers, "discovery_inventory", {"limit": 1}).json()[
            "result"
        ]["structuredContent"]
        assert page["items"] == [others[1]]
        following = rpc(
            client,
            headers,
            "discovery_inventory",
            {"limit": 1, "cursor": page["next_cursor"]},
        ).json()["result"]["structuredContent"]
        assert following["items"] == [others[2]]
