"""VenomQA v1 - Clean, minimal API for stateful exploration testing.

This module provides the v1 API with ~18 exports instead of 300+.
Import what you need from here.

Example:
    from venomqa.v1 import State, Action, Graph, World, Agent, Invariant, explore
"""

from venomqa.v1.adapters.http import HttpClient
from venomqa.v1.auth import ApiKeyAuth, AuthHttpClient, BearerTokenAuth, MultiRoleAuth
from venomqa.v1.invariants import OpenAPISchemaInvariant
from venomqa.v1.agent import Agent, Scheduler
from venomqa.v1.agent.strategies import (
    BFS,
    DFS,
    CoverageGuided,
    DimensionNoveltyStrategy,
    Random,
    Strategy,
    Weighted,
)
from venomqa.v1.core.action import (
    Action,
    ActionResult,
    HTTPRequest,
    HTTPResponse,
    precondition_action_ran,
    precondition_has_context,
)
from venomqa.v1.core.constraints import (
    DEFAULT_CONSTRAINTS,
    AnonHasNoRole,
    AuthHasRole,
    FreeCannotExceedUsage,
    LambdaConstraint,
    StateConstraint,
    constraint,
)
from venomqa.v1.core.context import Context
from venomqa.v1.core.coverage import DimensionAxisCoverage, DimensionCoverage

# Hypergraph / multi-dimensional state space
from venomqa.v1.core.dimensions import (
    BUILTIN_DIMENSIONS,
    AuthStatus,
    CountClass,
    EntityStatus,
    PlanType,
    UsageClass,
    UserRole,
)
from venomqa.v1.core.graph import Graph
from venomqa.v1.core.hyperedge import Hyperedge
from venomqa.v1.core.hypergraph import Hypergraph
from venomqa.v1.core.invariant import (
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
from venomqa.v1.core.result import ExplorationResult
from venomqa.v1.core.state import Observation, State
from venomqa.v1.core.transition import Transition
from venomqa.v1.dsl import Branch, Journey, Path, Step
from venomqa.v1.dsl import Checkpoint as JourneyCheckpoint
from venomqa.v1.dsl.compiler import compile as compile_journey
from venomqa.v1.dsl.decorators import action, invariant

# Recording
from venomqa.v1.recording import RecordedRequest, RequestRecorder, generate_journey_code

# Setup helpers (high-level API)
from venomqa.v1.setup import connect_to_app, connect_to_api, setup_from_config

# Reporters
from venomqa.v1.reporters.console import ConsoleReporter
from venomqa.v1.reporters.dimension_report import DimensionCoverageReporter
from venomqa.v1.reporters.html_trace import HTMLTraceReporter
from venomqa.v1.reporters.json import JSONReporter
from venomqa.v1.reporters.junit import JUnitReporter
from venomqa.v1.reporters.markdown import MarkdownReporter

# Validation
from venomqa.v1.validation import (
    SchemaValidator,
    has_fields,
    is_list,
    matches_type,
    validate_response,
)
from venomqa.v1.world import World
from venomqa.v1.world.checkpoint import Checkpoint, SystemCheckpoint
from venomqa.v1.world.rollbackable import Rollbackable

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

    Returns:
        ExplorationResult with graph, violations, and statistics.

    Example:
        from venomqa.v1 import Journey, Step, Checkpoint, explore

        journey = Journey(
            name="login_test",
            steps=[
                Step("login", login_action),
                Checkpoint("logged_in"),
                Step("logout", logout_action),
            ],
        )

        result = explore("http://localhost:8000", journey)
        assert result.success
    """
    from venomqa.v1.adapters.http import HttpClient
    from venomqa.v1.dsl.compiler import compile

    # Create HTTP client
    api = HttpClient(base_url)

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
    compiled = compile(journey)

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
    "setup_from_config",
    # Type aliases
    "StateID",
    "TransitionID",
    "CheckpointID",
    "ViolationID",
]
