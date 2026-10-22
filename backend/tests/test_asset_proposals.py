import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from database_support import database, restore_copy
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_chat import send
from test_mcp_http import rpc, signed_headers

from lifegather.auth.store import AuthStore
from lifegather.chat.provider import Completion
from lifegather.chat.service import SaveText, save_text
from lifegather.credentials.keygen import generate
from lifegather.main import create_app
from lifegather.memory.backup import operator_snapshot
from lifegather.memory.models import Entity
from lifegather.memory.notes import CorrectionInput, NoteConflict, NoteService
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.reconciliation.proposal_models import AssetProposal
from lifegather.reconciliation.proposals import (
    AssetExtraction,
    AssetFields,
    ProposalPreview,
    ProposalReview,
    ProposalService,
)
from lifegather.reconciliation.service import ReconciliationService

TEXT = "I bought a Husqvarna 525L trimmer."


def fields(**changes: Any) -> AssetFields:
    return AssetFields.model_validate(
        {
            "name": "Husqvarna 525L",
            "manufacturer": "Husqvarna",
            "model": "525L",
            "serial": None,
            "kind": "purchase",
            "quote": TEXT,
            **changes,
        }
    )


def setup(tmp_path: Path) -> tuple[Any, ...]:
    auth = AuthStore(database(tmp_path))
    auth.migrate()
    alice = auth.login("alice", "alice@example.test", "Alice", now=1).user
    bob = auth.login("bob", "bob@example.test", "Bob", now=1).user
    memory = MemoryService(auth.engine)
    original = save_text(memory, alice, SaveText(text=TEXT, request_id="original"))
    service = ProposalService(auth.engine)
    proposal = service.create(
        alice,
        original.id,
        AssetExtraction(
            candidate=fields(),
            explanation="A stated purchase, not verified current ownership.",
        ),
    )
    return auth, alice, bob, memory, original, service, proposal


def review(identifier: str, key: str = "accept", **changes: Any) -> ProposalReview:
    return ProposalReview.model_validate(
        {
            "proposal_id": identifier,
            "request_id": key,
            "action": "new",
            "fields": fields().model_dump(),
            **changes,
        }
    )


def test_proposal_does_not_write_inventory_and_confirm_is_atomic_idempotent(
    tmp_path: Path,
) -> None:
    auth, alice, bob, memory, original, service, proposal = setup(tmp_path)
    assert ReconciliationService(auth.engine).inventory(alice) == []
    assert memory.export_page(alice, "entities")["items"] == []
    assert service.for_source(alice, original.id) == proposal["id"]
    preview = service.preview(
        alice,
        ProposalPreview(proposal_id=proposal["id"], fields=fields(name="trimmer")),
    )
    assert preview["candidates"] == []
    data = review(proposal["id"], fields=fields(name="trimmer").model_dump())
    with ThreadPoolExecutor(max_workers=4) as pool:
        accepted = list(pool.map(lambda _: service.review(alice, data), range(4)))
    assert all(result == accepted[0] for result in accepted)
    asset_id = accepted[0]["result"]["asset_ids"][0]
    assert ReconciliationService(auth.engine).inventory(alice) == [asset_id]
    assert memory.get_entity(alice, asset_id).name == "trimmer"
    facts = memory.facts(alice, asset_id)
    owned = next(f for f in facts if f.predicate == "owned")
    assert owned.status == "inferred" and owned.evidence[0]["source_id"] == original.id
    assert memory.get_source(alice, original.id).text == TEXT
    assert accepted[0]["proposed"]["candidate"]["name"] == "Husqvarna 525L"
    assert accepted[0]["reviewed"]["name"] == "trimmer"
    assert service.export_page(bob)["items"] == []
    with pytest.raises(MemoryError):
        service.get(bob, proposal["id"])
    with pytest.raises(MemoryError):
        service.review(bob, data)
    with pytest.raises(NoteConflict):
        service.review(alice, review(proposal["id"], "other"))
    backup = tmp_path / "restored.jsonl"
    operator_snapshot(auth.engine, backup)
    restored = AuthStore(restore_copy(backup))
    restored.migrate()
    assert ProposalService(restored.engine).get(alice, proposal["id"]) == accepted[0]
    assert ReconciliationService(restored.engine).inventory(alice) == [asset_id]


def test_reject_invalid_evidence_stale_sources_and_mentions(tmp_path: Path) -> None:
    auth, alice, _, memory, original, service, proposal = setup(tmp_path)
    for changed in (
        fields(serial="invented"),
        fields(quote="not the original"),
        fields(name="invented"),
    ):
        with pytest.raises(MemoryError):
            service.review(alice, review(proposal["id"], fields=changed.model_dump()))
    with pytest.raises(MemoryError):
        service.review(
            alice, review(proposal["id"], fields=fields(kind="mention").model_dump())
        )
    NoteService(auth.engine).correct(
        alice,
        CorrectionInput(
            source_id=original.id,
            request_id="correction",
            text="I no longer own that trimmer.",
        ),
    )
    with pytest.raises(NoteConflict):
        service.review(alice, review(proposal["id"]))
    rejected = service.review(
        alice, review(proposal["id"], "reject", action="reject", fields=None)
    )
    assert rejected["state"] == "rejected" and rejected["stale"] is True
    assert ReconciliationService(auth.engine).inventory(alice) == []
    assert (
        service.review(
            alice, review(proposal["id"], "reject", action="reject", fields=None)
        )
        == rejected
    )
    with pytest.raises(NoteConflict):
        service.review(alice, review(proposal["id"], "reject"))
    assert memory.get_source(alice, original.id).text == TEXT


def test_possible_duplicates_require_checked_explicit_identity(tmp_path: Path) -> None:
    auth, alice, bob, memory, _, service, proposal = setup(tmp_path)
    first = service.review(alice, review(proposal["id"]))
    asset_id = first["result"]["asset_ids"][0]
    source = save_text(
        memory, alice, SaveText(text=TEXT + " Another note.", request_id="another")
    )
    second = service.create(
        alice,
        source.id,
        AssetExtraction(candidate=fields(), explanation="Possible repeat mention."),
    )
    checked = service.preview(
        alice, ProposalPreview(proposal_id=second["id"], fields=fields())
    )
    assert checked["candidates"][0]["id"] == asset_id
    with pytest.raises(NoteConflict):
        service.review(alice, review(second["id"]))
    with pytest.raises(NoteConflict):
        service.review(
            alice,
            review(
                second["id"],
                action="link",
                asset_id="foreign",
                candidate_ids=[asset_id],
            ),
        )
    linked = service.review(
        alice,
        review(
            second["id"],
            "accept-second",
            action="link",
            asset_id=asset_id,
            candidate_ids=[asset_id],
        ),
    )
    assert linked["result"]["asset_ids"] == [asset_id]
    assert ReconciliationService(auth.engine).inventory(alice) == [asset_id]
    assert ReconciliationService(auth.engine).inventory(bob) == []
    third_source = save_text(
        memory, alice, SaveText(text=TEXT + " Separate item.", request_id="third")
    )
    third = service.create(
        alice,
        third_source.id,
        AssetExtraction(candidate=fields(), explanation="Separate item."),
    )
    service.review(alice, review(third["id"], "accept-third", candidate_ids=[asset_id]))
    assert len(ReconciliationService(auth.engine).inventory(alice)) == 2


def test_failure_rolls_back_derived_graph_and_proposal_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth, alice, _, memory, _, service, proposal = setup(tmp_path)
    original_audit = service.memory._audit

    def fail(db: Any, actor: Any, operation: str, target: str, now: int) -> None:
        if operation == "asset_proposal_accepted":
            raise MemoryError("Synthetic commit failure")
        original_audit(db, actor, operation, target, now)

    monkeypatch.setattr(service.memory, "_audit", fail)
    with pytest.raises(MemoryError):
        service.review(alice, review(proposal["id"]))
    assert service.get(alice, proposal["id"])["state"] == "proposed"
    assert memory.export_page(alice, "entities")["items"] == []
    assert memory.search(alice, "trimmer")[0]["kind"] == "source"
    assert ReconciliationService(auth.engine).inventory(alice) == []
    with Session(auth.engine) as db:
        assert not list(db.scalars(select(Entity)))


class FakeExtractor:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.value = AssetExtraction(
            candidate=fields(), explanation="Review the stated purchase."
        ).model_dump()
        self.fail = False
        self.started: threading.Event | None = None
        self.hold = False

    async def complete(
        self,
        secret: str,
        model: str,
        instruction: str,
        payload: dict[str, Any],
        schema: Any,
    ) -> Completion:
        assert schema is AssetExtraction and "untrusted" in instruction
        self.calls.append(payload)
        if self.fail:
            raise ValueError("SENSITIVE secret provider response")
        if self.hold:
            if self.started:
                self.started.set()
            await asyncio.Event().wait()
        return Completion(self.value, 12, 8)


def test_extraction_http_mcp_consent_replay_and_no_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = tmp_path / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()
    provider = FakeExtractor()
    app.state.chat_provider = provider
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        conversation = client.post("/api/chat/conversations", headers=alice).json()[
            "id"
        ]
        credential = client.post(
            "/api/credentials",
            headers=alice,
            json={
                "kind": "ai",
                "provider": "openai",
                "label": "Fixture",
                "secret": "synthetic-sensitive-token",
            },
        ).json()["id"]
        saved = send(client, alice, conversation, "save", "save", TEXT).json()
        source = saved["result"]["sources"][0]["id"]
        params = {
            "source_id": source,
            "credential_id": credential,
            "model": "fixture-model",
        }
        denied = send(client, alice, conversation, "denied", "extract", TEXT, **params)
        assert denied.json()["state"] == "failed" and not provider.calls
        client.put("/api/settings", headers=alice, json={"allow_external_ai": True})
        answer = send(
            client, alice, conversation, "extract", "extract", TEXT, **params
        ).json()
        assert answer["state"] == "complete", answer
        identifier = answer["result"]["proposal_id"]
        assert provider.calls == [{"saved_note": TEXT}]
        assert client.get("/api/chat/usage", headers=alice).json()["requests"] == 1
        assert (
            send(
                client, alice, conversation, "extract", "extract", TEXT, **params
            ).json()
            == answer
        )
        cached = send(
            client, alice, conversation, "extract-again", "extract", TEXT, **params
        ).json()
        assert (
            cached["result"]["proposal_id"] == identifier and len(provider.calls) == 1
        )
        path = f"/api/chat/asset-proposals/{identifier}"
        assert client.get(path).status_code == 401
        assert client.get(path, headers=bob).status_code == 400
        body = review(identifier).model_dump()
        assert (
            client.post(
                "/api/chat/asset-proposals/review",
                json=body,
                headers={"Cookie": alice["Cookie"]},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/chat/asset-proposals/review",
                json={**body, "user_id": "foreign"},
                headers=alice,
            ).status_code
            == 422
        )
        assert (
            client.get(f"/api/chat/sources/{source}", headers=alice).json()[
                "asset_proposal_id"
            ]
            == identifier
        )
        assert rpc(
            client, bob, "asset_proposal_get", {"proposal_id": identifier}
        ).json()["result"]["isError"]
        assert (
            rpc(
                client,
                alice,
                "asset_proposal_preview",
                {"proposal_id": identifier, "fields": fields().model_dump()},
            ).json()["result"]["structuredContent"]["candidates"]
            == []
        )
        accepted = rpc(client, alice, "asset_proposal_review", body).json()["result"][
            "structuredContent"
        ]
        assert accepted["state"] == "accepted"
        assert (
            client.post(
                "/api/chat/asset-proposals/review", json=body, headers=alice
            ).json()
            == accepted
        )
        assert (
            client.post(
                "/api/chat/asset-proposals/review",
                json={**body, "request_id": "different"},
                headers=alice,
            ).status_code
            == 409
        )
        assert (
            len(ReconciliationService(app.state.auth_store.engine).inventory(actor))
            == 1
        )
        # Reopen the application and retrieve the same review without provider access.
    with TestClient(create_app()) as restarted:
        assert restarted.get(path, headers=alice).json() == accepted


def test_serial_identity_and_competing_reviews(tmp_path: Path) -> None:
    auth, alice, _, memory, _, service, proposal = setup(tmp_path)

    def accept(index: int) -> str:
        try:
            return str(
                service.review(alice, review(proposal["id"], f"competing-{index}"))[
                    "state"
                ]
            )
        except NoteConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = list(pool.map(accept, range(4)))
    assert outcomes.count("accepted") == 1 and outcomes.count("conflict") == 3
    serial_text = "I own a Husqvarna 525L serial ABC123."
    serial_fields = fields(serial="ABC123", quote=serial_text, kind="possession")
    source = save_text(memory, alice, SaveText(text=serial_text, request_id="serial"))
    serial_proposal = service.create(
        alice,
        source.id,
        AssetExtraction(candidate=serial_fields, explanation="An explicit serial."),
    )
    with pytest.raises(MemoryError):
        service.preview(
            alice,
            ProposalPreview(
                proposal_id=serial_proposal["id"],
                fields=fields(serial="abc123", quote=serial_text, kind="possession"),
            ),
        )
    preview = service.preview(
        alice, ProposalPreview(proposal_id=serial_proposal["id"], fields=serial_fields)
    )
    current = service.review(
        alice,
        review(
            serial_proposal["id"],
            "serial-accept",
            fields=serial_fields.model_dump(),
            candidate_ids=[c["id"] for c in preview["candidates"]],
        ),
    )
    other = save_text(
        memory,
        alice,
        SaveText(text=serial_text + " A later note.", request_id="same-serial"),
    )
    other_proposal = service.create(
        alice,
        other.id,
        AssetExtraction(candidate=serial_fields, explanation="Same serial."),
    )
    duplicate = service.preview(
        alice, ProposalPreview(proposal_id=other_proposal["id"], fields=serial_fields)
    )
    assert duplicate["reliable_ids"] == current["result"]["asset_ids"]
    with pytest.raises(NoteConflict):
        service.review(
            alice,
            review(
                other_proposal["id"],
                "no-double-serial",
                fields=serial_fields.model_dump(),
                candidate_ids=[c["id"] for c in duplicate["candidates"]],
            ),
        )


@pytest.mark.parametrize(
    "case",
    [
        "no_item",
        "invalid_quote",
        "provider_failure",
        "foreign_source",
        "budget",
        "cancel",
    ],
)
def test_extraction_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    from lifegather.chat.models import Usage
    from lifegather.chat.service import ChatService

    key = tmp_path / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()
    provider = FakeExtractor()
    app.state.chat_provider = provider
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        _, bob_actor = signed_headers(app, "bob")
        conversation = client.post("/api/chat/conversations", headers=alice).json()[
            "id"
        ]
        credential = client.post(
            "/api/credentials",
            headers=alice,
            json={
                "kind": "ai",
                "provider": "openai",
                "label": "Fixture",
                "secret": "synthetic-sensitive-token",
            },
        ).json()["id"]
        client.put("/api/settings", headers=alice, json={"allow_external_ai": True})
        source_actor = actor
        if case == "foreign_source":
            source_actor = bob_actor
        source = save_text(
            MemoryService(app.state.auth_store.engine),
            source_actor,
            SaveText(text=TEXT, request_id="boundary-note"),
        )
        params = {
            "credential_id": credential,
            "model": "fixture-model",
            "source_id": source.id,
        }
        if case == "no_item":
            provider.value = {
                "candidate": None,
                "explanation": "Multiple items or no supported possession.",
            }
        if case == "invalid_quote":
            provider.value = AssetExtraction(
                candidate=fields(quote="Invented evidence"),
                explanation="Unsafe proposal",
            ).model_dump()
        if case == "provider_failure":
            provider.fail = True
        if case == "budget":
            chat = ChatService(app.state.auth_store.engine)
            chat.reserve(actor, app.state.private_settings, credential)
            with Session(chat.engine) as db, db.begin():
                usage = db.get(Usage, (actor.id, chat.usage(actor)["day"]))
                assert usage is not None
                usage.requests = 20
        if case == "cancel":
            provider.started = threading.Event()
            provider.hold = True
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    send,
                    client,
                    alice,
                    conversation,
                    "boundary",
                    "extract",
                    TEXT,
                    **params,
                )
                assert provider.started.wait(5)
                assert (
                    client.post(
                        "/api/chat/requests/boundary/cancel", headers=alice
                    ).json()["state"]
                    == "canceled"
                )
                result = future.result(timeout=5)
            assert result.json()["state"] == "canceled"
        else:
            result = send(
                client, alice, conversation, "boundary", "extract", TEXT, **params
            )
            assert result.json()["state"] == (
                "complete" if case == "no_item" else "failed"
            )
        assert (
            "SENSITIVE" not in result.text
            and "synthetic-sensitive-token" not in result.text
        )
        service = ProposalService(app.state.auth_store.engine)
        assert ReconciliationService(service.engine).inventory(actor) == []
        rows = service.export_page(actor)["items"]
        assert len(rows) == (1 if case == "no_item" else 0)
        if case in {"foreign_source", "budget"}:
            assert provider.calls == []
        if case == "no_item":
            assert rows[0]["state"] == "no_item"
            with pytest.raises(NoteConflict):
                service.review(actor, review(rows[0]["id"]))


@pytest.mark.usefixtures("legacy_audit_writer")
def test_upgrade_foreign_keys_and_export_paging(tmp_path: Path) -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import insert
    from sqlalchemy.exc import IntegrityError

    import lifegather

    auth = AuthStore(database(tmp_path / "legacy", empty=True))
    config = Config()
    config.set_main_option(
        "script_location", str(Path(lifegather.__file__).parent / "migrations")
    )
    with auth.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0007_note_corrections")
    signed = auth.login("legacy", "legacy@example.test", "Legacy", now=100)
    source = save_text(
        MemoryService(auth.engine),
        signed.user,
        SaveText(text=TEXT, request_id="old-note"),
    )
    from lifegather.chat.service import ChatService, TurnInput

    chat = ChatService(auth.engine)
    conversation = chat.create(signed.user)["id"]
    turn = TurnInput(request_id="old-request", mode="save", text=TEXT)
    prior, _ = chat.begin(signed.user, conversation, turn)
    chat.finish(signed.user, prior["id"], {"text": "Saved"})
    auth.migrate()
    assert auth.authenticate(signed.token, now=101) is not None
    replay, fresh = chat.begin(signed.user, conversation, turn)
    assert not fresh and replay["id"] == prior["id"]
    service = ProposalService(auth.engine)
    original = service.create(
        signed.user,
        source.id,
        AssetExtraction(candidate=fields(), explanation="Legacy note"),
    )
    for index in range(26):
        note = save_text(
            service.memory,
            signed.user,
            SaveText(
                text=f"Synthetic separate note {index}", request_id=f"note-{index}"
            ),
        )
        service.create(
            signed.user,
            note.id,
            AssetExtraction(candidate=None, explanation="No supported item"),
        )
    first = service.export_page(signed.user)
    second = service.export_page(signed.user, first["next_cursor"])
    assert len(first["items"]) == 25 and len(second["items"]) == 2
    assert len({r["id"] for r in first["items"] + second["items"]}) == 27
    bob = auth.login("bob", "bob@example.test", "Bob", now=100).user
    with pytest.raises(IntegrityError), auth.engine.begin() as connection:
        connection.execute(
            insert(AssetProposal).values(
                id="foreign-link",
                user_id=bob.id,
                source_id=source.id,
                recorded_at=1,
                state="no_item",
                proposed_json="{}",
                result_json="{}",
            )
        )
    assert service.get(signed.user, original["id"])["state"] == "proposed"
