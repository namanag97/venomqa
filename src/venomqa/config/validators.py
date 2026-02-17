"""Custom validators for VenomQA configuration.

This module provides comprehensive configuration validation with:
- JSON Schema validation for structure
- Semantic validation for URLs, paths, formats
- Helpful error messages with suggestions
- Production readiness warnings

Example:
    from venomqa.config.validators import validate_config

    try:
        validate_config(my_config)
    except ConfigValidationError as e:
        for error in e.errors:
            print(f"Field: {error.get('field')}")
            print(f"Error: {error.get('message')}")
            print(f"Hint: {error.get('hint')}")
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from venomqa.config.schema import VENOMQA_CONFIG_SCHEMA


class ConfigValidationError(Exception):
    """Raised when configuration validation fails.

    Provides structured access to all validation errors with:
    - path: Where in the config the error occurred
    - message: What went wrong
    - hint: How to fix it
    - value: The invalid value (if applicable)

    Attributes:
        errors: List of error dictionaries with details
    """

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self.errors = errors
        messages = []
        for error in errors:
            path = " -> ".join(str(p) for p in error.get("path", []))
            if error.get("field"):
                path = error["field"]
            message = error.get("message", "Unknown error")
            if path:
                messages.append(f"{path}: {message}")
            else:
                messages.append(message)

        # Build user-friendly error message
        error_text = "Configuration validation failed:\n  " + "\n  ".join(messages)

        # Add hints if available
        hints = [e.get("hint") for e in errors if e.get("hint")]
        if hints:
            error_text += "\n\nHints:"
            for hint in hints[:3]:  # Show up to 3 hints
                error_text += f"\n  - {hint}"

        super().__init__(error_text)

    @property
    def suggestions(self) -> list[str]:
        """Get list of suggestions for fixing the errors."""
        suggestions = []
        for error in self.errors:
            if error.get("hint"):
                suggestions.append(error["hint"])
            elif error.get("allowed"):
                suggestions.append(f"Allowed values: {error['allowed']}")
            elif error.get("valid_formats"):
                suggestions.append(f"Valid formats: {error['valid_formats']}")
        return suggestions

    def to_dict(self) -> dict[str, Any]:
        """Return error details as dictionary."""
        return {
            "error_type": "config_validation",
            "errors": self.errors,
            "suggestions": self.suggestions,
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


def validate_for_production(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Check configuration for production readiness.

    This validates the config against best practices for production
    deployments. Returns a list of warnings (not errors).

    Args:
        config: Configuration dictionary to check

    Returns:
        List of warning dictionaries with field, message, and suggestion

    Example:
        warnings = validate_for_production(config)
        for w in warnings:
            print(f"Warning: {w['message']}")
            print(f"Suggestion: {w['suggestion']}")
    """
    warnings: list[dict[str, Any]] = []

    # Check for localhost in base_url
    base_url = config.get("base_url", "")
    if "localhost" in base_url or "127.0.0.1" in base_url:
        warnings.append({
            "field": "base_url",
            "level": "warning",
            "message": "base_url points to localhost",
            "suggestion": "Use environment variable: base_url: ${API_BASE_URL}",
        })

    # Check for hardcoded credentials in db_url
    db_url = config.get("db_url", "")
    if db_url and "@" in db_url and "://" in db_url:
        # Simple check for non-env-var password
        if "${" not in db_url and ":" in db_url.split("@")[0]:
            warnings.append({
                "field": "db_url",
                "level": "warning",
                "message": "Database URL may contain hardcoded credentials",
                "suggestion": "Use environment variable: db_url: ${DATABASE_URL}",
            })

    # Check timeout is reasonable for production
    timeout = config.get("timeout", 30)
    if timeout > 120:
        warnings.append({
            "field": "timeout",
            "level": "warning",
            "message": f"Timeout of {timeout}s is very high for production",
            "suggestion": "Consider timeout: 30 or lower for faster failure detection",
        })
    elif timeout < 5:
        warnings.append({
            "field": "timeout",
            "level": "warning",
            "message": f"Timeout of {timeout}s may be too low for production",
            "suggestion": "Consider timeout: 10-30 for reliability",
        })

    # Check retry configuration
    retry = config.get("retry", {})
    if retry.get("max_attempts", 3) < 2:
        warnings.append({
            "field": "retry.max_attempts",
            "level": "warning",
            "message": "Only 1 retry attempt configured",
            "suggestion": "Consider max_attempts: 3 for resilience against transient failures",
        })

    # Check for JUnit output format (needed for CI)
    report = config.get("report", {})
    formats = report.get("formats", [])
    if "junit" not in formats:
        warnings.append({
            "field": "report.formats",
            "level": "info",
            "message": "JUnit format not configured",
            "suggestion": "Add 'junit' to formats for CI/CD integration",
        })

    # Check parallel_paths for production
    parallel = config.get("parallel_paths", 1)
    if parallel > 8:
        warnings.append({
            "field": "parallel_paths",
            "level": "warning",
            "message": f"High parallelism ({parallel}) may overwhelm target API",
            "suggestion": "Consider parallel_paths: 4-8 for production stability",
        })

    # Check fail_fast is set appropriately
    if not config.get("fail_fast"):
        warnings.append({
            "field": "fail_fast",
            "level": "info",
            "message": "fail_fast is disabled",
            "suggestion": "Enable fail_fast: true for faster CI feedback",
        })

    # Check capture_logs for debugging
    if not config.get("capture_logs", True):
        warnings.append({
            "field": "capture_logs",
            "level": "info",
            "message": "Log capture is disabled",
            "suggestion": "Enable capture_logs: true for better debugging",
        })

    return warnings


def get_config_summary(config: dict[str, Any]) -> dict[str, Any]:
    """Generate a summary of the configuration for display.

    Args:
        config: Configuration dictionary

    Returns:
        Summary dictionary with key settings and their status
    """
    return {
        "api": {
            "base_url": config.get("base_url", "not set"),
            "timeout": f"{config.get('timeout', 30)}s",
        },
        "database": {
            "configured": bool(config.get("db_url")),
            "backend": config.get("db_backend", "postgresql"),
        },
        "retry": {
            "max_attempts": config.get("retry", {}).get("max_attempts", 3),
            "delay": f"{config.get('retry', {}).get('delay', 1.0)}s",
        },
        "execution": {
            "parallel_paths": config.get("parallel_paths", 1),
            "fail_fast": config.get("fail_fast", False),
        },
        "reporting": {
            "formats": config.get("report", {}).get("formats", ["markdown"]),
            "output_dir": config.get("report", {}).get("output_dir", "reports"),
        },
        "features": {
            "capture_logs": config.get("capture_logs", True),
            "verbose": config.get("verbose", False),
        },
    }
