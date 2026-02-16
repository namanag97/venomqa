"""Core data objects for VenomQA v1.

This module contains the fundamental data structures:
- State, Observation: World snapshots
- Action, ActionResult: Things that change the world
- Transition: State change records
- Graph: All states and transitions
- Invariant, Violation, Severity: Verification
- ExplorationResult: Final output
"""

from venomqa.v1.core.state import State, Observation
from venomqa.v1.core.action import Action, ActionResult
from venomqa.v1.core.transition import Transition
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Invariant, Violation, Severity
from venomqa.v1.core.result import ExplorationResult

__all__ = [
    "State",
    "Observation",
    "Action",
    "ActionResult",
    "Transition",
    "Graph",
    "Invariant",
    "Violation",
    "Severity",
    "ExplorationResult",
]
