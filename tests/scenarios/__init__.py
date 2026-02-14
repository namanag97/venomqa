"""VenomQA Stress Test Scenarios.

This package contains comprehensive test scenarios designed to stress-test
VenomQA's capabilities across various dimensions:

- Deep Branching: Nested checkpoints and state isolation
- Concurrent Users: Parallel execution and race condition detection
- Long-Running Journeys: Memory usage and leak detection
- Failure Recovery: Retry logic and partial result handling
- Real-Time Integration: WebSocket and notification testing
- File Operations: Upload, storage, and cleanup verification
- Time-Based Testing: Expiration and time manipulation

Each scenario module contains Journey definitions that can be run against
the example applications (todo_app, full_featured_app).
"""

# Use relative imports for package structure
from .scenario_concurrent_users import (
    concurrent_checkout_journey,
    inventory_stress_journey,
)
from .scenario_deep_branching import (
    deep_branching_journey,
    triple_nested_journey,
)
from .scenario_failure_recovery import (
    failure_recovery_journey,
    partial_save_journey,
)
from .scenario_file_operations import (
    file_cleanup_journey,
    file_operations_journey,
)
from .scenario_long_running import (
    long_running_journey,
    memory_intensive_journey,
)
from .scenario_realtime import (
    notification_journey,
    websocket_recovery_journey,
)
from .scenario_time_based import (
    cart_expiration_journey,
    session_timeout_journey,
)

__all__ = [
    # Deep branching
    "deep_branching_journey",
    "triple_nested_journey",
    # Concurrent users
    "concurrent_checkout_journey",
    "inventory_stress_journey",
    # Long running
    "long_running_journey",
    "memory_intensive_journey",
    # Failure recovery
    "failure_recovery_journey",
    "partial_save_journey",
    # Real-time
    "websocket_recovery_journey",
    "notification_journey",
    # File operations
    "file_operations_journey",
    "file_cleanup_journey",
    # Time-based
    "cart_expiration_journey",
    "session_timeout_journey",
]
