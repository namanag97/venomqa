"""GraphQL code generation for VenomQA.

Generates VenomQA action functions from GraphQL schemas, enabling
automated test scaffolding from schema definitions.

Example:
    >>> from venomqa.graphql import generate_actions_from_schema
    >>>
    >>> # Generate from schema file
    >>> generate_actions_from_schema(
    ...     "schema.graphql",
    ...     output_dir="qa/actions/",
    ... )
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from venomqa.graphql.schema import (
    GraphQLField,
    GraphQLSchemaInfo,
    GraphQLTypeKind,
    load_schema_from_file,
    load_schema_from_introspection,
)


@dataclass
class GeneratedAction:
    """Represents a generated action.

    Attributes:
        name: Function name.
        operation_name: GraphQL operation name.
        operation_type: query, mutation, or subscription.
        query: The GraphQL query string.
        args: Function arguments.
        return_type: Return type hint.
        docstring: Function documentation.
    """

    name: str
    operation_name: str
    operation_type: str
    query: str
    args: list[tuple[str, str, Any | None]]  # (name, type, default)
    return_type: str
    docstring: str


class SchemaParser:
    """Parser for extracting action information from schemas.

    Analyzes GraphQL schemas to identify operations that can be
    converted into VenomQA actions.
    """

    def __init__(self, schema: GraphQLSchemaInfo):
        """Initialize the parser.

        Args:
            schema: The schema to parse.
        """
        self.schema = schema

    def get_query_operations(self) -> list[GraphQLField]:
        """Get all query operations.

        Returns:
            List of query fields.
        """
        query_fields = self.schema.get_query_fields()
        return list(query_fields.values())

    def get_mutation_operations(self) -> list[GraphQLField]:
        """Get all mutation operations.

        Returns:
            List of mutation fields.
        """
        mutation_fields = self.schema.get_mutation_fields()
        return list(mutation_fields.values())

    def get_subscription_operations(self) -> list[GraphQLField]:
        """Get all subscription operations.

        Returns:
            List of subscription fields.
        """
        subscription_fields = self.schema.get_subscription_fields()
        return list(subscription_fields.values())

    def get_all_operations(self) -> dict[str, list[GraphQLField]]:
        """Get all operations organized by type.

        Returns:
            Dictionary with query, mutation, subscription keys.
        """
        return {
            "query": self.get_query_operations(),
            "mutation": self.get_mutation_operations(),
            "subscription": self.get_subscription_operations(),
        }


class ActionGenerator:
    """Generates VenomQA action code from GraphQL operations.

    Produces Python code files with action functions that can be
    used in VenomQA journeys.
    """

    def __init__(
        self,
        schema: GraphQLSchemaInfo,
        module_name: str = "actions",
        include_docstrings: bool = True,
        include_type_hints: bool = True,
    ):
        """Initialize the generator.

        Args:
            schema: The schema to generate from.
            module_name: Name for the generated module.
            include_docstrings: Include docstrings in generated code.
            include_type_hints: Include type hints in generated code.
        """
        self.schema = schema
        self.module_name = module_name
        self.include_docstrings = include_docstrings
        self.include_type_hints = include_type_hints
        self._parser = SchemaParser(schema)

    def generate_action(
        self,
        field: GraphQLField,
        operation_type: str,
    ) -> GeneratedAction:
        """Generate an action from a GraphQL field.

        Args:
            field: The GraphQL field.
            operation_type: query, mutation, or subscription.

        Returns:
            GeneratedAction with all generation details.
        """
        # Generate function name
        func_name = _to_snake_case(field.name)
        operation_name = _to_pascal_case(field.name)

        # Build arguments
        args: list[tuple[str, str, Any | None]] = []
        for arg in field.args:
            arg_name = _to_snake_case(arg.name)
            arg_type = _graphql_to_python_type(arg.type_name, arg.is_list)
            default = None if arg.is_required else "None"
            args.append((arg_name, arg_type, default))

        # Build query
        query = self._build_query(field, operation_type)

        # Build docstring
        docstring = self._build_docstring(field, operation_type)

        return GeneratedAction(
            name=func_name,
            operation_name=operation_name,
            operation_type=operation_type,
            query=query,
            args=args,
            return_type="GraphQLResponse",
            docstring=docstring,
        )

    def _build_query(self, field: GraphQLField, operation_type: str) -> str:
        """Build a GraphQL query string for a field.

        Args:
            field: The field to build a query for.
            operation_type: query, mutation, or subscription.

        Returns:
            GraphQL query string.
        """
        operation_name = _to_pascal_case(field.name)

        # Build variable definitions
        var_defs = []
        var_args = []
        for arg in field.args:
            gql_type = _build_graphql_type(arg.type_name, arg.is_required, arg.is_list)
            var_defs.append(f"${arg.name}: {gql_type}")
            var_args.append(f"{arg.name}: ${arg.name}")

        var_str = ", ".join(var_defs)
        args_str = ", ".join(var_args)

        # Build selection set
        selection = self._build_selection_set(field.type_name)

        # Compose query
        if var_defs:
            query = f"{operation_type} {operation_name}({var_str}) {{\n"
        else:
            query = f"{operation_type} {operation_name} {{\n"

        if args_str:
            query += f"    {field.name}({args_str}) {{\n"
        else:
            query += f"    {field.name} {{\n"

        query += f"        {selection}\n"
        query += "    }\n"
        query += "}"

        return query

    def _build_selection_set(self, type_name: str, depth: int = 0) -> str:
        """Build a selection set for a type.

        Args:
            type_name: The type name.
            depth: Current recursion depth.

        Returns:
            Selection set string.
        """
        if depth > 2:
            return "id"

        type_info = self.schema.get_type(type_name)
        if not type_info:
            return "id"

        # Get scalar and simple fields
        selections = []
        for field_name, field_info in type_info.fields.items():
            if field_info.type_kind in (
                GraphQLTypeKind.SCALAR,
                GraphQLTypeKind.ENUM,
            ):
                selections.append(field_name)
            elif depth < 2:
                nested = self._build_selection_set(field_info.type_name, depth + 1)
                selections.append(f"{field_name} {{ {nested} }}")

        return "\n        ".join(selections[:10])  # Limit fields

    def _build_docstring(self, field: GraphQLField, operation_type: str) -> str:
        """Build a docstring for an action.

        Args:
            field: The field to document.
            operation_type: query, mutation, or subscription.

        Returns:
            Docstring content.
        """
        lines = [f"Execute {operation_type} {field.name}."]

        if field.description:
            lines.append("")
            lines.append(field.description)

        if field.args:
            lines.append("")
            lines.append("Args:")
            for arg in field.args:
                req = "" if arg.is_required else " (optional)"
                lines.append(f"    {_to_snake_case(arg.name)}: {arg.type_name}{req}")

        lines.append("")
        lines.append("Returns:")
        lines.append(f"    GraphQLResponse with {field.type_name} data.")

        return "\n".join(lines)

    def generate_all(self) -> list[GeneratedAction]:
        """Generate actions for all operations.

        Returns:
            List of all generated actions.
        """
        actions = []
        operations = self._parser.get_all_operations()

        for op_type, fields in operations.items():
            for field in fields:
                actions.append(self.generate_action(field, op_type))

        return actions

    def generate_module_code(self) -> str:
        """Generate a complete Python module with all actions.

        Returns:
            Python code as a string.
        """
        actions = self.generate_all()

        lines = [
            '"""Generated VenomQA actions from GraphQL schema.',
            "",
            "This module was auto-generated. Do not edit directly.",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "from typing import Any",
            "",
            "from venomqa.http.graphql import GraphQLClient, GraphQLResponse",
            "from venomqa.graphql import query, mutation, subscription",
            "",
            "",
        ]

        for action in actions:
            lines.extend(self._generate_action_code(action))
            lines.append("")
            lines.append("")

        return "\n".join(lines)

    def _generate_action_code(self, action: GeneratedAction) -> list[str]:
        """Generate Python code for a single action.

        Args:
            action: The action to generate code for.

        Returns:
            List of code lines.
        """
        lines = []

        # Decorator
        decorator_name = action.operation_type
        lines.append(f'@{decorator_name}("{action.operation_name}")')

        # Function signature
        args_parts = ["client: GraphQLClient", "ctx: Any"]
        for arg_name, arg_type, default in action.args:
            if default is not None:
                args_parts.append(f"{arg_name}: {arg_type} = {default}")
            else:
                args_parts.append(f"{arg_name}: {arg_type}")

        args_str = ", ".join(args_parts)
        lines.append(f"def {action.name}({args_str}) -> {action.return_type}:")

        # Docstring
        if self.include_docstrings:
            lines.append(f'    """{action.docstring}')
            lines.append('    """')

        # Build variables dict
        lines.append("    variables = {}")
        for arg_name, _, _ in action.args:
            original_name = _to_camel_case(arg_name)
            lines.append(f'    if {arg_name} is not None:')
            lines.append(f'        variables["{original_name}"] = {arg_name}')

        # Query execution
        lines.append("")
        lines.append("    return client.execute(")
        lines.append("        query='''")
        for query_line in action.query.split("\n"):
            lines.append(f"            {query_line}")
        lines.append("        ''',")
        lines.append("        variables=variables if variables else None,")
        lines.append(f'        operation_name="{action.operation_name}",')
        lines.append("    )")

        return lines


def generate_actions_from_schema(
    schema_source: str | Path | dict[str, Any],
    output_dir: str | Path | None = None,
    module_name: str = "actions",
    include_docstrings: bool = True,
    include_type_hints: bool = True,
) -> str:
    """Generate VenomQA actions from a GraphQL schema.

    Args:
        schema_source: Path to schema file, introspection result, or endpoint.
        output_dir: Directory to write generated files (optional).
        module_name: Name for the generated module.
        include_docstrings: Include docstrings in generated code.
        include_type_hints: Include type hints in generated code.

    Returns:
        Generated Python code as a string.

    Example:
        >>> # Generate from schema file
        >>> code = generate_actions_from_schema("schema.graphql")
        >>>
        >>> # Generate and write to file
        >>> generate_actions_from_schema(
        ...     "schema.graphql",
        ...     output_dir="qa/actions/",
        ... )
    """
    # Load schema
    if isinstance(schema_source, dict):
        schema = load_schema_from_introspection(schema_source)
    elif isinstance(schema_source, (str, Path)):
        path = Path(schema_source)
        if path.exists():
            schema = load_schema_from_file(path)
        else:
            raise FileNotFoundError(f"Schema file not found: {schema_source}")
    else:
        raise ValueError(f"Invalid schema source: {type(schema_source)}")

    # Generate code
    generator = ActionGenerator(
        schema=schema,
        module_name=module_name,
        include_docstrings=include_docstrings,
        include_type_hints=include_type_hints,
    )
    code = generator.generate_module_code()

    # Write to file if output_dir specified
    if output_dir:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        output_file = output_path / f"{module_name}.py"
        output_file.write_text(code)

        # Create __init__.py if it doesn't exist
        init_file = output_path / "__init__.py"
        if not init_file.exists():
            init_file.write_text(f'"""Generated actions package."""\n\nfrom .{module_name} import *\n')

    return code


# Helper functions


def _to_snake_case(name: str) -> str:
    """Convert a name to snake_case.

    Args:
        name: The name to convert.

    Returns:
        snake_case version.
    """
    # Handle acronyms and consecutive capitals
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _to_pascal_case(name: str) -> str:
    """Convert a name to PascalCase.

    Args:
        name: The name to convert.

    Returns:
        PascalCase version.
    """
    if "_" in name:
        parts = name.split("_")
        return "".join(p.capitalize() for p in parts)
    return name[0].upper() + name[1:] if name else ""


def _to_camel_case(name: str) -> str:
    """Convert a name to camelCase.

    Args:
        name: The name to convert.

    Returns:
        camelCase version.
    """
    pascal = _to_pascal_case(name)
    return pascal[0].lower() + pascal[1:] if pascal else ""


def _graphql_to_python_type(gql_type: str, is_list: bool = False) -> str:
    """Convert a GraphQL type to Python type hint.

    Args:
        gql_type: The GraphQL type name.
        is_list: Whether the type is a list.

    Returns:
        Python type hint string.
    """
    type_map = {
        "String": "str",
        "Int": "int",
        "Float": "float",
        "Boolean": "bool",
        "ID": "str",
    }
    python_type = type_map.get(gql_type, "Any")

    if is_list:
        return f"list[{python_type}]"
    return python_type


def _build_graphql_type(type_name: str, is_required: bool, is_list: bool) -> str:
    """Build a GraphQL type string.

    Args:
        type_name: The base type name.
        is_required: Whether the type is non-null.
        is_list: Whether the type is a list.

    Returns:
        GraphQL type string (e.g., "[String!]!").
    """
    if is_list:
        result = f"[{type_name}!]"
    else:
        result = type_name

    if is_required:
        result += "!"

    return result
