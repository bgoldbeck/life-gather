"""The Cloudflare test-site Worker passes only settings this app understands."""

import json
from pathlib import Path

import pytest

from lifegather.config import Settings

SETTINGS_FILE = (
    Path(__file__).resolve().parents[2] / "deploy/cloudflare/container-settings.json"
)
PREFIX = "LIFEGATHER_"


def worker_settings() -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = json.loads(SETTINGS_FILE.read_text("utf-8"))
    return data


def test_every_container_setting_is_a_real_setting() -> None:
    data = worker_settings()
    names = [*data["fixed"], *data["required"], *data["optional"]]
    assert len(names) == len(set(names))
    for name in names:
        assert name.startswith(PREFIX)
        assert name.removeprefix(PREFIX).lower() in Settings.model_fields, name


def test_worker_settings_pass_app_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    data = worker_settings()
    sample = {
        "PUBLIC_URL": "https://lifegather-test.example.workers.dev",
        "DATABASE_URL": "postgresql://user:pw@db.example/lifegather?sslmode=require",
        "VAULT_KEYS": "test:" + "A" * 43 + "=",
        "JOB_TICK_TOKEN": "0123456789abcdef" * 4,
        "R2_BUCKET": "lifegather-test-files",
        "R2_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
        "R2_ACCESS_KEY_ID": "synthetic-id",
        "R2_SECRET_ACCESS_KEY": "synthetic-secret",
    }
    assert set(sample) == set(data["required"].values())
    for name, value in data["fixed"].items():
        monkeypatch.setenv(name, value)
    for name, source in data["required"].items():
        monkeypatch.setenv(name, sample[source])

    settings = Settings()

    assert settings.background_mode == "external"
    assert settings.tick_endpoint_enabled
    assert settings.storage_backend == "s3"
    assert settings.migrate_on_start
    assert settings.trusted_proxy_list == []
