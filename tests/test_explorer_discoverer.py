"""
Tests for the VenomQA State Explorer API Discoverer.

This test module verifies that the APIDiscoverer class can properly parse
OpenAPI specifications and extract endpoints, methods, parameters, and
request bodies.
"""

import json
from pathlib import Path

import pytest

from venomqa.explorer.discoverer import APIDiscoverer
from venomqa.explorer.models import Action, ExplorationConfig


# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_OPENAPI_JSON = FIXTURES_DIR / "test_openapi.json"


class TestAPIDiscovererBasics:
    """Test basic APIDiscoverer functionality."""

    def test_create_discoverer(self):
        """Test creating an APIDiscoverer instance."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        assert discoverer.base_url == "http://localhost:8000"
        assert discoverer.discovered_actions == set()
        assert discoverer.discovered_endpoints == set()

    def test_base_url_trailing_slash_removed(self):
        """Test that trailing slash is removed from base URL."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000/")
        assert discoverer.base_url == "http://localhost:8000"

    def test_discoverer_with_config(self):
        """Test creating discoverer with custom config."""
        config = ExplorationConfig(
            max_depth=5,
            include_patterns=[r"/api/.*"],
            exclude_patterns=[r"/internal/.*"],
        )
        discoverer = APIDiscoverer(base_url="http://localhost:8000", config=config)
        assert discoverer.config.max_depth == 5
        assert discoverer.config.include_patterns == [r"/api/.*"]


class TestNormalizeEndpoint:
    """Test endpoint normalization."""

    def test_normalize_simple_path(self):
        """Test normalizing a simple path."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        result = discoverer._normalize_endpoint("/users")
        assert result == "/users"

    def test_normalize_removes_trailing_slash(self):
        """Test that trailing slash is removed."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        result = discoverer._normalize_endpoint("/users/")
        assert result == "/users"

    def test_normalize_adds_leading_slash(self):
        """Test that leading slash is added if missing."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        result = discoverer._normalize_endpoint("users")
        assert result == "/users"

    def test_normalize_removes_query_params(self):
        """Test that query parameters are stripped."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        result = discoverer._normalize_endpoint("/users?page=1&limit=10")
        assert result == "/users"

    def test_normalize_removes_base_url(self):
        """Test that base URL is removed from full URL."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        result = discoverer._normalize_endpoint("http://localhost:8000/users")
        assert result == "/users"

    def test_normalize_root_path(self):
        """Test that root path is preserved."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        result = discoverer._normalize_endpoint("/")
        assert result == "/"


class TestExtractPathParams:
    """Test path parameter extraction."""

    def test_extract_single_param(self):
        """Test extracting a single path parameter."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        result = discoverer._extract_path_params("/users/{userId}")
        assert result == ["userId"]

    def test_extract_multiple_params(self):
        """Test extracting multiple path parameters."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        result = discoverer._extract_path_params("/users/{userId}/posts/{postId}")
        assert result == ["userId", "postId"]

    def test_extract_no_params(self):
        """Test path with no parameters."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        result = discoverer._extract_path_params("/users/all")
        assert result == []


class TestShouldIncludeEndpoint:
    """Test endpoint inclusion/exclusion patterns."""

    def test_include_without_patterns(self):
        """Test that all endpoints are included when no patterns specified."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        assert discoverer._should_include_endpoint("/users") is True
        assert discoverer._should_include_endpoint("/api/items") is True

    def test_exclude_pattern(self):
        """Test that exclude patterns work."""
        config = ExplorationConfig(exclude_patterns=[r"/internal/.*"])
        discoverer = APIDiscoverer(base_url="http://localhost:8000", config=config)

        assert discoverer._should_include_endpoint("/users") is True
        assert discoverer._should_include_endpoint("/internal/admin") is False

    def test_include_pattern(self):
        """Test that include patterns work."""
        config = ExplorationConfig(include_patterns=[r"/api/.*"])
        discoverer = APIDiscoverer(base_url="http://localhost:8000", config=config)

        assert discoverer._should_include_endpoint("/api/users") is True
        assert discoverer._should_include_endpoint("/users") is False

    def test_exclude_takes_precedence(self):
        """Test that exclude patterns take precedence over include."""
        config = ExplorationConfig(
            include_patterns=[r"/api/.*"],
            exclude_patterns=[r"/api/internal/.*"],
        )
        discoverer = APIDiscoverer(base_url="http://localhost:8000", config=config)

        assert discoverer._should_include_endpoint("/api/users") is True
        assert discoverer._should_include_endpoint("/api/internal/admin") is False


class TestAddSeedEndpoints:
    """Test adding seed endpoints."""

    def test_add_single_seed(self):
        """Test adding a single seed endpoint."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        discoverer.add_seed_endpoints([("GET", "/users")])

        actions = discoverer.get_discovered_actions()
        assert len(actions) == 1
        assert actions[0].method == "GET"
        assert actions[0].endpoint == "/users"

    def test_add_multiple_seeds(self):
        """Test adding multiple seed endpoints."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        discoverer.add_seed_endpoints([
            ("GET", "/users"),
            ("POST", "/users"),
            ("DELETE", "/users/{id}"),
        ])

        actions = discoverer.get_discovered_actions()
        assert len(actions) == 3
        assert discoverer.get_endpoint_count() == 2  # /users and /users/{id}

    def test_add_seed_normalizes_method(self):
        """Test that method is uppercased."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        discoverer.add_seed_endpoints([("get", "/users")])

        actions = discoverer.get_discovered_actions()
        assert actions[0].method == "GET"

    def test_add_seed_respects_exclude_patterns(self):
        """Test that excluded patterns are not added."""
        config = ExplorationConfig(exclude_patterns=[r"/internal/.*"])
        discoverer = APIDiscoverer(base_url="http://localhost:8000", config=config)
        discoverer.add_seed_endpoints([
            ("GET", "/users"),
            ("GET", "/internal/admin"),
        ])

        actions = discoverer.get_discovered_actions()
        assert len(actions) == 1
        assert actions[0].endpoint == "/users"

    def test_add_seed_invalid_method_ignored(self):
        """Test that invalid HTTP methods are ignored."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        discoverer.add_seed_endpoints([
            ("GET", "/users"),
            ("INVALID", "/items"),
        ])

        actions = discoverer.get_discovered_actions()
        assert len(actions) == 1


class TestParseOpenAPISpec:
    """Test parsing OpenAPI specifications."""

    def test_parse_from_dict(self):
        """Test parsing OpenAPI spec from dictionary."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/users": {
                    "get": {
                        "summary": "List users",
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }

        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(spec)

        assert len(actions) == 1
        assert actions[0].method == "GET"
        assert actions[0].endpoint == "/users"
        assert actions[0].description == "List users"

    def test_parse_from_json_string(self):
        """Test parsing OpenAPI spec from JSON string."""
        spec_str = json.dumps({
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/items": {
                    "post": {
                        "summary": "Create item",
                        "responses": {"201": {"description": "Created"}},
                    }
                }
            },
        })

        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(spec_str)

        assert len(actions) == 1
        assert actions[0].method == "POST"
        assert actions[0].endpoint == "/items"

    def test_parse_from_file(self):
        """Test parsing OpenAPI spec from file."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(TEST_OPENAPI_JSON)

        # Should have endpoints: GET/POST /users, GET/PUT/DELETE /users/{userId},
        # GET/POST /items, GET /health, GET /internal/admin
        # That's 9 total endpoints
        assert len(actions) == 9

    def test_parse_extracts_methods(self):
        """Test that all HTTP methods are extracted."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(TEST_OPENAPI_JSON)

        methods = {a.method for a in actions}
        assert "GET" in methods
        assert "POST" in methods
        assert "PUT" in methods
        assert "DELETE" in methods

    def test_parse_extracts_query_params(self):
        """Test that query parameters are extracted."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(TEST_OPENAPI_JSON)

        # Find GET /users which has page and limit params
        get_users = next(
            (a for a in actions if a.method == "GET" and a.endpoint == "/users"),
            None,
        )
        assert get_users is not None
        assert get_users.params is not None
        # page has default=1, limit has example=20
        assert get_users.params.get("page") == 1
        assert get_users.params.get("limit") == 20

    def test_parse_extracts_request_body(self):
        """Test that request body examples are extracted."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(TEST_OPENAPI_JSON)

        # Find POST /users which has a request body example
        post_users = next(
            (a for a in actions if a.method == "POST" and a.endpoint == "/users"),
            None,
        )
        assert post_users is not None
        assert post_users.body is not None
        assert post_users.body.get("name") == "John Doe"
        assert post_users.body.get("email") == "john@example.com"

    def test_parse_extracts_auth_requirements(self):
        """Test that authentication requirements are detected."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(TEST_OPENAPI_JSON)

        # GET /users has global security (requires auth)
        get_users = next(
            (a for a in actions if a.method == "GET" and a.endpoint == "/users"),
            None,
        )
        assert get_users is not None
        assert get_users.requires_auth is True

        # POST /users has security: [] (no auth)
        post_users = next(
            (a for a in actions if a.method == "POST" and a.endpoint == "/users"),
            None,
        )
        assert post_users is not None
        assert post_users.requires_auth is False

    def test_parse_extracts_header_params(self):
        """Test that header parameters are extracted."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(TEST_OPENAPI_JSON)

        # GET /items has X-Request-ID header
        get_items = next(
            (a for a in actions if a.method == "GET" and a.endpoint == "/items"),
            None,
        )
        assert get_items is not None
        assert get_items.headers is not None
        assert get_items.headers.get("X-Request-ID") == "req-12345"

    def test_parse_with_exclude_patterns(self):
        """Test parsing with exclude patterns."""
        config = ExplorationConfig(exclude_patterns=[r"/internal/.*"])
        discoverer = APIDiscoverer(base_url="http://localhost:8000", config=config)
        actions = discoverer.parse_openapi_spec(TEST_OPENAPI_JSON)

        # /internal/admin should be excluded
        internal_endpoints = [a for a in actions if "/internal/" in a.endpoint]
        assert len(internal_endpoints) == 0

    def test_parse_with_include_patterns(self):
        """Test parsing with include patterns."""
        config = ExplorationConfig(include_patterns=[r"/users.*"])
        discoverer = APIDiscoverer(base_url="http://localhost:8000", config=config)
        actions = discoverer.parse_openapi_spec(TEST_OPENAPI_JSON)

        # Only /users and /users/{userId} endpoints should be included
        assert all("/users" in a.endpoint for a in actions)
        assert len(actions) == 5  # GET/POST /users + GET/PUT/DELETE /users/{userId}

    def test_parse_invalid_spec_raises_error(self):
        """Test that invalid spec raises ValueError."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        with pytest.raises(ValueError, match="missing 'openapi' or 'swagger'"):
            discoverer.parse_openapi_spec({"paths": {}})

    def test_parse_empty_paths(self):
        """Test parsing spec with no paths."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Empty API", "version": "1.0.0"},
            "paths": {},
        }

        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(spec)

        assert actions == []


class TestBuildExampleFromSchema:
    """Test building example values from OpenAPI schemas."""

    def test_build_string_example(self):
        """Test building string example."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        schema = {"type": "string"}
        result = discoverer._build_example_from_schema(schema)
        assert result == "string"

    def test_build_string_with_format(self):
        """Test building string with format."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        assert discoverer._build_example_from_schema({"type": "string", "format": "email"}) == "user@example.com"
        assert discoverer._build_example_from_schema({"type": "string", "format": "date"}) == "2024-01-01"
        assert discoverer._build_example_from_schema({"type": "string", "format": "uuid"}).count("-") == 4

    def test_build_string_with_enum(self):
        """Test building string from enum."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        schema = {"type": "string", "enum": ["active", "inactive", "pending"]}
        result = discoverer._build_example_from_schema(schema)
        assert result == "active"

    def test_build_integer_example(self):
        """Test building integer example."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        schema = {"type": "integer"}
        result = discoverer._build_example_from_schema(schema)
        assert result == 0

    def test_build_integer_with_minimum(self):
        """Test building integer with minimum."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        schema = {"type": "integer", "minimum": 5}
        result = discoverer._build_example_from_schema(schema)
        assert result == 5

    def test_build_number_example(self):
        """Test building number example."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        schema = {"type": "number", "minimum": 1.5}
        result = discoverer._build_example_from_schema(schema)
        assert result == 1.5

    def test_build_boolean_example(self):
        """Test building boolean example."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        schema = {"type": "boolean"}
        result = discoverer._build_example_from_schema(schema)
        assert result is True

    def test_build_array_example(self):
        """Test building array example."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        schema = {"type": "array", "items": {"type": "string"}}
        result = discoverer._build_example_from_schema(schema)
        assert result == ["string"]

    def test_build_object_example(self):
        """Test building object example."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
        }
        result = discoverer._build_example_from_schema(schema)
        assert result == {"name": "string", "age": 0}

    def test_build_uses_explicit_example(self):
        """Test that explicit example takes precedence."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        schema = {"type": "string", "example": "custom_value"}
        result = discoverer._build_example_from_schema(schema)
        assert result == "custom_value"

    def test_build_nested_object(self):
        """Test building nested object example."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "email": {"type": "string", "format": "email"},
                    },
                },
            },
        }
        result = discoverer._build_example_from_schema(schema)
        assert result == {"user": {"id": 0, "email": "user@example.com"}}


class TestDiscovererClearAndState:
    """Test discoverer state management."""

    def test_clear_removes_all_discovered(self):
        """Test that clear removes all discovered endpoints."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        discoverer.add_seed_endpoints([("GET", "/users"), ("POST", "/items")])

        assert len(discoverer.discovered_actions) == 2
        assert len(discoverer.discovered_endpoints) == 2

        discoverer.clear()

        assert len(discoverer.discovered_actions) == 0
        assert len(discoverer.discovered_endpoints) == 0

    def test_get_endpoint_count(self):
        """Test getting endpoint count."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        discoverer.add_seed_endpoints([
            ("GET", "/users"),
            ("POST", "/users"),  # Same endpoint, different method
            ("GET", "/items"),
        ])

        # Should have 2 unique endpoints
        assert discoverer.get_endpoint_count() == 2


class TestFromOpenAPI:
    """Test the from_openapi convenience method."""

    def test_from_openapi_loads_file(self):
        """Test from_openapi loads a spec file."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.from_openapi(str(TEST_OPENAPI_JSON))

        assert len(actions) == 9
        methods = {a.method for a in actions}
        assert "GET" in methods
        assert "POST" in methods

    def test_from_openapi_nonexistent_file_raises_error(self):
        """Test from_openapi raises FileNotFoundError for missing files."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        with pytest.raises(FileNotFoundError):
            discoverer.from_openapi("/nonexistent/path/openapi.json")

    def test_from_openapi_directory_raises_error(self):
        """Test from_openapi raises ValueError for directories."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        with pytest.raises(ValueError, match="not a file"):
            discoverer.from_openapi(str(FIXTURES_DIR))


class TestParseOpenAPIYAML:
    """Test parsing YAML OpenAPI specs."""

    def test_parse_yaml_string(self):
        """Test parsing YAML format spec."""
        yaml_spec = """
openapi: "3.0.0"
info:
  title: YAML Test API
  version: "1.0.0"
paths:
  /test:
    get:
      summary: Test endpoint
      responses:
        "200":
          description: OK
"""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(yaml_spec)

        assert len(actions) == 1
        assert actions[0].method == "GET"
        assert actions[0].endpoint == "/test"


class TestParseSwagger2:
    """Test parsing Swagger 2.0 specs."""

    def test_parse_swagger2_spec(self):
        """Test parsing Swagger 2.0 format spec."""
        spec = {
            "swagger": "2.0",
            "info": {"title": "Swagger 2.0 API", "version": "1.0.0"},
            "paths": {
                "/legacy": {
                    "get": {
                        "summary": "Legacy endpoint",
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }

        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(spec)

        assert len(actions) == 1
        assert actions[0].endpoint == "/legacy"


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_parse_spec_with_path_item_ref(self):
        """Test handling path items that might have $ref."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/normal": {
                    "get": {
                        "responses": {"200": {"description": "OK"}},
                    }
                },
                # This path item has a string value (might be $ref or invalid)
                "/ref-path": "invalid",
            },
        }

        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(spec)

        # Should only parse the valid path
        assert len(actions) == 1
        assert actions[0].endpoint == "/normal"

    def test_parse_operation_without_responses(self):
        """Test parsing operation that might be missing responses."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/minimal": {
                    "get": {
                        "responses": {"200": {"description": "OK"}},
                    },  # Minimal operation with required responses field
                }
            },
        }

        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(spec)

        assert len(actions) == 1
        assert actions[0].endpoint == "/minimal"
        assert actions[0].description is None

    def test_long_description_truncated(self):
        """Test that very long descriptions are truncated."""
        long_description = "A" * 300
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/verbose": {
                    "get": {
                        "summary": long_description,
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }

        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(spec)

        assert len(actions[0].description) == 200  # 197 + "..."

    def test_parameter_without_name_ignored(self):
        """Test that parameters without name are handled."""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/test": {
                    "get": {
                        "parameters": [
                            {"in": "query", "schema": {"type": "string"}},  # Missing name
                            {"name": "valid", "in": "query", "example": "test"},
                        ],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }

        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        actions = discoverer.parse_openapi_spec(spec)

        assert actions[0].params == {"valid": "test"}


class TestComprehensiveOpenAPI:
    """Test parsing a comprehensive OpenAPI spec with $ref resolution."""

    COMPREHENSIVE_OPENAPI_YAML = FIXTURES_DIR / "comprehensive_openapi.yaml"

    def test_from_openapi_yaml_file(self):
        """Test loading a comprehensive YAML OpenAPI spec."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # Should have many endpoints
        assert len(actions) >= 15

        # Verify methods are extracted
        methods = {a.method for a in actions}
        assert "GET" in methods
        assert "POST" in methods
        assert "PUT" in methods
        assert "DELETE" in methods
        assert "PATCH" in methods

    def test_ref_resolution_in_parameters(self):
        """Test that $ref parameters are properly resolved."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # GET /users uses $ref for PageParam and LimitParam
        get_users = next(
            (a for a in actions if a.method == "GET" and a.endpoint == "/users"),
            None,
        )
        assert get_users is not None
        assert get_users.params is not None

        # PageParam has default=1, LimitParam has default=20
        assert get_users.params.get("page") == 1
        assert get_users.params.get("limit") == 20
        # status has default=active
        assert get_users.params.get("status") == "active"

    def test_ref_resolution_in_request_body(self):
        """Test that $ref requestBodies are properly resolved."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # POST /users uses $ref for requestBody
        post_users = next(
            (a for a in actions if a.method == "POST" and a.endpoint == "/users"),
            None,
        )
        assert post_users is not None
        assert post_users.body is not None

        # The example should be used
        assert post_users.body.get("email") == "newuser@example.com"
        assert post_users.body.get("name") == "New User"

    def test_ref_resolution_in_schema(self):
        """Test that $ref schemas in request bodies are resolved."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # POST /products has inline example
        post_products = next(
            (a for a in actions if a.method == "POST" and a.endpoint == "/products"),
            None,
        )
        assert post_products is not None
        assert post_products.body is not None
        assert post_products.body.get("name") == "Premium Widget"
        assert post_products.body.get("price") == 99.99

    def test_allof_schema_resolution(self):
        """Test that allOf schemas are properly merged."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        # Parse the spec and check that allOf schemas work
        spec = discoverer._load_spec(self.COMPREHENSIVE_OPENAPI_YAML)
        discoverer._spec_components = spec.get("components", {})

        # UserWithProfile uses allOf to combine User and profile
        user_with_profile = discoverer._spec_components["schemas"]["UserWithProfile"]
        example = discoverer._build_example_from_schema(user_with_profile)

        # Should have fields from both User and the added profile
        assert "id" in example  # From User
        assert "email" in example  # From User
        assert "profile" in example  # From added object

    def test_path_parameters_resolved_with_examples(self):
        """Test that path parameters with examples are extracted."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # GET /users/{userId} uses UserIdParam with example=42
        get_user = next(
            (a for a in actions if a.method == "GET" and a.endpoint == "/users/{userId}"),
            None,
        )
        assert get_user is not None
        assert get_user.params is not None
        # Path params are stored under _path_params
        path_params = get_user.params.get("_path_params", {})
        assert path_params.get("userId") == 42

    def test_header_parameters_extracted(self):
        """Test that header parameters are properly extracted."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # GET /users has X-Correlation-ID header parameter
        get_users = next(
            (a for a in actions if a.method == "GET" and a.endpoint == "/users"),
            None,
        )
        assert get_users is not None
        assert get_users.headers is not None
        assert "X-Correlation-ID" in get_users.headers
        assert get_users.headers["X-Correlation-ID"] == "550e8400-e29b-41d4-a716-446655440000"

    def test_cookie_parameters_in_headers(self):
        """Test that cookie parameters are converted to Cookie header."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # GET /orders has X-Session-ID cookie parameter
        get_orders = next(
            (a for a in actions if a.method == "GET" and a.endpoint == "/orders"),
            None,
        )
        assert get_orders is not None
        assert get_orders.headers is not None
        # Cookie params should be in Cookie header
        assert "Cookie" in get_orders.headers
        assert "X-Session-ID=session_abc123" in get_orders.headers["Cookie"]

    def test_security_requirements_detected(self):
        """Test that security requirements are properly detected."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # GET /users requires auth (global security)
        get_users = next(
            (a for a in actions if a.method == "GET" and a.endpoint == "/users"),
            None,
        )
        assert get_users is not None
        assert get_users.requires_auth is True

        # POST /users has security: [] (no auth)
        post_users = next(
            (a for a in actions if a.method == "POST" and a.endpoint == "/users"),
            None,
        )
        assert post_users is not None
        assert post_users.requires_auth is False

        # GET /health has security: [] (no auth)
        get_health = next(
            (a for a in actions if a.method == "GET" and a.endpoint == "/health"),
            None,
        )
        assert get_health is not None
        assert get_health.requires_auth is False

    def test_multipart_form_data_request_body(self):
        """Test that multipart/form-data request bodies are handled."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # POST /users/{userId}/avatar uses multipart/form-data
        upload_avatar = next(
            (a for a in actions if a.method == "POST" and a.endpoint == "/users/{userId}/avatar"),
            None,
        )
        assert upload_avatar is not None
        assert upload_avatar.body is not None
        # Should have form fields
        assert "file" in upload_avatar.body or "description" in upload_avatar.body

    def test_examples_used_in_request_body(self):
        """Test that request body examples are used when available."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # PATCH /users/{userId}/profile has examples in requestBody
        patch_profile = next(
            (a for a in actions if a.method == "PATCH" and a.endpoint == "/users/{userId}/profile"),
            None,
        )
        assert patch_profile is not None
        assert patch_profile.body is not None
        # Should use first example
        assert "bio" in patch_profile.body or "avatar_url" in patch_profile.body

    def test_nested_object_schemas_resolved(self):
        """Test that nested object schemas are properly resolved."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # POST /orders has nested CreateOrder schema with Address
        post_order = next(
            (a for a in actions if a.method == "POST" and a.endpoint == "/orders"),
            None,
        )
        assert post_order is not None
        assert post_order.body is not None
        # Should have shippingAddress nested object
        assert "shippingAddress" in post_order.body
        assert isinstance(post_order.body["shippingAddress"], dict)
        # Address should have required fields
        shipping = post_order.body["shippingAddress"]
        assert "street" in shipping
        assert "city" in shipping
        assert "country" in shipping

    def test_array_items_resolved(self):
        """Test that array item schemas are properly resolved."""
        discoverer = APIDiscoverer(base_url="https://api.example.com/v1")
        actions = discoverer.from_openapi(str(self.COMPREHENSIVE_OPENAPI_YAML))

        # POST /orders has items array
        post_order = next(
            (a for a in actions if a.method == "POST" and a.endpoint == "/orders"),
            None,
        )
        assert post_order is not None
        assert post_order.body is not None
        assert "items" in post_order.body
        assert isinstance(post_order.body["items"], list)
        # Each item should have productId and quantity
        if post_order.body["items"]:
            item = post_order.body["items"][0]
            assert "productId" in item
            assert "quantity" in item


class TestRefResolution:
    """Test $ref resolution in isolation."""

    def test_resolve_simple_schema_ref(self):
        """Test resolving a simple schema $ref."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        discoverer._spec_components = {
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                    },
                }
            }
        }

        resolved = discoverer._resolve_ref("#/components/schemas/User")
        assert resolved["type"] == "object"
        assert "id" in resolved["properties"]
        assert "name" in resolved["properties"]

    def test_resolve_parameter_ref(self):
        """Test resolving a parameter $ref."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        discoverer._spec_components = {
            "parameters": {
                "PageParam": {
                    "name": "page",
                    "in": "query",
                    "schema": {"type": "integer", "default": 1},
                }
            }
        }

        param = {"$ref": "#/components/parameters/PageParam"}
        resolved = discoverer._resolve_parameter(param)
        assert resolved["name"] == "page"
        assert resolved["in"] == "query"
        assert resolved["schema"]["default"] == 1

    def test_resolve_nonexistent_ref(self):
        """Test that nonexistent $ref returns empty dict."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        discoverer._spec_components = {}

        resolved = discoverer._resolve_ref("#/components/schemas/NonExistent")
        assert resolved == {}

    def test_resolve_external_ref_returns_empty(self):
        """Test that external $refs return empty dict."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        discoverer._spec_components = {}

        # External refs (not starting with #/) are not supported
        resolved = discoverer._resolve_ref("./external.yaml#/components/schemas/User")
        assert resolved == {}

    def test_build_example_with_circular_ref(self):
        """Test that circular $refs don't cause infinite recursion."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")
        discoverer._spec_components = {
            "schemas": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "children": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Node"},
                        },
                    },
                }
            }
        }

        # This should not hang due to circular reference
        schema = {"$ref": "#/components/schemas/Node"}
        result = discoverer._build_example_from_schema(schema)

        assert isinstance(result, dict)
        assert "value" in result
        assert "children" in result


class TestBuildExampleEnhancements:
    """Test enhanced example building from schemas."""

    def test_build_with_default_value(self):
        """Test that default values are used."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        schema = {"type": "string", "default": "default_value"}
        result = discoverer._build_example_from_schema(schema)
        assert result == "default_value"

    def test_build_integer_with_exclusive_minimum(self):
        """Test integer with exclusiveMinimum."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        schema = {"type": "integer", "exclusiveMinimum": 5}
        result = discoverer._build_example_from_schema(schema)
        assert result == 6

    def test_build_number_with_exclusive_minimum(self):
        """Test number with exclusiveMinimum."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        schema = {"type": "number", "exclusiveMinimum": 0.0}
        result = discoverer._build_example_from_schema(schema)
        assert result == 0.1

    def test_build_string_with_minlength(self):
        """Test string respects minLength."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        schema = {"type": "string", "minLength": 5}
        result = discoverer._build_example_from_schema(schema)
        assert len(result) >= 5

    def test_build_string_formats(self):
        """Test various string formats."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        formats = {
            "hostname": "example.com",
            "ipv4": "192.168.1.1",
            "ipv6": "::1",
            "password": "password123",
            "byte": "dGVzdA==",
            "time": "12:00:00",
        }

        for fmt, expected in formats.items():
            schema = {"type": "string", "format": fmt}
            result = discoverer._build_example_from_schema(schema)
            assert result == expected, f"Format {fmt} should return {expected}, got {result}"

    def test_build_null_type(self):
        """Test null type returns None."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        schema = {"type": "null"}
        result = discoverer._build_example_from_schema(schema)
        assert result is None

    def test_build_oneof_uses_first(self):
        """Test oneOf uses first option."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        schema = {
            "oneOf": [
                {"type": "string", "example": "option1"},
                {"type": "integer", "example": 42},
            ]
        }
        result = discoverer._build_example_from_schema(schema)
        assert result == "option1"

    def test_build_anyof_uses_first(self):
        """Test anyOf uses first option."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        schema = {
            "anyOf": [
                {"type": "integer", "example": 100},
                {"type": "string"},
            ]
        }
        result = discoverer._build_example_from_schema(schema)
        assert result == 100

    def test_build_infers_type_from_properties(self):
        """Test type is inferred as object when properties exist."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        # No type specified but has properties
        schema = {
            "properties": {
                "name": {"type": "string"},
            }
        }
        result = discoverer._build_example_from_schema(schema)
        assert isinstance(result, dict)
        assert "name" in result

    def test_build_infers_type_from_items(self):
        """Test type is inferred as array when items exist."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        # No type specified but has items
        schema = {
            "items": {"type": "string"}
        }
        result = discoverer._build_example_from_schema(schema)
        assert isinstance(result, list)

    def test_build_additional_properties(self):
        """Test additionalProperties in object without properties."""
        discoverer = APIDiscoverer(base_url="http://localhost:8000")

        schema = {
            "type": "object",
            "additionalProperties": {"type": "string"}
        }
        result = discoverer._build_example_from_schema(schema)
        assert isinstance(result, dict)
        # Should have at least one example additional property
        assert "additionalProp1" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
