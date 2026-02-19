"""Rate limiting journeys for API testing.

Demonstrates:
- Burst rate limit enforcement
- Sustained rate limit enforcement
- Rate limit header validation

This module provides journeys for testing API rate limiting behavior
including burst limits, sustained limits, and proper header handling.
"""

from __future__ import annotations

import time
from typing import Any

from venomqa import JourneyCheckpoint as Checkpoint, Journey, Step
from venomqa.http import Client


class RateLimitActions:
    """Actions for rate limit testing operations.

    Provides methods for making requests to test rate limiting
    behavior and checking rate limit status.

    Args:
        base_url: Base URL for the API service.
    """

    def __init__(self, base_url: str) -> None:
        self.client = Client(base_url=base_url)

    def make_request(self, endpoint: str, token: str | None = None) -> Any:
        """Make a GET request to an endpoint.

        Args:
            endpoint: API endpoint path.
            token: Optional authentication token.

        Returns:
            Response object from the request.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get(endpoint, headers=headers)

    def make_authenticated_request(self, endpoint: str, token: str) -> Any:
        """Make an authenticated GET request.

        Args:
            endpoint: API endpoint path.
            token: Required authentication token.

        Returns:
            Response object from the request.
        """
        return self.client.get(endpoint, headers={"Authorization": f"Bearer {token}"})

    def get_rate_limit_status(self, token: str | None = None) -> Any:
        """Get current rate limit status.

        Args:
            token: Optional authentication token.

        Returns:
            Response object containing rate limit status.
        """
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get("/api/rate-limit/status", headers=headers)


def login(client: Client, context: dict) -> Any:
    """Authenticate and store token in context.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from login request.
    """
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "test@example.com"),
            "password": context.get("password", "password123"),
        },
    )
    if response.status_code == 200:
        context["token"] = response.json().get("access_token")
    return response


def make_single_request(client: Client, context: dict) -> Any:
    """Make a single request to test endpoint.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from the request.
    """
    actions = RateLimitActions(base_url=context.get("base_url", "http://localhost:8000"))
    response = actions.make_request(endpoint="/api/test", token=context.get("token"))
    context["last_response"] = response
    return response


def make_burst_requests(client: Client, context: dict) -> dict[str, Any]:
    """Make multiple rapid requests to trigger burst rate limiting.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Dictionary with burst test results.
    """
    actions = RateLimitActions(base_url=context.get("base_url", "http://localhost:8000"))
    burst_count = context.get("burst_count", 10)
    responses = []
    for i in range(burst_count):
        response = actions.make_request(endpoint="/api/test", token=context.get("token"))
        responses.append(
            {
                "index": i,
                "status_code": response.status_code,
                "headers": dict(response.headers) if hasattr(response, "headers") else {},
            }
        )
    context["burst_responses"] = responses
    rate_limited = [r for r in responses if r["status_code"] == 429]
    context["rate_limited_count"] = len(rate_limited)
    return {"total_requests": burst_count, "rate_limited": len(rate_limited)}


def make_sustained_requests(client: Client, context: dict) -> dict[str, Any]:
    """Make sustained requests over time to test sustained rate limiting.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Dictionary with sustained test results.
    """
    actions = RateLimitActions(base_url=context.get("base_url", "http://localhost:8000"))
    total_requests = context.get("sustained_count", 20)
    interval = context.get("request_interval", 0.1)
    responses = []
    for i in range(total_requests):
        response = actions.make_request(endpoint="/api/test", token=context.get("token"))
        responses.append(
            {
                "index": i,
                "status_code": response.status_code,
            }
        )
        if interval > 0:
            time.sleep(interval)
    context["sustained_responses"] = responses
    rate_limited = [r for r in responses if r["status_code"] == 429]
    context["sustained_rate_limited_count"] = len(rate_limited)
    return {"total_requests": total_requests, "rate_limited": len(rate_limited)}


def check_rate_limit_headers(client: Client, context: dict) -> Any:
    """Verify rate limit headers are present in response.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object from the request.
    """
    actions = RateLimitActions(base_url=context.get("base_url", "http://localhost:8000"))
    response = actions.make_request(endpoint="/api/test", token=context.get("token"))
    headers = dict(response.headers) if hasattr(response, "headers") else {}
    context["rate_limit_headers"] = {
        "x_ratelimit_limit": headers.get("X-RateLimit-Limit"),
        "x_ratelimit_remaining": headers.get("X-RateLimit-Remaining"),
        "x_ratelimit_reset": headers.get("X-RateLimit-Reset"),
    }
    if response.status_code == 200:
        assert headers.get("X-RateLimit-Limit") is not None, "Should have X-RateLimit-Limit header"
        assert headers.get("X-RateLimit-Remaining") is not None, (
            "Should have X-RateLimit-Remaining header"
        )
    return response


def verify_rate_limit_exceeded(client: Client, context: dict) -> dict[str, int]:
    """Verify that rate limit was exceeded during burst test.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary containing burst_responses.

    Returns:
        Dictionary with rate limited count.
    """
    responses = context.get("burst_responses", [])
    rate_limited = [r for r in responses if r["status_code"] == 429]
    assert len(rate_limited) > 0, "Should have rate limited responses"
    return {"rate_limited_count": len(rate_limited)}


def get_rate_limit_status(client: Client, context: dict) -> Any:
    """Get current rate limit status from API.

    Args:
        client: HTTP client for making requests.
        context: Test context dictionary for storing state.

    Returns:
        Response object containing rate limit status.
    """
    actions = RateLimitActions(base_url=context.get("base_url", "http://localhost:8000"))
    response = actions.get_rate_limit_status(token=context.get("token"))
    if response.status_code == 200:
        data = response.json()
        context["rate_limit_status"] = data
    return response


rate_limit_burst_flow = Journey(
    name="api_rate_limit_burst",
    description="Test burst rate limit enforcement",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="burst_requests", action=make_burst_requests, args={"burst_count": 20}),
        Checkpoint(name="burst_complete"),
        Step(name="verify_rate_limited", action=verify_rate_limit_exceeded),
    ],
)

rate_limit_sustained_flow = Journey(
    name="api_rate_limit_sustained",
    description="Test sustained rate limit enforcement",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(
            name="sustained_requests",
            action=make_sustained_requests,
            args={"sustained_count": 30, "request_interval": 0.05},
        ),
        Checkpoint(name="sustained_complete"),
        Step(name="check_status", action=get_rate_limit_status),
    ],
)

rate_limit_headers_flow = Journey(
    name="api_rate_limit_headers",
    description="Verify rate limit headers are present and correct",
    steps=[
        Step(name="login", action=login),
        Checkpoint(name="authenticated"),
        Step(name="check_headers", action=check_rate_limit_headers),
        Checkpoint(name="headers_verified"),
        Step(name="get_status", action=get_rate_limit_status),
    ],
)
