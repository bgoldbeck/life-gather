from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_maintenance import change, plan
from test_mcp_http import signed_headers
from test_purchase_details import WHEN, accepted, body
from test_receipts import choices, extraction
from test_reconciliation import setup

from lifegather.chat.service import SaveText, save_text
from lifegather.insights.service import (
    DashboardRead,
    InsightsService,
    TimelineRead,
    month_keys,
)
from lifegather.main import create_app
from lifegather.maintenance.service import MaintenanceService
from lifegather.memory.service import MemoryService
from lifegather.profiles.service import ProfileCreate, ProfileService
from lifegather.reconciliation.purchase_details import PurchaseDetails
from lifegather.reconciliation.receipts import ReceiptReview, ReceiptService

pytestmark = pytest.mark.usefixtures("configured_database")

TODAY = date(2026, 10, 23)
EURO = "Acme Drill Qty: 2; Line total: EUR 12.00\nAcme Saw Qty: 1"


def second_receipt(engine: Any, actor: Any) -> dict[str, Any]:
    source = save_text(
        MemoryService(engine), actor, SaveText(text=EURO, request_id="euro-source")
    )
    service = ReceiptService(engine)
    draft = service.create(actor, source.id, extraction())
    return service.review(
        actor,
        ReceiptReview(
            receipt_id=draft["id"],
            request_id="euro-confirm",
            choices=choices(service, actor, draft),
        ),
    )


def test_month_keys_span_year_boundaries() -> None:
    assert month_keys(date(2026, 2, 14), 6) == [
        "2025-09",
        "2025-10",
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
    ]
    with pytest.raises(ValidationError):
        DashboardRead(timezone="Mars/Olympus")
    with pytest.raises(ValidationError):
        TimelineRead(month="2026-13")


def test_spending_counts_current_sourced_lines_per_currency_and_owner(
    tmp_path: Path,
) -> None:
    auth, alice, bob, _, _ = setup(tmp_path)
    details = PurchaseDetails(auth.engine)
    receipt = accepted(auth.engine, alice)
    first = details.save(
        alice, body(receipt, request_id="old", purchase_date=None, date_quote=None)
    )
    # Only the current revision counts; the superseded total is history.
    details.save(alice, body(receipt, request_id="new", expected_head=first["id"]))
    # The second line has a stated date but no total.
    details.save(
        alice,
        body(
            receipt,
            index=1,
            request_id="saw",
            line_total=None,
            money_quote=None,
            date_quote=WHEN,
        ),
    )
    euro = second_receipt(auth.engine, alice)
    details.save(
        alice,
        body(
            euro,
            request_id="euro",
            currency="EUR",
            line_total="12.00",
            money_quote="Acme Drill Qty: 2; Line total: EUR 12.00",
            purchase_date=None,
            date_quote=None,
        ),
    )
    service = InsightsService(auth.engine, today=TODAY)
    result = service.dashboard(alice, DashboardRead(months=6))
    assert result["months"][-1] == "2026-10" and len(result["months"]) == 6
    usd, eur = result["spending"]
    assert usd["currency"] == "USD" and usd["total_minor"] == 4990
    assert usd["by_month"][-1] == 4990 and usd["line_count"] == 1
    assert usd["undated_count"] == 0
    assert usd["largest"][0]["name"] == "Drill"
    assert eur["total_minor"] == 0 and eur["by_month"] == [0] * 6
    assert (eur["undated_minor"], eur["undated_count"]) == (1200, 1)
    assert result["missing_total_count"] == 1
    assert result["activity"]["purchase"][-1] == 2
    assert result["truncated"] is False

    # Another account sees none of it.
    other = service.dashboard(bob, DashboardRead(months=6))
    assert other["spending"] == [] and other["activity"]["purchase"] == [0] * 6

    month = service.timeline(alice, TimelineRead(month="2026-10"))
    purchases = [item for item in month["items"] if item["kind"] == "purchase"]
    assert [(item["title"], item["amount_minor"]) for item in purchases] == [
        ("Drill", 4990),
        ("Saw", None),
    ]
    assert purchases[0]["date"] == "2026-10-18"
    assert purchases[0]["date_basis"] == "stated"
    assert purchases[0]["target"] == {"view": "Memories", "id": receipt["source_id"]}
    assert service.timeline(bob, TimelineRead(month="2026-10"))["items"] == []
    only = service.timeline(alice, TimelineRead(month="2026-10", kinds=["asset"]))
    assert {item["kind"] for item in only["items"]} <= {"asset"}
    auth.engine.dispose()


def test_maintenance_due_done_and_upcoming(tmp_path: Path) -> None:
    auth, alice, bob, _, _ = setup(tmp_path)
    vehicle = (
        ProfileService(auth.engine)
        .create(
            alice,
            ProfileCreate(
                name="Synthetic vehicle",
                kind="vehicle",
                text="My synthetic vehicle.",
                operation_key="vehicle",
            ),
        )
        .id
    )
    tasks = MaintenanceService(auth.engine)
    tasks.create(alice, plan(vehicle, due_on="2026-10-30"))
    done = tasks.create(
        alice, plan(vehicle, title="Rotate tires", request_id="tires", due_on=None)
    )
    tasks.revise(
        alice,
        change(
            tasks.get(alice, done["id"]),
            "finish",
            state="completed",
            completed_on="2026-10-02",
        ),
    )
    tasks.create(
        alice, plan(vehicle, title="Wash", request_id="wash", due_on="2026-10-01")
    )
    service = InsightsService(auth.engine, today=TODAY)
    result = service.dashboard(alice, DashboardRead(months=12))
    assert result["activity"]["maintenance_done"][-1] == 1
    assert result["overdue_count"] == 1
    assert [item["title"] for item in result["upcoming"]] == [
        "Wash",
        "Replace cabin filter",
    ]
    assert result["upcoming"][0]["overdue"] is True
    assert result["upcoming"][1]["entity_name"] == "Synthetic vehicle"
    assert service.dashboard(bob, DashboardRead())["upcoming"] == []
    month = service.timeline(alice, TimelineRead(month="2026-10"))
    kinds = [
        (item["kind"], item["date"], item["title"])
        for item in month["items"]
        if item["kind"].startswith("maintenance")
    ]
    assert kinds == [
        ("maintenance_due", "2026-10-30", "Replace cabin filter"),
        ("maintenance_done", "2026-10-02", "Rotate tires"),
        ("maintenance_due", "2026-10-01", "Wash"),
    ]
    assert month["items"][0]["target"]["id"] == vehicle
    auth.engine.dispose()


def test_assets_counted_in_local_months_and_http_guards() -> None:
    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "insights-alice")
        bob, _ = signed_headers(app, "insights-bob")
        accepted(app.state.auth_store.engine, actor)
        assert client.get("/api/insights/dashboard").status_code == 401
        assert (
            client.get(
                "/api/insights/dashboard",
                headers=alice,
                params={"timezone": "Nowhere/City"},
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/insights/dashboard", headers=alice, params={"months": 7}
            ).status_code
            == 422
        )
        mine = client.get(
            "/api/insights/dashboard",
            headers=alice,
            params={"months": 6, "timezone": "America/Los_Angeles"},
        )
        assert mine.status_code == 200, mine.text
        # Two drills are two physical units; the saw is the third.
        assert sum(mine.json()["activity"]["asset"]) == 3
        theirs = client.get("/api/insights/dashboard", headers=bob).json()
        assert sum(theirs["activity"]["asset"]) == 0
        current = mine.json()["months"][-1]
        month = client.get(
            "/api/insights/timeline",
            headers=alice,
            params={"month": current, "kind": ["asset"]},
        )
        assert month.status_code == 200
        assert {item["title"] for item in month.json()["items"]} == {"Drill", "Saw"}
        assert all(item["date_basis"] == "recorded" for item in month.json()["items"])
        assert (
            client.get(
                "/api/insights/timeline", headers=alice, params={"month": "2026-1"}
            ).status_code
            == 422
        )
