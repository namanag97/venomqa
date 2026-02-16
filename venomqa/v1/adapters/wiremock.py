"""WireMock adapter for mocking external APIs."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import httpx

from venomqa.v1.core.state import Observation
from venomqa.v1.world.rollbackable import SystemCheckpoint


class WireMockAdapter:
    """WireMock adapter for mocking external HTTP services.

    WireMock is a tool for mocking HTTP-based APIs. This adapter provides:
    - checkpoint(): Save current stub mappings
    - rollback(): Restore stub mappings
    - observe(): Get request journal and stub info

    WireMock must be running and accessible at the admin_url.
    """

    def __init__(
        self,
        admin_url: str = "http://localhost:8080/__admin",
        timeout: float = 10.0,
    ) -> None:
        """Initialize the WireMock adapter.

        Args:
            admin_url: WireMock admin API URL (usually http://host:port/__admin)
            timeout: Request timeout in seconds
        """
        self.admin_url = admin_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def checkpoint(self, name: str) -> SystemCheckpoint:
        """Save current stub mappings.

        Returns a snapshot of all current mappings that can be restored later.
        """
        # Get all current mappings
        response = self._client.get(f"{self.admin_url}/mappings")
        response.raise_for_status()
        mappings = response.json()

        # Get request journal
        response = self._client.get(f"{self.admin_url}/requests")
        response.raise_for_status()
        requests = response.json()

        return {
            "name": name,
            "mappings": mappings,
            "requests_count": len(requests.get("requests", [])),
            "timestamp": datetime.now().isoformat(),
        }

    def rollback(self, checkpoint: SystemCheckpoint) -> None:
        """Restore stub mappings from checkpoint."""
        # Reset all mappings
        self._client.post(f"{self.admin_url}/mappings/reset")

        # Restore saved mappings
        mappings = checkpoint.get("mappings", {})
        for mapping in mappings.get("mappings", []):
            self._client.post(
                f"{self.admin_url}/mappings",
                json=mapping,
            )

        # Clear request journal
        self._client.delete(f"{self.admin_url}/requests")

    def observe(self) -> Observation:
        """Get current WireMock state."""
        # Get mappings count
        response = self._client.get(f"{self.admin_url}/mappings")
        mappings = response.json() if response.is_success else {"mappings": []}

        # Get request count
        response = self._client.get(f"{self.admin_url}/requests")
        requests = response.json() if response.is_success else {"requests": []}

        # Get unmatched requests
        response = self._client.get(f"{self.admin_url}/requests/unmatched")
        unmatched = response.json() if response.is_success else {"requests": []}

        return Observation(
            system="wiremock",
            data={
                "mappings_count": len(mappings.get("mappings", [])),
                "requests_count": len(requests.get("requests", [])),
                "unmatched_count": len(unmatched.get("requests", [])),
            },
            observed_at=datetime.now(),
        )

    def add_stub(
        self,
        url_pattern: str,
        method: str = "GET",
        response_body: Any = None,
        response_status: int = 200,
        response_headers: dict[str, str] | None = None,
    ) -> str:
        """Add a stub mapping.

        Returns the mapping ID.
        """
        mapping = {
            "request": {
                "method": method,
                "urlPattern": url_pattern,
            },
            "response": {
                "status": response_status,
                "headers": response_headers or {"Content-Type": "application/json"},
            },
        }

        if response_body is not None:
            if isinstance(response_body, (dict, list)):
                mapping["response"]["jsonBody"] = response_body
            else:
                mapping["response"]["body"] = str(response_body)

        response = self._client.post(
            f"{self.admin_url}/mappings",
            json=mapping,
        )
        response.raise_for_status()
        return response.json().get("id", "")

    def remove_stub(self, mapping_id: str) -> None:
        """Remove a stub mapping by ID."""
        self._client.delete(f"{self.admin_url}/mappings/{mapping_id}")

    def get_requests(self, url_pattern: str | None = None) -> list[dict[str, Any]]:
        """Get recorded requests, optionally filtered by URL pattern."""
        if url_pattern:
            response = self._client.post(
                f"{self.admin_url}/requests/find",
                json={"urlPattern": url_pattern},
            )
        else:
            response = self._client.get(f"{self.admin_url}/requests")

        if response.is_success:
            return response.json().get("requests", [])
        return []

    def verify_called(
        self,
        url_pattern: str,
        method: str = "GET",
        times: int | None = None,
    ) -> bool:
        """Verify that a URL was called.

        Args:
            url_pattern: URL pattern to check
            method: HTTP method
            times: Expected number of calls (None = at least once)

        Returns:
            True if verification passes
        """
        response = self._client.post(
            f"{self.admin_url}/requests/count",
            json={
                "method": method,
                "urlPattern": url_pattern,
            },
        )

        if not response.is_success:
            return False

        count = response.json().get("count", 0)

        if times is None:
            return count > 0
        return count == times

    def reset(self) -> None:
        """Reset all mappings and request journal."""
        self._client.post(f"{self.admin_url}/reset")

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> WireMockAdapter:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
