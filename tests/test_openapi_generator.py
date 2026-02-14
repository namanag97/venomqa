"""Tests for OpenAPI code generator."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from venomqa.generators import (
    EndpointInfo,
    GeneratedAction,
    GeneratedFixture,
    GeneratorConfig,
    OpenAPIGenerator,
    OpenAPIParseError,
    OpenAPISchema,
    ParameterInfo,
    PropertyInfo,
    RequestBodyInfo,
    ResponseInfo,
    SchemaInfo,
)


# Sample OpenAPI specification for testing
SAMPLE_OPENAPI_SPEC = {
    "openapi": "3.0.0",
    "info": {
        "title": "Test API",
        "version": "1.0.0",
        "description": "A test API for VenomQA generator tests",
    },
    "servers": [
        {"url": "https://api.example.com/v1"}
    ],
    "paths": {
        "/products": {
            "get": {
                "operationId": "listProducts",
                "summary": "List all products",
                "description": "Returns a paginated list of products",
                "tags": ["products"],
                "parameters": [
                    {
                        "name": "page",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer", "default": 1},
                        "description": "Page number",
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer", "default": 20},
                        "description": "Items per page",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "List of products",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/Product"},
                                }
                            }
                        },
                    }
                },
            },
            "post": {
                "operationId": "createProduct",
                "summary": "Create a new product",
                "tags": ["products"],
                "security": [{"bearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ProductCreate"}
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Product created",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Product"}
                            }
                        },
                    }
                },
            },
        },
        "/products/{id}": {
            "parameters": [
                {
                    "name": "id",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                    "description": "Product ID",
                }
            ],
            "get": {
                "operationId": "getProduct",
                "summary": "Get a product by ID",
                "tags": ["products"],
                "responses": {
                    "200": {
                        "description": "Product details",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Product"}
                            }
                        },
                    },
                    "404": {"description": "Product not found"},
                },
            },
            "put": {
                "operationId": "updateProduct",
                "summary": "Update a product",
                "tags": ["products"],
                "security": [{"bearerAuth": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ProductUpdate"}
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Product updated",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Product"}
                            }
                        },
                    }
                },
            },
            "delete": {
                "operationId": "deleteProduct",
                "summary": "Delete a product",
                "tags": ["products"],
                "security": [{"bearerAuth": []}],
                "responses": {
                    "204": {"description": "Product deleted"},
                },
            },
        },
        "/users": {
            "post": {
                "operationId": "createUser",
                "summary": "Create a new user",
                "tags": ["users"],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/UserCreate"}
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "User created",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        },
                    }
                },
            }
        },
    },
    "components": {
        "securitySchemes": {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
            }
        },
        "schemas": {
            "Product": {
                "type": "object",
                "required": ["id", "title", "price"],
                "properties": {
                    "id": {"type": "integer", "description": "Product ID"},
                    "title": {"type": "string", "description": "Product title"},
                    "description": {"type": "string", "description": "Product description"},
                    "price": {"type": "number", "description": "Product price"},
                    "category": {
                        "type": "string",
                        "enum": ["electronics", "clothing", "books"],
                        "description": "Product category",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Product tags",
                    },
                    "in_stock": {"type": "boolean", "default": True},
                },
            },
            "ProductCreate": {
                "type": "object",
                "required": ["title", "price"],
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "price": {"type": "number"},
                    "category": {"type": "string"},
                },
            },
            "ProductUpdate": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "price": {"type": "number"},
                    "category": {"type": "string"},
                },
            },
            "User": {
                "type": "object",
                "required": ["id", "email"],
                "properties": {
                    "id": {"type": "integer"},
                    "email": {"type": "string", "format": "email"},
                    "name": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                },
            },
            "UserCreate": {
                "type": "object",
                "required": ["email", "password"],
                "properties": {
                    "email": {"type": "string", "format": "email"},
                    "password": {"type": "string", "format": "password"},
                    "name": {"type": "string"},
                },
            },
        },
    },
}


@pytest.fixture
def sample_yaml_spec(tmp_path: Path) -> Path:
    """Create a sample OpenAPI YAML spec file."""
    spec_path = tmp_path / "openapi.yaml"
    with open(spec_path, "w") as f:
        yaml.dump(SAMPLE_OPENAPI_SPEC, f)
    return spec_path


@pytest.fixture
def sample_json_spec(tmp_path: Path) -> Path:
    """Create a sample OpenAPI JSON spec file."""
    spec_path = tmp_path / "openapi.json"
    with open(spec_path, "w") as f:
        json.dump(SAMPLE_OPENAPI_SPEC, f)
    return spec_path


@pytest.fixture
def generator(sample_yaml_spec: Path) -> OpenAPIGenerator:
    """Create a generator instance with the sample spec."""
    return OpenAPIGenerator(sample_yaml_spec)


class TestParameterInfo:
    """Tests for ParameterInfo dataclass."""

    def test_python_type_string(self) -> None:
        param = ParameterInfo(
            name="name",
            location="query",
            required=True,
            schema_type="string",
        )
        assert param.python_type == "str"

    def test_python_type_integer(self) -> None:
        param = ParameterInfo(
            name="id",
            location="path",
            required=True,
            schema_type="integer",
        )
        assert param.python_type == "int"

    def test_python_type_optional(self) -> None:
        param = ParameterInfo(
            name="page",
            location="query",
            required=False,
            schema_type="integer",
        )
        assert param.python_type == "int | None"

    def test_python_type_array(self) -> None:
        param = ParameterInfo(
            name="tags",
            location="query",
            required=True,
            schema_type="array",
        )
        assert param.python_type == "list"


class TestPropertyInfo:
    """Tests for PropertyInfo dataclass."""

    def test_python_type_required(self) -> None:
        prop = PropertyInfo(name="title", schema_type="string", required=True)
        assert prop.python_type == "str"

    def test_python_type_optional(self) -> None:
        prop = PropertyInfo(name="description", schema_type="string", required=False)
        assert prop.python_type == "str | None"

    def test_python_type_array_with_items(self) -> None:
        prop = PropertyInfo(
            name="tags",
            schema_type="array",
            items="string",
            required=True,
        )
        assert prop.python_type == "list[str]"

    def test_get_default_value_string(self) -> None:
        prop = PropertyInfo(name="title", schema_type="string")
        assert prop.get_default_value() == '""'

    def test_get_default_value_integer(self) -> None:
        prop = PropertyInfo(name="count", schema_type="integer")
        assert prop.get_default_value() == "0"

    def test_get_default_value_with_explicit_default(self) -> None:
        prop = PropertyInfo(name="status", schema_type="string", default="active")
        assert prop.get_default_value() == '"active"'

    def test_get_default_value_with_enum(self) -> None:
        prop = PropertyInfo(
            name="category",
            schema_type="string",
            enum=["electronics", "clothing"],
        )
        assert prop.get_default_value() == '"electronics"'

    def test_get_default_value_email_format(self) -> None:
        prop = PropertyInfo(name="email", schema_type="string", format="email")
        assert prop.get_default_value() == '"test@example.com"'

    def test_get_default_value_datetime_format(self) -> None:
        prop = PropertyInfo(name="created_at", schema_type="string", format="date-time")
        assert prop.get_default_value() == '"2024-01-01T00:00:00Z"'


class TestOpenAPIGenerator:
    """Tests for OpenAPIGenerator class."""

    def test_load_yaml_spec(self, sample_yaml_spec: Path) -> None:
        generator = OpenAPIGenerator(sample_yaml_spec)
        schema = generator.load()

        assert schema.title == "Test API"
        assert schema.version == "1.0.0"
        assert schema.base_url == "https://api.example.com/v1"

    def test_load_json_spec(self, sample_json_spec: Path) -> None:
        generator = OpenAPIGenerator(sample_json_spec)
        schema = generator.load()

        assert schema.title == "Test API"
        assert schema.version == "1.0.0"

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        generator = OpenAPIGenerator(tmp_path / "nonexistent.yaml")

        with pytest.raises(OpenAPIParseError, match="not found"):
            generator.load()

    def test_load_invalid_yaml(self, tmp_path: Path) -> None:
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("invalid: yaml: content: [")

        generator = OpenAPIGenerator(bad_yaml)
        with pytest.raises(OpenAPIParseError, match="YAML parsing error"):
            generator.load()

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{invalid json}")

        generator = OpenAPIGenerator(bad_json)
        with pytest.raises(OpenAPIParseError, match="JSON parsing error"):
            generator.load()

    def test_parse_endpoints(self, generator: OpenAPIGenerator) -> None:
        schema = generator.load()

        assert len(schema.endpoints) == 6  # 6 operations in our spec
        operation_ids = [e.operation_id for e in schema.endpoints]
        assert "listProducts" in operation_ids
        assert "createProduct" in operation_ids
        assert "getProduct" in operation_ids
        assert "updateProduct" in operation_ids
        assert "deleteProduct" in operation_ids
        assert "createUser" in operation_ids

    def test_parse_path_parameters(self, generator: OpenAPIGenerator) -> None:
        schema = generator.load()

        get_product = next(e for e in schema.endpoints if e.operation_id == "getProduct")
        assert len(get_product.path_parameters) == 1
        assert get_product.path_parameters[0].name == "id"
        assert get_product.path_parameters[0].schema_type == "integer"

    def test_parse_query_parameters(self, generator: OpenAPIGenerator) -> None:
        schema = generator.load()

        list_products = next(e for e in schema.endpoints if e.operation_id == "listProducts")
        assert len(list_products.query_parameters) == 2

        page_param = next(p for p in list_products.query_parameters if p.name == "page")
        assert page_param.default == 1
        assert not page_param.required

    def test_parse_request_body(self, generator: OpenAPIGenerator) -> None:
        schema = generator.load()

        create_product = next(e for e in schema.endpoints if e.operation_id == "createProduct")
        assert create_product.request_body is not None
        assert create_product.request_body.required
        assert create_product.request_body.schema_ref == "ProductCreate"

    def test_parse_security(self, generator: OpenAPIGenerator) -> None:
        schema = generator.load()

        create_product = next(e for e in schema.endpoints if e.operation_id == "createProduct")
        assert create_product.requires_auth

        list_products = next(e for e in schema.endpoints if e.operation_id == "listProducts")
        assert not list_products.requires_auth

    def test_parse_schemas(self, generator: OpenAPIGenerator) -> None:
        schema = generator.load()

        assert "Product" in schema.schemas
        assert "ProductCreate" in schema.schemas
        assert "User" in schema.schemas

        product_schema = schema.schemas["Product"]
        assert len(product_schema.properties) == 7
        assert "title" in product_schema.required_properties

    def test_parse_schema_properties(self, generator: OpenAPIGenerator) -> None:
        schema = generator.load()

        user_schema = schema.schemas["User"]
        email_prop = next(p for p in user_schema.properties if p.name == "email")
        assert email_prop.format == "email"

        product_schema = schema.schemas["Product"]
        category_prop = next(p for p in product_schema.properties if p.name == "category")
        assert category_prop.enum == ["electronics", "clothing", "books"]


class TestCodeGeneration:
    """Tests for code generation."""

    def test_generate_actions_code(self, generator: OpenAPIGenerator) -> None:
        code = generator.generate_actions_code()

        # Check module header
        assert "Auto-generated VenomQA actions" in code
        assert "Test API v1.0.0" in code

        # Check function definitions
        assert "def listproducts(" in code
        assert "def createproduct(" in code
        assert "def getproduct(" in code

        # Check imports
        assert "from typing import" in code

    def test_generate_action_with_path_params(self, generator: OpenAPIGenerator) -> None:
        code = generator.generate_actions_code()

        # getProduct should have path parameter substitution
        assert 'ctx.get("id")' in code

    def test_generate_action_with_query_params(self, generator: OpenAPIGenerator) -> None:
        code = generator.generate_actions_code()

        # listProducts should have params dict
        assert "params = {}" in code
        assert 'ctx.get("page")' in code or '"page"' in code

    def test_generate_action_with_request_body(self, generator: OpenAPIGenerator) -> None:
        code = generator.generate_actions_code()

        # createProduct should have body
        assert "body = {" in code or "json=body" in code

    def test_generate_action_with_auth(self, generator: OpenAPIGenerator) -> None:
        code = generator.generate_actions_code()

        # createProduct requires auth
        assert "Authorization" in code or "token" in code

    def test_generate_fixtures_code(self, generator: OpenAPIGenerator) -> None:
        code = generator.generate_fixtures_code()

        # Check module header
        assert "Auto-generated VenomQA fixtures" in code

        # Check fixture functions
        assert "def create_product(" in code
        assert "def create_user(" in code
        assert "def create_productcreate(" in code

    def test_generate_fixture_with_defaults(self, generator: OpenAPIGenerator) -> None:
        code = generator.generate_fixtures_code()

        # Product fixture should have default values
        assert 'data = {' in code

    def test_generate_to_directory(
        self,
        generator: OpenAPIGenerator,
        tmp_path: Path,
    ) -> None:
        output_dir = tmp_path / "generated"
        files = generator.generate(output_dir)

        assert output_dir.exists()
        assert "actions.py" in files
        assert "fixtures.py" in files
        assert "__init__.py" in files

        # Check files were written
        assert (output_dir / "actions.py").exists()
        assert (output_dir / "fixtures.py").exists()
        assert (output_dir / "__init__.py").exists()

    def test_generate_with_custom_config(
        self,
        sample_yaml_spec: Path,
        tmp_path: Path,
    ) -> None:
        config = GeneratorConfig(
            actions_file="api_actions.py",
            fixtures_file="api_fixtures.py",
            include_docstrings=False,
            include_type_hints=False,
        )
        generator = OpenAPIGenerator(sample_yaml_spec, config=config)
        output_dir = tmp_path / "custom_output"
        files = generator.generate(output_dir)

        assert "api_actions.py" in files
        assert "api_fixtures.py" in files

    def test_generate_without_fixtures(
        self,
        sample_yaml_spec: Path,
        tmp_path: Path,
    ) -> None:
        config = GeneratorConfig(generate_fixtures=False)
        generator = OpenAPIGenerator(sample_yaml_spec, config=config)
        output_dir = tmp_path / "no_fixtures"
        files = generator.generate(output_dir)

        assert "actions.py" in files
        assert "fixtures.py" not in files

    def test_generate_grouped_by_tags(
        self,
        sample_yaml_spec: Path,
        tmp_path: Path,
    ) -> None:
        config = GeneratorConfig(group_by_tags=True)
        generator = OpenAPIGenerator(sample_yaml_spec, config=config)
        output_dir = tmp_path / "by_tags"
        files = generator.generate(output_dir)

        # Should have separate files for each tag
        assert "products_actions.py" in files
        assert "users_actions.py" in files


class TestEndpointInfo:
    """Tests for EndpointInfo dataclass."""

    def test_path_parameters(self) -> None:
        endpoint = EndpointInfo(
            path="/users/{id}",
            method="GET",
            operation_id="getUser",
            parameters=[
                ParameterInfo(name="id", location="path", required=True, schema_type="integer"),
                ParameterInfo(name="include", location="query", required=False, schema_type="string"),
            ],
        )
        assert len(endpoint.path_parameters) == 1
        assert endpoint.path_parameters[0].name == "id"

    def test_query_parameters(self) -> None:
        endpoint = EndpointInfo(
            path="/users",
            method="GET",
            operation_id="listUsers",
            parameters=[
                ParameterInfo(name="page", location="query", required=False, schema_type="integer"),
                ParameterInfo(name="limit", location="query", required=False, schema_type="integer"),
            ],
        )
        assert len(endpoint.query_parameters) == 2

    def test_requires_auth(self) -> None:
        endpoint_auth = EndpointInfo(
            path="/admin",
            method="GET",
            operation_id="admin",
            security=[{"bearerAuth": []}],
        )
        endpoint_public = EndpointInfo(
            path="/public",
            method="GET",
            operation_id="public",
        )
        assert endpoint_auth.requires_auth
        assert not endpoint_public.requires_auth


class TestSanitizeName:
    """Tests for name sanitization."""

    def test_sanitize_simple(self, generator: OpenAPIGenerator) -> None:
        assert generator._sanitize_name("getUser") == "getuser"

    def test_sanitize_with_special_chars(self, generator: OpenAPIGenerator) -> None:
        assert generator._sanitize_name("get-user") == "get_user"
        assert generator._sanitize_name("get.user") == "get_user"

    def test_sanitize_leading_digits(self, generator: OpenAPIGenerator) -> None:
        assert generator._sanitize_name("123user") == "user"

    def test_sanitize_keyword(self, generator: OpenAPIGenerator) -> None:
        assert generator._sanitize_name("class") == "class_"
        assert generator._sanitize_name("import") == "import_"

    def test_sanitize_empty(self, generator: OpenAPIGenerator) -> None:
        assert generator._sanitize_name("") == "unnamed"
        assert generator._sanitize_name("123") == "unnamed"


class TestGeneratedCode:
    """Tests to verify generated code is valid Python."""

    def test_generated_actions_is_valid_python(
        self,
        generator: OpenAPIGenerator,
    ) -> None:
        code = generator.generate_actions_code()

        # Should compile without errors
        compile(code, "<string>", "exec")

    def test_generated_fixtures_is_valid_python(
        self,
        generator: OpenAPIGenerator,
    ) -> None:
        code = generator.generate_fixtures_code()

        # Should compile without errors
        compile(code, "<string>", "exec")

    def test_generated_code_can_be_imported(
        self,
        generator: OpenAPIGenerator,
        tmp_path: Path,
    ) -> None:
        output_dir = tmp_path / "importable"
        generator.generate(output_dir)

        # Add to path and try to import
        import sys
        sys.path.insert(0, str(tmp_path))

        try:
            import importable.actions  # noqa: F401
            import importable.fixtures  # noqa: F401
        finally:
            sys.path.remove(str(tmp_path))


class TestGeneratorConfig:
    """Tests for GeneratorConfig."""

    def test_default_config(self) -> None:
        config = GeneratorConfig()

        assert config.output_dir == "."
        assert config.actions_file == "actions.py"
        assert config.fixtures_file == "fixtures.py"
        assert config.include_docstrings is True
        assert config.include_type_hints is True
        assert config.generate_fixtures is True
        assert config.group_by_tags is False

    def test_custom_config(self) -> None:
        config = GeneratorConfig(
            output_dir="./output",
            actions_file="my_actions.py",
            include_docstrings=False,
            generate_fixtures=False,
        )

        assert config.output_dir == "./output"
        assert config.actions_file == "my_actions.py"
        assert config.include_docstrings is False
        assert config.generate_fixtures is False


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_spec_without_servers(self, tmp_path: Path) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "No Servers", "version": "1.0.0"},
            "paths": {},
        }
        spec_path = tmp_path / "no_servers.yaml"
        with open(spec_path, "w") as f:
            yaml.dump(spec, f)

        generator = OpenAPIGenerator(spec_path)
        schema = generator.load()
        assert schema.base_url == ""

    def test_spec_without_schemas(self, tmp_path: Path) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "No Schemas", "version": "1.0.0"},
            "paths": {
                "/ping": {
                    "get": {
                        "responses": {"200": {"description": "pong"}}
                    }
                }
            },
        }
        spec_path = tmp_path / "no_schemas.yaml"
        with open(spec_path, "w") as f:
            yaml.dump(spec, f)

        generator = OpenAPIGenerator(spec_path)
        schema = generator.load()
        assert len(schema.schemas) == 0

    def test_endpoint_without_operation_id(self, tmp_path: Path) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "No OpId", "version": "1.0.0"},
            "paths": {
                "/users/{id}": {
                    "get": {
                        "responses": {"200": {"description": "ok"}}
                    }
                }
            },
        }
        spec_path = tmp_path / "no_opid.yaml"
        with open(spec_path, "w") as f:
            yaml.dump(spec, f)

        generator = OpenAPIGenerator(spec_path)
        schema = generator.load()
        # Should generate an operation ID
        assert schema.endpoints[0].operation_id == "get_users"

    def test_inline_request_body_schema(self, tmp_path: Path) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Inline Body", "version": "1.0.0"},
            "paths": {
                "/items": {
                    "post": {
                        "operationId": "createItem",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "value": {"type": "integer"},
                                        },
                                        "required": ["name"],
                                    }
                                }
                            },
                        },
                        "responses": {"201": {"description": "created"}},
                    }
                }
            },
        }
        spec_path = tmp_path / "inline_body.yaml"
        with open(spec_path, "w") as f:
            yaml.dump(spec, f)

        generator = OpenAPIGenerator(spec_path)
        schema = generator.load()

        endpoint = schema.endpoints[0]
        assert endpoint.request_body is not None
        assert len(endpoint.request_body.properties) == 2

    def test_response_with_inline_schema(self, tmp_path: Path) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Inline Response", "version": "1.0.0"},
            "paths": {
                "/status": {
                    "get": {
                        "operationId": "getStatus",
                        "responses": {
                            "200": {
                                "description": "status",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "status": {"type": "string"},
                                                "uptime": {"type": "integer"},
                                            },
                                        }
                                    }
                                },
                            }
                        },
                    }
                }
            },
        }
        spec_path = tmp_path / "inline_response.yaml"
        with open(spec_path, "w") as f:
            yaml.dump(spec, f)

        generator = OpenAPIGenerator(spec_path)
        schema = generator.load()

        endpoint = schema.endpoints[0]
        response = endpoint.responses["200"]
        assert len(response.properties) == 2
