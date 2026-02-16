"""World module - the execution sandbox.

World coordinates all systems (db, cache, queue) and provides:
- act(): Execute an action via the API
- observe(): Get current state from all systems
- checkpoint(): Save current state for rollback
- rollback(): Restore to a checkpoint
"""

from venomqa.v1.world.rollbackable import Rollbackable
from venomqa.v1.world.checkpoint import Checkpoint, SystemCheckpoint

__all__ = [
    "World",
    "Rollbackable",
    "Checkpoint",
    "SystemCheckpoint",
]

# TODO: Implement World class in Task #10
class World:
    """The execution sandbox that coordinates all systems."""
    pass
