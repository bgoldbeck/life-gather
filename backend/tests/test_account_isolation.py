"""Cross-account isolation: row-level security, files, jobs, HTTP routes and MCP.

Bob signs in and calls every HTTP route and MCP tool with Alice's identifiers.
No response may contain Alice's records and none of Alice's rows may change.
"""

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

import pytest
from database_support import database
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from stored_files import files
from test_documents import synthetic_pdf
from test_maintenance import plan
from test_mcp_http import rpc, signed_headers
from test_recovery_bundle import Installation, installation
from test_scans import SyntheticHandler, registry

from lifegather.auth.store import Account, AuthStore
from lifegather.chat.service import ChatService, TurnInput
from lifegather.database import ACCOUNT_ROLE, ACTING_ACCOUNT, account_scope
from lifegather.documents.service import DocumentService
from lifegather.findings.service import FindingSave, FindingService
from lifegather.main import create_app
from lifegather.maintenance.service import MaintenanceService
from lifegather.mcp_api.schemas import INPUTS
from lifegather.memory.schemas import SourceInput
from lifegather.memory.service import MemoryError, MemoryService
from lifegather.scans.models import ScanRun
from lifegather.scans.registry import (
    ScanBatch,
    ScanContext,
    ScanEvidence,
    ScanRegistry,
)
from lifegather.scans.schedules import ScheduleInput, ScheduleService
from lifegather.scans.service import ScanService
from lifegather.scans.worker import ScanWorker
from lifegather.storage.base import StorageError

pytestmark = pytest.mark.usefixtures("configured_database")

ORIGIN = "http://127.0.0.1:8787"

# Which of Alice's records an identifier names. A new identifier parameter or
# body field fails test_every_identifier_is_mapped until it is listed here.
ENTITY = ("memory_entities",)
ID_TABLES: dict[str, tuple[str, ...]] = {
    "asset_id": ENTITY,
    "asset_ids": ENTITY,
    "candidate_ids": ENTITY,
    "entity_id": ENTITY,
    "primary_id": ENTITY,
    "secondary_id": ENTITY,
    "target_asset_id": ENTITY,
    "subject_id": ENTITY,
    "object_id": ENTITY,
    "run_id": ("scan_runs",),
    "last_run_id": ("scan_runs",),
    "action_id": ("asset_actions",),
    "expected_action_id": ("asset_actions",),
    "consolidation_id": ("asset_consolidations",),
    "conversation_id": ("chat_conversations",),
    "credential_id": ("credentials",),
    "decision_id": ("reconciliation_decisions",),
    "expected_decision_id": ("reconciliation_decisions",),
    "document_id": ("documents",),
    "field_id": ("asset_type_fields",),
    "id": ("asset_type_fields",),
    "mailbox_id": ("mailboxes",),
    "observation_id": ("reconciliation_observations",),
    "order_id": ("reconciliation_purchases",),
    "photo_id": ("photos",),
    "proposal_id": ("asset_proposals", "receipt_proposals"),
    "purchase_id": ("reconciliation_purchases",),
    "receipt_id": ("receipt_proposals",),
    "replaces_id": ("memory_facts",),
    "request_id": ("<request ids>",),
    "source_id": ("memory_sources",),
    "task_id": ("maintenance_tasks",),
    "turn_id": ("chat_turns",),
    "finding_id": ("research_findings",),
    "type_id": ("asset_types",),
}
# `identifier` path parameters, by route prefix.
IDENTIFIERS = {
    "/api/scans/": ("scan_runs",),
    "/api/scan-schedules/": ("scan_schedules",),
    "/api/purchases/sources/": ("memory_sources",),
    "/api/purchases/": ("reconciliation_purchases",),
}
# Sign-in, sign-out and health routes act before or outside an account.
SKIPPED = (
    "/auth/",
    "/health",
    "/api/version",
)
# Distinctive text only Alice's records contain.
MARKERS = ("mower", "Acme", "Red paint", "Blue paint", "alice@example.test")


def owned_tables(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.scalars(
                text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND column_name = 'user_id' "
                    "ORDER BY table_name"
                )
            )
        )


def columns(engine: Engine, name: str) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.scalars(
                text(
                    "SELECT table_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND column_name = :name"
                ),
                {"name": name},
            )
        )


def identifiers(engine: Engine, user_id: str) -> dict[str, list[str]]:
    """Each owned table's ids for one account, read in the system context."""
    found: dict[str, list[str]] = {}
    with engine.connect() as connection:
        for table in columns(engine, "id"):
            if table in owned_tables(engine):
                found[table] = list(
                    connection.scalars(
                        text(f"SELECT id FROM {table} WHERE user_id = :u ORDER BY id"),
                        {"u": user_id},
                    )
                )
        found["<request ids>"] = sorted(
            {
                value
                for table in columns(engine, "request_id")
                if table in owned_tables(engine)
                for value in connection.scalars(
                    text(f"SELECT request_id FROM {table} WHERE user_id = :u"),
                    {"u": user_id},
                )
                if value
            }
        )
    return found


def snapshot(engine: Engine, user_id: str) -> dict[str, str | None]:
    """A digest of every row the account owns."""
    with engine.connect() as connection:
        digests = {
            table: connection.scalar(
                text(
                    f"SELECT md5(string_agg(t::text, '|' ORDER BY t::text)) "
                    f"FROM {table} t WHERE user_id = :u"
                ),
                {"u": user_id},
            )
            for table in owned_tables(engine)
            # Signing in prunes expired sessions of every account.
            if table != "login_sessions"
        }
        digests["users"] = connection.scalar(
            text("SELECT md5(u::text) FROM users u WHERE id = :u"), {"u": user_id}
        )
    return digests


def rich_alice(tmp_path: Path) -> Installation:
    """The recovery fixture plus Alice's documents, tasks, chat and scans."""
    case = installation(tmp_path)
    engine = case.store.engine
    alice = case.alice
    DocumentService(engine, files(engine)).upload(
        alice, synthetic_pdf(), "alice-mower-manual.pdf"
    )
    MaintenanceService(engine).create(alice, plan(case.primary))
    chat = ChatService(engine)
    conversation = chat.create(alice)["id"]
    row, _ = chat.begin(
        alice,
        conversation,
        TurnInput(request_id="alice-chat", mode="search", text="Where is my mower?"),
    )
    chat.finish(alice, row["id"], {"text": "The mower is in the shed", "sources": []})
    from test_research_findings import research_turn

    FindingService(MemoryService(engine)).save(
        alice,
        FindingSave(
            request_id="alice-finding",
            turn_id=research_turn(engine, alice, "alice-research"),
            url="https://manufacturer.example/mower-manual",
            asset_id=case.primary,
        ),
    )
    scans = ScanService(engine, registry())
    run = scans.enqueue(alice, "synthetic", {"count": 1}, "alice-scan")
    # Canceled, so the app's own worker leaves it alone during the test.
    scans.cancel(alice, run["id"])
    ScheduleService(scans).create(
        alice,
        ScheduleInput(
            label="Alice mower scan",
            handler_key="synthetic",
            config={"count": 1},
            timezone="UTC",
            cadence="daily",
            local_time="09:00",
            lookback_days=1,
            request_id="alice-schedule",
        ),
    )
    return case


def use_installation(case: Installation, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the app at the fixture's database, files and vault key."""
    monkeypatch.setenv("LIFEGATHER_DATA_DIR", str(case.settings.data_dir))
    monkeypatch.setenv(
        "LIFEGATHER_DATABASE_URL",
        str(case.store.engine.url.render_as_string(hide_password=False)),
    )
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(case.settings.vault_key_file))


def sign_in(client: TestClient, subject: str) -> dict[str, str]:
    store: AuthStore = client.app.state.auth_store  # type: ignore[attr-defined]
    signed = store.login(
        subject, subject + "@example.test", subject.title(), now=int(time.time())
    )
    client.cookies.clear()
    client.cookies.set("lifegather_session", signed.token)
    csrf = client.get("/auth/session").json()["csrf_token"]
    return {"origin": ORIGIN, "x-csrf-token": csrf}


def id_like(name: str) -> bool:
    return name in ID_TABLES or name == "identifier" or name.endswith(("_id", "_ids"))


class Values:
    """Fill identifier slots with one of Alice's ids; everything else validly."""

    def __init__(
        self, schemas: dict[str, Any], alice: dict[str, list[str]], attempt: int
    ) -> None:
        self.schemas = schemas
        self.alice = alice
        self.attempt = attempt
        self.used: set[str] = set()

    def identifier(self, name: str, tables: tuple[str, ...]) -> str:
        ids = [value for table in tables for value in self.alice.get(table, [])]
        # Successive slots get different ids, so pairs name two distinct records.
        value = ids[(self.attempt + len(self.used)) % len(ids)] if ids else "a" * 32
        self.used.add(value)
        return value

    def tables(self, name: str, path: str = "") -> tuple[str, ...]:
        if name == "identifier":
            return next(
                tables
                for prefix, tables in IDENTIFIERS.items()
                if path.startswith(prefix)
            )
        return ID_TABLES[name]

    def make(self, schema: dict[str, Any], name: str = "", depth: int = 0) -> Any:
        if "$ref" in schema:
            schema = self.schemas[schema["$ref"].rsplit("/", 1)[-1]]
        if "const" in schema:
            return schema["const"]
        if "enum" in schema:
            return schema["enum"][0]
        for key in ("anyOf", "oneOf"):
            if key in schema:
                options = [o for o in schema[key] if o.get("type") != "null"]
                return self.make(options[0], name, depth) if options else None
        if "allOf" in schema:
            return self.make(schema["allOf"][0], name, depth)
        kind = schema.get("type")
        if kind == "array":
            item = schema.get("items", {"type": "string"})
            count = max(1, int(schema.get("minItems", 1)))
            if id_like(name) and name in ID_TABLES:
                return [self.identifier(name, ID_TABLES[name]) for _ in range(count)]
            return [self.make(item, name, depth + 1) for _ in range(count)]
        if kind == "object" or "properties" in schema:
            if depth > 6:
                return {}
            required = set(schema.get("required", []))
            return {
                key: self.make(value, key, depth + 1)
                for key, value in schema.get("properties", {}).items()
                if key in required or id_like(key)
            }
        if kind == "string":
            if name in ID_TABLES:
                return self.identifier(name, ID_TABLES[name])
            if name == "timezone":
                return "UTC"
            pattern = re.fullmatch(
                r"\^\[a-f0-9\]\{(\d+)\}\$", schema.get("pattern", "")
            )
            if pattern:
                return "a" * int(pattern.group(1))
            if schema.get("format") == "date":
                return "2026-10-18"
            if schema.get("format") == "date-time":
                return "2026-10-18T09:00:00Z"
            return "x" * max(1, int(schema.get("minLength", 1)))
        if kind in {"integer", "number"}:
            return max(
                int(schema.get("minimum", 1)),
                int(schema.get("exclusiveMinimum", 0)) + 1,
            )
        if kind == "boolean":
            return True
        return "x"


def leaked(
    body: str, alice: dict[str, list[str]], bob: dict[str, list[str]], used: set[str]
) -> list[str]:
    """Alice's markers and ids in a response, except ids the request supplied."""
    shared = {value for ids in bob.values() for value in ids}
    found = [marker for marker in MARKERS if marker.lower() in body.lower()]
    found += [
        value
        for ids in alice.values()
        for value in ids
        if len(value) >= 12
        and value not in used
        and value not in shared
        and value in body
    ]
    return found


def routes(app: Any) -> list[tuple[str, str, dict[str, Any]]]:
    spec = app.openapi()
    return [
        (method.upper(), path, operation)
        for path, operations in spec["paths"].items()
        for method, operation in operations.items()
        if not path.startswith(SKIPPED)
    ]


def test_every_owned_table_has_row_security(tmp_path: Path) -> None:
    store = AuthStore(database(tmp_path))
    store.migrate()
    with store.engine.connect() as connection:
        protected: dict[str, bool] = dict(
            connection.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity AND EXISTS ("
                    "  SELECT FROM pg_policies p WHERE p.tablename = c.relname"
                    "  AND p.policyname = 'account_rows' AND :role = ANY(p.roles))"
                    " FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                    " WHERE n.nspname = 'public' AND c.relkind = 'r'"
                ),
                {"role": ACCOUNT_ROLE},
            ).all()
        )
    owned = owned_tables(store.engine)
    assert len(owned) >= 40
    missing = [name for name in (*owned, "users") if not protected[name]]
    assert missing == [], "add an account_rows policy for: " + ", ".join(missing)
    store.engine.dispose()


def test_row_security_limits_raw_sql_to_the_acting_account(tmp_path: Path) -> None:
    case = installation(tmp_path)
    engine, alice, bob = case.store.engine, case.alice, case.bob
    owned = owned_tables(engine)
    with engine.connect() as connection:
        everyone = {
            table: connection.scalar(text(f"SELECT count(*) FROM {table}"))
            for table in owned
        }
    for actor, other in ((bob, alice), (alice, bob)):
        with account_scope(actor.id), engine.connect() as connection:
            for table in owned:
                # No WHERE clause on the owner: RLS alone limits the rows.
                assert (
                    connection.scalar(
                        text(f"SELECT count(*) FROM {table} WHERE user_id <> :u"),
                        {"u": actor.id},
                    )
                    == 0
                ), table
            assert connection.scalar(text("SELECT count(*) FROM users")) == 1
            assert (
                connection.execute(
                    text(
                        "UPDATE memory_entities SET name = 'taken' WHERE user_id = :o"
                    ),
                    {"o": other.id},
                ).rowcount
                == 0
            )
            assert (
                connection.execute(
                    text("DELETE FROM memory_sources WHERE user_id = :o"),
                    {"o": other.id},
                ).rowcount
                == 0
            )
            connection.rollback()
    assert everyone["memory_entities"] > 0 and everyone["documents"] > 0
    # Writing a row for another account fails the policy check.
    with account_scope(bob.id), Session(engine) as db:
        with pytest.raises(DBAPIError, match="row-level security"):
            db.execute(
                text("UPDATE documents SET user_id = :a WHERE user_id = :b"),
                {"a": alice.id, "b": bob.id},
            )
    # The system context (startup, schedulers, recovery) still sees everyone.
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM users")) == 2
    engine.dispose()


def test_file_storage_refuses_another_accounts_keys(tmp_path: Path) -> None:
    case = installation(tmp_path)
    engine = case.store.engine
    storage = files(engine)
    with engine.connect() as connection:
        key = connection.scalar(
            text("SELECT original_key FROM photos WHERE user_id = :u"),
            {"u": case.alice.id},
        )
    assert key and key.startswith(f"users/{case.alice.id}/")
    with account_scope(case.alice.id):
        assert storage.get(key)
    with account_scope(case.bob.id):
        for attempt in (
            lambda: storage.get(key),
            lambda: storage.exists(key),
            lambda: storage.delete(key),
            lambda: storage.save(b"taken", key),
        ):
            with pytest.raises(StorageError, match="another account"):
                attempt()
    assert storage.get(key)
    engine.dispose()


def test_scan_jobs_run_as_their_owner(tmp_path: Path) -> None:
    case = installation(tmp_path)
    engine, alice, bob = case.store.engine, case.alice, case.bob
    seen: list[tuple[str | None, int]] = []

    class Spy(SyntheticHandler):
        async def step(
            self, context: ScanContext, config: dict[str, Any], cursor: dict[str, Any]
        ) -> ScanBatch:
            with engine.connect() as connection:
                # An unfiltered read inside the job sees only its owner's rows.
                seen.append(
                    (
                        ACTING_ACCOUNT.get(),
                        connection.scalar(
                            text(
                                "SELECT count(*) FROM memory_entities "
                                "WHERE user_id = :a"
                            ),
                            {"a": alice.id},
                        ),
                    )
                )
            return ScanBatch(
                [
                    ScanEvidence(
                        key="0",
                        source=SourceInput(
                            text="Synthetic job evidence",
                            source_type="import",
                            namespace="synthetic-scans",
                            external_id="0",
                        ),
                        label="Synthetic job record",
                    )
                ],
                None,
            )

    scans = ScanService(engine, ScanRegistry([Spy()]))
    run = scans.enqueue(bob, "synthetic", {"count": 1}, "bob-job")
    assert asyncio.run(ScanWorker(scans).run_once())
    assert seen == [(bob.id, 0)]
    assert ACTING_ACCOUNT.get() is None
    assert scans.get(bob, run["id"])["state"] == "completed"
    engine.dispose()


def test_removed_service_filter_is_caught_by_row_security(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = rich_alice(tmp_path)
    use_installation(case, monkeypatch)
    engine = case.store.engine
    with engine.connect() as connection:
        run = connection.scalar(
            text("SELECT id FROM scan_runs WHERE user_id = :u"), {"u": case.alice.id}
        )

    def unfiltered(db: Session, actor: Account, identifier: str) -> ScanRun:
        # The owner condition is deliberately missing.
        row = db.scalar(select(ScanRun).where(ScanRun.id == identifier))
        if row is None:
            raise MemoryError("Scan not found")
        return row

    monkeypatch.setattr(ScanService, "owned", staticmethod(unfiltered))
    # Without RLS (system context) the broken filter really would leak.
    with Session(engine) as db:
        assert unfiltered(db, case.bob, run).user_id == case.alice.id
    engine.dispose()
    with TestClient(create_app()) as client:
        sign_in(client, "bob")
        response = client.get(f"/api/scans/{run}")
        assert response.status_code == 400
        assert response.json() == {"detail": "Scan not found"}
        sign_in(client, "alice")
        assert client.get(f"/api/scans/{run}").status_code == 200


def test_every_identifier_is_mapped() -> None:
    app = create_app()
    unmapped: set[str] = set()
    for _, path, operation in routes(app):
        for parameter in operation.get("parameters", []):
            name = parameter["name"]
            if not id_like(name):
                continue
            if name == "identifier":
                if not any(path.startswith(prefix) for prefix in IDENTIFIERS):
                    unmapped.add(f"{path}:{name}")
            elif name not in ID_TABLES:
                unmapped.add(name)
    schemas = app.openapi()["components"]["schemas"]
    models = list(schemas.values()) + [
        model.model_json_schema() for model in INPUTS.values()
    ]
    for schema in models:
        for name in schema.get("properties", {}):
            if id_like(name) and name not in ID_TABLES:
                unmapped.add(name)
        for nested in schema.get("$defs", {}).values():
            for name in nested.get("properties", {}):
                if id_like(name) and name not in ID_TABLES:
                    unmapped.add(name)
    assert unmapped == set(), "map these identifiers in ID_TABLES: " + str(unmapped)


def test_http_routes_never_cross_accounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = rich_alice(tmp_path)
    use_installation(case, monkeypatch)
    engine = case.store.engine
    alice = identifiers(engine, case.alice.id)
    bob = identifiers(engine, case.bob.id)
    before = snapshot(engine, case.alice.id)
    app = create_app()
    exercised: list[str] = []
    problems: list[str] = []
    with TestClient(app, raise_server_exceptions=False) as client:
        headers = sign_in(client, "bob")
        schemas = app.openapi()["components"]["schemas"]
        for method, path, operation in routes(app):
            slots = [
                (p["name"], Values(schemas, alice, 0).tables(p["name"], path))
                for p in operation.get("parameters", [])
                if p["in"] == "path"
            ]
            attempts = max(
                [1]
                + [
                    min(3, len([i for t in tables for i in alice.get(t, [])]))
                    for _, tables in slots
                ]
            )
            for attempt in range(attempts):
                values = Values(schemas, alice, attempt)
                url = path
                for name, tables in slots:
                    url = url.replace("{" + name + "}", values.identifier(name, tables))
                query = {
                    p["name"]: (
                        values.identifier(p["name"], ID_TABLES[p["name"]])
                        if p["name"] in ID_TABLES
                        else values.make(p.get("schema", {}), p["name"])
                    )
                    for p in operation.get("parameters", [])
                    if p["in"] == "query" and (p.get("required") or id_like(p["name"]))
                }
                content = operation.get("requestBody", {}).get("content", {})
                kwargs: dict[str, Any] = {}
                if "application/json" in content:
                    kwargs["json"] = values.make(content["application/json"]["schema"])
                elif content:
                    kwargs["content"] = b"not a real upload"
                response = client.request(
                    method, url, params=query, headers=headers, **kwargs
                )
                label = f"{method} {url} {json.dumps(kwargs.get('json'))[:200]}"
                # 503 means a provider (Gmail, AI) is not configured here.
                if response.status_code >= 500 and response.status_code != 503:
                    problems.append(f"{response.status_code} {label}")
                if response.status_code != 422:
                    exercised.append(f"{method} {path}")
                found = leaked(response.text, alice, bob, values.used)
                if found:
                    problems.append(f"leaked {found[:3]} via {label}")
        # Control: the same check does flag Alice's own records for Alice.
        sign_in(client, "alice")
        assert leaked(client.get("/api/assets").text, alice, bob, set())
    print(f"HTTP: {len(set(exercised))} of {len(routes(app))} routes past validation")
    assert problems == []
    assert snapshot(engine, case.alice.id) == before
    # Most routes must get past validation, or the suite proves little.
    assert len(set(exercised)) >= 0.8 * len({f"{m} {p}" for m, p, _ in routes(app)})
    engine.dispose()


def test_mcp_tools_never_cross_accounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = rich_alice(tmp_path)
    use_installation(case, monkeypatch)
    engine = case.store.engine
    alice = identifiers(engine, case.alice.id)
    bob = identifiers(engine, case.bob.id)
    before = snapshot(engine, case.alice.id)
    app = create_app()
    problems: list[str] = []
    exercised: list[str] = []
    with TestClient(app, raise_server_exceptions=False) as client:
        headers, _ = signed_headers(app, "bob")
        # The per-account MCP rate limit is tested elsewhere.
        monkeypatch.setattr(app.state.mcp_gate.limiter, "allow", lambda user: True)
        acting: list[str | None] = []
        search = MemoryService.search

        def spy(self: MemoryService, *args: Any) -> Any:
            acting.append(ACTING_ACCOUNT.get())
            return search(self, *args)

        monkeypatch.setattr(MemoryService, "search", spy)
        rpc(client, headers, "memory_search", {"query": "mower"})
        assert acting == [case.bob.id]
        for name, model in INPUTS.items():
            schema = model.model_json_schema()
            for attempt in range(3):
                values = Values(schema.get("$defs", {}), alice, attempt)
                data = values.make(schema)
                response = rpc(client, headers, name, data)
                if response.status_code >= 500:
                    problems.append(f"{response.status_code} {name} {data}")
                if response.status_code == 200:
                    exercised.append(name)

                found = leaked(response.text, alice, bob, values.used)
                if found:
                    problems.append(f"leaked {found[:3]} via {name} {data}")
    print(f"MCP: {len(set(exercised))} of {len(INPUTS)} tools answered")
    assert problems == []
    assert snapshot(engine, case.alice.id) == before
    assert len(set(exercised)) >= 0.8 * len(INPUTS)
    engine.dispose()
