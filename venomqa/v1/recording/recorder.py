"""Request recorder — wraps HttpClient to capture HTTP traffic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from venomqa.v1.core.action import ActionResult, HTTPRequest, HTTPResponse


@dataclass
class RecordedRequest:
    """A single captured HTTP request/response pair."""

    method: str
    url: str
    request_headers: dict[str, str]
    request_body: Any
    status_code: int
    response_headers: dict[str, str]
    response_body: Any
    duration_ms: float
    recorded_at: datetime = field(default_factory=datetime.now)

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    @classmethod
    def from_action_result(cls, result: ActionResult) -> "RecordedRequest":
        req = result.request
        resp = result.response
        return cls(
            method=req.method,
            url=req.url,
            request_headers=req.headers,
            request_body=req.body,
            status_code=resp.status_code if resp else 0,
            response_headers=resp.headers if resp else {},
            response_body=resp.body if resp else None,
            duration_ms=result.duration_ms,
        )


class RequestRecorder:
    """Wraps an HttpClient and records every request/response.

    Usage::

        from venomqa.v1.adapters.http import HttpClient
        from venomqa.v1.recording import RequestRecorder

        api = HttpClient("http://localhost:8000")
        recorder = RequestRecorder(api)

        # Use recorder as a drop-in replacement for api
        recorder.get("/users")
        recorder.post("/users", json={"name": "Alice"})

        # Access captured traffic
        for req in recorder.captured:
            print(req.method, req.url, req.status_code)

        # Generate a Journey skeleton from the captured traffic
        from venomqa.v1.recording import generate_journey_code
        print(generate_journey_code(recorder.captured))
    """

    def __init__(self, api: Any) -> None:
        self._api = api
        self._captured: list[RecordedRequest] = []

    # ------------------------------------------------------------------
    # Proxy all HTTP methods to the underlying client
    # ------------------------------------------------------------------

    def get(self, path: str, **kwargs: Any) -> Any:
        return self._record("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self._record("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self._record("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        return self._record("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self._record("DELETE", path, **kwargs)

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._record(method.upper(), path, **kwargs)

    # ------------------------------------------------------------------
    # Forwarding to underlying api — supports ActionResult-returning clients
    # ------------------------------------------------------------------

    def _record(self, method: str, path: str, **kwargs: Any) -> Any:
        import time
        t0 = time.perf_counter()
        result = getattr(self._api, method.lower())(path, **kwargs)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # If the underlying client returns an ActionResult, record it directly
        if isinstance(result, ActionResult):
            recorded = RecordedRequest.from_action_result(result)
            recorded.duration_ms = elapsed_ms
            self._captured.append(recorded)
            return result

        # Otherwise record a minimal entry
        recorded = RecordedRequest(
            method=method,
            url=path,
            request_headers={},
            request_body=kwargs.get("json") or kwargs.get("data"),
            status_code=getattr(getattr(result, "status_code", None), "__int__", lambda: 0)(),
            response_headers={},
            response_body=None,
            duration_ms=elapsed_ms,
        )
        self._captured.append(recorded)
        return result

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    @property
    def captured(self) -> list[RecordedRequest]:
        """All captured requests in order."""
        return list(self._captured)

    def clear(self) -> None:
        """Clear captured requests."""
        self._captured.clear()

    def __len__(self) -> int:
        return len(self._captured)

    def __iter__(self):
        return iter(self._captured)

    # ------------------------------------------------------------------
    # Passthrough for attributes of the underlying api (e.g. base_url)
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        return getattr(self._api, name)
