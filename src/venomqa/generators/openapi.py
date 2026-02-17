"""OpenAPI specification parser and code generator.

This module provides functionality to parse OpenAPI 3.0 specifications
and generate VenomQA action functions, fixtures, and test data factories.

Classes:
    OpenAPIGenerator: Main generator class for creating VenomQA code from OpenAPI specs.
    OpenAPISchema: Parsed OpenAPI schema with endpoints and models.
    GeneratedAction: Represents a generated action function.
    GeneratedFixture: Represents a generated fixture function.
    GeneratorConfig: Configuration options for the generator.

Example:
    >>> from venomqa.generators.openapi import OpenAPIGenerator
    >>> generator = OpenAPIGenerator("openapi.yaml")
    >>> generator.generate("./qa/actions/")
"""

from __future__ import annotations

import json
import keyword
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _default_for_type(schema_type: str, fmt: str | None = None) -> Any:
    """Return a sensible default value for a JSON schema type.

    Args:
        schema_type: JSON schema type name.
        fmt: Optional format specifier.

    Returns:
        A default value suitable for the type.
    """
    format_defaults: dict[str, Any] = {
        "email": "test@example.com",
        "date": "2024-01-01",
        "date-time": "2024-01-01T00:00:00Z",
        "uri": "https://example.com",
        "uuid": "00000000-0000-0000-0000-000000000000",
        "password": "TestPassword123!",
    }
    if fmt and fmt in format_defaults:
        return format_defaults[fmt]

    type_defaults: dict[str, Any] = {
        "string": "test_string",
        "integer": 1,
        "number": 1.0,
        "boolean": True,
        "array": [],
        "object": {},
    }
    return type_defaults.get(schema_type, None)


class OpenAPIParseError(Exception):
    """Raised when OpenAPI specification parsing fails."""

    def __init__(self, message: str, path: str | None = None) -> None:
        self.path = path
        super().__init__(message)


@dataclass
class ParameterInfo:
    """Information about an API parameter.

    Attributes:
        name: Parameter name.
        location: Where the parameter is located (path, query, header, cookie).
        required: Whether the parameter is required.
        schema_type: The JSON schema type of the parameter.
        description: Parameter description.
        default: Default value if any.
        enum: List of allowed values if constrained.
        format: Schema format (e.g., 'date-time', 'email').
    """

    name: str
    location: str  # path, query, header, cookie
    required: bool
    schema_type: str
    description: str = ""
    default: Any = None
    enum: list[Any] | None = None
    format: str | None = None

    @property
    def python_type(self) -> str:
        """Get the Python type hint for this parameter."""
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "array": "list",
            "object": "dict",
        }
        base_type = type_map.get(self.schema_type, "Any")
        if not self.required:
            return f"{base_type} | None"
        return base_type


@dataclass
class PropertyInfo:
    """Information about a schema property.

    Attributes:
        name: Property name.
        schema_type: JSON schema type.
        required: Whether the property is required.
        description: Property description.
        default: Default value if any.
        format: Schema format.
        enum: Allowed values if constrained.
        ref: Reference to another schema.
        items: For arrays, the item schema type.
    """

    name: str
    schema_type: str
    required: bool = False
    description: str = ""
    default: Any = None
    format: str | None = None
    enum: list[Any] | None = None
    ref: str | None = None
    items: str | None = None

    @property
    def python_type(self) -> str:
        """Get the Python type hint for this property."""
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "array": "list",
            "object": "dict",
        }
        base_type = type_map.get(self.schema_type, "Any")
        if self.schema_type == "array" and self.items:
            item_type = type_map.get(self.items, "Any")
            base_type = f"list[{item_type}]"
        if not self.required:
            return f"{base_type} | None"
        return base_type

    def get_default_value(self) -> str:
        """Get a default value for this property as a Python expression."""
        if self.default is not None:
            if isinstance(self.default, str):
                return f'"{self.default}"'
            elif isinstance(self.default, bool):
                return str(self.default)
            else:
                return repr(self.default)

        if self.enum and len(self.enum) > 0:
            val = self.enum[0]
            if isinstance(val, str):
                return f'"{val}"'
            return repr(val)

        defaults = {
            "string": '""',
            "integer": "0",
            "number": "0.0",
            "boolean": "False",
            "array": "[]",
            "object": "{}",
        }

        if self.format:
            format_defaults = {
                "email": '"test@example.com"',
                "date": '"2024-01-01"',
                "date-time": '"2024-01-01T00:00:00Z"',
                "uri": '"https://example.com"',
                "uuid": '"00000000-0000-0000-0000-000000000000"',
                "password": '"password123"',
            }
            if self.format in format_defaults:
                return format_defaults[self.format]

        return defaults.get(self.schema_type, "None")


@dataclass
class RequestBodyInfo:
    """Information about a request body.

    Attributes:
        content_type: Media type (e.g., 'application/json').
        required: Whether the body is required.
        schema_ref: Reference to a schema if using $ref.
        properties: List of properties if inline schema.
        description: Request body description.
    """

    content_type: str
    required: bool
    schema_ref: str | None = None
    properties: list[PropertyInfo] = field(default_factory=list)
    description: str = ""


@dataclass
class ResponseInfo:
    """Information about an API response.

    Attributes:
        status_code: HTTP status code.
        description: Response description.
        content_type: Media type of the response.
        schema_ref: Reference to a schema if using $ref.
        properties: List of properties if inline schema.
    """

    status_code: str
    description: str
    content_type: str | None = None
    schema_ref: str | None = None
    properties: list[PropertyInfo] = field(default_factory=list)


@dataclass
class EndpointInfo:
    """Information about an API endpoint.

    Attributes:
        path: URL path (e.g., '/users/{id}').
        method: HTTP method (GET, POST, etc.).
        operation_id: Unique operation identifier.
        summary: Short summary.
        description: Detailed description.
        tags: List of tags for grouping.
        parameters: Path, query, header parameters.
        request_body: Request body information.
        responses: Map of status codes to response info.
        security: Security requirements.
    """

    path: str
    method: str
    operation_id: str
    summary: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    parameters: list[ParameterInfo] = field(default_factory=list)
    request_body: RequestBodyInfo | None = None
    responses: dict[str, ResponseInfo] = field(default_factory=dict)
    security: list[dict[str, list[str]]] = field(default_factory=list)

    @property
    def path_parameters(self) -> list[ParameterInfo]:
        """Get only path parameters."""
        return [p for p in self.parameters if p.location == "path"]

    @property
    def query_parameters(self) -> list[ParameterInfo]:
        """Get only query parameters."""
        return [p for p in self.parameters if p.location == "query"]

    @property
    def header_parameters(self) -> list[ParameterInfo]:
        """Get only header parameters."""
        return [p for p in self.parameters if p.location == "header"]

    @property
    def requires_auth(self) -> bool:
        """Check if endpoint requires authentication."""
        return len(self.security) > 0


@dataclass
class SchemaInfo:
    """Information about a schema/model definition.

    Attributes:
        name: Schema name.
        description: Schema description.
        properties: List of properties.
        required_properties: List of required property names.
        type: Schema type (usually 'object').
    """

    name: str
    description: str = ""
    properties: list[PropertyInfo] = field(default_factory=list)
    required_properties: list[str] = field(default_factory=list)
    type: str = "object"


@dataclass
class OpenAPISchema:
    """Parsed OpenAPI schema.

    Attributes:
        title: API title.
        version: API version.
        description: API description.
        base_url: Base URL for the API.
        endpoints: List of parsed endpoints.
        schemas: Map of schema names to schema info.
        security_schemes: Security scheme definitions.
    """

    title: str
    version: str
    description: str = ""
    base_url: str = ""
    endpoints: list[EndpointInfo] = field(default_factory=list)
    schemas: dict[str, SchemaInfo] = field(default_factory=dict)
    security_schemes: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class GeneratedAction:
    """Represents a generated action function.

    Attributes:
        name: Function name.
        endpoint: The endpoint this action calls.
        code: Generated Python code.
        imports: Required imports.
    """

    name: str
    endpoint: EndpointInfo
    code: str
    imports: set[str] = field(default_factory=set)


@dataclass
class GeneratedFixture:
    """Represents a generated fixture function.

    Attributes:
        name: Fixture name.
        schema: The schema this fixture creates.
        code: Generated Python code.
        imports: Required imports.
    """

    name: str
    schema: SchemaInfo
    code: str
    imports: set[str] = field(default_factory=set)


@dataclass
class GeneratorConfig:
    """Configuration for code generation.

    Attributes:
        output_dir: Directory for generated files.
        actions_file: Filename for actions module.
        fixtures_file: Filename for fixtures module.
        include_docstrings: Whether to generate docstrings.
        include_type_hints: Whether to generate type hints.
        default_timeout: Default timeout for actions.
        group_by_tags: Whether to group actions by tags.
        generate_fixtures: Whether to generate fixture factories.
        fixture_prefix: Prefix for fixture function names.
        action_decorator: Decorator to use for actions.
    """

    output_dir: str = "."
    actions_file: str = "actions.py"
    fixtures_file: str = "fixtures.py"
    include_docstrings: bool = True
    include_type_hints: bool = True
    default_timeout: float | None = None
    group_by_tags: bool = False
    generate_fixtures: bool = True
    fixture_prefix: str = "create_"
    action_decorator: str = "action"


class OpenAPIGenerator:
    """Generator for creating VenomQA code from OpenAPI specifications.

    Parses an OpenAPI 3.0 specification and generates:
    - Action functions for each endpoint
    - Fixture factories for each schema
    - Type hints and docstrings

    Example:
        >>> generator = OpenAPIGenerator("api.yaml")
        >>> generator.generate("./qa/generated/")

        >>> # Or with custom config
        >>> config = GeneratorConfig(
        ...     include_type_hints=True,
        ...     generate_fixtures=True,
        ...     group_by_tags=True,
        ... )
        >>> generator = OpenAPIGenerator("api.yaml", config=config)
        >>> generator.generate("./qa/generated/")

    Attributes:
        spec_path: Path to the OpenAPI specification file.
        config: Generator configuration.
        schema: Parsed OpenAPI schema.
    """

    def __init__(
        self,
        spec_path: str | Path,
        config: GeneratorConfig | None = None,
    ) -> None:
        """Initialize the generator.

        Args:
            spec_path: Path to the OpenAPI YAML or JSON file.
            config: Optional generator configuration.

        Raises:
            OpenAPIParseError: If the specification cannot be loaded.
        """
        self.spec_path = Path(spec_path)
        self.config = config or GeneratorConfig()
        self._raw_spec: dict[str, Any] = {}
        self.schema: OpenAPISchema | None = None

    def load(self) -> OpenAPISchema:
        """Load and parse the OpenAPI specification.

        Returns:
            Parsed OpenAPISchema object.

        Raises:
            OpenAPIParseError: If parsing fails.
        """
        if not self.spec_path.exists():
            raise OpenAPIParseError(
                f"Specification file not found: {self.spec_path}",
                path=str(self.spec_path),
            )

        try:
            content = self.spec_path.read_text(encoding="utf-8")
            if self.spec_path.suffix.lower() in (".yaml", ".yml"):
                self._raw_spec = yaml.safe_load(content)
            else:
                self._raw_spec = json.loads(content)
        except yaml.YAMLError as e:
            raise OpenAPIParseError(f"YAML parsing error: {e}", path=str(self.spec_path))
        except json.JSONDecodeError as e:
            raise OpenAPIParseError(f"JSON parsing error: {e}", path=str(self.spec_path))

        self.schema = self._parse_spec()
        return self.schema

    def _parse_spec(self) -> OpenAPISchema:
        """Parse the raw specification into structured data."""
        info = self._raw_spec.get("info", {})
        servers = self._raw_spec.get("servers", [])
        base_url = servers[0].get("url", "") if servers else ""

        schema = OpenAPISchema(
            title=info.get("title", "API"),
            version=info.get("version", "1.0.0"),
            description=info.get("description", ""),
            base_url=base_url,
        )

        # Parse security schemes
        components = self._raw_spec.get("components", {})
        schema.security_schemes = components.get("securitySchemes", {})

        # Parse schemas/models
        schemas_raw = components.get("schemas", {})
        for name, schema_def in schemas_raw.items():
            schema.schemas[name] = self._parse_schema(name, schema_def)

        # Parse paths/endpoints
        paths = self._raw_spec.get("paths", {})
        for path, path_item in paths.items():
            # Handle path-level parameters
            path_params = path_item.get("parameters", [])

            for method in ["get", "post", "put", "patch", "delete", "head", "options"]:
                if method in path_item:
                    operation = path_item[method]
                    endpoint = self._parse_endpoint(path, method, operation, path_params)
                    schema.endpoints.append(endpoint)

        return schema

    def _parse_schema(self, name: str, schema_def: dict[str, Any]) -> SchemaInfo:
        """Parse a schema definition."""
        required = schema_def.get("required", [])
        properties = []

        for prop_name, prop_def in schema_def.get("properties", {}).items():
            prop = self._parse_property(prop_name, prop_def, prop_name in required)
            properties.append(prop)

        return SchemaInfo(
            name=name,
            description=schema_def.get("description", ""),
            properties=properties,
            required_properties=required,
            type=schema_def.get("type", "object"),
        )

    def _parse_property(
        self,
        name: str,
        prop_def: dict[str, Any],
        required: bool,
    ) -> PropertyInfo:
        """Parse a property definition."""
        schema_type = prop_def.get("type", "string")
        items = None
        ref = None

        if "$ref" in prop_def:
            ref = prop_def["$ref"].split("/")[-1]
            schema_type = "object"
        elif schema_type == "array" and "items" in prop_def:
            items_def = prop_def["items"]
            if "$ref" in items_def:
                items = items_def["$ref"].split("/")[-1]
            else:
                items = items_def.get("type", "string")

        return PropertyInfo(
            name=name,
            schema_type=schema_type,
            required=required,
            description=prop_def.get("description", ""),
            default=prop_def.get("default"),
            format=prop_def.get("format"),
            enum=prop_def.get("enum"),
            ref=ref,
            items=items,
        )

    def _parse_endpoint(
        self,
        path: str,
        method: str,
        operation: dict[str, Any],
        path_params: list[dict[str, Any]],
    ) -> EndpointInfo:
        """Parse an endpoint operation."""
        # Generate operation_id if not provided
        operation_id = operation.get("operationId")
        if not operation_id:
            operation_id = self._generate_operation_id(path, method)

        endpoint = EndpointInfo(
            path=path,
            method=method.upper(),
            operation_id=operation_id,
            summary=operation.get("summary", ""),
            description=operation.get("description", ""),
            tags=operation.get("tags", []),
            security=operation.get("security", []),
        )

        # Parse parameters (path-level + operation-level)
        all_params = path_params + operation.get("parameters", [])
        for param in all_params:
            param_info = self._parse_parameter(param)
            endpoint.parameters.append(param_info)

        # Parse request body
        if "requestBody" in operation:
            endpoint.request_body = self._parse_request_body(operation["requestBody"])

        # Parse responses
        for status_code, response in operation.get("responses", {}).items():
            endpoint.responses[status_code] = self._parse_response(status_code, response)

        return endpoint

    def _parse_parameter(self, param: dict[str, Any]) -> ParameterInfo:
        """Parse a parameter definition."""
        schema = param.get("schema", {})
        return ParameterInfo(
            name=param.get("name", ""),
            location=param.get("in", "query"),
            required=param.get("required", False),
            schema_type=schema.get("type", "string"),
            description=param.get("description", ""),
            default=schema.get("default"),
            enum=schema.get("enum"),
            format=schema.get("format"),
        )

    def _parse_request_body(self, body: dict[str, Any]) -> RequestBodyInfo:
        """Parse a request body definition."""
        content = body.get("content", {})

        # Prefer JSON content type
        for content_type in ["application/json", "application/x-www-form-urlencoded"]:
            if content_type in content:
                media = content[content_type]
                schema = media.get("schema", {})

                schema_ref = None
                properties = []

                if "$ref" in schema:
                    schema_ref = schema["$ref"].split("/")[-1]
                else:
                    required = schema.get("required", [])
                    for prop_name, prop_def in schema.get("properties", {}).items():
                        prop = self._parse_property(prop_name, prop_def, prop_name in required)
                        properties.append(prop)

                return RequestBodyInfo(
                    content_type=content_type,
                    required=body.get("required", False),
                    schema_ref=schema_ref,
                    properties=properties,
                    description=body.get("description", ""),
                )

        # Fallback to first content type
        if content:
            content_type = next(iter(content))
            return RequestBodyInfo(
                content_type=content_type,
                required=body.get("required", False),
                description=body.get("description", ""),
            )

        return RequestBodyInfo(
            content_type="application/json",
            required=False,
        )

    def _parse_response(self, status_code: str, response: dict[str, Any]) -> ResponseInfo:
        """Parse a response definition."""
        content = response.get("content", {})

        resp_info = ResponseInfo(
            status_code=status_code,
            description=response.get("description", ""),
        )

        if "application/json" in content:
            resp_info.content_type = "application/json"
            schema = content["application/json"].get("schema", {})

            if "$ref" in schema:
                resp_info.schema_ref = schema["$ref"].split("/")[-1]
            else:
                required = schema.get("required", [])
                for prop_name, prop_def in schema.get("properties", {}).items():
                    prop = self._parse_property(prop_name, prop_def, prop_name in required)
                    resp_info.properties.append(prop)

        return resp_info

    def _generate_operation_id(self, path: str, method: str) -> str:
        """Generate an operation ID from path and method."""
        # Remove path parameters and convert to snake_case
        clean_path = re.sub(r"\{[^}]+\}", "", path)
        clean_path = re.sub(r"[^a-zA-Z0-9]", "_", clean_path)
        clean_path = re.sub(r"_+", "_", clean_path).strip("_")

        return f"{method}_{clean_path}"

    def generate(self, output_dir: str | Path | None = None) -> dict[str, str]:
        """Generate VenomQA code from the specification.

        Args:
            output_dir: Output directory. Uses config.output_dir if not specified.

        Returns:
            Dictionary mapping filenames to generated code.

        Raises:
            OpenAPIParseError: If specification is not loaded.
        """
        if self.schema is None:
            self.load()

        output_path = Path(output_dir) if output_dir else Path(self.config.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        generated_files: dict[str, str] = {}

        # Generate actions
        if self.config.group_by_tags:
            actions_by_tag = self._group_actions_by_tag()
            for tag, actions in actions_by_tag.items():
                filename = f"{self._sanitize_name(tag)}_actions.py"
                code = self._generate_actions_module(actions)
                generated_files[filename] = code
                (output_path / filename).write_text(code, encoding="utf-8")
        else:
            actions = self._generate_all_actions()
            code = self._generate_actions_module(actions)
            generated_files[self.config.actions_file] = code
            (output_path / self.config.actions_file).write_text(code, encoding="utf-8")

        # Generate fixtures
        if self.config.generate_fixtures:
            fixtures = self._generate_all_fixtures()
            code = self._generate_fixtures_module(fixtures)
            generated_files[self.config.fixtures_file] = code
            (output_path / self.config.fixtures_file).write_text(code, encoding="utf-8")

        # Generate __init__.py
        init_code = self._generate_init_module(generated_files)
        generated_files["__init__.py"] = init_code
        (output_path / "__init__.py").write_text(init_code, encoding="utf-8")

        return generated_files

    def generate_actions_code(self) -> str:
        """Generate only the actions code without writing to file.

        Returns:
            Generated Python code as a string.
        """
        if self.schema is None:
            self.load()

        actions = self._generate_all_actions()
        return self._generate_actions_module(actions)

    def generate_fixtures_code(self) -> str:
        """Generate only the fixtures code without writing to file.

        Returns:
            Generated Python code as a string.
        """
        if self.schema is None:
            self.load()

        fixtures = self._generate_all_fixtures()
        return self._generate_fixtures_module(fixtures)

    def _generate_all_actions(self) -> list[GeneratedAction]:
        """Generate actions for all endpoints."""
        actions = []
        for endpoint in self.schema.endpoints:
            action = self._generate_action(endpoint)
            actions.append(action)
        return actions

    def _group_actions_by_tag(self) -> dict[str, list[GeneratedAction]]:
        """Group generated actions by tag."""
        by_tag: dict[str, list[GeneratedAction]] = {"default": []}

        for endpoint in self.schema.endpoints:
            action = self._generate_action(endpoint)
            if endpoint.tags:
                for tag in endpoint.tags:
                    if tag not in by_tag:
                        by_tag[tag] = []
                    by_tag[tag].append(action)
            else:
                by_tag["default"].append(action)

        return {k: v for k, v in by_tag.items() if v}

    def _generate_action(self, endpoint: EndpointInfo) -> GeneratedAction:
        """Generate an action for a single endpoint."""
        func_name = self._sanitize_name(endpoint.operation_id)
        imports: set[str] = {"from typing import Any"}

        # Build function signature
        params = ["client: Client", "ctx: Context"]

        # Build docstring
        docstring_parts = []
        if endpoint.summary:
            docstring_parts.append(endpoint.summary)
        if endpoint.description and endpoint.description != endpoint.summary:
            if docstring_parts:
                docstring_parts.append("")
            docstring_parts.append(endpoint.description)
        docstring_parts.append("")
        docstring_parts.append(f"{endpoint.method} {endpoint.path}")

        # Build path with parameter substitution
        path_code = f'"{endpoint.path}"'
        for param in endpoint.path_parameters:
            placeholder = f"{{{param.name}}}"
            ctx_get = f'ctx.get("{param.name}")'
            if param.default is not None:
                default = repr(param.default) if isinstance(param.default, str) else param.default
                ctx_get = f'ctx.get("{param.name}", {default})'
            path_code = f'{path_code}.replace("{placeholder}", str({ctx_get}))'

        if endpoint.path_parameters:
            path_code = f"path = {path_code}"
        else:
            path_code = f'path = "{endpoint.path}"'

        # Build query parameters
        query_params_code = ""
        if endpoint.query_parameters:
            query_lines = ["params = {}"]
            for param in endpoint.query_parameters:
                if param.default is not None:
                    default = f'"{param.default}"' if isinstance(param.default, str) else param.default
                    query_lines.append(
                        f'if ctx.get("{param.name}") is not None:\n'
                        f'        params["{param.name}"] = ctx.get("{param.name}", {default})'
                    )
                else:
                    query_lines.append(
                        f'if ctx.get("{param.name}") is not None:\n'
                        f'        params["{param.name}"] = ctx.get("{param.name}")'
                    )
            query_params_code = "\n    ".join(query_lines)

        # Build request body
        body_code = ""
        if endpoint.request_body:
            body_lines = ["body = {"]

            # Get properties from schema ref or inline
            properties = endpoint.request_body.properties
            if endpoint.request_body.schema_ref and self.schema:
                ref_schema = self.schema.schemas.get(endpoint.request_body.schema_ref)
                if ref_schema:
                    properties = ref_schema.properties

            for prop in properties:
                default_val = prop.get_default_value()
                body_lines.append(f'        "{prop.name}": ctx.get("{prop.name}", {default_val}),')

            body_lines.append("    }")
            body_code = "\n".join(body_lines)

        # Build headers for auth
        headers_code = ""
        if endpoint.requires_auth:
            headers_code = """headers = {}
    if ctx.get("token"):
        headers["Authorization"] = f"Bearer {ctx.get('token')}\""""

        # Build the HTTP call
        method_lower = endpoint.method.lower()
        call_args = ["path"]
        if query_params_code:
            call_args.append("params=params")
        if body_code:
            call_args.append("json=body")
        if headers_code:
            call_args.append("headers=headers")

        call_code = f"return client.{method_lower}({', '.join(call_args)})"

        # Assemble function body
        body_parts = []
        body_parts.append(path_code)
        if query_params_code:
            body_parts.append(query_params_code)
        if headers_code:
            body_parts.append(headers_code)
        if body_code:
            body_parts.append(body_code)
        body_parts.append(call_code)

        body = "\n    ".join(body_parts)

        # Generate the full function
        docstring = ""
        if self.config.include_docstrings and docstring_parts:
            escaped_docstring = "\n    ".join(docstring_parts)
            docstring = f'"""{escaped_docstring}\n    """'

        type_hint = " -> Response" if self.config.include_type_hints else ""
        decorator = f"@{self.config.action_decorator}\n" if self.config.action_decorator else ""

        code = f'''{decorator}def {func_name}({", ".join(params)}){type_hint}:
    {docstring}
    {body}
'''

        return GeneratedAction(
            name=func_name,
            endpoint=endpoint,
            code=code,
            imports=imports,
        )

    def _generate_all_fixtures(self) -> list[GeneratedFixture]:
        """Generate fixtures for all schemas."""
        fixtures = []
        for schema in self.schema.schemas.values():
            fixture = self._generate_fixture(schema)
            fixtures.append(fixture)
        return fixtures

    def _generate_fixture(self, schema: SchemaInfo) -> GeneratedFixture:
        """Generate a fixture for a schema."""
        func_name = f"{self.config.fixture_prefix}{self._sanitize_name(schema.name.lower())}"
        imports: set[str] = {"from typing import Any"}

        # Build docstring
        docstring = f'"""Create test data for {schema.name}.'
        if schema.description:
            docstring += f"\n\n    {schema.description}"
        docstring += '\n    """'

        # Build default data
        data_lines = ["data = {"]
        for prop in schema.properties:
            default_val = prop.get_default_value()
            data_lines.append(f'        "{prop.name}": {default_val},')
        data_lines.append("    }")
        data_code = "\n".join(data_lines)

        # Build override logic
        override_code = """# Apply overrides from kwargs
    for key, value in kwargs.items():
        if value is not None:
            data[key] = value"""

        code = f'''def {func_name}(**kwargs: Any) -> dict[str, Any]:
    {docstring}
    {data_code}
    {override_code}
    return data
'''

        return GeneratedFixture(
            name=func_name,
            schema=schema,
            code=code,
            imports=imports,
        )

    def _generate_actions_module(self, actions: list[GeneratedAction]) -> str:
        """Generate the complete actions module."""
        header = f'''"""Auto-generated VenomQA actions from OpenAPI specification.

Generated from: {self.spec_path.name}
API: {self.schema.title} v{self.schema.version}

This module contains action functions for each API endpoint.
Actions receive (client, ctx) and return a Response.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.http import Client
    from venomqa.core.context import ExecutionContext as Context
    from httpx import Response


def action(func):
    """Decorator marking a function as a VenomQA action."""
    func._is_action = True
    return func


'''

        # Collect all action code
        action_codes = [action.code for action in actions]

        # Generate __all__
        all_names = [action.name for action in actions]
        all_export = f"__all__ = {all_names!r}\n\n"

        return header + all_export + "\n\n".join(action_codes)

    def _generate_fixtures_module(self, fixtures: list[GeneratedFixture]) -> str:
        """Generate the complete fixtures module."""
        header = f'''"""Auto-generated VenomQA fixtures from OpenAPI specification.

Generated from: {self.spec_path.name}
API: {self.schema.title} v{self.schema.version}

This module contains fixture factories for creating test data.
"""

from __future__ import annotations

from typing import Any


'''

        # Collect all fixture code
        fixture_codes = [fixture.code for fixture in fixtures]

        # Generate __all__
        all_names = [fixture.name for fixture in fixtures]
        all_export = f"__all__ = {all_names!r}\n\n"

        return header + all_export + "\n\n".join(fixture_codes)

    def _generate_init_module(self, generated_files: dict[str, str]) -> str:
        """Generate __init__.py that exports all generated code."""
        lines = [
            f'"""Auto-generated VenomQA code from {self.spec_path.name}."""',
            "",
        ]

        for filename in generated_files:
            if filename.endswith(".py") and filename != "__init__.py":
                module_name = filename[:-3]  # Remove .py
                lines.append(f"from .{module_name} import *")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Combinatorial integration: generate dimensions and transitions
    # from OpenAPI specification for live API testing.
    # ------------------------------------------------------------------

    @classmethod
    def from_url(cls, url: str, config: GeneratorConfig | None = None) -> OpenAPIGenerator:
        """Load an OpenAPI specification from a URL.

        Downloads the spec (YAML or JSON) and creates an OpenAPIGenerator
        instance ready for parsing and code/combinatorial generation.

        Args:
            url: HTTP(S) URL to the OpenAPI specification.
            config: Optional generator configuration.

        Returns:
            OpenAPIGenerator instance with the spec loaded.

        Raises:
            OpenAPIParseError: If the spec cannot be downloaded or parsed.

        Example:
            >>> gen = OpenAPIGenerator.from_url("http://localhost:8000/openapi.json")
            >>> schema = gen.load()
            >>> print(schema.title)
        """
        import tempfile
        import urllib.error
        import urllib.request

        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json, application/yaml, */*"})
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode("utf-8")
        except urllib.error.URLError as e:
            raise OpenAPIParseError(f"Failed to download spec from {url}: {e}", path=url)

        # Determine format from URL or content
        suffix = ".json"
        if url.endswith((".yaml", ".yml")) or content.lstrip().startswith(("openapi:", "swagger:", "info:")):
            suffix = ".yaml"

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
        tmp.write(content)
        tmp.close()

        instance = cls(tmp.name, config=config)
        instance.load()
        return instance

    def generate_dimensions(self) -> Any:
        """Extract combinatorial dimensions from the OpenAPI specification.

        Analyzes endpoints, HTTP methods, parameters, and authentication
        requirements to produce a DimensionSpace suitable for combinatorial
        test generation.

        Returns:
            DimensionSpace with dimensions derived from the spec:
            - http_method: All HTTP methods in the spec
            - auth_state: ["none", "valid", "invalid"] if security schemes exist
            - content_type: Content types used in request bodies
            - endpoint_group: Groups of endpoints (by tag)
            - parameter_presence: ["all_required", "optional_only", "missing_required"]

        Raises:
            OpenAPIParseError: If specification is not loaded.

        Example:
            >>> gen = OpenAPIGenerator("api.yaml")
            >>> gen.load()
            >>> space = gen.generate_dimensions()
            >>> print(space.dimension_names)
        """
        from venomqa.combinatorial.dimensions import Dimension, DimensionSpace

        if self.schema is None:
            self.load()

        dimensions = []

        # 1. HTTP method dimension
        methods = sorted({ep.method.upper() for ep in self.schema.endpoints})
        if methods:
            dimensions.append(Dimension(
                name="http_method",
                values=methods,
                description="HTTP method being tested",
                default_value=methods[0],
            ))

        # 2. Auth state dimension (if security schemes are defined)
        if self.schema.security_schemes:
            dimensions.append(Dimension(
                name="auth_state",
                values=["none", "valid", "invalid"],
                description="Authentication token state",
                default_value="none",
            ))

        # 3. Content type dimension
        content_types = set()
        for ep in self.schema.endpoints:
            if ep.request_body:
                content_types.add(ep.request_body.content_type)
        if not content_types:
            content_types = {"application/json"}
        ct_list = sorted(content_types)
        dimensions.append(Dimension(
            name="content_type",
            values=ct_list,
            description="Request content type",
            default_value=ct_list[0],
        ))

        # 4. Endpoint group dimension (by tag)
        tags = set()
        for ep in self.schema.endpoints:
            for tag in ep.tags:
                tags.add(tag)
        if not tags:
            tags = {"default"}
        tag_list = sorted(tags)
        dimensions.append(Dimension(
            name="endpoint_group",
            values=tag_list,
            description="API endpoint group (tag)",
            default_value=tag_list[0],
        ))

        # 5. Parameter coverage dimension
        dimensions.append(Dimension(
            name="param_coverage",
            values=["all_required", "optional_included", "missing_required"],
            description="Which parameters are included in the request",
            default_value="all_required",
        ))

        return DimensionSpace(dimensions)

    def generate_transitions(self) -> list[Any]:
        """Generate transition actions for each endpoint.

        Creates TransitionAction objects that can be registered with a
        CombinatorialGraphBuilder. Each transition represents invoking
        an endpoint with specific parameters.

        Returns:
            List of TransitionAction objects.

        Raises:
            OpenAPIParseError: If specification is not loaded.

        Example:
            >>> gen = OpenAPIGenerator("api.yaml")
            >>> gen.load()
            >>> transitions = gen.generate_transitions()
            >>> for t in transitions:
            ...     print(t.name)
        """
        from venomqa.combinatorial.builder import TransitionAction, TransitionKey

        if self.schema is None:
            self.load()

        transitions = []

        for endpoint in self.schema.endpoints:
            method = endpoint.method.upper()
            func_name = self._sanitize_name(endpoint.operation_id)

            # Create a transition for testing this endpoint
            def _make_action(ep: EndpointInfo) -> Any:
                """Create an action callable for the given endpoint."""
                def action(client: Any, context: dict[str, Any]) -> Any:
                    path = ep.path
                    for param in ep.path_parameters:
                        placeholder = f"{{{param.name}}}"
                        value = context.get(param.name, f"test_{param.name}")
                        path = path.replace(placeholder, str(value))

                    kwargs: dict[str, Any] = {}
                    if ep.query_parameters:
                        params = {}
                        for param in ep.query_parameters:
                            if param.name in context:
                                params[param.name] = context[param.name]
                            elif param.default is not None:
                                params[param.name] = param.default
                        if params:
                            kwargs["params"] = params

                    if ep.request_body and ep.method.upper() in ("POST", "PUT", "PATCH"):
                        body = {}
                        props = ep.request_body.properties
                        if ep.request_body.schema_ref and hasattr(client, "_schema"):
                            pass  # Use schema ref if available
                        for prop in props:
                            if prop.name in context:
                                body[prop.name] = context[prop.name]
                            else:
                                body[prop.name] = _default_for_type(prop.schema_type, prop.format)
                        kwargs["json"] = body

                    method_fn = getattr(client, ep.method.lower(), None)
                    if method_fn is None:
                        raise AttributeError(
                            f"Client does not have method '{ep.method.lower()}'"
                        )
                    return method_fn(path, **kwargs)

                action.__name__ = f"action_{ep.operation_id}"  # noqa: B023
                action.__doc__ = f"{ep.method} {ep.path}: {ep.summary}"  # noqa: B023
                return action  # noqa: B023

            action = _make_action(endpoint)

            # Create a TransitionAction (not registered to a builder yet)
            trans = TransitionAction(
                key=TransitionKey(
                    dimension="http_method",
                    from_value=method,
                    to_value=method,
                ),
                action=action,
                name=func_name,
                description=f"{method} {endpoint.path}: {endpoint.summary}",
            )
            transitions.append(trans)

        return transitions

    def build_graph(self) -> Any:
        """Build a complete CombinatorialGraphBuilder from the OpenAPI spec.

        Combines generate_dimensions(), generate_transitions(), and
        appropriate constraints into a ready-to-use builder.

        Returns:
            CombinatorialGraphBuilder configured from the spec.

        Raises:
            OpenAPIParseError: If specification is not loaded.

        Example:
            >>> gen = OpenAPIGenerator("api.yaml")
            >>> gen.load()
            >>> builder = gen.build_graph()
            >>> graph = builder.build(strength=2)
            >>> result = graph.explore(client)
        """
        from venomqa.combinatorial.builder import CombinatorialGraphBuilder
        from venomqa.combinatorial.constraints import ConstraintSet, exclude

        if self.schema is None:
            self.load()

        space = self.generate_dimensions()
        transitions = self.generate_transitions()

        # Build constraints
        constraint_list = []

        # Constraint: missing_required params should only be used with GET
        # (POST/PUT with missing required fields is tested separately)
        has_auth = any(d.name == "auth_state" for d in space.dimensions)
        if has_auth:
            constraint_list.append(exclude(
                "no_write_without_auth",
                auth_state="none",
                http_method="POST",
                description="Cannot write without authentication",
            ))
            constraint_list.append(exclude(
                "no_delete_without_auth",
                auth_state="none",
                http_method="DELETE",
                description="Cannot delete without authentication",
            ))

        constraints = ConstraintSet(constraint_list)

        builder = CombinatorialGraphBuilder(
            name=f"{self._sanitize_name(self.schema.title)}_combinatorial",
            space=space,
            constraints=constraints,
            description=(
                f"Combinatorial test graph generated from {self.schema.title} "
                f"v{self.schema.version} OpenAPI specification"
            ),
        )

        # Register transitions
        for trans in transitions:
            method = trans.key.from_value
            methods = [d.values for d in space.dimensions if d.name == "http_method"]
            if methods:
                for from_method in methods[0]:
                    if from_method != method:
                        builder.register_transition(
                            "http_method",
                            from_method,
                            method,
                            action=trans.action,
                            name=f"{trans.name}_from_{from_method.lower()}",
                        )

        return builder

    def _sanitize_name(self, name: str) -> str:
        """Convert a name to a valid Python identifier."""
        # Replace non-alphanumeric with underscore
        sanitized = re.sub(r"[^a-zA-Z0-9]", "_", name)
        # Remove leading digits
        sanitized = re.sub(r"^[0-9]+", "", sanitized)
        # Remove consecutive underscores
        sanitized = re.sub(r"_+", "_", sanitized)
        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_")
        # Convert to lowercase
        sanitized = sanitized.lower()
        # Handle Python keywords
        if keyword.iskeyword(sanitized):
            sanitized = f"{sanitized}_"
        # Ensure not empty
        if not sanitized:
            sanitized = "unnamed"
        return sanitized
