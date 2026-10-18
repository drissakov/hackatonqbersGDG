"""Server-only configuration; process environment overrides backend/.env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-6-luna"
    openai_embedding_model: str = "text-embedding-3-large"
    openai_embedding_dimensions: int = Field(default=1536, ge=1536, le=1536)
    twogis_api_key: SecretStr = SecretStr("")
    twogis_enabled: bool = False
    app_timezone: str = "Asia/Almaty"
    default_locale: Literal["kk", "ru", "en"] = "kk"

    @field_validator("app_timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError("APP_TIMEZONE must be a valid IANA timezone") from None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
