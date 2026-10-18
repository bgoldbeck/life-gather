"""Bounded provider SSE decoding and transient structured-answer previews."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import httpx2
from pydantic_core import from_json

DeltaSink = Callable[[str], Awaitable[None]]


async def events(response: httpx2.Response) -> AsyncIterator[dict[str, Any]]:
    pending = bytearray()
    data: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > 524288:
            raise ValueError("Provider stream exceeded limit")
        pending.extend(chunk)
        while b"\n" in pending:
            line, _, remaining = pending.partition(b"\n")
            pending = bytearray(remaining)
            line = line.rstrip(b"\r")
            if not line:
                if data:
                    raw = b"\n".join(data)
                    data = []
                    if raw == b"[DONE]":
                        continue
                    value = json.loads(raw)
                    if not isinstance(value, dict):
                        raise ValueError("Invalid stream event")
                    yield value
            elif line.startswith(b"data:"):
                data.append(bytes(line[5:].lstrip(b" ")))
            if len(pending) + sum(map(len, data)) > 131072:
                raise ValueError("Provider event exceeded limit")
        if len(pending) > 131072:
            raise ValueError("Provider event exceeded limit")
    if pending or data:
        raise ValueError("Incomplete provider event")


async def openai_response(response: httpx2.Response, emit: DeltaSink) -> dict[str, Any]:
    output = ""
    async for event in events(response):
        kind = event.get("type")
        if kind == "response.output_text.delta":
            delta = event["delta"]
            if not isinstance(delta, str) or len(output) + len(delta) > 32768:
                raise ValueError("Invalid answer delta")
            output += delta
            await emit(delta)
        elif kind == "response.completed":
            result: dict[str, Any] = event["response"]
            final = "".join(
                part["text"]
                for item in result.get("output", [])
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            if final != output:
                raise ValueError("Stream answer changed")
            return result
        elif kind in {
            "error",
            "response.failed",
            "response.incomplete",
            "response.refusal.delta",
        }:
            raise ValueError("Provider stream failed")
    raise ValueError("Provider stream did not complete")


async def claude_response(response: httpx2.Response, emit: DeltaSink) -> dict[str, Any]:
    result: dict[str, Any] | None = None
    output = ""
    started = False
    async for event in events(response):
        kind = event.get("type")
        if kind == "message_start":
            if result is not None:
                raise ValueError("Duplicate message")
            result = event["message"]
        elif kind == "content_block_start":
            if (
                started
                or event.get("index") != 0
                or event["content_block"].get("type") != "text"
            ):
                raise ValueError("Unexpected streamed content")
            started = True
            output = event["content_block"].get("text", "")
            if output:
                await emit(output)
        elif kind == "content_block_delta":
            delta = event["delta"]
            if (
                not started
                or event.get("index") != 0
                or delta.get("type") != "text_delta"
            ):
                raise ValueError("Unexpected streamed content")
            text = delta["text"]
            if not isinstance(text, str) or len(output) + len(text) > 32768:
                raise ValueError("Invalid answer delta")
            output += text
            await emit(text)
        elif kind == "message_delta":
            if result is None:
                raise ValueError("Missing stream start")
            result.update(event.get("delta", {}))
            result["usage"] = {**result.get("usage", {}), **event.get("usage", {})}
        elif kind == "message_stop":
            if result is None or not started:
                raise ValueError("Incomplete stream")
            result["content"] = [{"type": "text", "text": output}]
            return result
        elif kind == "error":
            raise ValueError("Provider stream failed")
    raise ValueError("Provider stream did not complete")


class AnswerPreview:
    """Decode only the answer's text; drafts are never trusted or persisted."""

    def __init__(self, emit: DeltaSink) -> None:
        self.emit = emit
        self.raw = ""
        self.text = ""

    async def append(self, delta: str) -> None:
        self.raw += delta
        if len(self.raw) > 32768:
            raise ValueError("Answer exceeded limit")
        try:
            partial = from_json(self.raw, allow_partial="trailing-strings")
        except ValueError:
            return
        text = partial.get("text") if isinstance(partial, dict) else None
        if isinstance(text, str) and text != self.text:
            if len(text) > 6000 or not text.startswith(self.text):
                raise ValueError("Invalid answer preview")
            suffix = text[len(self.text) :]
            self.text = text
            await self.emit(suffix)
