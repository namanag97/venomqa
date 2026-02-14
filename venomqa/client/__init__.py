"""HTTP Client with history tracking and retry logic.

.. deprecated:: 0.2.0
    This module path is deprecated. Import from `venomqa.http` or
    directly from `venomqa` instead::

        # Old (deprecated):
        from venomqa.client import Client

        # New (preferred):
        from venomqa.http import Client
        # Or:
        from venomqa import Client

This module provides HTTP clients for testing REST APIs with comprehensive
features including request history tracking, automatic retries, authentication,
and sensitive data handling.

Classes:
    RequestRecord: Record of an HTTP request/response.
    SecureCredentials: Secure credential storage with auto-refresh.
    Client: Synchronous HTTP client.
    AsyncClient: Asynchronous HTTP client.

Example:
    >>> from venomqa import Client  # Recommended
    >>> with Client("https://api.example.com") as client:
    ...     client.set_auth_token("my-token")
    ...     response = client.get("/users")
    ...     print(response.json())
"""

import warnings

# Issue deprecation warning when this module is imported
warnings.warn(
    "Importing from 'venomqa.client' is deprecated. "
    "Use 'from venomqa import Client' or 'from venomqa.http import Client' instead. "
    "This import path will be removed in version 1.0.0.",
    DeprecationWarning,
    stacklevel=2,
)

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
