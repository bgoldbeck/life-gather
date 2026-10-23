from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from stored_files import files

from lifegather.documents.service import DocumentService, DocumentText
from lifegather.main import create_app
from lifegather.memory.service import MemoryError, MemoryService

pytestmark = pytest.mark.usefixtures("configured_database")


def synthetic_pdf(
    text: str = "Synthetic receipt item 349.00",
    *,
    pages: int = 1,
    encrypted: bool = False,
    compressed: bool = False,
) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(612, 792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        content = DecodedStreamObject()
        content.set_data(("BT /F1 12 Tf 50 700 Td (" + text + ") Tj ET").encode())
        page[NameObject("/Contents")] = writer._add_object(
            content.flate_encode() if compressed else content
        )
    if encrypted:
        writer.encrypt("synthetic-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_private_pdf_originals_reviewed_text_and_retry_identity() -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "a@example.test", "Alice", now=2000000000).user
        bob = store.login("bob", "b@example.test", "Bob", now=2000000000).user
        service = DocumentService(store.engine, files(store.engine))
        raw = synthetic_pdf()
        doc = service.upload(alice, raw, "synthetic-receipt.pdf")
        assert doc["source_id"] is None and doc["pages"] == 1
        assert "Synthetic receipt" in doc["extracted_text"]
        assert service.upload(alice, raw, "again.pdf")["id"] == doc["id"]
        assert service.binary(alice, doc["id"]) == raw
        assert service.list(bob)["items"] == []
        with pytest.raises(MemoryError):
            service.binary(bob, doc["id"])
        saved = service.save_text(
            alice,
            DocumentText(
                document_id=doc["id"],
                text=doc["extracted_text"],
                expected_updated_at=doc["updated_at"],
            ),
        )
        assert saved["source_id"]
        assert (
            service.save_text(
                alice,
                DocumentText(
                    document_id=doc["id"],
                    text=doc["extracted_text"],
                    expected_updated_at=doc["updated_at"],
                ),
            )["source_id"]
            == saved["source_id"]
        )
        assert (
            MemoryService(store.engine).get_source(alice, saved["source_id"]).text
            == doc["extracted_text"]
        )


@pytest.mark.parametrize(
    "raw", [b"NOT PDF", synthetic_pdf(pages=11), synthetic_pdf(encrypted=True)]
)
def test_rejects_invalid_encrypted_or_overlong_pdf(raw: bytes) -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        actor = store.login("owner", "o@example.test", "Owner", now=2000000000).user
        with pytest.raises(MemoryError):
            DocumentService(store.engine, files(store.engine)).upload(
                actor, raw, "synthetic.pdf"
            )


def test_pdf_api_privacy_corrections_and_original_deletion() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/api/documents").status_code == 401
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        alice = store.login("alice", "a@example.test", "Alice", now=2000000000)
        bob = store.login("bob", "b@example.test", "Bob", now=2000000000)
        client.cookies.set("lifegather_session", alice.token)
        headers = {
            "Origin": "http://127.0.0.1:8787",
            "X-CSRF-Token": client.get("/auth/session").json()["csrf_token"],
            "X-File-Name": "synthetic.pdf",
        }
        raw = synthetic_pdf()
        assert (
            client.post(
                "/api/documents", content=raw, headers={"X-File-Name": "synthetic.pdf"}
            ).status_code
            == 403
        )
        uploaded = client.post("/api/documents", content=raw, headers=headers)
        assert uploaded.status_code == 201
        doc = uploaded.json()
        download = client.get("/api/documents/" + doc["id"] + "/original")
        assert download.content == raw
        assert download.headers["content-type"] == "application/octet-stream"
        assert download.headers["content-disposition"].startswith("attachment;")
        assert download.headers["cache-control"] == "no-store"
        client.cookies.set("lifegather_session", bob.token)
        assert client.get("/api/documents").json()["items"] == []
        assert (
            client.get("/api/documents/" + doc["id"] + "/original").status_code == 400
        )
        client.cookies.set("lifegather_session", alice.token)
        saved = client.post(
            "/api/documents/text",
            headers=headers,
            json={
                "document_id": doc["id"],
                "text": doc["extracted_text"],
                "expected_updated_at": doc["updated_at"],
            },
        ).json()
        source = client.get("/api/chat/sources/" + saved["source_id"]).json()
        assert source["document"]["id"] == doc["id"]
        assert source["note"]["can_correct"] is True
        corrected = client.post(
            "/api/chat/sources/" + saved["source_id"] + "/corrections",
            headers=headers,
            json={
                "request_id": "pdf-correction",
                "text": "Synthetic corrected receipt item",
            },
        ).json()
        corrected_source = client.get(
            "/api/chat/sources/" + corrected["source"]["id"]
        ).json()
        assert corrected_source["document"]["id"] == doc["id"]
        assert (
            client.post(
                "/api/documents/delete",
                headers=headers,
                json={
                    "document_id": doc["id"],
                    "expected_updated_at": doc["updated_at"],
                },
            ).status_code
            == 409
        )
        deleted = client.post(
            "/api/documents/delete",
            headers=headers,
            json={"document_id": doc["id"], "expected_updated_at": saved["updated_at"]},
        )
        assert deleted.status_code == 200
        assert (
            client.get("/api/documents/" + doc["id"] + "/original").status_code == 400
        )
        assert (
            client.get("/api/chat/sources/" + corrected["source"]["id"]).json()["text"]
            == "Synthetic corrected receipt item"
        )


def test_pdf_parse_timeout_does_not_persist_an_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess
    from typing import Any

    def timeout(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired("synthetic-worker", 8)

    monkeypatch.setattr("lifegather.documents.extractor.subprocess.run", timeout)
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        actor = store.login("owner", "o@example.test", "Owner", now=2000000000).user
        service = DocumentService(store.engine, files(store.engine))
        with pytest.raises(MemoryError):
            service.upload(actor, synthetic_pdf(), "synthetic.pdf")
        assert service.list(actor)["items"] == []


def test_pdf_extraction_is_limited_and_compression_is_bounded() -> None:
    with TestClient(create_app()) as client:
        store = client.app.state.auth_store  # type: ignore[attr-defined]
        actor = store.login("owner", "o@example.test", "Owner", now=2000000000).user
        service = DocumentService(store.engine, files(store.engine))
        limited = service.upload(actor, synthetic_pdf("X" * 4100), "long.pdf")
        assert limited["text_truncated"] and len(limited["extracted_text"]) == 4000
        blank = service.upload(actor, synthetic_pdf(""), "blank.pdf")
        assert blank["extracted_text"] == "" and blank["source_id"] is None
        bomb = synthetic_pdf("X" * (2 * 1024 * 1024 + 1), compressed=True)
        assert len(bomb) < 10000
        with pytest.raises(MemoryError):
            service.upload(actor, bomb, "compressed.pdf")


def test_private_mcp_document_reads_do_not_include_original_bytes() -> None:
    from test_mcp_http import rpc, signed_headers

    app = create_app()
    with TestClient(app) as client:
        alice, owner = signed_headers(app, "document-alice")
        bob, _ = signed_headers(app, "document-bob")
        doc = DocumentService(
            app.state.auth_store.engine, files(app.state.auth_store.engine)
        ).upload(owner, synthetic_pdf(), "synthetic.pdf")
        listing = rpc(client, alice, "document_list", {}).json()["result"]
        assert "synthetic.pdf" in str(listing) and "extracted_text" not in str(listing)
        read = rpc(client, alice, "document_get", {"document_id": doc["id"]}).json()[
            "result"
        ]
        assert "Synthetic receipt" in str(read) and "%PDF-" not in str(read)
        denied = rpc(client, bob, "document_get", {"document_id": doc["id"]}).json()[
            "result"
        ]
        assert denied["isError"] is True
