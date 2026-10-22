"""Synthetic format fixtures exercise actual bounded local workers, not providers."""

import json
import subprocess
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from stored_files import files

from lifegather.documents.service import DocumentService, DocumentText
from lifegather.main import create_app
from lifegather.memory.archive import PersonalArchive
from lifegather.memory.service import MemoryError, MemoryService


def office(kind: str, *, unsafe: bool = False) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        if kind == "docx":
            archive.writestr(
                "word/document.xml",
                '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                'wordprocessingml/2006/main"><w:body><w:p><w:r>'
                "<w:t>Synthetic filter guide</w:t></w:r></w:p><w:tbl><w:tr><w:tc>"
                "<w:p><w:r><w:t>Filter 0012</w:t></w:r></w:p>"
                "</w:tc></w:tr></w:tbl></w:body></w:document>",
            )
        else:
            archive.writestr(
                "xl/workbook.xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
                'officeDocument/2006/relationships"><sheets>'
                '<sheet name="Inventory" sheetId="1" r:id="rId1"/>'
                '<sheet name="Other" sheetId="2" r:id="rId2"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/'
                'package/2006/relationships"><Relationship Id="rId1" '
                'Target="worksheets/sheet1.xml"/><Relationship Id="rId2" '
                'Target="worksheets/sheet2.xml"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main"><sheetData><row r="1">'
                '<c r="A1" t="inlineStr"><is><t>Serial</t></is></c>'
                '<c r="B1" t="inlineStr"><is><t>Value</t></is></c></row>'
                '<row r="2"><c r="A2" t="inlineStr"><is><t>0012</t></is></c>'
                '<c r="B2"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>',
            )
            archive.writestr(
                "xl/worksheets/sheet2.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/'
                'spreadsheetml/2006/main"><sheetData><row r="1">'
                '<c r="A1" t="inlineStr"><is><t>Other sheet</t></is></c>'
                "</row></sheetData></worksheet>",
            )
        if unsafe:
            archive.writestr("../escape.xml", "bad")
    return output.getvalue()


@pytest.mark.parametrize(
    "extension,raw,needle",
    [
        ("txt", b"Synthetic filter 0012\nSecond line", "L1"),
        ("md", b"# Synthetic guide\n<script>untrusted</script>", "# Synthetic guide"),
        ("csv", b"Serial;Amount\n0012;19.90\n", "0012"),
        ("docx", office("docx"), "Filter 0012"),
        ("xlsx", office("xlsx"), "0012"),
    ],
)
def test_formats_keep_reviewed_evidence_originals_owner_and_archive(
    extension: str, raw: bytes, needle: str
) -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("formats-alice", "a@example.test", "A", now=2000000000).user
        bob = store.login("formats-bob", "b@example.test", "B", now=2000000000).user
        service = DocumentService(store.engine, files(store.engine))
        doc = service.upload(alice, raw, "synthetic." + extension)
        assert doc["format"] == extension
        assert doc["pages"] is None
        assert doc["mime"] != "application/pdf"
        assert needle in doc["extracted_text"]
        assert doc["extraction_metadata"]["parser_version"]
        assert service.binary(alice, doc["id"]) == raw
        assert service.upload(alice, raw, "again." + extension)["id"] == doc["id"]
        with pytest.raises(MemoryError):
            service.binary(bob, doc["id"])
        assert service.list(bob)["items"] == []
        saved = service.save_text(
            alice,
            DocumentText(
                document_id=doc["id"],
                text=doc["extracted_text"],
                expected_updated_at=doc["updated_at"],
            ),
        )
        assert (
            MemoryService(store.engine).get_source(alice, saved["source_id"]).text
            == doc["extracted_text"]
        )
        assert service.source_document(alice, saved["source_id"])["format"] == extension  # type: ignore[index]
        with ZipFile(
            BytesIO(PersonalArchive(store.engine, files(store.engine)).download(alice))
        ) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            original = manifest["originals"][0]
            assert original["path"].endswith("." + extension)
            assert original["mime"] == doc["mime"]
            assert archive.read(original["path"]) == raw
            records = json.loads(archive.read("records.json"))
            assert records["collections"]["documents"][0]["pages"] is None


def test_xlsx_selection_and_csv_encoding_delimiter_preview() -> None:
    from lifegather.documents.service import DocumentPreview

    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        actor = store.login("preview", "p@example.test", "P", now=2000000000).user
        service = DocumentService(store.engine, files(store.engine))
        doc = service.upload(actor, office("xlsx"), "inventory.xlsx")
        assert doc["extraction_metadata"]["sheets"] == ["Inventory", "Other"]
        assert "formula" in doc["extracted_text"].lower()
        assert "cached" in doc["extracted_text"].lower()
        preview = service.preview(
            actor,
            DocumentPreview(document_id=doc["id"], sheet="Other", cell_range="A1:A1"),
        )
        assert "Other sheet" in preview["text"] and "0012" not in preview["text"]
        csv = service.upload(actor, b"Serial;Amount\n0012;19.90\n", "inventory.csv")
        preview = service.preview(
            actor, DocumentPreview(document_id=csv["id"], delimiter=";", header=True)
        )
        assert preview["metadata"]["delimiter"] == ";"
        assert "R2C1" in preview["text"] and "0012" in preview["text"]
        assert service.get(actor, doc["id"])["source_id"] is None


@pytest.mark.parametrize(
    "filename,raw",
    [
        ("bad.docx", office("docx", unsafe=True)),
        ("wrong.xlsx", office("docx")),
        ("bad.txt", b"\x00\x01binary"),
        ("bad.txt", b"\xffinvalid utf8"),
        ("legacy.doc", b"legacy"),
        ("macro.xlsm", office("xlsx")),
    ],
)
def test_rejects_unsafe_mislabeled_or_unsupported_files(
    filename: str, raw: bytes
) -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        actor = store.login("reject", "r@example.test", "R", now=2000000000).user
        with pytest.raises(MemoryError):
            DocumentService(store.engine, files(store.engine)).upload(
                actor, raw, filename
            )
        assert (
            DocumentService(store.engine, files(store.engine)).list(actor)["items"]
            == []
        )


def test_document_http_mcp_preview_search_and_deletion() -> None:
    from test_mcp_http import rpc, signed_headers

    from lifegather.documents.service import DocumentDelete, DocumentPreview
    from lifegather.memory.library import LibraryPage, MemoryLibrary

    app = create_app()
    with TestClient(app) as client:
        headers, actor = signed_headers(app, "formats-api")
        other_headers, _ = signed_headers(app, "formats-other")
        # The MCP fixture's headers carry its session cookie.
        raw = b"Serial;Value\n0012;19.90\n"
        response = client.post(
            "/api/documents",
            content=raw,
            headers={**headers, "X-File-Name": "inventory.csv"},
        )
        assert response.status_code == 201
        doc = response.json()
        original = client.get(f"/api/documents/{doc['id']}/original", headers=headers)
        assert original.content == raw
        assert original.headers["content-disposition"].endswith('.csv"')
        assert (
            client.post(
                "/api/documents/preview",
                json={"document_id": doc["id"]},
                headers=other_headers,
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/documents/preview",
                json={"document_id": doc["id"], "user_id": actor.id},
                headers=headers,
            ).status_code
            == 422
        )
        preview = client.post(
            "/api/documents/preview",
            json={"document_id": doc["id"], "delimiter": ";"},
            headers=headers,
        )
        assert preview.status_code == 200 and "0012" in preview.json()["text"]
        read = rpc(client, headers, "document_get", {"document_id": doc["id"]}).json()[
            "result"
        ]
        assert "csv" in str(read) and "parser_version" in str(read)
        service = DocumentService(
            app.state.auth_store.engine, files(app.state.auth_store.engine)
        )
        saved = service.save_text(
            actor,
            DocumentText(
                document_id=doc["id"],
                text=doc["extracted_text"],
                expected_updated_at=doc["updated_at"],
            ),
        )
        assert MemoryLibrary(service.engine).list(
            actor, LibraryPage(kind="documents", query="0012")
        )["items"]
        service.delete(
            actor,
            DocumentDelete(
                document_id=doc["id"], expected_updated_at=saved["updated_at"]
            ),
        )
        with pytest.raises(MemoryError):
            service.preview(actor, DocumentPreview(document_id=doc["id"]))
        assert MemoryService(service.engine).get_source(actor, saved["source_id"]).text


def test_non_pdf_documents_survive_encrypted_recovery(tmp_path: Path) -> None:
    from test_recovery_bundle import PASSWORD, installation

    from lifegather.auth.store import AuthStore
    from lifegather.recovery.bundle import RecoveryService

    case = installation(tmp_path)
    service = DocumentService(case.store.engine, files(case.store.engine))
    originals = [(kind, office(kind)) for kind in ("docx", "xlsx")]
    originals += [
        (kind, ("Synthetic 0012 " + kind).encode()) for kind in ("txt", "md", "csv")
    ]
    documents = [
        service.upload(case.alice, raw, "synthetic." + kind) for kind, raw in originals
    ]
    recovery = RecoveryService(case.settings)
    bundle, restored = tmp_path / "formats.lgbackup", tmp_path / "restored-formats"
    recovery.create(bundle, PASSWORD)
    recovery.restore(bundle, restored, PASSWORD)
    store = AuthStore(restored / "data" / "auth.sqlite3")
    for doc, (kind, raw) in zip(documents, originals, strict=True):
        reader = DocumentService(store.engine, files(store.engine))
        assert reader.binary(case.alice, doc["id"]) == raw
        assert reader.get(case.alice, doc["id"])["format"] == kind
        with pytest.raises(MemoryError):
            reader.binary(case.bob, doc["id"])
    store.engine.dispose()


def test_explicit_legacy_encoding_and_worker_limits() -> None:
    from zipfile import ZIP_DEFLATED

    from lifegather.documents.extractor import extract_document
    from lifegather.documents.formats import PreviewOptions

    latin = extract_document(b"Caf\xe9", "txt", PreviewOptions(encoding="cp1252"))
    assert "Café" in latin.text and latin.metadata["encoding"] == "cp1252"
    long = extract_document(b"X" * 4500, "txt", PreviewOptions())
    assert long.truncated and len(long.text) == 4000
    with pytest.raises(subprocess.CalledProcessError):
        extract_document(office("xlsx"), "xlsx", PreviewOptions(cell_range="A1:AZ201"))
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(subprocess.CalledProcessError):
        extract_document(output.getvalue(), "docx", PreviewOptions())
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<!DOCTYPE Types [<!ENTITY x "bad">]><Types>&x;</Types>',
        )
    with pytest.raises(subprocess.CalledProcessError):
        extract_document(output.getvalue(), "docx", PreviewOptions())


def test_document_migration_preserves_existing_pdf_bytes_and_refuses_lossy_downgrade(
    tmp_path: Path,
) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from test_documents import synthetic_pdf

    from lifegather.auth.store import AuthStore

    store = AuthStore(tmp_path / "migration.sqlite3")
    store.migrate()
    actor = store.login("migration", "m@example.test", "M", now=1).user
    service = DocumentService(store.engine, files(store.engine))
    raw = synthetic_pdf()
    doc = service.upload(actor, raw, "legacy.pdf")
    saved = service.save_text(
        actor,
        DocumentText(
            document_id=doc["id"],
            text=doc["extracted_text"],
            expected_updated_at=doc["updated_at"],
        ),
    )
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parents[1] / "src/lifegather/migrations")
    )
    storage = files(store.engine)

    def inline() -> None:
        # Older schemas hold originals in the database; 0028 refuses otherwise.
        with store.engine.begin() as connection:
            rows = connection.execute(
                text("SELECT id, original_key FROM documents WHERE original_key!=''")
            ).all()
            for identifier, key in rows:
                connection.execute(
                    text(
                        "UPDATE documents SET original=:raw, original_key=NULL "
                        "WHERE id=:id"
                    ),
                    {"raw": storage.get(key), "id": identifier},
                )

    with pytest.raises(RuntimeError, match="object storage"):
        with store.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0027_forest_dark_theme")
    inline()
    with store.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0024_maintenance")
        assert (
            connection.scalar(
                text("SELECT original FROM documents WHERE id=:id"), {"id": doc["id"]}
            )
            == raw
        )
    store.migrate()
    restored = service.get(actor, doc["id"])
    assert restored["format"] == "pdf" and restored["source_id"] == saved["source_id"]
    assert service.binary(actor, doc["id"]) == raw
    service.upload(actor, b"Synthetic new text", "new.txt")
    inline()
    with pytest.raises(ValueError, match="non-PDF"):
        with store.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0024_maintenance")
    assert service.get(actor, doc["id"])["format"] == "pdf"
    store.engine.dispose()
