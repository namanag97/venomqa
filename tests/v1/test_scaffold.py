"""Tests for OpenAPI scaffold (parse_openapi + generate_actions_code)."""

from __future__ import annotations

import pytest

from venomqa.v1.cli.scaffold import (
    EndpointDef,
    generate_actions_code,
    parse_openapi,
    _sanitize_name,
    _infer_tag,
)


# ─── Minimal OpenAPI fixtures ──────────────────────────────────────────────

MINIMAL_SPEC: dict = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {
        "/users": {
            "get": {
                "summary": "List users",
                "responses": {"200": {"description": "OK"}},
            },
            "post": {
                "summary": "Create user",
                "requestBody": {"content": {"application/json": {"schema": {}}}},
                "responses": {
                    "201": {
                        "description": "Created",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                                }
                            }
                        },
                    }
                },
            },
        },
        "/users/{id}": {
            "get": {
                "summary": "Get user by id",
                "responses": {"200": {"description": "OK"}},
            },
            "delete": {
                "summary": "Delete user",
                "responses": {"204": {"description": "No content"}},
            },
        },
        "/orders": {
            "post": {
                "summary": "Create order",
                "requestBody": {"content": {}},
                "responses": {"201": {"description": "Created"}},
            },
        },
    },
}


# ─── _sanitize_name ─────────────────────────────────────────────────────────

class TestSanitizeName:
    def test_simple_post(self):
        assert _sanitize_name("POST", "/users") == "post_users"

    def test_simple_get(self):
        assert _sanitize_name("GET", "/users") == "get_users"

    def test_path_param_becomes_by(self):
        assert _sanitize_name("GET", "/users/{id}") == "get_users_by_id"

    def test_delete_with_param(self):
        assert _sanitize_name("DELETE", "/orders/{id}") == "delete_orders_by_id"

    def test_nested_path(self):
        name = _sanitize_name("PATCH", "/users/{id}/profile")
        assert name == "patch_users_by_id_profile"


# ─── _infer_tag ──────────────────────────────────────────────────────────────

class TestInferTag:
    def test_plural_resource(self):
        assert _infer_tag("/users") == "user"

    def test_nested_resource(self):
        assert _infer_tag("/users/{id}") == "user"

    def test_versioned_path(self):
        # v1 segment skipped
        assert _infer_tag("/v1/orders") == "order"


# ─── parse_openapi ───────────────────────────────────────────────────────────

class TestParseOpenapi:
    def test_rejects_swagger_2(self):
        with pytest.raises(ValueError, match="Not an OpenAPI 3.x"):
            parse_openapi({"swagger": "2.0", "paths": {}})

    def test_rejects_empty_paths(self):
        with pytest.raises(ValueError, match="no 'paths'"):
            parse_openapi({"openapi": "3.0.0", "paths": {}})

    def test_parses_minimal_spec(self):
        endpoints = parse_openapi(MINIMAL_SPEC)
        assert len(endpoints) == 5  # GET /users, POST /users, GET /users/{id}, DELETE /users/{id}, POST /orders

    def test_method_names_correct(self):
        endpoints = parse_openapi(MINIMAL_SPEC)
        methods = {ep.method for ep in endpoints}
        assert "GET" in methods
        assert "POST" in methods
        assert "DELETE" in methods

    def test_path_params_extracted(self):
        endpoints = parse_openapi(MINIMAL_SPEC)
        user_by_id = next(ep for ep in endpoints if ep.path == "/users/{id}" and ep.method == "GET")
        assert user_by_id.path_params == ["id"]

    def test_no_path_params_for_collection(self):
        endpoints = parse_openapi(MINIMAL_SPEC)
        list_users = next(ep for ep in endpoints if ep.path == "/users" and ep.method == "GET")
        assert list_users.path_params == []

    def test_response_has_id_detected(self):
        endpoints = parse_openapi(MINIMAL_SPEC)
        create_user = next(ep for ep in endpoints if ep.path == "/users" and ep.method == "POST")
        assert create_user.response_has_id is True

    def test_response_no_id_for_list(self):
        endpoints = parse_openapi(MINIMAL_SPEC)
        list_users = next(ep for ep in endpoints if ep.path == "/users" and ep.method == "GET")
        # List endpoint has no id in schema
        assert list_users.response_has_id is False

    def test_expected_status_from_spec(self):
        endpoints = parse_openapi(MINIMAL_SPEC)
        create_user = next(ep for ep in endpoints if ep.path == "/users" and ep.method == "POST")
        assert 201 in create_user.expected_status

    def test_delete_expected_status(self):
        endpoints = parse_openapi(MINIMAL_SPEC)
        delete_user = next(ep for ep in endpoints if ep.path == "/users/{id}" and ep.method == "DELETE")
        assert 204 in delete_user.expected_status

    def test_func_name_generated(self):
        endpoints = parse_openapi(MINIMAL_SPEC)
        names = {ep.func_name for ep in endpoints}
        assert "get_users" in names
        assert "post_users" in names
        assert "get_users_by_id" in names
        assert "delete_users_by_id" in names

    def test_has_body_for_post_with_request_body(self):
        endpoints = parse_openapi(MINIMAL_SPEC)
        create_user = next(ep for ep in endpoints if ep.path == "/users" and ep.method == "POST")
        assert create_user.has_body is True

    def test_no_body_for_get(self):
        endpoints = parse_openapi(MINIMAL_SPEC)
        list_users = next(ep for ep in endpoints if ep.path == "/users" and ep.method == "GET")
        assert list_users.has_body is False


# ─── generate_actions_code ──────────────────────────────────────────────────

class TestGenerateActionsCode:
    def _parse(self) -> list[EndpointDef]:
        return parse_openapi(MINIMAL_SPEC)

    def test_raises_on_empty_endpoints(self):
        with pytest.raises(ValueError, match="No endpoints"):
            generate_actions_code([])

    def test_output_is_valid_python(self):
        endpoints = self._parse()
        code = generate_actions_code(endpoints, base_url="http://api.example.com")
        compile(code, "<generated>", "exec")  # Must not raise SyntaxError

    def test_contains_venomqa_imports(self):
        code = generate_actions_code(self._parse())
        assert "from venomqa.v1 import" in code

    def test_contains_action_functions(self):
        code = generate_actions_code(self._parse())
        assert "def get_users(api, context):" in code
        assert "def post_users(api, context):" in code
        assert "def get_users_by_id(api, context):" in code
        assert "def delete_users_by_id(api, context):" in code

    def test_path_param_uses_context_get(self):
        code = generate_actions_code(self._parse())
        # /users/{id} should read user_id from context
        assert 'context.get("user_id")' in code

    def test_post_with_body_uses_json(self):
        code = generate_actions_code(self._parse())
        assert "api.post" in code
        assert "json=" in code

    def test_response_id_stored_in_context(self):
        code = generate_actions_code(self._parse())
        # POST /users has id in response → should store user_id
        assert 'context.set("user_id"' in code

    def test_actions_list_present(self):
        code = generate_actions_code(self._parse())
        assert "ACTIONS = [" in code
        assert 'name="get_users"' in code
        assert 'name="post_users"' in code

    def test_expected_status_in_action_list(self):
        code = generate_actions_code(self._parse())
        assert "expected_status=[201]" in code

    def test_agent_setup_at_bottom(self):
        code = generate_actions_code(self._parse())
        assert 'if __name__ == "__main__":' in code
        assert "agent = Agent(" in code
        assert "result = agent.explore()" in code

    def test_base_url_in_output(self):
        code = generate_actions_code(self._parse(), base_url="http://myapi.example.com")
        assert "http://myapi.example.com" in code

    def test_journey_name_in_docstring(self):
        code = generate_actions_code(self._parse(), journey_name="my_journey")
        assert "my_journey" in code
