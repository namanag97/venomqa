"""Exploration Context - State space search and bug finding.

The Exploration context is responsible for:
- Orchestrating state traversal (Agent)
- Search strategies (BFS, DFS, MCTS, etc.)
- Managing the exploration frontier
- Recording the state graph and transitions
- Detecting invariant violations (bugs)

Core abstractions:
- Agent: Orchestrates the exploration loop
- ExplorationStrategy: Protocol for search algorithms
- Frontier: Manages unexplored (state, action) pairs
- Graph: Records visited states and transitions
- Transition: A single state change
- ExplorationResult: Output of an exploration run
"""

from venomqa.exploration.frontier import Frontier, QueueFrontier, StackFrontier
from venomqa.exploration.graph import Graph
from venomqa.exploration.result import ExplorationResult
from venomqa.exploration.strategies import (
    BFS,
    DFS,
    MCTS,
    BaseStrategy,
    CoverageGuided,
    ExplorationStrategy,
    Random,
    Strategy,  # Backward compat alias
    Weighted,
)
from venomqa.exploration.transition import Transition

__all__ = [
    # Core types
    "Graph",
    "Transition",
    "ExplorationResult",
    # Strategy protocol and implementations
    "ExplorationStrategy",
    "Strategy",  # Backward compat alias
    "BaseStrategy",
    "BFS",
    "DFS",
    "MCTS",
    "Random",
    "CoverageGuided",
    "Weighted",
    # Frontier abstraction
    "Frontier",
    "QueueFrontier",
    "StackFrontier",
]
