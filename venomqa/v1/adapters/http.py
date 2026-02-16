"""HTTP client adapter."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import httpx

from venomqa.v1.core.action import ActionResult, HTTPRequest, HTTPResponse


class HttpClient:
    """HTTP client for making requests to the API under test."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.default_headers = headers or {}
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers=self.default_headers,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> ActionResult:
        """Make an HTTP request and return ActionResult."""
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        merged_headers = {**self.default_headers, **(headers or {})}

        request = HTTPRequest(
            method=method.upper(),
            url=url,
            headers=merged_headers,
            body=json or data,
        )

        start = time.perf_counter()
        try:
            resp = self._client.request(
                method=method,
                url=path,
                json=json,
                data=data,
                headers=headers,
                params=params,
            )
            duration_ms = (time.perf_counter() - start) * 1000

            response = HTTPResponse(
                status_code=resp.status_code,
                headers=dict(resp.headers),
                body=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text,
            )

            return ActionResult.from_response(request, response, duration_ms)

        except httpx.HTTPError as e:
            return ActionResult.from_error(request, str(e))

    def get(self, path: str, **kwargs: Any) -> ActionResult:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> ActionResult:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> ActionResult:
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> ActionResult:
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> ActionResult:
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
