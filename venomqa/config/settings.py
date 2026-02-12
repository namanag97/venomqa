"""Configuration settings and loading."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class QAConfig(BaseSettings):
    """Configuration for VenomQA framework."""

    model_config = SettingsConfigDict(
        env_prefix="VENOMQA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = "http://localhost:8000"
    db_url: str | None = None
    db_backend: str = "postgresql"
    docker_compose_file: str = "docker-compose.qa.yml"
    timeout: int = 30
    retry_count: int = 3
    retry_delay: float = 1.0
    capture_logs: bool = True
    log_lines: int = 50
    parallel_paths: int = 1
    report_dir: str = "reports"
    report_formats: list[str] = Field(default_factory=lambda: ["markdown"])
    verbose: bool = False
    fail_fast: bool = False

    @field_validator("db_url", mode="before")
    @classmethod
    def validate_db_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.startswith(("postgresql://", "postgres://")):
            raise ValueError("db_url must be a PostgreSQL connection string")
        return v

    @field_validator("report_formats", mode="before")
    @classmethod
    def validate_report_formats(cls, v: list[str]) -> list[str]:
        valid = {"markdown", "json", "junit", "html"}
        invalid = set(v) - valid
        if invalid:
            raise ValueError(f"Invalid report formats: {invalid}. Valid: {valid}")
        return v


def load_config(config_path: str | Path | None = None) -> QAConfig:
    """Load configuration from file and environment.

    Priority: CLI args > env vars > config file > defaults
    """
    config_data: dict[str, Any] = {}

    if config_path is not None:
        config_path = Path(config_path)
        if config_path.exists():
            with open(config_path) as f:
                config_data = yaml.safe_load(f) or {}

    env_overrides = _get_env_overrides()
    config_data.update(env_overrides)

    return QAConfig(**config_data)


def _get_env_overrides() -> dict[str, Any]:
    """Get configuration overrides from environment variables."""
    overrides: dict[str, Any] = {}

    env_mappings = {
        "VENOMQA_BASE_URL": "base_url",
        "VENOMQA_DB_URL": "db_url",
        "VENOMQA_TIMEOUT": ("timeout", int),
        "VENOMQA_VERBOSE": ("verbose", lambda x: x.lower() in ("true", "1", "yes")),
    }

    for env_key, config_key in env_mappings.items():
        value = os.environ.get(env_key)
        if value is not None:
            if isinstance(config_key, tuple):
                key, converter = config_key
                overrides[key] = converter(value)
            else:
                overrides[config_key] = value

    return overrides
