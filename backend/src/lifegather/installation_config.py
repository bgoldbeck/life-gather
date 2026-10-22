"""Explicit private JSON settings for lossless operator recovery configuration."""

import json
from pathlib import Path
from typing import Any

from pydantic.fields import FieldInfo
from pydantic_settings import PydanticBaseSettingsSource

MAX_CONFIGURATION_BYTES = 65536
INSTALLATION_FIELDS = frozenset(
    {
        "app_name",
        "public_url",
        "google_client_id",
        "google_client_secret",
        "test_login_enabled",
        "smtp_host",
        "smtp_port",
        "smtp_username",
        "smtp_password",
        "smtp_sender",
        "smtp_implicit_tls",
        "data_dir",
        "database_url",
        "vault_key_file",
    }
)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate configuration key")
        result[key] = value
    return result


def read_configuration(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file():
            raise ValueError("Choose a regular configuration file")
        with path.open("rb") as source:
            raw = source.read(MAX_CONFIGURATION_BYTES + 1)
        if len(raw) > MAX_CONFIGURATION_BYTES:
            raise ValueError("Configuration exceeds the size limit")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
        if (
            not isinstance(data, dict)
            or not data.keys() <= INSTALLATION_FIELDS
            or any(
                type(value) not in {str, int, bool, type(None)}
                for value in data.values()
            )
        ):
            raise ValueError("Unsupported configuration settings")
        return data
    except (OSError, ValueError, RecursionError):
        # Configuration values may include secrets. Never propagate parser input.
        raise ValueError(
            "Unable to read the private installation configuration"
        ) from None


class InstallationConfigSource(PydanticBaseSettingsSource):
    def get_field_value(
        self, field: FieldInfo, field_name: str
    ) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        path = self.current_state.get("configuration_file")
        if path is None or path == "":
            return {}
        if not isinstance(path, (str, Path)):
            raise ValueError("Choose a private installation configuration file")
        return read_configuration(Path(path))
