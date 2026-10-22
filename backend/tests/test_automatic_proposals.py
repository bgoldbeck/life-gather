from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from stored_files import files
from test_asset_actions import change
from test_asset_proposals import TEXT, fields, review, setup
from test_mcp_http import rpc, signed_headers

from lifegather.assets.actions import ActionService
from lifegather.auth.store import AuthStore
from lifegather.chat.service import SaveText, save_text
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.models import Observation
from lifegather.reconciliation.proposals import (
    AssetExtraction,
    ProposalService,
)
from lifegather.reconciliation.service import ReconciliationService


def draft(
    service: ProposalService,
    memory: MemoryService,
    actor: Any,
    key: str,
    **changes: Any,
) -> dict[str, Any]:
    value = fields(**changes)
    source = save_text(memory, actor, SaveText(text=value.quote, request_id=key))
    return service.create(
        actor,
        source.id,
        AssetExtraction(candidate=value, explanation="Synthetic item draft"),
    )


def test_clear_new_discovery_is_atomic_private_and_replay_safe(tmp_path: Path) -> None:
    auth, actor, bob, memory, original, service, proposal = setup(tmp_path)
    data = review(proposal["id"], action="auto")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.review(actor, data), range(4)))
    assert all(r == results[0] for r in results)
    assert results[0]["result"]["automatic_outcome"] == "create"
    assert len(ReconciliationService(auth.engine).inventory(actor)) == 1
    with pytest.raises(MemoryError):
        service.review(bob, data)
    snapshot = tmp_path / "snapshot.sqlite3"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(snapshot)
    restored.migrate()
    assert ProposalService(restored.engine).get(actor, proposal["id"]) == results[0]
    restored.engine.dispose()
    auth.engine.dispose()


def test_similarity_stays_pending_with_no_derived_write_or_lost_fields(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _, service, first = setup(tmp_path)
    accepted = service.review(actor, review(first["id"], action="auto"))
    second = draft(service, memory, actor, "second")
    response = service.review(
        actor,
        review(
            second["id"],
            "second-review",
            action="auto",
            fields=fields(name="Husqvarna 525L").model_dump(),
        ),
    )
    assert response["state"] == "proposed" and response["automatic_outcome"] == "review"
    assert (
        response["automatic_check"]["candidates"][0]["id"]
        == accepted["result"]["asset_ids"][0]
    )
    with Session(auth.engine) as db:
        assert len(list(db.scalars(select(Observation)))) == 1
    assert service.get(actor, second["id"])["state"] == "proposed"
    assert (
        service.review(actor, review(second["id"], "second-review", action="auto"))[
            "automatic_outcome"
        ]
        == "review"
    )
    auth.engine.dispose()


def test_reliable_active_serial_enriches_but_sold_or_dismissed_identity_waits(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _, service, _ = setup(tmp_path)
    text = TEXT + " Serial S1"
    first = draft(service, memory, actor, "serial-first", serial="S1", quote=text)
    accepted = service.review(
        actor,
        review(
            first["id"],
            "first",
            action="auto",
            fields=fields(serial="S1", quote=text).model_dump(),
        ),
    )
    second = draft(service, memory, actor, "serial-second", serial="S1", quote=text)
    enriched = service.review(
        actor,
        review(
            second["id"],
            "second",
            action="auto",
            fields=fields(serial="S1", quote=text).model_dump(),
        ),
    )
    assert enriched["result"]["automatic_outcome"] == "enrich"
    assert enriched["result"]["asset_ids"] == accepted["result"]["asset_ids"]
    assert len(ReconciliationService(auth.engine).inventory(actor)) == 1
    ActionService(auth.engine).apply(actor, change(accepted["result"]["asset_ids"][0]))
    third = draft(service, memory, actor, "serial-third", serial="S1", quote=text)
    pending = service.review(
        actor,
        review(
            third["id"],
            "third",
            action="auto",
            fields=fields(serial="S1", quote=text).model_dump(),
        ),
    )
    assert pending["automatic_outcome"] == "review" and pending["state"] == "proposed"
    auth.engine.dispose()


def test_automatic_action_rejects_mentions_invented_details_and_stale_sources(
    tmp_path: Path,
) -> None:
    auth, actor, _, _, original, service, proposal = setup(tmp_path)
    for value in (
        fields(kind="mention"),
        fields(serial="invented"),
        fields(quote="invented"),
    ):
        with pytest.raises(MemoryError):
            service.review(
                actor, review(proposal["id"], action="auto", fields=value.model_dump())
            )
    NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=original.id, text="Corrected note", request_id="correct"
        ),
    )
    with pytest.raises(MemoryError):
        service.review(actor, review(proposal["id"], action="auto"))
    assert not ReconciliationService(auth.engine).inventory(actor)
    auth.engine.dispose()


def test_deleted_pdf_blocks_manual_and_automatic_proposals(tmp_path: Path) -> None:
    from test_documents import synthetic_pdf

    from lifegather.documents.service import (
        DocumentDelete,
        DocumentService,
        DocumentText,
    )

    auth, actor, _, _, _, service, _ = setup(tmp_path)
    documents = DocumentService(auth.engine, files(auth.engine))
    doc = documents.upload(actor, synthetic_pdf(), "synthetic.pdf")
    doc = documents.save_text(
        actor,
        DocumentText(
            document_id=doc["id"], text=TEXT, expected_updated_at=doc["updated_at"]
        ),
    )
    proposal = service.create(
        actor,
        doc["source_id"],
        AssetExtraction(candidate=fields(), explanation="Synthetic PDF draft"),
    )
    documents.delete(
        actor,
        DocumentDelete(document_id=doc["id"], expected_updated_at=doc["updated_at"]),
    )
    for action in ("auto", "new"):
        with pytest.raises(MemoryError, match="document was deleted"):
            service.review(actor, review(proposal["id"], action=action))
    assert (
        service.review(actor, review(proposal["id"], action="reject", fields=None))[
            "state"
        ]
        == "rejected"
    )
    auth.engine.dispose()


def test_automatic_review_uses_existing_private_http_and_mcp_contracts() -> None:
    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        memory = MemoryService(app.state.auth_store.engine)
        service = ProposalService(app.state.auth_store.engine)
        proposal = draft(service, memory, actor, "source")
        body = review(proposal["id"], action="auto").model_dump()
        assert (
            client.post(
                "/api/chat/asset-proposals/review",
                headers={"Cookie": alice["Cookie"]},
                json=body,
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/chat/asset-proposals/review", headers=bob, json=body
            ).status_code
            == 400
        )
        response = client.post(
            "/api/chat/asset-proposals/review", headers=alice, json=body
        )
        assert response.status_code == 200, response.text
        assert response.json()["result"]["automatic_outcome"] == "create"
        assert (
            not rpc(client, alice, "asset_proposal_review", body)
            .json()["result"]
            .get("isError")
        )


def test_automatic_discovery_does_not_ignore_conflicting_serial_history(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _, service, _ = setup(tmp_path)
    text = TEXT + " Serial S1"
    first = draft(service, memory, actor, "serial-one", serial="S1", quote=text)
    accepted = service.review(
        actor,
        review(
            first["id"],
            "one",
            action="auto",
            fields=fields(serial="S1", quote=text).model_dump(),
        ),
    )
    result = accepted["result"]
    ReconciliationService(auth.engine).resolve(
        actor, result["id"], result["decision_id"], asset_ids=None
    )
    later = draft(service, memory, actor, "serial-later", serial="S1", quote=text)
    pending = service.review(
        actor,
        review(
            later["id"],
            "later",
            action="auto",
            fields=fields(serial="S1", quote=text).model_dump(),
        ),
    )
    assert pending["automatic_outcome"] == "review" and pending["state"] == "proposed"
    auth.engine.dispose()
