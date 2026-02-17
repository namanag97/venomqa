"""Example plugins for VenomQA.

This module provides example plugin implementations demonstrating
different plugin types and hook usage patterns.

Available Examples:
    - SlackNotifierPlugin: Send Slack notifications on test events
    - DataDogMetricsPlugin: Report metrics to DataDog
    - ConsoleLoggerPlugin: Log events to console
    - CustomAssertionsPlugin: Provide custom assertion helpers
    - TimingAnalyzerPlugin: Analyze step timing patterns

Usage:
    >>> from venomqa.plugins.examples import SlackNotifierPlugin
    >>>
    >>> plugin = SlackNotifierPlugin()
    >>> plugin.on_load({"webhook_url": "https://hooks.slack.com/..."})
"""

from venomqa.plugins.examples.console_logger import ConsoleLoggerPlugin
from venomqa.plugins.examples.custom_assertions import CustomAssertionsPlugin
from venomqa.plugins.examples.datadog_metrics import DataDogMetricsPlugin
from venomqa.plugins.examples.slack_notifier import SlackNotifierPlugin
from venomqa.plugins.examples.timing_analyzer import TimingAnalyzerPlugin

__all__ = [
    "SlackNotifierPlugin",
    "DataDogMetricsPlugin",
    "ConsoleLoggerPlugin",
    "CustomAssertionsPlugin",
    "TimingAnalyzerPlugin",
]
