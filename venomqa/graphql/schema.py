"""GraphQL schema validation for VenomQA.

Provides schema loading from introspection queries or SDL files,
query validation against the schema, and type-safe variable handling.

Example:
    >>> from venomqa.graphql import SchemaValidator, load_schema_from_file
    >>>
    >>> validator = SchemaValidator(load_schema_from_file("schema.graphql"))
    >>> validator.validate_query('''
    ...     query GetUser($id: ID!) {
    ...         user(id: $id) { id name email }
    ...     }
    ... ''')
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class GraphQLTypeKind(Enum):
    """GraphQL type kinds.

    Represents the different kinds of types in a GraphQL schema.
    """

    SCALAR = "SCALAR"
    OBJECT = "OBJECT"
    INTERFACE = "INTERFACE"
    UNION = "UNION"
    ENUM = "ENUM"
    INPUT_OBJECT = "INPUT_OBJECT"
    LIST = "LIST"
    NON_NULL = "NON_NULL"


@dataclass
class GraphQLField:
    """Represents a GraphQL field.

    Attributes:
        name: The field name.
        type_name: The type of the field.
        type_kind: The kind of the type.
        is_required: Whether the field is non-null.
        is_list: Whether the field is a list.
        args: Arguments the field accepts.
        description: Optional description.
        is_deprecated: Whether the field is deprecated.
        deprecation_reason: Reason for deprecation.
    """

    name: str
    type_name: str
    type_kind: GraphQLTypeKind
    is_required: bool = False
    is_list: bool = False
    args: list[GraphQLField] = field(default_factory=list)
    description: str | None = None
    is_deprecated: bool = False
    deprecation_reason: str | None = None


@dataclass
class GraphQLObjectType:
    """Represents a GraphQL object type.

    Attributes:
        name: The type name.
        kind: The type kind.
        fields: Fields on this type.
        interfaces: Implemented interfaces.
        description: Optional description.
    """

    name: str
    kind: GraphQLTypeKind
    fields: dict[str, GraphQLField] = field(default_factory=dict)
    interfaces: list[str] = field(default_factory=list)
    description: str | None = None


@dataclass
class GraphQLEnumType:
    """Represents a GraphQL enum type.

    Attributes:
        name: The enum name.
        values: Enum values.
        description: Optional description.
    """

    name: str
    values: list[str] = field(default_factory=list)
    description: str | None = None


@dataclass
class GraphQLInputType:
    """Represents a GraphQL input object type.

    Attributes:
        name: The type name.
        fields: Input fields.
        description: Optional description.
    """

    name: str
    fields: dict[str, GraphQLField] = field(default_factory=dict)
    description: str | None = None


@dataclass
class GraphQLSchemaInfo:
    """Represents a GraphQL schema.

    Attributes:
        query_type: Name of the Query type.
        mutation_type: Name of the Mutation type.
        subscription_type: Name of the Subscription type.
        types: All types in the schema.
        enums: Enum types.
        inputs: Input types.
        directives: Schema directives.
    """

    query_type: str | None = None
    mutation_type: str | None = None
    subscription_type: str | None = None
    types: dict[str, GraphQLObjectType] = field(default_factory=dict)
    enums: dict[str, GraphQLEnumType] = field(default_factory=dict)
    inputs: dict[str, GraphQLInputType] = field(default_factory=dict)
    directives: list[str] = field(default_factory=list)

    def get_type(self, name: str) -> GraphQLObjectType | None:
        """Get an object type by name.

        Args:
            name: The type name.

        Returns:
            The type or None if not found.
        """
        return self.types.get(name)

    def get_enum(self, name: str) -> GraphQLEnumType | None:
        """Get an enum type by name.

        Args:
            name: The enum name.

        Returns:
            The enum or None if not found.
        """
        return self.enums.get(name)

    def get_input(self, name: str) -> GraphQLInputType | None:
        """Get an input type by name.

        Args:
            name: The input type name.

        Returns:
            The input type or None if not found.
        """
        return self.inputs.get(name)

    def get_query_fields(self) -> dict[str, GraphQLField]:
        """Get all query fields.

        Returns:
            Dictionary of query field names to fields.
        """
        if self.query_type and self.query_type in self.types:
            return self.types[self.query_type].fields
        return {}

    def get_mutation_fields(self) -> dict[str, GraphQLField]:
        """Get all mutation fields.

        Returns:
            Dictionary of mutation field names to fields.
        """
        if self.mutation_type and self.mutation_type in self.types:
            return self.types[self.mutation_type].fields
        return {}

    def get_subscription_fields(self) -> dict[str, GraphQLField]:
        """Get all subscription fields.

        Returns:
            Dictionary of subscription field names to fields.
        """
        if self.subscription_type and self.subscription_type in self.types:
            return self.types[self.subscription_type].fields
        return {}


class SchemaValidationError(Exception):
    """Raised when schema validation fails.

    Attributes:
        message: The error message.
        errors: List of validation errors.
    """

    def __init__(self, message: str, errors: list[str] | None = None):
        self.message = message
        self.errors = errors or []
        super().__init__(message)


def load_schema_from_introspection(introspection_result: dict[str, Any]) -> GraphQLSchemaInfo:
    """Load a schema from an introspection query result.

    Args:
        introspection_result: Result from an introspection query.

    Returns:
        GraphQLSchemaInfo with parsed schema information.

    Raises:
        SchemaValidationError: If the introspection result is invalid.
    """
    schema = GraphQLSchemaInfo()

    try:
        schema_data = introspection_result.get("data", {}).get("__schema", {})
        if not schema_data:
            # Try direct schema data
            schema_data = introspection_result.get("__schema", introspection_result)

        # Extract root types
        query_type = schema_data.get("queryType", {})
        schema.query_type = query_type.get("name") if query_type else None

        mutation_type = schema_data.get("mutationType", {})
        schema.mutation_type = mutation_type.get("name") if mutation_type else None

        subscription_type = schema_data.get("subscriptionType", {})
        schema.subscription_type = subscription_type.get("name") if subscription_type else None

        # Parse types
        for type_data in schema_data.get("types", []):
            name = type_data.get("name")
            if not name or name.startswith("__"):
                continue

            kind = type_data.get("kind", "OBJECT")

            if kind == "ENUM":
                enum_values = [v.get("name") for v in type_data.get("enumValues", [])]
                schema.enums[name] = GraphQLEnumType(
                    name=name,
                    values=enum_values,
                    description=type_data.get("description"),
                )
            elif kind == "INPUT_OBJECT":
                input_fields = _parse_fields(type_data.get("inputFields", []))
                schema.inputs[name] = GraphQLInputType(
                    name=name,
                    fields=input_fields,
                    description=type_data.get("description"),
                )
            elif kind in ("OBJECT", "INTERFACE"):
                fields = _parse_fields(type_data.get("fields", []))
                interfaces = [i.get("name") for i in type_data.get("interfaces", [])]
                schema.types[name] = GraphQLObjectType(
                    name=name,
                    kind=GraphQLTypeKind(kind),
                    fields=fields,
                    interfaces=interfaces,
                    description=type_data.get("description"),
                )

    except Exception as e:
        raise SchemaValidationError(f"Failed to parse introspection result: {e}") from e

    return schema


def _parse_fields(fields_data: list[dict[str, Any]]) -> dict[str, GraphQLField]:
    """Parse fields from introspection data.

    Args:
        fields_data: List of field data dictionaries.

    Returns:
        Dictionary of field names to GraphQLField objects.
    """
    fields: dict[str, GraphQLField] = {}

    for field_data in fields_data:
        name = field_data.get("name")
        if not name:
            continue

        type_info = _extract_type_info(field_data.get("type", {}))
        args = []

        for arg_data in field_data.get("args", []):
            arg_type_info = _extract_type_info(arg_data.get("type", {}))
            args.append(
                GraphQLField(
                    name=arg_data.get("name", ""),
                    type_name=arg_type_info["name"],
                    type_kind=GraphQLTypeKind(arg_type_info["kind"]),
                    is_required=arg_type_info["is_required"],
                    is_list=arg_type_info["is_list"],
                    description=arg_data.get("description"),
                )
            )

        fields[name] = GraphQLField(
            name=name,
            type_name=type_info["name"],
            type_kind=GraphQLTypeKind(type_info["kind"]),
            is_required=type_info["is_required"],
            is_list=type_info["is_list"],
            args=args,
            description=field_data.get("description"),
            is_deprecated=field_data.get("isDeprecated", False),
            deprecation_reason=field_data.get("deprecationReason"),
        )

    return fields


def _extract_type_info(type_data: dict[str, Any]) -> dict[str, Any]:
    """Extract type information from nested type structure.

    Args:
        type_data: Type data from introspection.

    Returns:
        Dictionary with type name, kind, is_required, is_list.
    """
    is_required = False
    is_list = False
    kind = type_data.get("kind", "SCALAR")
    name = type_data.get("name", "Unknown")

    # Unwrap NON_NULL and LIST modifiers
    current = type_data
    while current:
        current_kind = current.get("kind")
        if current_kind == "NON_NULL":
            is_required = True
            current = current.get("ofType", {})
        elif current_kind == "LIST":
            is_list = True
            current = current.get("ofType", {})
        else:
            kind = current_kind or "SCALAR"
            name = current.get("name", "Unknown")
            break

    return {
        "name": name,
        "kind": kind,
        "is_required": is_required,
        "is_list": is_list,
    }


def load_schema_from_file(file_path: str | Path) -> GraphQLSchemaInfo:
    """Load a schema from a GraphQL SDL file.

    Args:
        file_path: Path to the .graphql or .json schema file.

    Returns:
        GraphQLSchemaInfo with parsed schema information.

    Raises:
        SchemaValidationError: If the file is invalid.
        FileNotFoundError: If the file doesn't exist.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"Schema file not found: {file_path}")

    content = path.read_text()

    # Check if it's a JSON introspection result
    if path.suffix == ".json":
        try:
            data = json.loads(content)
            return load_schema_from_introspection(data)
        except json.JSONDecodeError as e:
            raise SchemaValidationError(f"Invalid JSON schema file: {e}") from e

    # Parse SDL
    return _parse_sdl(content)


def _parse_sdl(sdl: str) -> GraphQLSchemaInfo:
    """Parse GraphQL SDL (Schema Definition Language).

    Args:
        sdl: The SDL string.

    Returns:
        GraphQLSchemaInfo with parsed schema information.
    """
    schema = GraphQLSchemaInfo()

    # Remove comments
    sdl = re.sub(r"#.*$", "", sdl, flags=re.MULTILINE)

    # Parse schema directive
    schema_match = re.search(
        r"schema\s*\{([^}]+)\}",
        sdl,
        re.DOTALL,
    )
    if schema_match:
        schema_body = schema_match.group(1)
        query_match = re.search(r"query\s*:\s*(\w+)", schema_body)
        if query_match:
            schema.query_type = query_match.group(1)
        mutation_match = re.search(r"mutation\s*:\s*(\w+)", schema_body)
        if mutation_match:
            schema.mutation_type = mutation_match.group(1)
        subscription_match = re.search(r"subscription\s*:\s*(\w+)", schema_body)
        if subscription_match:
            schema.subscription_type = subscription_match.group(1)
    else:
        # Default root types
        schema.query_type = "Query"
        schema.mutation_type = "Mutation"
        schema.subscription_type = "Subscription"

    # Parse type definitions
    type_pattern = r"type\s+(\w+)(?:\s+implements\s+([\w\s&,]+))?\s*\{([^}]+)\}"
    for match in re.finditer(type_pattern, sdl, re.DOTALL):
        name = match.group(1)
        implements = match.group(2)
        body = match.group(3)

        interfaces = []
        if implements:
            interfaces = [i.strip() for i in re.split(r"[&,]", implements)]

        fields = _parse_sdl_fields(body)
        schema.types[name] = GraphQLObjectType(
            name=name,
            kind=GraphQLTypeKind.OBJECT,
            fields=fields,
            interfaces=interfaces,
        )

    # Parse interface definitions
    interface_pattern = r"interface\s+(\w+)\s*\{([^}]+)\}"
    for match in re.finditer(interface_pattern, sdl, re.DOTALL):
        name = match.group(1)
        body = match.group(2)
        fields = _parse_sdl_fields(body)
        schema.types[name] = GraphQLObjectType(
            name=name,
            kind=GraphQLTypeKind.INTERFACE,
            fields=fields,
        )

    # Parse enum definitions
    enum_pattern = r"enum\s+(\w+)\s*\{([^}]+)\}"
    for match in re.finditer(enum_pattern, sdl, re.DOTALL):
        name = match.group(1)
        body = match.group(2)
        values = [v.strip() for v in body.split() if v.strip()]
        schema.enums[name] = GraphQLEnumType(name=name, values=values)

    # Parse input definitions
    input_pattern = r"input\s+(\w+)\s*\{([^}]+)\}"
    for match in re.finditer(input_pattern, sdl, re.DOTALL):
        name = match.group(1)
        body = match.group(2)
        fields = _parse_sdl_fields(body, is_input=True)
        schema.inputs[name] = GraphQLInputType(name=name, fields=fields)

    return schema


def _parse_sdl_fields(body: str, is_input: bool = False) -> dict[str, GraphQLField]:
    """Parse fields from SDL body.

    Args:
        body: The field definitions.
        is_input: Whether this is an input type.

    Returns:
        Dictionary of field names to GraphQLField objects.
    """
    fields: dict[str, GraphQLField] = {}

    # Field pattern with optional arguments
    field_pattern = r"(\w+)(?:\s*\(([^)]*)\))?\s*:\s*([^\n]+)"

    for match in re.finditer(field_pattern, body):
        name = match.group(1)
        args_str = match.group(2) or ""
        type_str = match.group(3).strip()

        # Parse type
        type_info = _parse_sdl_type(type_str)

        # Parse arguments
        args = []
        if args_str and not is_input:
            for arg_match in re.finditer(r"(\w+)\s*:\s*([^,\)]+)", args_str):
                arg_name = arg_match.group(1)
                arg_type_str = arg_match.group(2).strip()
                arg_type_info = _parse_sdl_type(arg_type_str)
                args.append(
                    GraphQLField(
                        name=arg_name,
                        type_name=arg_type_info["name"],
                        type_kind=arg_type_info["kind"],
                        is_required=arg_type_info["is_required"],
                        is_list=arg_type_info["is_list"],
                    )
                )

        fields[name] = GraphQLField(
            name=name,
            type_name=type_info["name"],
            type_kind=type_info["kind"],
            is_required=type_info["is_required"],
            is_list=type_info["is_list"],
            args=args,
        )

    return fields


def _parse_sdl_type(type_str: str) -> dict[str, Any]:
    """Parse SDL type string.

    Args:
        type_str: The type string (e.g., "[String!]!").

    Returns:
        Dictionary with type name, kind, is_required, is_list.
    """
    type_str = type_str.strip()
    is_required = type_str.endswith("!")
    if is_required:
        type_str = type_str[:-1]

    is_list = type_str.startswith("[")
    if is_list:
        type_str = type_str[1:-1]  # Remove brackets
        if type_str.endswith("!"):
            type_str = type_str[:-1]

    # Determine kind
    scalars = {"String", "Int", "Float", "Boolean", "ID"}
    kind = GraphQLTypeKind.SCALAR if type_str in scalars else GraphQLTypeKind.OBJECT

    return {
        "name": type_str,
        "kind": kind,
        "is_required": is_required,
        "is_list": is_list,
    }


class SchemaValidator:
    """Validates GraphQL queries against a schema.

    Provides build-time validation of queries and mutations,
    including field existence, argument types, and variable usage.

    Example:
        >>> validator = SchemaValidator(schema)
        >>> validator.validate_query('''
        ...     query GetUser($id: ID!) {
        ...         user(id: $id) { name email }
        ...     }
        ... ''')
    """

    def __init__(self, schema: GraphQLSchemaInfo):
        """Initialize the validator.

        Args:
            schema: The schema to validate against.
        """
        self.schema = schema

    def validate_query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> list[str]:
        """Validate a GraphQL query against the schema.

        Args:
            query: The GraphQL query string.
            variables: Variables to validate types against.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []

        # Determine operation type
        operation_match = re.search(r"(query|mutation|subscription)\s+(\w+)?", query)
        if not operation_match:
            # Anonymous query
            operation_type = "query"
        else:
            operation_type = operation_match.group(1)

        # Get root type
        if operation_type == "query":
            root_type = self.schema.query_type
        elif operation_type == "mutation":
            root_type = self.schema.mutation_type
        else:
            root_type = self.schema.subscription_type

        if not root_type or root_type not in self.schema.types:
            errors.append(f"No {operation_type} root type defined in schema")
            return errors

        root = self.schema.types[root_type]

        # Extract variable definitions
        var_match = re.search(r"\(([^)]+)\)", query)
        declared_vars: dict[str, str] = {}
        if var_match:
            var_str = var_match.group(1)
            for var_def in re.finditer(r"\$(\w+)\s*:\s*([^,\)]+)", var_str):
                declared_vars[var_def.group(1)] = var_def.group(2).strip()

        # Validate variables if provided
        if variables:
            for var_name, var_value in variables.items():
                if var_name not in declared_vars:
                    errors.append(f"Variable ${var_name} is not declared in query")
                else:
                    var_type = declared_vars[var_name]
                    type_error = self._validate_variable_type(var_name, var_value, var_type)
                    if type_error:
                        errors.append(type_error)

        # Validate selection set
        selection_match = re.search(r"\{([^{}]+(?:\{[^{}]*\}[^{}]*)*)\}", query)
        if selection_match:
            selection_errors = self._validate_selection(
                selection_match.group(1),
                root,
            )
            errors.extend(selection_errors)

        return errors

    def _validate_variable_type(
        self,
        var_name: str,
        var_value: Any,
        expected_type: str,
    ) -> str | None:
        """Validate a variable value against its expected type.

        Args:
            var_name: The variable name.
            var_value: The variable value.
            expected_type: The expected GraphQL type string.

        Returns:
            Error message if invalid, None if valid.
        """
        # Strip non-null modifier for checking
        is_required = expected_type.endswith("!")
        base_type = expected_type.rstrip("!").strip("[]")

        if var_value is None:
            if is_required:
                return f"Variable ${var_name} is required but got null"
            return None

        # Type checking
        if base_type == "String" and not isinstance(var_value, str):
            return f"Variable ${var_name} expected String, got {type(var_value).__name__}"
        if base_type == "Int" and not isinstance(var_value, int):
            return f"Variable ${var_name} expected Int, got {type(var_value).__name__}"
        if base_type == "Float" and not isinstance(var_value, (int, float)):
            return f"Variable ${var_name} expected Float, got {type(var_value).__name__}"
        if base_type == "Boolean" and not isinstance(var_value, bool):
            return f"Variable ${var_name} expected Boolean, got {type(var_value).__name__}"
        if base_type == "ID" and not isinstance(var_value, (str, int)):
            return f"Variable ${var_name} expected ID, got {type(var_value).__name__}"

        # Enum validation
        if base_type in self.schema.enums:
            enum_type = self.schema.enums[base_type]
            if var_value not in enum_type.values:
                return f"Variable ${var_name} has invalid enum value '{var_value}'"

        return None

    def _validate_selection(
        self,
        selection: str,
        parent_type: GraphQLObjectType,
    ) -> list[str]:
        """Validate a selection set against a parent type.

        Args:
            selection: The selection set string.
            parent_type: The parent type to validate against.

        Returns:
            List of validation errors.
        """
        errors: list[str] = []

        # Extract field names (simple approach)
        field_pattern = r"(\w+)(?:\s*\([^)]*\))?\s*(?:\{[^{}]*\})?"
        for match in re.finditer(field_pattern, selection):
            field_name = match.group(1)

            # Skip GraphQL keywords
            if field_name in ("query", "mutation", "subscription", "fragment", "on"):
                continue

            if field_name not in parent_type.fields:
                errors.append(f"Field '{field_name}' not found on type '{parent_type.name}'")

        return errors

    def validate_variables(
        self,
        query: str,
        variables: dict[str, Any],
    ) -> list[str]:
        """Validate variables against query variable definitions.

        Args:
            query: The GraphQL query string.
            variables: Variables to validate.

        Returns:
            List of validation errors.
        """
        errors: list[str] = []

        # Extract variable definitions
        var_match = re.search(r"\(([^)]+)\)", query)
        if not var_match:
            if variables:
                errors.append("Query has no variable definitions but variables were provided")
            return errors

        var_str = var_match.group(1)
        declared_vars: dict[str, str] = {}
        for var_def in re.finditer(r"\$(\w+)\s*:\s*([^,\)]+)", var_str):
            declared_vars[var_def.group(1)] = var_def.group(2).strip()

        # Check required variables are provided
        for var_name, var_type in declared_vars.items():
            is_required = var_type.endswith("!")
            if is_required and var_name not in variables:
                errors.append(f"Required variable ${var_name} is not provided")

        # Check provided variables are declared
        for var_name in variables:
            if var_name not in declared_vars:
                errors.append(f"Variable ${var_name} is not declared in query")

        return errors
