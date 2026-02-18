"""Sandbox Context - The test execution environment.

The Sandbox is responsible for:
- State isolation via checkpoint/rollback
- Context management for sharing data between actions
- Coordinating multiple rollbackable systems (databases, caches, etc.)

Core abstractions:
- World: The execution sandbox that coordinates all systems
- Context: Key-value store for sharing data between actions
- State: Immutable snapshot of the world at a point in time
- Observation: Data observed from a single system
- Rollbackable: Protocol for systems that support checkpoint/rollback
- Checkpoint: A saved state that can be rolled back to
"""

from venomqa.sandbox.checkpoint import Checkpoint
from venomqa.sandbox.context import Context, ScopedContext
from venomqa.sandbox.rollbackable import Rollbackable, SystemCheckpoint
from venomqa.sandbox.state import Observation, State
from venomqa.sandbox.world import World

__all__ = [
    # Core sandbox types
    "World",
    "Context",
    "ScopedContext",
    "State",
    "Observation",
    # Rollback support
    "Rollbackable",
    "Checkpoint",
    "SystemCheckpoint",
]
