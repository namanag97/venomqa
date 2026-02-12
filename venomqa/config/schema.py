"""JSON Schema definitions for VenomQA configuration validation."""

from __future__ import annotations

from typing import Any

VENOMQA_CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://venomqa.dev/schemas/config.json",
    "title": "VenomQA Configuration",
    "description": "Configuration schema for VenomQA testing framework",
    "type": "object",
    "properties": {
        "base_url": {
            "type": "string",
            "format": "uri",
            "description": "Base URL for the application under test",
            "default": "http://localhost:8000",
            "examples": [
                "http://localhost:3000",
                "https://api.example.com",
                "https://staging.example.com",
            ],
        },
        "db_url": {
            "type": "string",
            "pattern": "^postgresql://.*|^postgres://.*$",
            "description": "PostgreSQL connection string for database state management",
            "examples": [
                "postgresql://user:password@localhost:5432/venomqa_test",
                "postgres://qa:secret@db:5432/testdb",
            ],
        },
        "db_backend": {
            "type": "string",
            "enum": ["postgresql", "mysql", "sqlite"],
            "default": "postgresql",
            "description": "Database backend type",
        },
        "docker_compose_file": {
            "type": "string",
            "default": "docker-compose.qa.yml",
            "description": "Path to Docker Compose file for test infrastructure",
            "examples": ["docker-compose.qa.yml", "infra/docker-compose.test.yml"],
        },
        "timeout": {
            "type": "integer",
            "minimum": 1,
            "maximum": 3600,
            "default": 30,
            "description": "Default timeout in seconds for HTTP requests",
        },
        "retry": {
            "type": "object",
            "description": "Retry configuration for failed requests",
            "properties": {
                "max_attempts": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 3,
                    "description": "Maximum number of retry attempts",
                },
                "delay": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 60,
                    "default": 1.0,
                    "description": "Initial delay between retries in seconds",
                },
                "backoff_multiplier": {
                    "type": "number",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 2,
                    "description": "Multiplier for exponential backoff",
                },
            },
            "additionalProperties": False,
        },
        "retry_count": {
            "type": "integer",
            "minimum": 0,
            "maximum": 10,
            "default": 3,
            "description": "Number of retry attempts (deprecated: use retry.max_attempts)",
        },
        "retry_delay": {
            "type": "number",
            "minimum": 0,
            "maximum": 60,
            "default": 1.0,
            "description": "Delay between retries in seconds (deprecated: use retry.delay)",
        },
        "capture_logs": {
            "type": "boolean",
            "default": True,
            "description": "Whether to capture logs from Docker containers on failure",
        },
        "log_lines": {
            "type": "integer",
            "minimum": 10,
            "maximum": 10000,
            "default": 50,
            "description": "Number of log lines to capture on failure",
        },
        "parallel_paths": {
            "type": "integer",
            "minimum": 1,
            "maximum": 32,
            "default": 1,
            "description": "Number of parallel test paths to execute",
        },
        "report": {
            "type": "object",
            "description": "Reporting configuration",
            "properties": {
                "formats": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["markdown", "json", "junit", "html"],
                    },
                    "minItems": 1,
                    "default": ["markdown"],
                    "description": "Report output formats",
                },
                "output_dir": {
                    "type": "string",
                    "default": "reports",
                    "description": "Directory for report output files",
                },
                "filename_prefix": {
                    "type": "string",
                    "default": "venomqa-report",
                    "description": "Prefix for generated report filenames",
                },
                "include_timestamp": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include timestamp in report filename",
                },
            },
            "additionalProperties": False,
        },
        "report_dir": {
            "type": "string",
            "default": "reports",
            "description": "Directory for report output (deprecated: use report.output_dir)",
        },
        "report_formats": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["markdown", "json", "junit", "html"],
            },
            "minItems": 1,
            "default": ["markdown"],
            "description": "Report formats (deprecated: use report.formats)",
        },
        "verbose": {
            "type": "boolean",
            "default": False,
            "description": "Enable verbose output",
        },
        "fail_fast": {
            "type": "boolean",
            "default": False,
            "description": "Stop execution on first failure",
        },
        "profile": {
            "type": "string",
            "enum": ["dev", "staging", "prod", "test"],
            "description": "Configuration profile to use",
        },
        "profiles": {
            "type": "object",
            "description": "Profile-specific configuration overrides",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "base_url": {"type": "string"},
                    "timeout": {"type": "integer"},
                    "verbose": {"type": "boolean"},
                    "fail_fast": {"type": "boolean"},
                    "report": {"type": "object"},
                },
            },
        },
        "env": {
            "type": "object",
            "description": "Environment variable interpolation mapping",
            "additionalProperties": {"type": "string"},
            "examples": [
                {
                    "BASE_URL": "${APP_BASE_URL}",
                    "DB_URL": "${DATABASE_URL}",
                }
            ],
        },
    },
    "additionalProperties": False,
}

PROFILE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://venomqa.dev/schemas/profile.json",
    "title": "VenomQA Profile Configuration",
    "description": "Profile-specific configuration overrides",
    "type": "object",
    "properties": {
        "base_url": {"type": "string", "format": "uri"},
        "timeout": {"type": "integer", "minimum": 1, "maximum": 3600},
        "verbose": {"type": "boolean"},
        "fail_fast": {"type": "boolean"},
        "capture_logs": {"type": "boolean"},
        "parallel_paths": {"type": "integer", "minimum": 1, "maximum": 32},
        "report": {
            "type": "object",
            "properties": {
                "formats": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["markdown", "json", "junit", "html"]},
                },
                "output_dir": {"type": "string"},
            },
        },
        "retry": {
            "type": "object",
            "properties": {
                "max_attempts": {"type": "integer", "minimum": 1},
                "delay": {"type": "number", "minimum": 0},
                "backoff_multiplier": {"type": "number", "minimum": 1},
            },
        },
    },
    "additionalProperties": False,
}


def get_schema() -> dict[str, Any]:
    """Return the VenomQA configuration schema."""
    return VENOMQA_CONFIG_SCHEMA.copy()


def get_profile_schema() -> dict[str, Any]:
    """Return the profile configuration schema."""
    return PROFILE_SCHEMA.copy()


def get_default_config() -> dict[str, Any]:
    """Return default configuration values from schema."""
    return {
        "base_url": "http://localhost:8000",
        "db_backend": "postgresql",
        "docker_compose_file": "docker-compose.qa.yml",
        "timeout": 30,
        "retry": {
            "max_attempts": 3,
            "delay": 1.0,
            "backoff_multiplier": 2,
        },
        "capture_logs": True,
        "log_lines": 50,
        "parallel_paths": 1,
        "report": {
            "formats": ["markdown"],
            "output_dir": "reports",
            "filename_prefix": "venomqa-report",
            "include_timestamp": True,
        },
        "verbose": False,
        "fail_fast": False,
    }


def get_config_examples() -> dict[str, dict[str, Any]]:
    """Return example configurations for common use cases."""
    return {
        "development": {
            "base_url": "http://localhost:3000",
            "timeout": 60,
            "verbose": True,
            "capture_logs": True,
            "report": {
                "formats": ["markdown", "html"],
                "output_dir": "./reports",
            },
        },
        "staging": {
            "base_url": "https://staging.example.com",
            "timeout": 30,
            "verbose": False,
            "fail_fast": False,
            "report": {
                "formats": ["junit", "json"],
                "output_dir": "/var/lib/venomqa/reports",
            },
        },
        "production": {
            "base_url": "https://api.example.com",
            "timeout": 15,
            "verbose": False,
            "fail_fast": True,
            "parallel_paths": 4,
            "report": {
                "formats": ["junit"],
                "output_dir": "/var/lib/venomqa/reports",
            },
        },
        "ci": {
            "base_url": "${CI_BASE_URL}",
            "db_url": "${DATABASE_URL}",
            "timeout": 30,
            "verbose": False,
            "fail_fast": True,
            "parallel_paths": 2,
            "report": {
                "formats": ["junit", "json"],
                "output_dir": "./test-results",
            },
        },
    }
