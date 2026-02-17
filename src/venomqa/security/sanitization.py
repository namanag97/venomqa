"""Sanitization utilities for SQL injection and XSS prevention.

This module provides comprehensive sanitization utilities for protecting
against common injection attacks including SQL injection, XSS, and path traversal.

Example:
    >>> from venomqa.security.sanitization import Sanitizer
    >>> sanitizer = Sanitizer(strict_mode=True)
    >>> result = sanitizer.sanitize_sql_identifier("users; DROP TABLE users;")
    >>> print(result.sanitized)
    users_DROP_TABLE_users_
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SanitizationError(Exception):
    """Raised when sanitization fails.

    This exception is raised when input cannot be safely sanitized,
    typically when the input contains dangerous patterns that cannot
    be automatically removed or escaped.

    Example:
        >>> raise SanitizationError("SQL identifier cannot be empty")
    """

    pass


@dataclass
class SanitizationResult:
    """Result of a sanitization operation.

    Contains information about the original input, the sanitized output,
    whether modifications were made, and any warnings generated.

    Attributes:
        original: The original input string before sanitization.
        sanitized: The sanitized output string.
        was_modified: Whether the input was modified during sanitization.
        warnings: List of warning messages generated during sanitization.

    Example:
        >>> result = SanitizationResult(
        ...     original="test; DROP",
        ...     sanitized="test_DROP",
        ...     was_modified=True,
        ...     warnings=["Replaced dangerous character"]
        ... )
    """

    original: str
    sanitized: str
    was_modified: bool = False
    warnings: list[str] = field(default_factory=list)


class Sanitizer:
    """SQL injection and XSS prevention sanitizer.

    This class provides comprehensive sanitization methods for protecting
    against various injection attacks. It can operate in strict mode
    (raises exceptions on dangerous input) or non-strict mode (logs warnings).

    Attributes:
        SQL_KEYWORDS: Set of reserved SQL keywords that cannot be used as identifiers.
        SQL_INJECTION_PATTERNS: Patterns for detecting SQL injection attempts.
        XSS_PATTERNS: Patterns for detecting XSS attack attempts.
        IDENTIFIER_PATTERN: Valid pattern for SQL identifiers.

    Example:
        >>> sanitizer = Sanitizer(strict_mode=True)
        >>> result = sanitizer.sanitize_sql_identifier("user_name")
        >>> print(result.sanitized)
        user_name
    """

    SQL_KEYWORDS: Final[frozenset[str]] = frozenset(
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
            "GRANT",
            "REVOKE",
            "COMMIT",
            "ROLLBACK",
            "BEGIN",
            "DECLARE",
            "CURSOR",
            "PROCEDURE",
            "FUNCTION",
            "TRIGGER",
            "INDEX",
            "DATABASE",
            "TABLE",
            "VIEW",
        ]
    )

    SQL_INJECTION_PATTERNS: Final[list[tuple[str, str]]] = [
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
        (r"BENCHMARK\s*\(", "Time-based injection"),
        (r"SLEEP\s*\(", "Time-based injection"),
        (r"WAITFOR\s+DELAY", "Time-based injection (MSSQL)"),
        (r"pg_sleep", "Time-based injection (PostgreSQL)"),
    ]

    XSS_PATTERNS: Final[list[tuple[str, str]]] = [
        (r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", "Script tag"),
        (r"javascript\s*:", "JavaScript protocol"),
        (
            r"on(?:error|load|click|mouse|focus|blur|key|submit|change|input|drag|drop|scroll)\s*=",
            "Event handler",
        ),
        (r"<\s*iframe", "Iframe injection"),
        (r"<\s*object", "Object injection"),
        (r"<\s*embed", "Embed injection"),
        (r"<\s*form", "Form injection"),
        (r"expression\s*\(", "CSS expression"),
        (r"vbscript\s*:", "VBScript protocol"),
        (r"data\s*:\s*text/html", "Data URL injection"),
        (r"<\s*base", "Base tag injection"),
        (r"<\s*link", "Link tag injection"),
        (r"<\s*meta", "Meta tag injection"),
        (r"&#x?[0-9a-f]+;", "HTML entity encoding"),
    ]

    IDENTIFIER_PATTERN: Final[re.Pattern] = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")

    DANGEROUS_URL_SCHEMES: Final[frozenset[str]] = frozenset(
        ["javascript", "vbscript", "data", "file"]
    )

    def __init__(
        self,
        strict_mode: bool = True,
        max_sql_identifier_length: int = 64,
        max_string_length: int = 10000,
    ) -> None:
        """Initialize the sanitizer.

        Args:
            strict_mode: If True, raise exceptions on dangerous input.
                        If False, log warnings and continue.
            max_sql_identifier_length: Maximum length for SQL identifiers.
            max_string_length: Maximum length for string values.
        """
        self.strict_mode = strict_mode
        self.max_sql_identifier_length = max_sql_identifier_length
        self.max_string_length = max_string_length

    def sanitize_sql_identifier(self, identifier: str) -> SanitizationResult:
        """Sanitize a SQL identifier (table name, column name).

        Validates that the identifier is not a reserved keyword and contains
        only valid characters. Invalid characters are replaced with underscores.

        Args:
            identifier: The SQL identifier to sanitize.

        Returns:
            SanitizationResult with the sanitized identifier.

        Raises:
            SanitizationError: If the identifier is empty or cannot be sanitized.

        Example:
            >>> sanitizer.sanitize_sql_identifier("user-name")
            SanitizationResult(original='user-name', sanitized='user_name', ...)
        """
        warnings: list[str] = []
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
        """Sanitize a SQL value for safe embedding in queries.

        Converts the value to an appropriate SQL representation and escapes
        any dangerous characters. For string values, checks for injection patterns.

        Args:
            value: The value to sanitize (any type).
            quote_char: The quote character to use for strings.

        Returns:
            Sanitized SQL value string ready for embedding in queries.

        Raises:
            SanitizationError: If strict mode and potential injection detected.

        Example:
            >>> sanitizer.sanitize_sql_value("test")
            "'test'"
            >>> sanitizer.sanitize_sql_value(None)
            "NULL"
        """
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
        """Check a string for potential SQL injection patterns.

        Scans the input string for known SQL injection patterns without
        modifying the input.

        Args:
            value: The string to check.

        Returns:
            Tuple of (is_safe, list_of_detected_patterns).

        Example:
            >>> is_safe, patterns = sanitizer.check_sql_injection("'; DROP TABLE users;--")
            >>> is_safe
            False
            >>> patterns
            ['SQL statement injection']
        """
        detected: list[str] = []
        is_safe = True

        for pattern, description in self.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                detected.append(description)
                is_safe = False

        return is_safe, detected

    def sanitize_url(
        self, url: str, allowed_schemes: list[str] | None = None
    ) -> SanitizationResult:
        """Sanitize a URL for safe use.

        Validates the URL format, checks for dangerous schemes, and scans
        for XSS patterns in the URL.

        Args:
            url: The URL string to sanitize.
            allowed_schemes: List of allowed URL schemes. Defaults to ['http', 'https'].

        Returns:
            SanitizationResult with the sanitized URL.

        Raises:
            SanitizationError: If URL is empty, malformed, or contains dangerous content.

        Example:
            >>> sanitizer.sanitize_url("https://example.com/path")
            SanitizationResult(original='...', sanitized='...', ...)
        """
        warnings: list[str] = []
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
            if parsed.scheme.lower() in self.DANGEROUS_URL_SCHEMES:
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
        """Sanitize HTML content, removing dangerous elements.

        Removes XSS attack vectors from HTML content while optionally
        preserving safe tags.

        Args:
            value: The HTML string to sanitize.
            allowed_tags: List of HTML tags to preserve. If None, escapes all HTML.

        Returns:
            Sanitized HTML string.

        Example:
            >>> sanitizer.sanitize_html("<script>alert(1)</script>Hello")
            'Hello'
            >>> sanitizer.sanitize_html("<b>Bold</b>", allowed_tags=["b"])
            '<b>Bold</b>'
        """
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
        """Check a string for potential XSS patterns.

        Scans the input string for known XSS attack patterns without
        modifying the input.

        Args:
            value: The string to check.

        Returns:
            Tuple of (is_safe, list_of_detected_patterns).

        Example:
            >>> is_safe, patterns = sanitizer.check_xss("<script>alert(1)</script>")
            >>> is_safe
            False
            >>> patterns
            ['Script tag']
        """
        detected: list[str] = []
        is_safe = True

        for pattern, description in self.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                detected.append(description)
                is_safe = False

        return is_safe, detected

    def sanitize_for_log(self, value: str, max_length: int = 500) -> str:
        """Sanitize a value for safe logging.

        Removes control characters, newlines, and redacts potentially
        dangerous patterns to prevent log injection attacks.

        Args:
            value: The string to sanitize.
            max_length: Maximum length for the output.

        Returns:
            Sanitized string safe for logging.

        Example:
            >>> sanitizer.sanitize_for_log("test\\nFAKE LOG ENTRY")
            'test\\\\nFAKE LOG ENTRY'
        """
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
        """Sanitize a file path to prevent directory traversal.

        Removes path traversal sequences and dangerous characters to
        prevent unauthorized file access.

        Args:
            path: The file path to sanitize.
            allow_absolute: Whether to allow absolute paths.

        Returns:
            SanitizationResult with the sanitized path.

        Raises:
            SanitizationError: If path contains traversal sequences.

        Example:
            >>> sanitizer.sanitize_path("../../etc/passwd")
            SanitizationError: Path traversal detected
        """
        warnings: list[str] = []
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
        """Sanitize a JSON key.

        Converts the key to a valid JSON key format by replacing
        invalid characters with underscores.

        Args:
            key: The JSON key to sanitize.

        Returns:
            Sanitized JSON key string.

        Example:
            >>> sanitizer.sanitize_json_key("user-name")
            'user_name'
            >>> sanitizer.sanitize_json_key("123key")
            '_123key'
        """
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
        """Sanitize a dictionary, redacting sensitive values.

        Recursively processes dictionary values, redacting values whose
        keys match sensitive patterns and sanitizing HTML in string values.

        Args:
            data: The dictionary to sanitize.
            sensitive_keys: Set of key patterns to redact. Defaults to common sensitive keys.
            redaction: The string to use for redacted values.

        Returns:
            New dictionary with sanitized values.

        Example:
            >>> sanitizer.sanitize_dict_values({"password": "secret", "name": "John"})
            {'password': '[REDACTED]', 'name': 'John'}
        """
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
            "session",
            "cookie",
            "authorization",
        }

        result: dict[str, Any] = {}
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
            elif isinstance(value, list):
                result[key] = [
                    self.sanitize_dict_values(v, sensitive, redaction) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                result[key] = value

        return result


class SensitiveDataFilter(logging.Filter):
    """Logging filter that redacts sensitive data.

    This filter automatically redacts sensitive information such as
    passwords, API keys, and connection strings from log records.

    Attributes:
        DEFAULT_PATTERNS: Default patterns for sensitive data detection.

    Example:
        >>> import logging
        >>> handler = logging.StreamHandler()
        >>> handler.addFilter(SensitiveDataFilter())
        >>> logger.addHandler(handler)
    """

    DEFAULT_PATTERNS: Final[list[tuple[re.Pattern, str]]] = [
        (
            re.compile(r"(password|passwd|pwd)[\'\"]?\s*[:=]\s*[\'\"]?([^\s\'\"]+)", re.IGNORECASE),
            r"\1=***REDACTED***",
        ),
        (
            re.compile(
                r"(token|api_key|apikey|secret|access_key)[\'\"]?\s*[:=]\s*[\'\"]?([^\s\'\"]+)",
                re.IGNORECASE,
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
        (re.compile(r"mongodb(\+srv)?://[^:]+:([^@]+)@", re.IGNORECASE), r"mongodb://***:***@"),
        (re.compile(r"amqp://[^:]+:([^@]+)@", re.IGNORECASE), r"amqp://***:***@"),
    ]

    def __init__(
        self,
        additional_patterns: list[tuple[re.Pattern, str]] | None = None,
        custom_redactor: Callable[[str], str] | None = None,
    ) -> None:
        """Initialize the sensitive data filter.

        Args:
            additional_patterns: Additional patterns to redact.
            custom_redactor: Custom function for redacting messages.
        """
        super().__init__()
        self.patterns = list(self.DEFAULT_PATTERNS)
        self.custom_redactor = custom_redactor

        if additional_patterns:
            self.patterns.extend(additional_patterns)

    def filter(self, record: logging.LogRecord) -> bool:
        """Filter and redact sensitive data from log records.

        Args:
            record: The log record to filter.

        Returns:
            Always returns True to allow the record through.
        """
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
        """Redact sensitive patterns from a message.

        Args:
            message: The message to redact.

        Returns:
            Redacted message string.
        """
        if self.custom_redactor:
            message = self.custom_redactor(message)

        for pattern, replacement in self.patterns:
            message = pattern.sub(replacement, message)

        return message

    def add_pattern(self, pattern: re.Pattern, replacement: str) -> None:
        """Add a custom redaction pattern.

        Args:
            pattern: Regex pattern to match.
            replacement: Replacement string for matches.
        """
        self.patterns.append((pattern, replacement))

    def remove_pattern(self, pattern: re.Pattern) -> bool:
        """Remove a redaction pattern.

        Args:
            pattern: The pattern to remove.

        Returns:
            True if pattern was found and removed, False otherwise.
        """
        for i, (p, _) in enumerate(self.patterns):
            if p.pattern == pattern.pattern:
                self.patterns.pop(i)
                return True
        return False
