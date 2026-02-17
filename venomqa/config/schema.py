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
                "max_delay": {
                    "type": "number",
                    "minimum": 1,
                    "maximum": 300,
                    "default": 30.0,
                    "description": "Maximum delay between retries in seconds",
                },
                "retry_on_status": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 100, "maximum": 599},
                    "default": [429, 500, 502, 503, 504],
                    "description": "HTTP status codes to retry on",
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
                "include_request_response": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include request/response data in reports (may contain sensitive data)",
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
        "results_database": {
            "type": "string",
            "description": "Database URL for storing journey results history",
            "default": "sqlite:///venomqa_results.db",
            "examples": [
                "sqlite:///venomqa_results.db",
                "sqlite:///./reports/history.db",
            ],
        },
        "persist_results": {
            "type": "boolean",
            "description": "Whether to automatically persist journey results",
            "default": False,
        },
        "ports": {
            "type": "array",
            "description": "Port configurations for dependency injection",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Port name for reference in code",
                    },
                    "adapter_type": {
                        "type": "string",
                        "description": "Type of adapter (e.g., postgres, redis, time)",
                    },
                    "config": {
                        "type": "object",
                        "description": "Adapter-specific configuration",
                        "additionalProperties": True,
                    },
                },
                "required": ["name", "adapter_type"],
            },
            "default": [],
        },
        "notifications": {
            "type": "object",
            "description": "Notification configuration for test results",
            "properties": {
                "channels": {
                    "type": "array",
                    "description": "Notification channel configurations",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["slack", "discord", "email", "webhook"],
                                "description": "Notification channel type",
                            },
                            "name": {
                                "type": "string",
                                "description": "Channel name for identification",
                            },
                            "webhook_url": {
                                "type": "string",
                                "description": "Webhook URL for the notification",
                            },
                            "on": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": ["failure", "success", "recovery", "info"],
                                },
                                "description": "Events that trigger notifications",
                            },
                        },
                        "required": ["type", "name"],
                    },
                },
            },
            "additionalProperties": True,
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
    """Return default configuration values from schema.

    These defaults are designed to be production-ready while still
    being developer-friendly out of the box.

    Production considerations built in:
    - Reasonable timeouts (30s default, not too long for CI)
    - Retry with exponential backoff
    - Structured logging capture
    - Parallel execution disabled by default (safer)
    - JUnit output for CI integration

    Returns:
        dict with all default configuration values
    """
    return {
        # API Connection
        "base_url": "http://localhost:8000",
        "timeout": 30,  # 30s is reasonable for most APIs

        # Database (optional but recommended for state branching)
        "db_backend": "postgresql",
        "docker_compose_file": "docker-compose.qa.yml",

        # Retry configuration with exponential backoff
        # These defaults handle transient failures gracefully
        "retry": {
            "max_attempts": 3,
            "delay": 1.0,  # Start with 1s delay
            "backoff_multiplier": 2,  # 1s, 2s, 4s
            "max_delay": 30.0,  # Cap at 30s between retries
            "retry_on_status": [429, 500, 502, 503, 504],  # Retryable HTTP codes
        },

        # Logging and debugging
        "capture_logs": True,
        "log_lines": 100,  # Increased for better debugging
        "verbose": False,

        # Execution behavior
        "parallel_paths": 1,  # Sequential by default (safer)
        "fail_fast": False,  # See all failures by default

        # Reporting - include JUnit for CI by default
        "report": {
            "formats": ["markdown", "junit"],  # JUnit for CI
            "output_dir": "reports",
            "filename_prefix": "venomqa-report",
            "include_timestamp": True,
            "include_request_response": False,  # Privacy by default
        },

        # Results persistence
        "results_database": "sqlite:///venomqa_results.db",
        "persist_results": False,

        # Circuit breaker defaults (enterprise feature)
        "circuit_breaker": {
            "enabled": True,
            "failure_threshold": 5,  # Open after 5 consecutive failures
            "reset_timeout": 60,  # Wait 60s before trying again
            "half_open_requests": 1,  # Test with 1 request
        },

        # Rate limiting protection
        "rate_limit": {
            "enabled": True,
            "requests_per_second": 10,  # Reasonable default
            "burst_size": 20,
        },

        # Connection pooling for performance
        "connection_pool": {
            "max_connections": 10,
            "max_keepalive_connections": 5,
            "keepalive_expiry": 30,
        },
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
