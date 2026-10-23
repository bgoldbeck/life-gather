from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Any, Literal

import pytest
from database_support import restore_copy
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import event
from stored_files import files
from test_mcp_http import rpc, signed_headers
from test_photos import image_bytes
from test_reconciliation import discovery, setup
from test_unit_corrections import prepared

from lifegather.assets import comparison
from lifegather.assets.comparison import RecordComparison, RecordComparisonService
from lifegather.auth.store import AuthStore
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.photos.service import PhotoAttach, PhotoDelete, PhotoService
from lifegather.purchases.schemas import EvidenceSave
from lifegather.purchases.service import PurchaseEvidenceService

pytestmark = pytest.mark.usefixtures("configured_database")


def pair(tmp_path: Path) -> tuple[Any, ...]:
    auth, actor, bob, memory, _ = setup(tmp_path)
    source = memory.ingest(actor, SourceInput(text="Synthetic drill and backup drill."))
    records = [
        memory.create_entity(
            actor,
            EntityInput(
                name=name, kind="asset", source_id=source.id, operation_key=name
            ),
        )
        for name in ("Drill", "Backup drill")
    ]
    data = RecordComparison(asset_id=records[0].id, target_asset_id=records[1].id)
    return auth, actor, bob, memory, source, records, data


def test_complete_comparison_retains_evidence_aliases_photos_units_and_money(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _, receipt, line, target, _ = prepared(tmp_path)
    old = line["asset_ids"][0]
    source = memory.ingest(
        actor,
        SourceInput(text="My synthetic red drill aka workshop drill, and blue backup."),
    )
    memory.add_alias(actor, old, "workshop drill", source.id)
    for identifier, value in [(old, "red"), (target.id, "blue")]:
        memory.assert_fact(
            actor,
            FactInput(
                subject_id=identifier,
                predicate="color",
                value=value,
                source_id=source.id,
                quote=source.text,
                operation_key=identifier,
            ),
        )
    place = memory.create_entity(
        actor,
        EntityInput(
            name="Workshop", kind="place", source_id=source.id, operation_key="place"
        ),
    )
    incoming = memory.assert_fact(
        actor,
        FactInput(
            subject_id=place.id,
            predicate="contains",
            object_id=old,
            source_id=source.id,
            operation_key="incoming",
        ),
    )
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "synthetic.jpg", "photo", old)
    attached = photos.link(
        actor,
        PhotoAttach(
            photo_id=photo["id"],
            asset_id=target.id,
            expected_updated_at=photo["updated_at"],
        ),
    )
    photos.delete(
        actor,
        PhotoDelete(photo_id=photo["id"], expected_updated_at=attached["updated_at"]),
    )
    before = {
        table: memory.export_page(actor, table)
        for table in ("facts", "sources", "entities")
    }
    queries: list[str] = []

    def query(
        _conn: Any,
        _cursor: Any,
        statement: str,
        _params: Any,
        _context: Any,
        _many: Any,
    ) -> None:
        queries.append(statement)

    event.listen(auth.engine, "before_cursor_execute", query)
    result = RecordComparisonService(auth.engine).get(
        actor, RecordComparison(asset_id=old, target_asset_id=target.id)
    )
    event.remove(auth.engine, "before_cursor_execute", query)
    assert result["complete"] and result["counts"]["receipt_lines"] == 1
    assert result["sections"]["aliases"][0]["name"] == "workshop drill"
    assert any(row["id"] == incoming.id for row in result["sections"]["statements"])
    assert result["references"][0]["id"] == place.id
    assert len(result["sections"]["photos"]) == 2
    assert all(row["deleted"] for row in result["sections"]["photos"])
    claim = result["sections"]["receipt_lines"][0]
    assert claim["quantity"] == 2 and claim["unit"] == 1
    assert (
        claim["claim"]["line_total"] == "49.90" and claim["claim"]["currency"] == "USD"
    )
    assert any(row.get("predicate") == "color" for row in result["warnings"])
    assert not any(
        sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        for sql in queries
    )
    assert "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ" in queries
    assert before == {
        table: memory.export_page(actor, table)
        for table in ("facts", "sources", "entities")
    }
    assert memory.get_source(actor, receipt["source_id"]).id == receipt["source_id"]


def test_distinct_receipt_units_are_flagged_without_merging(tmp_path: Path) -> None:
    auth, actor, _, _, _, _, line, _, _ = prepared(tmp_path)
    result = RecordComparisonService(auth.engine).get(
        actor,
        RecordComparison(
            asset_id=line["asset_ids"][0], target_asset_id=line["asset_ids"][1]
        ),
    )
    assert result["complete"]
    assert any(row["code"] == "distinct_units" for row in result["warnings"])
    assert sorted(row["unit"] for row in result["sections"]["associations"]) == [1, 2]
    assert [
        row["claim"]["total_minor"] for row in result["sections"]["receipt_lines"]
    ] == [4990, 4990]


def test_same_foreign_missing_and_non_asset_records_are_refused(tmp_path: Path) -> None:
    auth, actor, bob, memory, source, records, data = pair(tmp_path)
    service = RecordComparisonService(auth.engine)
    with pytest.raises(ValidationError):
        service.get(actor, data.model_copy(update={"target_asset_id": records[0].id}))
    for owner, request in [
        (bob, data),
        (actor, data.model_copy(update={"target_asset_id": "missing"})),
    ]:
        with pytest.raises(MemoryError):
            service.get(owner, request)
    place = memory.create_entity(
        actor,
        EntityInput(
            name="Place", kind="place", source_id=source.id, operation_key="place"
        ),
    )
    with pytest.raises(MemoryError):
        service.get(actor, data.model_copy(update={"target_asset_id": place.id}))


def test_nonoverlapping_dates_are_not_reported_as_conflicting(tmp_path: Path) -> None:
    auth, actor, _, memory, source, records, data = pair(tmp_path)
    for index, (value, start, end) in enumerate(
        [("red", None, date(2025, 1, 1)), ("blue", date(2025, 1, 1), None)]
    ):
        memory.assert_fact(
            actor,
            FactInput(
                subject_id=records[index].id,
                predicate="color",
                value=value,
                valid_from=start,
                valid_to=end,
                source_id=source.id,
                operation_key=str(index),
            ),
        )
    result = RecordComparisonService(auth.engine).get(actor, data)
    assert result["complete"] and not result["warnings"]


def test_collection_overflow_refuses_partial_result_and_preserves_counts(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, source, records, data = pair(tmp_path)
    for index in range(51):
        memory.assert_fact(
            actor,
            FactInput(
                subject_id=records[0].id,
                predicate="color",
                value=str(index),
                source_id=source.id,
                operation_key=str(index),
            ),
        )
    result = RecordComparisonService(auth.engine).get(actor, data)
    assert not result["complete"] and result["sections"] == {}
    assert result["limited_sections"] == ["statements"]
    assert result["counts"]["statements"] == 51


def test_response_bytes_refuse_whole_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth, actor, _, memory, source, records, data = pair(tmp_path)
    memory.assert_fact(
        actor,
        FactInput(
            subject_id=records[0].id,
            predicate="description",
            value="界" * 2000,
            source_id=source.id,
            operation_key="long",
        ),
    )
    monkeypatch.setattr(comparison, "MAX_BYTES", 2000)
    result = RecordComparisonService(auth.engine).get(actor, data)
    assert not result["complete"] and result["limited_sections"] == ["response_bytes"]
    assert result["sections"] == {} and "references" not in result


def test_http_mcp_read_only_parity_and_private_body_limits() -> None:
    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "comparison-owner")
        foreign, _ = signed_headers(app, "comparison-foreign")
        memory = MemoryService(app.state.auth_store.engine)
        source = memory.ingest(actor, SourceInput(text="Synthetic pair."))
        records = [
            memory.create_entity(
                actor,
                EntityInput(
                    name=str(index),
                    kind="asset",
                    source_id=source.id,
                    operation_key=str(index),
                ),
            )
            for index in range(2)
        ]
        data = {"asset_id": records[0].id, "target_asset_id": records[1].id}
        path = "/api/assets/comparison"
        assert client.post(path, json=data).status_code == 401
        assert client.post(path, headers=foreign, json=data).status_code == 400
        result = client.post(path, headers=headers, json=data)
        assert result.status_code == 200 and result.json()["complete"]
        assert (
            rpc(client, headers, "asset_record_comparison", data).json()["result"][
                "structuredContent"
            ]
            == result.json()
        )
        assert rpc(client, foreign, "asset_record_comparison", data).json()["result"][
            "isError"
        ]
        assert (
            client.post(
                path, headers=headers, json={**data, "max_bytes": 1000000}
            ).status_code
            == 422
        )
        assert (
            client.post(path, headers=headers, content=b" " * 33000).status_code == 413
        )


def test_read_snapshot_survives_an_alias_written_between_sections(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, source, records, data = pair(tmp_path)
    inserted = False
    with ThreadPoolExecutor(max_workers=1) as pool:

        def insert(
            _conn: Any,
            _cursor: Any,
            statement: str,
            _params: Any,
            _context: Any,
            _many: Any,
        ) -> None:
            nonlocal inserted
            if "FROM memory_aliases" in statement and not inserted:
                inserted = True
                pool.submit(
                    memory.add_alias, actor, records[0].id, "synthetic drill", source.id
                ).result(timeout=5)

        event.listen(auth.engine, "before_cursor_execute", insert)
        try:
            first = RecordComparisonService(auth.engine).get(actor, data)
        finally:
            event.remove(auth.engine, "before_cursor_execute", insert)
    assert inserted and first["sections"]["aliases"] == []
    second = RecordComparisonService(auth.engine).get(actor, data)
    assert second["sections"]["aliases"][0]["name"] == "synthetic drill"


def test_scoped_purchase_evidence_is_unique_and_corrected_sources_are_historical(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    created = reconcile.discover(actor, discovery(memory, actor, quantity=2))
    source = memory.ingest(
        actor,
        SourceInput(
            text="Home Depot order A100. JPY 4990",
            source_type="email",
            namespace="gmail-memory:test",
            external_id="order",
        ),
    )
    evidence = PurchaseEvidenceService(auth.engine).save(
        actor,
        EvidenceSave(
            source_id=source.id,
            role="order",
            retailer="Home Depot",
            account_scope="mine",
            order_id="A100",
            quote=source.text,
            reason="Synthetic original",
            request_id="purchase",
        ),
    )
    data = RecordComparison(
        asset_id=created.asset_ids[0], target_asset_id=created.asset_ids[1]
    )
    service = RecordComparisonService(auth.engine)
    result = service.get(actor, data)
    assert len(result["sections"]["purchase_evidence"]) == 1
    assert result["sections"]["purchase_evidence"][0]["id"] == evidence["id"]
    NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=source.id,
            text="This synthetic order was corrected.",
            request_id="comparison-note",
        ),
    )
    changed = service.get(actor, data)
    assert not changed["source_states"][source.id]["is_current"]
    assert not changed["sections"]["purchase_evidence"][0]["source_current"]


@pytest.mark.parametrize(
    "section",
    ["evidence", "aliases", "photos", "associations", "receipt_lines", "sources"],
)
def test_each_collection_bound_refuses_all_partial_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, section: str
) -> None:
    auth, actor, _, memory, _, _, line, _, _ = prepared(tmp_path)
    source = memory.ingest(
        actor, SourceInput(text="Synthetic alias one and alias two.")
    )
    for identifier, name in zip(
        line["asset_ids"], ("alias one", "alias two"), strict=True
    ):
        memory.add_alias(actor, identifier, name, source.id)
    photos = PhotoService(auth.engine, files(auth.engine))
    photo = photos.upload(
        actor, image_bytes(), "synthetic.jpg", "photo", line["asset_ids"][0]
    )
    photos.link(
        actor,
        PhotoAttach(
            photo_id=photo["id"],
            asset_id=line["asset_ids"][1],
            expected_updated_at=photo["updated_at"],
        ),
    )
    monkeypatch.setattr(comparison, "LIMITS", {**comparison.LIMITS, section: 1})
    result = RecordComparisonService(auth.engine).get(
        actor,
        RecordComparison(
            asset_id=line["asset_ids"][0], target_asset_id=line["asset_ids"][1]
        ),
    )
    assert not result["complete"] and result["sections"] == {}
    assert section in result["limited_sections"]
    assert result["counts"][section] >= 2


def test_large_literal_integer_has_an_exact_browser_display(tmp_path: Path) -> None:
    auth, actor, _, memory, source, records, data = pair(tmp_path)
    memory.assert_fact(
        actor,
        FactInput(
            subject_id=records[0].id,
            predicate="identifier",
            value=9007199254740993,
            source_id=source.id,
            operation_key="large-integer",
        ),
    )
    result = RecordComparisonService(auth.engine).get(actor, data)
    assert result["sections"]["statements"][0]["display_value"] == "9007199254740993"


def test_replacement_warning_and_snapshot_preserve_original_records(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, source, records, data = pair(tmp_path)
    memory.assert_fact(
        actor,
        FactInput(
            subject_id=records[0].id,
            predicate="replaced_by",
            object_id=records[1].id,
            source_id=source.id,
            operation_key="replacement",
        ),
    )
    result = RecordComparisonService(auth.engine).get(actor, data)
    assert result["complete"] and result["warnings"][0]["code"] == "replacement"
    snapshot = tmp_path / "comparison.jsonl"
    operator_snapshot(auth.engine, snapshot)
    restored = AuthStore(restore_copy(snapshot))
    restored.migrate()
    assert RecordComparisonService(restored.engine).get(actor, data) == result


def test_purchase_totals_remain_separate_and_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth, actor, _, memory, reconcile = setup(tmp_path)
    created = reconcile.discover(actor, discovery(memory, actor, quantity=2))
    service = PurchaseEvidenceService(auth.engine)
    for index, total in enumerate(("4990", "5000")):
        source = memory.ingest(
            actor,
            SourceInput(
                text=f"Home Depot order A100. JPY {total}", external_id=str(index)
            ),
        )
        service.save(
            actor,
            EvidenceSave(
                source_id=source.id,
                role="receipt",
                retailer="Home Depot",
                account_scope="mine",
                order_id="A100",
                amount=total,
                currency="JPY",
                money_quote=f"JPY {total}",
                quote=source.text,
                reason="Exact synthetic total",
                request_id=str(index),
            ),
        )
    data = RecordComparison(
        asset_id=created.asset_ids[0], target_asset_id=created.asset_ids[1]
    )
    result = RecordComparisonService(auth.engine).get(actor, data)
    assert len(result["sections"]["purchase_evidence"]) == 2
    assert sorted(
        row["amount_minor"] for row in result["sections"]["purchase_evidence"]
    ) == [4990, 5000]
    assert any(row["code"] == "purchase_totals_differ" for row in result["warnings"])
    monkeypatch.setattr(
        comparison, "LIMITS", {**comparison.LIMITS, "purchase_evidence": 1}
    )
    refused = RecordComparisonService(auth.engine).get(actor, data)
    assert not refused["complete"] and refused["sections"] == {}
    assert "purchase_evidence" in refused["limited_sections"]


@pytest.mark.parametrize("status", ["stated", "unknown"])
def test_unknown_literals_do_not_contradict_known_statements(
    tmp_path: Path, status: Literal["stated", "unknown"]
) -> None:
    auth, actor, _, memory, source, records, data = pair(tmp_path)
    memory.assert_fact(
        actor,
        FactInput(
            subject_id=records[0].id,
            predicate="color",
            value=None,
            status=status,
            source_id=source.id,
            operation_key="unknown",
        ),
    )
    memory.assert_fact(
        actor,
        FactInput(
            subject_id=records[1].id,
            predicate="color",
            value="blue",
            source_id=source.id,
            operation_key="known",
        ),
    )
    result = RecordComparisonService(auth.engine).get(actor, data)
    assert result["complete"] and not result["warnings"]
