"""A proxy that proves LIFEGATHER_PROXY_SECRET may set the visitor's address."""

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from lifegather.config import Settings
from lifegather.main import create_app

SECRET = "s3cret-" + "x" * 32
BASE = "http://127.0.0.1:8787"
PEER = ("10.0.0.5", 50000)


def echo_app() -> object:
    app = create_app()

    def echo(request: Request) -> dict[str, object]:
        return {
            "client": request.client.host if request.client else None,
            "scheme": request.url.scheme,
            "secret_seen": "x-lifegather-proxy-secret" in request.headers,
        }

    app.add_api_route("/echo", echo)
    return app


def headers(**extra: str) -> dict[str, str]:
    return {"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Proto": "https", **extra}


def test_without_a_secret_forwarded_headers_are_ignored() -> None:
    with TestClient(echo_app(), client=PEER) as client:  # type: ignore[arg-type]
        # An empty proof must not match the empty default secret.
        for proof in ({}, {"X-LifeGather-Proxy-Secret": ""}):
            assert client.get("/echo", headers=headers(**proof)).json() == {
                "client": "10.0.0.5",
                "scheme": "http",
                "secret_seen": False,
            }


def test_the_right_secret_sets_client_and_scheme(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_PROXY_SECRET", SECRET)
    with TestClient(echo_app(), client=PEER) as client:  # type: ignore[arg-type]
        proof = {"X-LifeGather-Proxy-Secret": SECRET}
        assert client.get("/echo", headers=headers(**proof)).json() == {
            "client": "203.0.113.9",
            "scheme": "https",
            "secret_seen": False,
        }
        ipv6 = client.get(
            "/echo",
            headers={**proof, "X-Forwarded-For": " 2001:db8::7 "},
        ).json()
        assert ipv6["client"] == "2001:db8::7" and ipv6["scheme"] == "http"


@pytest.mark.parametrize(
    "sent",
    [
        {},
        {"X-LifeGather-Proxy-Secret": "wrong-" + "x" * 33},
        {"X-LifeGather-Proxy-Secret": SECRET[:-1]},
        {"X-LifeGather-Proxy-Secret": SECRET + "x"},
    ],
)
def test_a_missing_or_wrong_secret_is_ignored(
    monkeypatch: pytest.MonkeyPatch, sent: dict[str, str]
) -> None:
    monkeypatch.setenv("LIFEGATHER_PROXY_SECRET", SECRET)
    with TestClient(echo_app(), client=PEER) as client:  # type: ignore[arg-type]
        assert client.get("/echo", headers=headers(**sent)).json() == {
            "client": "10.0.0.5",
            "scheme": "http",
            "secret_seen": False,
        }


def test_a_repeated_secret_header_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_PROXY_SECRET", SECRET)
    with TestClient(echo_app(), client=PEER) as client:  # type: ignore[arg-type]
        sent = [
            ("X-LifeGather-Proxy-Secret", SECRET),
            ("X-LifeGather-Proxy-Secret", SECRET),
            ("X-Forwarded-For", "203.0.113.9"),
        ]
        assert client.get("/echo", headers=sent).json()["client"] == "10.0.0.5"


@pytest.mark.parametrize(
    "address", ["203.0.113.9, 198.51.100.2", "not-an-address", "", "10.0.0.0/8"]
)
def test_only_one_plain_address_is_used(
    monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    monkeypatch.setenv("LIFEGATHER_PROXY_SECRET", SECRET)
    with TestClient(echo_app(), client=PEER) as client:  # type: ignore[arg-type]
        sent = {
            "X-LifeGather-Proxy-Secret": SECRET,
            "X-Forwarded-For": address,
            "X-Forwarded-Proto": "gopher",
        }
        assert client.get("/echo", headers=sent).json() == {
            "client": "10.0.0.5",
            "scheme": "http",
            "secret_seen": False,
        }


def test_trusted_proxies_still_work_alongside_the_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_PROXY_SECRET", SECRET)
    monkeypatch.setenv("LIFEGATHER_TRUSTED_PROXIES", "10.0.0.0/24")
    with TestClient(echo_app(), client=PEER) as client:  # type: ignore[arg-type]
        assert client.get("/echo", headers=headers()).json()["client"] == (
            "203.0.113.9"
        )
    with TestClient(echo_app(), client=("198.51.100.7", 1)) as client:  # type: ignore[arg-type]
        assert client.get("/echo", headers=headers()).json()["client"] == (
            "198.51.100.7"
        )


def test_sign_in_limits_count_each_signed_visitor_separately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "true")
    monkeypatch.setenv("LIFEGATHER_PROXY_SECRET", SECRET)

    def attempt(client: TestClient, visitor: str, proof: str = SECRET) -> int:
        client.cookies.clear()
        return client.post(
            "/auth/test-login",
            headers={
                "origin": BASE,
                "X-LifeGather-Proxy-Secret": proof,
                "X-Forwarded-For": visitor,
            },
            json={},
        ).status_code

    with TestClient(create_app(), base_url=BASE, client=PEER) as client:
        assert [attempt(client, "203.0.113.1") for _ in range(10)] == [204] * 10
        assert attempt(client, "203.0.113.1") == 429
        assert attempt(client, "203.0.113.2") == 204
        # A forged address without the secret counts against the proxy itself.
        assert attempt(client, "203.0.113.3", proof="forged-" + "x" * 32) == 204


@pytest.mark.parametrize("weak", ["short", "x" * 31, "x" * 31 + " ", "é" * 32])
def test_weak_proxy_secrets_are_refused(weak: str) -> None:
    with pytest.raises(ValueError, match="proxy secret"):
        Settings(proxy_secret=SecretStr(weak))
