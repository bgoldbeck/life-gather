"""Bounded Claude Messages adapter; model selection never changes the endpoint."""

import base64
import json
from typing import Any

import httpx2
from pydantic import BaseModel

from lifegather.chat.provider import Completion, ProviderError
from lifegather.chat.streaming import DeltaSink, claude_response


def wire_schema(value: Any) -> Any:
    """Move unsupported constraints to static descriptions, retain local validation.

    Traverse schema nodes, never arbitrary property-name dictionaries: a field
    named 'maximum' is still a field. Personal data never enters schemas.
    """
    if not isinstance(value, dict):
        return value
    unsupported = {
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minLength",
        "maxLength",
        "maxItems",
        "uniqueItems",
    }
    result = dict(value)
    bounds = {}
    for key in unsupported:
        if key in result:
            bounds[key] = result.pop(key)
    if result.get("minItems", 0) not in (0, 1):
        bounds["minItems"] = result.pop("minItems")
    if bounds:
        result["description"] = (
            str(result.get("description", ""))
            + " Constraints: "
            + json.dumps(bounds, sort_keys=True)
        )
    if result.get("type") == "object":
        result["additionalProperties"] = False
    for key in ("properties", "$defs", "definitions"):
        if key in result:
            result[key] = {
                name: wire_schema(child) for name, child in result[key].items()
            }
    for key in ("anyOf", "allOf", "oneOf"):
        if key in result:
            result[key] = [wire_schema(child) for child in result[key]]
    if "items" in result:
        result["items"] = wire_schema(result["items"])
    return result


class ClaudeProvider:
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

    async def _complete(
        self,
        secret: str,
        model: str,
        instruction: str,
        payload: dict[str, Any],
        schema: type[BaseModel],
        emit: DeltaSink | None = None,
    ) -> Completion:
        payload = dict(payload)
        image = payload.pop("_image_jpeg", None)
        text = json.dumps(payload, ensure_ascii=False)
        if len(text.encode()) > 40000:
            raise ProviderError("Context exceeds the chat limit")
        content: list[dict[str, Any]] = []
        if image is not None:
            if (
                not isinstance(image, bytes)
                or not image
                or len(image) > 2 * 1024 * 1024
            ):
                raise ProviderError("Invalid image preview")
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": base64.b64encode(image).decode(),
                    },
                }
            )
        content.append({"type": "text", "text": text})
        try:
            async with httpx2.AsyncClient(
                timeout=25,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": secret, "anthropic-version": "2023-06-01"},
                    json={
                        "model": model,
                        **({"stream": True} if emit else {}),
                        "max_tokens": 1500,
                        "system": instruction,
                        "messages": [{"role": "user", "content": content}],
                        "output_config": {
                            "format": {
                                "type": "json_schema",
                                "schema": wire_schema(schema.model_json_schema()),
                            }
                        },
                    },
                ) as response:
                    if response.status_code != 200:
                        raise ProviderError(
                            "Claude request failed; check access and model"
                        )
                    if emit:
                        data = await claude_response(response, emit)
                    else:
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(raw) + len(chunk) > 131072:
                                raise ProviderError(
                                    "Claude response exceeded the limit"
                                )
                            raw.extend(chunk)
                        data = json.loads(raw)
            if data.get("type") != "message" or data.get("stop_reason") != "end_turn":
                raise ProviderError("Claude did not complete the answer")
            parts = data.get("content", [])
            if not parts or any(part.get("type") != "text" for part in parts):
                raise ProviderError("Unexpected Claude response content")
            parsed = schema.model_validate_json("".join(part["text"] for part in parts))
            usage = data.get("usage", {})
            # Include reported cached inputs without requesting prompt caching.
            inputs = [
                usage.get(name, 0)
                for name in (
                    "input_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                )
            ]
            output = usage.get("output_tokens", 0)
            if any(
                type(n) is not int or not 0 <= n <= 100000 for n in [*inputs, output]
            ):
                raise ProviderError("Invalid provider usage")
            if sum(inputs) > 100000:
                raise ProviderError("Invalid provider usage")
            return Completion(parsed.model_dump(), sum(inputs), output)
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(
                "Claude is unavailable or returned an invalid answer"
            ) from None
