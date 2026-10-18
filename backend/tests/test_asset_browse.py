from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_asset_proposals import review, setup
from test_mcp_http import rpc, signed_headers

from lifegather.assets.service import AssetList, AssetRead, AssetService
from lifegather.main import create_app
from lifegather.memory.schemas import FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.schemas import DiscoveryInput
from lifegather.reconciliation.service import ReconciliationService


def test_private_asset_detail_and_history(tmp_path: Path) -> None:
    auth, alice, bob, memory, original, proposals, proposal = setup(tmp_path)
    accepted = proposals.review(alice, review(proposal["id"]))
    identifier = accepted["result"]["asset_ids"][0]
    assets = AssetService(auth.engine)
    assert assets.list(alice, AssetList())["items"][0]["id"] == identifier
    assert assets.list(bob, AssetList(include_history=True))["items"] == []
    detail = assets.get(alice, AssetRead(asset_id=identifier))
    assert detail["in_inventory"] is True
    assert detail["decisions"][0]["quote"] == original.text
    assert detail["decisions"][0]["manufacturer"] == "Husqvarna"
    assert any(f["status"] == "inferred" for f in detail["facts"])
    assert any(f["object_name"] == "Husqvarna 525L" for f in detail["facts"])
    with pytest.raises(MemoryError):
        assets.get(bob, AssetRead(asset_id=identifier))
    reconciliation = ReconciliationService(auth.engine)
    reconciliation.undo(alice, accepted["result"]["decision_id"])
    assert assets.list(alice, AssetList())["items"] == []
    assert (
        assets.list(alice, AssetList(include_history=True))["items"][0]["in_inventory"]
        is False
    )
    assert (
        assets.get(alice, AssetRead(asset_id=identifier))["decisions"][0][
            "superseded_at"
        ]
        is not None
    )
    assert memory.get_source(alice, original.id).text == original.text


def test_list_and_fact_paging_search_and_invalid_cursors(tmp_path: Path) -> None:
    auth, alice, _, memory, _, _, _ = setup(tmp_path)
    source = memory.ingest(
        alice, SourceInput(text="\n".join(f"I own Tool {n}." for n in range(27)))
    )
    reconciliation = ReconciliationService(auth.engine)
    identifiers = []
    for number in range(27):
        result = reconciliation.discover(
            alice,
            DiscoveryInput(
                source_id=source.id,
                item_key=str(number),
                name=f"Tool {number}",
                quantity=1,
                kind="possession",
                quote=f"I own Tool {number}.",
            ),
        )
        identifiers.extend(result.asset_ids)
    assets = AssetService(auth.engine)
    first = assets.list(alice, AssetList())
    second = assets.list(alice, AssetList(cursor=first["next_cursor"]))
    assert len(first["items"]) == 25 and len(second["items"]) == 2
    assert len({row["id"] for row in first["items"] + second["items"]}) == 27
    assert len(assets.list(alice, AssetList(query="TOOL 26"))["items"]) == 1
    assert assets.list(alice, AssetList(query="%"))["items"] == []
    asset_id = identifiers[0]
    for index in range(27):
        memory.assert_fact(
            alice,
            FactInput(
                subject_id=asset_id,
                predicate="note",
                value=str(index),
                source_id=source.id,
                quote="I own Tool 0.",
                operation_key=f"fact-{index}",
            ),
        )
    facts = assets.get(alice, AssetRead(asset_id=asset_id))
    later = assets.get(
        alice, AssetRead(asset_id=asset_id, fact_cursor=facts["next_fact_cursor"])
    )
    assert len(facts["facts"]) == 25 and len(later["facts"]) == 3
    with pytest.raises(MemoryError):
        assets.get(alice, AssetRead(asset_id=asset_id, fact_cursor="foreign"))
    with pytest.raises(MemoryError):
        assets.get(alice, AssetRead(asset_id=asset_id, decision_cursor="foreign"))


def test_http_and_mcp_browsing_is_authenticated_and_bounded() -> None:
    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        memory = MemoryService(app.state.auth_store.engine)
        source = memory.ingest(actor, SourceInput(text="I own a synthetic drill."))
        result = ReconciliationService(memory.engine).discover(
            actor,
            DiscoveryInput(
                source_id=source.id,
                item_key="drill",
                name="synthetic drill",
                quantity=1,
                kind="possession",
                quote=source.text,
            ),
        )
        identifier = result.asset_ids[0]
        assert client.get("/api/assets").status_code == 401
        assert client.get("/api/assets?limit=26", headers=alice).status_code == 422
        assert client.get("/api/assets", headers=bob).json()["items"] == []
        assert client.get(f"/api/assets/{identifier}", headers=bob).status_code == 400
        assert (
            client.get(f"/api/assets/{identifier}", headers=alice).json()["asset"][
                "name"
            ]
            == "synthetic drill"
        )
        listed = rpc(client, alice, "assets_list", {}).json()["result"][
            "structuredContent"
        ]
        assert listed["items"][0]["id"] == identifier
        assert (
            rpc(client, alice, "asset_detail", {"asset_id": identifier}).json()[
                "result"
            ]["structuredContent"]["in_inventory"]
            is True
        )
        assert (
            rpc(client, bob, "asset_detail", {"asset_id": identifier}).json()["result"][
                "isError"
            ]
            is True
        )
        assert (
            client.get(
                f"/api/assets/{identifier}?decision_cursor=foreign", headers=alice
            ).status_code
            == 400
        )
