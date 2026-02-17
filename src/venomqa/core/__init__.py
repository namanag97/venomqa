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

# Submodule aliasing FIRST: allow `from venomqa.core.action import Action` etc.
# This must happen before any imports from venomqa.core.* submodules
# so that the v1 modules take precedence.
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

# Main API (from v1)
from venomqa.v1.core.action import Action, ActionResult, HTTPRequest, HTTPResponse  # noqa: E402
from venomqa.v1.core.context import Context  # noqa: E402
from venomqa.v1.core.graph import Graph  # noqa: E402
from venomqa.v1.core.invariant import Invariant, InvariantTiming, ResponseAssertion, Severity as V1Severity, Violation  # noqa: E402
from venomqa.v1.core.result import ExplorationResult  # noqa: E402
from venomqa.v1.core.state import Observation, State  # noqa: E402
from venomqa.v1.core.transition import Transition  # noqa: E402

# Legacy exports - import from the actual files (not the aliases)
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

# ExecutionContext: must import from the v0 context module directly since
# we aliased venomqa.core.context -> venomqa.v1.core.context
from venomqa.v1.core.context import Context as _V1Context  # noqa: E402
_v0_context = importlib.import_module("venomqa.core.context")
# The v0 context module is now shadowed in sys.modules by the v1 version.
# We need to get ExecutionContext from the actual v0 file.
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "venomqa.core._v0_context",
    str(__import__("pathlib").Path(__file__).parent / "context.py"),
)
if _spec and _spec.loader:
    _v0_mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_v0_mod)
    ExecutionContext = _v0_mod.ExecutionContext
else:
    ExecutionContext = None  # type: ignore

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
