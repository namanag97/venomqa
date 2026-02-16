"""Response validation utilities.

This module provides schema validation for API responses.
Supports JSON Schema, Pydantic models, and simple type checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Type, TYPE_CHECKING

if TYPE_CHECKING:
    from venomqa.v1.core.action import ActionResult


@dataclass
class SchemaValidator:
    """Validates response body against a schema.

    Supports multiple validation approaches:
    - JSON Schema (if jsonschema installed)
    - Pydantic model (if pydantic installed)
    - Custom validator function
    - Simple type/field checks

    Example with JSON Schema:
        schema = {
            "type": "object",
            "required": ["id", "name"],
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"},
            }
        }
        validator = SchemaValidator.from_json_schema(schema)

    Example with Pydantic:
        class User(BaseModel):
            id: int
            name: str

        validator = SchemaValidator.from_pydantic(User)

    Example with custom check:
        validator = SchemaValidator(
            check=lambda body: body.get("id") is not None,
            message="Response must have 'id' field"
        )
    """

    check: Callable[[Any], bool]
    message: str = "Schema validation failed"

    def validate(self, result: "ActionResult") -> tuple[bool, str]:
        """Validate an ActionResult's response body.

        Returns:
            (passed, message) tuple.
        """
        if result.response is None:
            return False, "No response to validate"

        body = result.response.body
        try:
            if self.check(body):
                return True, ""
            return False, self.message
        except Exception as e:
            return False, f"Validation error: {e}"

    @classmethod
    def from_json_schema(cls, schema: dict[str, Any]) -> "SchemaValidator":
        """Create validator from JSON Schema.

        Requires: pip install jsonschema
        """
        try:
            import jsonschema
        except ImportError:
            raise ImportError("jsonschema required: pip install jsonschema")

        def check(body: Any) -> bool:
            try:
                jsonschema.validate(body, schema)
                return True
            except jsonschema.ValidationError:
                return False

        return cls(check=check, message="JSON Schema validation failed")

    @classmethod
    def from_pydantic(cls, model: Type[Any]) -> "SchemaValidator":
        """Create validator from Pydantic model.

        Requires: pip install pydantic
        """
        def check(body: Any) -> bool:
            try:
                model.model_validate(body)
                return True
            except Exception:
                return False

        return cls(check=check, message=f"Pydantic validation failed for {model.__name__}")

    @classmethod
    def has_fields(cls, *fields: str) -> "SchemaValidator":
        """Create validator that checks for required fields."""
        def check(body: Any) -> bool:
            if not isinstance(body, dict):
                return False
            return all(f in body for f in fields)

        return cls(
            check=check,
            message=f"Response must have fields: {', '.join(fields)}"
        )

    @classmethod
    def is_list(cls, min_length: int = 0) -> "SchemaValidator":
        """Create validator that checks for list response."""
        def check(body: Any) -> bool:
            return isinstance(body, list) and len(body) >= min_length

        return cls(
            check=check,
            message=f"Response must be list with at least {min_length} items"
        )

    @classmethod
    def matches_type(cls, expected_type: Type[Any]) -> "SchemaValidator":
        """Create validator that checks response type."""
        def check(body: Any) -> bool:
            return isinstance(body, expected_type)

        return cls(
            check=check,
            message=f"Response must be {expected_type.__name__}"
        )


def validate_response(
    result: "ActionResult",
    *validators: SchemaValidator,
) -> tuple[bool, list[str]]:
    """Run multiple validators on a response.

    Returns:
        (all_passed, list_of_error_messages)
    """
    errors = []
    for validator in validators:
        passed, message = validator.validate(result)
        if not passed:
            errors.append(message)
    return len(errors) == 0, errors


# Convenience shortcuts
def has_fields(*fields: str) -> SchemaValidator:
    """Shortcut for SchemaValidator.has_fields()."""
    return SchemaValidator.has_fields(*fields)


def is_list(min_length: int = 0) -> SchemaValidator:
    """Shortcut for SchemaValidator.is_list()."""
    return SchemaValidator.is_list(min_length)


def matches_type(expected_type: Type[Any]) -> SchemaValidator:
    """Shortcut for SchemaValidator.matches_type()."""
    return SchemaValidator.matches_type(expected_type)
