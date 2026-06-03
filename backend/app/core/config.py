"""Application settings (PRIVPORTAL_* env prefix)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PRIVPORTAL_",
        env_file=".env",
        extra="ignore",
    )

    api_host: str = "127.0.0.1"
    api_port: int = 12790
    database_url: str = "sqlite:///./privportal.db"
