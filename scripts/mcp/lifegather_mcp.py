#!/usr/bin/env python3
"""Standard stdio MCP adapter for LifeGather.

Allows AI assistants (such as Google Antigravity, Claude Desktop, and Cursor)
to connect via Model Context Protocol (MCP) using standard I/O (stdio).
Forwards JSON-RPC requests to the running LifeGather HTTP server.
Uses only the Python standard library so no additional packages are required.
"""

import argparse
import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class LifeGatherBridge:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        parsed = urllib.parse.urlsplit(self.base_url)
        self.host = parsed.netloc
        self.origin = f"{parsed.scheme}://{self.host}"
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.session_token: str = os.environ.get("LIFEGATHER_SESSION", "")
        self.csrf_token: str = ""

    def authenticate(self) -> None:
        """Authenticate with the LifeGather backend if credentials exist."""
        email = os.environ.get("LIFEGATHER_EMAIL", "")
        password = os.environ.get("LIFEGATHER_PASSWORD", "")

        # 1. Direct email and password login
        if email and password:
            data = json.dumps({"email": email, "password": password}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/auth/email/login",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Origin": self.origin,
                    "Host": self.host,
                },
                method="POST",
            )
            try:
                with self.opener.open(req) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    self.csrf_token = body.get("csrf_token", "")
                    return
            except Exception as exc:
                sys.stderr.write(f"LifeGather login warning: {exc}\n")
                sys.stderr.flush()

        # 2. Try test login if enabled
        try:
            req = urllib.request.Request(
                f"{self.base_url}/auth/test",
                data=b"",
                headers={
                    "Origin": self.origin,
                    "Host": self.host,
                },
                method="POST",
            )
            with self.opener.open(req):
                pass

            # Fetch settings to get CSRF token
            req_settings = urllib.request.Request(
                f"{self.base_url}/api/settings",
                headers={
                    "Origin": self.origin,
                    "Host": self.host,
                },
            )
            with self.opener.open(req_settings) as resp:
                self.csrf_token = resp.headers.get("x-csrf-token", "")
        except Exception:
            pass

    def forward(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Forward a JSON-RPC request to the LifeGather /mcp endpoint."""
        method = payload.get("method", "")
        headers = {
            "Content-Type": "application/json",
            "Origin": self.origin,
            "Host": self.host,
            "Accept": "application/json",
            "Mcp-Method": method,
        }
        if self.csrf_token:
            headers["X-CSRF-Token"] = self.csrf_token

        params = payload.get("params", {})
        if method == "tools/call" and isinstance(params, dict) and "name" in params:
            headers["Mcp-Name"] = params["name"]

        if self.session_token:
            headers["Cookie"] = f"lifegather_session={self.session_token}"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/mcp",
            data=data,
            headers=headers,
            method="POST",
        )
        try:
            with self.opener.open(req, timeout=30.0) as resp:
                return json.loads(resp.read().decode("utf-8"))  # type: ignore[no-any-return]
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")[:200]
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {
                    "code": -32603,
                    "message": f"LifeGather returned HTTP {exc.code}: {err_body}",
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {
                    "code": -32603,
                    "message": f"Failed to connect to LifeGather at {self.base_url}: {exc}",
                },
            }


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

    bridge = LifeGatherBridge(args.url)
    try:
        bridge.authenticate()
    except Exception as exc:
        sys.stderr.write(f"LifeGather MCP auth warning: {exc}\n")
        sys.stderr.flush()

    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            request = json.loads(text)
        except json.JSONDecodeError:
            continue

        method = request.get("method")
        req_id = request.get("id")

        if method == "initialize":
            init_response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2026-07-28",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "LifeGather",
                        "version": "0.108.0",
                    },
                },
            }
            sys.stdout.write(json.dumps(init_response) + "\n")
            sys.stdout.flush()
            continue

        if method == "notifications/initialized":
            continue

        response = bridge.forward(request)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
