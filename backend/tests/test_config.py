from pathlib import Path

import pytest

from lifegather.config import Settings
from lifegather.main import create_app

pytestmark = pytest.mark.usefixtures("configured_database")


def test_environment_configures_application_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIFEGATHER_APP_NAME", "LifeGather Local")

    assert create_app().title == "LifeGather Local"


def test_environment_overrides_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("LIFEGATHER_APP_NAME=From file\n", encoding="utf-8")
    monkeypatch.setenv("LIFEGATHER_APP_NAME", "From environment")

    assert Settings().app_name == "From environment"


def test_dotenv_configures_application(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LIFEGATHER_APP_NAME", raising=False)
    (tmp_path / ".env").write_text("LIFEGATHER_APP_NAME=From file\n", encoding="utf-8")

    assert create_app().title == "From file"
