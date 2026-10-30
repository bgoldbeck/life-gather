import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_mcp_http import signed_headers
from test_setup_account import PASSWORD, terminal

from lifegather import setup_account
from lifegather.main import create_app
from lifegather.version import __version__

pytestmark = pytest.mark.usefixtures("configured_database")

ORIGIN = "http://127.0.0.1:8787"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mcp" / "lifegather_mcp.py"


def load_bridge() -> ModuleType:
    spec = importlib.util.spec_from_file_location("lifegather_mcp_bridge", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge_module = load_bridge()


def transport(client: TestClient, calls: list[str]) -> Any:
    def send(
        method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> tuple[int, list[tuple[str, str]], bytes]:
        calls.append(f"{method} {url}")
        # The bridge must carry the session itself, not rely on a cookie jar.
        client.cookies.clear()
        response = client.request(method, url, headers=headers, content=body)
        return (
            response.status_code,
            list(response.headers.multi_items()),
            response.content,
        )

    return send


def request(request_id: int, method: str, params: dict[str, Any] | None = None) -> Any:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }


def password_account(monkeypatch: pytest.MonkeyPatch) -> None:
    terminal(monkeypatch, [PASSWORD, PASSWORD])
    assert setup_account.main([]) == 0


def test_password_sign_in_lists_tools_and_server_negotiates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_account(monkeypatch)
    app = create_app()
    with TestClient(app) as client:
        bridge = bridge_module.LifeGatherBridge(
            ORIGIN,
            {"LIFEGATHER_EMAIL": "test@example.test", "LIFEGATHER_PASSWORD": PASSWORD},
            transport(client, []),
        )
        bridge.authenticate()
        assert bridge.auth_error == ""
        init = bridge.handle(
            request(
                1,
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "synthetic", "version": "1"},
                },
            )
        )
        assert init["result"]["protocolVersion"] == "2025-06-18"
        assert init["result"]["serverInfo"]["version"] == __version__
        tools = bridge.handle(request(2, "tools/list"))
        assert tools["id"] == 2 and tools["result"]["tools"]
        assert (
            bridge.handle({"jsonrpc": "2.0", "method": "notifications/cancelled"})
            is None
        )


def test_browser_session_token_is_accepted() -> None:
    app = create_app()
    with TestClient(app) as client:
        headers, _ = signed_headers(app, "bridge-session")
        token = headers["Cookie"].split("=", 1)[1]
        bridge = bridge_module.LifeGatherBridge(
            ORIGIN, {"LIFEGATHER_SESSION": token}, transport(client, [])
        )
        bridge.authenticate()
        assert bridge.auth_error == ""
        assert bridge.handle(request(3, "tools/list"))["result"]["tools"]


def test_missing_credentials_never_uses_the_test_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "true")
    app = create_app()
    calls: list[str] = []
    with TestClient(app) as client:
        bridge = bridge_module.LifeGatherBridge(ORIGIN, {}, transport(client, calls))
        bridge.authenticate()
        reply = bridge.handle(request(4, "tools/list"))
    assert calls == []
    assert reply["id"] == 4
    assert "LIFEGATHER_EMAIL" in reply["error"]["message"]


def test_wrong_password_is_reported_on_each_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    password_account(monkeypatch)
    app = create_app()
    with TestClient(app) as client:
        bridge = bridge_module.LifeGatherBridge(
            ORIGIN,
            {"LIFEGATHER_EMAIL": "test@example.test", "LIFEGATHER_PASSWORD": "wrong"},
            transport(client, []),
        )
        bridge.authenticate()
        reply = bridge.handle(request(5, "tools/list"))
    assert "sign-in failed (HTTP 401)" in reply["error"]["message"]
    assert "wrong" not in reply["error"]["message"]


def test_ended_session_signs_in_again(monkeypatch: pytest.MonkeyPatch) -> None:
    password_account(monkeypatch)
    app = create_app()
    calls: list[str] = []
    with TestClient(app) as client:
        bridge = bridge_module.LifeGatherBridge(
            ORIGIN,
            {"LIFEGATHER_EMAIL": "test@example.test", "LIFEGATHER_PASSWORD": PASSWORD},
            transport(client, calls),
        )
        bridge.authenticate()
        app.state.auth_store.logout(bridge.session_token)
        assert bridge.handle(request(6, "tools/list"))["result"]["tools"]
    assert calls.count(f"POST {ORIGIN}/auth/email/login") == 2


def test_stdio_loop_answers_bad_input_and_skips_notifications(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ("LIFEGATHER_EMAIL", "LIFEGATHER_PASSWORD", "LIFEGATHER_SESSION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "argv", ["lifegather_mcp.py", "--url", ORIGIN])
    lines = [
        "not json",
        "[1]",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps(request(7, "tools/list")),
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(lines) + "\n"))
    bridge_module.main()
    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [reply["error"]["code"] for reply in replies] == [-32700, -32600, -32000]
    assert [reply["id"] for reply in replies] == [None, None, 7]
