from typing import Any

from fastapi.testclient import TestClient
from test_mcp_http import rpc, signed_headers

from lifegather.main import create_app


def test_http_and_mcp_share_complete_private_typed_asset_workflow() -> None:
    app = create_app()
    with TestClient(app) as client:
        alice, _ = signed_headers(app, "type-alice")
        bob, _ = signed_headers(app, "type-bob")

        def call(name: str, data: dict[str, Any]) -> dict[str, Any]:
            response = rpc(client, alice, name, data)
            assert response.status_code == 200
            result = response.json()["result"]
            assert not result.get("isError"), result
            return result["structuredContent"]  # type: ignore[no-any-return]

        defaults = call("asset_types_list", {})["items"]
        assert len(defaults) == 5
        template = call(
            "asset_type_save",
            {
                "name": "Private synthetic camera",
                "request_id": "type-create",
                "fields": [{"name": "Lens mount"}],
            },
        )
        assert (
            client.get("/api/asset-types/" + template["id"], headers=alice).json()
            == template
        )
        assert (
            client.get("/api/asset-types/" + template["id"], headers=bob).status_code
            == 400
        )
        denied = rpc(client, bob, "asset_type_get", {"type_id": template["id"]}).json()
        assert denied["result"]["isError"] and "Private synthetic camera" not in str(
            denied
        )
        assert (
            client.post(
                "/api/asset-types",
                headers={
                    key: value for key, value in alice.items() if key != "X-CSRF-Token"
                },
                json={"name": "Denied", "request_id": "deny"},
            ).status_code
            == 403
        )
        field = template["fields"][0]
        fields = {
            "name": "Synthetic camera",
            "ownership_confirmed": True,
            "type_id": template["id"],
            "type_revision": template["revision"],
            "type_values": [
                {
                    "field_id": field["id"],
                    "value": "Mount Q",
                    "text": "My camera has Mount Q.",
                }
            ],
        }
        assert call("asset_manual_preview", fields)["candidates"] == []
        body = {**fields, "request_id": "manual"}
        saved = call("asset_manual_save", body)
        assert call("asset_manual_save", body) == saved
        asset_id = saved["asset"]["id"]
        current = call("asset_typed_get", {"entity_id": asset_id})
        fact = current["facts"][0]
        corrected = call(
            "asset_type_field_save",
            {
                "entity_id": asset_id,
                "type_id": template["id"],
                "field_id": field["id"],
                "value": "Mount R",
                "text": "Correction: Mount R.",
                "request_id": "correct",
                "replaces_id": fact["id"],
            },
        )
        assert corrected["value"] == "Mount R"
        updated = call(
            "asset_type_save",
            {
                "type_id": template["id"],
                "expected_revision": template["revision"],
                "name": "Private camera",
                "request_id": "edit",
                "fields": [
                    {**field, "name": "Mount system"},
                    {"name": "Sensor format"},
                ],
            },
        )
        assert call("asset_type_history", {"type_id": template["id"]})["next_cursor"]
        assert call("asset_type_get", {"type_id": template["id"]}) == updated
        typed = client.get("/api/asset-types/assets/" + asset_id, headers=alice).json()
        assert typed["facts"][0]["label"] == "Mount system"
        changed = call(
            "asset_type_assign",
            {
                "entity_id": asset_id,
                "type_id": defaults[2]["id"],
                "replaces_id": typed["assignments"][0]["id"],
                "request_id": "assign",
            },
        )
        assert changed["value"] == defaults[2]["id"]
        assert (
            len(
                call("asset_typed_get", {"entity_id": asset_id, "history": True})[
                    "facts"
                ]
            )
            == 2
        )
        assert (
            client.get("/api/asset-types/assets/" + asset_id, headers=bob).status_code
            == 400
        )
        for tool, data in (
            (
                "asset_type_assign",
                {
                    "entity_id": asset_id,
                    "type_id": defaults[0]["id"],
                    "request_id": "foreign",
                },
            ),
            (
                "asset_type_field_save",
                {
                    "entity_id": asset_id,
                    "type_id": template["id"],
                    "field_id": field["id"],
                    "value": "x",
                    "text": "x",
                    "request_id": "foreign",
                },
            ),
            (
                "asset_type_save",
                {
                    "type_id": template["id"],
                    "expected_revision": updated["revision"],
                    "name": "x",
                    "fields": updated["fields"],
                    "request_id": "foreign",
                },
            ),
        ):
            assert rpc(client, bob, tool, data).json()["result"]["isError"]
