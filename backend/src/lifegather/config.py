from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LIFEGATHER_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    app_name: str = "LifeGather"
    data_dir: Path = Path("data")
    static_dir: Path | None = None
    public_url: str = "http://127.0.0.1:8787"
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    vault_key_file: Path | None = None

    @field_validator("vault_key_file", mode="before")
    @classmethod
    def empty_key_path(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def google_enabled(self) -> bool:
        return bool(
            self.google_client_id and self.google_client_secret.get_secret_value()
        )

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def google_callback(self) -> str:
        return self.public_url + "/auth/google/callback"

    @model_validator(mode="after")
    def validate_auth(self) -> Self:
        self.public_url = self.public_url.rstrip("/")
        url = urlsplit(self.public_url)
        if (
            url.scheme not in {"https", "http"}
            or not url.hostname
            or url.username
            or url.password
            or url.path
            or url.query
            or url.fragment
        ):
            raise ValueError("public_url must be an HTTP(S) origin without a path")
        if url.scheme == "http" and url.hostname not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError("Use HTTPS except for loopback development")
        if bool(self.google_client_id) != bool(
            self.google_client_secret.get_secret_value()
        ):
            raise ValueError("Configure both Google client ID and secret")
        return self

    @model_validator(mode="after")
    def keep_data_private(self) -> Self:
        if self.static_dir is not None and self.data_dir.resolve().is_relative_to(
            self.static_dir.resolve()
        ):
            raise ValueError("Private data must be outside the static directory")
        if self.vault_key_file is not None:
            key = self.vault_key_file.resolve()
            if key.is_relative_to(self.data_dir.resolve()) or (
                self.static_dir is not None
                and key.is_relative_to(self.static_dir.resolve())
            ):
                raise ValueError(
                    "Vault key must be outside data and static directories"
                )
        return self
