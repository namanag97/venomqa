"""Security module for VenomQA - validation, secrets management, sanitization, and testing.

This module provides comprehensive security utilities for:
    - Input validation and sanitization
    - Secrets management with multiple backends
    - SQL injection and XSS prevention
    - Security testing and vulnerability scanning

Example:
    >>> from venomqa.security import InputValidator, SecurityTester
    >>> validator = InputValidator()
    >>> tester = SecurityTester()
"""

from venomqa.security.sanitization import (
    SanitizationError,
    SanitizationResult,
    Sanitizer,
    SensitiveDataFilter,
)
from venomqa.security.secrets import (
    CachedSecret,
    EnvironmentBackend,
    SecretBackend,
    SecretNotFoundError,
    SecretsError,
    SecretsManager,
    VaultBackend,
    VaultConnectionError,
)
from venomqa.security.testing import (
    AuthBypassPayloads,
    CommandInjectionPayloads,
    IDORTester,
    LDAPInjectionPayloads,
    OpenRedirectPayloads,
    PathTraversalPayloads,
    RateLimitTester,
    SecurityTester,
    SecurityTestResult,
    SQLInjectionPayloads,
    SSRFPPayloads,
    VulnerabilityFinding,
    VulnerabilitySeverity,
    VulnerabilityType,
    XSSPayloads,
    XXEPayloads,
)
from venomqa.security.validation import (
    InputValidationError,
    InputValidator,
    ValidationResult,
    ValidationRule,
)

__all__ = [
    "InputValidator",
    "InputValidationError",
    "ValidationRule",
    "ValidationResult",
    "SecretsManager",
    "SecretsError",
    "SecretNotFoundError",
    "VaultConnectionError",
    "SecretBackend",
    "CachedSecret",
    "VaultBackend",
    "EnvironmentBackend",
    "Sanitizer",
    "SanitizationError",
    "SanitizationResult",
    "SensitiveDataFilter",
    "SecurityTester",
    "SecurityTestResult",
    "VulnerabilityFinding",
    "VulnerabilityType",
    "VulnerabilitySeverity",
    "SQLInjectionPayloads",
    "XSSPayloads",
    "PathTraversalPayloads",
    "CommandInjectionPayloads",
    "LDAPInjectionPayloads",
    "AuthBypassPayloads",
    "SSRFPPayloads",
    "OpenRedirectPayloads",
    "XXEPayloads",
    "IDORTester",
    "RateLimitTester",
]
