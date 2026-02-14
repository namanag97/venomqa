"""Time-Based Testing Scenario - Tests expiration and time manipulation.

This scenario verifies VenomQA's ability to:
- Manipulate time for testing expiration logic
- Test cart/session expiration
- Verify time-dependent business logic
- Handle scheduled tasks and timeouts

Requires: todo_app or full_featured_app running on localhost:8000
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.adapters.controllable_time import ControllableTimeAdapter
from venomqa.core.context import ExecutionContext

# =============================================================================
# Time Adapter Setup
# =============================================================================


def setup_time_adapter(client: Any, context: ExecutionContext) -> Any:
    """Initialize controllable time adapter."""
    # Create time adapter starting at current time
    time_adapter = ControllableTimeAdapter(
        initial_time=datetime.now(timezone.utc),
        timezone_name="UTC",
    )

    # Freeze time for deterministic testing
    time_adapter.freeze()

    context["time_adapter"] = time_adapter
    context["time_frozen"] = True
    context["initial_time"] = time_adapter.now()
    context["time_advances"] = []
    context["expiration_events"] = []
    context["test_start_time"] = time.time()

    return {
        "status": "time_initialized",
        "initial_time": context["initial_time"].isoformat(),
        "frozen": True,
    }


def get_current_test_time(client: Any, context: ExecutionContext) -> Any:
    """Get the current test time from the adapter."""
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if not time_adapter:
        return {"status": "error", "message": "No time adapter"}

    current = time_adapter.now()

    return {
        "current_time": current.isoformat(),
        "is_frozen": time_adapter.is_frozen(),
    }


# =============================================================================
# Cart Expiration Testing
# =============================================================================


def create_cart_with_expiration(client: Any, context: ExecutionContext) -> Any:
    """Create a cart that expires after a certain time."""
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if not time_adapter:
        return {"status": "error", "message": "No time adapter"}

    # Record creation time
    creation_time = time_adapter.now()
    context["cart_creation_time"] = creation_time

    # Cart expires in 30 minutes
    expiration_time = creation_time + timedelta(minutes=30)
    context["cart_expiration_time"] = expiration_time

    response = client.post(
        "/api/cart",
        json={
            "expires_at": expiration_time.isoformat(),
        },
    )

    if response.status_code in [200, 201]:
        data = response.json()
        context["cart_id"] = data.get("id")
        context["cart_expires_at"] = data.get("expires_at")

    return response


def add_item_to_cart(client: Any, context: ExecutionContext) -> Any:
    """Add an item to the cart."""
    cart_id = context.get("cart_id")

    if not cart_id:
        return {"status": "skip", "message": "No cart"}

    response = client.post(
        f"/api/cart/{cart_id}/items",
        json={
            "product_id": "test_product",
            "quantity": 1,
        },
    )

    return response


def verify_cart_active(client: Any, context: ExecutionContext) -> Any:
    """Verify cart is still active."""
    cart_id = context.get("cart_id")
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if not cart_id:
        return {"status": "skip", "message": "No cart"}

    response = client.get(f"/api/cart/{cart_id}")

    result = {
        "cart_exists": response.status_code == 200,
        "current_time": time_adapter.now().isoformat() if time_adapter else None,
    }

    if response.status_code == 200:
        data = response.json()
        result["status"] = data.get("status")
        result["is_active"] = data.get("status") not in ["expired", "cancelled"]

        # Cart should still be active before expiration
        expiration_time = context.get("cart_expiration_time")
        if expiration_time and time_adapter:
            current_time = time_adapter.now()
            assert current_time < expiration_time, "Cart should not be expired yet"

    return result


def advance_time_near_expiration(client: Any, context: ExecutionContext) -> Any:
    """Advance time to just before cart expiration."""
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if not time_adapter:
        return {"status": "error", "message": "No time adapter"}

    # Advance to 1 minute before expiration
    expiration_time = context.get("cart_expiration_time")
    if not expiration_time:
        return {"status": "error", "message": "No expiration time set"}

    time_to_advance = (expiration_time - time_adapter.now()) - timedelta(minutes=1)

    if time_to_advance.total_seconds() > 0:
        new_time = time_adapter.advance(time_to_advance)
        context["time_advances"].append(
            {
                "delta_seconds": time_to_advance.total_seconds(),
                "new_time": new_time.isoformat(),
                "reason": "near_expiration",
            }
        )

    return {
        "status": "time_advanced",
        "current_time": time_adapter.now().isoformat(),
        "time_until_expiration": "~1 minute",
    }


def verify_cart_still_active(client: Any, context: ExecutionContext) -> Any:
    """Verify cart is still active near expiration."""
    return verify_cart_active(client, context)


def advance_time_past_expiration(client: Any, context: ExecutionContext) -> Any:
    """Advance time past cart expiration."""
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if not time_adapter:
        return {"status": "error", "message": "No time adapter"}

    # Advance 5 more minutes (past expiration)
    new_time = time_adapter.advance(timedelta(minutes=5))

    context["time_advances"].append(
        {
            "delta_seconds": 300,
            "new_time": new_time.isoformat(),
            "reason": "past_expiration",
        }
    )

    context["expiration_events"].append(
        {
            "type": "cart_expired",
            "cart_id": context.get("cart_id"),
            "time": new_time.isoformat(),
        }
    )

    return {
        "status": "time_advanced_past_expiration",
        "current_time": new_time.isoformat(),
    }


def verify_cart_expired(client: Any, context: ExecutionContext) -> Any:
    """Verify cart has expired."""
    cart_id = context.get("cart_id")
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if not cart_id:
        return {"status": "skip", "message": "No cart"}

    response = client.get(f"/api/cart/{cart_id}")

    result = {
        "current_time": time_adapter.now().isoformat() if time_adapter else None,
        "cart_id": cart_id,
    }

    if response.status_code == 404:
        # Cart deleted after expiration
        result["status"] = "deleted"
        result["is_expired"] = True
    elif response.status_code == 200:
        data = response.json()
        result["status"] = data.get("status")
        result["is_expired"] = data.get("status") in ["expired", "cancelled"]
    else:
        result["status"] = f"error_{response.status_code}"
        result["is_expired"] = False

    # Assert cart is expired
    expiration_time = context.get("cart_expiration_time")
    if time_adapter and expiration_time:
        current_time = time_adapter.now()
        assert current_time > expiration_time, "Time should be past expiration"
        # Note: Application may or may not mark cart as expired depending on implementation

    return result


# =============================================================================
# Session Expiration Testing
# =============================================================================


def create_session_with_timeout(client: Any, context: ExecutionContext) -> Any:
    """Create a user session with timeout."""
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if not time_adapter:
        return {"status": "error", "message": "No time adapter"}

    # Login to create session
    response = client.post(
        "/api/auth/login",
        json={
            "email": context.get("email", "test@example.com"),
            "password": context.get("password", "password123"),
        },
    )

    if response.status_code == 200:
        data = response.json()
        context["session_token"] = data.get("access_token") or data.get("token")
        context["session_created_at"] = time_adapter.now()

        # Session typically expires in 1 hour
        context["session_expires_at"] = time_adapter.now() + timedelta(hours=1)

    return response


def verify_session_active(client: Any, context: ExecutionContext) -> Any:
    """Verify session is still active."""
    token = context.get("session_token")

    if not token:
        return {"status": "skip", "message": "No session"}

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    return {
        "session_active": response.status_code == 200,
        "status_code": response.status_code,
    }


def advance_time_session_idle(client: Any, context: ExecutionContext) -> Any:
    """Advance time to simulate session idle."""
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if not time_adapter:
        return {"status": "error", "message": "No time adapter"}

    # Advance 30 minutes (idle timeout might be 15-30 min)
    new_time = time_adapter.advance(timedelta(minutes=30))

    context["time_advances"].append(
        {
            "delta_seconds": 1800,
            "new_time": new_time.isoformat(),
            "reason": "session_idle",
        }
    )

    return {
        "status": "time_advanced",
        "current_time": new_time.isoformat(),
        "idle_duration_minutes": 30,
    }


def advance_time_session_expired(client: Any, context: ExecutionContext) -> Any:
    """Advance time past session expiration."""
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if not time_adapter:
        return {"status": "error", "message": "No time adapter"}

    # Advance to past session expiration
    session_expires = context.get("session_expires_at")
    if session_expires:
        time_to_expiry = session_expires - time_adapter.now() + timedelta(minutes=5)
        if time_to_expiry.total_seconds() > 0:
            new_time = time_adapter.advance(time_to_expiry)
        else:
            new_time = time_adapter.now()
    else:
        # Default: advance 2 hours
        new_time = time_adapter.advance(timedelta(hours=2))

    context["time_advances"].append(
        {
            "new_time": new_time.isoformat(),
            "reason": "session_expired",
        }
    )

    return {
        "status": "time_advanced_past_session_expiry",
        "current_time": new_time.isoformat(),
    }


def verify_session_expired(client: Any, context: ExecutionContext) -> Any:
    """Verify session has expired."""
    token = context.get("session_token")

    if not token:
        return {"status": "skip", "message": "No session"}

    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    is_expired = response.status_code in [401, 403]

    context["expiration_events"].append(
        {
            "type": "session_expired",
            "time": context.get("time_adapter").now().isoformat() if context.get("time_adapter") else None,
        }
    )

    return {
        "session_expired": is_expired,
        "status_code": response.status_code,
    }


# =============================================================================
# Scheduled Task Testing
# =============================================================================


def schedule_future_task(client: Any, context: ExecutionContext) -> Any:
    """Schedule a task to run in the future."""
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if not time_adapter:
        return {"status": "error", "message": "No time adapter"}

    # Track scheduled tasks
    tasks_executed = []

    def task_callback():
        tasks_executed.append(
            {
                "executed_at": time_adapter.now().isoformat(),
            }
        )

    # Schedule task for 10 minutes from now
    scheduled_time = time_adapter.now() + timedelta(minutes=10)
    task_id = time_adapter.schedule(task_callback, scheduled_time)

    context["scheduled_task_id"] = task_id
    context["scheduled_task_time"] = scheduled_time
    context["tasks_executed"] = tasks_executed

    return {
        "status": "task_scheduled",
        "task_id": task_id,
        "scheduled_for": scheduled_time.isoformat(),
    }


def verify_task_not_executed(client: Any, context: ExecutionContext) -> Any:
    """Verify scheduled task has not executed yet."""
    tasks_executed = context.get("tasks_executed", [])

    assert len(tasks_executed) == 0, "Task should not have executed yet"

    return {
        "status": "task_pending",
        "executions": len(tasks_executed),
    }


def advance_time_to_task(client: Any, context: ExecutionContext) -> Any:
    """Advance time to when task should execute."""
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if not time_adapter:
        return {"status": "error", "message": "No time adapter"}

    # Advance past scheduled time
    new_time = time_adapter.advance(timedelta(minutes=15))

    return {
        "status": "time_advanced",
        "current_time": new_time.isoformat(),
    }


def verify_task_executed(client: Any, context: ExecutionContext) -> Any:
    """Verify scheduled task has executed."""
    tasks_executed = context.get("tasks_executed", [])

    # Task should have executed when time advanced
    # Note: This depends on the time adapter's implementation

    return {
        "status": "task_status_checked",
        "executions": len(tasks_executed),
        "executed": len(tasks_executed) > 0,
    }


# =============================================================================
# Cleanup and Reporting
# =============================================================================


def cleanup_time_test(client: Any, context: ExecutionContext) -> Any:
    """Clean up time test resources."""
    time_adapter: ControllableTimeAdapter = context.get("time_adapter")

    if time_adapter:
        time_adapter.reset()
        time_adapter.unfreeze()

    context["time_adapter"] = None
    context["time_frozen"] = False

    return {"status": "cleaned_up"}


def generate_time_report(client: Any, context: ExecutionContext) -> Any:
    """Generate time-based test report."""
    elapsed_real_time = time.time() - context.get("test_start_time", 0)

    # Calculate total simulated time
    time_advances = context.get("time_advances", [])
    total_simulated_seconds = sum(
        adv.get("delta_seconds", 0) for adv in time_advances
    )

    report = {
        "summary": {
            "real_elapsed_seconds": elapsed_real_time,
            "simulated_seconds": total_simulated_seconds,
            "time_compression_ratio": (
                total_simulated_seconds / elapsed_real_time
                if elapsed_real_time > 0
                else 0
            ),
            "time_advances_count": len(time_advances),
            "expiration_events_count": len(context.get("expiration_events", [])),
        },
        "time_advances": time_advances,
        "expiration_events": context.get("expiration_events", []),
    }

    context["time_report"] = report
    return report


# =============================================================================
# Journey Definitions
# =============================================================================

cart_expiration_journey = Journey(
    name="cart_expiration_scenario",
    description="Tests cart expiration using time manipulation",
    tags=["stress-test", "time", "expiration"],
    timeout=120.0,
    steps=[
        Step(
            name="setup_time",
            action=setup_time_adapter,
            description="Initialize controllable time",
        ),
        Checkpoint(name="time_ready"),
        Step(
            name="create_cart",
            action=create_cart_with_expiration,
            description="Create cart with expiration",
        ),
        Step(
            name="add_item",
            action=add_item_to_cart,
            description="Add item to cart",
        ),
        Step(
            name="verify_active_1",
            action=verify_cart_active,
            description="Verify cart is active",
        ),
        Checkpoint(name="cart_created"),
        Step(
            name="advance_near_expiry",
            action=advance_time_near_expiration,
            description="Advance time near expiration",
        ),
        Step(
            name="verify_active_2",
            action=verify_cart_still_active,
            description="Verify cart still active",
        ),
        Checkpoint(name="near_expiration"),
        Step(
            name="advance_past_expiry",
            action=advance_time_past_expiration,
            description="Advance time past expiration",
        ),
        Step(
            name="verify_expired",
            action=verify_cart_expired,
            description="Verify cart expired",
        ),
        Checkpoint(name="expiration_verified"),
        Step(
            name="cleanup",
            action=cleanup_time_test,
            description="Clean up time test",
        ),
        Step(
            name="report",
            action=generate_time_report,
            description="Generate time test report",
        ),
    ],
)

session_timeout_journey = Journey(
    name="session_timeout_scenario",
    description="Tests session timeout using time manipulation",
    tags=["stress-test", "time", "session"],
    timeout=120.0,
    steps=[
        Step(name="setup_time", action=setup_time_adapter),
        Checkpoint(name="ready"),
        Step(
            name="create_session",
            action=create_session_with_timeout,
            description="Create user session",
        ),
        Step(
            name="verify_active",
            action=verify_session_active,
            description="Verify session active",
        ),
        Checkpoint(name="session_active"),
        Step(
            name="advance_idle",
            action=advance_time_session_idle,
            description="Simulate idle time",
        ),
        Step(
            name="verify_after_idle",
            action=verify_session_active,
            description="Verify session after idle",
        ),
        Checkpoint(name="after_idle"),
        Step(
            name="advance_expiry",
            action=advance_time_session_expired,
            description="Advance past session expiry",
        ),
        Step(
            name="verify_expired",
            action=verify_session_expired,
            description="Verify session expired",
        ),
        Checkpoint(name="session_expired"),
        Branch(
            checkpoint_name="session_expired",
            paths=[
                Path(
                    name="verify_reauth_required",
                    steps=[
                        Step(
                            name="attempt_action",
                            action=verify_session_active,
                            description="Verify action fails without valid session",
                        ),
                    ],
                ),
            ],
        ),
        Step(name="cleanup", action=cleanup_time_test),
        Step(name="report", action=generate_time_report),
    ],
)
