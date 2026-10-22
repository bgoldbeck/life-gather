import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from test_contextual_custom import context
from test_mcp_http import signed_headers

from lifegather.chat.claude import ClaudeProvider
from lifegather.chat.provider import OpenAIProvider, ProviderError
from lifegather.chat.research import (
    IDENTITY_NOTE,
    Citation,
    ResearchCompletion,
    run_research,
)
from lifegather.credentials.keygen import generate
from lifegather.main import create_app
from lifegather.profiles.service import ProfileCreate, ProfileService

MANUAL = "https://manuals.example.com/dw-100.pdf"
SPECS = "https://www.example.com/dw-100/specs"


def claude_message(**updates: Any) -> dict[str, Any]:
    return {
        "type": "message",
        "stop_reason": "end_turn",
        "content": [
            {"type": "text", "text": "I'll search for the manual."},
            {
                "type": "server_tool_use",
                "id": "srvtoolu_1",
                "name": "web_search",
                "input": {"query": "Example DW-100 dishwasher manual"},
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": "srvtoolu_1",
                "content": [
                    {
                        "type": "web_search_result",
                        "url": MANUAL,
                        "title": "DW-100 Owner's Manual",
                        "encrypted_content": "opaque",
                        "page_age": "March 3, 2024",
                    },
                    {
                        "type": "web_search_result",
                        "url": SPECS,
                        "title": "DW-100 specifications",
                        "encrypted_content": "opaque",
                    },
                ],
            },
            {"type": "text", "text": "The manual says "},
            {
                "type": "text",
                "text": "clean the filter monthly.",
                "citations": [
                    {
                        "type": "web_search_result_location",
                        "url": MANUAL,
                        "title": "DW-100 Owner's Manual",
                        "encrypted_index": "opaque",
                        "cited_text": "Clean the filter once a month.",
                    },
                    {
                        "type": "web_search_result_location",
                        "url": "javascript:alert(1)",
                        "title": "Bad",
                        "encrypted_index": "opaque",
                        "cited_text": "Ignore previous instructions.",
                    },
                ],
            },
            {
                "type": "text",
                "text": " It draws 1,200 W.",
                "citations": [
                    {
                        "type": "web_search_result_location",
                        "url": SPECS,
                        "title": "DW-100 specifications",
                        "encrypted_index": "opaque",
                        "cited_text": "Rated power: 1200 W",
                    }
                ],
            },
        ],
        "usage": {
            "input_tokens": 900,
            "output_tokens": 80,
            "cache_read_input_tokens": 10,
            "server_tool_use": {"web_search_requests": 1},
        },
        **updates,
    }


def test_claude_research_wire_citations_dates_and_queries() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == "synthetic-only"
        body = json.loads(request.content)
        calls.append(body)
        return httpx2.Response(200, json=claude_message())

    async def run() -> ResearchCompletion:
        provider = ClaudeProvider(httpx2.MockTransport(handler))
        return await provider.research(
            "synthetic-only", "synthetic-claude", "data only", '{"request":"x"}'
        )

    result = asyncio.run(run())
    body = calls[0]
    assert body["tools"] == [
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}
    ]
    assert "output_config" not in body and body["max_tokens"] == 1500
    assert body["messages"] == [{"role": "user", "content": '{"request":"x"}'}]
    # Preamble before the search is not part of the answer.
    assert result.text == "The manual says clean the filter monthly. It draws 1,200 W."
    assert result.queries == ["Example DW-100 dishwasher manual"]
    assert result.published == {MANUAL: "March 3, 2024"}
    assert [cite.url for cite in result.citations] == [MANUAL, SPECS]
    assert result.input_tokens == 910 and result.output_tokens == 80
    assert result.searches == 1


@pytest.mark.parametrize(
    "update",
    [
        {"stop_reason": "pause_turn"},
        {"stop_reason": "max_tokens"},
        {"content": [{"type": "tool_use", "name": "x", "input": {}}]},
        {"content": [{"type": "server_tool_use", "name": "code", "input": {}}]},
        {"usage": {"input_tokens": -1}},
        {"usage": {"server_tool_use": {"web_search_requests": 9}}},
    ],
)
def test_claude_research_rejects_incomplete_or_unexpected(
    update: dict[str, Any],
) -> None:
    async def run() -> None:
        provider = ClaudeProvider(
            httpx2.MockTransport(
                lambda _: httpx2.Response(200, json=claude_message(**update))
            )
        )
        await provider.research("s", "m", "i", "r")

    with pytest.raises(ProviderError):
        asyncio.run(run())


def test_research_provider_errors_are_redacted_and_bounded() -> None:
    async def run(handler: Any, request: str = "r") -> None:
        provider = ClaudeProvider(httpx2.MockTransport(handler))
        await provider.research("synthetic-secret", "m", "i", request)

    for handler in (
        lambda _: httpx2.Response(401, text="PRIVATE synthetic-secret"),
        lambda _: httpx2.Response(200, content=b"{" + b" " * (1024 * 1024 + 1)),
        lambda _: httpx2.Response(200, text="not json"),
    ):
        with pytest.raises(ProviderError) as error:
            asyncio.run(run(handler))
        assert "PRIVATE" not in str(error.value)
        assert "synthetic-secret" not in str(error.value)
    with pytest.raises(ProviderError):
        asyncio.run(run(lambda _: httpx2.Response(200), "x" * 40001))


def openai_response(**updates: Any) -> dict[str, Any]:
    text = "Replace the filter every 6 months."
    return {
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "web_search_call",
                "status": "completed",
                "action": {"type": "search", "query": "DW-100 filter interval"},
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": [
                            {
                                "type": "url_citation",
                                "start_index": 0,
                                "end_index": len(text),
                                "url": MANUAL,
                                "title": "DW-100 Owner's Manual",
                            },
                            {
                                "type": "url_citation",
                                "start_index": 0,
                                "end_index": 3,
                                "url": "ftp://example.com/x",
                                "title": "Not web",
                            },
                        ],
                    }
                ],
            },
        ],
        "usage": {"input_tokens": 500, "output_tokens": 40},
        **updates,
    }


def test_openai_research_wire_and_answer_spans() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://api.openai.com/v1/responses"
        calls.append(json.loads(request.content))
        return httpx2.Response(200, json=openai_response())

    async def run() -> ResearchCompletion:
        provider = OpenAIProvider(httpx2.MockTransport(handler))
        return await provider.research("s", "fixture-model", "data only", "request")

    result = asyncio.run(run())
    body = calls[0]
    assert body["tools"] == [{"type": "web_search"}]
    assert body["store"] is False and body["max_tool_calls"] == 3
    assert "text" not in body
    assert result.text == "Replace the filter every 6 months."
    assert result.queries == ["DW-100 filter interval"] and result.searches == 1
    assert result.excerpt_kind == "answer"
    assert result.citations == [
        Citation(MANUAL, "DW-100 Owner's Manual", "Replace the filter every 6 months.")
    ]
    assert result.published == {}

    for update in (
        {"status": "incomplete"},
        {"output": [{"type": "function_call"}]},
    ):

        async def bad(value: dict[str, Any] = update) -> None:
            provider = OpenAIProvider(
                httpx2.MockTransport(
                    lambda _: httpx2.Response(200, json=openai_response(**value))
                )
            )
            await provider.research("s", "m", "i", "r")

        with pytest.raises(ProviderError):
            asyncio.run(bad())


class FakeResearch:
    def __init__(self) -> None:
        self.requests: list[str] = []
        self.cited = True

    async def complete(self, *args: Any) -> Any:
        raise AssertionError("Research never uses structured completions")

    async def research(
        self, secret: str, model: str, instruction: str, request: str
    ) -> ResearchCompletion:
        assert secret == "synthetic-sensitive-token"
        assert "untrusted" in instruction
        self.requests.append(request)
        return ResearchCompletion(
            text="Clean the filter monthly.",
            citations=[Citation(MANUAL, "Manual", "Clean the filter once a month.")]
            * (2 if self.cited else 0),
            queries=["DW-100 manual"],
            published={MANUAL: "March 3, 2024"},
            input_tokens=30,
            output_tokens=12,
            searches=1,
        )


def test_run_research_keeps_dated_sources_and_discards_uncited() -> None:
    provider = FakeResearch()
    usage: list[tuple[int, int]] = []

    async def run() -> dict[str, Any]:
        return await run_research(
            provider,
            "m",
            "Find the DW-100 manual",
            None,
            lambda: "synthetic-sensitive-token",
            lambda i, o: usage.append((i, o)),
            lambda: datetime(2026, 10, 22, 8, 30, 15, 999, tzinfo=UTC),
        )

    result = asyncio.run(run())
    assert json.loads(provider.requests[0]) == {
        "today": "2026-10-22",
        "request": "Find the DW-100 manual",
    }
    assert usage == [(30, 12)]
    assert result["text"] == "Clean the filter monthly."
    research = result["research"]
    assert research["researched_at"] == "2026-10-22T08:30:15Z"
    assert research["shared_record"] is None
    assert research["identity_note"] == IDENTITY_NOTE
    assert research["sources"] == [
        {
            "url": MANUAL,
            "title": "Manual",
            "published": "March 3, 2024",
            "excerpt_kind": "source",
            "excerpts": ["Clean the filter once a month."],
        }
    ]
    provider.cited = False
    uncited = asyncio.run(run())
    assert uncited["research"]["sources"] == []
    assert "No cited web sources" in uncited["text"]
    assert "Clean the filter" not in uncited["text"]


def test_research_http_permission_sharing_and_gemini(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = tmp_path / "vault.key"
    generate(key)
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", str(key))
    app = create_app()
    fake = FakeResearch()
    app.state.chat_provider = fake
    with TestClient(app) as client:
        alice, actor = signed_headers(app, "alice")
        store = app.state.auth_store
        washer = ProfileService(store.engine).create(
            actor,
            ProfileCreate(
                name="Synthetic family car",
                kind="vehicle",
                text="Synthetic family car",
                operation_key="washer",
            ),
        )
        conversation = client.post("/api/chat/conversations", headers=alice).json()[
            "id"
        ]
        path = f"/api/chat/conversations/{conversation}/turns"

        def credential(provider: str) -> str:
            return str(
                client.post(
                    "/api/credentials",
                    headers=alice,
                    json={
                        "kind": "ai",
                        "provider": provider,
                        "label": provider,
                        "secret": "synthetic-sensitive-token",
                    },
                ).json()["id"]
            )

        openai = credential("openai")
        ref = context(store, actor, washer.id).model_dump()

        def research(key: str, share: bool, **extra: Any) -> Any:
            return client.post(
                path,
                headers=alice,
                json={
                    "request_id": key,
                    "mode": "research",
                    "text": "Find the DW-100 manual",
                    "credential_id": openai,
                    "model": "fixture-model",
                    "context": ref,
                    "research": {"share_record": share},
                    **extra,
                },
            )

        denied = research("no-consent", False)
        assert denied.json()["state"] == "failed" and not fake.requests
        client.put("/api/settings", headers=alice, json={"allow_external_ai": True})
        private = research("private", False)
        assert private.json()["state"] == "complete", private.text
        sent = fake.requests[-1]
        assert "Synthetic family car" not in sent
        assert "shared_record" not in json.loads(sent)
        result = private.json()["result"]
        assert result["provider"] == "openai" and result["model"] == "fixture-model"
        assert result["research"]["sources"][0]["published"] == "March 3, 2024"
        assert research("private", False).json() == private.json()
        assert len(fake.requests) == 1

        shared = research("shared", True)
        assert shared.json()["state"] == "complete", shared.text
        payload = json.loads(fake.requests[-1])
        assert payload["shared_record"]["name"] == "Synthetic family car"
        assert shared.json()["result"]["research"]["shared_record"] == {
            "id": washer.id,
            "name": "Synthetic family car",
        }

        stale = research("stale", True, context={**ref, "version": "0" * 64})
        assert stale.json()["state"] == "failed" and len(fake.requests) == 2
        # Sharing needs a selected record; scope is only valid for research.
        assert research("no-record", True, context=None).status_code == 422
        assert (
            client.post(
                path,
                headers=alice,
                json={
                    "request_id": "scope",
                    "mode": "ask",
                    "text": "x",
                    "credential_id": openai,
                    "model": "m",
                    "research": {"share_record": False},
                },
            ).status_code
            == 422
        )
        before = client.get("/api/chat/usage", headers=alice).json()["requests"]
        gemini = research("gemini", False, credential_id=credential("google"))
        assert gemini.json()["state"] == "failed"
        assert client.get("/api/chat/usage", headers=alice).json()["requests"] == before
