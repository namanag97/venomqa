"""Core module exports.

This module provides the fundamental building blocks for VenomQA:
- Action, ActionResult, HTTPRequest, HTTPResponse
- State, Observation, Context
- Graph, Transition, Invariant, Violation
- ExplorationResult

Legacy exports (backwards compatibility):
- Models: Step, Journey, Checkpoint, Branch, Path, etc.
- Results: StepResult, JourneyResult, BranchResult, PathResult, Issue
- Context: ExecutionContext for sharing state between steps
"""

from __future__ import annotations

import importlib
import sys

# Main API (from v1)
from venomqa.v1.core.action import Action, ActionResult, HTTPRequest, HTTPResponse
from venomqa.v1.core.context import Context
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.invariant import Invariant, InvariantTiming, ResponseAssertion, Severity as V1Severity, Violation
from venomqa.v1.core.result import ExplorationResult
from venomqa.v1.core.state import Observation, State
from venomqa.v1.core.transition import Transition

# Legacy exports
from venomqa.core.context import ExecutionContext
from venomqa.core.models import (
    ActionCallable,
    Branch,
    BranchResult,
    Checkpoint,
    Issue,
    Journey,
    JourneyResult,
    Path,
    PathResult,
    Severity,
    Step,
    StepOrCheckpointOrBranch,
    StepResult,
)

# Submodule aliasing: allow `from venomqa.core.action import Action` etc.
_V1_CORE_SUBMODULES = [
    "action", "state", "context", "graph", "transition",
    "invariant", "result", "observers", "constraints",
    "coverage", "dimensions", "hyperedge", "hypergraph",
]

for _submod in _V1_CORE_SUBMODULES:
    _v1_name = f"venomqa.v1.core.{_submod}"
    _alias_name = f"venomqa.core.{_submod}"
    if _alias_name not in sys.modules:
        try:
            _mod = importlib.import_module(_v1_name)
            sys.modules[_alias_name] = _mod
        except ImportError:
            pass

__all__ = [
    # Main API
    "Action",
    "ActionResult",
    "HTTPRequest",
    "HTTPResponse",
    "State",
    "Observation",
    "Context",
    "Graph",
    "Transition",
    "Invariant",
    "Violation",
    "V1Severity",
    "InvariantTiming",
    "ResponseAssertion",
    "ExplorationResult",
    # Legacy
    "ActionCallable",
    "Branch",
    "BranchResult",
    "Checkpoint",
    "ExecutionContext",
    "Issue",
    "Journey",
    "JourneyResult",
    "Path",
    "PathResult",
    "Severity",
    "Step",
    "StepOrCheckpointOrBranch",
    "StepResult",
]
