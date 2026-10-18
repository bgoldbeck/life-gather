"""Stateless Gemini Interactions adapter; no agents or provider-hosted tools."""

import base64
import json
import re
from typing import Any

import httpx2
from pydantic import BaseModel

from lifegather.chat.provider import Completion, ProviderError
from lifegather.chat.streaming import DeltaSink, events


class GeminiProvider:
    def __init__(self, transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def complete(
        self,
        secret: str,
        model: str,
        instruction: str,
        payload: dict[str, Any],
        schema: type[BaseModel],
    ) -> Completion:
        return await self._complete(secret, model, instruction, payload, schema)

    async def stream_complete(
        self,
        secret: str,
        model: str,
        instruction: str,
        payload: dict[str, Any],
        schema: type[BaseModel],
        emit: DeltaSink,
    ) -> Completion:
        return await self._complete(secret, model, instruction, payload, schema, emit)

    @staticmethod
    async def _stream(response: httpx2.Response, emit: DeltaSink) -> dict[str, Any]:
        steps: dict[int, str] = {}
        stopped: set[int] = set()
        output = ""
        async for event in events(response):
            kind = event.get("event_type")
            if kind == "step.start":
                index = event["index"]
                step = event["step"]["type"]
                if (
                    type(index) is not int
                    or not 0 <= index < 8
                    or index in steps
                    or step not in {"model_output", "thought"}
                ):
                    raise ProviderError("Unexpected Gemini response content")
                if step == "model_output" and "model_output" in steps.values():
                    raise ProviderError("Unexpected Gemini response content")
                steps[index] = step
            elif kind == "step.delta":
                index = event["index"]
                if index not in steps or index in stopped:
                    raise ProviderError("Unexpected Gemini response content")
                if steps[index] == "model_output":
                    delta = event["delta"]
                    text = delta.get("text")
                    if (
                        delta.get("type") != "text"
                        or not isinstance(text, str)
                        or len(output) + len(text) > 32768
                    ):
                        raise ProviderError("Unexpected Gemini answer delta")
                    output += text
                    await emit(text)
            elif kind == "step.stop":
                if event["index"] not in steps:
                    raise ProviderError("Unexpected Gemini response content")
                stopped.add(event["index"])
            elif kind == "interaction.completed":
                if "model_output" not in steps.values() or set(steps) != stopped:
                    raise ProviderError("Gemini stream did not complete")
                result: dict[str, Any] = event["interaction"]
                result["steps"] = [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": output}],
                    }
                ]
                return result
            elif kind == "error":
                raise ProviderError("Gemini stream failed")
        raise ProviderError("Gemini stream did not complete")

    async def _complete(
        self,
        secret: str,
        model: str,
        instruction: str,
        payload: dict[str, Any],
        schema: type[BaseModel],
        emit: DeltaSink | None = None,
    ) -> Completion:
        if len(model) > 100 or not re.fullmatch(r"gemini-[a-zA-Z0-9._:-]+", model):
            raise ProviderError(
                "Choose a Gemini model ID; managed agents are unsupported"
            )
        payload = dict(payload)
        image = payload.pop("_image_jpeg", None)
        text = json.dumps(payload, ensure_ascii=False)
        if len(text.encode()) > 40000:
            raise ProviderError("Context exceeds the chat limit")
        parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
        if image is not None:
            if (
                not isinstance(image, bytes)
                or not image
                or len(image) > 2 * 1024 * 1024
            ):
                raise ProviderError("Invalid image preview")
            parts.append(
                {
                    "type": "image",
                    "data": base64.b64encode(image).decode(),
                    "mime_type": "image/jpeg",
                }
            )
        try:
            async with httpx2.AsyncClient(
                timeout=25,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST",
                    "https://generativelanguage.googleapis.com/v1beta/interactions",
                    headers={"x-goog-api-key": secret},
                    json={
                        "model": model,
                        "input": parts,
                        "system_instruction": instruction,
                        "store": False,
                        "background": False,
                        "tools": [],
                        "generation_config": {"max_output_tokens": 1500},
                        "response_format": {
                            "type": "text",
                            "mime_type": "application/json",
                            "schema": schema.model_json_schema(),
                        },
                        **({"stream": True} if emit else {}),
                    },
                ) as response:
                    if response.status_code != 200:
                        raise ProviderError(
                            "Gemini request failed; check access and model"
                        )
                    if emit:
                        data = await self._stream(response, emit)
                    else:
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw) + len(chunk) > 131072:
                                raise ProviderError(
                                    "Gemini response exceeded the limit"
                                )
                            raw.extend(chunk)
                        data = json.loads(raw)
            if data.get("status") != "completed":
                raise ProviderError("Gemini did not complete the answer")
            steps = data.get("steps", [])
            if len(steps) > 8 or any(
                step.get("type") not in {"thought", "model_output"} for step in steps
            ):
                raise ProviderError("Unexpected Gemini response content")
            outputs = [step for step in steps if step.get("type") == "model_output"]
            if len(outputs) != 1:
                raise ProviderError("Unexpected Gemini response content")
            content = outputs[0].get("content", [])
            if not content or any(part.get("type") != "text" for part in content):
                raise ProviderError("Unexpected Gemini response content")
            parsed = schema.model_validate_json(
                "".join(part["text"] for part in content)
            )
            usage = data.get("usage", {})
            counts = [
                usage.get(key, 0)
                for key in (
                    "total_input_tokens",
                    "total_output_tokens",
                    "total_thought_tokens",
                )
            ]
            if (
                any(type(n) is not int or not 0 <= n <= 100000 for n in counts)
                or sum(counts[1:]) > 100000
            ):
                raise ProviderError("Invalid provider usage")
            return Completion(parsed.model_dump(), counts[0], sum(counts[1:]))
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(
                "Gemini is unavailable or returned an invalid answer"
            ) from None
