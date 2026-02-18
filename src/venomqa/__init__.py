"""VenomQA - Autonomous API QA Agent.

Define Actions and Invariants. VenomQA explores every state path automatically.

Quick Start:
    from venomqa import Action, Invariant, World, Agent, HttpClient

    api = HttpClient("http://localhost:8000")
    world = World(api=api, systems={"db": db})

    # Define actions and invariants...
    # Then explore with Agent

See: https://venomqa.dev for full documentation.
"""

from __future__ import annotations

import importlib
import sys

# Adapters
from venomqa.v1.adapters.http import HttpClient

# Backwards compatibility alias
Client = HttpClient
from venomqa.v1.adapters.resource_graph import (
    ResourceGraph,
    ResourceSchema,
    ResourceType,
    schema_from_openapi,
)
from venomqa.v1.adapters.sqlite import SQLiteAdapter

# Agent (exploration engine)
from venomqa.v1.agent import Agent, Scheduler

# Exploration strategies (canonical location is venomqa.exploration)
from venomqa.exploration import (
    BFS,
    DFS,
    CoverageGuided,
    ExplorationStrategy,
    Random,
    Strategy,
    Weighted,
)
from venomqa.v1.agent.dimension_strategy import DimensionNoveltyStrategy

# Auth helpers
from venomqa.v1.auth import ApiKeyAuth, AuthHttpClient, BearerTokenAuth, MultiRoleAuth

# =============================================================================
# MAIN API - Import these directly: from venomqa import Action, State, ...
# =============================================================================
# Core types
from venomqa.v1.core.action import (
    Action,
    ActionResult,
    HTTPRequest,
    HTTPResponse,
    precondition_action_ran,
    precondition_has_context,
)

# Constraints
from venomqa.v1.core.constraints import (
    DEFAULT_CONSTRAINTS,
    AnonHasNoRole,
    AuthHasRole,
    FreeCannotExceedUsage,
    LambdaConstraint,
    StateConstraint,
    constraint,
)
# Sandbox context (canonical location for World, Context, State)
from venomqa.sandbox import Context

# Coverage
from venomqa.v1.core.coverage import DimensionAxisCoverage, DimensionCoverage

# Dimensions (hypergraph / multi-dimensional state space)
from venomqa.v1.core.dimensions import (
    BUILTIN_DIMENSIONS,
    AuthStatus,
    CountClass,
    EntityStatus,
    PlanType,
    UsageClass,
    UserRole,
)
# Exploration types (canonical location is venomqa.exploration)
from venomqa.exploration import Graph
from venomqa.v1.core.hyperedge import Hyperedge
from venomqa.v1.core.hypergraph import Hypergraph
from venomqa.v1.core.invariant import (
    Bug,
    Invariant,
    InvariantTiming,
    ResponseAssertion,
    Severity,
    Violation,
)

# Observation helpers
from venomqa.v1.core.observers import (
    COMMON_QUERIES,
    aggregate,
    column_value,
    combine_observers,
    has_rows,
    latest_row,
    row_with_status,
)
from venomqa.exploration import ExplorationResult
from venomqa.sandbox import Observation, State
from venomqa.exploration import Transition

# DSL (Journey definition)
from venomqa.v1.dsl import Branch, Journey, Path, Step
from venomqa.v1.dsl import Checkpoint as JourneyCheckpoint
from venomqa.v1.dsl.compiler import compile as compile_journey
from venomqa.v1.dsl.decorators import action, invariant

# Generators (OpenAPI action generation)
from venomqa.v1.generators.openapi_actions import (
    generate_actions,
    generate_schema_and_actions,
)

# Built-in invariants
from venomqa.v1.invariants import OpenAPISchemaInvariant

# Testing modes (deployment topology)
from venomqa.v1.modes import (
    FullSystemMode,
    InProcessMode,
    ProtocolMode,
    TestingMode,
    TestingModeType,
    full_system,
    in_process,
    protocol,
)

# Recording
from venomqa.v1.recording import RecordedRequest, RequestRecorder, generate_journey_code

# Reporters
from venomqa.v1.reporters.console import ConsoleReporter
from venomqa.v1.reporters.dimension_report import DimensionCoverageReporter
from venomqa.v1.reporters.html_trace import HTMLTraceReporter
from venomqa.v1.reporters.json import JSONReporter
from venomqa.v1.reporters.junit import JUnitReporter
from venomqa.v1.reporters.markdown import MarkdownReporter

# Setup helpers (high-level API)
from venomqa.v1.setup import connect_to_api, connect_to_app, connect_to_protocol, setup_from_config

# Validation
from venomqa.v1.validation import (
    SchemaValidator,
    has_fields,
    is_list,
    matches_type,
    validate_response,
)

# World (sandbox with checkpoint/rollback) - canonical location is venomqa.sandbox
from venomqa.sandbox import Checkpoint, Rollbackable, SystemCheckpoint, World

# Type aliases
StateID = str
TransitionID = str
CheckpointID = str
ViolationID = str


def explore(
    base_url: str,
    journey: Journey,
    *,
    db_url: str | None = None,
    redis_url: str | None = None,
    strategy: Strategy | None = None,
    max_steps: int = 1000,
    coverage_target: float | None = None,
    progress_every: int = 0,
) -> ExplorationResult:
    """Convenience function for running an exploration.

    This is the simplest way to run VenomQA. It:
    1. Creates an HTTP client for the base URL
    2. Sets up database/cache adapters if URLs provided
    3. Compiles the Journey to Actions
    4. Creates an Agent and runs exploration
    5. Returns the result

    Args:
        base_url: The base URL of the API to test.
        journey: The Journey DSL defining the test flow.
        db_url: Optional PostgreSQL connection string.
        redis_url: Optional Redis connection string.
        strategy: Exploration strategy (default: BFS).
        max_steps: Maximum exploration steps (default: 1000).
        coverage_target: Optional coverage percentage target (0.0 to 1.0).
        progress_every: Print progress every N steps (0 = disabled).

    Returns:
        ExplorationResult with graph, violations, and statistics.

    Example:
        from venomqa import Journey, Step, explore

        journey = Journey(
            name="login_test",
            steps=[
                Step("login", login_action),
                Step("logout", logout_action),
            ],
        )

        result = explore("http://localhost:8000", journey)
        assert result.success
    """
    from venomqa.v1.adapters.http import HttpClient as _HttpClient
    from venomqa.v1.dsl.compiler import compile as _compile

    # Create HTTP client
    api = _HttpClient(base_url)

    # Set up systems
    systems: dict[str, Rollbackable] = {}

    if db_url:
        from venomqa.v1.adapters.postgres import PostgresAdapter
        systems["db"] = PostgresAdapter(db_url)

    if redis_url:
        from venomqa.v1.adapters.redis import RedisAdapter
        systems["cache"] = RedisAdapter(redis_url)

    # Create world
    world = World(api=api, systems=systems)

    # Compile journey
    compiled = _compile(journey)

    # Create and run agent
    agent = Agent(
        world=world,
        actions=compiled.actions,
        invariants=compiled.invariants,
        strategy=strategy or BFS(),
        max_steps=max_steps,
        coverage_target=coverage_target,
        progress_every=progress_every,
    )

    return agent.explore()


# =============================================================================
# Module aliasing: allow `from venomqa.world import World` etc.
#
# For subpackages that only exist under v1/ (not at the v0 top-level),
# we register sys.modules aliases so Python resolves them automatically.
# =============================================================================

_V1_ONLY_SUBPACKAGES = [
    "agent",
    "bridge",
    "dsl",
    "invariants",
    "recording",
    "validation",
    "world",
    "modes",
    "setup",
    "auth",
]

for _subpkg in _V1_ONLY_SUBPACKAGES:
    _v1_name = f"venomqa.v1.{_subpkg}"
    _alias_name = f"venomqa.{_subpkg}"
    # Only create alias if the v1 module is already imported or can be imported,
    # AND there's no existing top-level module with that name
    if _alias_name not in sys.modules:
        try:
            _mod = importlib.import_module(_v1_name)
            sys.modules[_alias_name] = _mod
        except ImportError:
            pass


__version__ = "0.5.0"
__author__ = "Naman Agarwal"
__license__ = "MIT"

__all__ = [
    # Core
    "State",
    "Observation",
    "Context",
    "Action",
    "ActionResult",
    "HTTPRequest",
    "HTTPResponse",
    "Transition",
    "Graph",
    "Invariant",
    "Violation",
    "Severity",
    "InvariantTiming",
    "ResponseAssertion",
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
    "CoverageGuided",
    "Weighted",
    "DimensionNoveltyStrategy",
    "Scheduler",
    # Hypergraph
    "AuthStatus",
    "UserRole",
    "EntityStatus",
    "CountClass",
    "UsageClass",
    "PlanType",
    "BUILTIN_DIMENSIONS",
    "Hyperedge",
    "Hypergraph",
    "StateConstraint",
    "AnonHasNoRole",
    "AuthHasRole",
    "FreeCannotExceedUsage",
    "LambdaConstraint",
    "constraint",
    "DEFAULT_CONSTRAINTS",
    "DimensionCoverage",
    "DimensionAxisCoverage",
    "DimensionCoverageReporter",
    # DSL
    "Journey",
    "Step",
    "JourneyCheckpoint",
    "Branch",
    "Path",
    "action",
    "invariant",
    "compile_journey",
    # Built-in invariants
    "OpenAPISchemaInvariant",
    # Auth helpers
    "BearerTokenAuth",
    "ApiKeyAuth",
    "MultiRoleAuth",
    "AuthHttpClient",
    # Adapters
    "HttpClient",
    "SQLiteAdapter",
    # ResourceGraph
    "ResourceGraph",
    "ResourceSchema",
    "ResourceType",
    "schema_from_openapi",
    # Generators
    "generate_actions",
    "generate_schema_and_actions",
    # Recording
    "RequestRecorder",
    "RecordedRequest",
    "generate_journey_code",
    # Reporters
    "ConsoleReporter",
    "MarkdownReporter",
    "JSONReporter",
    "JUnitReporter",
    "HTMLTraceReporter",
    # Validation
    "SchemaValidator",
    "validate_response",
    "has_fields",
    "is_list",
    "matches_type",
    # Observation helpers
    "has_rows",
    "latest_row",
    "row_with_status",
    "column_value",
    "aggregate",
    "combine_observers",
    "COMMON_QUERIES",
    # Precondition helpers
    "precondition_has_context",
    "precondition_action_ran",
    # Convenience
    "explore",
    # Setup helpers
    "connect_to_app",
    "connect_to_api",
    "connect_to_protocol",
    "setup_from_config",
    # Testing modes
    "TestingMode",
    "TestingModeType",
    "InProcessMode",
    "FullSystemMode",
    "ProtocolMode",
    "in_process",
    "full_system",
    "protocol",
    # Type aliases
    "StateID",
    "TransitionID",
    "CheckpointID",
    "ViolationID",
]
