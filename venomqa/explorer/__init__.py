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

from venomqa.explorer.models import (
    StateID,
    State,
    ChainState,
    Transition,
    Action,
    StateGraph,
    Issue,
    IssueSeverity,
    CoverageReport,
    ExplorationResult,
    ExplorationConfig,
)
from venomqa.explorer.discoverer import APIDiscoverer
from venomqa.explorer.detector import StateDetector
from venomqa.explorer.engine import ExplorationEngine, ExplorationStrategy, ExplorationError
from venomqa.explorer.visualizer import GraphVisualizer, OutputFormat
from venomqa.explorer.reporter import ExplorationReporter, ReportFormat
from venomqa.explorer.explorer import StateExplorer

__all__ = [
    # Models
    "StateID",
    "State",
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
    "GraphVisualizer",
    "OutputFormat",
    "ExplorationReporter",
    "ReportFormat",
    "StateExplorer",
]
