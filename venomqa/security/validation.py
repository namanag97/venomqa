"""Input validation and sanitization for VenomQA.

This module provides comprehensive input validation utilities for securing
journey configurations, step parameters, and user inputs against common
security vulnerabilities.

Example:
    >>> validator = InputValidator(strict=True)
    >>> validator.validate_step({"name": "test_step", "action": "click"})
    True
    >>> validator.validate_url("javascript:alert(1)")  # Raises InputValidationError
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import urlparse


class InputValidationError(Exception):
    """Raised when input validation fails.

    Attributes:
        field: The name of the field that failed validation.
        message: A human-readable error message.
        value: The value that failed validation (optional, for debugging).

    Example:
        >>> raise InputValidationError("username", "Must be alphanumeric", "user@name")
        InputValidationError: Validation error for 'username': Must be alphanumeric
    """

    def __init__(self, field: str, message: str, value: Any = None) -> None:
        """Initialize the validation error.

        Args:
            field: The name of the field that failed validation.
            message: A description of why validation failed.
            value: The actual value that was rejected (optional).
        """
        self.field = field
        self.message = message
        self.value = value
        super().__init__(f"Validation error for '{field}': {message}")


@dataclass
class ValidationRule:
    """A single validation rule configuration.

    Validation rules can be applied to any input field to enforce constraints
    such as pattern matching, length limits, and custom validation logic.

    Attributes:
        name: Human-readable name for the rule.
        pattern: Regex pattern that the value must match.
        min_length: Minimum string length required.
        max_length: Maximum string length allowed.
        allowed_values: List of permitted values.
        custom_validator: Custom validation function returning bool.
        required: Whether the field is required.

    Example:
        >>> rule = ValidationRule(
        ...     name="username",
        ...     pattern=r"^[a-zA-Z0-9_]{3,20}$",
        ...     min_length=3,
        ...     max_length=20
        ... )
    """

    name: str
    pattern: str | None = None
    min_length: int | None = None
    max_length: int | None = None
    allowed_values: list[Any] | None = None
    custom_validator: Callable[[Any], bool] | None = None
    required: bool = True


@dataclass
class ValidationResult:
    """Result of a validation operation.

    Attributes:
        is_valid: Whether validation passed.
        errors: List of validation errors if any.
        warnings: List of validation warnings if any.
        sanitized_value: The sanitized version of the input value.
    """

    is_valid: bool = True
    errors: list[InputValidationError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sanitized_value: Any = None


class InputValidator:
    """Validates journey configs, step parameters, and user inputs.

    This validator provides comprehensive input validation with protection
    against common security vulnerabilities including injection attacks,
    path traversal, and malformed data.

    The validator operates in two modes:
        - Strict mode (default): Raises exceptions on validation failures.
        - Non-strict mode: Returns False and collects errors.

    Attributes:
        PATTERNS: Predefined regex patterns for common field types.
        MAX_URL_LENGTH: Maximum allowed URL length (2048 chars).
        MAX_STRING_LENGTH: Maximum allowed string length (10000 chars).
        MAX_STEPS: Maximum steps per journey (100).
        MAX_BRANCHES: Maximum branches per journey (20).
        MAX_PATHS_PER_BRANCH: Maximum paths per branch (10).

    Example:
        >>> validator = InputValidator(strict=True)
        >>> validator.validate_url("https://example.com/api")
        True
        >>> validator.validate_url("javascript:alert(1)")
        InputValidationError: URL contains dangerous protocol
    """

    PATTERNS: Final[dict[str, str]] = {
        "step_name": r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$",
        "journey_name": r"^[a-zA-Z][a-zA-Z0-9_-]{0,127}$",
        "checkpoint_name": r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$",
        "path_name": r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$",
        "tag": r"^[a-zA-Z][a-zA-Z0-9_-]{0,31}$",
        "http_method": r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|CONNECT|TRACE)$",
        "identifier": r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$",
        "safe_string": r"^[\w\s\-.,:;!?@#$%&*()+={}\[\]|\\<>/]{0,1000}$",
        "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        "uuid": r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        "alphanumeric": r"^[a-zA-Z0-9]+$",
        "snake_case": r"^[a-z][a-z0-9_]*$",
        "kebab_case": r"^[a-z][a-z0-9-]*$",
    }

    MAX_URL_LENGTH: Final[int] = 2048
    MAX_STRING_LENGTH: Final[int] = 10000
    MAX_STEPS: Final[int] = 100
    MAX_BRANCHES: Final[int] = 20
    MAX_PATHS_PER_BRANCH: Final[int] = 10
    MAX_HEADER_VALUE_LENGTH: Final[int] = 8192
    MAX_JSON_DEPTH: Final[int] = 10

    DANGEROUS_URL_SCHEMES: Final[frozenset[str]] = frozenset(
        ["javascript", "vbscript", "data", "file", "blob"]
    )

    DANGEROUS_HEADERS: Final[dict[str, str]] = {
        "host": "Host header injection risk",
        "x-forwarded-host": "X-Forwarded-Host injection risk",
        "x-original-url": "X-Original-URL injection risk",
        "x-rewrite-url": "X-Rewrite-URL injection risk",
        "x-host": "X-Host injection risk",
    }

    def __init__(self, strict: bool = True) -> None:
        """Initialize the input validator.

        Args:
            strict: If True, raise exceptions on validation failure.
                   If False, return False and collect errors.
        """
        self.strict = strict
        self._errors: list[InputValidationError] = []

    def validate_step(self, step_data: dict[str, Any]) -> bool:
        """Validate a step configuration dictionary.

        Validates that a step has required fields (name, action) and that
        optional fields (timeout, retries, description) meet constraints.

        Args:
            step_data: Dictionary containing step configuration.

        Returns:
            True if validation passes.

        Raises:
            InputValidationError: If strict mode and validation fails.

        Example:
            >>> validator.validate_step({
            ...     "name": "login_step",
            ...     "action": "click",
            ...     "timeout": 30
            ... })
            True
        """
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

        if "expect_failure" in step_data:
            if not isinstance(step_data["expect_failure"], bool):
                self._errors.append(InputValidationError("expect_failure", "Must be a boolean"))

        if self._errors:
            if self.strict:
                raise self._errors[0]
            return False
        return True

    def validate_journey(self, journey_data: dict[str, Any]) -> bool:
        """Validate a journey configuration dictionary.

        Validates journey structure including required fields, step count,
        tag formats, and timeout constraints.

        Args:
            journey_data: Dictionary containing journey configuration.

        Returns:
            True if validation passes.

        Raises:
            InputValidationError: If strict mode and validation fails.

        Example:
            >>> validator.validate_journey({
            ...     "name": "user_registration_flow",
            ...     "steps": [{"name": "step1", "action": "click"}]
            ... })
            True
        """
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

        if "parallel" in journey_data:
            if not isinstance(journey_data["parallel"], bool):
                self._errors.append(InputValidationError("parallel", "Must be a boolean"))

        if self._errors:
            if self.strict:
                raise self._errors[0]
            return False
        return True

    def validate_branch(self, branch_data: dict[str, Any]) -> bool:
        """Validate a branch configuration dictionary.

        Branches define conditional paths based on checkpoint states.
        This validates checkpoint references and path configurations.

        Args:
            branch_data: Dictionary containing branch configuration.

        Returns:
            True if validation passes.

        Raises:
            InputValidationError: If strict mode and validation fails.

        Example:
            >>> validator.validate_branch({
            ...     "checkpoint_name": "after_login",
            ...     "paths": [{"name": "success_path", "steps": []}]
            ... })
            True
        """
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

        if "condition" in branch_data:
            if not isinstance(branch_data["condition"], (str, dict)):
                self._errors.append(
                    InputValidationError("condition", "Condition must be string or dict")
                )

        if self._errors:
            if self.strict:
                raise self._errors[0]
            return False
        return True

    def validate_url(self, url: str, field_name: str = "url") -> bool:
        """Validate a URL string for safety and correctness.

        Checks URL format, scheme safety, and prevents dangerous protocols
        like javascript:, data:, and vbscript:.

        Args:
            url: The URL string to validate.
            field_name: Name of the field for error messages.

        Returns:
            True if the URL is valid and safe.

        Raises:
            InputValidationError: If strict mode and URL is invalid.

        Example:
            >>> validator.validate_url("https://api.example.com/users")
            True
            >>> validator.validate_url("javascript:alert(1)")  # Raises error
        """
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
            if parsed.scheme.lower() not in ("http", "https"):
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

        for scheme in self.DANGEROUS_URL_SCHEMES:
            pattern = rf"^{scheme}:"
            if re.search(pattern, url, re.IGNORECASE):
                if self.strict:
                    raise InputValidationError(
                        field_name, f"URL contains dangerous protocol: {scheme}"
                    )
                return False

        return True

    def validate_headers(self, headers: dict[str, str]) -> bool:
        """Validate HTTP headers for security vulnerabilities.

        Checks for header injection risks, dangerous headers, and
        malformed header names.

        Args:
            headers: Dictionary of HTTP headers to validate.

        Returns:
            True if all headers are valid and safe.

        Raises:
            InputValidationError: If strict mode and headers are invalid.

        Example:
            >>> validator.validate_headers({"Content-Type": "application/json"})
            True
            >>> validator.validate_headers({"Host": "evil.com"})  # Raises error
        """
        for header_name, warning in self.DANGEROUS_HEADERS.items():
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

            if len(str(value)) > self.MAX_HEADER_VALUE_LENGTH:
                if self.strict:
                    raise InputValidationError(f"header:{name}", "Header value too long")
                return False

            if "\n" in str(value) or "\r" in str(value):
                if self.strict:
                    raise InputValidationError(
                        f"header:{name}", "Header value contains newline characters"
                    )
                return False

        return True

    def validate_step_params(self, params: dict[str, Any]) -> bool:
        """Validate step parameters for safety and correctness.

        Ensures parameter keys are valid identifiers and values
        meet length constraints.

        Args:
            params: Dictionary of step parameters.

        Returns:
            True if all parameters are valid.

        Raises:
            InputValidationError: If strict mode and params are invalid.

        Example:
            >>> validator.validate_step_params({"timeout": 30, "retry_count": 3})
            True
        """
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

            if isinstance(value, (dict, list)):
                self._validate_json_depth(value, key, 0)

        if self._errors:
            if self.strict:
                raise self._errors[0]
            return False
        return True

    def validate_json_depth(self, data: Any, max_depth: int = 10) -> ValidationResult:
        """Validate JSON data structure depth.

        Deeply nested JSON can cause stack overflow or DoS attacks.

        Args:
            data: JSON-serializable data to validate.
            max_depth: Maximum allowed nesting depth.

        Returns:
            ValidationResult with is_valid and depth info.
        """
        result = ValidationResult()

        def get_depth(obj: Any, current: int) -> int:
            if current > max_depth:
                return current
            if isinstance(obj, dict):
                if not obj:
                    return current
                return max(get_depth(v, current + 1) for v in obj.values())
            if isinstance(obj, list):
                if not obj:
                    return current
                return max(get_depth(item, current + 1) for item in obj)
            return current

        actual_depth = get_depth(data, 0)
        if actual_depth > max_depth:
            result.is_valid = False
            result.errors.append(
                InputValidationError("json", f"JSON depth {actual_depth} exceeds max {max_depth}")
            )
        result.sanitized_value = data
        return result

    def validate_identifier(self, value: str, field_name: str = "identifier") -> bool:
        """Validate a generic identifier string.

        Args:
            value: The identifier string to validate.
            field_name: Field name for error messages.

        Returns:
            True if identifier is valid.

        Raises:
            InputValidationError: If strict mode and invalid.
        """
        if not value:
            if self.strict:
                raise InputValidationError(field_name, "Identifier cannot be empty")
            return False

        if not re.match(self.PATTERNS["identifier"], value):
            if self.strict:
                raise InputValidationError(field_name, f"Invalid identifier format: {value}")
            return False

        return True

    def validate_email(self, email: str, field_name: str = "email") -> bool:
        """Validate an email address format.

        Args:
            email: The email address to validate.
            field_name: Field name for error messages.

        Returns:
            True if email format is valid.

        Raises:
            InputValidationError: If strict mode and invalid.
        """
        if not email:
            if self.strict:
                raise InputValidationError(field_name, "Email is required")
            return False

        if len(email) > 254:
            if self.strict:
                raise InputValidationError(field_name, "Email exceeds max length of 254")
            return False

        if not re.match(self.PATTERNS["email"], email, re.IGNORECASE):
            if self.strict:
                raise InputValidationError(field_name, f"Invalid email format: {email}")
            return False

        return True

    def sanitize_string(self, value: str, max_length: int | None = None) -> str:
        """Sanitize a string value by removing dangerous characters.

        Removes control characters and truncates to maximum length.

        Args:
            value: The string to sanitize.
            max_length: Maximum allowed length (defaults to MAX_STRING_LENGTH).

        Returns:
            Sanitized string value.

        Example:
            >>> validator.sanitize_string("hello\\x00world")
            'helloworld'
        """
        max_len = max_length or self.MAX_STRING_LENGTH
        sanitized = value[:max_len]
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", sanitized)
        return sanitized.strip()

    def validate_with_rule(self, value: Any, rule: ValidationRule) -> ValidationResult:
        """Validate a value against a ValidationRule.

        Args:
            value: The value to validate.
            rule: The validation rule to apply.

        Returns:
            ValidationResult with validation outcome.
        """
        result = ValidationResult()

        if value is None or value == "":
            if rule.required:
                result.is_valid = False
                result.errors.append(InputValidationError(rule.name, f"{rule.name} is required"))
            return result

        if rule.pattern and isinstance(value, str):
            if not re.match(rule.pattern, value):
                result.is_valid = False
                result.errors.append(
                    InputValidationError(rule.name, f"Value does not match pattern: {rule.pattern}")
                )

        if rule.min_length is not None and isinstance(value, str):
            if len(value) < rule.min_length:
                result.is_valid = False
                result.errors.append(
                    InputValidationError(rule.name, f"Minimum length is {rule.min_length}")
                )

        if rule.max_length is not None and isinstance(value, str):
            if len(value) > rule.max_length:
                result.warnings.append(f"Value truncated to {rule.max_length} characters")
                result.sanitized_value = value[: rule.max_length]

        if rule.allowed_values is not None:
            if value not in rule.allowed_values:
                result.is_valid = False
                result.errors.append(
                    InputValidationError(rule.name, f"Value must be one of: {rule.allowed_values}")
                )

        if rule.custom_validator is not None:
            try:
                if not rule.custom_validator(value):
                    result.is_valid = False
                    result.errors.append(
                        InputValidationError(rule.name, "Custom validation failed")
                    )
            except Exception as e:
                result.is_valid = False
                result.errors.append(InputValidationError(rule.name, f"Validation error: {e}"))

        if result.sanitized_value is None:
            result.sanitized_value = value

        return result

    def _validate_pattern(self, pattern_name: str, value: str, field_name: str) -> None:
        """Validate a value against a named pattern.

        Args:
            pattern_name: Key from PATTERNS dict.
            value: The string value to validate.
            field_name: Field name for error messages.
        """
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
        """Validate string length constraints.

        Args:
            value: The string to validate.
            field_name: Field name for error messages.
            min_len: Minimum required length.
            max_len: Maximum allowed length.
        """
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
        """Validate numeric range constraints.

        Args:
            value: The numeric value to validate.
            field_name: Field name for error messages.
            min_val: Minimum allowed value.
            max_val: Maximum allowed value.
        """
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
        """Validate a path within a branch.

        Args:
            path_data: Dictionary containing path configuration.
            field_prefix: Prefix for field names in error messages.
        """
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

    def _validate_json_depth(self, data: Any, field_name: str, current_depth: int) -> None:
        """Recursively validate JSON depth.

        Args:
            data: The data structure to check.
            field_name: Field name for error messages.
            current_depth: Current nesting depth.
        """
        if current_depth > self.MAX_JSON_DEPTH:
            self._errors.append(
                InputValidationError(
                    field_name, f"JSON nesting exceeds max depth of {self.MAX_JSON_DEPTH}"
                )
            )
            return

        if isinstance(data, dict):
            for key, value in data.items():
                self._validate_json_depth(value, f"{field_name}.{key}", current_depth + 1)
        elif isinstance(data, list):
            for i, item in enumerate(data):
                self._validate_json_depth(item, f"{field_name}[{i}]", current_depth + 1)

    @property
    def errors(self) -> list[InputValidationError]:
        """Get a copy of accumulated validation errors.

        Returns:
            List of InputValidationError instances.
        """
        return self._errors.copy()

    def clear_errors(self) -> None:
        """Clear accumulated validation errors."""
        self._errors = []
