"""Application settings (12-factor, environment-driven).

All operational knobs live here and are overridable via environment variables (prefix
``APP_``) or a ``.env`` file. Comparator *algorithm* tuning stays in ``config.yaml`` — this
module only configures the web/service layer. See ``.env.example`` for the full list.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_COMPARATOR_CONFIG = _BACKEND_ROOT / "config.yaml"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Runtime ---
    env: str = "production"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    # --- CORS (frontend origins). "*" allows any origin. ---
    cors_allow_origins: str | list[str] = Field(default_factory=lambda: ["*"])

    # --- Upload limits ---
    max_upload_bytes: int = 512 * 1024 * 1024   # total multipart body cap
    max_file_bytes: int = 64 * 1024 * 1024      # per-PDF cap
    max_files_per_side: int = 20                # cap on reference/candidate count each (per folder)
    max_pairs: int = 20                         # cap on matched pairs per job

    # --- Worker / job store (sized for a single small EC2 box) ---
    worker_concurrency: int = 1                 # CV threads; raise on multi-vCPU hosts
    max_pending_jobs: int = 8                   # queued+running before /compare returns 429
    job_ttl_seconds: int = 3600                 # evict finished jobs after this long
    max_jobs: int = 50                          # hard cap on retained jobs (memory bound)

    # --- Comparator config ---
    comparator_config_path: Path = _DEFAULT_COMPARATOR_CONFIG

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        # Accept a comma-separated string from the environment.
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @field_validator("comparator_config_path")
    @classmethod
    def _config_exists(cls, value: Path) -> Path:
        if not value.exists():
            raise ValueError(f"comparator config not found: {value}")
        return value


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton (import-safe, test-overridable via cache clear)."""
    return Settings()
