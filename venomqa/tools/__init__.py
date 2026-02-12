"""VenomQA Action Tools Library.

This module provides reusable action functions for QA testing including:
- HTTP actions (REST, GraphQL, WebSocket)
- Authentication helpers (OAuth2, JWT, API Key, Basic)
- Database actions (query, insert, update, delete)
- Wait/polling actions
- Assertion helpers
- Email testing actions
- Mock server integration
"""

from venomqa.tools.assertions import (
    assert_contains,
    assert_header,
    assert_header_exists,
    assert_json_contains,
    assert_json_path,
    assert_json_schema,
    assert_response_time,
    assert_status_code,
)
from venomqa.tools.auth import (
    api_key_auth,
    basic_auth,
    bearer_token_auth,
    get_auth_headers,
    jwt_login,
    oauth2_client_credentials,
    oauth2_login,
    oauth2_refresh_token,
    set_auth_context,
)
from venomqa.tools.database import (
    db_delete,
    db_execute,
    db_insert,
    db_query,
    db_update,
    db_upsert,
)
from venomqa.tools.email import (
    clear_emails,
    get_email_by_subject,
    get_latest_email,
    list_emails,
    wait_for_email,
)
from venomqa.tools.http import (
    delete,
    get,
    graphql_query,
    head,
    options,
    patch,
    post,
    put,
    websocket_close,
    websocket_connect,
    websocket_receive,
    websocket_send,
)
from venomqa.tools.mock import (
    clear_mocks,
    get_mock_requests,
    remove_mock,
    setup_mock,
    setup_mock_sequence,
    verify_mock_called,
)
from venomqa.tools.wait import (
    wait_for_condition,
    wait_for_email_received,
    wait_for_health_check,
    wait_for_json_path,
    wait_for_response,
    wait_for_status,
    wait_until,
)

__all__ = [
    # HTTP tools
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "graphql_query",
    "websocket_connect",
    "websocket_send",
    "websocket_receive",
    "websocket_close",
    # Auth tools
    "basic_auth",
    "api_key_auth",
    "bearer_token_auth",
    "oauth2_login",
    "oauth2_client_credentials",
    "oauth2_refresh_token",
    "jwt_login",
    "set_auth_context",
    "get_auth_headers",
    # Database tools
    "db_query",
    "db_insert",
    "db_update",
    "db_delete",
    "db_upsert",
    "db_execute",
    # Wait tools
    "wait_for_response",
    "wait_for_status",
    "wait_for_condition",
    "wait_until",
    "wait_for_health_check",
    "wait_for_json_path",
    "wait_for_email_received",
    # Assertion tools
    "assert_status_code",
    "assert_response_time",
    "assert_json_schema",
    "assert_json_path",
    "assert_json_contains",
    "assert_contains",
    "assert_header",
    "assert_header_exists",
    # Email tools
    "get_latest_email",
    "get_email_by_subject",
    "list_emails",
    "wait_for_email",
    "clear_emails",
    # Mock tools
    "setup_mock",
    "setup_mock_sequence",
    "remove_mock",
    "clear_mocks",
    "verify_mock_called",
    "get_mock_requests",
]
