"""Tests for VenomQA notification and alerting system."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from venomqa.core.models import (
    Issue,
    JourneyResult,
    Severity,
    StepResult,
)
from venomqa.notifications.alerts import (
    AlertAggregator,
    AlertCondition,
    AlertManager,
    AlertState,
    AlertTrigger,
    NotificationConfig,
    NotificationManager,
    RateLimiter,
    create_notification_manager_from_config,
)
from venomqa.notifications.channels import (
    ChannelType,
    CustomWebhookChannel,
    DiscordChannel,
    EmailChannel,
    NotificationEvent,
    NotificationMessage,
    PagerDutyChannel,
    SlackChannel,
    create_channel,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_message() -> NotificationMessage:
    """Create a sample notification message."""
    return NotificationMessage(
        title="Test Alert",
        body="This is a test notification",
        event=NotificationEvent.FAILURE,
        severity="high",
        journey_name="checkout_flow",
        step_name="payment",
        error="HTTP 500 Internal Server Error",
        report_url="https://reports.example.com/test-123",
    )


@pytest.fixture
def recovery_message() -> NotificationMessage:
    """Create a recovery notification message."""
    return NotificationMessage(
        title="Tests Recovered",
        body="All tests are now passing",
        event=NotificationEvent.RECOVERY,
        severity="info",
        journey_name="checkout_flow",
    )


@pytest.fixture
def sample_results() -> list[JourneyResult]:
    """Create sample journey results."""
    now = datetime.now()
    return [
        JourneyResult(
            journey_name="checkout_flow",
            success=True,
            started_at=now,
            finished_at=now,
            step_results=[
                StepResult(
                    step_name="login",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=100.0,
                ),
                StepResult(
                    step_name="add_to_cart",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=150.0,
                ),
            ],
            issues=[],
            duration_ms=250.0,
        ),
    ]


@pytest.fixture
def failed_results() -> list[JourneyResult]:
    """Create sample failed journey results."""
    now = datetime.now()
    return [
        JourneyResult(
            journey_name="checkout_flow",
            success=False,
            started_at=now,
            finished_at=now,
            step_results=[
                StepResult(
                    step_name="login",
                    success=True,
                    started_at=now,
                    finished_at=now,
                    duration_ms=100.0,
                ),
                StepResult(
                    step_name="payment",
                    success=False,
                    started_at=now,
                    finished_at=now,
                    error="HTTP 500",
                    duration_ms=50.0,
                ),
            ],
            issues=[
                Issue(
                    journey="checkout_flow",
                    path="main",
                    step="payment",
                    error="HTTP 500 Internal Server Error",
                    severity=Severity.HIGH,
                ),
            ],
            duration_ms=150.0,
        ),
    ]


@pytest.fixture
def mixed_results(sample_results: list[JourneyResult], failed_results: list[JourneyResult]) -> list[JourneyResult]:
    """Create mixed success/failure results."""
    return sample_results + failed_results


# ============================================================================
# NotificationMessage Tests
# ============================================================================


class TestNotificationMessage:
    """Tests for NotificationMessage dataclass."""

    def test_default_values(self) -> None:
        msg = NotificationMessage(title="Test", body="Body")
        assert msg.event == NotificationEvent.INFO
        assert msg.severity == "info"
        assert msg.journey_name is None
        assert msg.step_name is None
        assert isinstance(msg.timestamp, datetime)
        assert msg.metadata == {}
        assert msg.quick_actions == []

    def test_to_dict(self, sample_message: NotificationMessage) -> None:
        result = sample_message.to_dict()
        assert result["title"] == "Test Alert"
        assert result["body"] == "This is a test notification"
        assert result["event"] == "failure"
        assert result["severity"] == "high"
        assert result["journey_name"] == "checkout_flow"
        assert result["step_name"] == "payment"
        assert "timestamp" in result

    def test_custom_metadata(self) -> None:
        msg = NotificationMessage(
            title="Test",
            body="Body",
            metadata={"run_id": "123", "env": "staging"},
        )
        assert msg.metadata["run_id"] == "123"
        assert msg.metadata["env"] == "staging"

    def test_quick_actions(self) -> None:
        msg = NotificationMessage(
            title="Test",
            body="Body",
            quick_actions=[
                {"label": "View Logs", "url": "https://logs.example.com"},
                {"label": "Retry", "url": "https://ci.example.com/retry"},
            ],
        )
        assert len(msg.quick_actions) == 2
        assert msg.quick_actions[0]["label"] == "View Logs"


# ============================================================================
# Slack Channel Tests
# ============================================================================


class TestSlackChannel:
    """Tests for SlackChannel."""

    def test_channel_type(self) -> None:
        channel = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            name="slack-test",
        )
        assert channel.channel_type == ChannelType.SLACK

    def test_should_send_when_enabled(self, sample_message: NotificationMessage) -> None:
        channel = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            enabled=True,
            events=[NotificationEvent.FAILURE],
        )
        assert channel.should_send(sample_message) is True

    def test_should_not_send_when_disabled(self, sample_message: NotificationMessage) -> None:
        channel = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            enabled=False,
        )
        assert channel.should_send(sample_message) is False

    def test_should_not_send_wrong_event(self, sample_message: NotificationMessage) -> None:
        channel = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            events=[NotificationEvent.RECOVERY],  # Only recovery events
        )
        assert channel.should_send(sample_message) is False

    @patch("urllib.request.urlopen")
    def test_send_success(self, mock_urlopen: MagicMock, sample_message: NotificationMessage) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        channel = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            name="slack-test",
        )
        result = channel.send(sample_message)
        assert result is True

    @patch("urllib.request.urlopen")
    def test_send_failure(self, mock_urlopen: MagicMock, sample_message: NotificationMessage) -> None:
        import urllib.error

        mock_urlopen.side_effect = urllib.error.URLError("Connection failed")

        channel = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            name="slack-test",
        )
        result = channel.send(sample_message)
        assert result is False

    def test_build_payload_structure(self, sample_message: NotificationMessage) -> None:
        channel = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            channel="#alerts",
            username="TestBot",
            icon_emoji=":robot:",
            mention_on_failure=["<@U12345>"],
        )
        payload = channel._build_payload(sample_message)

        assert payload["username"] == "TestBot"
        assert payload["icon_emoji"] == ":robot:"
        assert payload["channel"] == "#alerts"
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1
        assert "blocks" in payload["attachments"][0]

    def test_color_for_failure(self, sample_message: NotificationMessage) -> None:
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")
        color = channel._get_color(sample_message)
        assert color == "danger"

    def test_color_for_recovery(self, recovery_message: NotificationMessage) -> None:
        channel = SlackChannel(webhook_url="https://hooks.slack.com/test")
        color = channel._get_color(recovery_message)
        assert color == "good"


# ============================================================================
# Discord Channel Tests
# ============================================================================


class TestDiscordChannel:
    """Tests for DiscordChannel."""

    def test_channel_type(self) -> None:
        channel = DiscordChannel(
            webhook_url="https://discord.com/api/webhooks/test",
            name="discord-test",
        )
        assert channel.channel_type == ChannelType.DISCORD

    @patch("urllib.request.urlopen")
    def test_send_success(self, mock_urlopen: MagicMock, sample_message: NotificationMessage) -> None:
        mock_response = MagicMock()
        mock_response.status = 204  # Discord returns 204 on success
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        channel = DiscordChannel(
            webhook_url="https://discord.com/api/webhooks/test",
            name="discord-test",
        )
        result = channel.send(sample_message)
        assert result is True

    def test_build_payload_with_embed(self, sample_message: NotificationMessage) -> None:
        channel = DiscordChannel(
            webhook_url="https://discord.com/api/webhooks/test",
            username="TestBot",
            avatar_url="https://example.com/avatar.png",
        )
        payload = channel._build_payload(sample_message)

        assert payload["username"] == "TestBot"
        assert payload["avatar_url"] == "https://example.com/avatar.png"
        assert "embeds" in payload
        assert len(payload["embeds"]) == 1

        embed = payload["embeds"][0]
        assert "title" in embed
        assert "color" in embed
        assert "fields" in embed

    def test_mentions_on_failure(self, sample_message: NotificationMessage) -> None:
        channel = DiscordChannel(
            webhook_url="https://discord.com/api/webhooks/test",
            mention_on_failure=["<@123456>", "<@&789012>"],
        )
        payload = channel._build_payload(sample_message)

        assert "content" in payload
        assert "<@123456>" in payload["content"]


# ============================================================================
# Email Channel Tests
# ============================================================================


class TestEmailChannel:
    """Tests for EmailChannel."""

    def test_channel_type(self) -> None:
        channel = EmailChannel(
            smtp_host="smtp.example.com",
            from_addr="alerts@example.com",
            to_addrs=["team@example.com"],
        )
        assert channel.channel_type == ChannelType.EMAIL

    def test_build_text_body(self, sample_message: NotificationMessage) -> None:
        channel = EmailChannel(
            smtp_host="smtp.example.com",
            from_addr="alerts@example.com",
            to_addrs=["team@example.com"],
        )
        text = channel._build_text_body(sample_message)

        assert "Test Alert" in text
        assert "checkout_flow" in text
        assert "payment" in text
        assert "HTTP 500" in text

    def test_build_html_body(self, sample_message: NotificationMessage) -> None:
        channel = EmailChannel(
            smtp_host="smtp.example.com",
            from_addr="alerts@example.com",
            to_addrs=["team@example.com"],
        )
        html = channel._build_html_body(sample_message)

        assert "<!DOCTYPE html>" in html
        assert "Test Alert" in html
        assert "checkout_flow" in html

    @patch("smtplib.SMTP")
    def test_send_success(self, mock_smtp: MagicMock, sample_message: NotificationMessage) -> None:
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        mock_server.starttls.return_value = None
        mock_server.login.return_value = None
        mock_server.sendmail.return_value = {}
        mock_server.quit.return_value = None

        channel = EmailChannel(
            smtp_host="smtp.example.com",
            from_addr="alerts@example.com",
            to_addrs=["team@example.com"],
            username="user",
            password="pass",
        )
        result = channel.send(sample_message)
        assert result is True


# ============================================================================
# PagerDuty Channel Tests
# ============================================================================


class TestPagerDutyChannel:
    """Tests for PagerDutyChannel."""

    def test_channel_type(self) -> None:
        channel = PagerDutyChannel(
            routing_key="test-routing-key",
            name="pagerduty-test",
        )
        assert channel.channel_type == ChannelType.PAGERDUTY

    @patch("urllib.request.urlopen")
    def test_send_trigger_event(self, mock_urlopen: MagicMock, sample_message: NotificationMessage) -> None:
        mock_response = MagicMock()
        mock_response.status = 202
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        channel = PagerDutyChannel(
            routing_key="test-routing-key",
            service_name="VenomQA Tests",
        )
        result = channel.send(sample_message)
        assert result is True

    def test_build_payload_structure(self, sample_message: NotificationMessage) -> None:
        channel = PagerDutyChannel(
            routing_key="test-routing-key",
            service_name="VenomQA Tests",
        )
        payload = channel._build_payload(sample_message)

        assert payload["routing_key"] == "test-routing-key"
        assert payload["event_action"] == "trigger"
        assert "dedup_key" in payload
        assert "payload" in payload
        assert payload["payload"]["source"] == "VenomQA Tests"
        assert payload["payload"]["severity"] == "error"  # high -> error

    def test_recovery_event_resolves(self, recovery_message: NotificationMessage) -> None:
        channel = PagerDutyChannel(routing_key="test-routing-key")
        payload = channel._build_payload(recovery_message)
        assert payload["event_action"] == "resolve"

    def test_dedup_key_generation(self, sample_message: NotificationMessage) -> None:
        channel = PagerDutyChannel(routing_key="test-routing-key")
        dedup_key = channel._generate_dedup_key(sample_message)
        assert "venomqa" in dedup_key
        assert "checkout_flow" in dedup_key
        assert "payment" in dedup_key


# ============================================================================
# Custom Webhook Channel Tests
# ============================================================================


class TestCustomWebhookChannel:
    """Tests for CustomWebhookChannel."""

    def test_channel_type(self) -> None:
        channel = CustomWebhookChannel(
            webhook_url="https://api.example.com/notify",
            name="custom-webhook",
        )
        assert channel.channel_type == ChannelType.WEBHOOK

    @patch("urllib.request.urlopen")
    def test_send_with_custom_headers(self, mock_urlopen: MagicMock, sample_message: NotificationMessage) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        channel = CustomWebhookChannel(
            webhook_url="https://api.example.com/notify",
            headers={"Authorization": "Bearer token123"},
        )
        result = channel.send(sample_message)
        assert result is True

        # Verify headers were set
        call_args = mock_urlopen.call_args
        request = call_args[0][0]
        assert request.get_header("Authorization") == "Bearer token123"

    def test_build_payload_with_template(self, sample_message: NotificationMessage) -> None:
        channel = CustomWebhookChannel(
            webhook_url="https://api.example.com/notify",
            payload_template={"service": "venomqa", "env": "production"},
        )
        payload = channel._build_payload(sample_message)

        assert payload["service"] == "venomqa"
        assert payload["env"] == "production"
        assert "venomqa" in payload  # Message data added


# ============================================================================
# Channel Factory Tests
# ============================================================================


class TestChannelFactory:
    """Tests for create_channel factory function."""

    def test_create_slack_channel(self) -> None:
        config = {
            "type": "slack",
            "name": "slack-alerts",
            "webhook_url": "https://hooks.slack.com/test",
            "channel": "#alerts",
            "on": ["failure", "recovery"],
        }
        channel = create_channel(config)
        assert isinstance(channel, SlackChannel)
        assert channel.name == "slack-alerts"
        assert channel.channel == "#alerts"

    def test_create_discord_channel(self) -> None:
        config = {
            "type": "discord",
            "name": "discord-alerts",
            "webhook_url": "https://discord.com/api/webhooks/test",
        }
        channel = create_channel(config)
        assert isinstance(channel, DiscordChannel)

    def test_create_email_channel(self) -> None:
        config = {
            "type": "email",
            "name": "email-alerts",
            "smtp_host": "smtp.example.com",
            "from": "alerts@example.com",
            "to": ["team@example.com"],
        }
        channel = create_channel(config)
        assert isinstance(channel, EmailChannel)

    def test_create_pagerduty_channel(self) -> None:
        config = {
            "type": "pagerduty",
            "name": "oncall",
            "routing_key": "test-key",
        }
        channel = create_channel(config)
        assert isinstance(channel, PagerDutyChannel)

    def test_create_webhook_channel(self) -> None:
        config = {
            "type": "webhook",
            "name": "custom",
            "webhook_url": "https://api.example.com/notify",
            "method": "PUT",
            "headers": {"X-Api-Key": "secret"},
        }
        channel = create_channel(config)
        assert isinstance(channel, CustomWebhookChannel)
        assert channel.method == "PUT"

    def test_unknown_channel_type_raises(self) -> None:
        config = {"type": "unknown", "name": "test"}
        with pytest.raises(ValueError, match="Unknown channel type"):
            create_channel(config)


# ============================================================================
# RateLimiter Tests
# ============================================================================


class TestRateLimiter:
    """Tests for RateLimiter."""

    def test_can_send_first_time(self) -> None:
        limiter = RateLimiter(default_cooldown=60.0)
        assert limiter.can_send("test-key") is True

    def test_cannot_send_during_cooldown(self) -> None:
        limiter = RateLimiter(default_cooldown=60.0)
        limiter.record_send("test-key")
        assert limiter.can_send("test-key") is False

    def test_can_send_after_cooldown(self) -> None:
        limiter = RateLimiter(default_cooldown=0.1)  # 100ms cooldown
        limiter.record_send("test-key")
        time.sleep(0.15)  # Wait for cooldown
        assert limiter.can_send("test-key") is True

    def test_custom_cooldown_per_key(self) -> None:
        limiter = RateLimiter(default_cooldown=60.0)
        limiter.record_send("test-key")
        # Can't send with default cooldown
        assert limiter.can_send("test-key", cooldown=60.0) is False
        # Wait briefly and check with very short custom cooldown
        time.sleep(0.01)  # Wait a tiny bit
        assert limiter.can_send("test-key", cooldown=0.001) is True

    def test_get_remaining_cooldown(self) -> None:
        limiter = RateLimiter(default_cooldown=10.0)
        limiter.record_send("test-key")
        remaining = limiter.get_remaining_cooldown("test-key")
        assert remaining > 0
        assert remaining <= 10.0

    def test_clear(self) -> None:
        limiter = RateLimiter(default_cooldown=60.0)
        limiter.record_send("key1")
        limiter.record_send("key2")
        limiter.clear()
        assert limiter.can_send("key1") is True
        assert limiter.can_send("key2") is True


# ============================================================================
# AlertAggregator Tests
# ============================================================================


class TestAlertAggregator:
    """Tests for AlertAggregator."""

    def test_single_message_returned_immediately(self, sample_message: NotificationMessage) -> None:
        aggregator = AlertAggregator(window_seconds=0.0)  # Instant window
        result = aggregator.add(sample_message)
        # With 0 window, first message triggers immediately
        assert result is not None

    def test_aggregates_similar_messages(self) -> None:
        aggregator = AlertAggregator(window_seconds=60.0)  # Long window
        msg1 = NotificationMessage(
            title="Alert 1",
            body="Body 1",
            event=NotificationEvent.FAILURE,
            severity="high",
            journey_name="test",
        )
        msg2 = NotificationMessage(
            title="Alert 2",
            body="Body 2",
            event=NotificationEvent.FAILURE,
            severity="high",
            journey_name="test",
        )

        # Add messages - should be pending
        result1 = aggregator.add(msg1)
        result2 = aggregator.add(msg2)

        # Both should be pending (None returned)
        assert result1 is None
        assert result2 is None

        # Flush should return aggregated message
        flushed = aggregator.flush()
        assert len(flushed) == 1
        # Check the aggregated message format - "[2 alerts]" or "2 similar alerts"
        assert "2" in flushed[0].title or "2" in flushed[0].body

    def test_flush_clears_pending(self) -> None:
        aggregator = AlertAggregator(window_seconds=60.0)
        msg = NotificationMessage(title="Test", body="Body", event=NotificationEvent.FAILURE)
        aggregator.add(msg)

        flushed1 = aggregator.flush()
        flushed2 = aggregator.flush()

        assert len(flushed1) == 1
        assert len(flushed2) == 0


# ============================================================================
# AlertCondition Tests
# ============================================================================


class TestAlertCondition:
    """Tests for AlertCondition."""

    def test_journey_failure_trigger(self, failed_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="journey_failure",
            trigger=AlertTrigger.JOURNEY_FAILURE,
            channels=["slack"],
        )
        state, message = alert.check(failed_results)
        assert state == AlertState.FIRING
        assert message is not None
        assert "Failed" in message.title

    def test_journey_failure_no_trigger_on_success(self, sample_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="journey_failure",
            trigger=AlertTrigger.JOURNEY_FAILURE,
            channels=["slack"],
        )
        state, message = alert.check(sample_results)
        assert state == AlertState.OK
        assert message is None

    def test_step_failure_trigger(self, failed_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="step_failure",
            trigger=AlertTrigger.STEP_FAILURE,
            channels=["slack"],
        )
        state, message = alert.check(failed_results)
        assert state == AlertState.FIRING
        assert message is not None

    def test_failure_rate_trigger(self, mixed_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="high_failure_rate",
            trigger=AlertTrigger.FAILURE_RATE,
            threshold=25.0,  # 25% threshold
            channels=["slack"],
        )
        # mixed_results has 1 pass, 1 fail = 50% failure rate
        state, message = alert.check(mixed_results)
        assert state == AlertState.FIRING
        assert message is not None
        assert "Failure Rate" in message.title

    def test_failure_rate_no_trigger_below_threshold(self, sample_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="high_failure_rate",
            trigger=AlertTrigger.FAILURE_RATE,
            threshold=50.0,
            channels=["slack"],
        )
        state, message = alert.check(sample_results)
        assert state == AlertState.OK

    def test_latency_trigger(self, sample_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="slow_response",
            trigger=AlertTrigger.P99_LATENCY,
            threshold=50.0,  # 50ms threshold
            channels=["slack"],
        )
        # sample_results has durations > 50ms
        state, message = alert.check(sample_results)
        assert state == AlertState.FIRING

    def test_recovery_trigger(self, sample_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="recovery",
            trigger=AlertTrigger.RECOVERY,
            channels=["slack"],
        )
        # Check with previous state as FIRING
        state, message = alert.check(sample_results, previous_state=AlertState.FIRING)
        assert state == AlertState.OK
        assert message is not None
        assert "Recovered" in message.title

    def test_disabled_alert(self, failed_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="disabled_alert",
            trigger=AlertTrigger.JOURNEY_FAILURE,
            channels=["slack"],
            enabled=False,
        )
        state, message = alert.check(failed_results)
        assert state == AlertState.OK
        assert message is None


# ============================================================================
# AlertManager Tests
# ============================================================================


class TestAlertManager:
    """Tests for AlertManager."""

    def test_evaluate_triggers_alerts(self, failed_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="failure",
            trigger=AlertTrigger.JOURNEY_FAILURE,
            channels=["slack"],
            cooldown_seconds=0.0,  # No cooldown for testing
        )
        manager = AlertManager(
            alerts=[alert],
            rate_limiter=RateLimiter(default_cooldown=0.0),
            aggregator=AlertAggregator(window_seconds=0.0),
        )

        triggered = manager.evaluate(failed_results)
        assert len(triggered) > 0

    def test_rate_limiting_prevents_spam(self, failed_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="failure",
            trigger=AlertTrigger.JOURNEY_FAILURE,
            channels=["slack"],
            cooldown_seconds=60.0,
        )
        manager = AlertManager(alerts=[alert])

        # First evaluation triggers
        triggered1 = manager.evaluate(failed_results)
        # Second evaluation is rate limited
        triggered2 = manager.evaluate(failed_results)

        assert len(triggered1) > 0
        assert len(triggered2) == 0  # Rate limited

    def test_get_state(self, failed_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="failure",
            trigger=AlertTrigger.JOURNEY_FAILURE,
            channels=["slack"],
        )
        manager = AlertManager(
            alerts=[alert],
            aggregator=AlertAggregator(window_seconds=0.0),
        )

        # Initial state
        assert manager.get_state("failure") == AlertState.OK

        # After evaluation
        manager.evaluate(failed_results)
        assert manager.get_state("failure") == AlertState.FIRING

    def test_reset(self, failed_results: list[JourneyResult]) -> None:
        alert = AlertCondition(
            name="failure",
            trigger=AlertTrigger.JOURNEY_FAILURE,
            channels=["slack"],
        )
        manager = AlertManager(alerts=[alert])
        manager.evaluate(failed_results)

        manager.reset()

        assert manager.get_state("failure") == AlertState.OK


# ============================================================================
# NotificationConfig Tests
# ============================================================================


class TestNotificationConfig:
    """Tests for NotificationConfig."""

    def test_from_dict(self) -> None:
        data = {
            "channels": [
                {"type": "slack", "webhook_url": "https://hooks.slack.com/test"},
            ],
            "alerts": [
                {"name": "failure", "condition": "failure_rate > 10%", "channels": ["slack"]},
            ],
            "rate_limit_seconds": 120.0,
            "enabled": True,
        }
        config = NotificationConfig.from_dict(data)

        assert len(config.channels) == 1
        assert len(config.alerts) == 1
        assert config.rate_limit_seconds == 120.0
        assert config.enabled is True

    def test_default_values(self) -> None:
        config = NotificationConfig()
        assert config.channels == []
        assert config.alerts == []
        assert config.rate_limit_seconds == 300.0
        assert config.enabled is True


# ============================================================================
# NotificationManager Tests
# ============================================================================


class TestNotificationManager:
    """Tests for NotificationManager."""

    def test_initialization_with_channels(self) -> None:
        slack = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            name="slack",
        )
        manager = NotificationManager(channels=[slack])
        assert "slack" in manager.channels

    def test_add_and_remove_channel(self) -> None:
        manager = NotificationManager()
        slack = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            name="slack",
        )

        manager.add_channel(slack)
        assert "slack" in manager.channels

        result = manager.remove_channel("slack")
        assert result is True
        assert "slack" not in manager.channels

    def test_remove_nonexistent_channel(self) -> None:
        manager = NotificationManager()
        result = manager.remove_channel("nonexistent")
        assert result is False

    def test_add_and_remove_alert(self) -> None:
        manager = NotificationManager()
        alert = AlertCondition(
            name="test",
            trigger=AlertTrigger.JOURNEY_FAILURE,
            channels=["slack"],
        )

        manager.add_alert(alert)
        assert len(manager.alert_manager.alerts) == 1

        result = manager.remove_alert("test")
        assert result is True
        assert len(manager.alert_manager.alerts) == 0

    @patch("urllib.request.urlopen")
    def test_send_message_to_specific_channels(self, mock_urlopen: MagicMock, sample_message: NotificationMessage) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        slack = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            name="slack",
        )
        manager = NotificationManager(channels=[slack])

        results = manager.send_message(sample_message, channels=["slack"])
        assert len(results) == 1
        assert results[0] == ("slack", True)

    @patch("urllib.request.urlopen")
    def test_process_results_triggers_notifications(
        self, mock_urlopen: MagicMock, failed_results: list[JourneyResult]
    ) -> None:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        slack = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            name="slack",
        )
        alert = AlertCondition(
            name="failure",
            trigger=AlertTrigger.JOURNEY_FAILURE,
            channels=["slack"],
            cooldown_seconds=0.0,
        )
        config = NotificationConfig(rate_limit_seconds=0.0, aggregate_window_seconds=0.0)
        manager = NotificationManager(
            channels=[slack],
            alerts=[alert],
            config=config,
        )

        results = manager.process_results(failed_results)
        assert len(results) > 0

    def test_reset(self) -> None:
        manager = NotificationManager()
        manager._previous_success = False
        manager.reset()
        assert manager._previous_success is None


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestCreateNotificationManagerFromConfig:
    """Tests for create_notification_manager_from_config."""

    def test_creates_manager_from_config(self) -> None:
        config = {
            "notifications": {
                "channels": [
                    {
                        "type": "slack",
                        "name": "slack",
                        "webhook_url": "https://hooks.slack.com/test",
                        "on": ["failure"],
                    },
                ],
                "alerts": [
                    {
                        "name": "failures",
                        "condition": "failure_rate > 10%",
                        "channels": ["slack"],
                    },
                ],
            }
        }
        manager = create_notification_manager_from_config(config)

        assert "slack" in manager.channels
        assert len(manager.alert_manager.alerts) == 1

    def test_handles_empty_config(self) -> None:
        config: dict[str, Any] = {}
        manager = create_notification_manager_from_config(config)
        assert len(manager.channels) == 0

    def test_includes_report_url(self) -> None:
        config = {"notifications": {"channels": []}}
        manager = create_notification_manager_from_config(
            config, report_url="https://reports.example.com/123"
        )
        assert manager.report_url == "https://reports.example.com/123"


# ============================================================================
# Integration Tests
# ============================================================================


class TestNotificationIntegration:
    """Integration tests for the notification system."""

    @patch("urllib.request.urlopen")
    def test_full_notification_flow(self, mock_urlopen: MagicMock, failed_results: list[JourneyResult]) -> None:
        """Test complete flow from results to notification."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        config = {
            "notifications": {
                "channels": [
                    {
                        "type": "slack",
                        "name": "slack",
                        "webhook_url": "https://hooks.slack.com/test",
                        "on": ["failure", "recovery"],
                    },
                ],
                "alerts": [
                    {
                        "name": "failure",
                        "trigger": "journey_failure",
                        "channels": ["slack"],
                        "cooldown_seconds": 0.0,
                    },
                ],
                "rate_limit_seconds": 0.0,
                "aggregate_window_seconds": 0.0,
            }
        }

        manager = create_notification_manager_from_config(config)
        results = manager.process_results(failed_results, report_url="https://example.com/report")

        # Should have sent a notification
        assert len(results) > 0
        assert results[0][1] is True  # Success

    @patch("urllib.request.urlopen")
    def test_recovery_detection(
        self,
        mock_urlopen: MagicMock,
        failed_results: list[JourneyResult],
        sample_results: list[JourneyResult],
    ) -> None:
        """Test that recovery notifications are sent."""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        slack = SlackChannel(
            webhook_url="https://hooks.slack.com/test",
            name="slack",
            events=[NotificationEvent.FAILURE, NotificationEvent.RECOVERY],
        )
        manager = NotificationManager(channels=[slack])

        # First run fails
        manager.process_results(failed_results)
        # Second run succeeds - should send recovery
        results = manager.process_results(sample_results)

        # Should have sent recovery notification
        assert len(results) > 0
