"""Bounded MIME text extraction. Attachments and remote resources are never read."""

import base64
from html.parser import HTMLParser
from typing import Any


class PlainHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag in {"p", "br", "div", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def message_text(payload: dict[str, Any]) -> tuple[str, bool]:
    plain: list[str] = []
    html: list[str] = []
    stack = [(payload, 0)]
    visited = 0
    omitted = False
    while stack and visited < 100:
        part, depth = stack.pop()
        visited += 1
        if depth > 10 or part.get("filename"):
            omitted = True
            continue
        body = part.get("body", {})
        if not isinstance(body, dict):
            continue
        if body.get("attachmentId"):
            omitted = True
        data = body.get("data", "")
        kind = part.get("mimeType")
        if (
            isinstance(data, str)
            and data
            and len(data) <= 350000
            and kind in {"text/plain", "text/html"}
        ):
            try:
                decoded = base64.b64decode(
                    data + "=" * (-len(data) % 4), altchars=b"-_", validate=True
                ).decode("utf-8", errors="replace")
            except ValueError:
                omitted = True
                continue
            (plain if kind == "text/plain" else html).append(decoded)
        children = part.get("parts", [])
        if isinstance(children, list):
            stack.extend(
                (child, depth + 1)
                for child in reversed(children[:100])
                if isinstance(child, dict)
            )
    if plain:
        text = "\n".join(plain)
    else:
        parser = PlainHTML()
        parser.feed("\n".join(html))
        text = "".join(parser.parts)
    return text.strip(), omitted or bool(stack)
