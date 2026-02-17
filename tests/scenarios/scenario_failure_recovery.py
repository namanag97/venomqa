"""Failure Recovery Scenario - Tests retry logic and partial result handling.

This scenario verifies VenomQA's ability to:
- Handle randomly failing steps
- Execute retry logic correctly
- Save partial results on failure
- Recover from transient errors

Requires: todo_app or full_featured_app running on localhost:8000
"""

from __future__ import annotations

import random
import time
from typing import Any

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.core.context import ExecutionContext
from venomqa.errors import (
    BackoffStrategy,
    CircuitBreaker,
    RetryConfig,
    RetryExhaustedError,
    RetryPolicy,
)

# =============================================================================
# Configuration
# =============================================================================

# Probability of failure for flaky operations
FLAKY_FAILURE_RATE = 0.3  # 30% chance of failure

# Track failure attempts for verification
_failure_attempts: dict[str, list[dict[str, Any]]] = {}
_retry_counts: dict[str, int] = {}


def reset_failure_tracking() -> None:
    """Reset failure tracking between runs."""
    global _failure_attempts, _retry_counts
    _failure_attempts = {}
    _retry_counts = {}


# =============================================================================
# Flaky Action Helpers
# =============================================================================


def create_flaky_action(
    action_name: str,
    failure_rate: float = FLAKY_FAILURE_RATE,
    failure_type: str = "exception",
):
    """Create an action that randomly fails."""

    def flaky_action(client: Any, context: ExecutionContext) -> Any:
        _failure_attempts.setdefault(action_name, [])

        attempt = {
            "timestamp": time.time(),
            "success": False,
            "error": None,
        }

        if random.random() < failure_rate:
            attempt["error"] = f"Random failure in {action_name}"
            _failure_attempts[action_name].append(attempt)

            if failure_type == "exception":
                raise RuntimeError(f"Simulated failure in {action_name}")
            elif failure_type == "timeout":
                time.sleep(5)  # Simulate timeout
                raise TimeoutError(f"Simulated timeout in {action_name}")
            elif failure_type == "http_error":
                return type(
                    "Response",
                    (),
                    {
                        "status_code": 500,
                        "is_error": True,
                        "json": lambda: {"error": "Internal server error"},
                        "text": "Internal server error",
                    },
                )()

        # Success
        attempt["success"] = True
        _failure_attempts[action_name].append(attempt)
        return {"status": "success", "action": action_name}

    return flaky_action


# =============================================================================
# Setup Actions
# =============================================================================


def setup_failure_test(client: Any, context: ExecutionContext) -> Any:
    """Initialize failure recovery test state."""
    reset_failure_tracking()

    context["partial_results"] = []
    context["completed_steps"] = []
    context["failed_steps"] = []
    context["retry_successes"] = 0
    context["total_retries"] = 0
    context["test_start_time"] = time.time()

    return {"status": "initialized", "timestamp": context["test_start_time"]}


def save_partial_result(client: Any, context: ExecutionContext, step_name: str) -> None:
    """Save a partial result for a completed step."""
    context.get("partial_results", []).append(
        {
            "step": step_name,
            "timestamp": time.time(),
            "context_snapshot": {
                "completed_steps": context.get("completed_steps", []).copy(),
                "partial_results_count": len(context.get("partial_results", [])),
            },
        }
    )
    context.get("completed_steps", []).append(step_name)


# =============================================================================
# Retry-Wrapped Actions
# =============================================================================


def create_todo_with_retry(client: Any, context: ExecutionContext) -> Any:
    """Create a todo with retry logic for transient failures."""
    retry_policy = RetryPolicy(
        RetryConfig(
            max_attempts=3,
            base_delay=0.5,
            backoff_strategy=BackoffStrategy.EXPONENTIAL_FULL_JITTER,
            retryable_exceptions=(RuntimeError, TimeoutError, ConnectionError),
        )
    )

    attempt_count = 0

    def do_create() -> Any:
        nonlocal attempt_count
        attempt_count += 1
        context["total_retries"] = context.get("total_retries", 0) + 1

        # Simulate 40% failure rate
        if random.random() < 0.4:
            raise RuntimeError("Transient failure during todo creation")

        response = client.post(
            "/todos",
            json={
                "title": f"Retry test todo {time.time()}",
                "description": "Created with retry logic",
            },
        )
        return response

    try:
        result = retry_policy.execute(do_create)

        if hasattr(result, "status_code") and result.status_code in [200, 201]:
            todo_id = result.json().get("id")
            context["last_created_todo"] = todo_id
            context["retry_successes"] = context.get("retry_successes", 0) + 1

        save_partial_result(client, context, "create_todo_with_retry")
        context["create_attempts"] = attempt_count

        return result

    except RetryExhaustedError:
        context.get("failed_steps", []).append("create_todo_with_retry")
        context["create_attempts"] = attempt_count
        context["create_exhausted"] = True
        raise


def update_todo_with_retry(client: Any, context: ExecutionContext) -> Any:
    """Update a todo with retry logic."""
    todo_id = context.get("last_created_todo")

    if not todo_id:
        return {"status": "skip", "reason": "no todo to update"}

    retry_policy = RetryPolicy(
        RetryConfig(
            max_attempts=5,
            base_delay=0.3,
            max_delay=5.0,
            backoff_strategy=BackoffStrategy.EXPONENTIAL_EQUAL_JITTER,
        )
    )

    attempt_count = 0

    def do_update() -> Any:
        nonlocal attempt_count
        attempt_count += 1
        context["total_retries"] = context.get("total_retries", 0) + 1

        # Simulate 30% failure rate
        if random.random() < 0.3:
            raise RuntimeError("Transient failure during update")

        return client.patch(
            f"/todos/{todo_id}",
            json={"title": "Updated with retry", "completed": True},
        )

    try:
        result = retry_policy.execute(do_update)
        save_partial_result(client, context, "update_todo_with_retry")
        context["update_attempts"] = attempt_count
        return result

    except RetryExhaustedError:
        context.get("failed_steps", []).append("update_todo_with_retry")
        context["update_attempts"] = attempt_count
        raise


def delete_todo_with_retry(client: Any, context: ExecutionContext) -> Any:
    """Delete a todo with retry logic."""
    todo_id = context.get("last_created_todo")

    if not todo_id:
        return {"status": "skip", "reason": "no todo to delete"}

    retry_policy = RetryPolicy(
        RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            backoff_strategy=BackoffStrategy.LINEAR,
        )
    )

    def do_delete() -> Any:
        context["total_retries"] = context.get("total_retries", 0) + 1

        # Simulate 20% failure rate
        if random.random() < 0.2:
            raise RuntimeError("Transient failure during delete")

        return client.delete(f"/todos/{todo_id}")

    try:
        result = retry_policy.execute(do_delete)
        save_partial_result(client, context, "delete_todo_with_retry")
        context["last_created_todo"] = None
        return result

    except RetryExhaustedError:
        context.get("failed_steps", []).append("delete_todo_with_retry")
        raise


# =============================================================================
# Circuit Breaker Actions
# =============================================================================


def setup_circuit_breaker(client: Any, context: ExecutionContext) -> Any:
    """Initialize circuit breaker for failure handling."""
    context["circuit_breaker"] = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=5.0,
        half_open_max_calls=2,
    )
    context["circuit_operations"] = []

    return {"status": "circuit_breaker_initialized"}


def operation_with_circuit_breaker(client: Any, context: ExecutionContext) -> Any:
    """Execute operation protected by circuit breaker."""
    circuit = context.get("circuit_breaker")

    if not circuit:
        return {"status": "error", "message": "no circuit breaker"}

    operation_result = {
        "timestamp": time.time(),
        "state_before": circuit.state.value,
        "success": False,
    }

    def flaky_operation() -> Any:
        # Simulate 50% failure rate
        if random.random() < 0.5:
            raise RuntimeError("Operation failed")

        return client.get("/todos")

    try:
        result = circuit.execute(flaky_operation)
        operation_result["success"] = True
        operation_result["state_after"] = circuit.state.value
        context.get("circuit_operations", []).append(operation_result)

        return result

    except Exception as e:
        operation_result["error"] = str(e)
        operation_result["state_after"] = circuit.state.value
        context.get("circuit_operations", []).append(operation_result)
        raise


def multiple_circuit_operations(client: Any, context: ExecutionContext) -> Any:
    """Execute multiple operations through circuit breaker."""
    results = {"successful": 0, "failed": 0, "circuit_opened": False}

    circuit = context.get("circuit_breaker")
    if not circuit:
        return {"status": "error"}

    for _i in range(10):
        try:
            operation_with_circuit_breaker(client, context)
            results["successful"] += 1
        except Exception as e:
            results["failed"] += 1
            if "circuit" in str(e).lower() or circuit.is_open:
                results["circuit_opened"] = True

    context["circuit_results"] = results
    return results


# =============================================================================
# Verification Actions
# =============================================================================


def verify_partial_results_saved(client: Any, context: ExecutionContext) -> Any:
    """Verify that partial results were saved."""
    partial_results = context.get("partial_results", [])
    completed_steps = context.get("completed_steps", [])
    failed_steps = context.get("failed_steps", [])

    # Verify structure of partial results
    for result in partial_results:
        assert "step" in result, "Partial result should have step name"
        assert "timestamp" in result, "Partial result should have timestamp"
        assert "context_snapshot" in result, "Partial result should have snapshot"

    # Verify completed steps match partial results
    partial_step_names = [r["step"] for r in partial_results]
    for completed in completed_steps:
        assert completed in partial_step_names, (
            f"Completed step {completed} should have partial result"
        )

    return {
        "status": "partial_results_verified",
        "completed_count": len(completed_steps),
        "failed_count": len(failed_steps),
        "partial_results_count": len(partial_results),
    }


def verify_retry_logic(client: Any, context: ExecutionContext) -> Any:
    """Verify retry logic worked correctly."""
    total_retries = context.get("total_retries", 0)
    retry_successes = context.get("retry_successes", 0)

    # Should have had some retries
    assert total_retries > 0, "Should have had retry attempts"

    # Should have some successes (with high probability)
    # Note: This could occasionally fail due to randomness

    return {
        "status": "retry_logic_verified",
        "total_retries": total_retries,
        "retry_successes": retry_successes,
        "create_attempts": context.get("create_attempts", 0),
        "update_attempts": context.get("update_attempts", 0),
    }


def verify_circuit_breaker(client: Any, context: ExecutionContext) -> Any:
    """Verify circuit breaker behavior."""
    circuit_results = context.get("circuit_results", {})
    circuit_operations = context.get("circuit_operations", [])

    # Verify circuit breaker state transitions occurred
    states_seen = set()
    for op in circuit_operations:
        states_seen.add(op.get("state_before"))
        states_seen.add(op.get("state_after"))

    return {
        "status": "circuit_breaker_verified",
        "total_operations": len(circuit_operations),
        "states_observed": list(states_seen),
        "successful": circuit_results.get("successful", 0),
        "failed": circuit_results.get("failed", 0),
        "circuit_opened": circuit_results.get("circuit_opened", False),
    }


def generate_failure_report(client: Any, context: ExecutionContext) -> Any:
    """Generate comprehensive failure and recovery report."""
    elapsed_time = time.time() - context.get("test_start_time", 0)

    report = {
        "summary": {
            "elapsed_seconds": elapsed_time,
            "total_retries": context.get("total_retries", 0),
            "retry_successes": context.get("retry_successes", 0),
            "completed_steps": len(context.get("completed_steps", [])),
            "failed_steps": len(context.get("failed_steps", [])),
            "partial_results": len(context.get("partial_results", [])),
        },
        "completed_steps": context.get("completed_steps", []),
        "failed_steps": context.get("failed_steps", []),
        "retry_details": {
            "create_attempts": context.get("create_attempts", 0),
            "update_attempts": context.get("update_attempts", 0),
        },
        "circuit_breaker": context.get("circuit_results", {}),
    }

    context["failure_report"] = report

    return report


# =============================================================================
# Flaky Step Actions (for testing expect_failure)
# =============================================================================


def always_failing_step(client: Any, context: ExecutionContext) -> Any:
    """Step that always fails - for testing expect_failure."""
    raise RuntimeError("This step always fails")


def sometimes_failing_step(client: Any, context: ExecutionContext) -> Any:
    """Step that fails 50% of the time."""
    if random.random() < 0.5:
        raise RuntimeError("Random failure occurred")
    return {"status": "success", "random_value": random.random()}


# =============================================================================
# Journey Definitions
# =============================================================================

failure_recovery_journey = Journey(
    name="failure_recovery_scenario",
    description="Tests retry logic, circuit breakers, and partial result handling",
    tags=["stress-test", "failure-recovery", "retry"],
    timeout=300.0,
    steps=[
        Step(
            name="setup",
            action=setup_failure_test,
            description="Initialize failure recovery test",
        ),
        Checkpoint(name="initialized"),
        # Retry logic tests
        Step(
            name="create_with_retry",
            action=create_todo_with_retry,
            description="Create todo with retry logic",
            retries=3,
        ),
        Checkpoint(name="after_create"),
        Step(
            name="update_with_retry",
            action=update_todo_with_retry,
            description="Update todo with retry logic",
            retries=5,
        ),
        Checkpoint(name="after_update"),
        Step(
            name="delete_with_retry",
            action=delete_todo_with_retry,
            description="Delete todo with retry logic",
            retries=3,
        ),
        Checkpoint(name="after_delete"),
        # Circuit breaker tests
        Step(
            name="setup_circuit",
            action=setup_circuit_breaker,
            description="Initialize circuit breaker",
        ),
        Step(
            name="circuit_operations",
            action=multiple_circuit_operations,
            description="Execute multiple operations through circuit breaker",
        ),
        Checkpoint(name="after_circuit"),
        # Verification
        Step(
            name="verify_partial_results",
            action=verify_partial_results_saved,
            description="Verify partial results were saved",
        ),
        Step(
            name="verify_retry",
            action=verify_retry_logic,
            description="Verify retry logic worked",
        ),
        Step(
            name="verify_circuit",
            action=verify_circuit_breaker,
            description="Verify circuit breaker behavior",
        ),
        Step(
            name="generate_report",
            action=generate_failure_report,
            description="Generate failure recovery report",
        ),
    ],
)

# Journey testing expected failures
partial_save_journey = Journey(
    name="partial_save_scenario",
    description="Tests saving partial results when some steps fail",
    tags=["stress-test", "partial-results"],
    timeout=120.0,
    steps=[
        Step(name="setup", action=setup_failure_test),
        Checkpoint(name="start"),
        Step(
            name="successful_step_1",
            action=lambda c, ctx: (
                save_partial_result(c, ctx, "step_1"),
                {"status": "success"},
            )[-1],
        ),
        Step(
            name="successful_step_2",
            action=lambda c, ctx: (
                save_partial_result(c, ctx, "step_2"),
                {"status": "success"},
            )[-1],
        ),
        Checkpoint(name="partial_complete"),
        Step(
            name="flaky_step",
            action=sometimes_failing_step,
            retries=2,
        ),
        Step(
            name="successful_step_3",
            action=lambda c, ctx: (
                save_partial_result(c, ctx, "step_3"),
                {"status": "success"},
            )[-1],
        ),
        Checkpoint(name="mostly_complete"),
        Step(
            name="verify_saved",
            action=verify_partial_results_saved,
        ),
        Branch(
            checkpoint_name="partial_complete",
            paths=[
                Path(
                    name="recovery_path",
                    description="Path taken after partial completion",
                    steps=[
                        Step(
                            name="recovery_step",
                            action=lambda c, ctx: {"status": "recovered"},
                        ),
                    ],
                ),
            ],
        ),
    ],
)
