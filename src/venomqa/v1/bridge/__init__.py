"""Bridge module for gradual migration from old API."""

from venomqa.v1.bridge.state_manager import adapt_state_manager

__all__ = [
    "adapt_state_manager",
]
