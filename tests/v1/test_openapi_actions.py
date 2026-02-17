"""Tests for OpenAPI action generator."""

import pytest

from venomqa.v1.generators.openapi_actions import (
    EndpointInfo,
    generate_actions,
    generate_schema_and_actions,
    parse_openapi_endpoints,
    _infer_operation_type,
    _singularize,
)


class TestSingularize:
    def test_regular_plural(self):
        assert _singularize("workspaces") == "workspace"
        assert _singularize("uploads") == "upload"

    def test_ies_plural(self):
        assert _singularize("entries") == "entry"
        assert _singularize("categories") == "category"

    def test_es_plural(self):
        assert _singularize("statuses") == "status"
        assert _singularize("boxes") == "box"

    def test_already_singular(self):
        assert _singularize("user") == "user"
        assert _singularize("data") == "data"


class TestInferOperationType:
    def test_post_is_create(self):
        assert _infer_operation_type("post", "/workspaces", []) == "create"
        assert _infer_operation_type("POST", "/workspaces/{id}/uploads", ["id"]) == "create"

    def test_get_with_id_is_read(self):
        assert _infer_operation_type("get", "/workspaces/{workspace_id}", ["workspace_id"]) == "read"

    def test_get_without_id_is_list(self):
        assert _infer_operation_type("get", "/workspaces", []) == "list"

    def test_put_is_update(self):
        assert _infer_operation_type("put", "/workspaces/{id}", ["id"]) == "update"

    def test_patch_is_update(self):
        assert _infer_operation_type("patch", "/workspaces/{id}", ["id"]) == "update"

    def test_delete_is_delete(self):
        assert _infer_operation_type("delete", "/workspaces/{id}", ["id"]) == "delete"


class TestParseOpenAPIEndpoints:
    @pytest.fixture
    def simple_spec(self):
        return {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/workspaces": {
                    "get": {"operationId": "listWorkspaces", "summary": "List all workspaces"},
                    "post": {"operationId": "createWorkspace", "summary": "Create workspace"},
                },
                "/workspaces/{workspace_id}": {
                    "get": {"operationId": "getWorkspace"},
                    "delete": {"operationId": "deleteWorkspace"},
                },
            },
        }

    @pytest.fixture
    def nested_spec(self):
        return {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/workspaces/{workspace_id}/uploads": {
                    "get": {"operationId": "listUploads"},
                    "post": {"operationId": "createUpload"},
                },
                "/workspaces/{workspace_id}/uploads/{upload_id}": {
                    "get": {"operationId": "getUpload"},
                    "delete": {"operationId": "deleteUpload"},
                },
            },
        }

    def test_parse_simple_endpoints(self, simple_spec):
        endpoints = parse_openapi_endpoints(simple_spec)
        assert len(endpoints) == 4

        # Check list workspaces
        list_ep = next(e for e in endpoints if e.operation_id == "listWorkspaces")
        assert list_ep.method == "GET"
        assert list_ep.path == "/workspaces"
        assert list_ep.operation == "list"
        assert list_ep.requires == []

        # Check create workspace
        create_ep = next(e for e in endpoints if e.operation_id == "createWorkspace")
        assert create_ep.method == "POST"
        assert create_ep.operation == "create"
        assert create_ep.requires == []

        # Check get workspace
        get_ep = next(e for e in endpoints if e.operation_id == "getWorkspace")
        assert get_ep.method == "GET"
        assert get_ep.operation == "read"
        assert get_ep.path_params == ["workspace_id"]

    def test_parse_nested_endpoints(self, nested_spec):
        endpoints = parse_openapi_endpoints(nested_spec)
        assert len(endpoints) == 4

        # Check create upload - should require workspace
        create_ep = next(e for e in endpoints if e.operation_id == "createUpload")
        assert create_ep.method == "POST"
        assert create_ep.operation == "create"
        assert create_ep.resource_type == "upload"
        assert "workspace" in create_ep.requires

        # Check get upload
        get_ep = next(e for e in endpoints if e.operation_id == "getUpload")
        assert get_ep.operation == "read"
        assert "workspace" in get_ep.requires


class TestGenerateActions:
    @pytest.fixture
    def spec(self):
        return {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/workspaces": {
                    "get": {"operationId": "listWorkspaces"},
                    "post": {"operationId": "createWorkspace"},
                },
                "/workspaces/{workspace_id}": {
                    "get": {"operationId": "getWorkspace"},
                    "delete": {"operationId": "deleteWorkspace"},
                },
                "/workspaces/{workspace_id}/uploads": {
                    "post": {"operationId": "createUpload"},
                },
            },
        }

    def test_generate_actions_from_spec(self, spec):
        actions = generate_actions(spec)
        assert len(actions) == 5

        # Check action names
        names = {a.name for a in actions}
        assert "listWorkspaces" in names
        assert "createWorkspace" in names
        assert "createUpload" in names

    def test_actions_have_requires(self, spec):
        actions = generate_actions(spec)

        # Find createUpload
        create_upload = next(a for a in actions if a.name == "createUpload")
        assert hasattr(create_upload, "requires")
        assert "workspace" in create_upload.requires

        # Find createWorkspace (no requirements)
        create_workspace = next(a for a in actions if a.name == "createWorkspace")
        assert create_workspace.requires == []

    def test_include_patterns(self, spec):
        actions = generate_actions(spec, include_patterns=["/workspaces"])
        assert len(actions) == 2  # Only list and create

    def test_exclude_patterns(self, spec):
        actions = generate_actions(spec, exclude_patterns=["*/uploads*"])
        assert len(actions) == 4  # All except upload endpoint


class TestGenerateSchemaAndActions:
    def test_returns_both(self):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"},
            "paths": {
                "/workspaces": {"post": {}},
                "/workspaces/{workspace_id}/uploads": {"post": {}},
            },
        }

        schema, actions = generate_schema_and_actions(spec)

        # Check schema
        assert "workspace" in schema.types
        assert "upload" in schema.types
        assert schema.types["upload"].parent == "workspace"

        # Check actions
        assert len(actions) == 2


class TestActionExecution:
    """Test that generated actions actually work."""

    @pytest.fixture
    def mock_api(self):
        class MockApi:
            def __init__(self):
                self.calls = []

            def get(self, url):
                self.calls.append(("GET", url))
                from venomqa.v1.core.action import ActionResult, HTTPRequest, HTTPResponse

                return ActionResult.from_response(
                    HTTPRequest("GET", url),
                    HTTPResponse(200, body={"data": []}),
                )

            def post(self, url, json=None):
                self.calls.append(("POST", url, json))
                from venomqa.v1.core.action import ActionResult, HTTPRequest, HTTPResponse

                return ActionResult.from_response(
                    HTTPRequest("POST", url),
                    HTTPResponse(201, body={"id": "new_123"}),
                )

            def delete(self, url):
                self.calls.append(("DELETE", url))
                from venomqa.v1.core.action import ActionResult, HTTPRequest, HTTPResponse

                return ActionResult.from_response(
                    HTTPRequest("DELETE", url),
                    HTTPResponse(204),
                )

        return MockApi()

    @pytest.fixture
    def mock_context(self):
        from venomqa.v1.core.context import Context

        return Context()

    def test_action_makes_correct_request(self, mock_api, mock_context):
        spec = {
            "paths": {
                "/workspaces": {"get": {"operationId": "listWorkspaces"}},
            }
        }
        actions = generate_actions(spec)
        action = actions[0]

        result = action.invoke(mock_api, mock_context)

        assert result.ok
        assert mock_api.calls == [("GET", "/workspaces")]

    def test_action_substitutes_path_params(self, mock_api, mock_context):
        spec = {
            "paths": {
                "/workspaces/{workspace_id}": {"get": {"operationId": "getWorkspace"}},
            }
        }
        actions = generate_actions(spec)
        action = actions[0]

        mock_context.set("workspace_id", "ws_123")
        result = action.invoke(mock_api, mock_context)

        assert result.ok
        assert mock_api.calls == [("GET", "/workspaces/ws_123")]

    def test_create_action_sets_context(self, mock_api, mock_context):
        spec = {
            "paths": {
                "/workspaces": {"post": {"operationId": "createWorkspace"}},
            }
        }
        actions = generate_actions(spec)
        action = actions[0]

        result = action.invoke(mock_api, mock_context)

        assert result.ok
        # Should have set workspace_id from response
        assert mock_context.get("workspace_id") == "new_123"
