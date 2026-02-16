"""Integration tests for full journey execution."""

from __future__ import annotations

import pytest

from venomqa.http import Client
from venomqa.core.models import (
    Branch,
    Checkpoint,
    Journey,
    JourneyResult,
    Path,
    Severity,
    Step,
)
from venomqa.errors import JourneyValidationError
from venomqa.runner import JourneyRunner
from venomqa.state import PostgreSQLStateManager
from .conftest import MockClient, MockHTTPResponse, MockStateManager


class TestFullJourneyIntegration:
    """Integration tests for complete journey workflows."""

    def test_simple_crud_journey(self, mock_client: MockClient) -> None:
        def create_user(client, ctx):
            response = client.post("/users", json={"name": "John Doe", "email": "john@example.com"})
            if hasattr(response, "json"):
                data = response.json()
                ctx.set("user_id", data.get("id"))
            return response

        def get_user(client, ctx):
            user_id = ctx.get("user_id")
            return client.get(f"/users/{user_id}")

        def update_user(client, ctx):
            user_id = ctx.get("user_id")
            return client.put(f"/users/{user_id}", json={"name": "Jane Doe"})

        def delete_user(client, ctx):
            user_id = ctx.get("user_id")
            return client.delete(f"/users/{user_id}")

        journey = Journey(
            name="user_crud",
            steps=[
                Step(name="create_user", action=create_user, description="Create a new user"),
                Step(name="get_user", action=get_user, description="Get the created user"),
                Step(name="update_user", action=update_user, description="Update user name"),
                Step(name="delete_user", action=delete_user, description="Delete the user"),
            ],
            description="Full CRUD lifecycle for user",
            tags=["crud", "users", "integration"],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=201, json_data={"id": 1, "name": "John Doe"}),
                MockHTTPResponse(status_code=200, json_data={"id": 1, "name": "John Doe"}),
                MockHTTPResponse(status_code=200, json_data={"id": 1, "name": "Jane Doe"}),
                MockHTTPResponse(status_code=204, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True
        assert result.journey_name == "user_crud"
        assert result.total_steps == 4
        assert result.passed_steps == 4
        assert len(result.issues) == 0
        assert len(mock_client.history) == 4

    def test_authentication_flow_journey(self, mock_client: MockClient) -> None:
        def login(client, ctx):
            response = client.post(
                "/auth/login",
                json={"username": "testuser", "password": "password123"},
            )
            if hasattr(response, "json"):
                data = response.json()
                token = data.get("token")
                if token:
                    client.set_auth_token(token)
                    ctx.set("authenticated", True)
            return response

        def get_profile(client, ctx):
            return client.get("/auth/profile")

        def logout(client, ctx):
            client.clear_auth()
            response = client.post("/auth/logout")
            ctx.set("authenticated", False)
            return response

        journey = Journey(
            name="auth_flow",
            steps=[
                Step(name="login", action=login),
                Step(name="get_profile", action=get_profile),
                Step(name="logout", action=logout),
            ],
            tags=["auth", "integration"],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={"token": "jwt-token-123"}),
                MockHTTPResponse(status_code=200, json_data={"username": "testuser"}),
                MockHTTPResponse(status_code=200, json_data={"message": "Logged out"}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True

        login_request = mock_client.history[0]
        assert login_request.method == "POST"
        assert "/auth/login" in login_request.url

        profile_request = mock_client.history[1]
        assert profile_request.method == "GET"

    def test_error_handling_journey(self, mock_client: MockClient) -> None:
        def create_resource(client, ctx):
            return client.post("/resources", json={"name": "test"})

        def access_forbidden(client, ctx):
            return client.get("/admin/secret")

        def access_not_found(client, ctx):
            return client.get("/nonexistent")

        journey = Journey(
            name="error_handling",
            steps=[
                Step(name="create", action=create_resource),
                Step(name="forbidden", action=access_forbidden, expect_failure=True),
                Step(name="not_found", action=access_not_found, expect_failure=True),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=201, json_data={"id": 1}),
                MockHTTPResponse(status_code=403, json_data={"error": "Forbidden"}),
                MockHTTPResponse(status_code=404, json_data={"error": "Not found"}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True
        assert result.issues == []

    def test_branching_journey_with_checkout_flow(self, mock_client: MockClient) -> None:
        def create_order(client, ctx):
            response = client.post("/orders", json={"product_id": 1, "quantity": 2})
            if hasattr(response, "json"):
                ctx.set("order_id", response.json().get("id"))
            return response

        def payment_success(client, ctx):
            order_id = ctx.get("order_id")
            return client.post(f"/orders/{order_id}/pay", json={"method": "credit_card"})

        def payment_failure(client, ctx):
            order_id = ctx.get("order_id")
            return client.post(
                f"/orders/{order_id}/pay",
                json={"method": "invalid_method"},
            )

        def cancel_order(client, ctx):
            order_id = ctx.get("order_id")
            return client.post(f"/orders/{order_id}/cancel")

        def confirm_delivery(client, ctx):
            order_id = ctx.get("order_id")
            return client.post(f"/orders/{order_id}/deliver")

        journey = Journey(
            name="checkout_flow",
            steps=[
                Step(name="create_order", action=create_order),
                Checkpoint(name="after_order_create"),
                Branch(
                    checkpoint_name="after_order_create",
                    paths=[
                        Path(
                            name="successful_payment",
                            steps=[
                                Step(name="pay_success", action=payment_success),
                                Step(name="confirm_delivery", action=confirm_delivery),
                            ],
                        ),
                        Path(
                            name="failed_payment",
                            steps=[
                                Step(name="pay_fail", action=payment_failure, expect_failure=True),
                                Step(name="cancel", action=cancel_order),
                            ],
                        ),
                    ],
                ),
            ],
            description="E-commerce checkout flow with payment branching",
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=201, json_data={"id": "order-123"}),
                MockHTTPResponse(status_code=200, json_data={"status": "paid"}),
                MockHTTPResponse(status_code=200, json_data={"status": "delivered"}),
                MockHTTPResponse(status_code=400, json_data={"error": "Invalid payment"}),
                MockHTTPResponse(status_code=200, json_data={"status": "cancelled"}),
            ]
        )

        state_manager = MockStateManager()
        runner = JourneyRunner(client=mock_client, state_manager=state_manager)
        result = runner.run(journey)

        assert result.success is True
        assert len(result.branch_results) == 1
        assert result.total_paths == 2
        assert result.passed_paths == 2
        assert "after_order_create" in state_manager._checkpoints

    def test_parallel_paths_journey(self, mock_client: MockClient) -> None:
        def create_item(client, ctx):
            response = client.post("/items", json={"name": "test"})
            if hasattr(response, "json"):
                ctx.set("item_id", response.json().get("id"))
            return response

        def path_a_action(client, ctx):
            item_id = ctx.get("item_id")
            return client.post(f"/items/{item_id}/action-a")

        def path_b_action(client, ctx):
            item_id = ctx.get("item_id")
            return client.post(f"/items/{item_id}/action-b")

        def path_c_action(client, ctx):
            item_id = ctx.get("item_id")
            return client.post(f"/items/{item_id}/action-c")

        journey = Journey(
            name="parallel_test",
            steps=[
                Step(name="create", action=create_item),
                Checkpoint(name="after_create"),
                Branch(
                    checkpoint_name="after_create",
                    paths=[
                        Path(name="path_a", steps=[Step(name="action_a", action=path_a_action)]),
                        Path(name="path_b", steps=[Step(name="action_b", action=path_b_action)]),
                        Path(name="path_c", steps=[Step(name="action_c", action=path_c_action)]),
                    ],
                ),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=201, json_data={"id": "item-1"}),
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        state_manager = MockStateManager()
        runner = JourneyRunner(client=mock_client, parallel_paths=3, state_manager=state_manager)
        result = runner.run(journey)

        assert result.success is True
        assert result.total_paths == 3

    def test_complex_nested_context_journey(self, mock_client: MockClient) -> None:
        def setup_user(client, ctx):
            response = client.post("/users", json={"name": "Test User"})
            ctx.set("user_id", 1)
            ctx["user_name"] = "Test User"
            return response

        def create_order(client, ctx):
            user_id = ctx.get("user_id")
            response = client.post(f"/users/{user_id}/orders", json={"total": 100})
            ctx.store_step_result("create_order", response)
            ctx.set("order_id", 2)
            return response

        def add_items(client, ctx):
            order_id = ctx.get("order_id")
            response = client.post(f"/orders/{order_id}/items", json={"items": [{"id": 1}]})
            ctx.set("items_added", True)
            return response

        def verify_context(client, ctx):
            assert ctx.get("user_id") == 1
            assert ctx.get("order_id") == 2
            assert ctx.get("items_added") is True
            assert ctx.get_step_result("create_order") is not None
            return client.get("/verify")

        journey = Journey(
            name="context_propagation",
            steps=[
                Step(name="setup_user", action=setup_user),
                Step(name="create_order", action=create_order),
                Step(name="add_items", action=add_items),
                Step(name="verify_context", action=verify_context),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=201, json_data={"id": 1}),
                MockHTTPResponse(status_code=201, json_data={"id": 2}),
                MockHTTPResponse(status_code=200, json_data={"added": True}),
                MockHTTPResponse(status_code=200, json_data={"valid": True}),
            ]
        )

        runner = JourneyRunner(client=mock_client)
        result = runner.run(journey)

        assert result.success is True

    def test_journey_with_mixed_results(self, mock_client: MockClient) -> None:
        def step_success(client, ctx):
            return client.get("/success")

        def step_failure(client, ctx):
            return client.get("/failure")

        def step_success2(client, ctx):
            return client.get("/success2")

        journey = Journey(
            name="mixed_results",
            steps=[
                Step(name="success1", action=step_success),
                Step(name="failure", action=step_failure),
                Step(name="success2", action=step_success2),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=500, json_data={"error": "Server error"}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        runner = JourneyRunner(client=mock_client, fail_fast=False)
        result = runner.run(journey)

        assert result.success is False
        assert result.passed_steps == 2
        assert result.total_steps == 3
        assert len(result.issues) == 1

        issue = result.issues[0]
        assert issue.journey == "mixed_results"
        assert issue.step == "failure"
        assert issue.severity == Severity.HIGH


class TestJourneyResultProperties:
    """Tests for JourneyResult computed properties."""

    def test_result_properties(self, mock_client: MockClient) -> None:
        def action(client, ctx):
            return client.get("/test")

        journey = Journey(
            name="property_test",
            steps=[
                Step(name="step1", action=action),
                Checkpoint(name="cp1"),
                Branch(
                    checkpoint_name="cp1",
                    paths=[
                        Path(name="p1", steps=[Step(name="s1", action=action)]),
                        Path(name="p2", steps=[Step(name="s2", action=action)]),
                    ],
                ),
            ],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
                MockHTTPResponse(status_code=200, json_data={}),
            ]
        )

        state_manager = MockStateManager()
        runner = JourneyRunner(client=mock_client, state_manager=state_manager)
        result = runner.run(journey)

        assert result.total_steps == 1
        assert result.passed_steps == 1
        assert result.total_paths == 2
        assert result.passed_paths == 2


class TestJourneyValidation:
    """Tests for journey validation."""

    def test_invalid_checkpoint_reference(self) -> None:
        with pytest.raises(JourneyValidationError, match="undefined checkpoint"):
            Journey(
                name="invalid",
                steps=[
                    Branch(
                        checkpoint_name="nonexistent",
                        paths=[Path(name="p1", steps=[])],
                    )
                ],
            )

    def test_valid_checkpoint_reference(self) -> None:
        journey = Journey(
            name="valid",
            steps=[
                Checkpoint(name="cp1"),
                Branch(
                    checkpoint_name="cp1",
                    paths=[Path(name="p1", steps=[])],
                ),
            ],
        )

        assert journey.name == "valid"
        assert len(journey.steps) == 2


class TestCompleteE2EScenario:
    """End-to-end test simulating a realistic API testing scenario."""

    def test_user_management_e2e(self, mock_client: MockClient) -> None:
        def register_user(client, ctx):
            response = client.post(
                "/api/v1/users/register",
                json={
                    "email": "newuser@example.com",
                    "password": "SecurePass123!",
                    "name": "New User",
                },
            )
            if hasattr(response, "json") and response.status_code == 201:
                ctx.set("registered_email", "newuser@example.com")
            return response

        def login_user(client, ctx):
            email = ctx.get("registered_email")
            response = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": "SecurePass123!"},
            )
            if hasattr(response, "json") and response.status_code == 200:
                token = response.json().get("access_token")
                if token:
                    client.set_auth_token(token)
                    ctx.set("logged_in", True)
            return response

        def get_user_profile(client, ctx):
            return client.get("/api/v1/users/me")

        def update_profile(client, ctx):
            return client.patch(
                "/api/v1/users/me",
                json={"name": "Updated Name"},
            )

        def delete_account(client, ctx):
            response = client.delete("/api/v1/users/me")
            client.clear_auth()
            return response

        def verify_deleted(client, ctx):
            return client.get("/api/v1/users/me")

        journey = Journey(
            name="user_management_e2e",
            steps=[
                Step(name="register", action=register_user),
                Step(name="login", action=login_user),
                Step(name="get_profile", action=get_user_profile),
                Step(name="update_profile", action=update_profile),
                Step(name="delete_account", action=delete_account),
                Step(name="verify_deleted", action=verify_deleted, expect_failure=True),
            ],
            description="Complete user management flow from registration to deletion",
            tags=["e2e", "users", "auth", "crud"],
        )

        mock_client.set_responses(
            [
                MockHTTPResponse(
                    status_code=201,
                    json_data={"id": 1, "email": "newuser@example.com"},
                ),
                MockHTTPResponse(
                    status_code=200,
                    json_data={"access_token": "jwt-token-xyz", "user": {"id": 1}},
                ),
                MockHTTPResponse(
                    status_code=200,
                    json_data={"id": 1, "email": "newuser@example.com", "name": "New User"},
                ),
                MockHTTPResponse(
                    status_code=200,
                    json_data={"id": 1, "name": "Updated Name"},
                ),
                MockHTTPResponse(status_code=204, json_data={}),
                MockHTTPResponse(status_code=401, json_data={"error": "Unauthorized"}),
            ]
        )

        runner = JourneyRunner(client=mock_client, capture_logs=True)
        result = runner.run(journey)

        assert result.success is True
        assert result.journey_name == "user_management_e2e"
        assert result.total_steps == 6
        assert result.passed_steps == 6

        assert mock_client.history[0].method == "POST"
        assert "register" in mock_client.history[0].url

        assert mock_client.history[1].method == "POST"
        assert "login" in mock_client.history[1].url

        assert mock_client.history[2].method == "GET"
        assert "me" in mock_client.history[2].url

        assert mock_client.history[4].method == "DELETE"
