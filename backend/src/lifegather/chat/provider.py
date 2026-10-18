"""Bounded OpenAI Responses adapter; no tools, retries, or provider-side state."""

import base64
import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx2
from pydantic import BaseModel, ConfigDict, Field


class SearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=200)


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(min_length=1, max_length=6000)
    source_ids: list[str] = Field(max_length=8)


@dataclass(frozen=True)
class Completion:
    value: dict[str, Any]
    input_tokens: int
    output_tokens: int


class Provider(Protocol):
    async def complete(
        self,
        secret: str,
        model: str,
        instruction: str,
        payload: dict[str, Any],
        schema: type[BaseModel],
    ) -> Completion: ...


class ProviderError(ValueError):
    pass


class OpenAIProvider:
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
        payload = dict(payload)
        image = payload.pop("_image_jpeg", None)
        content = json.dumps(payload, ensure_ascii=False)
        input_value: Any = content
        if image is not None:
            if (
                not isinstance(image, bytes)
                or not image
                or len(image) > 2 * 1024 * 1024
            ):
                raise ProviderError("Invalid image preview")
            input_value = [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": content},
                        {
                            "type": "input_image",
                            "image_url": "data:image/jpeg;base64,"
                            + base64.b64encode(image).decode(),
                            "detail": "high",
                        },
                    ],
                }
            ]
        if len(content.encode()) > 40000:
            raise ProviderError("Context exceeds the chat limit")
        try:
            async with httpx2.AsyncClient(
                timeout=25,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                async with client.stream(
                    "POST",
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": "Bearer " + secret},
                    json={
                        "model": model,
                        "store": False,
                        "max_output_tokens": 1500,
                        "instructions": instruction,
                        "input": input_value,
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": schema.__name__,
                                "strict": True,
                                "schema": schema.model_json_schema(),
                            }
                        },
                    },
                ) as response:
                    if response.status_code != 200:
                        raise ProviderError(
                            "OpenAI request failed; check access and model"
                        )
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(body) + len(chunk) > 131072:
                            raise ProviderError("OpenAI response exceeded the limit")
                        body.extend(chunk)
            data = json.loads(body)
            if data.get("status") != "completed":
                raise ProviderError("OpenAI did not complete the answer")
            output = "".join(
                part["text"]
                for item in data.get("output", [])
                if item.get("type") == "message"
                for part in item.get("content", [])
                if part.get("type") == "output_text"
            )
            parsed = schema.model_validate_json(output)
            usage = data.get("usage", {})
            counts = [usage.get("input_tokens", 0), usage.get("output_tokens", 0)]
            if any(type(n) is not int or not 0 <= n <= 100000 for n in counts):
                raise ProviderError("Invalid provider usage")
            return Completion(parsed.model_dump(), counts[0], counts[1])
        except ProviderError:
            raise
        except Exception:
            raise ProviderError(
                "OpenAI is unavailable or returned an invalid answer"
            ) from None
