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
        files: Any = None,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
    ) -> ActionResult:
        """Make an HTTP request and return ActionResult.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE)
            path: URL path (appended to base_url)
            json: JSON body (dict or list)
            data: Form data (dict)
            files: File uploads - dict of {field: (filename, content, content_type)}
                   Example: {"file": ("test.txt", b"content", "text/plain")}
            headers: Additional headers
            params: Query parameters
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        merged_headers = {**self.default_headers, **(headers or {})}

        request = HTTPRequest(
            method=method.upper(),
            url=url,
            headers=merged_headers,
            body=json or data or ("[file upload]" if files else None),
        )

        start = time.perf_counter()
        try:
            resp = self._client.request(
                method=method,
                url=path,
                json=json,
                data=data,
                files=files,
                headers=headers,
                params=params,
            )
            duration_ms = (time.perf_counter() - start) * 1000

            if resp.headers.get("content-type", "").startswith("application/json"):
                try:
                    body: Any = resp.json()
                except Exception:
                    body = resp.text
            else:
                body = resp.text

            response = HTTPResponse(
                status_code=resp.status_code,
                headers=dict(resp.headers),
                body=body,
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

    def with_headers(self, headers: dict[str, str]) -> HttpClient:
        """Return a new HttpClient with additional default headers.

        The new client shares the same base URL and timeout but merges
        the given headers on top of this client's default headers.
        Useful for injecting per-role or per-workspace auth tokens without
        creating an entirely separate client.

        Example::

            admin_api = api.with_headers({"Authorization": f"Bearer {admin_token}"})
            viewer_api = api.with_headers({"Authorization": f"Bearer {viewer_token}"})

            # In actions:
            def get_as_viewer(api, context):
                viewer = api.with_headers({"Authorization": context.get("viewer_token")})
                return viewer.get("/workspace/123/connections")
        """
        merged = {**self.default_headers, **headers}
        return HttpClient(base_url=self.base_url, timeout=self.timeout, headers=merged)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
