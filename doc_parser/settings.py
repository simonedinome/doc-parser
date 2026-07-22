"""Configurazione applicativa via pydantic-settings (.env / variabili d'ambiente)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = ""
    openrouter_api_key: str = ""

    foundry_endpoint: str = ""
    foundry_api_key: str = ""
    foundry_deployment: str = ""
    foundry_pages_per_batch: int = 10
    foundry_raster_dpi: int = 150

    storage_backend: Literal["sqlite", "azure"] = "sqlite"
    auth_provider: Literal["password", "easyauth"] = "password"

    data_dir: Path = _BASE_DIR / "data"
    users_file: Path = _BASE_DIR / "users.yaml"
    models_file: Path = _BASE_DIR / "models.yaml"

    max_upload_mb: int = 500
    max_pages: int = 300
    xlsx_max_rows_per_sheet: int = 5000

    worker_poll_seconds: float = 1.0
    retry_max_attempts: int = 2
    retry_backoff_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
