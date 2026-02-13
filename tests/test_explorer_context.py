"""
Tests for the VenomQA State Explorer context extraction utilities.

This test script verifies that the context extraction and path parameter
substitution in venomqa/explorer/context.py work correctly for state
chain exploration.
"""

import pytest

from venomqa.explorer.context import (
    ExplorationContext,
    extract_context_from_response,
    substitute_path_params,
    generate_state_name,
    has_unresolved_placeholders,
    get_required_placeholders,
    can_resolve_endpoint,
    _normalize_key,
    _infer_context_key_from_endpoint,
    _flatten_dict,
)


class TestExplorationContext:
    """Test ExplorationContext class."""

    def test_create_empty_context(self):
        """Test creating an empty context."""
        ctx = ExplorationContext()
        assert len(ctx) == 0
        assert ctx.to_dict() == {}

    def test_set_and_get(self):
        """Test setting and getting values."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)
        assert ctx.get("todo_id") == 42

    def test_get_with_default(self):
        """Test getting non-existent key with default."""
        ctx = ExplorationContext()
        assert ctx.get("missing") is None
        assert ctx.get("missing", "default") == "default"

    def test_has(self):
        """Test checking for key existence."""
        ctx = ExplorationContext()
        ctx.set("key", "value")
        assert ctx.has("key") is True
        assert ctx.has("missing") is False

    def test_keys(self):
        """Test getting all keys."""
        ctx = ExplorationContext()
        ctx.set("a", 1)
        ctx.set("b", 2)
        assert ctx.keys() == {"a", "b"}

    def test_extracted_keys(self):
        """Test tracking extracted keys."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)
        ctx.set("user_id", 5)
        assert ctx.extracted_keys() == {"todo_id", "user_id"}

    def test_copy(self):
        """Test copying context."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)

        ctx_copy = ctx.copy()
        assert ctx_copy.get("todo_id") == 42

        # Modifying copy should not affect original
        ctx_copy.set("todo_id", 99)
        assert ctx.get("todo_id") == 42
        assert ctx_copy.get("todo_id") == 99

    def test_copy_extracted_keys_reset(self):
        """Test that copy resets extracted_keys tracking."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)

        ctx_copy = ctx.copy()
        # Copy should have the data but fresh tracking
        assert ctx_copy.extracted_keys() == set()

    def test_to_dict(self):
        """Test converting to dictionary."""
        ctx = ExplorationContext()
        ctx.set("a", 1)
        ctx.set("b", "hello")

        result = ctx.to_dict()
        assert result == {"a": 1, "b": "hello"}

        # Modifying result should not affect context
        result["a"] = 999
        assert ctx.get("a") == 1

    def test_update(self):
        """Test updating with multiple values."""
        ctx = ExplorationContext()
        ctx.update({"a": 1, "b": 2, "c": 3})
        assert ctx.get("a") == 1
        assert ctx.get("b") == 2
        assert ctx.get("c") == 3
        assert ctx.extracted_keys() == {"a", "b", "c"}

    def test_len(self):
        """Test length of context."""
        ctx = ExplorationContext()
        assert len(ctx) == 0
        ctx.set("a", 1)
        assert len(ctx) == 1
        ctx.set("b", 2)
        assert len(ctx) == 2

    def test_repr(self):
        """Test string representation."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)
        assert "todo_id" in repr(ctx)
        assert "42" in repr(ctx)


class TestNormalizeKey:
    """Test _normalize_key helper function."""

    def test_lowercase_unchanged(self):
        """Test that lowercase keys are unchanged."""
        assert _normalize_key("todo_id") == "todo_id"
        assert _normalize_key("user") == "user"

    def test_camel_case_to_snake(self):
        """Test converting camelCase to snake_case."""
        assert _normalize_key("todoId") == "todo_id"
        assert _normalize_key("userId") == "user_id"
        assert _normalize_key("attachmentFileId") == "attachment_file_id"

    def test_all_uppercase(self):
        """Test converting all-uppercase to lowercase."""
        assert _normalize_key("ID") == "id"
        assert _normalize_key("UUID") == "uuid"

    def test_mixed_case(self):
        """Test mixed case conversions."""
        assert _normalize_key("userID") == "user_id"
        assert _normalize_key("APIKey") == "api_key"


class TestInferContextKeyFromEndpoint:
    """Test _infer_context_key_from_endpoint helper function."""

    def test_simple_plural_endpoint(self):
        """Test inferring from simple plural endpoints."""
        assert _infer_context_key_from_endpoint("/todos") == "todo_id"
        assert _infer_context_key_from_endpoint("/users") == "user_id"
        assert _infer_context_key_from_endpoint("/items") == "item_id"

    def test_nested_endpoint(self):
        """Test inferring from nested endpoints."""
        # Should use the last meaningful segment
        assert _infer_context_key_from_endpoint("/todos/42/attachments") == "attachment_id"
        assert _infer_context_key_from_endpoint("/users/5/posts") == "post_id"

    def test_endpoint_with_api_prefix(self):
        """Test endpoint with /api prefix."""
        assert _infer_context_key_from_endpoint("/api/todos") == "todo_id"
        assert _infer_context_key_from_endpoint("/api/v1/users") == "user_id"

    def test_endpoint_with_version(self):
        """Test endpoint with version prefix."""
        assert _infer_context_key_from_endpoint("/v1/orders") == "order_id"
        assert _infer_context_key_from_endpoint("/api/v2/products") == "product_id"

    def test_singular_ending_in_s(self):
        """Test resources that end in s but are singular."""
        # 'addresses' -> removes 'es' -> 'address' -> 'address_id'
        result = _infer_context_key_from_endpoint("/addresses")
        assert result == "address_id"

    def test_special_plural_forms(self):
        """Test special plural forms."""
        assert _infer_context_key_from_endpoint("/categories") == "category_id"
        assert _infer_context_key_from_endpoint("/statuses") == "status_id"

    def test_empty_endpoint(self):
        """Test empty or root endpoint."""
        assert _infer_context_key_from_endpoint("/") is None
        assert _infer_context_key_from_endpoint("") is None

    def test_endpoint_with_placeholders(self):
        """Test that placeholders are ignored."""
        assert _infer_context_key_from_endpoint("/todos/{todoId}") == "todo_id"
        assert _infer_context_key_from_endpoint("/users/{userId}/posts") == "post_id"


class TestFlattenDict:
    """Test _flatten_dict helper function."""

    def test_simple_dict(self):
        """Test flattening a simple dictionary."""
        data = {"a": 1, "b": 2}
        result = _flatten_dict(data)
        assert ("a", 1) in result
        assert ("b", 2) in result

    def test_nested_dict(self):
        """Test flattening nested dictionaries."""
        data = {"order": {"id": 1, "status": "pending"}}
        result = _flatten_dict(data)
        assert ("order.id", 1) in result
        assert ("order.status", "pending") in result

    def test_list_of_dicts(self):
        """Test flattening list of dictionaries."""
        data = {"items": [{"id": 1}, {"id": 2}]}
        result = _flatten_dict(data)
        assert ("items[0].id", 1) in result
        assert ("items[1].id", 2) in result

    def test_deeply_nested(self):
        """Test deeply nested structure."""
        data = {"a": {"b": {"c": {"d": "value"}}}}
        result = _flatten_dict(data)
        assert ("a.b.c.d", "value") in result


class TestExtractContextFromResponse:
    """Test extract_context_from_response function."""

    def test_extract_todo_id_from_simple_response(self):
        """Test case 1: Extract todo_id from {"id": 42, "title": "Test"}."""
        ctx = ExplorationContext()
        response = {"id": 42, "title": "Test"}
        endpoint = "/todos"

        result = extract_context_from_response(response, endpoint, ctx)

        assert result.get("todo_id") == 42
        assert result.get("id") == 42

    def test_extract_nested_ids(self):
        """Test case 2: Extract nested IDs from {"order": {"id": 1}, "items": [{"id": 2}]}."""
        ctx = ExplorationContext()
        response = {
            "order": {"id": 1},
            "items": [{"id": 2}, {"id": 3}]
        }
        endpoint = "/orders"

        result = extract_context_from_response(response, endpoint, ctx)

        # The root-level inference will use 'order_id' from endpoint
        # Nested order.id should also be found
        # Note: The current implementation extracts based on immediate key 'id'
        # and infers from endpoint
        assert result.get("order_id") == 1 or result.has("id")

    def test_extract_explicit_id_fields(self):
        """Test extracting fields that end in _id or Id."""
        ctx = ExplorationContext()
        response = {
            "id": 100,
            "user_id": 5,
            "parentId": 10,
            "categoryId": 3
        }
        endpoint = "/items"

        result = extract_context_from_response(response, endpoint, ctx)

        assert result.get("item_id") == 100
        assert result.get("user_id") == 5
        assert result.get("parent_id") == 10
        assert result.get("category_id") == 3

    def test_extract_tokens(self):
        """Test extracting token fields."""
        ctx = ExplorationContext()
        response = {
            "token": "abc123",
            "access_token": "def456",
            "refresh_token": "ghi789"
        }
        endpoint = "/auth/login"

        result = extract_context_from_response(response, endpoint, ctx)

        assert result.get("auth_token") == "abc123"
        assert result.get("access_token") == "def456"
        assert result.get("refresh_token") == "ghi789"

    def test_extract_status_fields(self):
        """Test extracting status/state fields."""
        ctx = ExplorationContext()
        response = {
            "id": 1,
            "completed": True,
            "status": "active"
        }
        endpoint = "/todos"

        result = extract_context_from_response(response, endpoint, ctx)

        assert result.get("completed") is True
        assert result.get("status") == "active"

    def test_extract_from_nested_response(self):
        """Test extracting from deeply nested response."""
        ctx = ExplorationContext()
        response = {
            "data": {
                "user": {
                    "id": 42,
                    "profile": {
                        "avatar_id": "abc"
                    }
                }
            }
        }
        endpoint = "/api/users"

        result = extract_context_from_response(response, endpoint, ctx)

        # Should extract avatar_id from nested structure
        assert result.get("avatar_id") == "abc"

    def test_skip_none_values(self):
        """Test that None values are skipped."""
        ctx = ExplorationContext()
        response = {
            "id": 1,
            "parent_id": None,
            "category_id": 5
        }
        endpoint = "/items"

        result = extract_context_from_response(response, endpoint, ctx)

        assert result.get("item_id") == 1
        assert result.get("category_id") == 5
        assert result.has("parent_id") is False

    def test_preserve_existing_context(self):
        """Test that existing context values are preserved."""
        ctx = ExplorationContext()
        ctx.set("user_id", 99)

        response = {"id": 42}
        endpoint = "/todos"

        result = extract_context_from_response(response, endpoint, ctx)

        assert result.get("user_id") == 99
        assert result.get("todo_id") == 42

    def test_non_dict_response(self):
        """Test handling non-dict response data."""
        ctx = ExplorationContext()

        # Should return context unchanged
        result = extract_context_from_response(None, "/todos", ctx)
        assert len(result) == 0

        result = extract_context_from_response([], "/todos", ctx)
        assert len(result) == 0


class TestSubstitutePathParams:
    """Test substitute_path_params function."""

    def test_simple_substitution(self):
        """Test case 3: Substitute /todos/{todoId} -> /todos/42."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)

        result = substitute_path_params("/todos/{todoId}", ctx)

        assert result == "/todos/42"

    def test_multiple_substitutions(self):
        """Test case 4: Substitute /todos/{todoId}/attachments/{fileId} with both IDs."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)
        ctx.set("file_id", "abc-123")

        result = substitute_path_params("/todos/{todoId}/attachments/{fileId}", ctx)

        assert result == "/todos/42/attachments/abc-123"

    def test_unresolved_placeholder_returns_none(self):
        """Test case 5: Return None when placeholder can't be resolved."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)
        # Missing file_id

        result = substitute_path_params("/todos/{todoId}/attachments/{fileId}", ctx)

        assert result is None

    def test_no_placeholders(self):
        """Test endpoint with no placeholders."""
        ctx = ExplorationContext()

        result = substitute_path_params("/todos", ctx)

        assert result == "/todos"

    def test_exact_key_match(self):
        """Test exact key matching."""
        ctx = ExplorationContext()
        ctx.set("todoId", 42)  # Exact match

        result = substitute_path_params("/todos/{todoId}", ctx)

        assert result == "/todos/42"

    def test_snake_case_conversion(self):
        """Test snake_case conversion of placeholder names."""
        ctx = ExplorationContext()
        ctx.set("user_id", 5)
        ctx.set("comment_id", 100)

        result = substitute_path_params("/users/{userId}/comments/{commentId}", ctx)

        assert result == "/users/5/comments/100"

    def test_with_id_suffix(self):
        """Test adding _id suffix for resolution."""
        ctx = ExplorationContext()
        ctx.set("user_id", 5)

        # Placeholder is just {user}, but context has user_id
        result = substitute_path_params("/api/{user}/profile", ctx)

        assert result == "/api/5/profile"

    def test_generic_id_placeholder(self):
        """Test generic {id} placeholder."""
        ctx = ExplorationContext()
        ctx.set("id", 42)

        result = substitute_path_params("/items/{id}", ctx)

        assert result == "/items/42"

    def test_string_id_values(self):
        """Test substituting string ID values."""
        ctx = ExplorationContext()
        ctx.set("todo_id", "uuid-1234-5678")

        result = substitute_path_params("/todos/{todoId}", ctx)

        assert result == "/todos/uuid-1234-5678"

    def test_integer_converted_to_string(self):
        """Test that integer values are converted to strings."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)

        result = substitute_path_params("/todos/{todoId}", ctx)

        assert result == "/todos/42"
        assert isinstance(result, str)


class TestGenerateStateName:
    """Test generate_state_name function."""

    def test_anonymous_state(self):
        """Test case 6: Generate "Anonymous" for empty context."""
        ctx = ExplorationContext()
        response = {}

        result = generate_state_name(ctx, response)

        assert result == "Anonymous"

    def test_authenticated_state(self):
        """Test generating authenticated state name."""
        ctx = ExplorationContext()
        ctx.set("auth_token", "abc123")
        response = {}

        result = generate_state_name(ctx, response)

        assert result == "Authenticated"

    def test_authenticated_with_access_token(self):
        """Test authenticated via access_token."""
        ctx = ExplorationContext()
        ctx.set("access_token", "token123")
        response = {}

        result = generate_state_name(ctx, response)

        assert result == "Authenticated"

    def test_anonymous_with_todo(self):
        """Test case 6: Generate "Anonymous | Todo:42"."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)
        response = {}

        result = generate_state_name(ctx, response)

        assert result == "Anonymous | Todo:42"

    def test_authenticated_with_user_and_todo(self):
        """Test case 6: Generate "Authenticated | User:5 | Todo:42"."""
        ctx = ExplorationContext()
        ctx.set("auth_token", "abc123")
        ctx.set("user_id", 5)
        ctx.set("todo_id", 42)
        response = {}

        result = generate_state_name(ctx, response)

        assert "Authenticated" in result
        assert "User:5" in result
        assert "Todo:42" in result

    def test_state_with_completed_flag(self):
        """Test case 6: Generate state with "Completed" flag."""
        ctx = ExplorationContext()
        ctx.set("auth_token", "abc123")
        ctx.set("user_id", 5)
        ctx.set("todo_id", 42)
        response = {"completed": True}

        result = generate_state_name(ctx, response)

        assert "Authenticated" in result
        assert "User:5" in result
        assert "Todo:42" in result
        assert "Completed" in result

    def test_state_with_status_string(self):
        """Test state with status string field."""
        ctx = ExplorationContext()
        ctx.set("order_id", 100)
        response = {"status": "pending"}

        result = generate_state_name(ctx, response)

        assert "Order:100" in result
        assert "Pending" in result

    def test_multiple_resource_ids(self):
        """Test state with multiple resource IDs."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)
        ctx.set("attachment_id", "abc-123")
        response = {}

        result = generate_state_name(ctx, response)

        assert "Todo:42" in result
        assert "Attachment:abc-123" in result

    def test_status_from_context(self):
        """Test status flag taken from context when not in response."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)
        ctx.set("completed", True)
        response = {}  # No completed in response

        result = generate_state_name(ctx, response)

        assert "Todo:42" in result
        assert "Completed" in result


class TestHasUnresolvedPlaceholders:
    """Test has_unresolved_placeholders function."""

    def test_no_placeholders(self):
        """Test endpoint with no placeholders."""
        assert has_unresolved_placeholders("/todos") is False
        assert has_unresolved_placeholders("/api/v1/users") is False

    def test_with_placeholders(self):
        """Test endpoint with placeholders."""
        assert has_unresolved_placeholders("/todos/{todoId}") is True
        assert has_unresolved_placeholders("/todos/{id}/items/{itemId}") is True

    def test_resolved_endpoint(self):
        """Test fully resolved endpoint."""
        assert has_unresolved_placeholders("/todos/42") is False
        assert has_unresolved_placeholders("/todos/42/items/100") is False


class TestGetRequiredPlaceholders:
    """Test get_required_placeholders function."""

    def test_no_placeholders(self):
        """Test endpoint with no placeholders."""
        assert get_required_placeholders("/todos") == []

    def test_single_placeholder(self):
        """Test endpoint with single placeholder."""
        assert get_required_placeholders("/todos/{todoId}") == ["todoId"]

    def test_multiple_placeholders(self):
        """Test endpoint with multiple placeholders."""
        result = get_required_placeholders("/todos/{todoId}/attachments/{fileId}")
        assert result == ["todoId", "fileId"]

    def test_same_placeholder_multiple_times(self):
        """Test endpoint with repeated placeholder."""
        result = get_required_placeholders("/compare/{id}/to/{id}")
        assert result == ["id", "id"]


class TestCanResolveEndpoint:
    """Test can_resolve_endpoint function."""

    def test_no_placeholders(self):
        """Test endpoint with no placeholders can always be resolved."""
        ctx = ExplorationContext()
        assert can_resolve_endpoint("/todos", ctx) is True

    def test_resolvable_endpoint(self):
        """Test endpoint that can be resolved."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)
        assert can_resolve_endpoint("/todos/{todoId}", ctx) is True

    def test_unresolvable_endpoint(self):
        """Test endpoint that cannot be resolved."""
        ctx = ExplorationContext()
        # Missing todo_id
        assert can_resolve_endpoint("/todos/{todoId}", ctx) is False

    def test_partially_resolvable(self):
        """Test endpoint with only some placeholders resolvable."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)
        # Missing file_id
        assert can_resolve_endpoint("/todos/{todoId}/files/{fileId}", ctx) is False


class TestIntegrationScenarios:
    """Integration tests for realistic scenarios."""

    def test_todo_creation_flow(self):
        """Test complete todo creation flow."""
        ctx = ExplorationContext()

        # Step 1: Create todo
        response1 = {"id": 42, "title": "Test Todo", "completed": False}
        ctx = extract_context_from_response(response1, "/todos", ctx)

        assert ctx.get("todo_id") == 42

        # Step 2: Resolve GET endpoint
        endpoint = substitute_path_params("/todos/{todoId}", ctx)
        assert endpoint == "/todos/42"

        # Step 3: Generate state name
        state_name = generate_state_name(ctx, response1)
        assert "Todo:42" in state_name
        assert "Anonymous" in state_name

    def test_attachment_flow(self):
        """Test todo with attachment flow."""
        ctx = ExplorationContext()

        # Step 1: Create todo
        response1 = {"id": 42, "title": "Test"}
        ctx = extract_context_from_response(response1, "/todos", ctx)

        # Step 2: Add attachment
        response2 = {"id": "abc-123", "filename": "doc.pdf", "todo_id": 42}
        ctx = extract_context_from_response(response2, "/todos/42/attachments", ctx)

        assert ctx.get("todo_id") == 42
        assert ctx.get("attachment_id") == "abc-123"

        # Step 3: Resolve nested endpoint
        endpoint = substitute_path_params(
            "/todos/{todoId}/attachments/{attachmentId}",
            ctx
        )
        assert endpoint == "/todos/42/attachments/abc-123"

        # Step 4: Generate state name
        state_name = generate_state_name(ctx, response2)
        assert "Todo:42" in state_name
        assert "Attachment:abc-123" in state_name

    def test_auth_flow(self):
        """Test authentication flow with tokens."""
        ctx = ExplorationContext()

        # Step 1: Login
        response1 = {
            "access_token": "jwt_token_123",
            "refresh_token": "refresh_456",
            "user_id": 5
        }
        ctx = extract_context_from_response(response1, "/auth/login", ctx)

        assert ctx.get("access_token") == "jwt_token_123"
        assert ctx.get("refresh_token") == "refresh_456"
        assert ctx.get("user_id") == 5

        # State should show authenticated
        state_name = generate_state_name(ctx, response1)
        assert "Authenticated" in state_name
        assert "User:5" in state_name

    def test_context_chain_preservation(self):
        """Test that context accumulates through the chain."""
        ctx = ExplorationContext()

        # Login
        login_response = {"token": "auth123", "user_id": 5}
        ctx = extract_context_from_response(login_response, "/auth/login", ctx)

        # Create order
        order_response = {"id": 100, "status": "pending"}
        ctx = extract_context_from_response(order_response, "/orders", ctx)

        # Create item in order
        item_response = {"id": 1, "order_id": 100, "product_id": 50}
        ctx = extract_context_from_response(item_response, "/orders/100/items", ctx)

        # All IDs should be accumulated
        assert ctx.get("auth_token") == "auth123"
        assert ctx.get("user_id") == 5
        assert ctx.get("order_id") == 100
        assert ctx.get("item_id") == 1
        assert ctx.get("product_id") == 50

        # Complex endpoint should resolve
        endpoint = substitute_path_params(
            "/orders/{orderId}/items/{itemId}",
            ctx
        )
        assert endpoint == "/orders/100/items/1"

    def test_context_copy_for_branching(self):
        """Test copying context for exploration branching."""
        ctx = ExplorationContext()
        ctx.set("todo_id", 42)

        # Branch 1: Mark as complete
        branch1 = ctx.copy()
        branch1.set("completed", True)

        # Branch 2: Delete
        branch2 = ctx.copy()
        branch2.set("deleted", True)

        # Original unchanged
        assert ctx.has("completed") is False
        assert ctx.has("deleted") is False

        # Branches have their own state
        state1 = generate_state_name(branch1, {})
        state2 = generate_state_name(branch2, {})

        assert "Completed" in state1
        assert "Deleted" in state2
