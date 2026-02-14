"""DataDog metrics plugin for VenomQA.

This plugin reports test metrics to DataDog for monitoring and alerting:
- Journey duration
- Step pass/fail counts
- Error rates
- Performance percentiles

Configuration:
    ```yaml
    plugins:
      - name: venomqa.plugins.examples.datadog_metrics
        config:
          api_key: ${DATADOG_API_KEY}
          app_key: ${DATADOG_APP_KEY}
          site: datadoghq.com
          prefix: venomqa
          tags:
            - env:staging
            - team:qa
    ```

Example:
    >>> from venomqa.plugins.examples import DataDogMetricsPlugin
    >>>
    >>> plugin = DataDogMetricsPlugin()
    >>> plugin.on_load({
    ...     "api_key": "your-api-key",
    ...     "prefix": "venomqa",
    ... })
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any
from urllib.request import Request, urlopen
from urllib.error import URLError

from venomqa.plugins.base import HookPlugin
from venomqa.plugins.types import (
    FailureContext,
    HookPriority,
    JourneyContext,
    PluginType,
    StepContext,
)

if TYPE_CHECKING:
    from venomqa.core.models import Journey, JourneyResult, Step, StepResult

logger = logging.getLogger(__name__)


class DataDogMetricsPlugin(HookPlugin):
    """Report test metrics to DataDog.

    This plugin sends metrics to the DataDog API for monitoring,
    dashboarding, and alerting on test execution.

    Metrics Reported:
        - {prefix}.journey.duration: Journey execution time (ms)
        - {prefix}.journey.success: Journey success (1/0)
        - {prefix}.journey.steps.total: Total steps in journey
        - {prefix}.journey.steps.passed: Passed steps count
        - {prefix}.journey.steps.failed: Failed steps count
        - {prefix}.step.duration: Step execution time (ms)
        - {prefix}.step.success: Step success (1/0)
        - {prefix}.errors.count: Error count

    Configuration Options:
        api_key: DataDog API key (required, or DATADOG_API_KEY env)
        app_key: DataDog app key (optional)
        site: DataDog site (default: datadoghq.com)
        prefix: Metric name prefix (default: venomqa)
        tags: Additional tags to add to all metrics
        batch_size: Metrics to batch before sending (default: 10)
        flush_interval: Seconds between flushes (default: 5)
    """

    name = "datadog-metrics"
    version = "1.0.0"
    plugin_type = PluginType.HOOK
    description = "Report test metrics to DataDog"
    author = "VenomQA Team"
    priority = HookPriority.LOW

    def __init__(self) -> None:
        super().__init__()
        self.api_key: str = ""
        self.app_key: str | None = None
        self.site: str = "datadoghq.com"
        self.prefix: str = "venomqa"
        self.tags: list[str] = []
        self.batch_size: int = 10
        self.flush_interval: float = 5.0
        self._metrics_buffer: list[dict[str, Any]] = []
        self._last_flush: float = 0.0

    def on_load(self, config: dict[str, Any]) -> None:
        """Load plugin configuration.

        Args:
            config: Plugin configuration

        Raises:
            ValueError: If api_key is not provided
        """
        super().on_load(config)

        # API key from config or environment
        self.api_key = config.get("api_key") or os.environ.get("DATADOG_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "DataDog api_key is required. "
                "Set via config or DATADOG_API_KEY environment variable."
            )

        self.app_key = config.get("app_key") or os.environ.get("DATADOG_APP_KEY")
        self.site = config.get("site", "datadoghq.com")
        self.prefix = config.get("prefix", "venomqa")
        self.tags = config.get("tags", [])
        self.batch_size = config.get("batch_size", 10)
        self.flush_interval = config.get("flush_interval", 5.0)

        self._logger.info(f"DataDog metrics configured with prefix: {self.prefix}")

    def on_unload(self) -> None:
        """Flush remaining metrics on unload."""
        self._flush_metrics()
        super().on_unload()

    def on_journey_start(self, context: JourneyContext) -> None:
        """Record journey start.

        Args:
            context: Journey context
        """
        self._record_metric(
            f"{self.prefix}.journey.started",
            1,
            tags=[f"journey:{context.journey.name}"],
            metric_type="count",
        )

    def on_journey_complete(
        self,
        journey: Journey,
        result: JourneyResult,
        context: JourneyContext,
    ) -> None:
        """Record journey completion metrics.

        Args:
            journey: The completed journey
            result: Journey result
            context: Journey context
        """
        base_tags = [f"journey:{journey.name}"]

        # Journey duration
        self._record_metric(
            f"{self.prefix}.journey.duration",
            result.duration_ms,
            tags=base_tags,
            metric_type="gauge",
        )

        # Journey success
        self._record_metric(
            f"{self.prefix}.journey.success",
            1 if result.success else 0,
            tags=base_tags,
            metric_type="gauge",
        )

        # Step counts
        self._record_metric(
            f"{self.prefix}.journey.steps.total",
            result.total_steps,
            tags=base_tags,
            metric_type="gauge",
        )
        self._record_metric(
            f"{self.prefix}.journey.steps.passed",
            result.passed_steps,
            tags=base_tags,
            metric_type="gauge",
        )
        self._record_metric(
            f"{self.prefix}.journey.steps.failed",
            result.failed_steps,
            tags=base_tags,
            metric_type="gauge",
        )

        # Path counts if any
        if result.total_paths > 0:
            self._record_metric(
                f"{self.prefix}.journey.paths.total",
                result.total_paths,
                tags=base_tags,
                metric_type="gauge",
            )
            self._record_metric(
                f"{self.prefix}.journey.paths.passed",
                result.passed_paths,
                tags=base_tags,
                metric_type="gauge",
            )

        # Issue count
        if result.issues:
            self._record_metric(
                f"{self.prefix}.journey.issues",
                len(result.issues),
                tags=base_tags,
                metric_type="count",
            )

        # Flush metrics
        self._maybe_flush()

    def on_step_complete(
        self,
        step: Step,
        result: StepResult,
        context: StepContext,
    ) -> None:
        """Record step completion metrics.

        Args:
            step: The completed step
            result: Step result
            context: Step context
        """
        tags = [
            f"journey:{context.journey_name}",
            f"path:{context.path_name}",
            f"step:{step.name}",
        ]

        # Step duration
        self._record_metric(
            f"{self.prefix}.step.duration",
            result.duration_ms,
            tags=tags,
            metric_type="gauge",
        )

        # Step success
        self._record_metric(
            f"{self.prefix}.step.success",
            1 if result.success else 0,
            tags=tags,
            metric_type="gauge",
        )

        self._maybe_flush()

    def on_failure(self, context: FailureContext) -> None:
        """Record failure metrics.

        Args:
            context: Failure context
        """
        tags = [
            f"journey:{context.journey_name}",
            f"path:{context.path_name}",
            f"step:{context.step_name}",
        ]

        self._record_metric(
            f"{self.prefix}.errors.count",
            1,
            tags=tags,
            metric_type="count",
        )

        self._maybe_flush()

    def _record_metric(
        self,
        name: str,
        value: float,
        tags: list[str] | None = None,
        metric_type: str = "gauge",
    ) -> None:
        """Buffer a metric for sending.

        Args:
            name: Metric name
            value: Metric value
            tags: Additional tags
            metric_type: Type (gauge, count, rate)
        """
        all_tags = list(self.tags)
        if tags:
            all_tags.extend(tags)

        metric = {
            "metric": name,
            "points": [[int(time.time()), value]],
            "type": metric_type,
            "tags": all_tags,
        }

        self._metrics_buffer.append(metric)

    def _maybe_flush(self) -> None:
        """Flush metrics if buffer is full or interval elapsed."""
        now = time.time()
        should_flush = (
            len(self._metrics_buffer) >= self.batch_size
            or (now - self._last_flush) >= self.flush_interval
        )

        if should_flush:
            self._flush_metrics()

    def _flush_metrics(self) -> None:
        """Send buffered metrics to DataDog."""
        if not self._metrics_buffer:
            return

        metrics = self._metrics_buffer.copy()
        self._metrics_buffer.clear()
        self._last_flush = time.time()

        try:
            self._send_metrics(metrics)
            self._logger.debug(f"Sent {len(metrics)} metrics to DataDog")
        except Exception as e:
            self._logger.error(f"Failed to send metrics to DataDog: {e}")
            # Put metrics back in buffer for retry
            self._metrics_buffer.extend(metrics)

    def _send_metrics(self, metrics: list[dict[str, Any]]) -> None:
        """Send metrics to DataDog API.

        Args:
            metrics: List of metric dictionaries
        """
        url = f"https://api.{self.site}/api/v1/series"

        headers = {
            "Content-Type": "application/json",
            "DD-API-KEY": self.api_key,
        }
        if self.app_key:
            headers["DD-APPLICATION-KEY"] = self.app_key

        payload = {"series": metrics}
        data = json.dumps(payload).encode("utf-8")

        request = Request(url, data=data, headers=headers, method="POST")

        try:
            with urlopen(request, timeout=10) as response:
                if response.status != 202:
                    self._logger.warning(f"DataDog API returned status {response.status}")
        except URLError as e:
            raise RuntimeError(f"Failed to send metrics: {e}") from e


# Allow direct import as plugin
Plugin = DataDogMetricsPlugin
plugin = DataDogMetricsPlugin()
