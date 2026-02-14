"""Tests for HTTP client with history tracking and retry logic."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import httpx
import pytest

from venomqa.client import AsyncClient, Client, RequestRecord


class TestRequestRecord:
    """Tests for RequestRecord model."""

    def test_request_record_creation(self) -> None:
        from datetime import datetime

        record = RequestRecord(
            method="GET",
            url="http://localhost/users/1",
            request_body=None,
            response_status=200,
            response_body={"id": 1},
            headers={"Authorization": "Bearer token"},
            duration_ms=50.5,
        )

        assert record.method == "GET"
        assert record.url == "http://localhost/users/1"
        assert record.response_status == 200
        assert record.response_body == {"id": 1}
        assert record.duration_ms == 50.5
        assert record.error is None
        assert isinstance(record.timestamp, datetime)

    def test_request_record_with_error(self) -> None:
        record = RequestRecord(
            method="POST",
            url="http://localhost/users",
            request_body={"name": "test"},
            response_status=0,
            response_body=None,
            headers={},
            duration_ms=0.0,
            error="Connection refused",
        )

        assert record.error == "Connection refused"
        assert record.response_status == 0


class TestClient:
    """Tests for synchronous HTTP client."""

    def test_client_initialization(self) -> None:
        client = Client(
            base_url="http://localhost:8080",
            timeout=60.0,
            retry_count=5,
            retry_delay=2.0,
            default_headers={"X-Custom": "value"},
        )

        assert client.base_url == "http://localhost:8080"
        assert client.timeout == 60.0
        assert client.retry_count == 5
        assert client.retry_delay == 2.0
        assert client.default_headers == {"X-Custom": "value"}
        assert client.history == []

    def test_client_base_url_trailing_slash(self) -> None:
        client = Client(base_url="http://localhost:8080/")
        assert client.base_url == "http://localhost:8080"

    def test_connect_creates_httpx_client(self) -> None:
        client = Client(base_url="http://localhost:8080")

        with patch("venomqa.http.rest.httpx.Client") as mock_httpx_client:
            client.connect()
            mock_httpx_client.assert_called_once()

    def test_disconnect_closes_client(self) -> None:
        client = Client(base_url="http://localhost:8080")
        mock_httpx = MagicMock()
        client._client = mock_httpx

        client.disconnect()

        mock_httpx.close.assert_called_once()
        assert client._client is None

    def test_set_auth_token(self) -> None:
        client = Client(base_url="http://localhost:8080")
        client.set_auth_token("my-token")

        assert client._auth_token == "Bearer my-token"

    def test_set_auth_token_custom_scheme(self) -> None:
        client = Client(base_url="http://localhost:8080")
        client.set_auth_token("my-token", scheme="Token")

        assert client._auth_token == "Token my-token"

    def test_clear_auth(self) -> None:
        client = Client(base_url="http://localhost:8080")
        client.set_auth_token("my-token")
        client.clear_auth()

        assert client._auth_token is None

    def test_request_success(self) -> None:
        client = Client(base_url="http://localhost:8080")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.is_server_error = False
        mock_response.json.return_value = {"id": 1}
        mock_response.headers = {"Content-Type": "application/json"}

        with patch.object(client, "_client") as mock_httpx:
            mock_httpx.request.return_value = mock_response
            client._client = mock_httpx

            response = client.get("/users/1")

        assert response.status_code == 200
        assert len(client.history) == 1

        record = client.history[0]
        assert record.method == "GET"
        assert record.response_status == 200
        assert record.error is None

    def test_request_tracks_history(self) -> None:
        client = Client(base_url="http://localhost:8080")

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.is_server_error = False
        mock_response.json.return_value = {"id": 1, "name": "Test"}
        mock_response.headers = {}

        with patch.object(client, "_client") as mock_httpx:
            mock_httpx.request.return_value = mock_response
            client._client = mock_httpx

            client.post("/users", json={"name": "Test"})

        assert len(client.history) == 1
        record = client.history[0]
        assert record.method == "POST"
        assert record.request_body == {"name": "Test"}

    def test_request_includes_auth_header(self) -> None:
        client = Client(base_url="http://localhost:8080")
        client.set_auth_token("secret-token")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.is_server_error = False
        mock_response.json.return_value = {}
        mock_response.headers = {}

        with patch.object(client, "_client") as mock_httpx:
            mock_httpx.request.return_value = mock_response
            client._client = mock_httpx

            client.get("/protected")

        call_args = mock_httpx.request.call_args
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer secret-token"

    def test_retry_on_server_error(self) -> None:
        client = Client(base_url="http://localhost:8080", retry_count=3, retry_delay=0.01)

        error_response = Mock()
        error_response.status_code = 500
        error_response.is_server_error = True
        error_response.json.return_value = {"error": "Internal error"}
        error_response.headers = {}

        success_response = Mock()
        success_response.status_code = 200
        success_response.is_server_error = False
        success_response.json.return_value = {"ok": True}
        success_response.headers = {}

        with patch.object(client, "_client") as mock_httpx:
            mock_httpx.request.side_effect = [error_response, error_response, success_response]
            client._client = mock_httpx

            with patch("venomqa.client.time.sleep"):
                response = client.get("/flaky-endpoint")

        assert response.status_code == 200
        assert mock_httpx.request.call_count == 3

    def test_retry_exhausted_raises_error(self) -> None:
        client = Client(base_url="http://localhost:8080", retry_count=2, retry_delay=0.01)

        error_response = Mock()
        error_response.status_code = 503
        error_response.is_server_error = True
        error_response.json.return_value = {}
        error_response.headers = {}

        with patch.object(client, "_client") as mock_httpx:
            mock_httpx.request.return_value = error_response
            client._client = mock_httpx

            with patch("venomqa.client.time.sleep"):
                response = client.get("/always-down")

        assert response.status_code == 503
        assert mock_httpx.request.call_count == 2

    def test_retry_on_timeout(self) -> None:
        client = Client(base_url="http://localhost:8080", retry_count=3, retry_delay=0.01)

        success_response = Mock()
        success_response.status_code = 200
        success_response.is_server_error = False
        success_response.json.return_value = {}
        success_response.headers = {}

        with patch.object(client, "_client") as mock_httpx:
            mock_httpx.request.side_effect = [
                httpx.TimeoutException("timeout"),
                success_response,
            ]
            client._client = mock_httpx

            with patch("venomqa.client.time.sleep"):
                response = client.get("/slow-endpoint")

        assert response.status_code == 200

    def test_retry_exhausted_on_timeout_raises(self) -> None:
        client = Client(base_url="http://localhost:8080", retry_count=2, retry_delay=0.01)

        with patch.object(client, "_client") as mock_httpx:
            mock_httpx.request.side_effect = httpx.TimeoutException("timeout")
            client._client = mock_httpx

            with patch("venomqa.client.time.sleep"):
                with pytest.raises(httpx.TimeoutException):
                    client.get("/always-timeout")

        assert len(client.history) == 1
        assert client.history[0].error is not None

    def test_get_history(self) -> None:
        client = Client(base_url="http://localhost:8080")
        client.history = [
            RequestRecord(
                method="GET",
                url="http://localhost/users",
                request_body=None,
                response_status=200,
                response_body=[],
                headers={},
                duration_ms=10.0,
            )
        ]

        history = client.get_history()

        assert len(history) == 1
        assert history is not client.history

    def test_clear_history(self) -> None:
        client = Client(base_url="http://localhost:8080")
        client.history = [
            RequestRecord(
                method="GET",
                url="http://localhost/users",
                request_body=None,
                response_status=200,
                response_body=[],
                headers={},
                duration_ms=10.0,
            )
        ]

        client.clear_history()

        assert client.history == []

    def test_last_request(self) -> None:
        client = Client(base_url="http://localhost:8080")
        client.history = [
            RequestRecord(
                method="GET",
                url="http://localhost/users/1",
                request_body=None,
                response_status=200,
                response_body={"id": 1},
                headers={},
                duration_ms=10.0,
            ),
            RequestRecord(
                method="POST",
                url="http://localhost/users",
                request_body={"name": "test"},
                response_status=201,
                response_body={"id": 2},
                headers={},
                duration_ms=20.0,
            ),
        ]

        last = client.last_request()

        assert last is not None
        assert last.method == "POST"

    def test_last_request_empty_history(self) -> None:
        client = Client(base_url="http://localhost:8080")

        assert client.last_request() is None

    def test_http_methods(self) -> None:
        client = Client(base_url="http://localhost:8080")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.is_server_error = False
        mock_response.json.return_value = {}
        mock_response.headers = {}

        with patch.object(client, "_client") as mock_httpx:
            mock_httpx.request.return_value = mock_response
            client._client = mock_httpx

            client.get("/resource")
            client.post("/resource", json={"data": "test"})
            client.put("/resource/1", json={"data": "updated"})
            client.patch("/resource/1", json={"data": "patched"})
            client.delete("/resource/1")

        assert len(client.history) == 5
        methods = [r.method for r in client.history]
        assert methods == ["GET", "POST", "PUT", "PATCH", "DELETE"]


class TestAsyncClient:
    """Tests for asynchronous HTTP client."""

    def test_async_client_initialization(self) -> None:
        client = AsyncClient(
            base_url="http://localhost:8080",
            timeout=60.0,
            retry_count=5,
        )

        assert client.base_url == "http://localhost:8080"
        assert client.timeout == 60.0
        assert client.retry_count == 5

    @pytest.mark.asyncio
    async def test_async_connect(self) -> None:
        client = AsyncClient(base_url="http://localhost:8080")

        with patch("venomqa.http.rest.httpx.AsyncClient") as mock_async_client:
            await client.connect()
            mock_async_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_disconnect(self) -> None:
        client = AsyncClient(base_url="http://localhost:8080")
        client._client = MagicMock()
        client._client.aclose = MagicMock(return_value=None)
        client._client.aclose.coroutine = MagicMock(return_value=None)

        with patch.object(client._client, "aclose", new_callable=MagicMock) as mock_close:
            mock_close.return_value = None
            import asyncio

            async def mock_aclose():
                return None

            mock_close.side_effect = mock_aclose
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_async_request_success(self) -> None:
        client = AsyncClient(base_url="http://localhost:8080")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.is_server_error = False
        mock_response.json.return_value = {"id": 1}
        mock_response.headers = {}

        async def mock_request(method, path, **kwargs):
            return mock_response

        with patch.object(client, "_client") as mock_httpx:
            mock_httpx.request = mock_request
            client._client = mock_httpx

            response = await client.get("/users/1")

        assert response.status_code == 200
        assert len(client.history) == 1

    def test_async_set_auth_token(self) -> None:
        client = AsyncClient(base_url="http://localhost:8080")
        client.set_auth_token("async-token")

        assert client._auth_token == "Bearer async-token"

    def test_async_get_history(self) -> None:
        client = AsyncClient(base_url="http://localhost:8080")
        client.history = [
            RequestRecord(
                method="GET",
                url="http://localhost/async",
                request_body=None,
                response_status=200,
                response_body={},
                headers={},
                duration_ms=5.0,
            )
        ]

        history = client.get_history()
        assert len(history) == 1
