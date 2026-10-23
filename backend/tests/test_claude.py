import asyncio
import json
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from test_chat import send
from test_mcp_http import signed_headers
from test_photos import image_bytes, reading

from lifegather.chat.claude import ClaudeProvider, wire_schema
from lifegather.chat.provider import Completion, ProviderError, SearchPlan
from lifegather.chat.recall import RecallPlan
from lifegather.chat.runner import PhotoReading
from lifegather.credentials.keygen import generate
from lifegather.main import create_app

pytestmark = pytest.mark.usefixtures("configured_database")


def message(value: dict[str, Any], **updates: Any) -> dict[str, Any]:
    return {
        "type": "message",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": json.dumps(value)}],
        "usage": {"input_tokens": 11, "output_tokens": 7, "cache_read_input_tokens": 3},
        **updates,
    }


def test_claude_wire_strict_json_vision_and_no_tools() -> None:
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == "synthetic-only"
        assert request.headers["anthropic-version"] == "2023-06-01"
        body = json.loads(request.content)
        calls.append(body)
        assert body["max_tokens"] == 1500
        assert not {"tools", "store", "cache_control", "metadata"} & body.keys()
        assert body["model"] == "synthetic-claude"
        assert body["output_config"]["format"]["type"] == "json_schema"
        schema = body["output_config"]["format"]["schema"]
        assert schema["additionalProperties"] is False
        assert '"maxLength":' not in json.dumps(schema)
        content = body["messages"][0]["content"]
        if len(content) == 2:
            assert content[0]["type"] == "image"
            assert content[0]["source"]["type"] == "base64"
            assert content[0]["source"]["media_type"] == "image/jpeg"
            assert "_image_jpeg" not in content[1]["text"]
            return httpx2.Response(200, json=message(reading()))
        return httpx2.Response(200, json=message({"query": "filter"}))

    async def run() -> None:
        provider = ClaudeProvider(httpx2.MockTransport(handler))
        plan = await provider.complete(
            "synthetic-only",
            "synthetic-claude",
            "data only",
            {"question": "filter"},
            SearchPlan,
        )
        assert plan.value == {"query": "filter"}
        assert plan.input_tokens == 14 and plan.output_tokens == 7
        from lifegather.photos.service import decode

        image = await provider.complete(
            "synthetic-only",
            "synthetic-claude",
            "data only",
            {"_image_jpeg": decode(image_bytes()).preview},
            PhotoReading,
        )
        assert image.value == reading()
        with pytest.raises(ProviderError):
            await provider.complete(
                "synthetic-only", "test", "safe", {"text": "x" * 40001}, SearchPlan
            )
        with pytest.raises(ProviderError):
            await provider.complete(
                "synthetic-only",
                "test",
                "safe",
                {"_image_jpeg": b"x" * (2 * 1024 * 1024 + 1)},
                PhotoReading,
            )

    asyncio.run(run())
    assert len(calls) == 2


@pytest.mark.parametrize(
    "case",
    [
        "refusal",
        "truncated",
        "tool",
        "malformed",
        "bounds",
        "huge",
        "redirect",
        "error",
        "usage",
        "exception",
    ],
)
def test_claude_failures_are_redacted_bounded_and_not_retried(case: str) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        if case == "exception":
            raise httpx2.ConnectError("synthetic-only PRIVATE", request=request)
        if case == "huge":
            return httpx2.Response(200, content=b"x" * 131073)
        if case == "redirect":
            return httpx2.Response(
                302, headers={"Location": "https://other.invalid/PRIVATE"}
            )
        if case == "error":
            return httpx2.Response(403, json={"error": "synthetic-only PRIVATE"})
        if case == "malformed":
            return httpx2.Response(200, content=b"PRIVATE")
        result = message({"query": "filter"})
        if case == "refusal":
            result["stop_reason"] = "refusal"
        if case == "truncated":
            result["stop_reason"] = "max_tokens"
        if case == "tool":
            result["content"] = [{"type": "tool_use", "name": "PRIVATE"}]
        if case == "bounds":
            result = message({"query": "x" * 201})
        if case == "usage":
            result["usage"] = {"input_tokens": True}
        return httpx2.Response(200, json=result)

    async def run() -> None:
        with pytest.raises(ProviderError) as caught:
            await ClaudeProvider(httpx2.MockTransport(handler)).complete(
                "synthetic-only", "test", "safe", {}, SearchPlan
            )
        assert "PRIVATE" not in str(caught.value) and "synthetic-only" not in str(
            caught.value
        )

    asyncio.run(run())
    assert calls == 1


def test_schema_transform_preserves_property_names_and_local_bounds() -> None:
    transformed = wire_schema(
        {
            "type": "object",
            "properties": {
                "maximum": {"type": "string", "minLength": 1, "maxLength": 10},
                "items": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 5},
                    "maxItems": 2,
                },
            },
        }
    )
    assert transformed["properties"]["maximum"]["type"] == "string"
    assert "maxLength" not in transformed["properties"]["maximum"]
    assert "10" in transformed["properties"]["maximum"]["description"]
    assert transformed["properties"]["items"]["items"]["type"] == "integer"


def test_provider_selection_shared_memory_consent_usage_isolation_and_photo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = tmp_path / "key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()

    class Fake:
        def __init__(self, expected_secret: str) -> None:
            self.expected_secret = expected_secret
            self.calls: list[dict[str, Any]] = []
            self.bad_citation = False

        async def complete(
            self,
            secret: str,
            model: str,
            instruction: str,
            payload: dict[str, Any],
            schema: type[BaseModel],
        ) -> Completion:
            assert secret == self.expected_secret
            self.calls.append(payload)
            if schema is RecallPlan:
                return Completion(
                    {
                        "query": "filter",
                        "entity_names": [],
                        "include_connections": False,
                    },
                    10,
                    5,
                )
            if schema is SearchPlan:
                return Completion({"query": "filter"}, 5, 2)
            if schema is PhotoReading:
                return Completion(reading(), 5, 2)
            return Completion(
                {
                    "text": "The note says 16x25x1.",
                    "source_ids": ["foreign"]
                    if self.bad_citation
                    else [payload["evidence"][0]["id"]],
                },
                5,
                2,
            )

    openai = Fake("synthetic-openai")
    claude = Fake("synthetic-claude")
    app.state.chat_provider = openai
    app.state.claude_provider = claude
    with TestClient(app) as client:
        alice, _ = signed_headers(app, "alice")
        bob, _ = signed_headers(app, "bob")
        credentials = {}
        for provider in ("openai", "anthropic", "unsupported"):
            credentials[provider] = client.post(
                "/api/credentials",
                headers=alice,
                json={
                    "kind": "ai",
                    "provider": provider,
                    "label": "Synthetic",
                    "secret": "synthetic-claude"
                    if provider == "anthropic"
                    else "synthetic-openai",
                },
            ).json()["id"]
        conversation = client.post("/api/chat/conversations", headers=alice).json()[
            "id"
        ]
        send(client, alice, conversation, "save", "save", "My filter is 16x25x1")
        params = {
            "credential_id": credentials["anthropic"],
            "model": "synthetic-claude",
        }
        assert (
            send(
                client, alice, conversation, "denied", "ask", "filter", **params
            ).json()["state"]
            == "failed"
        )
        assert not claude.calls and not openai.calls
        client.put("/api/settings", headers=alice, json={"allow_external_ai": True})
        answered = send(
            client, alice, conversation, "claude", "ask", "filter", **params
        ).json()
        assert (
            answered["state"] == "complete"
            and answered["result"]["provider"] == "anthropic"
        )
        assert len(claude.calls) == 2 and not openai.calls
        assert (
            send(
                client, alice, conversation, "claude", "ask", "filter", **params
            ).json()
            == answered
        )
        other = {"credential_id": credentials["openai"], "model": "synthetic-openai"}
        assert (
            send(
                client, alice, conversation, "openai", "ask", "filter", **other
            ).json()["state"]
            == "complete"
        )
        assert len(openai.calls) == 2
        assert (
            claude.calls[-1]["evidence"][0]["text"]
            == openai.calls[-1]["evidence"][0]["text"]
        )
        denied = send(
            client,
            alice,
            conversation,
            "unsupported",
            "ask",
            "filter",
            credential_id=credentials["unsupported"],
            model="anything",
        )
        assert (
            denied.json()["state"] == "failed"
            and len(openai.calls) == 2
            and len(claude.calls) == 2
        )
        bob_chat = client.post("/api/chat/conversations", headers=bob).json()["id"]
        client.put("/api/settings", headers=bob, json={"allow_external_ai": True})
        assert (
            send(client, bob, bob_chat, "cross-user", "ask", "filter", **params).json()[
                "state"
            ]
            == "failed"
        )
        claude.bad_citation = True
        assert (
            send(
                client, alice, conversation, "bad-citation", "ask", "filter", **params
            ).json()["state"]
            == "failed"
        )
        assert len(claude.calls) == 4
        photo = client.post(
            "/api/photos",
            headers={**alice, "X-File-Name": "synthetic.jpg"},
            content=image_bytes(),
        ).json()
        vision = send(
            client,
            alice,
            conversation,
            "vision",
            "extract_photo",
            "Read photo",
            photo_id=photo["id"],
            **params,
        ).json()
        assert (
            vision["state"] == "complete"
            and vision["result"]["provider"] == "anthropic"
        )
        assert len(claude.calls) == 5 and len(openai.calls) == 2
        assert client.get("/api/chat/usage", headers=alice).json()["requests"] == 4
