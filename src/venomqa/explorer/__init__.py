"""
VenomQA State Explorer Module.

This module provides automated state exploration capabilities for API testing.
It discovers endpoints, detects application states, explores state transitions,
and generates coverage reports and visualizations.

The main entry point is the StateExplorer class, which orchestrates all
exploration activities.

Example:
    from venomqa.explorer import StateExplorer

    explorer = StateExplorer(base_url="http://api.example.com")
    result = await explorer.explore()
    print(result.coverage.coverage_percent)
"""

from venomqa.explorer.context import (
    ExplorationContext,
    can_resolve_endpoint,
    extract_context_from_response,
    generate_state_name,
    get_required_placeholders,
    has_unresolved_placeholders,
    substitute_path_params,
)
from venomqa.explorer.detector import (
    StateDetector,
    extract_context,
)
from venomqa.explorer.detector import (
    generate_state_name as generate_state_name_legacy,
)
from venomqa.explorer.detector import (
    substitute_path_params as substitute_path_params_legacy,
)
from venomqa.explorer.discoverer import APIDiscoverer
from venomqa.explorer.engine import (
    ChainExplorationResult,
    ExplorationEngine,
    ExplorationError,
    ExplorationStrategy,
)
from venomqa.explorer.explorer import StateExplorer
from venomqa.explorer.models import (
    Action,
    ChainState,
    CoverageReport,
    ExplorationConfig,
    ExplorationResult,
    Issue,
    IssueSeverity,
    State,
    StateGraph,
    StateID,
    Transition,
)
from venomqa.explorer.reporter import ExplorationReporter, ReportFormat
from venomqa.explorer.visualizer import GraphVisualizer, OutputFormat

__all__ = [
    # Models
    "StateID",
    "State",
    "ChainState",
    "Transition",
    "Action",
    "StateGraph",
    "Issue",
    "IssueSeverity",
    "CoverageReport",
    "ExplorationResult",
    "ExplorationConfig",
    # Core classes
    "APIDiscoverer",
    "StateDetector",
    "ExplorationEngine",
    "ExplorationStrategy",
    "ExplorationError",
    "ChainExplorationResult",
    "GraphVisualizer",
    "OutputFormat",
    "ExplorationReporter",
    "ReportFormat",
    "StateExplorer",
    # Context functions (legacy from detector)
    "extract_context",
    # Context utilities (new robust implementation)
    "ExplorationContext",
    "extract_context_from_response",
    "substitute_path_params",
    "generate_state_name",
    "has_unresolved_placeholders",
    "get_required_placeholders",
    "can_resolve_endpoint",
]
