"""Alert conditions and notification management for VenomQA.

This module provides alert condition definitions, rate limiting,
and the notification manager that coordinates sending notifications
based on test results.

Example:
    >>> from venomqa.notifications.alerts import (
    ...     AlertCondition, AlertTrigger, NotificationManager
    ... )
    >>>
    >>> # Create alert conditions
    >>> high_failure = AlertCondition(
    ...     name="high_failure_rate",
    ...     trigger=AlertTrigger.FAILURE_RATE,
    ...     threshold=10.0,  # 10%
    ...     channels=["slack", "pagerduty"]
    ... )
    >>>
    >>> # Create notification manager
    >>> manager = NotificationManager(
    ...     channels=[slack_channel, pagerduty_channel],
    ...     alerts=[high_failure]
    ... )
    >>>
    >>> # Process test results
    >>> manager.process_results(journey_results)
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

from venomqa.notifications.channels import (
    BaseChannel,
    NotificationEvent,
    NotificationMessage,
    create_channel,
)

if TYPE_CHECKING:
    from venomqa.core.models import JourneyResult

logger = logging.getLogger(__name__)


class AlertTrigger(Enum):
    """Types of alert triggers."""

    # Journey/step level triggers
    JOURNEY_FAILURE = "journey_failure"
    STEP_FAILURE = "step_failure"
    PATH_FAILURE = "path_failure"

    # Aggregate triggers
    FAILURE_RATE = "failure_rate"
    FAILURE_COUNT = "failure_count"

    # Performance triggers
    P50_LATENCY = "p50_latency"
    P95_LATENCY = "p95_latency"
    P99_LATENCY = "p99_latency"
    MEAN_LATENCY = "mean_latency"
    MAX_LATENCY = "max_latency"

    # Recovery trigger
    RECOVERY = "recovery"

    # Invariant trigger
    INVARIANT_VIOLATION = "invariant_violation"


class AlertSeverity(Enum):
    """Alert severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AlertState(Enum):
    """State of an alert condition."""

    OK = "ok"
    FIRING = "firing"
    PENDING = "pending"


@dataclass
class AlertCondition:
    """Definition of an alert condition.

    Specifies when alerts should be triggered based on test results.

    Attributes:
        name: Unique identifier for this alert.
        trigger: Type of condition that triggers the alert.
        threshold: Numeric threshold for aggregate triggers.
        channels: List of channel names to notify.
        severity: Severity level of this alert.
        description: Human-readable description.
        cooldown_seconds: Minimum seconds between repeated alerts.
        enabled: Whether this alert is active.
    """

    name: str
    trigger: AlertTrigger
    channels: list[str]
    threshold: float | None = None
    severity: AlertSeverity = AlertSeverity.HIGH
    description: str = ""
    cooldown_seconds: float = 300.0  # 5 minutes default
    enabled: bool = True

    def check(
        self,
        results: list[JourneyResult],
        previous_state: AlertState = AlertState.OK,
    ) -> tuple[AlertState, NotificationMessage | None]:
        """Check if this alert condition is triggered.

        Args:
            results: List of journey results to evaluate.
            previous_state: Previous state of this alert.

        Returns:
            Tuple of (new_state, optional_message).
        """
        if not self.enabled or not results:
            return AlertState.OK, None

        message: NotificationMessage | None = None
        new_state = AlertState.OK

        if self.trigger == AlertTrigger.JOURNEY_FAILURE:
            message, new_state = self._check_journey_failure(results)
        elif self.trigger == AlertTrigger.STEP_FAILURE:
            message, new_state = self._check_step_failure(results)
        elif self.trigger == AlertTrigger.PATH_FAILURE:
            message, new_state = self._check_path_failure(results)
        elif self.trigger == AlertTrigger.FAILURE_RATE:
            message, new_state = self._check_failure_rate(results)
        elif self.trigger == AlertTrigger.FAILURE_COUNT:
            message, new_state = self._check_failure_count(results)
        elif self.trigger in (
            AlertTrigger.P50_LATENCY,
            AlertTrigger.P95_LATENCY,
            AlertTrigger.P99_LATENCY,
            AlertTrigger.MEAN_LATENCY,
            AlertTrigger.MAX_LATENCY,
        ):
            message, new_state = self._check_latency(results)
        elif self.trigger == AlertTrigger.RECOVERY:
            if previous_state == AlertState.FIRING:
                message, new_state = self._check_recovery(results)
        elif self.trigger == AlertTrigger.INVARIANT_VIOLATION:
            message, new_state = self._check_invariant_violation(results)

        return new_state, message

    def _check_journey_failure(
        self, results: list[JourneyResult]
    ) -> tuple[NotificationMessage | None, AlertState]:
        """Check for any journey failure."""
        failed_journeys = [r for r in results if not r.success]
        if not failed_journeys:
            return None, AlertState.OK

        # Create message for first failure
        first_failure = failed_journeys[0]
        error_msg = "Unknown error"
        if first_failure.issues:
            error_msg = first_failure.issues[0].error

        message = NotificationMessage(
            title=f"Journey Failed: {first_failure.journey_name}",
            body=f"{len(failed_journeys)} journey(s) failed",
            event=NotificationEvent.FAILURE,
            severity=self.severity.value,
            journey_name=first_failure.journey_name,
            error=error_msg,
            metadata={
                "failed_count": len(failed_journeys),
                "failed_journeys": [r.journey_name for r in failed_journeys],
            },
        )

        return message, AlertState.FIRING

    def _check_step_failure(
        self, results: list[JourneyResult]
    ) -> tuple[NotificationMessage | None, AlertState]:
        """Check for any step failure."""
        failed_steps = []
        for result in results:
            for step in result.step_results:
                if not step.success:
                    failed_steps.append({
                        "journey": result.journey_name,
                        "step": step.step_name,
                        "error": step.error,
                    })

        if not failed_steps:
            return None, AlertState.OK

        first = failed_steps[0]
        message = NotificationMessage(
            title=f"Step Failed: {first['journey']}/{first['step']}",
            body=f"{len(failed_steps)} step(s) failed across all journeys",
            event=NotificationEvent.FAILURE,
            severity=self.severity.value,
            journey_name=first["journey"],
            step_name=first["step"],
            error=first["error"],
            metadata={"failed_steps": failed_steps[:10]},  # Limit to 10
        )

        return message, AlertState.FIRING

    def _check_path_failure(
        self, results: list[JourneyResult]
    ) -> tuple[NotificationMessage | None, AlertState]:
        """Check for any path failure in branches."""
        failed_paths = []
        for result in results:
            for branch in result.branch_results:
                for path in branch.path_results:
                    if not path.success:
                        failed_paths.append({
                            "journey": result.journey_name,
                            "checkpoint": branch.checkpoint_name,
                            "path": path.path_name,
                            "error": path.error,
                        })

        if not failed_paths:
            return None, AlertState.OK

        first = failed_paths[0]
        message = NotificationMessage(
            title=f"Path Failed: {first['journey']}/{first['path']}",
            body=f"{len(failed_paths)} path(s) failed across all journeys",
            event=NotificationEvent.FAILURE,
            severity=self.severity.value,
            journey_name=first["journey"],
            path_name=first["path"],
            error=first["error"],
            metadata={"failed_paths": failed_paths[:10]},
        )

        return message, AlertState.FIRING

    def _check_failure_rate(
        self, results: list[JourneyResult]
    ) -> tuple[NotificationMessage | None, AlertState]:
        """Check if failure rate exceeds threshold."""
        if self.threshold is None or not results:
            return None, AlertState.OK

        total = len(results)
        failed = sum(1 for r in results if not r.success)
        failure_rate = (failed / total) * 100 if total > 0 else 0

        if failure_rate <= self.threshold:
            return None, AlertState.OK

        message = NotificationMessage(
            title=f"High Failure Rate: {failure_rate:.1f}%",
            body=f"Failure rate ({failure_rate:.1f}%) exceeds threshold ({self.threshold}%)",
            event=NotificationEvent.FAILURE,
            severity=self.severity.value,
            metadata={
                "failure_rate": failure_rate,
                "threshold": self.threshold,
                "total_journeys": total,
                "failed_journeys": failed,
            },
        )

        return message, AlertState.FIRING

    def _check_failure_count(
        self, results: list[JourneyResult]
    ) -> tuple[NotificationMessage | None, AlertState]:
        """Check if failure count exceeds threshold."""
        if self.threshold is None:
            return None, AlertState.OK

        failed = sum(1 for r in results if not r.success)

        if failed <= self.threshold:
            return None, AlertState.OK

        message = NotificationMessage(
            title=f"High Failure Count: {failed} journeys",
            body=f"Failure count ({failed}) exceeds threshold ({int(self.threshold)})",
            event=NotificationEvent.FAILURE,
            severity=self.severity.value,
            metadata={
                "failure_count": failed,
                "threshold": self.threshold,
            },
        )

        return message, AlertState.FIRING

    def _check_latency(
        self, results: list[JourneyResult]
    ) -> tuple[NotificationMessage | None, AlertState]:
        """Check if latency exceeds threshold."""
        if self.threshold is None or not results:
            return None, AlertState.OK

        # Collect all step durations
        durations = []
        for result in results:
            durations.append(result.duration_ms)
            for step in result.step_results:
                durations.append(step.duration_ms)

        if not durations:
            return None, AlertState.OK

        # Calculate the relevant percentile
        sorted_durations = sorted(durations)
        count = len(sorted_durations)

        if self.trigger == AlertTrigger.P50_LATENCY:
            value = sorted_durations[count // 2]
            percentile = "p50"
        elif self.trigger == AlertTrigger.P95_LATENCY:
            idx = int(count * 0.95)
            value = sorted_durations[min(idx, count - 1)]
            percentile = "p95"
        elif self.trigger == AlertTrigger.P99_LATENCY:
            idx = int(count * 0.99)
            value = sorted_durations[min(idx, count - 1)]
            percentile = "p99"
        elif self.trigger == AlertTrigger.MEAN_LATENCY:
            value = sum(durations) / count
            percentile = "mean"
        elif self.trigger == AlertTrigger.MAX_LATENCY:
            value = sorted_durations[-1]
            percentile = "max"
        else:
            return None, AlertState.OK

        if value <= self.threshold:
            return None, AlertState.OK

        message = NotificationMessage(
            title=f"High Latency: {percentile} = {value:.0f}ms",
            body=f"Latency ({percentile}: {value:.0f}ms) exceeds threshold ({self.threshold:.0f}ms)",
            event=NotificationEvent.PERFORMANCE,
            severity=self.severity.value,
            metadata={
                "percentile": percentile,
                "value_ms": value,
                "threshold_ms": self.threshold,
                "sample_count": count,
            },
        )

        return message, AlertState.FIRING

    def _check_recovery(
        self, results: list[JourneyResult]
    ) -> tuple[NotificationMessage | None, AlertState]:
        """Check if tests have recovered (all passing)."""
        if not results:
            return None, AlertState.OK

        all_passed = all(r.success for r in results)
        if not all_passed:
            return None, AlertState.FIRING

        total_duration = sum(r.duration_ms for r in results)
        message = NotificationMessage(
            title="Tests Recovered",
            body=f"All {len(results)} journey(s) are now passing",
            event=NotificationEvent.RECOVERY,
            severity="info",
            metadata={
                "journey_count": len(results),
                "total_duration_ms": total_duration,
            },
        )

        return message, AlertState.OK

    def _check_invariant_violation(
        self, results: list[JourneyResult]
    ) -> tuple[NotificationMessage | None, AlertState]:
        """Check for invariant violation issues."""
        violations = []
        for result in results:
            for issue in result.issues:
                # Check if the issue is an invariant violation
                if "invariant" in issue.error.lower():
                    violations.append({
                        "journey": result.journey_name,
                        "step": issue.step,
                        "error": issue.error,
                    })

        if not violations:
            return None, AlertState.OK

        first = violations[0]
        message = NotificationMessage(
            title=f"Invariant Violation: {first['journey']}",
            body=f"{len(violations)} invariant violation(s) detected",
            event=NotificationEvent.INVARIANT_VIOLATION,
            severity=self.severity.value,
            journey_name=first["journey"],
            step_name=first["step"],
            error=first["error"],
            metadata={"violations": violations[:10]},
        )

        return message, AlertState.FIRING


@dataclass
class RateLimiter:
    """Rate limiter for preventing notification spam.

    Tracks when notifications were last sent and enforces
    cooldown periods between repeated alerts.

    Attributes:
        default_cooldown: Default cooldown in seconds.
    """

    default_cooldown: float = 300.0  # 5 minutes
    _last_sent: dict[str, float] = field(default_factory=dict)

    def can_send(self, key: str, cooldown: float | None = None) -> bool:
        """Check if a notification can be sent.

        Args:
            key: Unique key identifying the notification type.
            cooldown: Optional custom cooldown in seconds.

        Returns:
            True if the notification can be sent.
        """
        cooldown = cooldown or self.default_cooldown
        now = time.time()
        last = self._last_sent.get(key, 0)
        return (now - last) >= cooldown

    def record_send(self, key: str) -> None:
        """Record that a notification was sent.

        Args:
            key: Unique key identifying the notification type.
        """
        self._last_sent[key] = time.time()

    def clear(self) -> None:
        """Clear all rate limit records."""
        self._last_sent.clear()

    def get_remaining_cooldown(self, key: str, cooldown: float | None = None) -> float:
        """Get remaining cooldown time for a key.

        Args:
            key: Unique key identifying the notification type.
            cooldown: Optional custom cooldown in seconds.

        Returns:
            Remaining seconds until notification can be sent (0 if ready).
        """
        cooldown = cooldown or self.default_cooldown
        now = time.time()
        last = self._last_sent.get(key, 0)
        remaining = cooldown - (now - last)
        return max(0, remaining)


@dataclass
class AlertAggregator:
    """Aggregates similar alerts to reduce noise.

    Groups similar alerts together and sends summary notifications
    instead of individual alerts for each failure.

    Attributes:
        window_seconds: Time window for aggregation.
    """

    window_seconds: float = 60.0
    _pending: dict[str, list[NotificationMessage]] = field(default_factory=dict)
    _window_start: dict[str, float] = field(default_factory=dict)

    def add(self, message: NotificationMessage) -> NotificationMessage | None:
        """Add a message to the aggregator.

        Args:
            message: The notification message to aggregate.

        Returns:
            Aggregated message if window expired, None otherwise.
        """
        key = self._generate_key(message)
        now = time.time()

        # Initialize window if needed
        if key not in self._window_start:
            self._window_start[key] = now
            self._pending[key] = []

        # Check if window expired
        if (now - self._window_start[key]) >= self.window_seconds:
            # Return aggregated message
            result = self._aggregate(key, message)
            # Reset window
            self._window_start[key] = now
            self._pending[key] = []
            return result

        # Add to pending
        self._pending[key].append(message)
        return None

    def flush(self) -> list[NotificationMessage]:
        """Flush all pending messages.

        Returns:
            List of aggregated messages for all pending alerts.
        """
        results = []
        for key in list(self._pending.keys()):
            if self._pending[key]:
                # Create a summary message for the group
                messages = self._pending[key]
                if len(messages) == 1:
                    results.append(messages[0])
                else:
                    results.append(self._create_summary(messages))
        self._pending.clear()
        self._window_start.clear()
        return results

    def _generate_key(self, message: NotificationMessage) -> str:
        """Generate aggregation key for a message."""
        parts = [
            message.event.value,
            message.severity,
            message.journey_name or "",
        ]
        return hashlib.md5(":".join(parts).encode()).hexdigest()

    def _aggregate(
        self, key: str, new_message: NotificationMessage
    ) -> NotificationMessage:
        """Create aggregated message for a group."""
        pending = self._pending.get(key, [])
        all_messages = pending + [new_message]

        if len(all_messages) == 1:
            return new_message

        return self._create_summary(all_messages)

    def _create_summary(self, messages: list[NotificationMessage]) -> NotificationMessage:
        """Create a summary message from multiple messages."""
        first = messages[0]
        count = len(messages)

        # Collect unique journeys
        journeys = set()
        steps = set()
        errors = []
        for msg in messages:
            if msg.journey_name:
                journeys.add(msg.journey_name)
            if msg.step_name:
                steps.add(msg.step_name)
            if msg.error:
                errors.append(msg.error)

        body_parts = [f"{count} similar alerts aggregated"]
        if journeys:
            body_parts.append(f"Journeys: {', '.join(sorted(journeys)[:5])}")
        if steps:
            body_parts.append(f"Steps: {', '.join(sorted(steps)[:5])}")

        return NotificationMessage(
            title=f"[{count} alerts] {first.title}",
            body="\n".join(body_parts),
            event=first.event,
            severity=first.severity,
            metadata={
                "aggregated_count": count,
                "journeys": list(journeys),
                "errors": errors[:5],
            },
        )


@dataclass
class NotificationConfig:
    """Configuration for the notification system.

    Attributes:
        channels: List of channel configurations.
        alerts: List of alert configurations.
        rate_limit_seconds: Default rate limit cooldown.
        aggregate_window_seconds: Alert aggregation window.
        enabled: Whether notifications are enabled.
        notify_on_success: Send notifications on successful runs.
    """

    channels: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    rate_limit_seconds: float = 300.0
    aggregate_window_seconds: float = 60.0
    enabled: bool = True
    notify_on_success: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NotificationConfig:
        """Create config from dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            NotificationConfig instance.
        """
        return cls(
            channels=data.get("channels", []),
            alerts=data.get("alerts", []),
            rate_limit_seconds=data.get("rate_limit_seconds", 300.0),
            aggregate_window_seconds=data.get("aggregate_window_seconds", 60.0),
            enabled=data.get("enabled", True),
            notify_on_success=data.get("notify_on_success", False),
        )

    @classmethod
    def from_yaml_section(cls, notifications_section: dict[str, Any]) -> NotificationConfig:
        """Create config from YAML notifications section.

        Args:
            notifications_section: The 'notifications' section from YAML config.

        Returns:
            NotificationConfig instance.
        """
        return cls.from_dict(notifications_section)


class AlertManager:
    """Manages alert conditions and their states.

    Tracks alert states, handles cooldowns, and coordinates
    which alerts should fire based on test results.

    Attributes:
        alerts: List of alert conditions.
        rate_limiter: Rate limiter for cooldowns.
        aggregator: Alert aggregator for grouping.
    """

    def __init__(
        self,
        alerts: list[AlertCondition] | None = None,
        rate_limiter: RateLimiter | None = None,
        aggregator: AlertAggregator | None = None,
    ) -> None:
        """Initialize alert manager.

        Args:
            alerts: List of alert conditions.
            rate_limiter: Optional custom rate limiter.
            aggregator: Optional custom aggregator.
        """
        self.alerts = alerts or []
        self.rate_limiter = rate_limiter or RateLimiter()
        self.aggregator = aggregator or AlertAggregator()
        self._states: dict[str, AlertState] = {}

    def evaluate(
        self, results: list[JourneyResult]
    ) -> list[tuple[AlertCondition, NotificationMessage]]:
        """Evaluate all alert conditions against results.

        Args:
            results: List of journey results to evaluate.

        Returns:
            List of (alert, message) tuples for triggered alerts.
        """
        triggered: list[tuple[AlertCondition, NotificationMessage]] = []

        for alert in self.alerts:
            if not alert.enabled:
                continue

            # Get previous state
            prev_state = self._states.get(alert.name, AlertState.OK)

            # Check the condition
            new_state, message = alert.check(results, prev_state)

            # Update state
            self._states[alert.name] = new_state

            if message is None:
                continue

            # Check rate limit
            rate_key = f"alert:{alert.name}"
            if not self.rate_limiter.can_send(rate_key, alert.cooldown_seconds):
                remaining = self.rate_limiter.get_remaining_cooldown(
                    rate_key, alert.cooldown_seconds
                )
                logger.debug(
                    f"Alert '{alert.name}' rate limited, {remaining:.0f}s remaining"
                )
                continue

            # Try to aggregate
            aggregated = self.aggregator.add(message)
            if aggregated:
                triggered.append((alert, aggregated))
                self.rate_limiter.record_send(rate_key)

        # Flush any pending aggregated alerts
        for flushed in self.aggregator.flush():
            # Find matching alert
            for alert in self.alerts:
                if alert.enabled:
                    rate_key = f"alert:{alert.name}"
                    if self.rate_limiter.can_send(rate_key, alert.cooldown_seconds):
                        triggered.append((alert, flushed))
                        self.rate_limiter.record_send(rate_key)
                        break

        return triggered

    def get_state(self, alert_name: str) -> AlertState:
        """Get the current state of an alert.

        Args:
            alert_name: Name of the alert.

        Returns:
            Current alert state.
        """
        return self._states.get(alert_name, AlertState.OK)

    def reset(self) -> None:
        """Reset all alert states."""
        self._states.clear()
        self.rate_limiter.clear()


class NotificationManager:
    """Central manager for the notification system.

    Coordinates channels, alerts, and sending notifications
    based on test results.

    Example:
        >>> manager = NotificationManager(
        ...     channels=[slack_channel],
        ...     alerts=[failure_alert]
        ... )
        >>> manager.process_results(results)
        >>> manager.send_message(custom_message, channels=["slack"])
    """

    def __init__(
        self,
        channels: list[BaseChannel] | None = None,
        alerts: list[AlertCondition] | None = None,
        config: NotificationConfig | None = None,
        report_url: str | None = None,
    ) -> None:
        """Initialize notification manager.

        Args:
            channels: List of notification channels.
            alerts: List of alert conditions.
            config: Optional configuration.
            report_url: URL to include in notifications.
        """
        self.config = config or NotificationConfig()
        self.report_url = report_url

        # Initialize channels from config if not provided
        self.channels: dict[str, BaseChannel] = {}
        if channels:
            for channel in channels:
                self.channels[channel.name] = channel
        elif self.config.channels:
            for channel_config in self.config.channels:
                channel = create_channel(channel_config)
                self.channels[channel.name] = channel

        # Initialize alerts from config if not provided
        alert_list = alerts or []
        if not alert_list and self.config.alerts:
            alert_list = self._parse_alerts(self.config.alerts)

        # Initialize alert manager
        self.alert_manager = AlertManager(
            alerts=alert_list,
            rate_limiter=RateLimiter(self.config.rate_limit_seconds),
            aggregator=AlertAggregator(self.config.aggregate_window_seconds),
        )

        # Track previous run state for recovery detection
        self._previous_success: bool | None = None

    def _parse_alerts(self, alert_configs: list[dict[str, Any]]) -> list[AlertCondition]:
        """Parse alert configurations into AlertCondition objects."""
        alerts = []
        for config in alert_configs:
            # Parse condition string if present
            trigger, threshold = self._parse_condition(config.get("condition", ""))

            # Or use explicit trigger
            if "trigger" in config:
                trigger = AlertTrigger(config["trigger"])
            if "threshold" in config:
                threshold = float(config["threshold"])

            alert = AlertCondition(
                name=config["name"],
                trigger=trigger or AlertTrigger.JOURNEY_FAILURE,
                threshold=threshold,
                channels=config.get("channels", []),
                severity=AlertSeverity(config.get("severity", "high")),
                description=config.get("description", ""),
                cooldown_seconds=config.get("cooldown_seconds", 300.0),
                enabled=config.get("enabled", True),
            )
            alerts.append(alert)
        return alerts

    def _parse_condition(
        self, condition: str
    ) -> tuple[AlertTrigger | None, float | None]:
        """Parse a condition string like 'failure_rate > 10%'.

        Args:
            condition: Condition string.

        Returns:
            Tuple of (trigger, threshold).
        """
        if not condition:
            return None, None

        condition = condition.lower().strip()

        # Parse common patterns
        patterns = [
            ("failure_rate", AlertTrigger.FAILURE_RATE),
            ("failure_count", AlertTrigger.FAILURE_COUNT),
            ("p99_latency", AlertTrigger.P99_LATENCY),
            ("p95_latency", AlertTrigger.P95_LATENCY),
            ("p50_latency", AlertTrigger.P50_LATENCY),
            ("mean_latency", AlertTrigger.MEAN_LATENCY),
            ("max_latency", AlertTrigger.MAX_LATENCY),
        ]

        trigger = None
        for pattern, trigger_type in patterns:
            if pattern in condition:
                trigger = trigger_type
                break

        # Extract threshold
        threshold = None
        import re

        # Match number with optional % or ms suffix
        match = re.search(r"(\d+(?:\.\d+)?)\s*(%|ms)?", condition)
        if match:
            threshold = float(match.group(1))
            # No conversion needed - keep as-is

        return trigger, threshold

    def process_results(
        self,
        results: list[JourneyResult],
        report_url: str | None = None,
    ) -> list[tuple[str, bool]]:
        """Process test results and send applicable notifications.

        Args:
            results: List of journey results.
            report_url: Optional URL to include in notifications.

        Returns:
            List of (channel_name, success) tuples for sent notifications.
        """
        if not self.config.enabled:
            return []

        report_url = report_url or self.report_url
        sent_results: list[tuple[str, bool]] = []

        # Check for recovery
        current_success = all(r.success for r in results)
        if self._previous_success is False and current_success:
            # Transitioned from failure to success - send recovery
            recovery_msg = NotificationMessage(
                title="Tests Recovered",
                body=f"All {len(results)} journey(s) are now passing",
                event=NotificationEvent.RECOVERY,
                severity="info",
                report_url=report_url,
                metadata={"journey_count": len(results)},
            )
            for channel_name, channel in self.channels.items():
                if channel.should_send(recovery_msg):
                    success = channel.send(recovery_msg)
                    sent_results.append((channel_name, success))

        self._previous_success = current_success

        # Evaluate alert conditions
        triggered = self.alert_manager.evaluate(results)

        # Send notifications for triggered alerts
        for alert, message in triggered:
            # Add report URL
            message.report_url = report_url

            # Send to specified channels
            for channel_name in alert.channels:
                if channel_name in self.channels:
                    channel = self.channels[channel_name]
                    success = channel.send(message)
                    sent_results.append((channel_name, success))
                    logger.info(
                        f"Alert '{alert.name}' sent to channel '{channel_name}': "
                        f"{'success' if success else 'failed'}"
                    )
                else:
                    logger.warning(
                        f"Alert '{alert.name}' references unknown channel '{channel_name}'"
                    )

        return sent_results

    def send_message(
        self,
        message: NotificationMessage,
        channels: list[str] | None = None,
    ) -> list[tuple[str, bool]]:
        """Send a custom notification message.

        Args:
            message: The notification message to send.
            channels: Optional list of channel names. Sends to all if not specified.

        Returns:
            List of (channel_name, success) tuples.
        """
        results: list[tuple[str, bool]] = []

        target_channels = channels or list(self.channels.keys())

        for channel_name in target_channels:
            if channel_name not in self.channels:
                logger.warning(f"Unknown channel: {channel_name}")
                continue

            channel = self.channels[channel_name]
            success = channel.send_if_applicable(message)
            results.append((channel_name, success))

        return results

    def add_channel(self, channel: BaseChannel) -> None:
        """Add a notification channel.

        Args:
            channel: The channel to add.
        """
        self.channels[channel.name] = channel

    def remove_channel(self, name: str) -> bool:
        """Remove a notification channel.

        Args:
            name: Name of the channel to remove.

        Returns:
            True if the channel was removed, False if not found.
        """
        if name in self.channels:
            del self.channels[name]
            return True
        return False

    def add_alert(self, alert: AlertCondition) -> None:
        """Add an alert condition.

        Args:
            alert: The alert condition to add.
        """
        self.alert_manager.alerts.append(alert)

    def remove_alert(self, name: str) -> bool:
        """Remove an alert condition.

        Args:
            name: Name of the alert to remove.

        Returns:
            True if the alert was removed, False if not found.
        """
        for i, alert in enumerate(self.alert_manager.alerts):
            if alert.name == name:
                del self.alert_manager.alerts[i]
                return True
        return False

    def reset(self) -> None:
        """Reset all alert states and rate limits."""
        self.alert_manager.reset()
        self._previous_success = None


def create_notification_manager_from_config(
    config: dict[str, Any],
    report_url: str | None = None,
) -> NotificationManager:
    """Create a NotificationManager from a configuration dictionary.

    Args:
        config: Configuration dictionary with 'notifications' section.
        report_url: Optional report URL to include in notifications.

    Returns:
        Configured NotificationManager instance.

    Example:
        >>> config = {
        ...     "notifications": {
        ...         "channels": [
        ...             {"type": "slack", "webhook_url": "...", "on": ["failure"]}
        ...         ],
        ...         "alerts": [
        ...             {"name": "failures", "condition": "failure_rate > 10%",
        ...              "channels": ["slack"]}
        ...         ]
        ...     }
        ... }
        >>> manager = create_notification_manager_from_config(config)
    """
    notifications_config = config.get("notifications", {})
    parsed_config = NotificationConfig.from_dict(notifications_config)
    return NotificationManager(config=parsed_config, report_url=report_url)
