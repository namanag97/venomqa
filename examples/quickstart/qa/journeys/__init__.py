"""Journey definitions for VenomQA Quickstart.

Journeys define complete test scenarios as a sequence of steps.
Each journey can include:
    - Steps: Individual test actions
    - Checkpoints: State snapshots for branching
    - Branches: Alternative paths from checkpoints
"""

from .hello_journey import journey

__all__ = ["journey"]
