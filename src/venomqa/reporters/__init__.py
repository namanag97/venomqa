"""Reporters module for VenomQA.

Main reporters (recommended):
- ConsoleReporter: Rich terminal output with color
- HTMLTraceReporter: Interactive D3 force graph visualization
- JSONReporter: Structured JSON output
- JUnitReporter: JUnit XML for CI/CD integration
- MarkdownReporter: Human-readable markdown reports
- DimensionCoverageReporter: Hypergraph dimension coverage

Legacy reporters (backwards compatibility):
- HTMLReporter, DashboardReporter, SlackReporter, DiscordReporter, SARIFReporter
"""

from __future__ import annotations

import importlib
import sys

# Main reporters (from v1)
from venomqa.v1.reporters.console import ConsoleReporter
from venomqa.v1.reporters.dimension_report import DimensionCoverageReporter
from venomqa.v1.reporters.html_trace import HTMLTraceReporter
from venomqa.v1.reporters.json import JSONReporter as V1JSONReporter
from venomqa.v1.reporters.junit import JUnitReporter as V1JUnitReporter
from venomqa.v1.reporters.markdown import MarkdownReporter as V1MarkdownReporter

# Legacy reporters
from venomqa.reporters.base import BaseReporter
from venomqa.reporters.dashboard import DashboardReporter
from venomqa.reporters.discord import DiscordReporter
from venomqa.reporters.html import HTMLReporter
from venomqa.reporters.json_report import JSONReporter
from venomqa.reporters.junit import JUnitReporter
from venomqa.reporters.markdown import MarkdownReporter
from venomqa.reporters.sarif import SARIFReporter
from venomqa.reporters.slack import SlackReporter

# Submodule aliasing: allow `from venomqa.reporters.console import ConsoleReporter` etc.
_V1_REPORTER_SUBMODULES = [
    "console", "html_trace", "json", "junit", "markdown", "dimension_report",
]

for _submod in _V1_REPORTER_SUBMODULES:
    _v1_name = f"venomqa.v1.reporters.{_submod}"
    _alias_name = f"venomqa.reporters.{_submod}"
    if _alias_name not in sys.modules:
        try:
            _mod = importlib.import_module(_v1_name)
            sys.modules[_alias_name] = _mod
        except ImportError:
            pass

__all__ = [
    # Main reporters
    "ConsoleReporter",
    "HTMLTraceReporter",
    "V1JSONReporter",
    "V1JUnitReporter",
    "V1MarkdownReporter",
    "DimensionCoverageReporter",
    # Legacy reporters
    "BaseReporter",
    "DashboardReporter",
    "DiscordReporter",
    "HTMLReporter",
    "JSONReporter",
    "JUnitReporter",
    "MarkdownReporter",
    "SARIFReporter",
    "SlackReporter",
]
