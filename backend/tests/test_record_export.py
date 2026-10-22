import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session
from stored_files import files
from test_documents import synthetic_pdf
from test_mcp_http import signed_headers
from test_photos import image_bytes
from test_purchase_details import accepted, body
from test_reconciliation import discovery, setup

from lifegather.chat.service import ChatService, SaveText, TurnInput, save_text
from lifegather.credentials.service import PrivateSettings
from lifegather.documents.service import DocumentService
from lifegather.main import create_app
from lifegather.memory import export
from lifegather.memory.export import COLLECTIONS, ExportLimitError, RecordExport
from lifegather.memory.notes import CorrectionInput, NoteService
from lifegather.memory.origins import change_origin
from lifegather.memory.schemas import EntityInput, FactInput, SourceInput
from lifegather.photos.service import PhotoService
from lifegather.reconciliation.purchase_details import PurchaseDetails


def test_empty_export_has_explicit_scope_and_no_account_identity(
    tmp_path: Path,
) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    raw = RecordExport(auth.engine).download(actor)
    data = json.loads(raw)
    assert data["format"] == "lifegather-records/5"
    assert datetime.fromisoformat(data["snapshot_at"]).tzinfo is not None
    assert data["total_records"] == 0
    assert len(data["collections"]) == 30
    assert all(not rows for rows in data["collections"].values())
    assert data["counts"] == {name: 0 for name in data["collections"]}
    assert "not a restorable backup" in data["purpose"]
    assert data["excluded"] and actor.id.encode() not in raw
    assert b"a@example.test" not in raw


def test_export_preserves_new_change_origins_and_unknown_legacy_values(
    tmp_path: Path,
) -> None:
    from sqlalchemy import update

    from lifegather.memory.models import Audit

    auth, actor, _, memory, _ = setup(tmp_path)
    first = memory.ingest(actor, SourceInput(text="Synthetic legacy evidence"))
    with Session(auth.engine) as db, db.begin():
        db.execute(
            update(Audit)
            .where(Audit.target_id == first.id)
            .values(provenance_json=None)
        )
    with change_origin(
        interface="web", initiator="account_request", method="manual_entry"
    ):
        second = memory.ingest(actor, SourceInput(text="Synthetic attributed evidence"))
    rows = json.loads(RecordExport(auth.engine).download(actor))["collections"][
        "memory_audit"
    ]
    assert (
        next(row for row in rows if row["target_id"] == first.id)["provenance_json"]
        is None
    )
    origin = next(row for row in rows if row["target_id"] == second.id)[
        "provenance_json"
    ]
    assert json.loads(origin) == {
        "interface": "web",
        "initiator": "account_request",
        "method": "manual_entry",
        "provider": None,
        "model": None,
        "related_id": None,
    }


def test_export_preserves_source_fact_correction_and_distinct_unit_history(
    tmp_path: Path,
) -> None:
    auth, actor, foreign, memory, reconcile = setup(tmp_path)
    source = save_text(
        memory,
        actor,
        SaveText(text="Synthetic original 日本語 Synthetic alias", request_id="note"),
    )
    corrected = NoteService(auth.engine).correct(
        actor,
        CorrectionInput(
            source_id=source.id, text="Synthetic corrected 日本語", request_id="correct"
        ),
    )
    item = memory.create_entity(
        actor,
        EntityInput(
            name="Synthetic object",
            kind="asset",
            source_id=source.id,
            operation_key="object",
        ),
    )
    memory.add_alias(actor, item.id, "Synthetic alias", source.id)
    first = memory.assert_fact(
        actor,
        FactInput(
            subject_id=item.id,
            predicate="color",
            value="green",
            source_id=source.id,
            operation_key="green",
            valid_from=date(2020, 1, 1),
        ),
    )
    memory.correct_fact(
        actor,
        first.id,
        FactInput(
            subject_id=item.id,
            predicate="color",
            value=None,
            status="unknown",
            source_id=source.id,
            operation_key="unknown",
        ),
    )
    incoming = discovery(memory, actor, quantity=2)
    reconcile.discover(actor, incoming)
    memory.ingest(foreign, SourceInput(text="FOREIGN PRIVATE CONTENT"))
    PrivateSettings(auth.engine, b"e" * 32).save(
        actor, "ai", "openai", "Secret connection", "DO-NOT-EXPORT-CREDENTIAL"
    )
    data = json.loads(RecordExport(auth.engine).download(actor))
    rows = data["collections"]
    assert {row["text"] for row in rows["memory_sources"]} >= {
        source.text,
        "Synthetic corrected 日本語",
    }
    assert rows["memory_note_revisions"][0]["root_source_id"] == source.id
    assert rows["memory_aliases"][0]["entity_id"] == item.id
    old = next(row for row in rows["memory_facts"] if row["id"] == first.id)
    assert old["valid_from"] == "2020-01-01" and old["superseded_at"] is not None
    current = next(
        row for row in rows["memory_facts"] if row["replaces_id"] == first.id
    )
    assert current["value_json"] == "null" and current["status"] == "unknown"
    assert {row["unit"] for row in rows["reconciliation_bindings"]} == {0, 1}
    assert len({row["asset_id"] for row in rows["reconciliation_bindings"]}) == 2
    assert rows["reconciliation_lines"][0]["quantity"] == 2
    assert data["total_records"] == sum(data["counts"].values())
    encoded = json.dumps(data)
    assert "FOREIGN PRIVATE CONTENT" not in encoded
    assert "DO-NOT-EXPORT-CREDENTIAL" not in encoded
    assert "Secret connection" not in encoded
    assert all(
        "user_id" not in row for collection in rows.values() for row in collection
    )
    assert corrected


def test_export_keeps_chat_and_original_metadata_without_file_bytes(
    tmp_path: Path,
) -> None:
    auth, actor, foreign, memory, _ = setup(tmp_path)
    photo = PhotoService(auth.engine, files(auth.engine)).upload(
        actor, image_bytes(), "synthetic.jpg"
    )
    document = DocumentService(auth.engine, files(auth.engine)).upload(
        actor, synthetic_pdf(), "synthetic.pdf"
    )
    PhotoService(auth.engine, files(auth.engine)).upload(
        foreign, image_bytes(), "FOREIGN.jpg"
    )
    chat = ChatService(auth.engine)
    conversation = chat.create(actor)["id"]
    row, _ = chat.begin(
        actor,
        conversation,
        TurnInput(request_id="chat", mode="search", text="Uncaptured synthetic chat"),
    )
    chat.finish(actor, row["id"], {"text": "Synthetic saved answer", "sources": []})
    data = json.loads(RecordExport(auth.engine).download(actor))["collections"]
    assert data["photos"][0]["id"] == photo["id"]
    assert len(data["photos"]) == 1
    assert data["documents"][0]["id"] == document["id"]
    assert data["documents"][0]["extracted_text"]
    assert not {"original", "preview"} & data["photos"][0].keys()
    assert "original" not in data["documents"][0]
    assert data["chat_turns"][0]["text"] == "Uncaptured synthetic chat"
    assert (
        json.loads(data["chat_turns"][0]["result_json"])["text"]
        == "Synthetic saved answer"
    )
    assert memory.export_page(actor, "sources")["items"] == []


def test_export_uses_one_sqlite_snapshot_during_concurrent_writes(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    memory.ingest(actor, SourceInput(text="Before snapshot"))
    changed = False

    def after_select(
        connection: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        nonlocal changed
        if not changed and statement.startswith("SELECT memory_sources."):
            changed = True

            def write() -> None:
                new = memory.ingest(actor, SourceInput(text="After snapshot"))
                memory.create_entity(
                    actor,
                    EntityInput(
                        name="After snapshot",
                        kind="asset",
                        source_id=new.id,
                        operation_key="after",
                    ),
                )

            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(write).result(timeout=5)

    event.listen(auth.engine, "after_cursor_execute", after_select)
    try:
        first = json.loads(RecordExport(auth.engine).download(actor))
    finally:
        event.remove(auth.engine, "after_cursor_execute", after_select)
    assert changed and first["collections"]["memory_entities"] == []
    assert [row["text"] for row in first["collections"]["memory_sources"]] == [
        "Before snapshot"
    ]
    later = json.loads(RecordExport(auth.engine).download(actor))
    assert later["collections"]["memory_entities"][0]["name"] == "After snapshot"


def test_whole_export_record_limit_refuses_partial_and_releases_transaction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    memory.ingest(actor, SourceInput(text="First"))
    count = json.loads(RecordExport(auth.engine).download(actor))["total_records"]
    monkeypatch.setattr(export, "MAX_RECORDS", count)
    assert (
        json.loads(RecordExport(auth.engine).download(actor))["total_records"] == count
    )
    memory.ingest(actor, SourceInput(text="Second"))
    with pytest.raises(ExportLimitError, match="record"):
        RecordExport(auth.engine).download(actor)
    memory.ingest(actor, SourceInput(text="Write after failure"))
    assert len(memory.export_page(actor, "sources")["items"]) == 3


def test_whole_export_counts_encoded_utf8_bytes_and_refuses_partial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    memory.ingest(actor, SourceInput(text="日本語" * 100))

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "FixedDateTime":
            return cls(2026, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(export, "datetime", FixedDateTime)
    raw = RecordExport(auth.engine).download(actor)
    monkeypatch.setattr(export, "MAX_BYTES", len(raw))
    assert RecordExport(auth.engine).download(actor) == raw
    monkeypatch.setattr(export, "MAX_BYTES", len(raw) - 1)
    with pytest.raises(ExportLimitError, match="MiB"):
        RecordExport(auth.engine).download(actor)
    with Session(auth.engine) as db:
        assert not db.in_transaction()


def test_projection_schema_never_selects_credentials_or_binary_columns() -> None:
    names = {projection.table.name for projection in COLLECTIONS}
    assert not names & {
        "users",
        "credentials",
        "email_credentials",
        "login_sessions",
        "scan_runs",
        "scan_schedules",
        "mailboxes",
        "email_discoveries",
    }
    for projection in COLLECTIONS:
        fields = projection.fields.split()
        assert len(fields) == len(set(fields))
        assert not {
            "user_id",
            "original",
            "preview",
            "password_hash",
            "ciphertext",
            "nonce",
            "csrf_token",
        } & set(fields)
        assert "id" in fields
        assert set(fields) <= set(projection.table.c.keys())


@pytest.mark.parametrize("currency", ["USD", "EUR", "GBP", "CAD", "AUD", "JPY"])
def test_export_preserves_exact_money_and_withdrawn_unknown_history(
    tmp_path: Path,
    currency: str,
) -> None:
    auth, actor, _, _, _ = setup(tmp_path)
    amount = "12345" if currency == "JPY" else "123.45"
    money = f"Acme Drill Qty: 2; Line total: {currency} {amount}"
    receipt = accepted(
        auth.engine, actor, money + "\nAcme Saw Qty: 1\nPurchase date: 2026-10-18"
    )
    service = PurchaseDetails(auth.engine)
    original = service.save(
        actor, body(receipt, currency=currency, line_total=amount, money_quote=money)
    )
    cleared = service.save(
        actor,
        body(
            receipt,
            currency=currency,
            request_id="clear",
            expected_head=original["id"],
            line_total=None,
            money_quote=None,
            purchase_date=None,
            date_quote=None,
            reason="Withdraw synthetic claim",
        ),
    )
    data = json.loads(RecordExport(auth.engine).download(actor))["collections"]
    details = {row["id"]: row for row in data["receipt_details"]}
    assert details[original["id"]]["total_minor"] == 12345
    assert type(details[original["id"]]["total_minor"]) is int
    assert details[original["id"]]["currency"] == currency
    assert details[original["id"]]["purchase_date"] == "2026-10-18"
    assert details[cleared["id"]]["total_minor"] is None
    assert details[cleared["id"]]["currency"] is None
    assert details[cleared["id"]]["purchase_date"] is None
    assert len(data["reconciliation_bindings"]) == 3
    assert data["receipt_proposals"][0]["state"] == "accepted"


def test_export_does_not_reconstitute_deleted_originals(tmp_path: Path) -> None:
    from lifegather.documents.service import DocumentDelete
    from lifegather.photos.service import PhotoDelete

    auth, actor, _, _, _ = setup(tmp_path)
    photos = PhotoService(auth.engine, files(auth.engine))
    documents = DocumentService(auth.engine, files(auth.engine))
    photo = photos.upload(actor, image_bytes(), "deleted.jpg")
    document = documents.upload(actor, synthetic_pdf(), "deleted.pdf")
    photos.delete(
        actor,
        PhotoDelete(photo_id=photo["id"], expected_updated_at=photo["updated_at"]),
    )
    documents.delete(
        actor,
        DocumentDelete(
            document_id=document["id"], expected_updated_at=document["updated_at"]
        ),
    )
    data = json.loads(RecordExport(auth.engine).download(actor))["collections"]
    assert data["photos"][0]["deleted_at"] is not None
    assert data["documents"][0]["deleted_at"] is not None
    assert data["documents"][0]["extracted_text"] == ""
    assert (
        "original" not in data["photos"][0] and "original" not in data["documents"][0]
    )


def test_export_executes_only_read_queries_and_rolls_back_snapshot(
    tmp_path: Path,
) -> None:
    auth, actor, _, memory, _ = setup(tmp_path)
    memory.ingest(actor, SourceInput(text="Synthetic read-only export"))
    statements: list[str] = []

    def record(
        connection: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(auth.engine, "before_cursor_execute", record)
    try:
        RecordExport(auth.engine).download(actor)
    finally:
        event.remove(auth.engine, "before_cursor_execute", record)
    assert statements[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
    assert all(statement.startswith("SELECT ") for statement in statements[1:])
    assert len(statements) == 1 + len(COLLECTIONS)
    memory.ingest(actor, SourceInput(text="Write after completed export"))


def test_http_export_requires_owner_csrf_and_has_private_download_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "export-owner")
        foreign, other = signed_headers(app, "export-other")
        from lifegather.memory.service import MemoryService

        memory = MemoryService(app.state.auth_store.engine)
        memory.ingest(actor, SourceInput(text="OWNER ONLY"))
        memory.ingest(other, SourceInput(text="OTHER ONLY"))
        path = "/api/export/records"
        assert client.post(path, json={}).status_code == 401
        assert (
            client.post(
                path, headers={"Cookie": headers["Cookie"]}, json={}
            ).status_code
            == 403
        )
        assert client.get(path, headers=headers).status_code == 405
        assert (
            client.post(path, headers=headers, json={"user_id": other.id}).status_code
            == 422
        )
        assert (
            client.post(path, headers=headers, content=b"x" * 32769).status_code == 413
        )
        result = client.post(path, headers=headers, json={})
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        assert result.headers["x-content-type-options"] == "nosniff"
        assert result.headers["content-type"].startswith("application/json")
        assert result.headers["content-disposition"].startswith(
            'attachment; filename="lifegather-records-'
        )
        assert "OWNER ONLY" in result.text and "OTHER ONLY" not in result.text
        reverse = client.post(path, headers=foreign, json={})
        assert "OTHER ONLY" in reverse.text and "OWNER ONLY" not in reverse.text
        monkeypatch.setattr(export, "MAX_BYTES", 1)
        failed = client.post(path, headers=headers, json={})
        assert failed.status_code == 413 and "content-disposition" not in failed.headers
