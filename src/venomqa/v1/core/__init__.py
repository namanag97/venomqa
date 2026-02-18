"""Core data objects for VenomQA v1.

This module contains the fundamental data structures:
- State, Observation: World snapshots
- Action, ActionResult: Things that change the world
- Transition: State change records
- Graph: All states and transitions
- Invariant, Violation, Severity: Verification
- ExplorationResult: Final output
"""

from venomqa.v1.core.action import Action, ActionResult
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Bug, Invariant, Severity, Violation
from venomqa.v1.core.result import ExplorationResult
from venomqa.v1.core.state import Observation, State
from venomqa.v1.core.transition import Transition

__all__ = [
    "State",
    "Observation",
    "Action",
    "ActionResult",
    "Transition",
    "Graph",
    "Bug",
    "Invariant",
    "Violation",
    "Severity",
    "ExplorationResult",
]
