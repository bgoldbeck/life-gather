import time
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx2
import pytest
from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey

import lifegather.main as main
from lifegather.auth.google import GoogleProvider
from lifegather.config import Settings
from lifegather.version import __version__


class GoogleFixture:
    def __init__(self) -> None:
        self.key = RSAKey.generate_key(2048, parameters={"kid": "fixture"})
        self.claims: dict[str, Any] = {}
        self.query: dict[str, list[str]] = {}
        self.token_calls = 0
        self.fail = False
        self.forged = False
        self.omit: list[str] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        if self.fail:
            return httpx2.Response(503)
        if request.url.path.endswith("openid-configuration"):
            return httpx2.Response(
                200,
                json={
                    "issuer": "https://accounts.google.com",
                    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_endpoint": "https://oauth2.googleapis.com/token",
                    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
                    "id_token_signing_alg_values_supported": ["RS256"],
                },
            )
        if request.url.path.endswith("certs"):
            return httpx2.Response(200, json={"keys": [self.key.as_dict()]})
        assert request.url.path == "/token"
        self.token_calls += 1
        form = parse_qs(request.content.decode())
        assert form["redirect_uri"] == ["http://127.0.0.1:8787/auth/google/callback"]
        assert form["code_verifier"]
        claims = {
            "iss": "https://accounts.google.com",
            "aud": "fixture-client",
            "sub": "google-user-one",
            "email": "person@example.test",
            "email_verified": True,
            "name": "Fixture User",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "nonce": self.query["nonce"][0],
            **self.claims,
        }
        for field in self.omit:
            claims.pop(field, None)
        key = RSAKey.generate_key(2048) if self.forged else self.key
        signed = jwt.encode({"alg": "RS256", "kid": "fixture"}, claims, key)
        return httpx2.Response(
            200,
            json={
                "access_token": "fixture-access",
                "token_type": "Bearer",
                "id_token": signed,
            },
        )

    def start(self, client: TestClient) -> str:
        response = client.get("/auth/google/start", follow_redirects=False)
        assert response.status_code == 303
        self.query = parse_qs(urlsplit(response.headers["location"]).query)
        assert self.query["scope"] == ["openid email profile"]
        assert self.query["code_challenge_method"] == ["S256"]
        assert response.headers["cache-control"] == "no-store"
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=lax" in response.headers["set-cookie"]
        return "/auth/google/callback?" + urlencode(
            {
                "code": "fixture-code",
                "state": self.query["state"][0],
            }
        )


@pytest.fixture
def google_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, GoogleFixture]]:
    google = GoogleFixture()
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_ID", "fixture-client")
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_SECRET", "fixture-secret")

    def provider(settings: Settings) -> GoogleProvider:
        return GoogleProvider(settings, httpx2.MockTransport(google.handle))

    monkeypatch.setattr(main, "GoogleProvider", provider)
    with TestClient(main.create_app(), base_url="http://127.0.0.1:8787") as client:
        yield client, google


def test_sign_in_logout_and_protected_identity(
    google_client: tuple[TestClient, GoogleFixture],
) -> None:
    client, google = google_client
    assert client.get("/api/me").status_code == 401
    callback = google.start(client)
    response = client.get(callback, follow_redirects=False)
    assert response.headers["location"] == "/"
    account = client.get("/api/me").json()
    assert account["email"] == "person@example.test"
    assert set(account) == {"id", "email", "name"}
    session = client.get("/auth/session").json()
    token = client.cookies.get("lifegather_session")
    assert token and token not in str(session)
    assert (
        client.get(callback, follow_redirects=False)
        .headers["location"]
        .startswith("/?auth_error=")
    )
    assert google.token_calls == 1
    assert client.post("/auth/logout").status_code == 403
    assert (
        client.post(
            "/auth/logout",
            headers={
                "origin": "https://evil.example",
                "x-csrf-token": session["csrf_token"],
            },
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/auth/logout",
            headers={
                "origin": "http://127.0.0.1:8787",
                "x-csrf-token": session["csrf_token"],
            },
        ).status_code
        == 204
    )
    client.cookies.set("lifegather_session", token)
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://evil.example"},
        {"aud": "wrong-client"},
        {"exp": 1},
        {"iat": int(time.time()) + 3600},
        {"nonce": "wrong"},
        {"email_verified": False},
        {"sub": ""},
    ],
)
def test_invalid_google_claims_fail_closed(
    google_client: tuple[TestClient, GoogleFixture],
    claims: dict[str, Any],
) -> None:
    client, google = google_client
    google.claims = claims
    callback = google.start(client)
    assert (
        "auth_error" in client.get(callback, follow_redirects=False).headers["location"]
    )
    assert client.get("/api/me").status_code == 401


def test_forged_signature_and_bad_state(
    google_client: tuple[TestClient, GoogleFixture],
) -> None:
    client, google = google_client
    callback = google.start(client)
    assert (
        "auth_error"
        in client.get(
            callback.replace("state=", "state=bad"), follow_redirects=False
        ).headers["location"]
    )
    assert google.token_calls == 0
    # Invalid callback clears the browser cookie, so start a new flow.
    callback = google.start(client)
    google.forged = True
    assert (
        "auth_error" in client.get(callback, follow_redirects=False).headers["location"]
    )
    assert client.get("/api/me").status_code == 401


def test_browser_binding_and_provider_failure(
    google_client: tuple[TestClient, GoogleFixture],
) -> None:
    client, google = google_client
    callback = google.start(client)
    client.cookies.clear()
    assert (
        "auth_error" in client.get(callback, follow_redirects=False).headers["location"]
    )
    assert google.token_calls == 0
    callback = google.start(client)
    google.fail = True
    assert (
        "auth_error" in client.get(callback, follow_redirects=False).headers["location"]
    )
    assert client.get("/api/me").status_code == 401


def test_separate_subjects_never_share_an_account(
    google_client: tuple[TestClient, GoogleFixture],
) -> None:
    client, google = google_client
    client.get(google.start(client), follow_redirects=False)
    first_token = client.cookies.get("lifegather_session")
    first = client.get("/api/me").json()
    client.cookies.clear()
    google.claims = {"sub": "google-user-two"}
    client.get(google.start(client), follow_redirects=False)
    second = client.get("/api/me").json()
    assert first["id"] != second["id"]
    client.cookies.clear()
    client.cookies.set("lifegather_session", first_token or "")
    assert client.get("/api/me?user_id=" + second["id"]).json() == first


def test_disabled_configuration_and_origin_validation() -> None:
    with TestClient(main.create_app()) as client:
        assert client.get("/auth/session").json() == {
            "configured": False,
            "test_login_enabled": False,
            "build": {"version": __version__, "revision": None},
            "email_delivery_enabled": False,
            "email_password_enabled": False,
            "user": None,
            "csrf_token": None,
        }
        assert client.get("/auth/google/start").status_code == 503
        assert client.get("/api/me").status_code == 401
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(public_url="http://192.168.1.1:8787")


@pytest.mark.parametrize("field", ["iss", "aud", "sub", "exp", "iat", "nonce"])
def test_missing_required_claim(
    google_client: tuple[TestClient, GoogleFixture], field: str
) -> None:
    client, google = google_client
    google.omit = [field]
    response = client.get(google.start(client), follow_redirects=False)
    assert "auth_error" in response.headers["location"]
    assert client.get("/api/me").status_code == 401


def test_secure_cookies_fixed_callback_and_rate_limit(
    google_client: tuple[TestClient, GoogleFixture], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, google = google_client
    for _ in range(10):
        google.start(client)
    assert client.get("/auth/google/start").status_code == 429
    monkeypatch.setenv("LIFEGATHER_PUBLIC_URL", "https://life.example.test")
    with TestClient(main.create_app(), base_url="https://life.example.test") as secure:
        response = secure.get(
            "/auth/google/start",
            headers={"host": "untrusted.example"},
            follow_redirects=False,
        )
        assert "Secure" in response.headers["set-cookie"]
        query = parse_qs(urlsplit(response.headers["location"]).query)
        assert query["redirect_uri"] == [
            "https://life.example.test/auth/google/callback"
        ]


def test_denied_sign_in_is_consumed(
    google_client: tuple[TestClient, GoogleFixture],
) -> None:
    client, google = google_client
    callback = google.start(client)
    response = client.get(callback + "&error=access_denied", follow_redirects=False)
    assert "auth_error" in response.headers["location"]
    assert client.get("/api/me").status_code == 401
    assert google.token_calls == 0
