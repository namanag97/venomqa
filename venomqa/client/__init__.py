"""HTTP Client with history tracking and retry logic.

.. deprecated::
    This module is deprecated. Import from `venomqa.http` instead::

        # Old (still works for backward compatibility):
        from venomqa.client import Client

        # New (preferred):
        from venomqa.http import Client

This module provides HTTP clients for testing REST APIs with comprehensive
features including request history tracking, automatic retries, authentication,
and sensitive data handling.

Classes:
    RequestRecord: Record of an HTTP request/response.
    SecureCredentials: Secure credential storage with auto-refresh.
    Client: Synchronous HTTP client.
    AsyncClient: Asynchronous HTTP client.

Example:
    >>> from venomqa.http import Client  # Preferred
    >>> with Client("https://api.example.com") as client:
    ...     client.set_auth_token("my-token")
    ...     response = client.get("/users")
    ...     print(response.json())
"""

# Re-export from new location for backward compatibility
from venomqa.http.rest import (
    AsyncClient,
    Client,
    ClientValidationError,
    RequestRecord,
    SecureCredentials,
)

__all__ = [
    "Client",
    "AsyncClient",
    "RequestRecord",
    "SecureCredentials",
    "ClientValidationError",
]
