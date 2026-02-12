"""Tests for assertion functions in VenomQA."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from unittest.mock import MagicMock

import httpx
import pytest

from venomqa.tools.assertions import (
    AssertionError,
    assert_status_code,
    assert_status_ok,
    assert_status_created,
    assert_status_no_content,
    assert_status_bad_request,
    assert_status_unauthorized,
    assert_status_forbidden,
    assert_status_not_found,
    assert_status_client_error,
    assert_status_server_error,
    assert_response_time,
    assert_response_time_range,
    assert_json_schema,
    assert_json_path,
    assert_json_contains,
    assert_json_list_length,
    assert_contains,
    assert_not_contains,
    assert_matches_regex,
    assert_header,
    assert_header_exists,
    assert_header_contains,
    assert_content_type,
    assert_json_type,
    assert_custom,
)


def create_response(
    status_code: int = 200,
    json_data: dict | None = None,
    text: str = "",
    headers: dict | None = None,
    elapsed_ms: float = 100.0,
) -> httpx.Response:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.headers = headers or {}
    response.text = text
    response.content = text.encode() if text else b""
    response.elapsed = timedelta(milliseconds=elapsed_ms)

    if json_data is not None:
        response.json = MagicMock(return_value=json_data)
        response._json_data = json_data
    else:

        def raise_json_error():
            raise json.JSONDecodeError("No JSON", "", 0)

        response.json = MagicMock(side_effect=raise_json_error)

    return response


class TestAssertStatusCode:
    """Tests for assert_status_code."""

    def test_single_code_match(self) -> None:
        response = create_response(status_code=200)
        assert_status_code(response, 200)

    def test_single_code_mismatch_raises(self) -> None:
        response = create_response(status_code=404, text="Not Found")
        with pytest.raises(AssertionError, match="Expected status code 200"):
            assert_status_code(response, 200)

    def test_multiple_codes_match(self) -> None:
        response = create_response(status_code=201)
        assert_status_code(response, [200, 201, 204])

    def test_multiple_codes_mismatch_raises(self) -> None:
        response = create_response(status_code=404)
        with pytest.raises(AssertionError):
            assert_status_code(response, [200, 201])

    def test_custom_message(self) -> None:
        response = create_response(status_code=500)
        with pytest.raises(AssertionError, match="Custom error"):
            assert_status_code(response, 200, message="Custom error")


class TestStatusHelpers:
    """Tests for status code helper assertions."""

    def test_assert_status_ok(self) -> None:
        response = create_response(status_code=200)
        assert_status_ok(response)

    def test_assert_status_ok_fails(self) -> None:
        response = create_response(status_code=201)
        with pytest.raises(AssertionError):
            assert_status_ok(response)

    def test_assert_status_created(self) -> None:
        response = create_response(status_code=201)
        assert_status_created(response)

    def test_assert_status_no_content(self) -> None:
        response = create_response(status_code=204)
        assert_status_no_content(response)

    def test_assert_status_bad_request(self) -> None:
        response = create_response(status_code=400)
        assert_status_bad_request(response)

    def test_assert_status_unauthorized(self) -> None:
        response = create_response(status_code=401)
        assert_status_unauthorized(response)

    def test_assert_status_forbidden(self) -> None:
        response = create_response(status_code=403)
        assert_status_forbidden(response)

    def test_assert_status_not_found(self) -> None:
        response = create_response(status_code=404)
        assert_status_not_found(response)

    def test_assert_status_client_error_4xx(self) -> None:
        for code in [400, 404, 422, 429]:
            response = create_response(status_code=code)
            assert_status_client_error(response)

    def test_assert_status_client_error_5xx_fails(self) -> None:
        response = create_response(status_code=500)
        with pytest.raises(AssertionError):
            assert_status_client_error(response)

    def test_assert_status_server_error_5xx(self) -> None:
        for code in [500, 502, 503, 504]:
            response = create_response(status_code=code)
            assert_status_server_error(response)

    def test_assert_status_server_error_4xx_fails(self) -> None:
        response = create_response(status_code=400)
        with pytest.raises(AssertionError):
            assert_status_server_error(response)


class TestAssertResponseTime:
    """Tests for assert_response_time."""

    def test_within_limit(self) -> None:
        response = create_response(elapsed_ms=100.0)
        assert_response_time(response, max_ms=200.0)

    def test_exceeds_limit_raises(self) -> None:
        response = create_response(elapsed_ms=500.0)
        with pytest.raises(AssertionError, match="exceeded maximum"):
            assert_response_time(response, max_ms=200.0)

    def test_custom_message(self) -> None:
        response = create_response(elapsed_ms=500.0)
        with pytest.raises(AssertionError, match="Too slow"):
            assert_response_time(response, max_ms=200.0, message="Too slow")


class TestAssertResponseTimeRange:
    """Tests for assert_response_time_range."""

    def test_within_range(self) -> None:
        response = create_response(elapsed_ms=150.0)
        assert_response_time_range(response, min_ms=100.0, max_ms=200.0)

    def test_below_minimum_raises(self) -> None:
        response = create_response(elapsed_ms=50.0)
        with pytest.raises(AssertionError):
            assert_response_time_range(response, min_ms=100.0, max_ms=200.0)

    def test_above_maximum_raises(self) -> None:
        response = create_response(elapsed_ms=300.0)
        with pytest.raises(AssertionError):
            assert_response_time_range(response, min_ms=100.0, max_ms=200.0)


class TestAssertJsonPath:
    """Tests for assert_json_path."""

    def test_simple_path_exists(self) -> None:
        response = create_response(json_data={"name": "John", "age": 30})
        result = assert_json_path(response, "name")
        assert result == "John"

    def test_nested_path_exists(self) -> None:
        response = create_response(json_data={"user": {"profile": {"city": "NYC"}}})
        result = assert_json_path(response, "user.profile.city")
        assert result == "NYC"

    def test_path_with_expected_value_match(self) -> None:
        response = create_response(json_data={"status": "active"})
        assert_json_path(response, "status", expected_value="active")

    def test_path_with_expected_value_mismatch(self) -> None:
        response = create_response(json_data={"status": "inactive"})
        with pytest.raises(AssertionError, match="Expected value"):
            assert_json_path(response, "status", expected_value="active")

    def test_path_not_found_raises(self) -> None:
        response = create_response(json_data={"name": "John"})
        with pytest.raises(AssertionError, match="not found"):
            assert_json_path(response, "email")

    def test_array_index_access(self) -> None:
        response = create_response(json_data={"items": [1, 2, 3]})
        result = assert_json_path(response, "items.0")
        assert result == 1

    def test_invalid_array_index_raises(self) -> None:
        response = create_response(json_data={"items": [1, 2]})
        with pytest.raises(AssertionError):
            assert_json_path(response, "items.10")


class TestAssertJsonContains:
    """Tests for assert_json_contains."""

    def test_contains_simple_pairs(self) -> None:
        response = create_response(json_data={"name": "John", "age": 30, "city": "NYC"})
        assert_json_contains(response, {"name": "John", "age": 30})

    def test_contains_nested_pairs(self) -> None:
        response = create_response(
            json_data={"user": {"name": "John", "email": "john@example.com"}, "status": "active"}
        )
        assert_json_contains(response, {"user": {"name": "John"}})

    def test_missing_key_raises(self) -> None:
        response = create_response(json_data={"name": "John"})
        with pytest.raises(AssertionError, match="does not contain"):
            assert_json_contains(response, {"email": "john@example.com"})

    def test_value_mismatch_raises(self) -> None:
        response = create_response(json_data={"status": "active"})
        with pytest.raises(AssertionError):
            assert_json_contains(response, {"status": "inactive"})


class TestAssertJsonListLength:
    """Tests for assert_json_list_length."""

    def test_exact_length_match(self) -> None:
        response = create_response(json_data={"items": [1, 2, 3, 4, 5]})
        assert_json_list_length(response, expected_length=5, list_path="items")

    def test_exact_length_mismatch(self) -> None:
        response = create_response(json_data={"items": [1, 2, 3]})
        with pytest.raises(AssertionError, match="Expected list length 5"):
            assert_json_list_length(response, expected_length=5, list_path="items")

    def test_range_within_bounds(self) -> None:
        response = create_response(json_data={"items": [1, 2, 3, 4]})
        assert_json_list_length(response, expected_length=(1, 10), list_path="items")

    def test_range_below_minimum(self) -> None:
        response = create_response(json_data={"items": [1]})
        with pytest.raises(AssertionError):
            assert_json_list_length(response, expected_length=(5, 10), list_path="items")

    def test_non_list_raises(self) -> None:
        response = create_response(json_data={"items": "not a list"})
        with pytest.raises(AssertionError, match="not a list"):
            assert_json_list_length(response, expected_length=5, list_path="items")


class TestAssertContains:
    """Tests for assert_contains."""

    def test_contains_string(self) -> None:
        response = create_response(text="Hello World, welcome!")
        assert_contains(response, "World")

    def test_contains_bytes(self) -> None:
        response = create_response(text="Binary data")
        assert_contains(response, b"data")

    def test_not_contains_raises(self) -> None:
        response = create_response(text="Hello World")
        with pytest.raises(AssertionError, match="does not contain"):
            assert_contains(response, "Goodbye")


class TestAssertNotContains:
    """Tests for assert_not_contains."""

    def test_not_contains_string(self) -> None:
        response = create_response(text="Hello World")
        assert_not_contains(response, "password")

    def test_contains_raises(self) -> None:
        response = create_response(text="The password is secret")
        with pytest.raises(AssertionError, match="contains unexpected"):
            assert_not_contains(response, "password")


class TestAssertMatchesRegex:
    """Tests for assert_matches_regex."""

    def test_pattern_matches(self) -> None:
        response = create_response(text='{"version": "1.2.3"}')
        assert_matches_regex(response, r'"version":\s*"\d+\.\d+\.\d+"')

    def test_pattern_does_not_match(self) -> None:
        response = create_response(text="No version here")
        with pytest.raises(AssertionError, match="does not match"):
            assert_matches_regex(response, r"version.*\d+")

    def test_compiled_pattern(self) -> None:
        response = create_response(text="Email: test@example.com")
        pattern = re.compile(r"[\w.]+@[\w.]+")
        assert_matches_regex(response, pattern)


class TestAssertHeader:
    """Tests for assert_header."""

    def test_header_matches(self) -> None:
        response = create_response(headers={"Content-Type": "application/json"})
        assert_header(response, "Content-Type", "application/json")

    def test_header_missing(self) -> None:
        response = create_response(headers={})
        with pytest.raises(AssertionError, match="not found"):
            assert_header(response, "X-Custom-Header", "value")

    def test_header_value_mismatch(self) -> None:
        response = create_response(headers={"Content-Type": "text/html"})
        with pytest.raises(AssertionError, match="expected"):
            assert_header(response, "Content-Type", "application/json")


class TestAssertHeaderExists:
    """Tests for assert_header_exists."""

    def test_header_exists(self) -> None:
        response = create_response(headers={"X-Request-ID": "abc123"})
        assert_header_exists(response, "X-Request-ID")

    def test_header_missing(self) -> None:
        response = create_response(headers={})
        with pytest.raises(AssertionError, match="not found"):
            assert_header_exists(response, "X-Request-ID")


class TestAssertHeaderContains:
    """Tests for assert_header_contains."""

    def test_header_contains_substring(self) -> None:
        response = create_response(headers={"Content-Type": "application/json; charset=utf-8"})
        assert_header_contains(response, "Content-Type", "json")

    def test_header_does_not_contain(self) -> None:
        response = create_response(headers={"Content-Type": "text/html"})
        with pytest.raises(AssertionError, match="does not contain"):
            assert_header_contains(response, "Content-Type", "json")


class TestAssertContentType:
    """Tests for assert_content_type."""

    def test_content_type_match(self) -> None:
        response = create_response(headers={"Content-Type": "application/json; charset=utf-8"})
        assert_content_type(response, "application/json")

    def test_content_type_mismatch(self) -> None:
        response = create_response(headers={"Content-Type": "text/html"})
        with pytest.raises(AssertionError):
            assert_content_type(response, "application/json")


class TestAssertJsonType:
    """Tests for assert_json_type."""

    def test_type_match_string(self) -> None:
        response = create_response(json_data={"name": "John"})
        assert_json_type(response, str, path="name")

    def test_type_match_integer(self) -> None:
        response = create_response(json_data={"count": 42})
        assert_json_type(response, int, path="count")

    def test_type_match_list(self) -> None:
        response = create_response(json_data={"items": [1, 2, 3]})
        assert_json_type(response, list, path="items")

    def test_type_match_multiple_types(self) -> None:
        response = create_response(json_data={"value": "string"})
        assert_json_type(response, (str, int), path="value")

    def test_type_mismatch(self) -> None:
        response = create_response(json_data={"count": 42})
        with pytest.raises(AssertionError, match="Expected type"):
            assert_json_type(response, str, path="count")


class TestAssertCustom:
    """Tests for assert_custom."""

    def test_custom_condition_passes(self) -> None:
        response = create_response(json_data={"users": [{"id": 1}, {"id": 2}]})
        assert_custom(response, condition_fn=lambda r: len(r.json()["users"]) >= 2)

    def test_custom_condition_fails(self) -> None:
        response = create_response(json_data={"users": []})
        with pytest.raises(AssertionError, match="No users found"):
            assert_custom(
                response,
                condition_fn=lambda r: len(r.json()["users"]) > 0,
                message="No users found",
            )


class TestAssertJsonSchema:
    """Tests for assert_json_schema."""

    def test_valid_schema(self) -> None:
        pytest.importorskip("jsonschema")
        schema = {
            "type": "object",
            "required": ["id", "name"],
            "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        }
        response = create_response(json_data={"id": 1, "name": "John"})
        assert_json_schema(response, schema)

    def test_invalid_schema_missing_required(self) -> None:
        pytest.importorskip("jsonschema")
        schema = {
            "type": "object",
            "required": ["id", "name"],
        }
        response = create_response(json_data={"id": 1})
        with pytest.raises(AssertionError):
            assert_json_schema(response, schema)

    def test_invalid_schema_wrong_type(self) -> None:
        pytest.importorskip("jsonschema")
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}
        response = create_response(json_data={"id": "not an integer"})
        with pytest.raises(AssertionError):
            assert_json_schema(response, schema)
