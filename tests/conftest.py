"""Pytest fixtures for VenomQA tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from venomqa.client import Client, RequestRecord
from venomqa.core.context import ExecutionContext
from venomqa.core.models import (
    Branch,
    Checkpoint,
    Issue,
    Journey,
    JourneyResult,
    Path,
    Severity,
    Step,
    StepResult,
)
from venomqa.state.base import BaseStateManager, StateManager


class MockStateManager:
    """Mock state manager for testing."""

    def __init__(self) -> None:
        self._connected = False
        self._checkpoints: dict[str, Any] = {}
        self._checkpoint_order: list[str] = []

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def checkpoint(self, name: str) -> None:
        self._checkpoints[name] = {"created": True}
        self._checkpoint_order.append(name)

    def rollback(self, name: str) -> None:
        if name not in self._checkpoints:
            raise ValueError(f"Checkpoint '{name}' not found")

    def release(self, name: str) -> None:
        self._checkpoints.pop(name, None)

    def reset(self) -> None:
        self._checkpoints.clear()
        self._checkpoint_order.clear()

    def is_connected(self) -> bool:
        return self._connected


class MockHTTPResponse:
    """Mock HTTP response for testing."""

    def __init__(
        self,
        status_code: int = 200,
        json_data: Any = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data or {}
        self._text = text
        self.headers = headers or {}
        self.is_error = status_code >= 400

    def json(self) -> Any:
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data

    @property
    def text(self) -> str:
        return self._text


class MockClient:
    """Mock HTTP client for testing."""

    def __init__(self, base_url: str = "http://localhost:8080") -> None:
        self.base_url = base_url
        self.history: list[RequestRecord] = []
        self._responses: list[MockHTTPResponse] = []
        self._response_index = 0
        self._auth_token: str | None = None
        self._connected = False

    def set_responses(self, responses: list[MockHTTPResponse]) -> None:
        self._responses = responses
        self._response_index = 0

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def set_auth_token(self, token: str, scheme: str = "Bearer") -> None:
        self._auth_token = f"{scheme} {token}"

    def clear_auth(self) -> None:
        self._auth_token = None

    def request(self, method: str, path: str, **kwargs: Any) -> MockHTTPResponse:
        from datetime import datetime
        from time import perf_counter

        if self._responses and self._response_index < len(self._responses):
            response = self._responses[self._response_index]
            self._response_index += 1
        else:
            response = MockHTTPResponse()

        record = RequestRecord(
            method=method,
            url=f"{self.base_url}{path}",
            request_body=kwargs.get("json") or kwargs.get("data"),
            response_status=response.status_code,
            response_body=response._json_data,
            headers=kwargs.get("headers", {}),
            duration_ms=1.0,
            timestamp=datetime.now(),
        )
        self.history.append(record)

        return response

    def get(self, path: str, **kwargs: Any) -> MockHTTPResponse:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> MockHTTPResponse:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> MockHTTPResponse:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> MockHTTPResponse:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> MockHTTPResponse:
        return self.request("DELETE", path, **kwargs)

    def get_history(self) -> list[RequestRecord]:
        return self.history.copy()

    def clear_history(self) -> None:
        self.history.clear()

    def last_request(self) -> RequestRecord | None:
        return self.history[-1] if self.history else None


@pytest.fixture
def mock_client() -> MockClient:
    """Create a mock HTTP client."""
    return MockClient()


@pytest.fixture
def mock_state_manager() -> MockStateManager:
    """Create a mock state manager."""
    return MockStateManager()


@pytest.fixture
def context() -> ExecutionContext:
    """Create a fresh execution context."""
    return ExecutionContext()


@pytest.fixture
def sample_step() -> Step:
    """Create a sample step."""

    def action(client: MockClient, ctx: ExecutionContext) -> MockHTTPResponse:
        return client.get("/users/1")

    return Step(name="get_user", action=action, description="Fetch user by ID")


@pytest.fixture
def sample_checkpoint() -> Checkpoint:
    """Create a sample checkpoint."""
    return Checkpoint(name="after_user_create")


@pytest.fixture
def sample_path(sample_step: Step) -> Path:
    """Create a sample path."""
    return Path(
        name="happy_path",
        steps=[sample_step],
        description="Happy path execution",
    )


@pytest.fixture
def sample_branch(sample_checkpoint: Checkpoint, sample_path: Path) -> Branch:
    """Create a sample branch."""

    def delete_action(client: MockClient, ctx: ExecutionContext) -> MockHTTPResponse:
        return client.delete("/users/1")

    delete_step = Step(name="delete_user", action=delete_action)

    error_path = Path(
        name="error_path",
        steps=[delete_step],
        description="Error handling path",
    )

    return Branch(
        checkpoint_name=sample_checkpoint.name,
        paths=[sample_path, error_path],
    )


@pytest.fixture
def sample_journey(
    sample_step: Step, sample_checkpoint: Checkpoint, sample_branch: Branch
) -> Journey:
    """Create a sample journey for testing."""

    def create_action(client: MockClient, ctx: ExecutionContext) -> MockHTTPResponse:
        response = client.post("/users", json={"name": "Test User"})
        ctx.set("user_id", 1)
        return response

    create_step = Step(name="create_user", action=create_action, description="Create a new user")

    return Journey(
        name="user_lifecycle",
        steps=[create_step, sample_checkpoint, sample_branch],
        description="Complete user lifecycle journey",
        tags=["users", "integration"],
    )


@pytest.fixture
def sample_journey_simple(sample_step: Step) -> Journey:
    """Create a simple journey without branching."""

    def create_action(client: MockClient, ctx: ExecutionContext) -> MockHTTPResponse:
        response = client.post("/users", json={"name": "Test"})
        ctx["created"] = True
        return response

    create_step = Step(name="create_user", action=create_action)

    return Journey(
        name="simple_journey",
        steps=[create_step, sample_step],
        description="Simple journey without branches",
    )


@pytest.fixture
def sample_issue() -> Issue:
    """Create a sample issue."""
    return Issue(
        journey="test_journey",
        path="main",
        step="get_user",
        error="HTTP 404",
        severity=Severity.HIGH,
        request={"method": "GET", "url": "/users/999"},
        response={"status_code": 404, "body": {"error": "Not found"}},
        logs=["Request failed"],
    )
