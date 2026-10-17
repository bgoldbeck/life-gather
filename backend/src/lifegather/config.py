from pathlib import Path
from typing import Self

from pydantic import model_validator
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

    @model_validator(mode="after")
    def keep_data_private(self) -> Self:
        if self.static_dir is not None and self.data_dir.resolve().is_relative_to(
            self.static_dir.resolve()
        ):
            raise ValueError("Private data must be outside the static directory")
        return self
