from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Request:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    body: Any = None
    json_body: dict[str, Any] | None = None
    form_data: dict[str, str] | None = None
    multipart_data: dict[str, Any] | None = None
    timeout: float = 30.0
    allow_redirects: bool = True
    verify_ssl: bool = True
    cookies: dict[str, str] = field(default_factory=dict)


@dataclass
class Response:
    status_code: int
    headers: dict[str, str]
    body: bytes
    json_data: dict[str, Any] | None = None
    text: str = ""
    elapsed_ms: float = 0.0
    cookies: dict[str, str] = field(default_factory=dict)
    request: Request | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict[str, Any]:
        if self.json_data is not None:
            return self.json_data
        import json

        return json.loads(self.text)


@dataclass
class RequestBuilder:
    base_url: str = ""
    default_headers: dict[str, str] = field(default_factory=dict)
    default_params: dict[str, str] = field(default_factory=dict)
    default_timeout: float = 30.0
    auth_token: str | None = None
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer"


class ClientPort(ABC):
    @abstractmethod
    def request(self, request: Request) -> Response:
        """
        Execute an HTTP request.

        Args:
            request: The request to execute.

        Returns:
            Response object containing the server response.
        """
        ...

    @abstractmethod
    def get(self, url: str, **kwargs: Any) -> Response:
        """
        Execute a GET request.

        Args:
            url: The URL to request.
            **kwargs: Additional request options (headers, params, etc.)

        Returns:
            Response object.
        """
        ...

    @abstractmethod
    def post(self, url: str, **kwargs: Any) -> Response:
        """
        Execute a POST request.

        Args:
            url: The URL to request.
            **kwargs: Additional request options (json, data, headers, etc.)

        Returns:
            Response object.
        """
        ...

    @abstractmethod
    def put(self, url: str, **kwargs: Any) -> Response:
        """
        Execute a PUT request.

        Args:
            url: The URL to request.
            **kwargs: Additional request options.

        Returns:
            Response object.
        """
        ...

    @abstractmethod
    def patch(self, url: str, **kwargs: Any) -> Response:
        """
        Execute a PATCH request.

        Args:
            url: The URL to request.
            **kwargs: Additional request options.

        Returns:
            Response object.
        """
        ...

    @abstractmethod
    def delete(self, url: str, **kwargs: Any) -> Response:
        """
        Execute a DELETE request.

        Args:
            url: The URL to request.
            **kwargs: Additional request options.

        Returns:
            Response object.
        """
        ...

    @abstractmethod
    def head(self, url: str, **kwargs: Any) -> Response:
        """
        Execute a HEAD request.

        Args:
            url: The URL to request.
            **kwargs: Additional request options.

        Returns:
            Response object.
        """
        ...

    @abstractmethod
    def options(self, url: str, **kwargs: Any) -> Response:
        """
        Execute an OPTIONS request.

        Args:
            url: The URL to request.
            **kwargs: Additional request options.

        Returns:
            Response object.
        """
        ...

    @abstractmethod
    def set_base_url(self, base_url: str) -> None:
        """
        Set the base URL for all requests.

        Args:
            base_url: The base URL to prepend to all request URLs.
        """
        ...

    @abstractmethod
    def set_default_header(self, name: str, value: str) -> None:
        """
        Set a default header for all requests.

        Args:
            name: Header name.
            value: Header value.
        """
        ...

    @abstractmethod
    def set_auth_token(
        self, token: str, header: str = "Authorization", prefix: str = "Bearer"
    ) -> None:
        """
        Set authentication token for all requests.

        Args:
            token: The auth token.
            header: Header name for the token.
            prefix: Prefix for the token value (e.g., "Bearer").
        """
        ...

    @abstractmethod
    def clear_auth_token(self) -> None:
        """
        Clear the authentication token.
        """
        ...

    @abstractmethod
    def set_cookies(self, cookies: dict[str, str]) -> None:
        """
        Set cookies for all requests.

        Args:
            cookies: Dictionary of cookie name-value pairs.
        """
        ...

    @abstractmethod
    def get_cookies(self) -> dict[str, str]:
        """
        Get current cookies.

        Returns:
            Dictionary of current cookies.
        """
        ...

    @abstractmethod
    def create_session(self) -> str:
        """
        Create a new isolated session with its own cookies/headers.

        Returns:
            Session ID for the new session.
        """
        ...

    @abstractmethod
    def use_session(self, session_id: str) -> None:
        """
        Switch to a specific session.

        Args:
            session_id: The session ID to use.
        """
        ...

    @abstractmethod
    def close_session(self, session_id: str) -> None:
        """
        Close and remove a session.

        Args:
            session_id: The session ID to close.
        """
        ...

    @abstractmethod
    def intercept_requests(self, interceptor: Callable[[Request], Request | None]) -> None:
        """
        Add a request interceptor.

        Args:
            interceptor: Function that can modify or block requests.
                        Return None to block the request.
        """
        ...

    @abstractmethod
    def intercept_responses(self, interceptor: Callable[[Response], Response | None]) -> None:
        """
        Add a response interceptor.

        Args:
            interceptor: Function that can modify responses.
                        Return None to treat as an error.
        """
        ...

    @abstractmethod
    def mock_response(self, method: str, url: str, response: Response) -> None:
        """
        Mock a response for a specific request pattern.

        Args:
            method: HTTP method to match.
            url: URL pattern to match (supports wildcards).
            response: The mock response to return.
        """
        ...

    @abstractmethod
    def clear_mocks(self) -> None:
        """
        Clear all mocked responses.
        """
        ...

    @abstractmethod
    def wait_for_request(
        self, method: str, url_pattern: str, timeout: float = 10.0
    ) -> Request | None:
        """
        Wait for a request matching the pattern to be made.

        Args:
            method: HTTP method to match.
            url_pattern: URL pattern to match (supports wildcards).
            timeout: Maximum time to wait in seconds.

        Returns:
            The matched request or None if timeout.
        """
        ...

    @abstractmethod
    def get_request_history(self, limit: int = 100) -> list[Request]:
        """
        Get history of made requests.

        Args:
            limit: Maximum number of requests to return.

        Returns:
            List of requests in chronological order.
        """
        ...
