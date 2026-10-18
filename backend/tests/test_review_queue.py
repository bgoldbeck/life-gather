from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_asset_proposals import fields, review
from test_asset_proposals import setup as proposal_setup
from test_mcp_http import rpc, signed_headers
from test_reconciliation import discovery, setup

from lifegather.auth.store import AuthStore
from lifegather.chat.service import SaveText, save_text
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.proposals import AssetExtraction, ProposalService
from lifegather.reconciliation.queue import IdentityReview, ReviewPage, ReviewService
from lifegather.reconciliation.service import ReconciliationService


def test_persistent_queue_unifies_proposals_and_identity_with_tenant_paging(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, _, proposals, proposal = proposal_setup(tmp_path)
    reconciler = ReconciliationService(auth.engine)
    proposals.review(actor, review(proposal["id"]))
    pending = reconciler.discover(
        actor, discovery(memory, actor, key="uncertain", order=None)
    )
    assert pending.outcome == "review"
    source = save_text(
        memory, actor, SaveText(text="I own a drill", request_id="drill")
    )
    proposed = proposals.create(
        actor,
        source.id,
        AssetExtraction(
            candidate=fields(
                name="drill",
                manufacturer=None,
                model=None,
                kind="possession",
                quote="I own a drill",
            ),
            explanation="Review this item",
        ),
    )
    queue = ReviewService(auth.engine)
    first = queue.list(actor, ReviewPage(limit=1))
    assert len(first["items"]) == 1 and first["next_cursor"]
    second = queue.list(actor, ReviewPage(limit=1, cursor=first["next_cursor"]))
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    assert {first["items"][0]["kind"], second["items"][0]["kind"]} == {
        "proposal",
        "identity",
    }
    assert queue.list(bob, ReviewPage())["items"] == []
    assert (
        queue.list(actor, ReviewPage(kind="proposals"))["items"][0]["id"]
        == proposed["id"]
    )
    assert (
        queue.list(actor, ReviewPage(kind="identities"))["items"][0]["id"] == pending.id
    )
    with pytest.raises(MemoryError):
        queue.detail(bob, pending.id)
    backup = tmp_path / "queue-snapshot.sqlite3"
    operator_snapshot(auth.engine, backup)
    restored = AuthStore(backup)
    restored.migrate()
    assert ReviewService(restored.engine).list(actor, ReviewPage()) == queue.list(
        actor, ReviewPage()
    )
    restored.engine.dispose()
    auth.engine.dispose()


def test_review_same_different_dismiss_stale_replay_and_quantity(
    tmp_path: Path,
) -> None:
    auth, actor, bob, memory, reconcile = setup(tmp_path)
    existing = reconcile.discover(actor, discovery(memory, actor))
    pending = reconcile.discover(
        actor, discovery(memory, actor, key="uncertain", order=None)
    )
    queue = ReviewService(auth.engine)
    detail = queue.detail(actor, pending.id)
    candidates = [c["id"] for c in detail["candidates"]]
    body = IdentityReview(
        observation_id=pending.id,
        expected_decision_id=pending.decision_id,
        action="link",
        asset_ids=existing.asset_ids,
        candidate_ids=candidates,
    )
    with pytest.raises(MemoryError):
        queue.review(bob, body)
    with pytest.raises(MemoryError, match="duplicates"):
        queue.review(actor, body.model_copy(update={"candidate_ids": []}))
    with ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(lambda _: queue.review(actor, body), range(3)))
    assert outcomes[0] == outcomes[1] == outcomes[2]
    assert outcomes[0]["asset_ids"] == existing.asset_ids
    assert queue.list(actor, ReviewPage())["items"] == []
    with pytest.raises(MemoryError):
        queue.review(actor, body.model_copy(update={"action": "new", "asset_ids": []}))
    undone = reconcile.undo(actor, outcomes[0]["decision_id"])
    assert undone.outcome == "review"
    assert queue.list(actor, ReviewPage())["items"]
    # A new decision head is required after undo, including for dismissal.
    dismissed = queue.review(
        actor,
        IdentityReview(
            observation_id=pending.id,
            expected_decision_id=undone.decision_id,
            action="dismiss",
        ),
    )
    assert dismissed["outcome"] == "dismissed"
    assert len(reconcile.history(actor, pending.id)) == 4
    multiple = reconcile.discover(
        actor, discovery(memory, actor, key="multi", order=None, quantity=2)
    )
    detail = queue.detail(actor, multiple.id)
    with pytest.raises(MemoryError, match="each unit"):
        queue.review(
            actor,
            IdentityReview(
                observation_id=multiple.id,
                expected_decision_id=multiple.decision_id,
                action="link",
                asset_ids=existing.asset_ids,
                candidate_ids=[c["id"] for c in detail["candidates"]],
            ),
        )
    result = queue.review(
        actor,
        IdentityReview(
            observation_id=multiple.id,
            expected_decision_id=multiple.decision_id,
            action="new",
            candidate_ids=[c["id"] for c in detail["candidates"]],
        ),
    )
    assert len(set(result["asset_ids"])) == 2
    assert not set(result["asset_ids"]) & set(existing.asset_ids)
    auth.engine.dispose()


def test_queue_http_mcp_and_shared_chat_state() -> None:
    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        memory = MemoryService(app.state.auth_store.engine)
        reconcile = ReconciliationService(memory.engine)
        reconcile.discover(actor, discovery(memory, actor))
        pending = reconcile.discover(
            actor, discovery(memory, actor, key="uncertain", order=None)
        )
        assert client.get("/api/reviews").status_code == 401
        assert client.get("/api/reviews", headers=bob).json()["items"] == []
        path = f"/api/reviews/identities/{pending.id}"
        assert client.get(path, headers=bob).status_code == 400
        detail = client.get(path, headers=alice).json()
        assert detail["observation"]["quote"]
        result = rpc(client, alice, "review_queue", {}).json()["result"]
        assert not result.get("isError"), result
        body = {
            "observation_id": pending.id,
            "expected_decision_id": pending.decision_id,
            "action": "dismiss",
        }
        assert (
            client.post(
                "/api/reviews/identities/review",
                headers={"Cookie": alice["Cookie"]},
                json=body,
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/reviews/identities/review", headers=bob, json=body
            ).status_code
            == 400
        )
        assert (
            not rpc(client, alice, "review_identity_resolve", body)
            .json()["result"]
            .get("isError")
        )
        assert client.get("/api/reviews", headers=alice).json()["items"] == []
        assert reconcile.get(actor, pending.id).outcome == "dismissed"
        source = save_text(
            memory, actor, SaveText(text="I own a drill", request_id="drill")
        )
        proposal = ProposalService(memory.engine).create(
            actor,
            source.id,
            AssetExtraction(
                candidate=fields(
                    name="drill",
                    manufacturer=None,
                    model=None,
                    kind="possession",
                    quote="I own a drill",
                ),
                explanation="Review first",
            ),
        )
        assert (
            client.get("/api/reviews", headers=alice).json()["items"][0]["id"]
            == proposal["id"]
        )
        client.post(
            "/api/chat/asset-proposals/review",
            headers=alice,
            json={
                "proposal_id": proposal["id"],
                "request_id": "reject",
                "action": "reject",
            },
        )
        assert client.get("/api/reviews", headers=alice).json()["items"] == []


def test_mention_cannot_be_resolved_into_owned_inventory(tmp_path: Path) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    payload = discovery(memory, actor, order=None, kind="mention")
    result = reconcile.discover(actor, payload)
    # An explicit undo creates a review even when an automatic mention was dismissed.
    pending = reconcile.undo(actor, result.decision_id)
    assert pending.outcome == "review"
    queue = ReviewService(auth.engine)
    with pytest.raises(MemoryError, match="possession source"):
        queue.review(
            actor,
            IdentityReview(
                observation_id=pending.id,
                expected_decision_id=pending.decision_id,
                action="new",
            ),
        )
    assert reconcile.inventory(actor) == []
    auth.engine.dispose()
