"""Reporters module for VenomQA.

Provides multiple report formats for test results:
- MarkdownReporter: Human-readable reports
- JSONReporter: Structured JSON output
- JUnitReporter: JUnit XML for CI/CD integration
- HTMLReporter: Beautiful HTML reports with charts
- SlackReporter: Slack webhook notifications
- DiscordReporter: Discord webhook notifications
- SARIFReporter: SARIF format for GitHub Code Scanning
"""

from venomqa.reporters.base import BaseReporter
from venomqa.reporters.discord import DiscordReporter
from venomqa.reporters.html import HTMLReporter
from venomqa.reporters.json_report import JSONReporter
from venomqa.reporters.junit import JUnitReporter
from venomqa.reporters.markdown import MarkdownReporter
from venomqa.reporters.sarif import SARIFReporter
from venomqa.reporters.slack import SlackReporter

__all__ = [
    "BaseReporter",
    "DiscordReporter",
    "HTMLReporter",
    "JSONReporter",
    "JUnitReporter",
    "MarkdownReporter",
    "SARIFReporter",
    "SlackReporter",
]
