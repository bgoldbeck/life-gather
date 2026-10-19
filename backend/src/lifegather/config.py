from pathlib import Path
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from lifegather.installation_config import InstallationConfigSource


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LIFEGATHER_",
        env_file=".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )

    app_name: str = "LifeGather"
    build_revision: str = Field(default="", pattern=r"^(?:[0-9a-f]{40})?$")
    data_dir: Path = Path("data")
    static_dir: Path | None = None
    public_url: str = "http://127.0.0.1:8787"
    google_client_id: str = ""
    test_login_enabled: bool = False
    google_client_secret: SecretStr = SecretStr("")
    vault_key_file: Path | None = None
    configuration_file: Path | None = None
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_sender: str = ""
    smtp_implicit_tls: bool = False

    @property
    def mail_enabled(self) -> bool:
        return bool(
            self.smtp_host
            and self.smtp_username
            and self.smtp_password.get_secret_value()
            and self.smtp_sender
        )

    @model_validator(mode="after")
    def validate_mail(self) -> Self:
        supplied = [
            bool(self.smtp_host),
            bool(self.smtp_username),
            bool(self.smtp_password.get_secret_value()),
            bool(self.smtp_sender),
        ]
        if any(supplied) and not all(supplied):
            raise ValueError(
                "Configure SMTP host, username, password and sender together"
            )
        if self.smtp_sender:
            from lifegather.auth.email_validation import email_key

            self.smtp_sender = email_key(self.smtp_sender)
        if any(c in self.smtp_host + self.smtp_username for c in "\r\n"):
            raise ValueError("Invalid SMTP configuration")
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            InstallationConfigSource(settings_cls),
            file_secret_settings,
        )

    @field_validator("vault_key_file", "configuration_file", mode="before")
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
        if self.configuration_file is not None:
            configuration = self.configuration_file.resolve()
            if configuration.is_relative_to(self.data_dir.resolve()) or (
                self.static_dir is not None
                and configuration.is_relative_to(self.static_dir.resolve())
            ):
                raise ValueError(
                    "Installation configuration must be outside "
                    "data and static directories"
                )
        return self
