"""Tests for retry and timeout handling in VenomQA.

This module tests:
- Configurable retry policies (YAML-based)
- Step-level and journey-level timeouts
- Wait/polling helpers
- Circuit breaker per service
- Timeout error messages
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from venomqa.errors import (
    BackoffStrategy,
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
    CircuitStats,
    RetryConfig,
    RetryExhaustedError,
    RetryPolicy,
    ResilientClient,
    StepTimeoutError,
    WaitTimeoutError,
    create_default_circuit_breaker,
    create_default_retry_policy,
    execute_with_timeout,
    with_timeout,
)
from venomqa.tools.wait import (
    poll_until_sync,
    wait_for_sync,
)


class TestRetryConfig:
    """Tests for RetryConfig class."""

    def test_default_config(self) -> None:
        """Test default retry configuration."""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_strategy == BackoffStrategy.EXPONENTIAL_FULL_JITTER

    def test_from_yaml_basic(self) -> None:
        """Test creating config from YAML dict."""
        yaml_config = {
            "max_attempts": 5,
            "backoff": "exponential",
            "initial_delay": 2.0,
            "max_delay": 30.0,
        }
        config = RetryConfig.from_yaml(yaml_config)
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 30.0
        assert config.backoff_strategy == BackoffStrategy.EXPONENTIAL

    def test_from_yaml_with_retry_key(self) -> None:
        """Test creating config from nested YAML with 'retry' key."""
        yaml_config = {
            "retry": {
                "max_attempts": 3,
                "backoff": "linear",
                "initial_delay": 1.0,
            }
        }
        config = RetryConfig.from_yaml(yaml_config)
        assert config.max_attempts == 3
        assert config.backoff_strategy == BackoffStrategy.LINEAR

    def test_from_yaml_with_retry_on_status_codes(self) -> None:
        """Test parsing retry_on with HTTP status codes."""
        yaml_config = {
            "max_attempts": 3,
            "retry_on": [500, 502, 503, 504, 429],
        }
        config = RetryConfig.from_yaml(yaml_config)
        assert 500 in config.retryable_status_codes
        assert 502 in config.retryable_status_codes
        assert 429 in config.retryable_status_codes

    def test_from_yaml_with_retry_on_exceptions(self) -> None:
        """Test parsing retry_on with exception types."""
        yaml_config = {
            "max_attempts": 3,
            "retry_on": ["ConnectionError", "Timeout", 500],
        }
        config = RetryConfig.from_yaml(yaml_config)
        assert ConnectionError in config.retryable_exceptions
        assert TimeoutError in config.retryable_exceptions
        assert 500 in config.retryable_status_codes

    def test_from_yaml_backoff_strategies(self) -> None:
        """Test various backoff strategy names."""
        strategies = [
            ("fixed", BackoffStrategy.FIXED),
            ("linear", BackoffStrategy.LINEAR),
            ("exponential", BackoffStrategy.EXPONENTIAL),
            ("exp", BackoffStrategy.EXPONENTIAL),
            ("exponential_full_jitter", BackoffStrategy.EXPONENTIAL_FULL_JITTER),
        ]
        for name, expected in strategies:
            config = RetryConfig.from_yaml({"backoff": name})
            assert config.backoff_strategy == expected

    def test_to_yaml(self) -> None:
        """Test converting config to YAML dict."""
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=30.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
        )
        yaml_dict = config.to_yaml()
        assert yaml_dict["max_attempts"] == 5
        assert yaml_dict["initial_delay"] == 2.0
        assert yaml_dict["backoff"] == "exponential"


class TestBackoffStrategy:
    """Tests for BackoffStrategy enum."""

    def test_from_string_valid(self) -> None:
        """Test creating strategy from valid string."""
        assert BackoffStrategy.from_string("fixed") == BackoffStrategy.FIXED
        assert BackoffStrategy.from_string("LINEAR") == BackoffStrategy.LINEAR
        assert BackoffStrategy.from_string("Exponential") == BackoffStrategy.EXPONENTIAL

    def test_from_string_invalid(self) -> None:
        """Test creating strategy from invalid string raises error."""
        with pytest.raises(ValueError, match="Unknown backoff strategy"):
            BackoffStrategy.from_string("invalid")


class TestRetryPolicy:
    """Tests for RetryPolicy class."""

    def test_calculate_delay_fixed(self) -> None:
        """Test fixed delay calculation."""
        config = RetryConfig(
            backoff_strategy=BackoffStrategy.FIXED,
            base_delay=2.0,
        )
        policy = RetryPolicy(config)
        assert policy.calculate_delay(0) == 2.0
        assert policy.calculate_delay(1) == 2.0
        assert policy.calculate_delay(5) == 2.0

    def test_calculate_delay_linear(self) -> None:
        """Test linear delay calculation."""
        config = RetryConfig(
            backoff_strategy=BackoffStrategy.LINEAR,
            base_delay=1.0,
        )
        policy = RetryPolicy(config)
        assert policy.calculate_delay(0) == 1.0
        assert policy.calculate_delay(1) == 2.0
        assert policy.calculate_delay(2) == 3.0

    def test_calculate_delay_exponential(self) -> None:
        """Test exponential delay calculation."""
        config = RetryConfig(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            base_delay=1.0,
            exponential_base=2.0,
        )
        policy = RetryPolicy(config)
        assert policy.calculate_delay(0) == 1.0
        assert policy.calculate_delay(1) == 2.0
        assert policy.calculate_delay(2) == 4.0

    def test_calculate_delay_respects_max(self) -> None:
        """Test that delay is capped at max_delay."""
        config = RetryConfig(
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            base_delay=1.0,
            max_delay=5.0,
        )
        policy = RetryPolicy(config)
        # Exponential would be 16.0 for attempt 4, but capped at 5.0
        assert policy.calculate_delay(4) == 5.0

    def test_execute_success(self) -> None:
        """Test successful execution on first try."""
        policy = RetryPolicy()
        result = policy.execute(lambda: "success")
        assert result == "success"

    def test_execute_retry_then_success(self) -> None:
        """Test retrying until success."""
        attempts = [0]

        def flaky_operation() -> str:
            attempts[0] += 1
            if attempts[0] < 3:
                raise ConnectionError("Flaky")
            return "success"

        config = RetryConfig(
            max_attempts=5,
            base_delay=0.01,
            retryable_exceptions=(ConnectionError,),
        )
        policy = RetryPolicy(config)
        result = policy.execute(flaky_operation)
        assert result == "success"
        assert attempts[0] == 3

    def test_execute_exhausted(self) -> None:
        """Test raising RetryExhaustedError when all attempts fail."""
        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
        )
        policy = RetryPolicy(config)

        with pytest.raises(RetryExhaustedError) as exc_info:
            policy.execute(lambda: (_ for _ in ()).throw(ValueError("Always fails")))

        assert exc_info.value.attempts == 3

    def test_execute_non_retryable_exception(self) -> None:
        """Test that non-retryable exceptions are raised immediately."""
        config = RetryConfig(
            max_attempts=5,
            retryable_exceptions=(ConnectionError,),
        )
        policy = RetryPolicy(config)

        with pytest.raises(ValueError):
            policy.execute(lambda: (_ for _ in ()).throw(ValueError("Not retryable")))

    def test_on_retry_callback(self) -> None:
        """Test on_retry callback is called."""
        callback_calls: list[tuple[int, Exception, float]] = []

        def on_retry(attempt: int, exc: Exception, delay: float) -> None:
            callback_calls.append((attempt, exc, delay))

        attempts = [0]

        def flaky_operation() -> str:
            attempts[0] += 1
            if attempts[0] < 3:
                raise ConnectionError("Flaky")
            return "success"

        config = RetryConfig(
            max_attempts=5,
            base_delay=0.01,
            retryable_exceptions=(ConnectionError,),
            on_retry=on_retry,
        )
        policy = RetryPolicy(config)
        policy.execute(flaky_operation)

        assert len(callback_calls) == 2
        assert callback_calls[0][0] == 1  # First retry
        assert callback_calls[1][0] == 2  # Second retry


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    def test_initial_state_closed(self) -> None:
        """Test circuit starts in closed state."""
        breaker = CircuitBreaker()
        assert breaker.is_closed
        assert not breaker.is_open
        assert breaker.state == CircuitState.CLOSED

    def test_successful_execution(self) -> None:
        """Test successful execution keeps circuit closed."""
        breaker = CircuitBreaker()
        result = breaker.execute(lambda: "success")
        assert result == "success"
        assert breaker.is_closed

    def test_trips_after_threshold(self) -> None:
        """Test circuit opens after failure threshold."""
        breaker = CircuitBreaker(failure_threshold=3)

        for _ in range(3):
            try:
                breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
            except ValueError:
                pass

        assert breaker.is_open

    def test_open_circuit_rejects_requests(self) -> None:
        """Test open circuit rejects requests."""
        breaker = CircuitBreaker(failure_threshold=1)

        try:
            breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
        except ValueError:
            pass

        with pytest.raises(CircuitOpenError):
            breaker.execute(lambda: "should not run")

    def test_half_open_after_recovery_timeout(self) -> None:
        """Test circuit transitions to half-open after recovery timeout."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        try:
            breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
        except ValueError:
            pass

        assert breaker.is_open
        time.sleep(0.15)  # Wait for recovery timeout

        # Should be half-open now
        assert breaker.state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self) -> None:
        """Test successful execution in half-open closes circuit."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        try:
            breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
        except ValueError:
            pass

        time.sleep(0.15)  # Wait for recovery timeout
        assert breaker.state == CircuitState.HALF_OPEN

        # Successful execution should close the circuit
        result = breaker.execute(lambda: "recovered")
        assert result == "recovered"
        assert breaker.is_closed

    def test_half_open_failure_reopens_circuit(self) -> None:
        """Test failure in half-open reopens circuit."""
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)

        try:
            breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
        except ValueError:
            pass

        time.sleep(0.15)  # Wait for recovery timeout
        assert breaker.state == CircuitState.HALF_OPEN

        # Failure should reopen the circuit
        try:
            breaker.execute(lambda: (_ for _ in ()).throw(ValueError("still failing")))
        except ValueError:
            pass

        assert breaker.is_open

    def test_reset(self) -> None:
        """Test manual reset."""
        breaker = CircuitBreaker(failure_threshold=1)

        try:
            breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
        except ValueError:
            pass

        assert breaker.is_open
        breaker.reset()
        assert breaker.is_closed

    def test_trip(self) -> None:
        """Test manual trip."""
        breaker = CircuitBreaker()
        assert breaker.is_closed
        breaker.trip()
        assert breaker.is_open

    def test_named_breaker(self) -> None:
        """Test circuit breaker with name."""
        breaker = CircuitBreaker(name="payment-service")
        assert breaker.name == "payment-service"

    def test_get_stats(self) -> None:
        """Test getting statistics."""
        breaker = CircuitBreaker(name="test-service")

        breaker.execute(lambda: "success")
        try:
            breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
        except ValueError:
            pass

        stats = breaker.get_stats()
        assert stats["name"] == "test-service"
        assert stats["state"] == "closed"
        assert stats["stats"]["successes"] == 1
        assert stats["stats"]["failures"] == 1

    def test_state_change_callback(self) -> None:
        """Test state change callback."""
        transitions: list[tuple[CircuitState, CircuitState]] = []

        def on_change(old: CircuitState, new: CircuitState) -> None:
            transitions.append((old, new))

        breaker = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0.1,
            on_state_change=on_change,
        )

        try:
            breaker.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))
        except ValueError:
            pass

        assert len(transitions) == 1
        assert transitions[0] == (CircuitState.CLOSED, CircuitState.OPEN)


class TestCircuitBreakerRegistry:
    """Tests for CircuitBreakerRegistry class."""

    def setup_method(self) -> None:
        """Reset registry before each test."""
        CircuitBreakerRegistry.reset()

    def test_get_instance_singleton(self) -> None:
        """Test singleton pattern."""
        registry1 = CircuitBreakerRegistry.get_instance()
        registry2 = CircuitBreakerRegistry.get_instance()
        assert registry1 is registry2

    def test_get_or_create_new(self) -> None:
        """Test creating new circuit breaker."""
        registry = CircuitBreakerRegistry.get_instance()
        breaker = registry.get_or_create("test-service")
        assert breaker is not None
        assert breaker.name == "test-service"

    def test_get_or_create_existing(self) -> None:
        """Test getting existing circuit breaker."""
        registry = CircuitBreakerRegistry.get_instance()
        breaker1 = registry.get_or_create("test-service")
        breaker2 = registry.get_or_create("test-service")
        assert breaker1 is breaker2

    def test_get_or_create_with_config(self) -> None:
        """Test creating with custom config."""
        registry = CircuitBreakerRegistry.get_instance()
        breaker = registry.get_or_create(
            "custom-service",
            failure_threshold=10,
            recovery_timeout=60.0,
        )
        assert breaker.failure_threshold == 10
        assert breaker.recovery_timeout == 60.0

    def test_configure_from_yaml(self) -> None:
        """Test configuring registry from YAML."""
        registry = CircuitBreakerRegistry.get_instance()
        registry.configure({
            "circuit_breakers": {
                "payment-service": {
                    "failure_threshold": 3,
                    "recovery_timeout": 15.0,
                },
                "inventory-service": {
                    "failure_threshold": 5,
                    "recovery_timeout": 30.0,
                },
            }
        })

        payment_breaker = registry.get_or_create("payment-service")
        assert payment_breaker.failure_threshold == 3
        assert payment_breaker.recovery_timeout == 15.0

    def test_get_open_circuits(self) -> None:
        """Test getting list of open circuits."""
        registry = CircuitBreakerRegistry.get_instance()
        breaker1 = registry.get_or_create("service-a", failure_threshold=1)
        breaker2 = registry.get_or_create("service-b", failure_threshold=1)
        registry.get_or_create("service-c")

        # Trip service-a and service-b
        breaker1.trip()
        breaker2.trip()

        open_circuits = registry.get_open_circuits()
        assert "service-a" in open_circuits
        assert "service-b" in open_circuits
        assert "service-c" not in open_circuits

    def test_reset_all(self) -> None:
        """Test resetting all circuit breakers."""
        registry = CircuitBreakerRegistry.get_instance()
        breaker1 = registry.get_or_create("service-a", failure_threshold=1)
        breaker2 = registry.get_or_create("service-b", failure_threshold=1)

        breaker1.trip()
        breaker2.trip()

        assert breaker1.is_open
        assert breaker2.is_open

        registry.reset_all()

        assert breaker1.is_closed
        assert breaker2.is_closed

    def test_get_all_stats(self) -> None:
        """Test getting stats for all circuit breakers."""
        registry = CircuitBreakerRegistry.get_instance()
        registry.get_or_create("service-a")
        registry.get_or_create("service-b")

        stats = registry.get_all_stats()
        assert "service-a" in stats
        assert "service-b" in stats


class TestResilientClient:
    """Tests for ResilientClient class."""

    def test_execute_with_both(self) -> None:
        """Test execution with retry and circuit breaker."""
        policy = RetryPolicy(RetryConfig(max_attempts=3, base_delay=0.01))
        breaker = CircuitBreaker(failure_threshold=5)
        client = ResilientClient(policy, breaker)

        result = client.execute(lambda: "success")
        assert result == "success"

    def test_circuit_opens_after_retry_exhaustions(self) -> None:
        """Test that circuit opens after multiple retry exhaustions."""
        # Use short retry attempts so each call fails quickly
        policy = RetryPolicy(RetryConfig(
            max_attempts=1,  # Fail immediately without retry
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
        ))
        breaker = CircuitBreaker(failure_threshold=2)
        client = ResilientClient(policy, breaker)

        # First call - fails and counts as 1 circuit breaker failure
        # The retry policy raises RetryExhaustedError after retries fail
        with pytest.raises(RetryExhaustedError):
            client.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))

        # Second call - fails and counts as 2 circuit breaker failures
        with pytest.raises(RetryExhaustedError):
            client.execute(lambda: (_ for _ in ()).throw(ValueError("fail")))

        # Circuit should now be open after 2 failures
        assert breaker.is_open

        # Third call should be rejected by circuit breaker
        with pytest.raises(CircuitOpenError):
            client.execute(lambda: "should not run")


class TestStepTimeoutError:
    """Tests for StepTimeoutError class."""

    def test_basic_error(self) -> None:
        """Test basic error creation."""
        error = StepTimeoutError(
            step_name="fetch_user",
            timeout_seconds=10.0,
            elapsed_seconds=10.5,
        )
        assert "fetch_user" in str(error)
        assert "10.0" in str(error)

    def test_with_description(self) -> None:
        """Test error with operation description."""
        error = StepTimeoutError(
            step_name="process_order",
            timeout_seconds=30.0,
            elapsed_seconds=30.2,
            operation_description="processing order #123",
        )
        assert "processing order #123" in str(error)

    def test_suggestion(self) -> None:
        """Test suggestion property."""
        error = StepTimeoutError(
            step_name="fast_op",
            timeout_seconds=5.0,
        )
        suggestion = error.suggestion
        assert "5" in suggestion or "timeout" in suggestion.lower()

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        error = StepTimeoutError(
            step_name="test_step",
            timeout_seconds=10.0,
            elapsed_seconds=10.5,
        )
        data = error.to_dict()
        assert data["step_name"] == "test_step"
        assert data["timeout_seconds"] == 10.0


class TestWaitTimeoutError:
    """Tests for WaitTimeoutError class."""

    def test_basic_error(self) -> None:
        """Test basic error creation."""
        error = WaitTimeoutError(
            condition_description="order status to be 'shipped'",
            timeout_seconds=60.0,
            elapsed_seconds=60.5,
            poll_attempts=30,
        )
        assert "shipped" in str(error)
        assert "60" in str(error)

    def test_with_values(self) -> None:
        """Test error with last/expected values."""
        error = WaitTimeoutError(
            condition_description="status check",
            timeout_seconds=30.0,
            elapsed_seconds=30.1,
            last_value="pending",
            expected_value="completed",
        )
        assert "pending" in str(error)
        assert "completed" in str(error)

    def test_suggestion(self) -> None:
        """Test suggestion property."""
        error = WaitTimeoutError(
            condition_description="test",
            timeout_seconds=10.0,
            poll_interval=5.0,
        )
        suggestion = error.suggestion
        assert "timeout" in suggestion.lower() or "interval" in suggestion.lower()


class TestTimeoutDecorator:
    """Tests for with_timeout decorator."""

    def test_successful_execution(self) -> None:
        """Test successful execution within timeout."""
        @with_timeout(1.0)
        def fast_operation() -> str:
            return "done"

        result = fast_operation()
        assert result == "done"

    def test_timeout_raised(self) -> None:
        """Test timeout is raised for slow operation."""
        @with_timeout(0.1, "slow operation")
        def slow_operation() -> str:
            time.sleep(1.0)
            return "done"

        with pytest.raises(StepTimeoutError) as exc_info:
            slow_operation()

        assert exc_info.value.timeout_seconds == 0.1
        assert "slow operation" in str(exc_info.value)


class TestExecuteWithTimeout:
    """Tests for execute_with_timeout function."""

    def test_successful_execution(self) -> None:
        """Test successful execution within timeout."""
        result = execute_with_timeout(
            operation=lambda: "success",
            timeout=1.0,
        )
        assert result == "success"

    def test_timeout_raised(self) -> None:
        """Test timeout is raised for slow operation."""
        def slow_op() -> str:
            time.sleep(1.0)
            return "done"

        with pytest.raises(StepTimeoutError):
            execute_with_timeout(
                operation=slow_op,
                timeout=0.1,
                operation_description="test operation",
            )


class TestWaitForSync:
    """Tests for synchronous wait_for function."""

    def test_condition_met_immediately(self) -> None:
        """Test condition that's already true."""
        result = wait_for_sync(
            condition=lambda: True,
            timeout=1.0,
        )
        assert result is True

    def test_condition_met_eventually(self) -> None:
        """Test condition that becomes true after some time."""
        counter = [0]

        def condition() -> bool:
            counter[0] += 1
            return counter[0] >= 3

        result = wait_for_sync(
            condition=condition,
            timeout=5.0,
            interval=0.1,
        )
        assert result is True
        assert counter[0] >= 3

    def test_timeout_raises(self) -> None:
        """Test timeout raises WaitTimeoutError."""
        with pytest.raises(WaitTimeoutError):
            wait_for_sync(
                condition=lambda: False,
                timeout=0.2,
                interval=0.05,
                description="never true condition",
            )

    def test_timeout_no_raise(self) -> None:
        """Test timeout returns False when raise_on_timeout=False."""
        result = wait_for_sync(
            condition=lambda: False,
            timeout=0.2,
            interval=0.05,
            raise_on_timeout=False,
        )
        assert result is False


class TestPollUntilSync:
    """Tests for synchronous poll_until function."""

    def test_condition_met(self) -> None:
        """Test polling until condition is met."""
        counter = [0]

        def fetcher() -> dict[str, int]:
            counter[0] += 1
            return {"count": counter[0]}

        result = poll_until_sync(
            fetcher=fetcher,
            condition=lambda x: x["count"] >= 3,
            timeout=5.0,
            interval=0.1,
        )
        assert result["count"] >= 3

    def test_timeout_includes_last_value(self) -> None:
        """Test timeout error includes last fetched value."""
        with pytest.raises(WaitTimeoutError) as exc_info:
            poll_until_sync(
                fetcher=lambda: {"status": "pending"},
                condition=lambda x: x["status"] == "completed",
                timeout=0.2,
                interval=0.05,
                description="status to be completed",
            )

        assert exc_info.value.last_value is not None


class TestCreateDefaultFunctions:
    """Tests for factory functions."""

    def test_create_default_retry_policy(self) -> None:
        """Test creating default retry policy."""
        policy = create_default_retry_policy(max_attempts=5, base_delay=2.0)
        assert policy.config.max_attempts == 5
        assert policy.config.base_delay == 2.0
        assert policy.config.backoff_strategy == BackoffStrategy.EXPONENTIAL_FULL_JITTER

    def test_create_default_circuit_breaker(self) -> None:
        """Test creating default circuit breaker."""
        breaker = create_default_circuit_breaker(
            name="test",
            failure_threshold=10,
            recovery_timeout=45.0,
        )
        assert breaker.name == "test"
        assert breaker.failure_threshold == 10
        assert breaker.recovery_timeout == 45.0


class TestAsyncRetry:
    """Tests for async retry functionality."""

    @pytest.mark.asyncio
    async def test_execute_async_success(self) -> None:
        """Test successful async execution."""
        policy = RetryPolicy()

        async def async_op() -> str:
            return "success"

        result = await policy.execute_async(async_op)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_execute_async_retry(self) -> None:
        """Test async execution with retries."""
        attempts = [0]

        async def flaky_async_op() -> str:
            attempts[0] += 1
            if attempts[0] < 3:
                raise ConnectionError("Flaky")
            return "success"

        config = RetryConfig(
            max_attempts=5,
            base_delay=0.01,
            retryable_exceptions=(ConnectionError,),
        )
        policy = RetryPolicy(config)
        result = await policy.execute_async(flaky_async_op)
        assert result == "success"
        assert attempts[0] == 3


class TestAsyncCircuitBreaker:
    """Tests for async circuit breaker functionality."""

    @pytest.mark.asyncio
    async def test_execute_async_success(self) -> None:
        """Test successful async execution."""
        breaker = CircuitBreaker()

        async def async_op() -> str:
            return "success"

        result = await breaker.execute_async(async_op)
        assert result == "success"
        assert breaker.is_closed

    @pytest.mark.asyncio
    async def test_execute_async_trips(self) -> None:
        """Test async execution trips circuit."""
        breaker = CircuitBreaker(failure_threshold=2)

        async def failing_op() -> str:
            raise ValueError("fail")

        for _ in range(2):
            try:
                await breaker.execute_async(failing_op)
            except ValueError:
                pass

        assert breaker.is_open
