import ipaddress
from pathlib import Path
from typing import Literal, Self
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
    database_url: SecretStr = SecretStr("")
    static_dir: Path | None = None
    public_url: str = "http://127.0.0.1:8787"
    google_client_id: str = ""
    test_login_enabled: bool = False
    google_client_secret: SecretStr = SecretStr("")
    vault_key_file: Path | None = None
    # "id:base64key[,id:base64key...]"; the first key is active, others previous.
    vault_keys: SecretStr = SecretStr("")
    # Comma-separated IP addresses or CIDR networks allowed to set X-Forwarded-*.
    trusted_proxies: str = ""
    migrate_on_start: bool = True
    # "external" runs scheduled scans only from POST /internal/jobs/tick or
    # python -m lifegather.jobs; "inprocess" keeps the built-in loop.
    background_mode: Literal["inprocess", "external"] = "inprocess"
    job_tick_token: SecretStr = SecretStr("")
    configuration_file: Path | None = None
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_sender: str = ""
    smtp_implicit_tls: bool = False
    storage_backend: Literal["local", "s3"] = "local"
    storage_dir: Path | None = None
    s3_bucket: str = ""
    s3_prefix: str = ""
    s3_endpoint_url: str = ""
    s3_region: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: SecretStr = SecretStr("")
    # Comma-separated account emails that may open the Operations page.
    operator_emails: str = ""
    # Optional HTTPS URL that receives a JSON alert for new installation errors.
    alert_webhook_url: str = ""

    @property
    def operator_email_set(self) -> frozenset[str]:
        return frozenset(
            part.strip().casefold()
            for part in self.operator_emails.split(",")
            if part.strip()
        )

    @field_validator("alert_webhook_url")
    @classmethod
    def https_webhook(cls, value: str) -> str:
        value = value.strip()
        if value:
            url = urlsplit(value)
            if url.scheme != "https" or not url.hostname or url.username:
                raise ValueError("The alert webhook must be an HTTPS URL")
        return value

    @property
    def trusted_proxy_list(self) -> list[str]:
        return [
            part.strip() for part in self.trusted_proxies.split(",") if part.strip()
        ]

    @field_validator("trusted_proxies")
    @classmethod
    def valid_proxies(cls, value: str) -> str:
        for part in value.split(","):
            if part.strip():
                try:
                    ipaddress.ip_network(part.strip(), strict=False)
                except ValueError:
                    raise ValueError(
                        "Trusted proxies must be IP addresses or CIDR networks"
                    ) from None
        return value

    @field_validator("job_tick_token")
    @classmethod
    def strong_tick_token(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if raw and (len(raw) < 32 or not all("!" <= c <= "~" for c in raw)):
            raise ValueError("The job tick token must be 32+ visible ASCII characters")
        return value

    @property
    def tick_endpoint_enabled(self) -> bool:
        return self.background_mode == "external" and bool(
            self.job_tick_token.get_secret_value()
        )

    @property
    def files_dir(self) -> Path:
        """Local original-file directory; inside the data mount by default."""
        return self.storage_dir or self.data_dir / "files"

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

    @model_validator(mode="after")
    def validate_storage(self) -> Self:
        if self.storage_backend == "s3":
            if not self.s3_bucket:
                raise ValueError("Configure LIFEGATHER_S3_BUCKET for S3 storage")
            if bool(self.s3_access_key_id) != bool(
                self.s3_secret_access_key.get_secret_value()
            ):
                raise ValueError("Configure both S3 access key ID and secret")
            if self.s3_endpoint_url and not self.s3_endpoint_url.startswith("https://"):
                url = urlsplit(self.s3_endpoint_url)
                if url.scheme != "http" or url.hostname not in {
                    "localhost",
                    "127.0.0.1",
                    "::1",
                }:
                    raise ValueError("Use an HTTPS S3 endpoint except on loopback")
        return self

    @field_validator("database_url")
    @classmethod
    def postgresql_url(cls, value: SecretStr) -> SecretStr:
        from lifegather.database import database_url

        raw = value.get_secret_value()
        return SecretStr(database_url(raw)) if raw.strip() else value

    def database(self) -> str:
        """The configured PostgreSQL URL; there is no implicit local database."""
        raw = self.database_url.get_secret_value()
        if not raw:
            from lifegather.database import DatabaseConfigurationError

            raise DatabaseConfigurationError(
                "Set LIFEGATHER_DATABASE_URL to the PostgreSQL database"
            )
        return raw

    @field_validator(
        "vault_key_file", "configuration_file", "storage_dir", mode="before"
    )
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
        if self.static_dir is not None and self.files_dir.resolve().is_relative_to(
            self.static_dir.resolve()
        ):
            raise ValueError("Private files must be outside the static directory")
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
