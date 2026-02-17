"""Integration tests for retry and timeout features.

These tests demonstrate the full usage of the retry and timeout
handling features in realistic scenarios.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from venomqa.core.models import Journey, Step
from venomqa.errors import (
    BackoffStrategy,
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    RetryConfig,
    RetryExhaustedError,
    RetryPolicy,
    StepTimeoutError,
    WaitTimeoutError,
)
from venomqa.errors.retry import execute_with_timeout


class TestRetryPolicyIntegration:
    """Integration tests for retry policies."""

    def test_retry_with_yaml_config(self) -> None:
        """Test using retry policy configured from YAML-like dict."""
        # Simulate loading config from venomqa.yaml
        yaml_config = {
            "retry": {
                "max_attempts": 3,
                "backoff": "exponential",
                "initial_delay": 0.01,
                "max_delay": 1.0,
                "retry_on": [500, 502, 503, 504, "ConnectionError", "Timeout"],
            }
        }

        config = RetryConfig.from_yaml(yaml_config)
        policy = RetryPolicy(config)

        # Simulate a flaky API call that succeeds after 2 failures
        call_count = [0]

        def flaky_api_call() -> dict[str, str]:
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("Connection reset")
            return {"status": "success"}

        result = policy.execute(flaky_api_call)
        assert result["status"] == "success"
        assert call_count[0] == 3

    def test_retry_exhaustion_with_good_error_message(self) -> None:
        """Test that retry exhaustion includes useful info."""
        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
        )
        policy = RetryPolicy(config)

        with pytest.raises(RetryExhaustedError) as exc_info:
            policy.execute(lambda: (_ for _ in ()).throw(ValueError("API error")))

        error = exc_info.value
        assert error.attempts == 3
        assert error.last_error is not None
        assert "API error" in str(error.last_error)


class TestCircuitBreakerIntegration:
    """Integration tests for circuit breakers."""

    def setup_method(self) -> None:
        """Reset circuit breaker registry before each test."""
        CircuitBreakerRegistry.reset()

    def test_service_specific_circuit_breakers(self) -> None:
        """Test using different circuit breakers for different services."""
        registry = CircuitBreakerRegistry.get_instance()

        # Configure circuit breakers for different services
        registry.configure({
            "circuit_breakers": {
                "payment-api": {
                    "failure_threshold": 2,
                    "recovery_timeout": 0.1,
                },
                "inventory-api": {
                    "failure_threshold": 5,
                    "recovery_timeout": 0.5,
                },
            }
        })

        payment_breaker = registry.get_or_create("payment-api")
        inventory_breaker = registry.get_or_create("inventory-api")

        # Trip the payment breaker
        for _ in range(2):
            try:
                payment_breaker.execute(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass

        # Payment breaker should be open
        assert payment_breaker.is_open

        # But inventory breaker should still be closed
        assert inventory_breaker.is_closed

        # Trying to use payment API should fail with CircuitOpenError
        with pytest.raises(CircuitOpenError) as exc_info:
            payment_breaker.execute(lambda: "should not run")

        assert "payment-api" in str(exc_info.value)

    def test_circuit_breaker_recovery(self) -> None:
        """Test that circuit breaker recovers after timeout."""
        breaker = CircuitBreaker(
            name="test-service",
            failure_threshold=1,
            recovery_timeout=0.1,
        )

        # Trip the breaker
        try:
            breaker.execute(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass

        assert breaker.is_open

        # Wait for recovery timeout
        time.sleep(0.15)

        # Should be half-open now, successful call closes it
        result = breaker.execute(lambda: "recovered")
        assert result == "recovered"
        assert breaker.is_closed


class TestTimeoutIntegration:
    """Integration tests for timeout handling."""

    def test_step_timeout_with_detailed_error(self) -> None:
        """Test that step timeout errors include useful information."""
        def slow_operation() -> str:
            time.sleep(1.0)
            return "done"

        with pytest.raises(StepTimeoutError) as exc_info:
            execute_with_timeout(
                operation=slow_operation,
                timeout=0.1,
                operation_description="fetching user profile",
            )

        error = exc_info.value
        assert error.timeout_seconds == 0.1
        assert error.elapsed_seconds is not None
        assert "fetching user profile" in str(error)

        # Check suggestion is helpful
        suggestion = error.suggestion
        assert "timeout" in suggestion.lower()

    def test_step_level_timeout_in_journey(self) -> None:
        """Test step-level timeout configuration."""
        call_times: list[float] = []

        def fast_action(client: Any, ctx: Any) -> dict[str, str]:
            call_times.append(time.time())
            return {"status": "ok"}

        def slow_action(client: Any, ctx: Any) -> dict[str, str]:
            time.sleep(0.5)
            call_times.append(time.time())
            return {"status": "ok"}

        # Create journey with step-level timeout
        journey = Journey(
            name="test_timeout",
            steps=[
                Step(
                    name="fast_step",
                    action=fast_action,
                    timeout=1.0,
                ),
                Step(
                    name="slow_step_with_timeout",
                    action=slow_action,
                    timeout=0.1,  # This should timeout
                ),
            ],
        )

        # Verify step has timeout configured
        assert journey.steps[1].timeout == 0.1


class TestWaitPollIntegration:
    """Integration tests for wait/poll functionality."""

    def test_wait_timeout_with_detailed_error(self) -> None:
        """Test that wait timeout errors are descriptive."""
        from venomqa.tools.wait import poll_until_sync

        counter = [0]

        def fetch_status() -> dict[str, str]:
            counter[0] += 1
            return {"status": "pending", "progress": f"{counter[0] * 10}%"}

        with pytest.raises(WaitTimeoutError) as exc_info:
            poll_until_sync(
                fetcher=fetch_status,
                condition=lambda x: x["status"] == "completed",
                timeout=0.3,
                interval=0.05,
                description="order status to be completed",
            )

        error = exc_info.value
        assert "order status" in str(error)
        assert error.poll_attempts > 0
        assert error.last_value is not None


class TestCombinedResiliencePattern:
    """Test combining retry + circuit breaker + timeout."""

    def setup_method(self) -> None:
        """Reset circuit breaker registry."""
        CircuitBreakerRegistry.reset()

    def test_full_resilience_stack(self) -> None:
        """Test using retry + circuit breaker together."""
        registry = CircuitBreakerRegistry.get_instance()
        breaker = registry.get_or_create(
            "api-service",
            failure_threshold=3,
            recovery_timeout=0.1,
        )

        config = RetryConfig(
            max_attempts=1,  # No actual retry, just 1 attempt
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
        )
        policy = RetryPolicy(config)

        call_count = [0]
        should_succeed = [False]

        def api_call() -> str:
            call_count[0] += 1
            if not should_succeed[0]:
                raise ValueError("API temporarily unavailable")
            return "success"

        # First attempt: fails, circuit breaker counts 1 failure
        with pytest.raises(RetryExhaustedError):
            breaker.execute(lambda: policy.execute(api_call))

        # Second attempt: fails, circuit breaker counts 2 failures
        with pytest.raises(RetryExhaustedError):
            breaker.execute(lambda: policy.execute(api_call))

        # Third attempt: fails, circuit breaker counts 3 failures -> OPEN
        with pytest.raises(RetryExhaustedError):
            breaker.execute(lambda: policy.execute(api_call))

        assert breaker.is_open

        # Fourth attempt: circuit breaker rejects immediately
        with pytest.raises(CircuitOpenError):
            breaker.execute(lambda: policy.execute(api_call))

        # Wait for recovery
        time.sleep(0.15)

        # Now make calls succeed
        should_succeed[0] = True

        # Recovery attempt should work
        result = breaker.execute(lambda: policy.execute(api_call))
        assert result == "success"
        assert breaker.is_closed


class TestYAMLConfigurationWorkflow:
    """Test the YAML configuration workflow."""

    def test_complete_yaml_config_workflow(self) -> None:
        """Test loading and using a complete YAML configuration."""
        # Simulate YAML config file content
        yaml_config = {
            "retry": {
                "max_attempts": 3,
                "backoff": "exponential",
                "initial_delay": 0.01,
                "max_delay": 1.0,
                "retry_on": [500, 502, 503, 504, "ConnectionError"],
            },
            "circuit_breakers": {
                "default": {
                    "failure_threshold": 5,
                    "recovery_timeout": 30.0,
                },
                "payment-service": {
                    "failure_threshold": 3,
                    "recovery_timeout": 15.0,
                },
            },
        }

        # Load retry config
        retry_config = RetryConfig.from_yaml(yaml_config["retry"])
        assert retry_config.max_attempts == 3
        assert retry_config.backoff_strategy == BackoffStrategy.EXPONENTIAL
        assert ConnectionError in retry_config.retryable_exceptions
        assert 500 in retry_config.retryable_status_codes

        # Load circuit breaker config
        CircuitBreakerRegistry.reset()
        registry = CircuitBreakerRegistry.get_instance()
        registry.configure({"circuit_breakers": yaml_config["circuit_breakers"]})

        payment_breaker = registry.get_or_create("payment-service")
        assert payment_breaker.failure_threshold == 3
        assert payment_breaker.recovery_timeout == 15.0

    def test_config_round_trip(self) -> None:
        """Test that config can be converted to and from YAML."""
        original = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=60.0,
            backoff_strategy=BackoffStrategy.LINEAR,
            retryable_exceptions=(ConnectionError, TimeoutError),
            retryable_status_codes={500, 502, 503},
        )

        # Convert to YAML dict
        yaml_dict = original.to_yaml()

        # Recreate from YAML dict
        restored = RetryConfig.from_yaml(yaml_dict)

        assert restored.max_attempts == original.max_attempts
        assert restored.base_delay == original.base_delay
        assert restored.max_delay == original.max_delay
        assert restored.backoff_strategy == original.backoff_strategy
