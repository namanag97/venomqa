"""Testing Modes for VenomQA.

Testing modes define HOW VenomQA connects to and controls the system under test.
This is orthogonal to exploration strategies (BFS, DFS) which define the ORDER
of state exploration.

┌─────────────────────────────────────────────────────────────────────────────┐
│                        VenomQA Testing Architecture                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   EXPLORATION STRATEGY          TESTING MODE                                │
│   (traversal order)             (system topology)                           │
│                                                                             │
│   ┌─────────────────┐           ┌─────────────────┐                        │
│   │ BFS / DFS /     │     +     │ InProcess /     │     =     Full Test    │
│   │ Random / etc    │           │ FullSystem /    │           Configuration│
│   └─────────────────┘           │ Protocol        │                        │
│                                 └─────────────────┘                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

TESTING MODES:

1. InProcess Mode (Unit/Component Testing)
   ════════════════════════════════════════

   ┌────────────────────────────────────────────────────────────────┐
   │                     SAME PYTHON PROCESS                        │
   │                                                                │
   │  ┌──────────────┐          ┌──────────────┐                   │
   │  │   VenomQA    │──ASGI───▶│  FastAPI/    │                   │
   │  │   Agent      │          │  Starlette   │                   │
   │  └──────┬───────┘          └──────┬───────┘                   │
   │         │                         │                            │
   │         │    SHARED CONNECTION    │                            │
   │         └────────────┬────────────┘                            │
   │                      ▼                                         │
   │              ┌──────────────┐                                  │
   │              │  PostgreSQL  │                                  │
   │              │  (SAVEPOINT) │                                  │
   │              └──────────────┘                                  │
   │                                                                │
   └────────────────────────────────────────────────────────────────┘

   Sequence Diagram:
   ─────────────────
   VenomQA          FastAPI           PostgreSQL
      │                │                  │
      │───BEGIN───────────────────────────▶│
      │                │                  │
      │──SAVEPOINT s1─────────────────────▶│
      │                │                  │
      │──POST /users──▶│                  │
      │                │──INSERT──────────▶│
      │                │                  │ (not committed!)
      │◀──201─────────│                  │
      │                │                  │
      │──SAVEPOINT s2─────────────────────▶│
      │                │                  │
      │──DELETE /users/1▶│                │
      │                │──DELETE──────────▶│
      │◀──204─────────│                  │
      │                │                  │
      │──ROLLBACK TO s1───────────────────▶│
      │                │                  │ (user restored!)
      │                │                  │
      │──PUT /users/1──▶│                 │
      │                │──UPDATE──────────▶│
      │◀──200─────────│                  │
      │                │                  │
      │──ROLLBACK─────────────────────────▶│
      │                │                  │ (all changes gone)

   ✓ SAVEPOINT rollback works (shared connection)
   ✓ Fast (no network overhead)
   ✓ Good for CI/unit testing
   ✗ Not testing real deployment
   ✗ Python apps only (FastAPI, Starlette)


2. FullSystem Mode (Integration/E2E Testing)
   ═══════════════════════════════════════════

   ┌────────────────────────────────────────────────────────────────┐
   │                     SEPARATE PROCESSES                         │
   │                                                                │
   │  ┌──────────────┐                                             │
   │  │   VenomQA    │                                             │
   │  │   (Python)   │                                             │
   │  └──────┬───────┘                                             │
   │         │                                                      │
   │         │ HTTP                                                 │
   │         ▼                                                      │
   │  ┌──────────────────────────────────────────────────────┐     │
   │  │              PRODUCTION-LIKE STACK                    │     │
   │  │                                                       │     │
   │  │  ┌──────────┐   ┌──────────┐   ┌──────────────────┐  │     │
   │  │  │   API    │──▶│ Temporal │──▶│ Data Pipeline    │  │     │
   │  │  │ (any     │   │ Workflow │   │ (Kafka, Iceberg) │  │     │
   │  │  │ language)│   └──────────┘   └──────────────────┘  │     │
   │  │  └────┬─────┘                                        │     │
   │  │       │                                              │     │
   │  │       ▼                                              │     │
   │  │  ┌──────────┐                                        │     │
   │  │  │ Postgres │                                        │     │
   │  │  └──────────┘                                        │     │
   │  └──────────────────────────────────────────────────────┘     │
   │                                                                │
   └────────────────────────────────────────────────────────────────┘

   Sequence Diagram:
   ─────────────────
   VenomQA          API            Temporal        Postgres       Iceberg
      │              │                │               │              │
      │──POST /job──▶│                │               │              │
      │              │──start workflow▶│              │              │
      │              │                │──INSERT───────▶│             │
      │              │                │               │              │
      │              │                │───────────────────write──────▶│
      │◀──202───────│                │               │              │
      │              │                │               │              │
      │──GET /job/1─▶│                │               │              │
      │◀─{status}───│                │               │              │
      │              │                │               │              │
      │  (poll until workflow completes)              │              │
      │              │                │               │              │
      │──verify data in Iceberg──────────────────────────────────────▶│
      │◀─data rows──────────────────────────────────────────────────│

   ✓ Tests REAL system (Temporal, Kafka, Iceberg, etc.)
   ✓ Works with any language (Node.js, Go, Java)
   ✓ Catches integration bugs
   ✗ Slower (network, async workflows)
   ✗ SAVEPOINT rollback requires Protocol implementation


3. Protocol Mode (Cross-Language with Rollback)
   ══════════════════════════════════════════════

   ┌────────────────────────────────────────────────────────────────┐
   │                     SEPARATE PROCESSES                         │
   │                                                                │
   │  ┌──────────────┐          ┌──────────────────────────────┐   │
   │  │   VenomQA    │──HTTP───▶│  API (Node.js/Go/Java)       │   │
   │  │   (Python)   │          │                              │   │
   │  └──────────────┘          │  Implements:                 │   │
   │                            │  • POST /venomqa/begin       │   │
   │   Control Protocol:        │  • POST /venomqa/checkpoint  │   │
   │   ───────────────          │  • POST /venomqa/rollback    │   │
   │   VenomQA sends            │  • POST /venomqa/end         │   │
   │   checkpoint/rollback      │                              │   │
   │   commands over HTTP       └──────────────┬───────────────┘   │
   │                                           │                    │
   │                                           │ CONTROLLED         │
   │                                           │ CONNECTION         │
   │                                           ▼                    │
   │                                   ┌──────────────┐             │
   │                                   │  PostgreSQL  │             │
   │                                   │  (SAVEPOINT) │             │
   │                                   └──────────────┘             │
   │                                                                │
   └────────────────────────────────────────────────────────────────┘

   Sequence Diagram:
   ─────────────────
   VenomQA                API (Node.js)           PostgreSQL
      │                        │                      │
      │──POST /venomqa/begin──▶│                      │
      │                        │──BEGIN───────────────▶│
      │◀─{session_id}─────────│                      │
      │                        │                      │
      │──POST /venomqa/checkpoint─▶│                  │
      │                        │──SAVEPOINT s1────────▶│
      │◀─{checkpoint_id: s1}──│                      │
      │                        │                      │
      │──POST /users──────────▶│                      │
      │  [X-VenomQA-Session]   │──INSERT──────────────▶│
      │◀─201──────────────────│                      │
      │                        │                      │
      │──POST /venomqa/rollback {s1}─▶│               │
      │                        │──ROLLBACK TO s1──────▶│
      │◀─{status: rolled_back}│                      │
      │                        │                      │
      │──POST /venomqa/end────▶│                      │
      │                        │──ROLLBACK────────────▶│
      │◀─{status: ended}──────│                      │

   ✓ Full SAVEPOINT rollback (like InProcess)
   ✓ Works with any language (via Protocol SDK)
   ✓ Tests real HTTP layer
   ✗ Requires API to implement Protocol
   ✗ Single database (no Temporal/Iceberg rollback)


CHOOSING A MODE:

┌───────────────────────────────────────────────────────────────────────────┐
│                                                                           │
│  Is your API in Python (FastAPI/Starlette)?                              │
│         │                                                                 │
│    YES  │  NO                                                             │
│    │    │                                                                 │
│    │    └──▶ Can you implement VenomQA Protocol in your API?             │
│    │              │                                                       │
│    │         YES  │  NO                                                   │
│    │         │    │                                                       │
│    │         │    └──▶ Use FullSystem Mode                               │
│    │         │         (limited rollback, full integration)               │
│    │         │                                                            │
│    │         └──▶ Use Protocol Mode                                       │
│    │              (full rollback, cross-language)                         │
│    │                                                                      │
│    └──▶ Do you need to test with Temporal/Kafka/Iceberg?                 │
│              │                                                            │
│         YES  │  NO                                                        │
│         │    │                                                            │
│         │    └──▶ Use InProcess Mode                                      │
│         │         (fastest, full rollback)                                │
│         │                                                                 │
│         └──▶ Use FullSystem Mode                                          │
│              (test complete stack, limited rollback)                      │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘


CRITICAL: STRATEGY + DATABASE COMPATIBILITY
═══════════════════════════════════════════

PostgreSQL SAVEPOINTs are a LIFO STACK. You can only rollback to the
most recent savepoint, then the one before it, etc. You CANNOT jump
to an arbitrary savepoint without destroying all savepoints after it.

   SAVEPOINT Stack:        Valid Rollback:       Invalid Rollback:
   ┌─────────────┐         ┌─────────────┐       ┌─────────────┐
   │    sp_3     │ ◀─ top  │    sp_3     │ ◀──   │    sp_3     │ destroyed!
   ├─────────────┤         ├─────────────┤       ├─────────────┤
   │    sp_2     │         │    sp_2     │       │    sp_2     │ destroyed!
   ├─────────────┤         ├─────────────┤       ├─────────────┤
   │    sp_1     │         │    sp_1     │       │    sp_1     │ ◀── jump here
   └─────────────┘         └─────────────┘       └─────────────┘
                           ROLLBACK TO sp_3     ROLLBACK TO sp_1
                           (OK - top of stack)   (DESTROYS sp_2, sp_3!)

DFS (Depth-First Search):
   Explores deep, then backtracks. Rollbacks are always LIFO.
   ✓ SAFE with PostgreSQL

   Exploration:           Rollbacks:
   sp_1 → sp_2 → sp_3     sp_3 → sp_2 → sp_1  (LIFO - matches stack!)

BFS / CoverageGuided / Weighted / Random:
   Jump to arbitrary states. Rollbacks are NOT LIFO.
   ✗ UNSAFE with PostgreSQL - will crash or corrupt state!

   Exploration:           Rollbacks needed:
   sp_1 → sp_2 → sp_3     sp_1 (jump!) → sp_3 (???) → sp_2 (???)
                          Can't jump to sp_1 without destroying sp_2, sp_3!

STRATEGY COMPATIBILITY MATRIX:
┌─────────────────────┬────────────┬──────────┬──────────────────────────┐
│ Strategy            │ PostgreSQL │ SQLite   │ MockHTTPServer           │
├─────────────────────┼────────────┼──────────┼──────────────────────────┤
│ DFS                 │ ✓ SAFE     │ ✓ SAFE   │ ✓ SAFE                   │
│ BFS                 │ ✗ UNSAFE   │ ✓ SAFE   │ ✓ SAFE (uses snapshots)  │
│ CoverageGuided      │ ✗ UNSAFE   │ ✓ SAFE   │ ✓ SAFE                   │
│ Weighted            │ ✗ UNSAFE   │ ✓ SAFE   │ ✓ SAFE                   │
│ Random              │ ✗ UNSAFE   │ ✓ SAFE   │ ✓ SAFE                   │
│ DimensionNovelty    │ ✗ UNSAFE   │ ✓ SAFE   │ ✓ SAFE                   │
└─────────────────────┴────────────┴──────────┴──────────────────────────┘

WHY SQLITE IS DIFFERENT:
   SQLite allows copying the entire database file, creating true
   independent snapshots. VenomQA can restore any snapshot without
   affecting others.

WHY MockHTTPServer IS DIFFERENT:
   In-memory state can be deep-copied (dict.copy(), etc.), creating
   true independent snapshots.

RECOMMENDATION:
   • PostgreSQL: ALWAYS use DFS()
   • SQLite: Any strategy works
   • In-memory mocks: Any strategy works

"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from venomqa.v1.world import World


class TestingModeType(Enum):
    """Type of testing mode."""

    IN_PROCESS = "in_process"
    FULL_SYSTEM = "full_system"
    PROTOCOL = "protocol"


@dataclass
class TestingModeConfig:
    """Configuration for a testing mode."""

    mode_type: TestingModeType
    description: str

    # InProcess mode
    app: Any | None = None
    db_dependency: Callable | None = None

    # FullSystem / Protocol mode
    api_url: str | None = None
    db_url: str | None = None

    # Protocol mode
    control_prefix: str = "/venomqa"

    # FullSystem mode
    state_keys: list[str] | None = None

    # Async workflows (Temporal, etc.)
    workflow_poll_interval: float = 1.0
    workflow_timeout: float = 60.0


class TestingMode(ABC):
    """Base class for testing modes.

    Testing modes define how VenomQA connects to the system under test
    and how it manages state rollback.
    """

    @property
    @abstractmethod
    def mode_type(self) -> TestingModeType:
        """Return the mode type."""
        ...

    @abstractmethod
    def create_world(self) -> World:
        """Create and configure the World for this mode."""
        ...

    @property
    @abstractmethod
    def supports_full_rollback(self) -> bool:
        """Whether this mode supports full SAVEPOINT rollback."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description of the mode."""
        return self.__class__.__doc__ or ""


class InProcessMode(TestingMode):
    """In-process testing mode for FastAPI/Starlette applications.

    Runs the API in the same Python process as VenomQA, sharing
    a database connection for true SAVEPOINT rollback support.

    Best for: Fast CI testing, Python APIs, unit/component testing
    """

    def __init__(
        self,
        app: Any,
        db_dependency: Callable,
        db_url: str,
        async_mode: bool = False,
    ):
        self.app = app
        self.db_dependency = db_dependency
        self.db_url = db_url
        self.async_mode = async_mode

    @property
    def mode_type(self) -> TestingModeType:
        return TestingModeType.IN_PROCESS

    @property
    def supports_full_rollback(self) -> bool:
        return True

    def create_world(self) -> World:
        from venomqa.v1.setup import connect_to_app

        return connect_to_app(
            app=self.app,
            db_dependency=self.db_dependency,
            db_url=self.db_url,
            async_mode=self.async_mode,
        )


class FullSystemMode(TestingMode):
    """Full system testing mode for complete integration testing.

    Tests the entire stack including async workflows (Temporal),
    data pipelines (Kafka, Iceberg), and multi-service architectures.

    Best for: E2E testing, pre-release validation, multi-service systems
    """

    def __init__(
        self,
        api_url: str,
        db_url: str | None = None,
        state_keys: list[str] | None = None,
        workflow_poll_interval: float = 1.0,
        workflow_timeout: float = 60.0,
    ):
        self.api_url = api_url
        self.db_url = db_url
        self.state_keys = state_keys
        self.workflow_poll_interval = workflow_poll_interval
        self.workflow_timeout = workflow_timeout

    @property
    def mode_type(self) -> TestingModeType:
        return TestingModeType.FULL_SYSTEM

    @property
    def supports_full_rollback(self) -> bool:
        # Limited rollback - can't rollback committed transactions
        # or async workflow side effects
        return False

    def create_world(self) -> World:
        from venomqa.v1.setup import connect_to_api

        return connect_to_api(
            api_url=self.api_url,
            db_url=self.db_url,
            state_keys=self.state_keys,
        )


class ProtocolMode(TestingMode):
    """Protocol-based testing mode for cross-language APIs.

    Uses the VenomQA Control Protocol to communicate with APIs
    written in any language (Node.js, Go, Java, etc.) that implement
    the protocol endpoints.

    Best for: Non-Python APIs, microservices, cross-language testing
    """

    def __init__(
        self,
        api_url: str,
        control_prefix: str = "/venomqa",
    ):
        self.api_url = api_url
        self.control_prefix = control_prefix

    @property
    def mode_type(self) -> TestingModeType:
        return TestingModeType.PROTOCOL

    @property
    def supports_full_rollback(self) -> bool:
        return True  # Protocol enables SAVEPOINT control

    def create_world(self) -> World:
        from venomqa.v1.setup import connect_to_protocol

        return connect_to_protocol(
            api_url=self.api_url,
            control_prefix=self.control_prefix,
        )


# Convenience factory functions


def in_process(
    app: Any,
    db_dependency: Callable,
    db_url: str,
    async_mode: bool = False,
) -> InProcessMode:
    """Create an in-process testing mode.

    Args:
        app: FastAPI or Starlette application
        db_dependency: The get_db dependency function
        db_url: PostgreSQL connection URL
        async_mode: Use async SQLAlchemy

    Returns:
        Configured InProcessMode
    """
    return InProcessMode(app, db_dependency, db_url, async_mode)


def full_system(
    api_url: str,
    db_url: str | None = None,
    state_keys: list[str] | None = None,
) -> FullSystemMode:
    """Create a full system testing mode.

    Args:
        api_url: Base URL of the API
        db_url: Optional database URL for state tracking
        state_keys: Context keys for state identity (if no db)

    Returns:
        Configured FullSystemMode
    """
    return FullSystemMode(api_url, db_url, state_keys)


def protocol(
    api_url: str,
    control_prefix: str = "/venomqa",
) -> ProtocolMode:
    """Create a protocol-based testing mode.

    Args:
        api_url: Base URL of the API
        control_prefix: URL prefix for control endpoints

    Returns:
        Configured ProtocolMode
    """
    return ProtocolMode(api_url, control_prefix)
