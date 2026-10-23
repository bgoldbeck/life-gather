import json

import pytest
from fastapi.testclient import TestClient
from test_maintenance import change, plan
from test_mcp_http import META, rpc, signed_headers

from lifegather.main import create_app
from lifegather.profiles.service import ProfileCreate, ProfileService

pytestmark = pytest.mark.usefixtures("configured_database")


def test_private_maintenance_http_and_mcp_share_source_history_and_owner_guards() -> (
    None
):
    app = create_app()
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "maintenance-alice")
        bob, _ = signed_headers(app, "maintenance-bob")
        vehicle = ProfileService(app.state.auth_store.engine).create(
            actor,
            ProfileCreate(
                name="Synthetic private vehicle",
                kind="vehicle",
                text="My synthetic vehicle.",
                operation_key="vehicle",
            ),
        )
        payload = plan(vehicle.id).model_dump(mode="json")
        assert client.get("/api/maintenance").status_code == 401
        assert client.post("/api/maintenance", json=payload).status_code == 401
        assert (
            client.post(
                "/api/maintenance",
                headers={**alice, "X-CSRF-Token": "wrong"},
                json=payload,
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/maintenance", headers=alice, json={**payload, "user_id": actor.id}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/maintenance",
                headers=alice,
                json={**payload, "due_on": 1792450000},
            ).status_code
            == 422
        )
        assert (
            client.post("/api/maintenance", headers=bob, json=payload).status_code
            == 400
        )
        posted = client.post("/api/maintenance", headers=alice, json=payload)
        assert posted.status_code == 200
        assert (
            client.post("/api/maintenance", headers=alice, json=payload).json()
            == posted.json()
        )
        identifier = posted.json()["id"]
        path = f"/api/maintenance/{identifier}"
        current = client.get(path, headers=alice)
        assert (
            current.status_code == 200
            and current.headers["cache-control"] == "no-store"
        )
        assert current.headers["referrer-policy"] == "no-referrer"
        assert client.get(path, headers=bob).status_code == 400
        assert client.get(path + "/history", headers=bob).status_code == 400
        updated = change(
            current.json(), "completed", state="completed", completed_on="2026-10-19"
        ).model_dump(mode="json")
        assert (
            client.post(
                "/api/maintenance/revise",
                headers={**alice, "X-CSRF-Token": "wrong"},
                json=updated,
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/maintenance/revise", headers=bob, json=updated
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/maintenance/revise", headers=alice, json=updated
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/maintenance/revise",
                headers=alice,
                json={**updated, "request_id": "stale"},
            ).status_code
            == 409
        )
        history = client.get(path + "/history", headers=alice).json()["items"]
        assert [row["state"] for row in history] == ["open", "completed"]
        assert history[-1]["origin"]["interface"] == "web"
        assert history[-1]["origin"]["method"] == "correction"
        assert client.get("/api/maintenance", headers=alice).json()["items"] == []
        assert (
            client.get("/api/maintenance?state=completed", headers=alice).json()[
                "items"
            ][0]["id"]
            == identifier
        )

        tools = client.post(
            "/mcp",
            headers=alice,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {"_meta": META},
            },
        ).json()["result"]["tools"]
        for tool in tools:
            if tool["name"].startswith("maintenance_"):
                assert tool["annotations"]["readOnlyHint"] == (
                    tool["name"] not in {"maintenance_create", "maintenance_revise"}
                )
                assert "user_id" not in json.dumps(tool["inputSchema"])
        private = rpc(client, alice, "maintenance_get", {"task_id": identifier}).json()[
            "result"
        ]
        assert private["structuredContent"]["revision"]["completed_on"] == "2026-10-19"
        denied = rpc(client, bob, "maintenance_get", {"task_id": identifier}).json()[
            "result"
        ]
        assert denied["isError"] and "Synthetic private vehicle" not in str(denied)
        assert rpc(client, bob, "maintenance_history", {"task_id": identifier}).json()[
            "result"
        ]["isError"]
        assert (
            rpc(client, bob, "maintenance_list", {}).json()["result"][
                "structuredContent"
            ]["items"]
            == []
        )
        mcp_payload = {**payload, "request_id": "mcp-created", "due_on": None}
        created = rpc(client, alice, "maintenance_create", mcp_payload).json()[
            "result"
        ]["structuredContent"]
        second = rpc(
            client, alice, "maintenance_get", {"task_id": created["id"]}
        ).json()["result"]["structuredContent"]
        correction = change(second, "mcp-revised", state="canceled").model_dump(
            mode="json"
        )
        revised = rpc(client, alice, "maintenance_revise", correction).json()["result"]
        assert not revised.get("isError")
        mcp_history = rpc(
            client, alice, "maintenance_history", {"task_id": created["id"]}
        ).json()["result"]["structuredContent"]["items"]
        assert mcp_history[-1]["state"] == "canceled"
        assert mcp_history[-1]["origin"]["interface"] == "mcp"
