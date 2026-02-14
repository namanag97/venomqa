"""Long-Running Journey Scenario - Tests memory usage and step limits.

This scenario verifies VenomQA's ability to:
- Execute journeys with 50+ steps
- Track memory usage throughout execution
- Detect memory leaks
- Maintain performance over extended runs

Requires: todo_app or full_featured_app running on localhost:8000
"""

from __future__ import annotations

import gc
import sys
import time
from typing import Any

from venomqa import Branch, Checkpoint, Journey, Path, Step
from venomqa.core.context import ExecutionContext


# =============================================================================
# Memory Tracking Utilities
# =============================================================================


def get_memory_usage() -> dict[str, Any]:
    """Get current memory usage statistics."""
    try:
        import resource

        rusage = resource.getrusage(resource.RUSAGE_SELF)
        return {
            "max_rss_mb": rusage.ru_maxrss / 1024 / 1024,  # macOS returns bytes
            "shared_mb": rusage.ru_ixrss / 1024 / 1024,
            "unshared_mb": rusage.ru_idrss / 1024 / 1024,
        }
    except ImportError:
        # Windows fallback
        try:
            import psutil

            process = psutil.Process()
            mem = process.memory_info()
            return {
                "rss_mb": mem.rss / 1024 / 1024,
                "vms_mb": mem.vms / 1024 / 1024,
            }
        except ImportError:
            return {"tracking": "unavailable"}


def get_object_counts() -> dict[str, int]:
    """Get count of objects by type."""
    gc.collect()
    types_count: dict[str, int] = {}

    for obj in gc.get_objects():
        obj_type = type(obj).__name__
        types_count[obj_type] = types_count.get(obj_type, 0) + 1

    # Return top 10 most common types
    sorted_types = sorted(types_count.items(), key=lambda x: -x[1])[:10]
    return dict(sorted_types)


# =============================================================================
# Memory Tracking Actions
# =============================================================================


def initialize_memory_tracking(client: Any, context: ExecutionContext) -> Any:
    """Initialize memory tracking at journey start."""
    gc.collect()

    context["memory_samples"] = []
    context["object_samples"] = []
    context["start_memory"] = get_memory_usage()
    context["start_objects"] = get_object_counts()
    context["step_counter"] = 0
    context["start_time"] = time.time()

    return {
        "status": "tracking_initialized",
        "initial_memory": context["start_memory"],
    }


def record_memory_sample(client: Any, context: ExecutionContext) -> Any:
    """Record a memory sample at the current step."""
    step_counter = context.get("step_counter", 0) + 1
    context["step_counter"] = step_counter

    current_memory = get_memory_usage()
    current_objects = get_object_counts()

    sample = {
        "step": step_counter,
        "timestamp": time.time() - context.get("start_time", 0),
        "memory": current_memory,
        "objects": current_objects,
    }

    context.get("memory_samples", []).append(sample)

    return {"status": "sample_recorded", "step": step_counter}


def finalize_memory_tracking(client: Any, context: ExecutionContext) -> Any:
    """Finalize memory tracking and analyze results."""
    gc.collect()

    end_memory = get_memory_usage()
    end_objects = get_object_counts()

    context["end_memory"] = end_memory
    context["end_objects"] = end_objects

    # Calculate memory growth
    start_mem = context.get("start_memory", {})
    memory_growth = {}

    for key in end_memory:
        if key in start_mem:
            growth = end_memory[key] - start_mem[key]
            memory_growth[key] = growth

    context["memory_growth"] = memory_growth

    # Analyze for potential leaks (more than 10MB growth is suspicious)
    potential_leak = any(
        abs(v) > 10 for v in memory_growth.values() if isinstance(v, (int, float))
    )

    return {
        "status": "tracking_complete",
        "total_steps": context.get("step_counter", 0),
        "memory_growth": memory_growth,
        "potential_leak_detected": potential_leak,
    }


# =============================================================================
# Long-Running Step Actions
# =============================================================================


def create_todo_item(client: Any, context: ExecutionContext, item_index: int = 0) -> Any:
    """Create a single todo item."""
    response = client.post(
        "/todos",
        json={
            "title": f"Long-running test item {item_index}",
            "description": f"Created at step {context.get('step_counter', 0)}",
            "priority": item_index % 3 + 1,
        },
    )

    if response.status_code in [200, 201]:
        todo_id = response.json().get("id")
        context.setdefault("created_todos", []).append(todo_id)

    return response


def update_todo_item(client: Any, context: ExecutionContext, item_index: int = 0) -> Any:
    """Update a todo item if it exists."""
    created_todos = context.get("created_todos", [])

    if not created_todos:
        return {"status": "skip", "reason": "no todos to update"}

    todo_id = created_todos[item_index % len(created_todos)]

    response = client.patch(
        f"/todos/{todo_id}",
        json={
            "title": f"Updated item at step {context.get('step_counter', 0)}",
            "completed": item_index % 2 == 0,
        },
    )

    return response


def fetch_all_todos(client: Any, context: ExecutionContext) -> Any:
    """Fetch all todos to test response handling."""
    response = client.get("/todos")

    if response.status_code == 200:
        data = response.json()
        context["last_fetch_count"] = len(data) if isinstance(data, list) else 0

    return response


def delete_oldest_todo(client: Any, context: ExecutionContext) -> Any:
    """Delete the oldest todo to prevent accumulation."""
    created_todos = context.get("created_todos", [])

    if not created_todos:
        return {"status": "skip", "reason": "no todos to delete"}

    oldest_id = created_todos.pop(0)
    response = client.delete(f"/todos/{oldest_id}")

    return response


def perform_batch_operations(client: Any, context: ExecutionContext) -> Any:
    """Perform multiple operations in a single step."""
    results = {
        "creates": 0,
        "updates": 0,
        "deletes": 0,
        "fetches": 0,
    }

    # Create 3 items
    for i in range(3):
        resp = client.post(
            "/todos",
            json={"title": f"Batch item {i}", "description": "Batch created"},
        )
        if resp.status_code in [200, 201]:
            results["creates"] += 1
            todo_id = resp.json().get("id")
            context.setdefault("created_todos", []).append(todo_id)

    # Fetch to verify
    resp = client.get("/todos")
    if resp.status_code == 200:
        results["fetches"] += 1

    return {"status": "batch_complete", "results": results}


# =============================================================================
# Checkpoint Verification Actions
# =============================================================================


def verify_checkpoint_10(client: Any, context: ExecutionContext) -> Any:
    """Verify state at checkpoint 10."""
    record_memory_sample(client, context)

    assert context.get("step_counter", 0) >= 10, "Should be at step 10+"

    return {
        "checkpoint": 10,
        "todos_created": len(context.get("created_todos", [])),
        "memory": get_memory_usage(),
    }


def verify_checkpoint_25(client: Any, context: ExecutionContext) -> Any:
    """Verify state at checkpoint 25."""
    record_memory_sample(client, context)

    assert context.get("step_counter", 0) >= 25, "Should be at step 25+"

    # Check memory growth is reasonable (less than 50MB since start)
    start_mem = context.get("start_memory", {})
    current_mem = get_memory_usage()

    for key in current_mem:
        if key in start_mem and isinstance(current_mem[key], (int, float)):
            growth = current_mem[key] - start_mem[key]
            assert growth < 50, f"Excessive memory growth in {key}: {growth}MB"

    return {
        "checkpoint": 25,
        "todos_created": len(context.get("created_todos", [])),
        "memory": current_mem,
    }


def verify_checkpoint_40(client: Any, context: ExecutionContext) -> Any:
    """Verify state at checkpoint 40."""
    record_memory_sample(client, context)

    assert context.get("step_counter", 0) >= 40, "Should be at step 40+"

    return {
        "checkpoint": 40,
        "todos_created": len(context.get("created_todos", [])),
        "memory": get_memory_usage(),
    }


def verify_checkpoint_50(client: Any, context: ExecutionContext) -> Any:
    """Final checkpoint verification at step 50+."""
    record_memory_sample(client, context)

    step_count = context.get("step_counter", 0)
    assert step_count >= 50, f"Should be at step 50+, got {step_count}"

    # Verify no significant memory leaks
    samples = context.get("memory_samples", [])
    if len(samples) >= 2:
        first_sample = samples[0].get("memory", {})
        last_sample = samples[-1].get("memory", {})

        # Calculate memory trend
        for key in last_sample:
            if key in first_sample and isinstance(last_sample[key], (int, float)):
                growth_per_step = (last_sample[key] - first_sample[key]) / step_count
                # Alert if growing more than 0.5MB per step
                if growth_per_step > 0.5:
                    context["potential_leak_warning"] = (
                        f"Memory growing {growth_per_step:.2f}MB/step in {key}"
                    )

    return {
        "checkpoint": 50,
        "total_steps": step_count,
        "final_memory": get_memory_usage(),
        "potential_leak": context.get("potential_leak_warning"),
    }


def cleanup_all_todos(client: Any, context: ExecutionContext) -> Any:
    """Clean up all created todos."""
    created_todos = context.get("created_todos", [])
    deleted_count = 0

    for todo_id in created_todos:
        resp = client.delete(f"/todos/{todo_id}")
        if resp.status_code in [200, 204]:
            deleted_count += 1

    context["created_todos"] = []

    return {"status": "cleanup_complete", "deleted": deleted_count}


# =============================================================================
# Generate Long Journey Steps
# =============================================================================


def _generate_long_journey_steps() -> list:
    """Generate 50+ steps for the long-running journey."""
    steps = [
        Step(
            name="init_memory_tracking",
            action=initialize_memory_tracking,
            description="Start memory tracking",
        ),
    ]

    # Steps 1-10: Initial creation phase
    for i in range(10):
        steps.append(
            Step(
                name=f"create_todo_{i}",
                action=lambda c, ctx, idx=i: create_todo_item(c, ctx, idx),
                description=f"Create todo item {i}",
            )
        )
        if i % 3 == 0:
            steps.append(
                Step(
                    name=f"memory_sample_{i}",
                    action=record_memory_sample,
                    description=f"Record memory at step {i}",
                )
            )

    steps.append(Checkpoint(name="checkpoint_10"))
    steps.append(
        Step(
            name="verify_cp_10",
            action=verify_checkpoint_10,
            description="Verify state at checkpoint 10",
        )
    )

    # Steps 11-25: Mixed operations
    for i in range(10, 25):
        if i % 3 == 0:
            steps.append(
                Step(
                    name=f"create_todo_{i}",
                    action=lambda c, ctx, idx=i: create_todo_item(c, ctx, idx),
                    description=f"Create todo {i}",
                )
            )
        elif i % 3 == 1:
            steps.append(
                Step(
                    name=f"update_todo_{i}",
                    action=lambda c, ctx, idx=i: update_todo_item(c, ctx, idx),
                    description=f"Update todo {i}",
                )
            )
        else:
            steps.append(
                Step(
                    name=f"fetch_todos_{i}",
                    action=fetch_all_todos,
                    description=f"Fetch all todos at step {i}",
                )
            )

        if i % 5 == 0:
            steps.append(
                Step(
                    name=f"memory_sample_{i}",
                    action=record_memory_sample,
                    description=f"Record memory at step {i}",
                )
            )

    steps.append(Checkpoint(name="checkpoint_25"))
    steps.append(
        Step(
            name="verify_cp_25",
            action=verify_checkpoint_25,
            description="Verify state at checkpoint 25",
        )
    )

    # Steps 26-40: Heavy operations with cleanup
    for i in range(25, 40):
        if i % 2 == 0:
            steps.append(
                Step(
                    name=f"batch_ops_{i}",
                    action=perform_batch_operations,
                    description=f"Batch operations at step {i}",
                )
            )
        else:
            steps.append(
                Step(
                    name=f"delete_oldest_{i}",
                    action=delete_oldest_todo,
                    description=f"Delete oldest todo at step {i}",
                )
            )

        if i % 4 == 0:
            steps.append(
                Step(
                    name=f"memory_sample_{i}",
                    action=record_memory_sample,
                    description=f"Record memory at step {i}",
                )
            )

    steps.append(Checkpoint(name="checkpoint_40"))
    steps.append(
        Step(
            name="verify_cp_40",
            action=verify_checkpoint_40,
            description="Verify state at checkpoint 40",
        )
    )

    # Steps 41-50: Final phase
    for i in range(40, 50):
        steps.append(
            Step(
                name=f"mixed_op_{i}",
                action=lambda c, ctx, idx=i: (
                    create_todo_item(c, ctx, idx)
                    if idx % 2 == 0
                    else update_todo_item(c, ctx, idx)
                ),
                description=f"Mixed operation at step {i}",
            )
        )

    steps.append(Checkpoint(name="checkpoint_50"))
    steps.append(
        Step(
            name="verify_cp_50",
            action=verify_checkpoint_50,
            description="Final verification at step 50",
        )
    )

    # Cleanup phase
    steps.append(
        Step(
            name="cleanup_todos",
            action=cleanup_all_todos,
            description="Clean up all created todos",
        )
    )
    steps.append(
        Step(
            name="finalize_memory",
            action=finalize_memory_tracking,
            description="Finalize memory analysis",
        )
    )

    return steps


# =============================================================================
# Journey Definitions
# =============================================================================

long_running_journey = Journey(
    name="long_running_50_steps",
    description="50+ step journey with memory tracking and multiple checkpoints",
    tags=["stress-test", "long-running", "memory"],
    timeout=600.0,  # 10 minutes
    steps=_generate_long_journey_steps(),
)

# Memory-intensive variant with more aggressive operations
memory_intensive_journey = Journey(
    name="memory_intensive_journey",
    description="Journey designed to stress memory management",
    tags=["stress-test", "memory", "intensive"],
    timeout=300.0,
    steps=[
        Step(name="init_tracking", action=initialize_memory_tracking),
        Checkpoint(name="start"),
        # Create many items rapidly
        *[
            Step(
                name=f"rapid_create_{i}",
                action=lambda c, ctx, idx=i: create_todo_item(c, ctx, idx),
            )
            for i in range(20)
        ],
        Checkpoint(name="after_rapid_create"),
        Step(name="memory_sample_1", action=record_memory_sample),
        # Batch operations
        *[
            Step(
                name=f"batch_{i}",
                action=perform_batch_operations,
            )
            for i in range(10)
        ],
        Checkpoint(name="after_batches"),
        Step(name="memory_sample_2", action=record_memory_sample),
        # Cleanup
        Step(name="cleanup", action=cleanup_all_todos),
        Step(name="final_memory", action=finalize_memory_tracking),
    ],
)
