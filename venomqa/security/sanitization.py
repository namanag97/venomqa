"""Sanitization utilities for SQL injection and XSS prevention."""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SanitizationError(Exception):
    """Raised when sanitization fails."""

    pass


@dataclass
class SanitizationResult:
    """Result of a sanitization operation."""

    original: str
    sanitized: str
    was_modified: bool = False
    warnings: list[str] = field(default_factory=list)


class Sanitizer:
    """SQL injection and XSS prevention sanitizer."""

    SQL_KEYWORDS = frozenset(
        [
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "TRUNCATE",
            "ALTER",
            "CREATE",
            "EXEC",
            "EXECUTE",
            "UNION",
            "JOIN",
            "WHERE",
            "FROM",
            "INTO",
            "ORDER",
            "GROUP",
            "HAVING",
            "LIMIT",
            "OFFSET",
            "VALUES",
            "SET",
        ]
    )

    SQL_INJECTION_PATTERNS = [
        (r"['\"].*?(?:OR|AND)\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+", "SQL injection pattern detected"),
        (r";\s*(?:DROP|DELETE|UPDATE|INSERT|CREATE|ALTER)", "SQL statement injection"),
        (r"--\s*$", "SQL comment injection"),
        (r"/\*.*?\*/", "SQL comment block"),
        (r"UNION\s+(?:ALL\s+)?SELECT", "UNION injection"),
        (r"(?:OR|AND)\s+1\s*=\s*1", "Boolean injection"),
        (r"(?:OR|AND)\s+['\"][^'\"]*['\"]\s*=\s*['\"][^'\"]*['\"]", "String injection"),
        (r"xp_cmdshell", "System command injection"),
        (r"INTO\s+OUTFILE", "File injection"),
        (r"LOAD_FILE", "File read injection"),
    ]

    XSS_PATTERNS = [
        (r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "Script tag"),
        (r"javascript\s*:", "JavaScript protocol"),
        (r"on(?:error|load|click|mouse|focus|blur|key|submit|change)\s*=", "Event handler"),
        (r"<\s*iframe", "Iframe injection"),
        (r"<\s*object", "Object injection"),
        (r"<\s*embed", "Embed injection"),
        (r"<\s*form", "Form injection"),
        (r"expression\s*\(", "CSS expression"),
        (r"vbscript\s*:", "VBScript protocol"),
        (r"data\s*:\s*text/html", "Data URL injection"),
    ]

    IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")

    def __init__(
        self,
        strict_mode: bool = True,
        max_sql_identifier_length: int = 64,
        max_string_length: int = 10000,
    ) -> None:
        self.strict_mode = strict_mode
        self.max_sql_identifier_length = max_sql_identifier_length
        self.max_string_length = max_string_length

    def sanitize_sql_identifier(self, identifier: str) -> SanitizationResult:
        """Sanitize a SQL identifier (table name, column name)."""
        warnings = []
        original = identifier

        sanitized = identifier.strip()

        if not sanitized:
            raise SanitizationError("SQL identifier cannot be empty")

        if len(sanitized) > self.max_sql_identifier_length:
            sanitized = sanitized[: self.max_sql_identifier_length]
            warnings.append(f"Identifier truncated to {self.max_sql_identifier_length} characters")

        upper_sanitized = sanitized.upper()
        if upper_sanitized in self.SQL_KEYWORDS:
            raise SanitizationError(f"SQL identifier cannot be a reserved keyword: {sanitized}")

        if not self.IDENTIFIER_PATTERN.match(sanitized):
            sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", sanitized)
            if sanitized and sanitized[0].isdigit():
                sanitized = "_" + sanitized
            warnings.append("Identifier contained invalid characters, replaced with underscores")

        if not self.IDENTIFIER_PATTERN.match(sanitized):
            raise SanitizationError(f"Cannot sanitize SQL identifier: {original}")

        return SanitizationResult(
            original=original,
            sanitized=sanitized,
            was_modified=original != sanitized,
            warnings=warnings,
        )

    def sanitize_sql_value(self, value: Any, quote_char: str = "'") -> str:
        """Sanitize a SQL value for safe embedding in queries."""
        if value is None:
            return "NULL"

        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"

        if isinstance(value, (int, float)):
            return str(value)

        str_value = str(value)

        if len(str_value) > self.max_string_length:
            str_value = str_value[: self.max_string_length]
            logger.warning(f"SQL value truncated to {self.max_string_length} characters")

        for pattern, description in self.SQL_INJECTION_PATTERNS:
            if re.search(pattern, str_value, re.IGNORECASE):
                if self.strict_mode:
                    raise SanitizationError(f"Potential SQL injection detected: {description}")
                logger.warning(f"Potential SQL injection pattern: {description}")

        escaped = str_value.replace(quote_char, quote_char + quote_char)
        escaped = escaped.replace("\\", "\\\\")

        return f"{quote_char}{escaped}{quote_char}"

    def check_sql_injection(self, value: str) -> tuple[bool, list[str]]:
        """Check a string for potential SQL injection patterns."""
        detected = []
        is_safe = True

        for pattern, description in self.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                detected.append(description)
                is_safe = False

        return is_safe, detected

    def sanitize_url(
        self, url: str, allowed_schemes: list[str] | None = None
    ) -> SanitizationResult:
        """Sanitize a URL for safe use."""
        warnings = []
        original = url

        if not url:
            raise SanitizationError("URL cannot be empty")

        sanitized = url.strip()

        schemes = allowed_schemes or ["http", "https"]

        try:
            parsed = urlparse(sanitized)
        except Exception as e:
            raise SanitizationError(f"Invalid URL format: {e}") from e

        if parsed.scheme.lower() not in schemes:
            dangerous_schemes = ["javascript", "vbscript", "data", "file"]
            if parsed.scheme.lower() in dangerous_schemes:
                raise SanitizationError(f"Dangerous URL scheme detected: {parsed.scheme}")
            warnings.append(f"URL scheme '{parsed.scheme}' not in allowed list: {schemes}")

        if not parsed.netloc and parsed.scheme:
            warnings.append("URL has scheme but no host")

        for pattern, description in self.XSS_PATTERNS:
            if re.search(pattern, sanitized, re.IGNORECASE):
                raise SanitizationError(f"Potential XSS in URL: {description}")

        return SanitizationResult(
            original=original,
            sanitized=sanitized,
            was_modified=original != sanitized,
            warnings=warnings,
        )

    def sanitize_html(self, value: str, allowed_tags: list[str] | None = None) -> str:
        """Sanitize HTML content, removing dangerous elements."""
        if not value:
            return ""

        allowed = set(allowed_tags or [])

        sanitized = value

        for pattern, _description in self.XSS_PATTERNS:
            sanitized = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)

        if not allowed:
            sanitized = html.escape(sanitized)
        else:
            tag_pattern = re.compile(r"<\s*/?([a-zA-Z0-9]+)[^>]*>")

            def replace_tag(match: re.Match) -> str:
                tag_name = match.group(1).lower()
                if tag_name in allowed:
                    return match.group(0)
                return ""

            sanitized = tag_pattern.sub(replace_tag, sanitized)

        return sanitized

    def check_xss(self, value: str) -> tuple[bool, list[str]]:
        """Check a string for potential XSS patterns."""
        detected = []
        is_safe = True

        for pattern, description in self.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                detected.append(description)
                is_safe = False

        return is_safe, detected

    def sanitize_for_log(self, value: str, max_length: int = 500) -> str:
        """Sanitize a value for safe logging."""
        if not value:
            return ""

        sanitized = value[:max_length]

        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", sanitized)

        sanitized = sanitized.replace("\n", "\\n").replace("\r", "\\r")

        for pattern, _ in self.SQL_INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)

        for pattern, _ in self.XSS_PATTERNS:
            sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)

        return sanitized

    def sanitize_path(self, path: str, allow_absolute: bool = False) -> SanitizationResult:
        """Sanitize a file path to prevent directory traversal."""
        warnings = []
        original = path

        if not path:
            raise SanitizationError("Path cannot be empty")

        sanitized = path.strip()

        if ".." in sanitized:
            raise SanitizationError("Path traversal detected: '..' not allowed")

        if not allow_absolute and sanitized.startswith("/"):
            warnings.append("Absolute path converted to relative")
            sanitized = sanitized.lstrip("/")

        dangerous_chars = ["\x00", "|", ";", "&", "$", "`", "(", ")", "<", ">"]
        for char in dangerous_chars:
            if char in sanitized:
                sanitized = sanitized.replace(char, "")
                warnings.append("Removed dangerous character from path")

        control_chars = re.compile(r"[\x00-\x1f\x7f]")
        sanitized = control_chars.sub("", sanitized)

        return SanitizationResult(
            original=original,
            sanitized=sanitized,
            was_modified=original != sanitized,
            warnings=warnings,
        )

    def sanitize_json_key(self, key: str) -> str:
        """Sanitize a JSON key."""
        sanitized = key.strip()

        sanitized = re.sub(r"[^\w\-.]", "_", sanitized)

        if sanitized and sanitized[0].isdigit():
            sanitized = "_" + sanitized

        return sanitized

    def sanitize_dict_values(
        self,
        data: dict[str, Any],
        sensitive_keys: set[str] | None = None,
        redaction: str = "[REDACTED]",
    ) -> dict[str, Any]:
        """Sanitize a dictionary, redacting sensitive values."""
        sensitive = sensitive_keys or {
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
            "credential",
            "private_key",
            "access_key",
            "auth",
        }

        result = {}
        for key, value in data.items():
            key_lower = key.lower()

            if any(s in key_lower for s in sensitive):
                result[key] = redaction
            elif isinstance(value, dict):
                result[key] = self.sanitize_dict_values(value, sensitive, redaction)
            elif isinstance(value, str):
                safe, patterns = self.check_xss(value)
                if not safe:
                    result[key] = self.sanitize_html(value)
                else:
                    result[key] = value
            else:
                result[key] = value

        return result


class SensitiveDataFilter(logging.Filter):
    """Logging filter that redacts sensitive data."""

    DEFAULT_PATTERNS = [
        (
            re.compile(r"(password|passwd|pwd)[\'\"]?\s*[:=]\s*[\'\"]?([^\s\'\"]+)", re.IGNORECASE),
            r"\1=***REDACTED***",
        ),
        (
            re.compile(
                r"(token|api_key|apikey|secret)[\'\"]?\s*[:=]\s*[\'\"]?([^\s\'\"]+)", re.IGNORECASE
            ),
            r"\1=***REDACTED***",
        ),
        (
            re.compile(r"(bearer|basic)\s+[a-zA-Z0-9\-._~+/]+=*", re.IGNORECASE),
            r"\1 ***REDACTED***",
        ),
        (re.compile(r"postgresql://[^:]+:([^@]+)@", re.IGNORECASE), r"postgresql://***:***@"),
        (re.compile(r"mysql://[^:]+:([^@]+)@", re.IGNORECASE), r"mysql://***:***@"),
        (re.compile(r"redis://[^:]*:([^@]+)@", re.IGNORECASE), r"redis://***:***@"),
    ]

    def __init__(
        self,
        additional_patterns: list[tuple[re.Pattern, str]] | None = None,
        custom_redactor: callable | None = None,
    ) -> None:
        super().__init__()
        self.patterns = list(self.DEFAULT_PATTERNS)
        self.custom_redactor = custom_redactor

        if additional_patterns:
            self.patterns.extend(additional_patterns)

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter and redact sensitive data from log records."""
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self._redact(record.msg)

        if hasattr(record, "args") and record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: self._redact(str(v)) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._redact(str(arg)) if isinstance(arg, str) else arg for arg in record.args
                )

        return True

    def _redact(self, message: str) -> str:
        """Redact sensitive patterns from a message."""
        if self.custom_redactor:
            message = self.custom_redactor(message)

        for pattern, replacement in self.patterns:
            message = pattern.sub(replacement, message)

        return message

    def add_pattern(self, pattern: re.Pattern, replacement: str) -> None:
        """Add a custom redaction pattern."""
        self.patterns.append((pattern, replacement))
