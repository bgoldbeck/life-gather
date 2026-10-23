"""Full account deletion: no rows or stored files remain; other accounts intact."""

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session
from stored_files import files
from test_account_isolation import (
    ORIGIN,
    owned_tables,
    rich_alice,
    snapshot,
    use_installation,
)
from test_documents import synthetic_pdf

from lifegather.auth.deletion import deletion_order
from lifegather.auth.email_service import EmailAuth
from lifegather.auth.routes import SESSION_COOKIE
from lifegather.auth.store import AuthStore
from lifegather.documents.service import DocumentService
from lifegather.main import create_app
from lifegather.storage.base import StorageError
from lifegather.storage.local import LocalStorage


def remaining(engine: Engine, user_id: str) -> dict[str, int]:
    """Rows still holding the account's id, in owned tables and in users."""
    with engine.connect() as connection:
        counts = {
            table: int(
                connection.scalar(
                    text(f"SELECT count(*) FROM {table} WHERE user_id = :u"),
                    {"u": user_id},
                )
                or 0
            )
            for table in owned_tables(engine)
        }
        counts["users"] = int(
            connection.scalar(
                text("SELECT count(*) FROM users WHERE id = :u"), {"u": user_id}
            )
            or 0
        )
    return {table: count for table, count in counts.items() if count}


def stored(root: Path, user_id: str) -> list[Path]:
    return [path for path in (root / "users" / user_id).rglob("*") if path.is_file()]


def signed_in(client: TestClient, token: str) -> dict[str, str]:
    client.cookies.clear()
    client.cookies.set(SESSION_COOKIE, token)
    csrf = client.get("/auth/session").json()["csrf_token"]
    return {"origin": ORIGIN, "x-csrf-token": csrf}


def login(client: TestClient, subject: str) -> dict[str, str]:
    store: AuthStore = client.app.state.auth_store  # type: ignore[attr-defined]
    signed = store.login(
        subject, f"{subject}@example.test", subject.title(), now=int(time.time())
    )
    return signed_in(client, signed.token)


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    case = rich_alice(tmp_path)
    engine = case.store.engine
    DocumentService(engine, files(engine)).upload(
        case.bob, synthetic_pdf(), "bob-manual.pdf"
    )
    use_installation(case, monkeypatch)
    yield case
    engine.dispose()


def test_deletion_order_covers_every_owned_table(case: Any) -> None:
    engine = case.store.engine
    with Session(engine) as db:
        order = deletion_order(db)
    assert sorted(order) == owned_tables(engine)
    # Children before the rows they reference.
    assert order.index("memory_facts") < order.index("memory_entities")
    assert order.index("memory_entities") < order.index("memory_sources")
    assert order.index("chat_turns") < order.index("chat_conversations")


def test_deleting_an_account_removes_every_row_and_file(case: Any) -> None:
    engine = case.store.engine
    root = files(engine).root
    alice, bob = case.alice.id, case.bob.id
    assert remaining(engine, alice)
    assert stored(root, alice)
    bob_before, bob_files = snapshot(engine, bob), stored(root, bob)
    assert bob_files
    with TestClient(create_app()) as client:
        headers = login(client, "alice")
        token = client.cookies.get(SESSION_COOKIE)
        response = client.post(
            "/api/account/delete",
            json={"email": " ALICE@example.test "},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["deleted"] is True and body["rows"] > 20 and body["files"] >= 2
        assert SESSION_COOKIE in response.headers["set-cookie"]
        assert remaining(engine, alice) == {}
        assert stored(root, alice) == []
        # The old session no longer authenticates.
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, str(token))
        assert client.get("/api/me").status_code == 401
        assert client.get("/auth/session").json()["user"] is None
    assert snapshot(engine, bob) == bob_before
    assert stored(root, bob) == bob_files
    # Signing in again with the same Google identity starts an empty account.
    fresh = case.store.login("alice", "alice@example.test", "Alice", now=2).user
    assert fresh.id != alice
    assert remaining(engine, fresh.id).keys() <= {
        "users",
        "login_sessions",
        "external_identities",
    }


@pytest.mark.parametrize(
    ("body", "status"),
    [({"email": "bob@example.test"}, 400), ({"email": ""}, 422)],
)
def test_wrong_confirmation_changes_nothing(
    case: Any, body: dict[str, str], status: int
) -> None:
    engine = case.store.engine
    with TestClient(create_app()) as client:
        headers = login(client, "alice")
        before = snapshot(engine, case.alice.id)
        response = client.post("/api/account/delete", json=body, headers=headers)
        assert response.status_code == status
        assert snapshot(engine, case.alice.id) == before
        assert stored(files(engine).root, case.alice.id)


def test_deletion_needs_the_csrf_token_and_origin(case: Any) -> None:
    engine = case.store.engine
    with TestClient(create_app()) as client:
        headers = login(client, "alice")
        before = snapshot(engine, case.alice.id)
        body = {"email": "alice@example.test"}
        for bad in (
            {"origin": ORIGIN},
            {**headers, "origin": "https://attacker.example"},
            {**headers, "x-csrf-token": "wrong"},
        ):
            response = client.post("/api/account/delete", json=body, headers=bad)
            assert response.status_code == 403
        client.cookies.clear()
        assert (
            client.post("/api/account/delete", json=body, headers=headers).status_code
            == 401
        )
        assert snapshot(engine, case.alice.id) == before


def test_password_accounts_must_give_their_password(case: Any) -> None:
    engine = case.store.engine
    with TestClient(create_app()) as client:
        service: EmailAuth = client.app.state.email_auth  # type: ignore[attr-defined]
        carol = service.provision_local_account(
            "Carol", "carol@example.test", "a long synthetic password", now=1
        )
        signed = service.login(
            "carol@example.test",
            "a long synthetic password",
            client="test",
            now=int(time.time()),
        )
        headers = signed_in(client, signed.token)
        for body in (
            {"email": "carol@example.test"},
            {"email": "carol@example.test", "password": "not the password"},
        ):
            response = client.post("/api/account/delete", json=body, headers=headers)
            assert response.status_code == 400
            assert remaining(engine, carol.id)
        body = {"email": "carol@example.test", "password": "a long synthetic password"}
        response = client.post("/api/account/delete", json=body, headers=headers)
        assert response.status_code == 200, response.text
        assert remaining(engine, carol.id) == {}


def test_storage_failure_refuses_then_a_retry_completes(
    case: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = case.store.engine
    root = files(engine).root
    original = LocalStorage.delete
    calls: list[str] = []

    def failing(self: LocalStorage, key: str) -> None:
        calls.append(key)
        if len(calls) == 2:
            raise StorageError("Unable to delete the stored file")
        original(self, key)

    monkeypatch.setattr(LocalStorage, "delete", failing)
    with TestClient(create_app()) as client:
        headers = login(client, "alice")
        before = snapshot(engine, case.alice.id)
        body = {"email": "alice@example.test"}
        response = client.post("/api/account/delete", json=body, headers=headers)
        assert response.status_code == 503
        assert "nothing else was deleted" in response.json()["detail"]
        assert snapshot(engine, case.alice.id) == before
        response = client.post("/api/account/delete", json=body, headers=headers)
        assert response.status_code == 200, response.text
    assert remaining(engine, case.alice.id) == {}
    assert stored(root, case.alice.id) == []
