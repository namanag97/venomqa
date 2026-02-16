"""VenomQA v1 - Clean, minimal API for stateful exploration testing.

This module provides the v1 API with ~18 exports instead of 300+.
Import what you need from here.

Example:
    from venomqa.v1 import State, Action, Graph, World, Agent, Invariant
"""

from venomqa.v1.core.state import State, Observation
from venomqa.v1.core.action import Action, ActionResult
from venomqa.v1.core.transition import Transition
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Invariant, Violation, Severity
from venomqa.v1.core.result import ExplorationResult

from venomqa.v1.world import World
from venomqa.v1.world.rollbackable import Rollbackable
from venomqa.v1.world.checkpoint import Checkpoint, SystemCheckpoint

from venomqa.v1.agent import Agent
from venomqa.v1.agent.strategies import Strategy, BFS, DFS, Random

# Type aliases
StateID = str
TransitionID = str
CheckpointID = str
ViolationID = str

__all__ = [
    # Core
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
    # World
    "World",
    "Rollbackable",
    "Checkpoint",
    "SystemCheckpoint",
    # Agent
    "Agent",
    "Strategy",
    "BFS",
    "DFS",
    "Random",
    # Type aliases
    "StateID",
    "TransitionID",
    "CheckpointID",
    "ViolationID",
]
