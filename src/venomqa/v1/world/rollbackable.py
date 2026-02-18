"""Rollbackable protocol - re-exports from sandbox context.

DEPRECATED: Import from venomqa.sandbox instead.
"""

from venomqa.sandbox.rollbackable import Rollbackable, SystemCheckpoint

__all__ = ["Rollbackable", "SystemCheckpoint"]
