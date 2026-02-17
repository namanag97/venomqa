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

# IMPORTANT: Import legacy modules FIRST (before aliasing), because
# venomqa.core.context and venomqa.core.graph exist as real files.
# We import ExecutionContext from the v0 context module before overriding
# the module entry in sys.modules.
from venomqa.core.context import ExecutionContext  # noqa: E402
from venomqa.core.models import (  # noqa: E402
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

# Now set up submodule aliasing: allow `from venomqa.core.action import Action` etc.
# For submodules that DON'T exist as real files in venomqa/core/,
# this creates sys.modules entries pointing to venomqa.v1.core.X.
# For context and graph that DO exist as real files, we override the
# already-loaded module entry with the v1 version.
_V1_CORE_SUBMODULES = [
    "action", "state", "context", "graph", "transition",
    "invariant", "result", "observers", "constraints",
    "coverage", "dimensions", "hyperedge", "hypergraph",
]

for _submod in _V1_CORE_SUBMODULES:
    _v1_name = f"venomqa.v1.core.{_submod}"
    _alias_name = f"venomqa.core.{_submod}"
    try:
        _mod = importlib.import_module(_v1_name)
        sys.modules[_alias_name] = _mod
    except ImportError:
        pass

# Main API (from v1) - these now resolve through the aliases above
from venomqa.v1.core.action import Action, ActionResult, HTTPRequest, HTTPResponse  # noqa: E402
from venomqa.v1.core.context import Context  # noqa: E402
from venomqa.v1.core.graph import Graph  # noqa: E402
from venomqa.v1.core.invariant import Invariant, InvariantTiming, ResponseAssertion, Severity as V1Severity, Violation  # noqa: E402
from venomqa.v1.core.result import ExplorationResult  # noqa: E402
from venomqa.v1.core.state import Observation, State  # noqa: E402
from venomqa.v1.core.transition import Transition  # noqa: E402

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
