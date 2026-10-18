import pytest
from fastapi.testclient import TestClient

from lifegather.auth.store import AuthStore
from lifegather.main import create_app

BASE = "http://127.0.0.1:8787"


def test_test_workspace_is_separate_from_normal_accounts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "true")
    with TestClient(create_app(), base_url=BASE) as client:
        store: AuthStore = client.app.state.auth_store  # type: ignore[attr-defined]
        normal = store.login(
            "normal-user", "normal@example.test", "Normal user", now=2000000000
        )
        client.cookies.set("lifegather_session", normal.token)
        csrf = client.get("/auth/session").json()["csrf_token"]
        assert (
            client.put(
                "/api/settings",
                headers={"origin": BASE, "x-csrf-token": csrf},
                json={"allow_external_ai": True},
            ).status_code
            == 204
        )
        assert (
            client.post(
                "/auth/test-login", headers={"origin": BASE}, json={}
            ).status_code
            == 409
        )
        client.cookies.clear()
        response = client.post("/auth/test-login", headers={"origin": BASE}, json={})
        assert response.status_code == 204
        assert "HttpOnly" in response.headers["set-cookie"]
        assert (
            client.get("/api/me?user_id=" + normal.user.id).json()["id"]
            != normal.user.id
        )
        assert client.get("/api/settings").json()["allow_external_ai"] is False
        test_session = client.get("/auth/session").json()
        test_token = client.cookies["lifegather_session"]
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "false")
    with TestClient(create_app(), base_url=BASE) as client:
        client.cookies.set("lifegather_session", test_token)
        assert (
            client.post(
                "/mcp",
                headers={"origin": BASE, "x-csrf-token": test_session["csrf_token"]},
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            ).status_code
            == 401
        )
        client.cookies.set("lifegather_session", normal.token)
        assert client.get("/api/me").json()["id"] == normal.user.id


def test_test_login_limits_anonymous_session_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "true")
    with TestClient(create_app(), base_url=BASE) as client:
        for _ in range(10):
            client.cookies.clear()
            assert (
                client.post(
                    "/auth/test-login", headers={"origin": BASE}, json={}
                ).status_code
                == 204
            )
        client.cookies.clear()
        assert (
            client.post(
                "/auth/test-login", headers={"origin": BASE}, json={}
            ).status_code
            == 429
        )


def test_test_login_is_disabled_by_default() -> None:
    with TestClient(create_app(), base_url=BASE) as client:
        assert client.get("/auth/session").json()["test_login_enabled"] is False
        assert (
            client.post(
                "/auth/test-login", headers={"origin": BASE}, json={}
            ).status_code
            == 404
        )


def test_opt_in_test_login_reuses_dedicated_workspace_and_disables_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "true")
    with TestClient(create_app(), base_url=BASE) as client:
        assert (
            client.post(
                "/auth/test-login", headers={"origin": BASE}, json={}
            ).status_code
            == 204
        )
        session = client.get("/auth/session").json()
        assert session["user"]["name"] == "Test user"
        assert session["test_login_enabled"] is True
        assert session["email_password_enabled"] is False
        first_id = session["user"]["id"]
        first_token = client.cookies["lifegather_session"]
        assert (
            client.post(
                "/auth/logout",
                headers={"origin": BASE, "x-csrf-token": session["csrf_token"]},
            ).status_code
            == 204
        )
        assert (
            client.post(
                "/auth/test-login", headers={"origin": BASE}, json={}
            ).status_code
            == 204
        )
        assert client.get("/auth/session").json()["user"]["id"] == first_id
        assert client.cookies["lifegather_session"] != first_token
        token = client.cookies["lifegather_session"]
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "false")
    with TestClient(create_app(), base_url=BASE) as disabled:
        disabled.cookies.set("lifegather_session", token)
        assert disabled.get("/auth/session").json()["user"] is None
        assert disabled.get("/api/me").status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"origin": "https://elsewhere.example"},
        {"origin": BASE, "sec-fetch-site": "cross-site"},
    ],
)
def test_test_login_rejects_cross_site_requests(
    monkeypatch: pytest.MonkeyPatch, headers: dict[str, str]
) -> None:
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "true")
    with TestClient(create_app(), base_url=BASE) as client:
        assert (
            client.post("/auth/test-login", headers=headers, json={}).status_code == 403
        )


def test_test_login_cannot_select_another_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "true")
    with TestClient(create_app(), base_url=BASE) as client:
        assert (
            client.post(
                "/auth/test-login",
                headers={"origin": BASE},
                json={"user_id": "someone-else"},
            ).status_code
            == 422
        )
