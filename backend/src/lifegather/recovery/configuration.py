"""Explicit complete configuration projection, encrypted with installation data."""

import json
from pathlib import Path
from typing import Any

from pydantic import SecretStr, ValidationError

from lifegather.config import Settings
from lifegather.installation_config import (
    INSTALLATION_FIELDS,
    MAX_CONFIGURATION_BYTES,
    read_configuration,
)
from lifegather.recovery.envelope import RecoveryError

PORTABLE_FIELDS = INSTALLATION_FIELDS - {"data_dir", "vault_key_file"}
LOCAL_FIELDS = {
    "data_dir",
    "vault_key_file",
    "static_dir",
    "configuration_file",
    "build_revision",
}
BOOLEAN_FIELDS = {"test_login_enabled", "smtp_implicit_tls"}


def encode_configuration(values: dict[str, Any]) -> bytes:
    raw = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_CONFIGURATION_BYTES:
        raise RecoveryError("Installation configuration exceeds the recovery limit")
    return raw


def capture_configuration(settings: Settings) -> dict[str, Any]:
    # New settings require an explicit privacy/completeness review, not automatic
    # environment capture or silent loss in a supposedly complete backup.
    if set(Settings.model_fields) - LOCAL_FIELDS != PORTABLE_FIELDS:
        raise RecoveryError("Installation settings need a recovery format review")
    values = {}
    for name in sorted(PORTABLE_FIELDS):
        value = getattr(settings, name)
        values[name] = (
            value.get_secret_value() if isinstance(value, SecretStr) else value
        )
    encode_configuration(values)
    return values


def validate_configuration(path: Path, root: Path, has_key: bool) -> dict[str, Any]:
    try:
        values = read_configuration(path)
        if values.keys() != PORTABLE_FIELDS:
            raise RecoveryError("Recovery configuration is incomplete")
        for name, value in values.items():
            expected = (
                bool if name in BOOLEAN_FIELDS else int if name == "smtp_port" else str
            )
            if type(value) is not expected:
                raise RecoveryError("Recovery configuration has an invalid setting")
        arguments: dict[str, Any] = {
            **values,
            "_env_file": None,
            "configuration_file": None,
            "data_dir": root / "data",
            "vault_key_file": root / "secrets" / "vault.key" if has_key else None,
            "static_dir": None,
            "build_revision": "",
        }
        # Every model field is supplied, so the operator's ambient settings cannot
        # change validation of the configuration stored inside the encrypted file.
        validated = Settings(**arguments)
        return capture_configuration(validated)
    except RecoveryError:
        raise
    except (ValueError, ValidationError):
        raise RecoveryError("Unable to validate recovery configuration") from None


def restored_configuration(values: dict[str, Any], root: Path, has_key: bool) -> bytes:
    return encode_configuration(
        {
            **values,
            "data_dir": str((root / "data").resolve()),
            "vault_key_file": str((root / "secrets" / "vault.key").resolve())
            if has_key
            else None,
        }
    )
