"""
Tests for the VenomQA State Explorer Detector module.

This test module verifies that the StateDetector can properly:
1. Detect application state from HTTP responses
2. Create unique fingerprints for state identification
3. Detect authentication state (tokens, user info, roles)
4. Detect entity states (IDs, statuses)
5. Extract HATEOAS links for available actions
"""

import pytest
from typing import Any, Dict, List, Optional

from venomqa.explorer.detector import (
    StateDetector,
    AuthState,
    EntityState,
    AUTH_TOKEN_FIELDS,
    USER_FIELDS,
    ENTITY_ID_FIELDS,
    STATUS_FIELDS,
)
from venomqa.explorer.models import Action, State


class TestStateDetector:
    """Test StateDetector basic functionality."""

    def test_init_defaults(self):
        """Test that StateDetector initializes with proper defaults."""
        detector = StateDetector()

        assert detector.state_extractors == []
        assert detector.action_extractors == []
        assert detector.known_states == {}
        # Default state key fields should be set
        assert "status" in detector.state_key_fields
        assert "state" in detector.state_key_fields
        assert "phase" in detector.state_key_fields

    def test_add_state_key_field(self):
        """Test adding state key fields."""
        detector = StateDetector()
        detector.add_state_key_field("order_status")

        assert "order_status" in detector.state_key_fields

        # Adding same field again should not duplicate
        detector.add_state_key_field("order_status")
        assert detector.state_key_fields.count("order_status") == 1

    def test_set_state_key_fields(self):
        """Test setting state key fields."""
        detector = StateDetector()
        detector.set_state_key_fields(["custom_field", "another_field"])

        assert detector.state_key_fields == ["custom_field", "another_field"]

    def test_clear_cache(self):
        """Test clearing the state cache."""
        detector = StateDetector()

        # Detect a state to populate cache
        response = {"status": "active", "id": 123}
        detector.detect_state(response)

        assert len(detector.known_states) > 0

        detector.clear_cache()

        assert len(detector.known_states) == 0
        assert len(detector._state_hashes) == 0


class TestDetectState:
    """Test the detect_state method."""

    def test_detect_state_basic(self):
        """Test basic state detection from a response."""
        detector = StateDetector()

        response = {
            "status": "pending",
            "id": 42,
            "name": "Test Order",
        }

        state = detector.detect_state(response, endpoint="/api/orders/42")

        assert state is not None
        assert isinstance(state, State)
        assert state.id is not None
        assert state.name is not None
        # Status should be in properties
        assert state.properties.get("status") == "pending"

    def test_detect_state_with_endpoint_context(self):
        """Test state detection with endpoint context."""
        detector = StateDetector()

        response = {"data": "test"}
        state = detector.detect_state(
            response,
            endpoint="/api/users/123",
            method="GET"
        )

        assert state.metadata.get("endpoint") == "/api/users/123"
        assert state.metadata.get("method") == "GET"

    def test_detect_state_caching(self):
        """Test that identical responses return cached states."""
        detector = StateDetector()

        response = {"status": "active", "id": 1}

        state1 = detector.detect_state(response)
        state2 = detector.detect_state(response)

        # Should return the same state object from cache
        assert state1.id == state2.id
        assert len(detector.known_states) == 1

    def test_detect_state_different_statuses(self):
        """Test that different statuses create different states."""
        detector = StateDetector()

        response1 = {"status": "pending", "id": 1}
        response2 = {"status": "completed", "id": 1}

        state1 = detector.detect_state(response1)
        state2 = detector.detect_state(response2)

        # Different statuses should create different states
        assert state1.id != state2.id

    def test_detect_state_with_custom_extractor(self):
        """Test state detection with custom extractor."""
        detector = StateDetector()

        def custom_extractor(response: Dict[str, Any]) -> Optional[State]:
            if "custom_state" in response:
                return State(
                    id="custom_state_id",
                    name="Custom State",
                    properties={"custom": True},
                )
            return None

        detector.add_state_extractor(custom_extractor)

        response = {"custom_state": True, "data": "test"}
        state = detector.detect_state(response)

        assert state.id == "custom_state_id"
        assert state.name == "Custom State"
        assert state.properties.get("custom") is True

    def test_detect_state_infers_name_from_status(self):
        """Test that state name is inferred from status field."""
        detector = StateDetector()

        response = {"status": "order_processing"}
        state = detector.detect_state(response)

        # Should convert underscores to spaces and title case
        assert state.name == "Order Processing"

    def test_detect_state_infers_name_from_endpoint(self):
        """Test that state name uses endpoint when no status."""
        detector = StateDetector()

        response = {"data": "test"}
        state = detector.detect_state(response, endpoint="/api/products")

        assert "products" in state.name.lower() or "api_products" in state.name.lower()


class TestDetectAuthState:
    """Test authentication state detection."""

    def test_detect_auth_with_access_token(self):
        """Test detection of access token in response."""
        detector = StateDetector()

        response = {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        auth_state = detector.detect_auth_state(response)

        assert auth_state.is_authenticated is True
        assert auth_state.has_token is True
        assert auth_state.token_type == "access_token"

    def test_detect_auth_with_jwt(self):
        """Test detection of JWT in response."""
        detector = StateDetector()

        response = {
            "jwt": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        }

        auth_state = detector.detect_auth_state(response)

        assert auth_state.is_authenticated is True
        assert auth_state.has_token is True
        assert auth_state.token_type == "jwt"

    def test_detect_auth_with_refresh_token(self):
        """Test detection of refresh token in response."""
        detector = StateDetector()

        response = {
            "refresh_token": "refresh_eyJhbGciOiJIUzI1NiJ9...",
        }

        auth_state = detector.detect_auth_state(response)

        assert auth_state.has_token is True
        assert auth_state.token_type == "refresh_token"

    def test_detect_auth_with_user_info(self):
        """Test detection of user info in response."""
        detector = StateDetector()

        response = {
            "user": {
                "id": 123,
                "email": "test@example.com",
                "name": "Test User",
            }
        }

        auth_state = detector.detect_auth_state(response)

        assert auth_state.is_authenticated is True
        assert "id" in auth_state.user_info
        assert "email" in auth_state.user_info
        assert auth_state.user_info["email"] == "test@example.com"

    def test_detect_auth_with_roles(self):
        """Test detection of roles in response."""
        detector = StateDetector()

        response = {
            "token": "abc123",
            "roles": ["admin", "user"],
        }

        auth_state = detector.detect_auth_state(response)

        assert auth_state.roles == ["admin", "user"]

    def test_detect_auth_with_user_roles(self):
        """Test detection of roles nested in user object."""
        detector = StateDetector()

        response = {
            "user": {
                "id": 1,
                "roles": ["editor", "viewer"],
                "permissions": ["read", "write"],
            }
        }

        auth_state = detector.detect_auth_state(response)

        assert auth_state.roles == ["editor", "viewer"]
        assert auth_state.permissions == ["read", "write"]

    def test_detect_auth_no_auth_data(self):
        """Test that non-auth responses are not authenticated."""
        detector = StateDetector()

        response = {
            "products": [{"id": 1, "name": "Widget"}],
            "total": 1,
        }

        auth_state = detector.detect_auth_state(response)

        assert auth_state.is_authenticated is False
        assert auth_state.has_token is False
        assert auth_state.user_info == {}

    def test_detect_auth_nested_in_data(self):
        """Test detection of token nested in data field."""
        detector = StateDetector()

        response = {
            "data": {
                "token": "nested_token_value",
                "user_id": 42,
            }
        }

        auth_state = detector.detect_auth_state(response)

        assert auth_state.has_token is True

    def test_auth_state_to_dict(self):
        """Test AuthState serialization to dict."""
        auth_state = AuthState(
            is_authenticated=True,
            has_token=True,
            token_type="access_token",
            user_info={"id": 1, "email": "test@example.com"},
            roles=["admin"],
            permissions=["read", "write"],
        )

        result = auth_state.to_dict()

        assert result["is_authenticated"] is True
        assert result["has_token"] is True
        assert result["token_type"] == "access_token"
        assert result["user_info"]["email"] == "test@example.com"
        assert result["roles"] == ["admin"]


class TestDetectEntityState:
    """Test entity state detection."""

    def test_detect_entity_with_id(self):
        """Test detection of entity ID in response."""
        detector = StateDetector()

        response = {
            "id": 123,
            "name": "Test Entity",
            "status": "active",
        }

        entity_state = detector.detect_entity_state(response, endpoint="/api/orders/123")

        assert entity_state.entity_id == "123"
        assert entity_state.status == "active"

    def test_detect_entity_type_from_endpoint(self):
        """Test inferring entity type from endpoint."""
        detector = StateDetector()

        response = {"id": 1}

        # Test with plural endpoint
        entity_state = detector.detect_entity_state(response, endpoint="/api/v1/users/123")
        assert entity_state.entity_type == "user"

        # Test with another endpoint
        response2 = {"id": 2}
        entity_state2 = detector.detect_entity_state(response2, endpoint="/api/products/456")
        assert entity_state2.entity_type == "product"

    def test_detect_entity_uuid(self):
        """Test detection of UUID entity ID."""
        detector = StateDetector()

        response = {
            "uuid": "550e8400-e29b-41d4-a716-446655440000",
            "status": "pending",
        }

        entity_state = detector.detect_entity_state(response)

        assert entity_state.entity_id == "550e8400-e29b-41d4-a716-446655440000"

    def test_detect_entity_nested_data(self):
        """Test entity detection with nested data."""
        detector = StateDetector()

        response = {
            "data": {
                "id": 42,
                "status": "processing",
            }
        }

        entity_state = detector.detect_entity_state(response)

        assert entity_state.entity_id == "42"
        assert entity_state.status == "processing"

    def test_detect_entity_extracts_properties(self):
        """Test that entity detection extracts additional properties."""
        detector = StateDetector()

        response = {
            "id": 1,
            "status": "active",
            "priority": "high",
            "count": 5,
            "items": [1, 2, 3],
        }

        entity_state = detector.detect_entity_state(response)

        # Simple properties should be extracted
        assert entity_state.properties.get("priority") == "high"
        assert entity_state.properties.get("count") == 5
        # Lists should have count extracted
        assert entity_state.properties.get("items_count") == 3

    def test_entity_state_to_dict(self):
        """Test EntityState serialization to dict."""
        entity_state = EntityState(
            entity_type="order",
            entity_id="123",
            status="pending",
            properties={"total": 99.99},
        )

        result = entity_state.to_dict()

        assert result["entity_type"] == "order"
        assert result["entity_id"] == "123"
        assert result["status"] == "pending"
        assert result["properties"]["total"] == 99.99


class TestFingerprint:
    """Test the fingerprint method."""

    def test_fingerprint_creates_hash(self):
        """Test that fingerprint creates a hash string."""
        detector = StateDetector()

        response = {"status": "active", "id": 1}

        fingerprint = detector.fingerprint(response)

        assert isinstance(fingerprint, str)
        assert len(fingerprint) == 16  # Should be a 16-char hex string

    def test_fingerprint_same_response_same_hash(self):
        """Test that identical responses produce same fingerprint."""
        detector = StateDetector()

        response1 = {"status": "active", "id": 1}
        response2 = {"status": "active", "id": 1}

        fp1 = detector.fingerprint(response1)
        fp2 = detector.fingerprint(response2)

        assert fp1 == fp2

    def test_fingerprint_different_status_different_hash(self):
        """Test that different statuses produce different fingerprints."""
        detector = StateDetector()

        response1 = {"status": "active", "id": 1}
        response2 = {"status": "inactive", "id": 1}

        fp1 = detector.fingerprint(response1)
        fp2 = detector.fingerprint(response2)

        assert fp1 != fp2

    def test_fingerprint_includes_auth_presence(self):
        """Test that fingerprint includes auth token presence."""
        detector = StateDetector()

        response1 = {"status": "active"}
        response2 = {"status": "active", "token": "abc123"}

        fp1 = detector.fingerprint(response1)
        fp2 = detector.fingerprint(response2)

        # Auth presence changes fingerprint
        assert fp1 != fp2

    def test_fingerprint_includes_structure(self):
        """Test that fingerprint includes response structure."""
        detector = StateDetector()

        response1 = {"status": "active", "items": [1, 2, 3]}
        response2 = {"status": "active", "data": {"nested": True}}

        fp1 = detector.fingerprint(response1)
        fp2 = detector.fingerprint(response2)

        # Different structures should produce different fingerprints
        assert fp1 != fp2

    def test_fingerprint_uses_state_key_fields(self):
        """Test that fingerprint uses configured state key fields."""
        detector = StateDetector()
        detector.set_state_key_fields(["order_status"])

        response1 = {"order_status": "pending", "id": 1}
        response2 = {"order_status": "pending", "id": 2}

        fp1 = detector.fingerprint(response1)
        fp2 = detector.fingerprint(response2)

        # Different IDs but same order_status - fingerprint should differ
        # because ID is included in fingerprint
        assert fp1 != fp2


class TestHATEOASExtraction:
    """Test HATEOAS link extraction for available actions."""

    def test_extract_hal_links(self):
        """Test extraction of HAL-style _links."""
        detector = StateDetector()

        response = {
            "id": 1,
            "_links": {
                "self": {"href": "/api/orders/1"},
                "cancel": {"href": "/api/orders/1/cancel", "method": "POST"},
                "items": {"href": "/api/orders/1/items"},
            }
        }

        actions = detector.detect_available_actions(response)

        # Should extract cancel and items (not self)
        assert len(actions) >= 2

        endpoints = [a.endpoint for a in actions]
        assert "/api/orders/1/cancel" in endpoints
        assert "/api/orders/1/items" in endpoints

        # Cancel should be POST
        cancel_action = next(a for a in actions if a.endpoint == "/api/orders/1/cancel")
        assert cancel_action.method == "POST"

    def test_extract_links_array(self):
        """Test extraction of links array format."""
        detector = StateDetector()

        response = {
            "id": 1,
            "links": [
                {"rel": "self", "href": "/api/users/1"},
                {"rel": "orders", "href": "/api/users/1/orders", "method": "GET"},
                {"rel": "delete", "href": "/api/users/1", "method": "DELETE"},
            ]
        }

        actions = detector.detect_available_actions(response)

        # Should extract orders and delete (not self)
        assert len(actions) >= 2

        endpoints = [a.endpoint for a in actions]
        assert "/api/users/1/orders" in endpoints

    def test_extract_jsonapi_links(self):
        """Test extraction of JSON:API style links."""
        detector = StateDetector()

        response = {
            "data": {"id": 1, "type": "order"},
            "links": {
                "self": "/api/orders/1",
                "related": "/api/orders/1/items",
                "create": "/api/orders",
                "delete": "/api/orders/1",
            }
        }

        actions = detector.detect_available_actions(response)

        # Check that actions are extracted with inferred methods
        create_actions = [a for a in actions if a.description == "create"]
        assert len(create_actions) == 1
        assert create_actions[0].method == "POST"

        delete_actions = [a for a in actions if a.description == "delete"]
        assert len(delete_actions) == 1
        assert delete_actions[0].method == "DELETE"

    def test_extract_actions_array(self):
        """Test extraction of actions array format."""
        detector = StateDetector()

        response = {
            "id": 1,
            "actions": [
                {"name": "approve", "href": "/api/orders/1/approve", "method": "POST"},
                {"name": "reject", "url": "/api/orders/1/reject", "method": "POST"},
                {"title": "view", "endpoint": "/api/orders/1", "type": "GET"},
            ]
        }

        actions = detector.detect_available_actions(response)

        assert len(actions) == 3

        endpoints = [a.endpoint for a in actions]
        assert "/api/orders/1/approve" in endpoints
        assert "/api/orders/1/reject" in endpoints
        assert "/api/orders/1" in endpoints

    def test_extract_operations_array(self):
        """Test extraction of operations array format."""
        detector = StateDetector()

        response = {
            "id": 1,
            "operations": [
                {"name": "start", "href": "/api/jobs/1/start", "method": "POST"},
                {"name": "stop", "href": "/api/jobs/1/stop", "method": "POST"},
            ]
        }

        actions = detector.detect_available_actions(response)

        assert len(actions) == 2
        methods = [a.method for a in actions]
        assert all(m == "POST" for m in methods)

    def test_custom_action_extractor(self):
        """Test custom action extractor."""
        detector = StateDetector()

        def custom_extractor(response: Dict[str, Any]) -> List[Action]:
            if "custom_actions" in response:
                return [
                    Action(
                        method="POST",
                        endpoint="/custom/action",
                        description="Custom Action",
                    )
                ]
            return []

        detector.add_action_extractor(custom_extractor)

        response = {"custom_actions": True}
        actions = detector.detect_available_actions(response)

        assert len(actions) == 1
        assert actions[0].endpoint == "/custom/action"

    def test_action_deduplication(self):
        """Test that duplicate actions are removed."""
        detector = StateDetector()

        response = {
            "_links": {
                "items": {"href": "/api/items"},
            },
            "links": [
                {"rel": "items", "href": "/api/items"},  # Duplicate
            ]
        }

        actions = detector.detect_available_actions(response)

        # Should only have one action for /api/items
        items_actions = [a for a in actions if a.endpoint == "/api/items"]
        assert len(items_actions) == 1


class TestIsSameState:
    """Test state comparison."""

    def test_same_state_same_id(self):
        """Test that states with same ID are considered same."""
        detector = StateDetector()

        state1 = State(id="s1", name="State 1", properties={"status": "active"})
        state2 = State(id="s1", name="State 1 Copy", properties={"status": "active"})

        assert detector.is_same_state(state1, state2) is True

    def test_different_id_same_properties(self):
        """Test comparison with different IDs but same key properties."""
        detector = StateDetector()

        state1 = State(id="s1", name="State 1", properties={"status": "active"})
        state2 = State(id="s2", name="State 2", properties={"status": "active"})

        # With default key fields, same status means same state
        assert detector.is_same_state(state1, state2) is True

    def test_different_id_different_properties(self):
        """Test that different key properties mean different states."""
        detector = StateDetector()

        state1 = State(id="s1", name="State 1", properties={"status": "active"})
        state2 = State(id="s2", name="State 2", properties={"status": "inactive"})

        assert detector.is_same_state(state1, state2) is False

    def test_no_key_fields_different_id(self):
        """Test that without key fields, different IDs mean different states."""
        detector = StateDetector()
        detector.set_state_key_fields([])  # Clear key fields

        state1 = State(id="s1", name="State 1", properties={"status": "active"})
        state2 = State(id="s2", name="State 2", properties={"status": "active"})

        assert detector.is_same_state(state1, state2) is False


class TestInferEntityTypeFromEndpoint:
    """Test entity type inference from endpoints."""

    def test_simple_plural_endpoint(self):
        """Test inferring from simple plural endpoint."""
        detector = StateDetector()

        entity_type = detector._infer_entity_type_from_endpoint("/api/users")
        assert entity_type == "user"

        entity_type = detector._infer_entity_type_from_endpoint("/api/products")
        assert entity_type == "product"

    def test_endpoint_with_id(self):
        """Test inferring from endpoint with numeric ID."""
        detector = StateDetector()

        entity_type = detector._infer_entity_type_from_endpoint("/api/orders/123")
        assert entity_type == "order"

    def test_endpoint_with_uuid(self):
        """Test inferring from endpoint with UUID."""
        detector = StateDetector()

        entity_type = detector._infer_entity_type_from_endpoint(
            "/api/items/550e8400-e29b-41d4-a716-446655440000"
        )
        assert entity_type == "item"

    def test_endpoint_with_version(self):
        """Test inferring from versioned endpoint."""
        detector = StateDetector()

        entity_type = detector._infer_entity_type_from_endpoint("/api/v1/customers")
        assert entity_type == "customer"

        entity_type = detector._infer_entity_type_from_endpoint("/api/v2/invoices/42")
        assert entity_type == "invoice"

    def test_nested_resource_endpoint(self):
        """Test inferring from nested resource endpoint."""
        detector = StateDetector()

        # Should get the first non-api/version segment
        entity_type = detector._infer_entity_type_from_endpoint("/api/v1/users/123/orders")
        assert entity_type == "user"

    def test_singular_endpoint(self):
        """Test endpoint that's already singular."""
        detector = StateDetector()

        entity_type = detector._infer_entity_type_from_endpoint("/api/user/profile")
        assert entity_type == "user"


class TestGetStructureSignature:
    """Test response structure signature generation."""

    def test_simple_dict_structure(self):
        """Test structure signature for simple dict."""
        detector = StateDetector()

        response = {"id": 1, "name": "Test", "active": True}
        sig = detector._get_structure_signature(response)

        assert "{" in sig
        assert "}" in sig

    def test_nested_structure(self):
        """Test structure signature for nested response."""
        detector = StateDetector()

        response = {
            "user": {"id": 1, "name": "Test"},
            "items": [{"id": 1}, {"id": 2}],
        }
        sig = detector._get_structure_signature(response)

        assert "{" in sig

    def test_empty_list_structure(self):
        """Test structure signature with empty list."""
        detector = StateDetector()

        # When response is the top-level empty list
        response_list: list = []
        sig = detector._get_structure_signature(response_list)  # type: ignore
        assert sig == "[]"

        # When response has a key with empty list, structure shows keys
        response_dict = {"items": []}
        sig_dict = detector._get_structure_signature(response_dict)
        assert "items" in sig_dict


class TestIntegration:
    """Integration tests combining multiple detector features."""

    def test_full_login_response_detection(self):
        """Test detecting state from a realistic login response."""
        detector = StateDetector()

        login_response = {
            "success": True,
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ",
            "refresh_token": "refresh_abc123",
            "expires_in": 3600,
            "user": {
                "id": 1,
                "email": "john@example.com",
                "name": "John Doe",
                "roles": ["user", "admin"],
            },
            "_links": {
                "self": {"href": "/api/auth/me"},
                "logout": {"href": "/api/auth/logout", "method": "POST"},
                "refresh": {"href": "/api/auth/refresh", "method": "POST"},
            }
        }

        state = detector.detect_state(login_response, endpoint="/api/auth/login", method="POST")

        # Should detect authenticated state
        assert "auth_state" in state.metadata
        auth_state = state.metadata["auth_state"]
        assert auth_state["is_authenticated"] is True
        assert auth_state["has_token"] is True
        assert "admin" in auth_state["roles"]

        # Should extract HATEOAS actions
        assert len(state.available_actions) >= 2
        action_endpoints = [a.endpoint for a in state.available_actions]
        assert "/api/auth/logout" in action_endpoints
        assert "/api/auth/refresh" in action_endpoints

    def test_full_entity_response_detection(self):
        """Test detecting state from a realistic entity response."""
        detector = StateDetector()

        order_response = {
            "id": 12345,
            "status": "processing",
            "total": 99.99,
            "items": [
                {"product_id": 1, "quantity": 2},
                {"product_id": 3, "quantity": 1},
            ],
            "customer": {
                "id": 42,
                "name": "Jane Smith",
            },
            "_links": {
                "self": {"href": "/api/orders/12345"},
                "cancel": {"href": "/api/orders/12345/cancel", "method": "POST"},
                "track": {"href": "/api/orders/12345/tracking"},
                "invoice": {"href": "/api/orders/12345/invoice"},
            }
        }

        state = detector.detect_state(order_response, endpoint="/api/orders/12345", method="GET")

        # State name should reflect status
        assert "processing" in state.name.lower()

        # Should detect entity state
        assert "entity_state" in state.metadata
        entity_state = state.metadata["entity_state"]
        assert entity_state["entity_id"] == "12345"
        assert entity_state["status"] == "processing"
        assert entity_state["entity_type"] == "order"

        # Should extract actions
        assert len(state.available_actions) >= 3
        action_endpoints = [a.endpoint for a in state.available_actions]
        assert "/api/orders/12345/cancel" in action_endpoints

    def test_list_response_detection(self):
        """Test detecting state from a list/collection response."""
        detector = StateDetector()

        list_response = {
            "data": [
                {"id": 1, "name": "Item 1"},
                {"id": 2, "name": "Item 2"},
            ],
            "meta": {
                "total": 100,
                "page": 1,
                "per_page": 10,
            },
            "links": {
                "self": "/api/items?page=1",
                "next": "/api/items?page=2",
                "last": "/api/items?page=10",
                "create": "/api/items",
            }
        }

        state = detector.detect_state(list_response, endpoint="/api/items")

        # Should extract pagination actions
        actions = state.available_actions
        endpoints = [a.endpoint for a in actions]

        assert "/api/items?page=2" in endpoints  # next
        assert "/api/items" in endpoints  # create

    def test_error_response_detection(self):
        """Test detecting state from an error response."""
        detector = StateDetector()

        error_response = {
            "error": True,
            "status": "error",
            "message": "Resource not found",
            "code": "NOT_FOUND",
            "_links": {
                "home": {"href": "/api"},
            }
        }

        state = detector.detect_state(error_response, endpoint="/api/missing/resource")

        # Should reflect error status
        assert "error" in state.name.lower()

        # Properties should include error info
        assert state.properties.get("error") is True
        assert state.properties.get("code") == "NOT_FOUND"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
