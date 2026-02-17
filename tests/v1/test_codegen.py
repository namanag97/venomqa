"""Unit tests for generate_journey_code (recording codegen)."""

from __future__ import annotations

import pytest

from venomqa.v1.recording.codegen import generate_journey_code
from venomqa.v1.recording.recorder import RecordedRequest


def _make_request(
    method: str = "GET",
    path: str = "/items",
    status: int = 200,
    req_body=None,
    resp_body=None,
) -> RecordedRequest:
    return RecordedRequest(
        method=method,
        url=f"http://localhost{path}",
        request_headers={},
        request_body=req_body,
        status_code=status,
        response_headers={},
        response_body=resp_body or {},
        duration_ms=10.0,
    )


class TestGenerateJourneyCodeEmpty:
    def test_empty_list_returns_valid_python(self):
        code = generate_journey_code([])
        assert "Journey" in code
        assert "steps=[]" in code

    def test_empty_uses_journey_name(self):
        code = generate_journey_code([], journey_name="my_journey")
        assert "my_journey" in code


class TestGenerateJourneyCodeSingleRequest:
    def test_get_request(self):
        reqs = [_make_request("GET", "/users", 200)]
        code = generate_journey_code(reqs)
        assert "GET" in code or "get" in code
        assert "/users" in code

    def test_post_request(self):
        reqs = [_make_request("POST", "/users", 201, req_body={"name": "Alice"})]
        code = generate_journey_code(reqs)
        assert "POST" in code or "post" in code
        assert "/users" in code

    def test_delete_request(self):
        reqs = [_make_request("DELETE", "/users/1", 204)]
        code = generate_journey_code(reqs)
        assert "DELETE" in code or "delete" in code

    def test_status_code_appears(self):
        reqs = [_make_request("GET", "/items", 404)]
        code = generate_journey_code(reqs)
        assert "404" in code


class TestGenerateJourneyCodeMultipleRequests:
    def test_multiple_actions_generated(self):
        reqs = [
            _make_request("GET", "/users", 200),
            _make_request("POST", "/users", 201),
            _make_request("DELETE", "/users/1", 204),
        ]
        code = generate_journey_code(reqs)
        # There should be multiple action functions defined
        action_count = code.count("def ")
        assert action_count >= 3

    def test_journey_name_in_output(self):
        reqs = [_make_request()]
        code = generate_journey_code(reqs, journey_name="dip_journey")
        assert "dip_journey" in code

    def test_base_url_in_header(self):
        reqs = [_make_request()]
        code = generate_journey_code(reqs, base_url="http://api.example.com")
        assert "api.example.com" in code

    def test_output_is_valid_python(self):
        reqs = [
            _make_request("GET", "/items", 200),
            _make_request("POST", "/items", 201, req_body={"name": "x"}),
        ]
        code = generate_journey_code(reqs)
        # Should compile without SyntaxError
        compile(code, "<generated>", "exec")

    def test_journey_import_included(self):
        reqs = [_make_request()]
        code = generate_journey_code(reqs)
        assert "from venomqa" in code or "import" in code


class TestGenerateJourneyCodeStepNames:
    def test_unique_step_names(self):
        reqs = [
            _make_request("GET", "/users", 200),
            _make_request("GET", "/users", 200),  # duplicate
        ]
        code = generate_journey_code(reqs)
        # Both should appear without syntax errors
        compile(code, "<generated>", "exec")

    def test_action_name_derived_from_path(self):
        reqs = [_make_request("GET", "/orders", 200)]
        code = generate_journey_code(reqs)
        # Action name should include something from the path or method
        assert "order" in code.lower() or "get" in code.lower()
