"""Custom validators for VenomQA configuration."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from venomqa.config.schema import VENOMQA_CONFIG_SCHEMA


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        messages = []
        for error in errors:
            path = " -> ".join(str(p) for p in error.get("path", []))
            message = error.get("message", "Unknown error")
            if path:
                messages.append(f"{path}: {message}")
            else:
                messages.append(message)
        super().__init__("Configuration validation failed:\n  " + "\n  ".join(messages))

    def to_dict(self) -> dict[str, Any]:
        """Return error details as dictionary."""
        return {
            "error_type": "config_validation",
            "errors": self.errors,
        }


class SchemaValidator:
    """JSON Schema validator for configuration."""

    def __init__(self, schema: dict[str, Any] | None = None) -> None:
        self.schema = schema or VENOMQA_CONFIG_SCHEMA

    def validate(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate configuration against schema.

        Returns list of errors, empty if valid.
        """
        errors: list[dict[str, Any]] = []
        self._validate_object(config, self.schema, [], errors)
        return errors

    def _validate_object(
        self,
        value: Any,
        schema: dict[str, Any],
        path: list[str | int],
        errors: list[dict[str, Any]],
    ) -> None:
        """Recursively validate an object against schema."""
        if schema.get("type") == "object":
            if not isinstance(value, dict):
                errors.append(
                    {
                        "path": path,
                        "message": f"Expected object, got {type(value).__name__}",
                        "value": value,
                    }
                )
                return

            properties = schema.get("properties", {})
            required = schema.get("required", [])

            for req in required:
                if req not in value:
                    errors.append(
                        {
                            "path": path + [req],
                            "message": f"Required property '{req}' is missing",
                        }
                    )

            for key, val in value.items():
                if key in properties:
                    self._validate_object(val, properties[key], path + [key], errors)
                elif not schema.get("additionalProperties", True):
                    errors.append(
                        {
                            "path": path + [key],
                            "message": f"Unknown property '{key}'",
                            "hint": f"Allowed properties: {list(properties.keys())}",
                        }
                    )

        elif schema.get("type") == "array":
            if not isinstance(value, list):
                errors.append(
                    {
                        "path": path,
                        "message": f"Expected array, got {type(value).__name__}",
                        "value": value,
                    }
                )
                return

            min_items = schema.get("minItems")
            if min_items is not None and len(value) < min_items:
                errors.append(
                    {
                        "path": path,
                        "message": f"Array must have at least {min_items} items, got {len(value)}",
                    }
                )

            items_schema = schema.get("items", {})
            for i, item in enumerate(value):
                self._validate_object(item, items_schema, path + [i], errors)

        elif schema.get("type") == "string":
            if not isinstance(value, str):
                errors.append(
                    {
                        "path": path,
                        "message": f"Expected string, got {type(value).__name__}",
                        "value": value,
                    }
                )
                return

            if "enum" in schema and value not in schema["enum"]:
                errors.append(
                    {
                        "path": path,
                        "message": f"Value '{value}' not in allowed values",
                        "allowed": schema["enum"],
                    }
                )

            if "pattern" in schema:
                if not re.search(schema["pattern"], value):
                    errors.append(
                        {
                            "path": path,
                            "message": f"Value does not match pattern: {schema['pattern']}",
                            "value": value,
                        }
                    )

            if "format" in schema:
                self._validate_format(value, schema["format"], path, errors)

        elif schema.get("type") == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(
                    {
                        "path": path,
                        "message": f"Expected integer, got {type(value).__name__}",
                        "value": value,
                    }
                )
                return

            self._validate_number_bounds(value, schema, path, errors)

        elif schema.get("type") == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(
                    {
                        "path": path,
                        "message": f"Expected number, got {type(value).__name__}",
                        "value": value,
                    }
                )
                return

            self._validate_number_bounds(value, schema, path, errors)

        elif schema.get("type") == "boolean":
            if not isinstance(value, bool):
                errors.append(
                    {
                        "path": path,
                        "message": f"Expected boolean, got {type(value).__name__}",
                        "value": value,
                    }
                )

    def _validate_format(
        self,
        value: str,
        format_type: str,
        path: list[str | int],
        errors: list[dict[str, Any]],
    ) -> None:
        """Validate string format."""
        if format_type == "uri":
            try:
                result = urlparse(value)
                if not all([result.scheme, result.netloc]):
                    raise ValueError("Invalid URI")
            except Exception:
                errors.append(
                    {
                        "path": path,
                        "message": f"Invalid URI format: {value}",
                        "hint": "Expected format: http://example.com or https://example.com",
                    }
                )

    def _validate_number_bounds(
        self,
        value: int | float,
        schema: dict[str, Any],
        path: list[str | int],
        errors: list[dict[str, Any]],
    ) -> None:
        """Validate number minimum/maximum bounds."""
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")

        if minimum is not None and value < minimum:
            errors.append(
                {
                    "path": path,
                    "message": f"Value {value} is less than minimum {minimum}",
                }
            )

        if maximum is not None and value > maximum:
            errors.append(
                {
                    "path": path,
                    "message": f"Value {value} is greater than maximum {maximum}",
                }
            )


class URLValidator:
    """Validates URL configurations."""

    @staticmethod
    def validate_base_url(url: str) -> dict[str, Any] | None:
        """Validate base URL and return error dict if invalid."""
        try:
            result = urlparse(url)
            if not result.scheme:
                return {
                    "field": "base_url",
                    "message": "URL must include scheme (http:// or https://)",
                    "value": url,
                }
            if result.scheme not in ("http", "https"):
                return {
                    "field": "base_url",
                    "message": f"Invalid URL scheme: {result.scheme}. Use http or https.",
                    "value": url,
                }
            if not result.netloc:
                return {
                    "field": "base_url",
                    "message": "URL must include host",
                    "value": url,
                }
            return None
        except Exception as e:
            return {
                "field": "base_url",
                "message": f"Invalid URL: {e}",
                "value": url,
            }

    @staticmethod
    def validate_db_url(url: str) -> dict[str, Any] | None:
        """Validate database URL and return error dict if invalid."""
        if not url:
            return None

        valid_prefixes = ("postgresql://", "postgres://", "mysql://", "sqlite://")
        if not url.startswith(valid_prefixes):
            return {
                "field": "db_url",
                "message": f"Invalid database URL. Must start with one of: {valid_prefixes}",
                "value": url,
                "hint": "Example: postgresql://user:password@localhost:5432/dbname",
            }
        return None


class PathValidator:
    """Validates file and directory paths."""

    @staticmethod
    def validate_path_exists(
        path: str,
        field_name: str,
        must_be_file: bool = False,
        must_be_dir: bool = False,
    ) -> dict[str, Any] | None:
        """Validate that a path exists."""
        p = Path(path)
        if not p.exists():
            return {
                "field": field_name,
                "message": f"Path does not exist: {path}",
                "hint": (
                    f"Create the {'file' if must_be_file else 'directory'} "
                    f"or update the configuration"
                )
                if must_be_file or must_be_dir
                else "Create the path or update the configuration",
            }

        if must_be_file and not p.is_file():
            return {
                "field": field_name,
                "message": f"Path is not a file: {path}",
            }

        if must_be_dir and not p.is_dir():
            return {
                "field": field_name,
                "message": f"Path is not a directory: {path}",
            }

        return None

    @staticmethod
    def validate_docker_compose(path: str) -> dict[str, Any] | None:
        """Validate Docker Compose file."""
        p = Path(path)
        if not p.exists():
            return {
                "field": "docker_compose_file",
                "message": f"Docker Compose file not found: {path}",
                "hint": "Create the file or update docker_compose_file in your config",
            }
        if p.suffix not in (".yml", ".yaml"):
            return {
                "field": "docker_compose_file",
                "message": f"Docker Compose file should be YAML: {path}",
            }
        return None


class ReportFormatValidator:
    """Validates report format configuration."""

    VALID_FORMATS = frozenset(["markdown", "json", "junit", "html"])

    @classmethod
    def validate_formats(cls, formats: list[str]) -> dict[str, Any] | None:
        """Validate report format list."""
        if not formats:
            return {
                "field": "report.formats",
                "message": "At least one report format must be specified",
            }

        invalid = set(formats) - cls.VALID_FORMATS
        if invalid:
            return {
                "field": "report.formats",
                "message": f"Invalid report formats: {invalid}",
                "valid_formats": list(cls.VALID_FORMATS),
            }

        return None


class RetryConfigValidator:
    """Validates retry configuration."""

    @staticmethod
    def validate(retry_config: dict[str, Any]) -> list[dict[str, Any]]:
        """Validate retry configuration and return list of errors."""
        errors: list[dict[str, Any]] = []

        if "max_attempts" in retry_config:
            attempts = retry_config["max_attempts"]
            if not isinstance(attempts, int) or attempts < 1:
                errors.append(
                    {
                        "field": "retry.max_attempts",
                        "message": "max_attempts must be a positive integer",
                        "value": attempts,
                    }
                )

        if "delay" in retry_config:
            delay = retry_config["delay"]
            if not isinstance(delay, (int, float)) or delay < 0:
                errors.append(
                    {
                        "field": "retry.delay",
                        "message": "delay must be a non-negative number",
                        "value": delay,
                    }
                )

        if "backoff_multiplier" in retry_config:
            multiplier = retry_config["backoff_multiplier"]
            if not isinstance(multiplier, (int, float)) or multiplier < 1:
                errors.append(
                    {
                        "field": "retry.backoff_multiplier",
                        "message": "backoff_multiplier must be >= 1",
                        "value": multiplier,
                    }
                )

        return errors


def validate_config(config: dict[str, Any]) -> None:
    """Validate configuration and raise ConfigValidationError if invalid."""
    errors: list[dict[str, Any]] = []

    schema_validator = SchemaValidator()
    errors.extend(schema_validator.validate(config))

    if "base_url" in config:
        url_error = URLValidator.validate_base_url(config["base_url"])
        if url_error:
            errors.append(url_error)

    if "db_url" in config and config["db_url"]:
        db_error = URLValidator.validate_db_url(config["db_url"])
        if db_error:
            errors.append(db_error)

    if "docker_compose_file" in config:
        path_error = PathValidator.validate_docker_compose(config["docker_compose_file"])
        if path_error:
            errors.append(path_error)

    if "report" in config and "formats" in config.get("report", {}):
        format_error = ReportFormatValidator.validate_formats(config["report"]["formats"])
        if format_error:
            errors.append(format_error)

    if "retry" in config:
        retry_errors = RetryConfigValidator.validate(config["retry"])
        errors.extend(retry_errors)

    if errors:
        raise ConfigValidationError(errors)


def validate_profile(profile_config: dict[str, Any], profile_name: str) -> None:
    """Validate a profile configuration."""
    from venomqa.config.schema import PROFILE_SCHEMA

    schema_validator = SchemaValidator(PROFILE_SCHEMA)
    errors = schema_validator.validate(profile_config)

    for error in errors:
        error["path"] = ["profiles", profile_name] + error.get("path", [])

    if errors:
        raise ConfigValidationError(errors)
