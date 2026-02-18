"""Tests for venomqa.autonomous.auth_detection module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from venomqa.autonomous.auth_detection import (
    AuthRequirement,
    check_auth_configured,
    detect_auth_from_openapi,
)
from venomqa.autonomous.credentials import AuthType, Credentials


class TestDetectAuthFromOpenapi:
    """Tests for detect_auth_from_openapi function."""

    def test_no_security_schemes(self):
        """Test spec with no security schemes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_file = Path(tmpdir) / "openapi.yaml"
            spec_file.write_text("""
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
paths: {}
""")
            requirements = detect_auth_from_openapi(spec_file)
            assert requirements == []

    def test_api_key_auth(self):
        """Test detection of API key auth."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_file = Path(tmpdir) / "openapi.yaml"
            spec_file.write_text("""
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
components:
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
paths: {}
""")
            requirements = detect_auth_from_openapi(spec_file)
            assert len(requirements) == 1
            assert requirements[0].auth_type == "apiKey"
            assert requirements[0].header_name == "X-API-Key"
            assert requirements[0].location == "header"

    def test_bearer_auth(self):
        """Test detection of Bearer token auth."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_file = Path(tmpdir) / "openapi.yaml"
            spec_file.write_text("""
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
paths: {}
""")
            requirements = detect_auth_from_openapi(spec_file)
            assert len(requirements) == 1
            assert requirements[0].auth_type == "http"
            assert requirements[0].scheme == "bearer"

    def test_basic_auth(self):
        """Test detection of Basic auth."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_file = Path(tmpdir) / "openapi.yaml"
            spec_file.write_text("""
openapi: 3.0.0
info:
  title: Test API
  version: 1.0.0
components:
  securitySchemes:
    BasicAuth:
      type: http
      scheme: basic
paths: {}
""")
            requirements = detect_auth_from_openapi(spec_file)
            assert len(requirements) == 1
            assert requirements[0].auth_type == "http"
            assert requirements[0].scheme == "basic"

    def test_swagger_2_security_definitions(self):
        """Test detection from Swagger 2.0 securityDefinitions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec_file = Path(tmpdir) / "swagger.yaml"
            spec_file.write_text("""
swagger: "2.0"
info:
  title: Test API
  version: 1.0.0
securityDefinitions:
  api_key:
    type: apiKey
    name: Authorization
    in: header
paths: {}
""")
            requirements = detect_auth_from_openapi(spec_file)
            assert len(requirements) == 1
            assert requirements[0].auth_type == "apiKey"

    def test_nonexistent_file(self):
        """Test handling of nonexistent file."""
        requirements = detect_auth_from_openapi(Path("/nonexistent/file.yaml"))
        assert requirements == []


class TestAuthRequirement:
    """Tests for AuthRequirement class."""

    def test_api_key_fix_instructions(self):
        """Test fix instructions for API key auth."""
        req = AuthRequirement(
            auth_type="apiKey",
            name="ApiKeyAuth",
            location="header",
            header_name="X-API-Key",
        )
        instructions = req.get_fix_instructions()
        assert "--api-key" in instructions

    def test_bearer_fix_instructions(self):
        """Test fix instructions for Bearer auth."""
        req = AuthRequirement(
            auth_type="http",
            name="BearerAuth",
            scheme="bearer",
        )
        instructions = req.get_fix_instructions()
        assert "--auth-token" in instructions

    def test_basic_fix_instructions(self):
        """Test fix instructions for Basic auth."""
        req = AuthRequirement(
            auth_type="http",
            name="BasicAuth",
            scheme="basic",
        )
        instructions = req.get_fix_instructions()
        assert "--basic-auth" in instructions


class TestCheckAuthConfigured:
    """Tests for check_auth_configured function."""

    def test_no_requirements(self):
        """Test when no auth is required."""
        ok, msg = check_auth_configured([], None)
        assert ok is True
        assert msg is None

    def test_requirements_with_credentials(self):
        """Test when auth required and credentials provided."""
        requirements = [AuthRequirement(
            auth_type="apiKey",
            name="ApiKeyAuth",
            location="header",
            header_name="X-API-Key",
        )]
        creds = Credentials(auth_type=AuthType.API_KEY, api_key="test-key")
        ok, msg = check_auth_configured(requirements, creds)
        assert ok is True
        assert msg is None

    def test_requirements_without_credentials(self):
        """Test when auth required but no credentials."""
        requirements = [AuthRequirement(
            auth_type="apiKey",
            name="ApiKeyAuth",
            location="header",
            header_name="X-API-Key",
        )]
        ok, msg = check_auth_configured(requirements, None)
        assert ok is False
        assert msg is not None
        assert "--api-key" in msg

    def test_requirements_with_empty_credentials(self):
        """Test when auth required but credentials have no auth."""
        requirements = [AuthRequirement(
            auth_type="apiKey",
            name="ApiKeyAuth",
            location="header",
            header_name="X-API-Key",
        )]
        creds = Credentials()  # No auth configured
        ok, msg = check_auth_configured(requirements, creds)
        assert ok is False
        assert msg is not None
