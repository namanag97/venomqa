"""Reporting Context - Communicating exploration findings.

The Reporting context is responsible for:
- Formatting exploration results for different outputs
- Creating bug reports with reproduction paths
- Generating test artifacts (JSON, JUnit, HTML, etc.)

Core abstractions:
- Reporter: Protocol for formatting exploration results
- ConsoleReporter: Terminal output with colors
- JSONReporter: Machine-readable JSON format
- HTMLTraceReporter: Interactive HTML visualization
- JUnitReporter: CI-compatible XML format
- MarkdownReporter: Human-readable markdown
"""

from venomqa.reporting.protocol import Reporter
from venomqa.reporting.console import ConsoleReporter

# Re-export other reporters from v1 (to be migrated later)
from venomqa.v1.reporters.json import JSONReporter
from venomqa.v1.reporters.junit import JUnitReporter
from venomqa.v1.reporters.markdown import MarkdownReporter
from venomqa.v1.reporters.html_trace import HTMLTraceReporter
from venomqa.v1.reporters.dimension_report import DimensionCoverageReporter

__all__ = [
    # Protocol
    "Reporter",
    # Implementations
    "ConsoleReporter",
    "JSONReporter",
    "JUnitReporter",
    "MarkdownReporter",
    "HTMLTraceReporter",
    "DimensionCoverageReporter",
]
