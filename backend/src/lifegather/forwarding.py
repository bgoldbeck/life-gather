"""Forwarded client address and scheme from a proxy that proves a shared secret.

Some platforms (such as a Cloudflare Worker in front of a container) connect from
addresses that cannot be listed in LIFEGATHER_TRUSTED_PROXIES. The proxy instead
sends the configured secret in SECRET_HEADER; only then are its single
X-Forwarded-For address and X-Forwarded-Proto scheme used.
"""

import hmac
import ipaddress

from starlette.types import ASGIApp, Receive, Scope, Send

SECRET_HEADER = b"x-lifegather-proxy-secret"
SCHEMES = {"http": ("http", "ws"), "https": ("https", "wss")}


class SignedProxyHeaders:
    def __init__(self, app: ASGIApp, secret: str) -> None:
        self.app = app
        self.secret = secret.encode("ascii")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        proof: list[bytes] = []
        headers: list[tuple[bytes, bytes]] = []
        for name, value in scope["headers"]:
            if name.lower() == SECRET_HEADER:
                proof.append(value)
            else:
                headers.append((name, value))
        # The secret never reaches the app, its logs or its error pages.
        scope = {**scope, "headers": headers}
        # An empty secret (the default) never matches, even an empty header.
        if (
            self.secret
            and len(proof) == 1
            and hmac.compare_digest(proof[0], self.secret)
        ):
            scope = forwarded(scope, headers)
        await self.app(scope, receive, send)


def forwarded(scope: Scope, headers: list[tuple[bytes, bytes]]) -> Scope:
    values: dict[bytes, list[bytes]] = {}
    for name, value in headers:
        values.setdefault(name.lower(), []).append(value)
    clients = values.get(b"x-forwarded-for", [])
    if len(clients) == 1:
        try:
            # One plain address only: a list means the proxy did not replace it.
            client = str(ipaddress.ip_address(clients[0].decode("ascii").strip()))
        except (UnicodeDecodeError, ValueError):
            pass
        else:
            scope = {**scope, "client": (client, 0)}
    schemes = values.get(b"x-forwarded-proto", [])
    if len(schemes) == 1:
        choice = SCHEMES.get(schemes[0].decode("latin-1").strip().lower())
        if choice:
            scope = {**scope, "scheme": choice[scope["type"] == "websocket"]}
    return scope
