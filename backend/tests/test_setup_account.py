import sys
import warnings
from getpass import GetPassWarning
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from lifegather import setup_account
from lifegather.auth.email_service import EmailAuth
from lifegather.auth.store import AuthStore
from lifegather.main import create_app

PASSWORD = "a private local testing passphrase!"


def terminal(monkeypatch: pytest.MonkeyPatch, passwords: list[str]) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(
        "builtins.input", Mock(side_effect=["Tester", "test@example.test"])
    )
    monkeypatch.setattr(setup_account, "getpass", Mock(side_effect=passwords))


def test_command_creates_account_in_configured_data_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    terminal(monkeypatch, [PASSWORD, PASSWORD])
    assert setup_account.main([]) == 0
    store = AuthStore(tmp_path / "data" / "auth.sqlite3")
    assert EmailAuth(store, None, "http://127.0.0.1:8787").login(
        "test@example.test", PASSWORD, client="test", now=2000000000
    )
    assert PASSWORD not in str(capsys.readouterr())
    with TestClient(create_app(), base_url="http://127.0.0.1:8787") as client:
        response = client.post(
            "/auth/email/login",
            headers={"origin": "http://127.0.0.1:8787"},
            json={"email": "test@example.test", "password": PASSWORD},
        )
        assert response.status_code == 204
        session = client.get("/auth/session").json()
        assert session["user"]["email"] == "test@example.test"
        assert session["email_delivery_enabled"] is False


def test_command_refuses_noninteractive_password_input(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert setup_account.main([]) == 1
    assert not (tmp_path / "data").exists()


def test_password_mismatch_does_not_create_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    terminal(monkeypatch, [PASSWORD, PASSWORD + "different"])
    assert setup_account.main([]) == 1
    assert not (tmp_path / "data").exists()
    output = str(capsys.readouterr())
    assert "match" in output and PASSWORD not in output


def test_command_refuses_password_echo_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    terminal(monkeypatch, [])

    def unavailable(prompt: str) -> str:
        warnings.warn("cannot hide input", GetPassWarning, stacklevel=1)
        raise AssertionError("Password must not be read after the warning")

    monkeypatch.setattr(setup_account, "getpass", unavailable)
    assert setup_account.main([]) == 1
    assert not (tmp_path / "data").exists()
