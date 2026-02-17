"""Protocol Adapter for language-agnostic API testing.

This adapter communicates with APIs that implement the VenomQA Control Protocol,
allowing VenomQA to test APIs written in any language (Node.js, Go, Java, etc.).

The target API must implement these endpoints:
    POST /venomqa/begin      - Start a session
    POST /venomqa/checkpoint - Create a savepoint
    POST /venomqa/rollback   - Rollback to a savepoint
    POST /venomqa/end        - End the session

See sdk/PROTOCOL.md for the full specification.

Usage:
    from venomqa.v1 import Agent, World
    from venomqa.v1.adapters.protocol import ProtocolAdapter

    # Connect to a Node.js/Go/Java API that implements the protocol
    adapter = ProtocolAdapter("http://localhost:3000")

    world = World(
        api=adapter,  # Uses same adapter for both API and control
        systems={"db": adapter},
    )

    agent = Agent(world=world, actions=[...], invariants=[...])
    result = agent.explore()
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class ProtocolResponse:
    """Response wrapper matching VenomQA's expected interface."""

    status_code: int
    headers: dict[str, str]
    content: bytes
    _json: Any = field(default=None, repr=False)

    def json(self) -> Any:
        """Parse response body as JSON."""
        if self._json is None:
            import json
            self._json = json.loads(self.content)
        return self._json

    @property
    def text(self) -> str:
        """Return response body as text."""
        return self.content.decode("utf-8")

    def expect_status(self, *expected: int) -> None:
        """Assert status code is one of the expected values."""
        if self.status_code not in expected:
            raise AssertionError(
                f"Expected status {expected}, got {self.status_code}: {self.text}"
            )

    def expect_json(self) -> Any:
        """Assert response is valid JSON and return it."""
        import json
        try:
            return self.json()
        except json.JSONDecodeError as e:
            raise AssertionError(f"Expected JSON response, got: {self.text}") from e

    def expect_json_field(self, field: str) -> Any:
        """Assert JSON response has a field and return the full JSON."""
        data = self.expect_json()
        if field not in data:
            raise AssertionError(f"Expected field '{field}' in response: {data}")
        return data

    def expect_json_list(self) -> list:
        """Assert response is a JSON array and return it."""
        data = self.expect_json()
        if not isinstance(data, list):
            raise AssertionError(f"Expected JSON array, got: {type(data).__name__}")
        return data


class ProtocolAdapter:
    """Adapter for APIs that implement the VenomQA Control Protocol.

    This adapter:
    1. Acts as an HTTP client for your API (get, post, put, delete)
    2. Manages VenomQA sessions via the control endpoints
    3. Implements the Rollbackable interface for World.systems

    The target API can be written in ANY language - Node.js, Go, Java, etc.
    It just needs to implement the VenomQA Control Protocol endpoints.

    Example:
        # Your API is running at http://localhost:3000
        # It implements /venomqa/begin, /venomqa/checkpoint, etc.

        adapter = ProtocolAdapter("http://localhost:3000")

        # Start a session
        adapter.begin_session()

        # Make API calls (adapter adds X-VenomQA-Session header)
        adapter.post("/users", json={"name": "Alice"})

        # Create checkpoint
        cp = adapter.checkpoint()

        # More API calls
        adapter.delete("/users/1")

        # Rollback to checkpoint (Alice is back!)
        adapter.rollback(cp)

        # End session (all changes discarded)
        adapter.end_session()
    """

    def __init__(
        self,
        base_url: str,
        control_prefix: str = "/venomqa",
        timeout: float = 30.0,
    ):
        """Initialize the protocol adapter.

        Args:
            base_url: Base URL of the API (e.g., "http://localhost:3000")
            control_prefix: URL prefix for control endpoints (default: "/venomqa")
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.control_prefix = control_prefix
        self.timeout = timeout

        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        self._session_id: str | None = None
        self._checkpoints: list[str] = []

    def _make_response(self, httpx_resp: httpx.Response) -> ProtocolResponse:
        """Convert httpx Response to ProtocolResponse."""
        return ProtocolResponse(
            status_code=httpx_resp.status_code,
            headers=dict(httpx_resp.headers),
            content=httpx_resp.content,
        )

    def _headers(self) -> dict[str, str]:
        """Get headers including VenomQA session if active."""
        headers = {}
        if self._session_id:
            headers["X-VenomQA-Session"] = self._session_id
            headers["X-VenomQA-Mode"] = "exploration"
        return headers

    # === HTTP Client Methods (for API calls) ===

    def get(self, path: str, **kwargs: Any) -> ProtocolResponse:
        """Send GET request to the API."""
        kwargs.setdefault("headers", {}).update(self._headers())
        resp = self._client.get(path, **kwargs)
        return self._make_response(resp)

    def post(self, path: str, **kwargs: Any) -> ProtocolResponse:
        """Send POST request to the API."""
        kwargs.setdefault("headers", {}).update(self._headers())
        resp = self._client.post(path, **kwargs)
        return self._make_response(resp)

    def put(self, path: str, **kwargs: Any) -> ProtocolResponse:
        """Send PUT request to the API."""
        kwargs.setdefault("headers", {}).update(self._headers())
        resp = self._client.put(path, **kwargs)
        return self._make_response(resp)

    def patch(self, path: str, **kwargs: Any) -> ProtocolResponse:
        """Send PATCH request to the API."""
        kwargs.setdefault("headers", {}).update(self._headers())
        resp = self._client.patch(path, **kwargs)
        return self._make_response(resp)

    def delete(self, path: str, **kwargs: Any) -> ProtocolResponse:
        """Send DELETE request to the API."""
        kwargs.setdefault("headers", {}).update(self._headers())
        resp = self._client.delete(path, **kwargs)
        return self._make_response(resp)

    def request(self, method: str, path: str, **kwargs: Any) -> ProtocolResponse:
        """Send arbitrary request to the API."""
        kwargs.setdefault("headers", {}).update(self._headers())
        resp = self._client.request(method, path, **kwargs)
        return self._make_response(resp)

    # === Control Protocol Methods ===

    def health_check(self) -> dict[str, Any]:
        """Check if the API implements the VenomQA protocol."""
        resp = self._client.get(f"{self.control_prefix}/health")
        if resp.status_code != 200:
            raise RuntimeError(
                f"VenomQA health check failed: {resp.status_code}. "
                f"Does your API implement {self.control_prefix}/health?"
            )
        return resp.json()

    def begin_session(self, session_id: str | None = None) -> str:
        """Begin a new VenomQA session.

        Returns the session ID.
        """
        if self._session_id:
            raise RuntimeError(f"Session already active: {self._session_id}")

        session_id = session_id or f"venomqa_{uuid.uuid4().hex[:12]}"

        resp = self._client.post(
            f"{self.control_prefix}/begin",
            json={"session_id": session_id},
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Failed to begin session: {resp.text}")

        self._session_id = session_id
        self._checkpoints = []
        return session_id

    def checkpoint(self) -> str:
        """Create a savepoint and return its ID."""
        if not self._session_id:
            raise RuntimeError("No active session. Call begin_session() first.")

        resp = self._client.post(
            f"{self.control_prefix}/checkpoint",
            json={"session_id": self._session_id},
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Failed to create checkpoint: {resp.text}")

        checkpoint_id = resp.json()["checkpoint_id"]
        self._checkpoints.append(checkpoint_id)
        return checkpoint_id

    def rollback(self, checkpoint_id: str | None = None) -> None:
        """Rollback to a savepoint."""
        if not self._session_id:
            raise RuntimeError("No active session. Call begin_session() first.")

        if checkpoint_id is None:
            if not self._checkpoints:
                raise RuntimeError("No checkpoints to rollback to")
            checkpoint_id = self._checkpoints[-1]

        resp = self._client.post(
            f"{self.control_prefix}/rollback",
            json={
                "session_id": self._session_id,
                "checkpoint_id": checkpoint_id,
            },
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Failed to rollback: {resp.text}")

        # Remove checkpoints after the rolled-back one
        if checkpoint_id in self._checkpoints:
            idx = self._checkpoints.index(checkpoint_id)
            self._checkpoints = self._checkpoints[:idx + 1]

    def end_session(self) -> None:
        """End the current session (rollback all changes)."""
        if not self._session_id:
            return  # No session to end

        resp = self._client.post(
            f"{self.control_prefix}/end",
            json={"session_id": self._session_id},
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Failed to end session: {resp.text}")

        self._session_id = None
        self._checkpoints = []

    # === Rollbackable Interface (for World.systems) ===

    def get_state_snapshot(self) -> str:
        """Create a checkpoint (Rollbackable interface)."""
        if not self._session_id:
            self.begin_session()
        return self.checkpoint()

    def rollback_from_snapshot(self, snapshot: str) -> None:
        """Rollback to a checkpoint (Rollbackable interface)."""
        self.rollback(snapshot)

    # === Context Manager ===

    def __enter__(self):
        self.begin_session()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_session()
        return False

    def close(self) -> None:
        """Close the adapter and end any active session."""
        self.end_session()
        self._client.close()
