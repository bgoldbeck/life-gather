import json
from pathlib import Path

import pytest

from lifegather.config import Settings
from lifegather.installation_config import MAX_CONFIGURATION_BYTES


@pytest.fixture(autouse=True)
def private_working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)


def test_literal_secrets_and_existing_configuration_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "Synthetic ${DO_NOT_EXPAND}\n雪"
    path = tmp_path / "installation.json"
    path.write_text(
        json.dumps(
            {
                "app_name": "From JSON",
                "google_client_id": "synthetic",
                "google_client_secret": secret,
            }
        ),
        encoding="utf-8",
    )
    for key in (
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "APP_NAME",
        "CONFIGURATION_FILE",
    ):
        monkeypatch.delenv("LIFEGATHER_" + key, raising=False)
    monkeypatch.setenv("DO_NOT_EXPAND", "must not replace a literal secret")
    settings = Settings(configuration_file=path)
    assert settings.app_name == "From JSON"
    assert settings.google_client_secret.get_secret_value() == secret
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f'LIFEGATHER_CONFIGURATION_FILE="{path.as_posix()}"\n'
        "LIFEGATHER_APP_NAME=From dotenv\n",
        encoding="utf-8",
    )
    assert Settings().app_name == "From dotenv"
    monkeypatch.setenv("LIFEGATHER_APP_NAME", "From environment")
    assert Settings().app_name == "From environment"
    assert Settings(app_name="From init").app_name == "From init"


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        '{"app_name":"first","app_name":"second"}',
        '{"build_revision":"SYNTHETIC_SECRET"}',
        '{"google_client_secret":{"nested":"SYNTHETIC_SECRET"}}',
        '{"smtp_port":NaN}',
    ],
)
def test_invalid_file_configuration_has_safe_errors(tmp_path: Path, raw: str) -> None:
    path = tmp_path / "installation.json"
    path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError) as failure:
        Settings(configuration_file=path)
    assert "SYNTHETIC_SECRET" not in str(failure.value)


def test_file_bound_missing_file_and_validation_errors_hide_inputs(
    tmp_path: Path,
) -> None:
    path = tmp_path / "installation.json"
    with pytest.raises(ValueError):
        Settings(configuration_file=path)
    path.write_bytes(b" " * (MAX_CONFIGURATION_BYTES + 1))
    with pytest.raises(ValueError):
        Settings(configuration_file=path)
    path.write_text('{"smtp_port":"SYNTHETIC_SECRET"}', encoding="utf-8")
    with pytest.raises(ValueError) as failure:
        Settings(configuration_file=path)
    assert "SYNTHETIC_SECRET" not in str(failure.value)


@pytest.mark.parametrize("storage", ["data", "public"])
def test_configuration_file_stays_outside_data_and_served_files(
    tmp_path: Path, storage: str
) -> None:
    directory = tmp_path / storage
    directory.mkdir()
    path = directory / "installation.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="configuration must be outside"):
        Settings(
            configuration_file=path,
            data_dir=tmp_path / "data",
            static_dir=tmp_path / "public",
        )
