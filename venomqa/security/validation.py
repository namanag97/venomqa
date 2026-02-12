"""Input validation and sanitization for VenomQA."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


class InputValidationError(Exception):
    """Raised when input validation fails."""

    def __init__(self, field: str, message: str, value: Any = None) -> None:
        self.field = field
        self.message = message
        self.value = value
        super().__init__(f"Validation error for '{field}': {message}")


@dataclass
class ValidationRule:
    """A single validation rule."""

    name: str
    pattern: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    allowed_values: list[Any] | None = None
    custom_validator: callable | None = None
    required: bool = True


class InputValidator:
    """Validates journey configs, step parameters, and user inputs."""

    PATTERNS = {
        "step_name": r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$",
        "journey_name": r"^[a-zA-Z][a-zA-Z0-9_-]{0,127}$",
        "checkpoint_name": r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$",
        "path_name": r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$",
        "tag": r"^[a-zA-Z][a-zA-Z0-9_-]{0,31}$",
        "http_method": r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)$",
        "identifier": r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$",
        "safe_string": r"^[\w\s\-.,:;!?@#$%&*()+={}\[\]|\\<>/]{0,1000}$",
    }

    MAX_URL_LENGTH = 2048
    MAX_STRING_LENGTH = 10000
    MAX_STEPS = 100
    MAX_BRANCHES = 20
    MAX_PATHS_PER_BRANCH = 10

    def __init__(self, strict: bool = True) -> None:
        self.strict = strict
        self._errors: list[InputValidationError] = []

    def validate_step(self, step_data: dict[str, Any]) -> bool:
        """Validate a step configuration."""
        self._errors = []

        if "name" not in step_data:
            self._errors.append(InputValidationError("name", "Step name is required"))
        else:
            self._validate_pattern("step_name", step_data["name"], "name")

        if "action" not in step_data:
            self._errors.append(InputValidationError("action", "Step action is required"))

        if "timeout" in step_data:
            self._validate_range(step_data["timeout"], "timeout", min_val=0.1, max_val=3600)

        if "retries" in step_data:
            self._validate_range(step_data["retries"], "retries", min_val=0, max_val=10)

        if "description" in step_data:
            self._validate_length(step_data["description"], "description", max_len=500)

        if self._errors:
            if self.strict:
                raise self._errors[0]
            return False
        return True

    def validate_journey(self, journey_data: dict[str, Any]) -> bool:
        """Validate a journey configuration."""
        self._errors = []

        if "name" not in journey_data:
            self._errors.append(InputValidationError("name", "Journey name is required"))
        else:
            self._validate_pattern("journey_name", journey_data["name"], "name")

        if "steps" not in journey_data:
            self._errors.append(InputValidationError("steps", "Journey must have steps"))
        else:
            self._validate_range(
                len(journey_data["steps"]), "steps count", min_val=1, max_val=self.MAX_STEPS
            )

        if "description" in journey_data:
            self._validate_length(journey_data["description"], "description", max_len=1000)

        if "tags" in journey_data:
            if not isinstance(journey_data["tags"], list):
                self._errors.append(InputValidationError("tags", "Tags must be a list"))
            else:
                for i, tag in enumerate(journey_data["tags"]):
                    self._validate_pattern("tag", tag, f"tags[{i}]")

        if "timeout" in journey_data:
            self._validate_range(journey_data["timeout"], "timeout", min_val=1, max_val=86400)

        if self._errors:
            if self.strict:
                raise self._errors[0]
            return False
        return True

    def validate_branch(self, branch_data: dict[str, Any]) -> bool:
        """Validate a branch configuration."""
        self._errors = []

        if "checkpoint_name" not in branch_data:
            self._errors.append(
                InputValidationError("checkpoint_name", "Branch must reference a checkpoint")
            )
        else:
            self._validate_pattern(
                "checkpoint_name", branch_data["checkpoint_name"], "checkpoint_name"
            )

        if "paths" not in branch_data:
            self._errors.append(InputValidationError("paths", "Branch must have paths"))
        else:
            self._validate_range(
                len(branch_data["paths"]),
                "paths count",
                min_val=1,
                max_val=self.MAX_PATHS_PER_BRANCH,
            )
            for i, path in enumerate(branch_data.get("paths", [])):
                self._validate_path(path, f"paths[{i}]")

        if self._errors:
            if self.strict:
                raise self._errors[0]
            return False
        return True

    def validate_url(self, url: str, field_name: str = "url") -> bool:
        """Validate a URL string."""
        if not url:
            if self.strict:
                raise InputValidationError(field_name, "URL is required")
            return False

        if len(url) > self.MAX_URL_LENGTH:
            if self.strict:
                raise InputValidationError(
                    field_name, f"URL exceeds max length of {self.MAX_URL_LENGTH}"
                )
            return False

        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                if self.strict:
                    raise InputValidationError(field_name, "URL must use http or https scheme")
                return False
            if not parsed.netloc:
                if self.strict:
                    raise InputValidationError(field_name, "URL must have a valid host")
                return False
        except Exception as e:
            if self.strict:
                raise InputValidationError(field_name, f"Invalid URL format: {e}") from None
            return False

        dangerous_patterns = [
            r"javascript:",
            r"data:",
            r"vbscript:",
            r"file:",
        ]
        for pattern in dangerous_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                if self.strict:
                    raise InputValidationError(
                        field_name, f"URL contains dangerous protocol: {pattern}"
                    )
                return False

        return True

    def validate_headers(self, headers: dict[str, str]) -> bool:
        """Validate HTTP headers for security."""
        dangerous_headers = {
            "host": "Host header injection",
            "x-forwarded-host": "X-Forwarded-Host injection",
            "x-original-url": "X-Original-URL injection",
        }

        for header_name, warning in dangerous_headers.items():
            if header_name.lower() in [h.lower() for h in headers]:
                if self.strict:
                    raise InputValidationError(
                        f"header:{header_name}", f"Potentially dangerous header: {warning}"
                    )
                return False

        for name, value in headers.items():
            if not re.match(r"^[A-Za-z][A-Za-z0-9\-]*$", name):
                if self.strict:
                    raise InputValidationError(f"header:{name}", "Invalid header name format")
                return False

            if len(str(value)) > 8192:
                if self.strict:
                    raise InputValidationError(f"header:{name}", "Header value too long")
                return False

        return True

    def validate_step_params(self, params: dict[str, Any]) -> bool:
        """Validate step parameters."""
        self._errors = []

        for key, value in params.items():
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
                self._errors.append(
                    InputValidationError(key, "Parameter key must be a valid identifier")
                )
                continue

            if isinstance(value, str):
                if len(value) > self.MAX_STRING_LENGTH:
                    self._errors.append(
                        InputValidationError(
                            key, f"String value exceeds max length of {self.MAX_STRING_LENGTH}"
                        )
                    )

        if self._errors:
            if self.strict:
                raise self._errors[0]
            return False
        return True

    def sanitize_string(self, value: str, max_length: int | None = None) -> str:
        """Sanitize a string value."""
        max_len = max_length or self.MAX_STRING_LENGTH
        sanitized = value[:max_len]
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", sanitized)
        return sanitized.strip()

    def _validate_pattern(self, pattern_name: str, value: str, field_name: str) -> None:
        """Validate a value against a named pattern."""
        if pattern_name not in self.PATTERNS:
            return

        if not isinstance(value, str):
            self._errors.append(
                InputValidationError(field_name, f"Expected string, got {type(value).__name__}")
            )
            return

        pattern = self.PATTERNS[pattern_name]
        if not re.match(pattern, value):
            self._errors.append(
                InputValidationError(
                    field_name, f"Value '{value}' does not match pattern for {pattern_name}"
                )
            )

    def _validate_length(
        self, value: str, field_name: str, min_len: int = 0, max_len: int | None = None
    ) -> None:
        """Validate string length."""
        if not isinstance(value, str):
            self._errors.append(
                InputValidationError(field_name, f"Expected string, got {type(value).__name__}")
            )
            return

        if len(value) < min_len:
            self._errors.append(
                InputValidationError(field_name, f"Value must be at least {min_len} characters")
            )

        if max_len and len(value) > max_len:
            self._errors.append(
                InputValidationError(field_name, f"Value must be at most {max_len} characters")
            )

    def _validate_range(
        self, value: Any, field_name: str, min_val: Any | None = None, max_val: Any | None = None
    ) -> None:
        """Validate numeric range."""
        try:
            num_value = float(value) if not isinstance(value, (int, float)) else value
        except (TypeError, ValueError):
            self._errors.append(
                InputValidationError(
                    field_name, f"Expected numeric value, got {type(value).__name__}"
                )
            )
            return

        if min_val is not None and num_value < min_val:
            self._errors.append(
                InputValidationError(field_name, f"Value must be at least {min_val}")
            )

        if max_val is not None and num_value > max_val:
            self._errors.append(
                InputValidationError(field_name, f"Value must be at most {max_val}")
            )

    def _validate_path(self, path_data: dict[str, Any], field_prefix: str = "") -> None:
        """Validate a path within a branch."""
        if "name" not in path_data:
            self._errors.append(
                InputValidationError(f"{field_prefix}.name", "Path name is required")
            )
        else:
            self._validate_pattern("path_name", path_data["name"], f"{field_prefix}.name")

        if "steps" not in path_data:
            self._errors.append(
                InputValidationError(f"{field_prefix}.steps", "Path must have steps")
            )
        else:
            self._validate_range(
                len(path_data["steps"]),
                f"{field_prefix}.steps count",
                min_val=1,
                max_val=self.MAX_STEPS,
            )

    @property
    def errors(self) -> list[InputValidationError]:
        """Get validation errors."""
        return self._errors.copy()
