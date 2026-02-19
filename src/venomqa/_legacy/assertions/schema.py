"""JSON Schema and data validation assertions for VenomQA.

Provides assertion functions for validating data against schemas,
format patterns, and structural constraints.

Example:
    >>> from venomqa.assertions import assert_matches_schema, assert_valid_email
    >>> assert_matches_schema(data, {"type": "object", "properties": {"id": {"type": "integer"}}})
    >>> assert_valid_email("user@example.com")
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from re import Pattern
from typing import Any

from venomqa.assertions.expect import AssertionFailed


class SchemaAssertionError(AssertionFailed):
    """Raised when a schema assertion fails."""

    pass


EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(
    r"^https?://"
    r"(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+"
    r"[A-Z]{2,6}"
    r"(?::[0-9]+)?"
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def assert_matches_schema(data: Any, schema: dict[str, Any]) -> None:
    """Assert data matches JSON Schema specification.

    Supports a subset of JSON Schema for validation.

    Args:
        data: Data to validate.
        schema: JSON Schema dictionary.

    Raises:
        SchemaAssertionError: If data doesn't match schema.

    Example:
        >>> schema = {"type": "object", "properties": {"id": {"type": "integer"}}}
        >>> assert_matches_schema({"id": 1}, schema)
    """
    errors = _validate_against_schema(data, schema, "$")
    if errors:
        raise SchemaAssertionError(
            f"Schema validation failed: {'; '.join(errors[:3])}",
            actual=data,
            expected=schema,
        )


def _validate_against_schema(
    data: Any,
    schema: dict[str, Any],
    path: str,
) -> list[str]:
    """Validate data against schema, returning list of errors."""
    errors = []

    schema_type = schema.get("type")
    if schema_type:
        if not _check_type(data, schema_type):
            errors.append(f"{path}: expected type {schema_type}, got {type(data).__name__}")
            return errors

    if schema_type == "object" or (schema_type is None and isinstance(data, dict)):
        errors.extend(_validate_object(data, schema, path))
    elif schema_type == "array" or (schema_type is None and isinstance(data, list)):
        errors.extend(_validate_array(data, schema, path))
    elif schema_type in ("string", "number", "integer"):
        errors.extend(_validate_primitive(data, schema, path))

    if "enum" in schema:
        if data not in schema["enum"]:
            errors.append(f"{path}: value {data!r} not in enum {schema['enum']}")

    if "const" in schema:
        if data != schema["const"]:
            errors.append(f"{path}: expected {schema['const']!r}, got {data!r}")

    return errors


def _check_type(data: Any, schema_type: str | list[str]) -> bool:
    """Check if data matches the expected type."""
    type_mapping = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }

    if isinstance(schema_type, list):
        return any(_check_type(data, t) for t in schema_type)

    expected = type_mapping.get(schema_type)
    if expected is None:
        return True

    if schema_type == "number":
        return isinstance(data, (int, float)) and not isinstance(data, bool)
    if schema_type == "integer":
        return isinstance(data, int) and not isinstance(data, bool)

    return isinstance(data, expected)


def _validate_object(data: dict, schema: dict[str, Any], path: str) -> list[str]:
    """Validate object against schema."""
    errors = []

    properties = schema.get("properties", {})
    required = schema.get("required", [])
    additional_props = schema.get("additionalProperties", True)

    for prop in required:
        if prop not in data:
            errors.append(f"{path}: missing required property {prop!r}")

    for key, value in data.items():
        if key in properties:
            errors.extend(_validate_against_schema(value, properties[key], f"{path}.{key}"))
        elif additional_props is False:
            errors.append(f"{path}.{key}: additional properties not allowed")
        elif isinstance(additional_props, dict):
            errors.extend(_validate_against_schema(value, additional_props, f"{path}.{key}"))

    min_props = schema.get("minProperties")
    if min_props is not None and len(data) < min_props:
        errors.append(f"{path}: object has {len(data)} properties, minimum is {min_props}")

    max_props = schema.get("maxProperties")
    if max_props is not None and len(data) > max_props:
        errors.append(f"{path}: object has {len(data)} properties, maximum is {max_props}")

    return errors


def _validate_array(data: list, schema: dict[str, Any], path: str) -> list[str]:
    """Validate array against schema."""
    errors = []

    items = schema.get("items")
    min_items = schema.get("minItems")
    max_items = schema.get("maxItems")
    unique = schema.get("uniqueItems", False)

    if min_items is not None and len(data) < min_items:
        errors.append(f"{path}: array has {len(data)} items, minimum is {min_items}")

    if max_items is not None and len(data) > max_items:
        errors.append(f"{path}: array has {len(data)} items, maximum is {max_items}")

    if unique and len(data) != len({str(x) for x in data}):
        errors.append(f"{path}: array items must be unique")

    if items is not None:
        for i, item in enumerate(data):
            errors.extend(_validate_against_schema(item, items, f"{path}[{i}]"))

    return errors


def _validate_primitive(data: Any, schema: dict[str, Any], path: str) -> list[str]:
    """Validate primitive value against schema."""
    errors = []

    if isinstance(data, str):
        min_len = schema.get("minLength")
        max_len = schema.get("maxLength")
        pattern = schema.get("pattern")
        fformat = schema.get("format")

        if min_len is not None and len(data) < min_len:
            errors.append(f"{path}: string length {len(data)} below minimum {min_len}")

        if max_len is not None and len(data) > max_len:
            errors.append(f"{path}: string length {len(data)} above maximum {max_len}")

        if pattern is not None:
            if not re.search(pattern, data):
                errors.append(f"{path}: string {data!r} doesn't match pattern {pattern!r}")

        if fformat is not None:
            format_error = _validate_format(data, fformat)
            if format_error:
                errors.append(f"{path}: {format_error}")

    elif isinstance(data, (int, float)):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        exclusive_min = schema.get("exclusiveMinimum")
        exclusive_max = schema.get("exclusiveMaximum")
        multiple_of = schema.get("multipleOf")

        if minimum is not None and data < minimum:
            errors.append(f"{path}: value {data} below minimum {minimum}")

        if maximum is not None and data > maximum:
            errors.append(f"{path}: value {data} above maximum {maximum}")

        if exclusive_min is not None and data <= exclusive_min:
            errors.append(f"{path}: value {data} not above exclusive minimum {exclusive_min}")

        if exclusive_max is not None and data >= exclusive_max:
            errors.append(f"{path}: value {data} not below exclusive maximum {exclusive_max}")

        if multiple_of is not None:
            if not (
                data % multiple_of == 0
                if isinstance(data, int)
                else data / multiple_of == int(data / multiple_of)
            ):
                errors.append(f"{path}: value {data} not a multiple of {multiple_of}")

    return errors


def _validate_format(value: str, fformat: str) -> str | None:
    """Validate string format. Returns error message or None."""
    if fformat == "email":
        if not EMAIL_PATTERN.match(value):
            return f"invalid email format: {value!r}"
    elif fformat == "uuid":
        if not UUID_PATTERN.match(value):
            return f"invalid UUID format: {value!r}"
    elif fformat == "uri" or fformat == "url":
        if not URL_PATTERN.match(value):
            return f"invalid URL format: {value!r}"
    elif fformat == "date":
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            return f"invalid date format: {value!r}"
    elif fformat == "date-time":
        if not ISO_DATETIME_PATTERN.match(value):
            return f"invalid datetime format: {value!r}"
    elif fformat == "hostname":
        if not re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$", value):
            return f"invalid hostname: {value!r}"
    elif fformat == "ipv4":
        parts = value.split(".")
        if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            return f"invalid IPv4 address: {value!r}"

    return None


def assert_valid_email(value: str) -> None:
    """Assert string is a valid email address.

    Args:
        value: String to validate.

    Raises:
        SchemaAssertionError: If not a valid email.

    Example:
        >>> assert_valid_email("user@example.com")
    """
    if not EMAIL_PATTERN.match(value):
        raise SchemaAssertionError(
            f"Invalid email address: {value!r}",
            actual=value,
            expected="valid email",
        )


def assert_valid_uuid(value: str) -> None:
    """Assert string is a valid UUID.

    Args:
        value: String to validate.

    Raises:
        SchemaAssertionError: If not a valid UUID.

    Example:
        >>> assert_valid_uuid("550e8400-e29b-41d4-a716-446655440000")
    """
    try:
        uuid.UUID(value)
    except ValueError:
        raise SchemaAssertionError(
            f"Invalid UUID: {value!r}",
            actual=value,
            expected="valid UUID",
        ) from None


def assert_valid_url(value: str, require_https: bool = False) -> None:
    """Assert string is a valid URL.

    Args:
        value: String to validate.
        require_https: If True, URL must use HTTPS.

    Raises:
        SchemaAssertionError: If not a valid URL.

    Example:
        >>> assert_valid_url("https://example.com/path")
    """
    if not URL_PATTERN.match(value):
        raise SchemaAssertionError(
            f"Invalid URL: {value!r}",
            actual=value,
            expected="valid URL",
        )

    if require_https and not value.lower().startswith("https://"):
        raise SchemaAssertionError(
            f"URL must use HTTPS: {value!r}",
            actual=value,
            expected="HTTPS URL",
        )


def assert_valid_iso_date(value: str) -> None:
    """Assert string is a valid ISO 8601 date (YYYY-MM-DD).

    Args:
        value: String to validate.

    Raises:
        SchemaAssertionError: If not a valid date.

    Example:
        >>> assert_valid_iso_date("2024-01-15")
    """
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise SchemaAssertionError(
            f"Invalid ISO date: {value!r}",
            actual=value,
            expected="YYYY-MM-DD",
        ) from None


def assert_valid_iso_datetime(value: str) -> None:
    """Assert string is a valid ISO 8601 datetime.

    Args:
        value: String to validate.

    Raises:
        SchemaAssertionError: If not a valid datetime.

    Example:
        >>> assert_valid_iso_datetime("2024-01-15T10:30:00Z")
    """
    if not ISO_DATETIME_PATTERN.match(value):
        raise SchemaAssertionError(
            f"Invalid ISO datetime: {value!r}",
            actual=value,
            expected="ISO 8601 datetime",
        )


def assert_is_integer(value: Any) -> None:
    """Assert value is an integer.

    Args:
        value: Value to check.

    Raises:
        SchemaAssertionError: If not an integer.

    Example:
        >>> assert_is_integer(42)
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise SchemaAssertionError(
            f"Expected integer, got {type(value).__name__}: {value!r}",
            actual=type(value).__name__,
            expected="integer",
        )


def assert_is_positive_integer(value: Any) -> None:
    """Assert value is a positive integer (> 0).

    Args:
        value: Value to check.

    Raises:
        SchemaAssertionError: If not a positive integer.

    Example:
        >>> assert_is_positive_integer(42)
    """
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise SchemaAssertionError(
            f"Expected positive integer, got {value!r}",
            actual=value,
            expected="positive integer",
        )


def assert_is_non_negative_integer(value: Any) -> None:
    """Assert value is a non-negative integer (>= 0).

    Args:
        value: Value to check.

    Raises:
        SchemaAssertionError: If not a non-negative integer.

    Example:
        >>> assert_is_non_negative_integer(0)
    """
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SchemaAssertionError(
            f"Expected non-negative integer, got {value!r}",
            actual=value,
            expected="non-negative integer",
        )


def assert_is_number(value: Any) -> None:
    """Assert value is a number (int or float).

    Args:
        value: Value to check.

    Raises:
        SchemaAssertionError: If not a number.

    Example:
        >>> assert_is_number(3.14)
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise SchemaAssertionError(
            f"Expected number, got {type(value).__name__}: {value!r}",
            actual=type(value).__name__,
            expected="number",
        )


def assert_is_string(value: Any) -> None:
    """Assert value is a string.

    Args:
        value: Value to check.

    Raises:
        SchemaAssertionError: If not a string.

    Example:
        >>> assert_is_string("hello")
    """
    if not isinstance(value, str):
        raise SchemaAssertionError(
            f"Expected string, got {type(value).__name__}: {value!r}",
            actual=type(value).__name__,
            expected="string",
        )


def assert_is_boolean(value: Any) -> None:
    """Assert value is a boolean.

    Args:
        value: Value to check.

    Raises:
        SchemaAssertionError: If not a boolean.

    Example:
        >>> assert_is_boolean(True)
    """
    if not isinstance(value, bool):
        raise SchemaAssertionError(
            f"Expected boolean, got {type(value).__name__}: {value!r}",
            actual=type(value).__name__,
            expected="boolean",
        )


def assert_is_array(value: Any) -> None:
    """Assert value is a list/array.

    Args:
        value: Value to check.

    Raises:
        SchemaAssertionError: If not a list.

    Example:
        >>> assert_is_array([1, 2, 3])
    """
    if not isinstance(value, list):
        raise SchemaAssertionError(
            f"Expected array, got {type(value).__name__}",
            actual=type(value).__name__,
            expected="array",
        )


def assert_is_object(value: Any) -> None:
    """Assert value is a dict/object.

    Args:
        value: Value to check.

    Raises:
        SchemaAssertionError: If not a dict.

    Example:
        >>> assert_is_object({"key": "value"})
    """
    if not isinstance(value, dict):
        raise SchemaAssertionError(
            f"Expected object, got {type(value).__name__}",
            actual=type(value).__name__,
            expected="object",
        )


def assert_in_range(value: int | float, min_val: int | float, max_val: int | float) -> None:
    """Assert value is within inclusive range.

    Args:
        value: Value to check.
        min_val: Minimum allowed value (inclusive).
        max_val: Maximum allowed value (inclusive).

    Raises:
        SchemaAssertionError: If value outside range.

    Example:
        >>> assert_in_range(5, 0, 10)
    """
    if not (min_val <= value <= max_val):
        raise SchemaAssertionError(
            f"Value {value} not in range [{min_val}, {max_val}]",
            actual=value,
            expected=f"[{min_val}, {max_val}]",
        )


def assert_matches_pattern(value: str, pattern: str | Pattern) -> None:
    r"""Assert string matches regex pattern.

    Args:
        value: String to check.
        pattern: Regex pattern (string or compiled).

    Raises:
        SchemaAssertionError: If string doesn't match.

    Example:
        >>> assert_matches_pattern("abc123", r"^abc\d+$")
    """
    if isinstance(pattern, str):
        pattern = re.compile(pattern)

    if not pattern.search(value):
        raise SchemaAssertionError(
            f"String {value!r} doesn't match pattern {pattern.pattern!r}",
            actual=value,
            expected=pattern.pattern,
        )
