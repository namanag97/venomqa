"""Configuration settings and loading."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from venomqa.errors import ConfigValidationError, ErrorContext


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
    ports: list[dict[str, Any]] = Field(default_factory=list)
    adapters: dict[str, Any] = Field(default_factory=dict)

    # Data generation settings
    data_seed: int | None = Field(default=None, description="Seed for reproducible fake data generation")
    data_locale: str = Field(default="en_US", description="Locale for generated data (e.g., de_DE, fr_FR)")

    @field_validator("db_url", mode="before")
    @classmethod
    def validate_db_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.startswith(("postgresql://", "postgres://")):
            raise ConfigValidationError(
                message="db_url must be a PostgreSQL connection string",
                field="db_url",
                value=v,
                context=ErrorContext(extra={"expected_prefix": "postgresql://"}),
            )
        return v

    @field_validator("report_formats", mode="before")
    @classmethod
    def validate_report_formats(cls, v: list[str]) -> list[str]:
        valid = {"markdown", "json", "junit", "html"}
        invalid = set(v) - valid
        if invalid:
            raise ConfigValidationError(
                message=f"Invalid report formats: {invalid}. Valid: {valid}",
                field="report_formats",
                value=v,
                context=ErrorContext(extra={"valid_formats": list(valid)}),
            )
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

    config = QAConfig(**config_data)

    # Configure global fake data generator if seed or locale is set
    _configure_fake_generator(config)

    return config


def _configure_fake_generator(config: QAConfig) -> None:
    """Configure the global fake data generator from config."""
    try:
        from venomqa.data import set_global_seed

        # Set locale if different from default
        if config.data_locale != "en_US":
            # Create a new generator with the specified locale
            import venomqa.data as data_module
            from venomqa.data.generators import FakeDataGenerator

            new_fake = FakeDataGenerator(
                locale=config.data_locale,
                seed=config.data_seed,
            )
            # Replace the global fake instance
            data_module.fake = new_fake
            data_module.generators.fake = new_fake
        elif config.data_seed is not None:
            # Just set the seed
            set_global_seed(config.data_seed)
    except ImportError:
        # Data module not available or faker not installed
        pass


def _get_env_overrides() -> dict[str, Any]:
    """Get configuration overrides from environment variables."""
    overrides: dict[str, Any] = {}

    env_mappings = {
        "VENOMQA_BASE_URL": "base_url",
        "VENOMQA_DB_URL": "db_url",
        "VENOMQA_TIMEOUT": ("timeout", int),
        "VENOMQA_VERBOSE": ("verbose", lambda x: x.lower() in ("true", "1", "yes")),
        "VENOMQA_DATA_SEED": ("data_seed", int),
        "VENOMQA_DATA_LOCALE": "data_locale",
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
