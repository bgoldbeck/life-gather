#!/usr/bin/env python3
"""Standard stdio MCP adapter for LifeGather.

Allows AI assistants (such as Google Antigravity, Claude Desktop, and Cursor)
to connect via Model Context Protocol (MCP) using standard I/O (stdio).
Forwards JSON-RPC requests to the running LifeGather HTTP server, which
negotiates the protocol version and reports its own name and version.
Uses only the Python standard library so no additional packages are required.

Sign in with LIFEGATHER_EMAIL and LIFEGATHER_PASSWORD (an email-and-password
account), or pass an existing browser session as LIFEGATHER_SESSION. Without
either, every request is answered with an error explaining what to set; the
bridge never falls back to the test workspace.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from http.cookies import CookieError, SimpleCookie
from typing import Any

SESSION_COOKIE = "lifegather_session"

# (method, url, headers, body) -> (status, response headers, response body)
Transport = Callable[
    [str, str, dict[str, str], bytes | None],
    tuple[int, list[tuple[str, str]], bytes],
]


class BridgeError(Exception):
    """A problem the person must fix before the bridge can reach LifeGather."""


def urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None
) -> tuple[int, list[tuple[str, str]], bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            return resp.status, list(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, list(exc.headers.items()), exc.read()


def detail(body: bytes) -> str:
    try:
        value = json.loads(body).get("detail")
    except (ValueError, AttributeError):
        value = None
    text = value if isinstance(value, str) else body.decode("utf-8", "replace")
    return text[:200]


def rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


class LifeGatherBridge:
    def __init__(
        self,
        base_url: str,
        env: Mapping[str, str],
        transport: Transport = urllib_transport,
    ):
        self.base_url = base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(self.base_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"
        self.transport = transport
        self.email = env.get("LIFEGATHER_EMAIL", "")
        self.password = env.get("LIFEGATHER_PASSWORD", "")
        self.session_token = env.get("LIFEGATHER_SESSION", "")
        self.csrf_token = ""
        self.auth_error = ""

    def request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        sent = {"Origin": self.origin, **(headers or {})}
        if self.session_token:
            sent["Cookie"] = f"{SESSION_COOKIE}={self.session_token}"
        try:
            return self.transport(method, self.base_url + path, sent, body)
        except (OSError, ValueError) as exc:
            raise BridgeError(
                f"Failed to connect to LifeGather at {self.base_url}: {exc}"
            ) from exc

    def authenticate(self) -> None:
        """Sign in once at startup; remember why it failed instead of exiting."""
        try:
            self._authenticate()
            self.auth_error = ""
        except BridgeError as exc:
            self.auth_error = str(exc)
            sys.stderr.write(f"LifeGather MCP: {exc}\n")
            sys.stderr.flush()

    def _authenticate(self) -> None:
        if self.email and self.password:
            self.session_token = ""
            status, headers, body = self.request(
                "POST",
                "/auth/email/login",
                json.dumps({"email": self.email, "password": self.password}).encode(),
                {"Content-Type": "application/json"},
            )
            if status != 204:
                raise BridgeError(
                    f"LifeGather sign-in failed (HTTP {status}): {detail(body)}"
                )
            self.session_token = session_from(headers)
            if not self.session_token:
                raise BridgeError("LifeGather sign-in returned no session")
        elif not self.session_token:
            raise BridgeError(
                "Set LIFEGATHER_EMAIL and LIFEGATHER_PASSWORD (or LIFEGATHER_SESSION) "
                "in the MCP server's env to choose the LifeGather account"
            )
        status, _, body = self.request("GET", "/auth/session")
        try:
            session = json.loads(body) if status == 200 else {}
        except ValueError:
            session = {}
        self.csrf_token = session.get("csrf_token") or ""
        if not self.csrf_token:
            raise BridgeError(
                "LifeGather did not accept the session; check the sign-in details"
            )
        terms = session.get("terms")
        if isinstance(terms, dict) and not terms.get("accepted"):
            raise BridgeError(
                "Accept the LifeGather terms in the browser before connecting"
            )

    def handle(self, message: Any) -> dict[str, Any] | None:
        """Return the reply for one message, or None when no reply is allowed."""
        if not isinstance(message, dict):
            return rpc_error(None, -32600, "Invalid Request")
        if "id" not in message:
            # Notifications never get a reply, and the stateless server has
            # nothing to do with them.
            return None
        if self.auth_error:
            return rpc_error(message["id"], -32000, self.auth_error)
        try:
            return self.forward(message)
        except BridgeError as exc:
            return rpc_error(message["id"], -32603, str(exc))

    def forward(self, payload: dict[str, Any], retry: bool = True) -> dict[str, Any]:
        """Forward a JSON-RPC request to the LifeGather /mcp endpoint."""
        method = payload.get("method", "")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-CSRF-Token": self.csrf_token,
        }
        if isinstance(method, str):
            headers["Mcp-Method"] = method
        params = payload.get("params")
        if method == "tools/call" and isinstance(params, dict):
            if isinstance(params.get("name"), str):
                headers["Mcp-Name"] = params["name"]
        status, _, body = self.request(
            "POST", "/mcp", json.dumps(payload).encode(), headers
        )
        if status == 401 and retry and self.email and self.password:
            self._authenticate()
            return self.forward(payload, retry=False)
        try:
            reply = json.loads(body)
        except ValueError:
            reply = None
        if isinstance(reply, dict) and reply.get("jsonrpc") == "2.0":
            return reply
        if status == 401:
            return rpc_error(
                payload["id"],
                -32000,
                "LifeGather session ended; restart the MCP server to sign in again",
            )
        return rpc_error(
            payload["id"], -32603, f"LifeGather returned HTTP {status}: {detail(body)}"
        )


def session_from(headers: list[tuple[str, str]]) -> str:
    for name, value in headers:
        if name.lower() != "set-cookie":
            continue
        cookie: SimpleCookie = SimpleCookie()
        try:
            cookie.load(value)
        except CookieError:
            continue
        if SESSION_COOKIE in cookie:
            return cookie[SESSION_COOKIE].value
    return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LifeGather stdio Model Context Protocol (MCP) bridge."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("LIFEGATHER_URL", "http://127.0.0.1:8787"),
        help="Base URL of the running LifeGather server (default: http://127.0.0.1:8787)",
    )
    args = parser.parse_args()

    bridge = LifeGatherBridge(args.url, os.environ)
    bridge.authenticate()

    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except ValueError:
            response: dict[str, Any] | None = rpc_error(None, -32700, "Parse error")
        else:
            response = bridge.handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
