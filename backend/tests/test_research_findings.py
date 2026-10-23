"""Saving cited web research sources to an asset as dated evidence."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from stored_files import files as stored
from test_account_isolation import sign_in, use_installation
from test_personal_restore import repack, target, unpack
from test_recovery_bundle import Installation, installation

from lifegather.assets.consolidation import ConsolidationService, ReverseConsolidation
from lifegather.assets.identity import canonical_id
from lifegather.auth.store import Account
from lifegather.chat.models import Turn
from lifegather.chat.research import IDENTITY_NOTE
from lifegather.chat.service import ChatService, TurnInput
from lifegather.database import account_scope
from lifegather.findings.models import ResearchFinding, ResearchSaveReceipt
from lifegather.findings.service import FindingRemove, FindingSave, FindingService
from lifegather.main import create_app
from lifegather.memory.archive import PersonalArchive
from lifegather.memory.models import Audit
from lifegather.memory.restore import PersonalRestore, RestoreError
from lifegather.memory.schemas import EntityInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService

pytestmark = pytest.mark.usefixtures("configured_database")

MANUAL = "https://manufacturer.example/mower-manual"
PARTS = "https://parts.example/filters"


def research_result() -> dict[str, Any]:
    return {
        "provider": "anthropic",
        "model": "synthetic-model",
        "text": "The synthetic manual lists filter AB-12.",
        "sources": [],
        "research": {
            "researched_at": "2026-10-22T09:00:00Z",
            "queries": ["synthetic mower manual"],
            "searches": 1,
            "shared_record": None,
            "sources": [
                {
                    "url": MANUAL,
                    "title": "Synthetic mower manual",
                    "published": "2025-04-01",
                    "excerpt_kind": "source",
                    "excerpts": ["Replace filter AB-12 every season."],
                },
                {
                    "url": PARTS,
                    "title": "Filters",
                    "published": None,
                    "excerpt_kind": "answer",
                    "excerpts": [],
                },
            ],
            "identity_note": IDENTITY_NOTE,
        },
    }


def research_turn(
    engine: Engine,
    actor: Account,
    request_id: str = "research",
    result: dict[str, Any] | None = None,
    mode: str = "research",
) -> str:
    chat = ChatService(engine)
    conversation = chat.create(actor)["id"]
    row, _ = chat.begin(
        actor,
        conversation,
        TurnInput.model_validate(
            {
                "request_id": request_id,
                "mode": mode,
                "text": "Owner's manual for the synthetic mower",
                **(
                    {
                        "research": {"share_record": False},
                        "credential_id": "synthetic",
                        "model": "synthetic-model",
                    }
                    if mode == "research"
                    else {}
                ),
            }
        ),
    )
    chat.finish(actor, row["id"], result or research_result())
    return str(row["id"])


def save(
    service: FindingService,
    actor: Account,
    turn: str,
    asset: str,
    url: str = MANUAL,
    request_id: str = "save-1",
) -> dict[str, Any]:
    return service.save(
        actor,
        FindingSave(request_id=request_id, turn_id=turn, url=url, asset_id=asset),
    )


@pytest.fixture
def case(tmp_path: Path) -> Installation:
    return installation(tmp_path)


def test_save_copies_the_cited_source_and_lists_it_on_the_asset(
    case: Installation,
) -> None:
    engine = case.store.engine
    turn = research_turn(engine, case.alice)
    service = FindingService(MemoryService(engine))
    saved = save(service, case.alice, turn, case.primary)
    assert saved["already_saved"] is False
    assert saved["url"] == MANUAL and saved["title"] == "Synthetic mower manual"
    assert saved["published"] == "2025-04-01"
    assert saved["excerpts"] == ["Replace filter AB-12 every season."]
    assert saved["researched_at"] == "2026-10-22T09:00:00Z"
    assert saved["question"] == "Owner's manual for the synthetic mower"
    assert saved["provider"] == "anthropic" and saved["identity_note"]
    listed = service.for_asset(case.alice, case.primary)["items"]
    assert [item["id"] for item in listed] == [saved["id"]]
    with Session(engine) as db:
        assert db.scalar(
            select(Audit.operation).where(Audit.target_id == saved["id"])
        ) == ("research_finding_saved")


def test_replay_and_duplicate_saves_keep_one_finding(case: Installation) -> None:
    engine = case.store.engine
    turn = research_turn(engine, case.alice)
    service = FindingService(MemoryService(engine))
    first = save(service, case.alice, turn, case.primary)
    replay = save(service, case.alice, turn, case.primary)
    assert replay["id"] == first["id"] and replay["already_saved"]
    duplicate = save(service, case.alice, turn, case.primary, request_id="save-2")
    assert duplicate["id"] == first["id"] and duplicate["already_saved"]
    with pytest.raises(MemoryError, match="already used"):
        save(service, case.alice, turn, case.primary, url=PARTS)
    other = save(service, case.alice, turn, case.primary, PARTS, "save-3")
    assert other["published"] is None and other["excerpt_kind"] == "answer"
    assert len(service.for_asset(case.alice, case.primary)["items"]) == 2


def test_only_cited_sources_of_finished_research_replies_save(
    case: Installation,
) -> None:
    engine = case.store.engine
    service = FindingService(MemoryService(engine))
    turn = research_turn(engine, case.alice)
    with pytest.raises(MemoryError, match="not cited"):
        save(service, case.alice, turn, case.primary, url="https://other.example/")
    search = research_turn(engine, case.alice, "search", mode="search")
    with pytest.raises(MemoryError, match="finished web research"):
        save(service, case.alice, search, case.primary)
    with Session(engine) as db, db.begin():
        db.execute(update(Turn).where(Turn.id == turn).values(state="pending"))
    with pytest.raises(MemoryError, match="finished web research"):
        save(service, case.alice, turn, case.primary)
    with Session(engine) as db, db.begin():
        db.execute(update(Turn).where(Turn.id == turn).values(state="complete"))
    unsafe = research_result()
    unsafe["research"]["sources"][0]["url"] = "javascript:alert(1)"
    bad = research_turn(engine, case.alice, "unsafe", unsafe)
    with pytest.raises(MemoryError, match="not cited"):
        save(service, case.alice, bad, case.primary, url="javascript:alert(1)")
    with pytest.raises(MemoryError, match="Message not found"):
        save(service, case.alice, "missing", case.primary)
    memory = MemoryService(engine)
    source = memory.ingest(case.alice, SourceInput(text="Synthetic neighbor"))
    person = memory.create_entity(
        case.alice,
        EntityInput(
            name="Synthetic neighbor",
            kind="person",
            source_id=source.id,
            operation_key="neighbor",
        ),
    )
    good = research_turn(engine, case.alice, "good")
    with pytest.raises(MemoryError, match="physical asset"):
        save(service, case.alice, good, person.id)
    with Session(engine) as db:
        assert db.scalar(select(ResearchFinding.id)) is None


def test_save_request_cannot_change_its_target(case: Installation) -> None:
    memory = MemoryService(case.store.engine)
    source = memory.ingest(case.alice, SourceInput(text="A separate synthetic item"))
    other = memory.create_entity(
        case.alice,
        EntityInput(
            name="Separate item",
            kind="asset",
            source_id=source.id,
            operation_key="separate-item",
        ),
    )
    turn = research_turn(case.store.engine, case.alice)
    service = FindingService(memory)
    save(service, case.alice, turn, case.primary)
    with pytest.raises(MemoryError, match="already used"):
        save(service, case.alice, turn, other.id)


def test_duplicate_receipt_does_not_revive_removed_evidence(case: Installation) -> None:
    engine = case.store.engine
    service = FindingService(MemoryService(engine))
    turn = research_turn(engine, case.alice)
    first = save(service, case.alice, turn, case.primary)
    duplicate = save(service, case.alice, turn, case.secondary, request_id="duplicate")
    assert duplicate["id"] == first["id"]
    removed = service.remove(case.alice, FindingRemove(finding_id=first["id"]))
    replay = save(service, case.alice, turn, case.secondary, request_id="duplicate")
    assert replay["id"] == first["id"]
    assert replay["removed_at"] == removed["removed_at"]
    assert service.for_asset(case.alice, case.primary)["items"] == []
    with Session(engine) as db, db.begin():
        db.execute(delete(Turn))
    assert (
        save(service, case.alice, turn, case.secondary, request_id="duplicate")["id"]
        == first["id"]
    )
    with pytest.raises(MemoryError, match="already used"):
        save(service, case.alice, turn, case.primary, request_id="duplicate")


def test_another_account_cannot_save_read_or_remove(case: Installation) -> None:
    engine = case.store.engine
    service = FindingService(MemoryService(engine))
    turn = research_turn(engine, case.alice)
    saved = save(service, case.alice, turn, case.primary)
    with pytest.raises(MemoryError, match="Message not found"):
        save(service, case.bob, turn, case.primary, request_id="bob")
    with pytest.raises(MemoryError, match="Entity not found"):
        service.for_asset(case.bob, case.primary)
    with pytest.raises(MemoryError, match="Finding not found"):
        service.remove(case.bob, FindingRemove(finding_id=saved["id"]))
    assert len(service.for_asset(case.alice, case.primary)["items"]) == 1


def test_receipts_are_atomic_and_enforce_account_boundaries(case: Installation) -> None:
    engine = case.store.engine
    service = FindingService(MemoryService(engine))
    turn = research_turn(engine, case.alice)
    with account_scope(case.alice.id):
        saved = save(service, case.alice, turn, case.primary)
    with Session(engine) as db:
        receipt = db.scalar(select(ResearchSaveReceipt))
        assert receipt is not None and receipt.finding_id == saved["id"]
    with account_scope(case.bob.id), engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT count(*) FROM research_save_receipts")) == 0
        )
        with pytest.raises(DBAPIError, match="row-level security"):
            connection.execute(
                insert(ResearchSaveReceipt).values(
                    id="forbidden",
                    user_id=case.alice.id,
                    request_id="foreign",
                    asset_id=case.primary,
                    turn_id=turn,
                    url=MANUAL,
                    finding_id=saved["id"],
                    recorded_at=1,
                )
            )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(ResearchSaveReceipt).values(
                id="foreign-reference",
                user_id=case.bob.id,
                request_id="foreign",
                asset_id=case.primary,
                turn_id=turn,
                url=MANUAL,
                finding_id=saved["id"],
                recorded_at=1,
            )
        )
    # A rejected conflicting payload creates neither a receipt nor new evidence.
    with pytest.raises(MemoryError):
        save(service, case.alice, turn, case.primary, url=PARTS)
    with Session(engine) as db:
        assert len(list(db.scalars(select(ResearchSaveReceipt)))) == 1
        assert len(list(db.scalars(select(ResearchFinding)))) == 1


def test_exact_receipt_survives_identity_reversal(case: Installation) -> None:
    engine = case.store.engine
    service = FindingService(MemoryService(engine))
    turn = research_turn(engine, case.alice)
    saved = save(service, case.alice, turn, case.secondary)
    ConsolidationService(engine).reverse(
        case.alice,
        ReverseConsolidation(
            consolidation_id=case.choice, request_id="separate", note="Separate items"
        ),
    )
    replay = save(service, case.alice, turn, case.secondary)
    assert replay["id"] == saved["id"] and replay["already_saved"]
    with pytest.raises(MemoryError, match="already used"):
        save(service, case.alice, turn, case.primary)


def test_concurrent_duplicate_requests_keep_each_receipt(case: Installation) -> None:
    engine = case.store.engine
    service = FindingService(MemoryService(engine))
    turn = research_turn(engine, case.alice)
    requests = ["one", "one", "two", "three"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda request: save(
                    service, case.alice, turn, case.primary, request_id=request
                ),
                requests,
            )
        )
    assert len({row["id"] for row in results}) == 1
    with Session(engine) as db:
        assert {
            row.request_id for row in db.scalars(select(ResearchSaveReceipt))
        } == set(requests)
        assert len(list(db.scalars(select(ResearchFinding)))) == 1


def test_remove_keeps_history_and_allows_saving_again(case: Installation) -> None:
    engine = case.store.engine
    service = FindingService(MemoryService(engine))
    turn = research_turn(engine, case.alice)
    saved = save(service, case.alice, turn, case.primary)
    removed = service.remove(case.alice, FindingRemove(finding_id=saved["id"]))
    assert removed["removed_at"] is not None
    again = service.remove(case.alice, FindingRemove(finding_id=saved["id"]))
    assert again["removed_at"] == removed["removed_at"]
    assert service.for_asset(case.alice, case.primary)["items"] == []
    resaved = save(service, case.alice, turn, case.primary, request_id="save-2")
    assert resaved["id"] != saved["id"] and not resaved["already_saved"]
    with Session(engine) as db:
        assert len(list(db.scalars(select(ResearchFinding)))) == 2


def test_findings_follow_consolidated_identity(case: Installation) -> None:
    engine = case.store.engine
    service = FindingService(MemoryService(engine))
    turn = research_turn(engine, case.alice)
    with Session(engine) as db:
        primary = canonical_id(db, case.alice, case.secondary)
    saved = save(service, case.alice, turn, case.secondary)
    assert saved["asset_id"] == primary
    for asset in (case.primary, case.secondary):
        items = service.for_asset(case.alice, asset)["items"]
        assert [item["id"] for item in items] == [saved["id"]]


def test_findings_survive_conversation_deletion(case: Installation) -> None:
    engine = case.store.engine
    service = FindingService(MemoryService(engine))
    turn = research_turn(engine, case.alice)
    save(service, case.alice, turn, case.primary)
    with Session(engine) as db, db.begin():
        db.execute(delete(Turn))
    assert len(service.for_asset(case.alice, case.primary)["items"]) == 1


def test_personal_archive_round_trip_and_format_4_archives(
    tmp_path: Path, case: Installation
) -> None:
    engine = case.store.engine
    service = FindingService(MemoryService(engine))
    saved = save(service, case.alice, research_turn(engine, case.alice), case.primary)
    raw = PersonalArchive(engine, stored(engine)).download(case.alice)
    manifest, records, _ = unpack(raw)
    assert manifest["records_format"] == "lifegather-records/6"
    receipts = records["collections"]["research_save_receipts"]
    assert len(receipts) == 1 and receipts[0]["finding_id"] == saved["id"]
    assert "user_id" not in receipts[0]
    assert [row["id"] for row in records["collections"]["research_findings"]] == [
        saved["id"]
    ]
    store, actor = target(tmp_path)
    PersonalRestore(store.engine, stored(store.engine)).restore(actor, raw)
    restored = FindingService(MemoryService(store.engine)).for_asset(
        actor, case.primary
    )["items"]
    assert [(item["id"], item["url"]) for item in restored] == [(saved["id"], MANUAL)]
    restored_service = FindingService(MemoryService(store.engine))
    restored_service.remove(actor, FindingRemove(finding_id=saved["id"]))
    replay = save(restored_service, actor, saved["turn_id"], case.primary)
    assert replay["id"] == saved["id"] and replay["removed_at"] is not None

    # An archive written before findings existed still restores, with none.
    older = dict(records, format="lifegather-records/4")
    older["collections"] = {
        k: v
        for k, v in records["collections"].items()
        if k not in {"research_findings", "research_save_receipts"}
    }
    older["counts"] = {
        k: v
        for k, v in records["counts"].items()
        if k not in {"research_findings", "research_save_receipts"}
    }
    older["total_records"] = records["total_records"] - 2
    old_raw = repack(raw, older, dict(manifest, records_format="lifegather-records/4"))
    store, actor = target(tmp_path / "old")
    PersonalRestore(store.engine, stored(store.engine)).restore(actor, old_raw)
    assert (
        FindingService(MemoryService(store.engine)).for_asset(actor, case.primary)[
            "items"
        ]
        == []
    )

    # A format 4 archive that carries findings, or a mismatched manifest, fails.
    with_findings = dict(older, collections=records["collections"])
    store, actor = target(tmp_path / "bad")
    restore = PersonalRestore(store.engine, stored(store.engine))
    for bad in (
        repack(
            raw, with_findings, dict(manifest, records_format="lifegather-records/4")
        ),
        repack(raw, older, manifest),
    ):
        with pytest.raises(RestoreError):
            restore.restore(actor, bad)


def test_format_5_receiptless_findings_replay_safely(
    tmp_path: Path, case: Installation
) -> None:
    engine = case.store.engine
    saved = save(
        FindingService(MemoryService(engine)),
        case.alice,
        research_turn(engine, case.alice),
        case.secondary,
    )
    raw = PersonalArchive(engine, stored(engine)).download(case.alice)
    manifest, records, _ = unpack(raw)
    old = dict(records, format="lifegather-records/5")
    for key in ("collections", "counts"):
        old[key] = {
            k: v for k, v in records[key].items() if k != "research_save_receipts"
        }
    old["total_records"] -= len(records["collections"]["research_save_receipts"])
    store, actor = target(tmp_path)
    PersonalRestore(store.engine, stored(store.engine)).restore(
        actor, repack(raw, old, dict(manifest, records_format="lifegather-records/5"))
    )
    service = FindingService(MemoryService(store.engine))
    service.remove(actor, FindingRemove(finding_id=saved["id"]))
    replay = save(service, actor, saved["turn_id"], case.secondary)
    assert replay["id"] == saved["id"] and replay["removed_at"] is not None
    with Session(store.engine) as db:
        receipt = db.scalar(select(ResearchSaveReceipt))
        assert receipt is not None and receipt.asset_id == case.secondary


def test_http_save_list_and_remove(
    case: Installation, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_installation(case, monkeypatch)
    turn = research_turn(case.store.engine, case.alice)
    with TestClient(create_app()) as client:
        headers = sign_in(client, "alice")
        body = {
            "request_id": "http-save",
            "turn_id": turn,
            "url": MANUAL,
            "asset_id": case.primary,
        }
        assert client.post("/api/research-findings", json=body).status_code == 403
        created = client.post("/api/research-findings", json=body, headers=headers)
        assert created.status_code == 201
        finding = created.json()
        listed = client.get(f"/api/research-findings/assets/{case.primary}").json()
        assert [item["id"] for item in listed["items"]] == [finding["id"]]
        bad = client.post(
            "/api/research-findings",
            json=body | {"request_id": "other", "url": "https://x.example/"},
            headers=headers,
        )
        assert bad.status_code == 400
        removed = client.post(
            "/api/research-findings/remove",
            json={"finding_id": finding["id"]},
            headers=headers,
        )
        assert removed.status_code == 200 and removed.json()["removed_at"]
        listed = client.get(f"/api/research-findings/assets/{case.primary}").json()
        assert listed["items"] == []
        bob = sign_in(client, "bob")
        refused = client.post(
            "/api/research-findings",
            json=body | {"request_id": "bob"},
            headers=bob,
        )
        assert refused.status_code == 400
        assert "mower" not in json.dumps(refused.json()).lower()


def test_mcp_reads_saved_findings(
    case: Installation, monkeypatch: pytest.MonkeyPatch
) -> None:
    from test_mcp_http import rpc, signed_headers

    use_installation(case, monkeypatch)
    engine = case.store.engine
    save(
        FindingService(MemoryService(engine)),
        case.alice,
        research_turn(engine, case.alice),
        case.primary,
    )
    app = create_app()
    with TestClient(app) as client:
        headers, _ = signed_headers(app, "alice")
        response = rpc(
            client, headers, "asset_research_findings", {"asset_id": case.primary}
        )
        assert response.status_code == 200
        assert MANUAL in response.text and "2025-04-01" in response.text
