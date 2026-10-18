from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_configuration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIFEGATHER_TEST_LOGIN_ENABLED", "false")
    monkeypatch.setenv("LIFEGATHER_BUILD_REVISION", "")
    monkeypatch.setenv("LIFEGATHER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("LIFEGATHER_GOOGLE_CLIENT_SECRET", "")
    monkeypatch.setenv("LIFEGATHER_PUBLIC_URL", "http://127.0.0.1:8787")
    monkeypatch.setenv("LIFEGATHER_VAULT_KEY_FILE", "")

    for name in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_SENDER"):
        monkeypatch.setenv("LIFEGATHER_" + name, "")
