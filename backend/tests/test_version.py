import re
from importlib.metadata import version

import pytest
from fastapi.testclient import TestClient

from lifegather.main import create_app
from lifegather.version import __version__


def test_runtime_version_matches_installed_package() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    assert version("lifegather-backend") == __version__
    with TestClient(create_app()) as client:
        expected = {"version": __version__, "revision": None}
        assert client.get("/api/version").json() == expected
        assert client.get("/auth/session").json()["build"] == expected


def test_release_revision_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIFEGATHER_BUILD_REVISION", "b" * 40)
    with TestClient(create_app()) as client:
        assert client.get("/api/version").json() == {
            "version": __version__,
            "revision": "b" * 40,
        }
