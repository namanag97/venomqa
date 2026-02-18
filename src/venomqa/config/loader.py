"""Enhanced configuration loader with validation and profile support."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from venomqa.config.schema import get_default_config
from venomqa.config.validators import validate_config, validate_profile


class ConfigLoadError(Exception):
    """Raised when configuration cannot be loaded."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        self.details = details or {}
        super().__init__(message)


class ConfigLoader:
    """Enhanced configuration loader with validation, interpolation, and profiles."""

    ENV_VAR_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")

    def __init__(
        self,
        config_path: str | Path | None = None,
        profile: str | None = None,
        validate: bool = True,
        interpolate_env: bool = True,
    ) -> None:
        self.config_path = Path(config_path) if config_path else None
        self.profile = profile or os.environ.get("VENOMQA_PROFILE")
        self.validate = validate
        self.interpolate_env = interpolate_env
        self._raw_config: dict[str, Any] = {}
        self._config: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        """Load and validate configuration.

        Priority: profile overrides > env vars > config file > defaults
        """
        config = get_default_config()

        if self.config_path:
            file_config = self._load_from_file(self.config_path)
            self._raw_config = file_config.copy()
            file_config = self._interpolate_env_vars(file_config)
            config = self._deep_merge(config, file_config)

        active_profile = self.profile or config.get("profile")
        if active_profile and "profiles" in config:
            profile_config = config.get("profiles", {}).get(active_profile, {})
            if profile_config:
                validate_profile(profile_config, active_profile)
                config = self._deep_merge(config, profile_config)
            config.pop("profiles", None)

        config = self._apply_env_overrides(config)

        # Resolve relative paths based on config file location
        if self.config_path:
            config = self._resolve_relative_paths(config, self.config_path.parent)

        if self.validate:
            validate_config(config)

        self._config = config
        return config

    def _load_from_file(self, path: Path) -> dict[str, Any]:
        """Load configuration from YAML file."""
        if not path.exists():
            raise ConfigLoadError(
                f"Configuration file not found: {path}",
                {
                    "path": str(path),
                    "suggestions": [
                        "Create a venomqa.yaml file in your project root",
                        "Specify a different config path with --config",
                    ],
                },
            )

        try:
            with open(path) as f:
                content = f.read()
                config = yaml.safe_load(content)
                if config is None:
                    return {}
                if not isinstance(config, dict):
                    raise ConfigLoadError(
                        f"Configuration must be a YAML object, got {type(config).__name__}",
                        {"path": str(path)},
                    )
                return config
        except yaml.YAMLError as e:
            raise ConfigLoadError(
                f"Failed to parse YAML configuration: {e}",
                {"path": str(path), "yaml_error": str(e)},
            ) from e

    def _interpolate_env_vars(self, config: dict[str, Any]) -> dict[str, Any]:
        """Recursively interpolate environment variables in config values."""
        if not self.interpolate_env:
            return config

        result: dict[str, Any] = {}
        env_mapping = config.pop("env", {})

        for key, value in config.items():
            if isinstance(value, dict):
                result[key] = self._interpolate_env_vars(value)
            elif isinstance(value, list):
                result[key] = [self._interpolate_value(item) for item in value]
            elif isinstance(value, str):
                result[key] = self._interpolate_value(value)
            else:
                result[key] = value

        for config_key, env_var in env_mapping.items():
            if config_key not in result:
                interpolated = self._interpolate_value(env_var)
                if interpolated and not interpolated.startswith("${"):
                    result[config_key] = interpolated

        return result

    def _interpolate_value(self, value: str) -> str:
        """Interpolate environment variables in a string value."""

        def replace_env_var(match: re.Match[str]) -> str:
            var_name = match.group(1)
            default_value = match.group(2) or ""
            return os.environ.get(var_name, default_value)

        return self.ENV_VAR_PATTERN.sub(replace_env_var, value)

    def _apply_env_overrides(self, config: dict[str, Any]) -> dict[str, Any]:
        """Apply environment variable overrides to configuration."""
        env_mappings: dict[str, tuple[str, Any]] = {
            "VENOMQA_BASE_URL": ("base_url", str),
            "VENOMQA_DB_URL": ("db_url", str),
            "VENOMQA_DB_BACKEND": ("db_backend", str),
            "VENOMQA_DOCKER_COMPOSE_FILE": ("docker_compose_file", str),
            "VENOMQA_TIMEOUT": ("timeout", int),
            "VENOMQA_RETRY_COUNT": ("retry_count", int),
            "VENOMQA_RETRY_DELAY": ("retry_delay", float),
            "VENOMQA_CAPTURE_LOGS": ("capture_logs", lambda x: x.lower() in ("true", "1", "yes")),
            "VENOMQA_LOG_LINES": ("log_lines", int),
            "VENOMQA_PARALLEL_PATHS": ("parallel_paths", int),
            "VENOMQA_REPORT_DIR": ("report_dir", str),
            "VENOMQA_VERBOSE": ("verbose", lambda x: x.lower() in ("true", "1", "yes")),
            "VENOMQA_FAIL_FAST": ("fail_fast", lambda x: x.lower() in ("true", "1", "yes")),
        }

        for env_key, (config_key, converter) in env_mappings.items():
            value = os.environ.get(env_key)
            if value is not None:
                try:
                    config[config_key] = converter(value)
                except (ValueError, TypeError) as e:
                    raise ConfigLoadError(
                        f"Invalid value for {env_key}: {value}",
                        {"env_var": env_key, "value": value, "error": str(e)},
                    ) from e

        if "VENOMQA_REPORT_FORMATS" in os.environ:
            formats_str = os.environ["VENOMQA_REPORT_FORMATS"]
            config.setdefault("report", {})["formats"] = [f.strip() for f in formats_str.split(",")]

        return config

    def _deep_merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Deep merge two dictionaries, with override taking precedence."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _resolve_relative_paths(self, config: dict[str, Any], base_dir: Path) -> dict[str, Any]:
        """Resolve relative paths in config relative to the config file's directory.

        Path fields are resolved relative to base_dir (usually config_path.parent).
        Absolute paths are left unchanged.
        """
        path_fields = ["docker_compose_file", "report_dir"]

        for field in path_fields:
            if field in config and isinstance(config[field], str):
                path = Path(config[field])
                if not path.is_absolute():
                    resolved = base_dir / path
                    if resolved.exists() or field == "report_dir":
                        # Use resolved path (for report_dir, always resolve even if not exists)
                        config[field] = str(resolved)
                    # If not exists, leave as-is for validation to catch

        return config

    def get_raw_config(self) -> dict[str, Any]:
        """Return the raw configuration before interpolation and overrides."""
        return self._raw_config.copy()

    def get_effective_config(self) -> dict[str, Any]:
        """Return the effective configuration after all processing."""
        return self._config.copy()


def load_config(
    config_path: str | Path | None = None,
    profile: str | None = None,
    validate: bool = True,
) -> dict[str, Any]:
    """Load configuration with validation and profile support.

    Args:
        config_path: Path to configuration file (default: auto-detect)
        profile: Configuration profile to use (dev, staging, prod)
        validate: Whether to validate configuration

    Returns:
        Configuration dictionary

    Raises:
        ConfigLoadError: If configuration cannot be loaded
        ConfigValidationError: If configuration validation fails
    """
    if config_path is None:
        for candidate in ["venomqa.yaml", "venomqa.yml", ".venomqa.yaml", "config/venomqa.yaml"]:
            if Path(candidate).exists():
                config_path = Path(candidate)
                break

    loader = ConfigLoader(
        config_path=config_path,
        profile=profile,
        validate=validate,
    )
    return loader.load()


def get_config_for_profile(
    base_config: dict[str, Any],
    profile: str,
) -> dict[str, Any]:
    """Get configuration for a specific profile from a base config.

    Args:
        base_config: Base configuration dictionary
        profile: Profile name to apply

    Returns:
        Merged configuration with profile overrides applied
    """
    config = get_default_config()
    config = {**config, **{k: v for k, v in base_config.items() if k != "profiles"}}

    profiles = base_config.get("profiles", {})
    if profile in profiles:
        profile_config = profiles[profile]
        validate_profile(profile_config, profile)

        def deep_merge(base: dict, override: dict) -> dict:
            result = base.copy()
            for key, value in override.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result

        config = deep_merge(config, profile_config)

    return config


def resolve_env_vars(value: str) -> str:
    """Resolve environment variables in a string value.

    Supports ${VAR} and ${VAR:-default} syntax.
    """
    pattern = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")

    def replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default = match.group(2) or ""
        return os.environ.get(var_name, default)

    return pattern.sub(replace, value)


def create_example_config(profile: str = "development") -> str:
    """Generate an example configuration file.

    Args:
        profile: Profile type for example (development, staging, production, ci)

    Returns:
        YAML configuration string
    """
    examples = {
        "development": """# VenomQA Development Configuration
base_url: "http://localhost:3000"

timeout: 60
verbose: true
capture_logs: true

retry:
  max_attempts: 3
  delay: 1.0
  backoff_multiplier: 2

report:
  formats:
    - markdown
    - html
  output_dir: "./reports"
  include_timestamp: true

parallel_paths: 1
fail_fast: false
""",
        "staging": """# VenomQA Staging Configuration
base_url: "https://staging.example.com"

timeout: 30
verbose: false
capture_logs: true

retry:
  max_attempts: 3
  delay: 2.0
  backoff_multiplier: 2

report:
  formats:
    - junit
    - json
  output_dir: "/var/lib/venomqa/reports"

parallel_paths: 2
fail_fast: false
""",
        "production": """# VenomQA Production Configuration
base_url: "https://api.example.com"

timeout: 15
verbose: false
capture_logs: false

retry:
  max_attempts: 2
  delay: 1.0
  backoff_multiplier: 1.5

report:
  formats:
    - junit
  output_dir: "/var/lib/venomqa/reports"

parallel_paths: 4
fail_fast: true
""",
        "ci": """# VenomQA CI Configuration
# Uses environment variable interpolation for portability

env:
  BASE_URL: "${CI_BASE_URL:-http://localhost:3000}"
  DB_URL: "${DATABASE_URL}"

base_url: "${BASE_URL}"
db_url: "${DB_URL}"

timeout: 30
verbose: false
capture_logs: true

retry:
  max_attempts: 2
  delay: 1.0
  backoff_multiplier: 2

report:
  formats:
    - junit
    - json
  output_dir: "./test-results"

parallel_paths: 2
fail_fast: true

profiles:
  dev:
    base_url: "http://localhost:3000"
    verbose: true
  staging:
    base_url: "https://staging.example.com"
  prod:
    base_url: "https://api.example.com"
    fail_fast: true
""",
    }

    return examples.get(profile, examples["development"])
