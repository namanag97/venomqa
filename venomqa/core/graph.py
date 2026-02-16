"""State Graph: Model your app as nodes (states) and edges (actions).

This module enables state-based testing where:
- Nodes represent application states (e.g., "no_files", "has_files", "at_quota")
- Edges represent actions that transition between states (e.g., "upload_file")
- Invariants are rules that must hold true at every state
- The explorer traverses all paths and verifies invariants

Architecture:
    The exploration uses a parent-pointer tree structure for memory efficiency.
    Instead of copying path/context at each branch (O(B^D * D) memory), we store
    parent pointers and reconstruct paths on demand (O(total_nodes) memory).

    Exploration uses DFS with explicit stack, streaming results as paths complete.
    This bounds memory to O(depth) for the stack, regardless of branching factor.

Example:
    >>> from venomqa.core.graph import StateGraph, StateNode, Edge, Invariant
    >>>
    >>> graph = StateGraph(name="todo_app")
    >>>
    >>> # Define states
    >>> graph.add_node("empty", description="No todos exist")
    >>> graph.add_node("has_todos", description="At least one todo exists")
    >>> graph.add_node("all_completed", description="All todos are completed")
    >>>
    >>> # Define transitions
    >>> graph.add_edge("empty", "has_todos", action=create_todo, name="create")
    >>> graph.add_edge("has_todos", "empty", action=delete_all, name="delete_all")
    >>> graph.add_edge("has_todos", "all_completed", action=complete_todo, name="complete")
    >>>
    >>> # Define invariants
    >>> graph.add_invariant(
    ...     name="count_matches",
    ...     check=lambda ctx: ctx["api_count"] == ctx["db_count"],
    ...     description="API count matches database count"
    ... )
    >>>
    >>> # Explore all paths (streaming internally, returns accumulated result)
    >>> result = graph.explore(client, db_connection)
    >>> print(result.summary())
    >>>
    >>> # Or stream results as they complete (memory-efficient for large graphs)
    >>> for path_result in graph.explore_iter(client, db_connection):
    ...     if not path_result.success:
    ...         print(f"Failed: {path_result.path}")
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Iterator, Protocol

logger = logging.getLogger(__name__)


class StateChecker(Protocol):
    """Protocol for checking if app is in a specific state."""

    def __call__(self, client: Any, db: Any, context: dict[str, Any]) -> bool:
        """Return True if the app is in this state."""
        ...


class InvariantChecker(Protocol):
    """Protocol for checking invariants."""

    def __call__(self, client: Any, db: Any, context: dict[str, Any]) -> bool:
        """Return True if invariant holds."""
        ...


class ActionCallable(Protocol):
    """Protocol for edge actions."""

    def __call__(self, client: Any, context: dict[str, Any]) -> Any:
        """Execute the action, return response."""
        ...


class Severity(Enum):
    """Severity levels for invariant violations."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class StateNode:
    """A node in the state graph representing an application state.

    Attributes:
        id: Unique identifier for this state
        description: Human-readable description
        checker: Function to verify app is in this state
        entry_actions: Actions to run when entering this state (for setup)
    """
    id: str
    description: str = ""
    checker: StateChecker | None = None
    entry_actions: list[ActionCallable] = field(default_factory=list)

    def is_current(self, client: Any, db: Any, context: dict[str, Any]) -> bool:
        """Check if the app is currently in this state."""
        if self.checker is None:
            return True  # No checker means always valid
        return self.checker(client, db, context)


@dataclass
class Edge:
    """An edge in the state graph representing an action/transition.

    Attributes:
        from_node: Source state ID
        to_node: Target state ID
        name: Action name
        action: Callable that performs the action
        variants: Different ways to perform this action (e.g., upload_csv, upload_xlsx)
    """
    from_node: str
    to_node: str
    name: str
    action: ActionCallable
    description: str = ""
    variants: list[Edge] = field(default_factory=list)


@dataclass
class Invariant:
    """A rule that must always be true after any action.

    Attributes:
        name: Unique identifier
        check: Function that returns True if invariant holds
        description: What this invariant verifies
        severity: How bad is it if this fails
        sql: Optional SQL query for database-level checks
    """
    name: str
    check: InvariantChecker
    description: str = ""
    severity: Severity = Severity.HIGH
    sql: str | None = None


@dataclass
class InvariantViolation:
    """Record of an invariant failure."""
    invariant: Invariant
    node: StateNode
    edge: Edge | None
    timestamp: datetime
    context_snapshot: dict[str, Any]
    error_message: str = ""


@dataclass
class EdgeResult:
    """Result of executing an edge."""
    edge: Edge
    success: bool
    response: Any
    duration_ms: float
    error: str | None = None
    invariant_violations: list[InvariantViolation] = field(default_factory=list)


@dataclass
class PathResult:
    """Result of exploring one path through the graph."""
    path: list[str]  # Node IDs
    edges_taken: list[Edge]
    edge_results: list[EdgeResult]
    success: bool
    invariant_violations: list[InvariantViolation] = field(default_factory=list)


@dataclass(slots=True)
class ExplorationNode:
    """A node in the exploration tree with parent pointer for structural sharing.

    Instead of copying the full path and context at each branch point, we store
    a pointer to the parent node. Path and context are reconstructed by walking
    parent pointers when needed (typically only for failed paths in reports).

    This reduces memory from O(B^D * D) to O(total_nodes) where B is branching
    factor and D is depth.

    Attributes:
        state_id: The graph node ID this exploration node represents.
        parent: Parent exploration node (None for root).
        edge: The edge taken to reach this node (None for root).
        response: Response from executing the edge action.
        duration_ms: Time taken to execute the edge action.
        error: Error message if edge execution failed.
        depth: Depth in the exploration tree (0 for root).
        invariant_violations: Violations found at this node.
    """
    state_id: str
    parent: ExplorationNode | None
    edge: Edge | None
    response: Any
    duration_ms: float
    error: str | None
    depth: int
    invariant_violations: list[InvariantViolation] = field(default_factory=list)

    def get_path(self) -> list[str]:
        """Reconstruct the full path by walking parent pointers.

        Returns:
            List of node IDs from root to this node.

        Complexity: O(depth)
        """
        path: list[str] = []
        node: ExplorationNode | None = self
        while node is not None:
            path.append(node.state_id)
            node = node.parent
        path.reverse()
        return path

    def get_edges(self) -> list[Edge]:
        """Reconstruct the list of edges taken by walking parent pointers.

        Returns:
            List of edges from root to this node.

        Complexity: O(depth)
        """
        edges: list[Edge] = []
        node: ExplorationNode | None = self
        while node is not None:
            if node.edge is not None:
                edges.append(node.edge)
            node = node.parent
        edges.reverse()
        return edges

    def get_context(self) -> dict[str, Any]:
        """Reconstruct context by walking parent pointers and collecting responses.

        Returns:
            Dict with all response data accumulated along the path.

        Complexity: O(depth)
        """
        context: dict[str, Any] = {}
        node: ExplorationNode | None = self
        while node is not None:
            if node.edge is not None and node.response is not None:
                context[f"_response_{node.edge.name}"] = node.response
                # Try to extract JSON if response has .json() method
                if hasattr(node.response, "json"):
                    try:
                        context[f"_json_{node.edge.name}"] = node.response.json()
                    except Exception:
                        pass
            node = node.parent
        return context

    def get_edge_results(self) -> list[EdgeResult]:
        """Reconstruct EdgeResult list by walking parent pointers.

        Returns:
            List of EdgeResult objects for each edge in the path.

        Complexity: O(depth)
        """
        results: list[EdgeResult] = []
        node: ExplorationNode | None = self
        while node is not None:
            if node.edge is not None:
                results.append(EdgeResult(
                    edge=node.edge,
                    success=node.error is None,
                    response=node.response,
                    duration_ms=node.duration_ms,
                    error=node.error,
                    invariant_violations=node.invariant_violations,
                ))
            node = node.parent
        results.reverse()
        return results

    def to_path_result(self) -> PathResult:
        """Convert this exploration node to a PathResult.

        Reconstructs path, edges, and results by walking parent pointers.
        Used when streaming results or building final ExplorationResult.

        Returns:
            PathResult with full path information.
        """
        # Collect all violations along the path
        all_violations: list[InvariantViolation] = []
        node: ExplorationNode | None = self
        while node is not None:
            all_violations.extend(node.invariant_violations)
            node = node.parent
        all_violations.reverse()

        return PathResult(
            path=self.get_path(),
            edges_taken=self.get_edges(),
            edge_results=self.get_edge_results(),
            success=self.error is None and len(all_violations) == 0,
            invariant_violations=all_violations,
        )


@dataclass
class ExplorationResult:
    """Complete result of exploring the state graph."""
    graph_name: str
    started_at: datetime
    finished_at: datetime
    paths_explored: list[PathResult]
    nodes_visited: set[str]
    edges_executed: set[str]
    invariant_violations: list[InvariantViolation]

    @property
    def success(self) -> bool:
        return len(self.invariant_violations) == 0

    @property
    def total_paths(self) -> int:
        return len(self.paths_explored)

    @property
    def successful_paths(self) -> int:
        return sum(1 for p in self.paths_explored if p.success)

    @property
    def failed_paths(self) -> int:
        return sum(1 for p in self.paths_explored if not p.success)

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"State Graph Exploration: {self.graph_name}",
            "=" * 50,
            f"Duration: {(self.finished_at - self.started_at).total_seconds():.2f}s",
            f"Nodes visited: {len(self.nodes_visited)}",
            f"Edges executed: {len(self.edges_executed)}",
            f"Paths explored: {self.total_paths}",
            f"  - Successful: {self.successful_paths}",
            f"  - Failed: {self.failed_paths}",
            "",
        ]

        if self.invariant_violations:
            lines.append(f"INVARIANT VIOLATIONS ({len(self.invariant_violations)}):")
            lines.append("-" * 40)
            for v in self.invariant_violations:
                lines.append(f"  [{v.invariant.severity.value.upper()}] {v.invariant.name}")
                lines.append(f"    At node: {v.node.id}")
                if v.edge:
                    lines.append(f"    After edge: {v.edge.name}")
                lines.append(f"    {v.invariant.description}")
                if v.error_message:
                    lines.append(f"    Error: {v.error_message}")
                lines.append("")
        else:
            lines.append("ALL INVARIANTS PASSED")

        return "\n".join(lines)

    def broken_nodes(self) -> list[str]:
        """Get list of node IDs where invariants failed."""
        return list(set(v.node.id for v in self.invariant_violations))

    def broken_edges(self) -> list[str]:
        """Get list of edge names that caused invariant failures."""
        return list(set(v.edge.name for v in self.invariant_violations if v.edge))


class StateGraph:
    """Model your application as a state graph for comprehensive testing.

    A StateGraph consists of:
    - Nodes: Application states (e.g., "empty", "has_data", "error_state")
    - Edges: Actions that transition between states
    - Invariants: Rules that must hold true at every state

    The explorer will traverse all reachable paths and verify invariants
    after each transition.
    """

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.nodes: dict[str, StateNode] = {}
        self.edges: dict[str, list[Edge]] = defaultdict(list)  # from_node -> [edges]
        self.invariants: list[Invariant] = []
        self._initial_node: str | None = None

    def add_node(
        self,
        node_id: str,
        description: str = "",
        checker: StateChecker | None = None,
        initial: bool = False,
    ) -> StateNode:
        """Add a state node to the graph.

        Args:
            node_id: Unique identifier for this state
            description: Human-readable description
            checker: Function to verify app is in this state
            initial: If True, this is the starting state

        Returns:
            The created StateNode
        """
        node = StateNode(id=node_id, description=description, checker=checker)
        self.nodes[node_id] = node

        if initial:
            self._initial_node = node_id

        return node

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        action: ActionCallable,
        name: str | None = None,
        description: str = "",
    ) -> Edge:
        """Add a transition edge between states.

        Args:
            from_node: Source state ID
            to_node: Target state ID
            action: Callable that performs the transition
            name: Edge name (defaults to from_to)
            description: What this action does

        Returns:
            The created Edge
        """
        if from_node not in self.nodes:
            raise ValueError(f"from_node '{from_node}' not in graph")
        if to_node not in self.nodes:
            raise ValueError(f"to_node '{to_node}' not in graph")

        edge_name = name or f"{from_node}_to_{to_node}"
        edge = Edge(
            from_node=from_node,
            to_node=to_node,
            name=edge_name,
            action=action,
            description=description,
        )
        self.edges[from_node].append(edge)
        return edge

    def add_invariant(
        self,
        name: str,
        check: InvariantChecker,
        description: str = "",
        severity: Severity = Severity.HIGH,
        sql: str | None = None,
    ) -> Invariant:
        """Add an invariant that must hold at every state.

        Args:
            name: Unique identifier
            check: Function returning True if invariant holds
            description: What this invariant verifies
            severity: How critical is a violation
            sql: Optional SQL for database-level checks

        Returns:
            The created Invariant
        """
        invariant = Invariant(
            name=name,
            check=check,
            description=description,
            severity=severity,
            sql=sql,
        )
        self.invariants.append(invariant)
        return invariant

    def set_initial_node(self, node_id: str) -> None:
        """Set the starting state for exploration."""
        if node_id not in self.nodes:
            raise ValueError(f"Node '{node_id}' not in graph")
        self._initial_node = node_id

    def get_edges_from(self, node_id: str) -> list[Edge]:
        """Get all edges leaving a node."""
        return self.edges.get(node_id, [])

    def _check_invariants(
        self,
        client: Any,
        db: Any,
        context: dict[str, Any],
        current_node: StateNode,
        last_edge: Edge | None,
    ) -> list[InvariantViolation]:
        """Check all invariants and return violations."""
        violations = []

        for inv in self.invariants:
            try:
                result = inv.check(client, db, context)
                if not result:
                    violations.append(InvariantViolation(
                        invariant=inv,
                        node=current_node,
                        edge=last_edge,
                        timestamp=datetime.now(),
                        context_snapshot=dict(context),
                    ))
            except Exception as e:
                violations.append(InvariantViolation(
                    invariant=inv,
                    node=current_node,
                    edge=last_edge,
                    timestamp=datetime.now(),
                    context_snapshot=dict(context),
                    error_message=str(e),
                ))

        return violations

    def _execute_edge(
        self,
        edge: Edge,
        client: Any,
        context: dict[str, Any],
    ) -> tuple[Any, float, str | None]:
        """Execute an edge action and return (response, duration_ms, error)."""
        start = time.perf_counter()
        error = None
        response = None

        try:
            response = edge.action(client, context)
        except Exception as e:
            error = str(e)
            logger.error(f"Edge {edge.name} failed: {e}")

        duration_ms = (time.perf_counter() - start) * 1000
        return response, duration_ms, error

    def explore_iter(
        self,
        client: Any,
        db: Any = None,
        max_depth: int = 10,
        stop_on_violation: bool = False,
        reset_state: Callable[[], None] | None = None,
    ) -> Iterator[PathResult]:
        """Explore all paths through the state graph, yielding results as they complete.

        This is the memory-efficient streaming version of explore(). Instead of
        accumulating all results in memory, it yields each PathResult as soon as
        a path completes (reaches a leaf or max depth).

        Uses DFS with explicit stack and parent-pointer tree structure:
        - Memory: O(depth) for stack, O(total_nodes) for exploration tree
        - Paths share structure via parent pointers
        - Context reconstructed on-demand by walking parents

        Args:
            client: HTTP client for making requests.
            db: Database connection for invariant checks.
            max_depth: Maximum path length to explore.
            stop_on_violation: Stop exploration on first invariant violation.
            reset_state: Function to reset app state between paths.

        Yields:
            PathResult for each completed path.

        Example:
            >>> for result in graph.explore_iter(client, db):
            ...     if not result.success:
            ...         print(f"FAIL: {result.path}")
            ...         for v in result.invariant_violations:
            ...             print(f"  - {v.invariant.name}")
        """
        if not self._initial_node:
            raise ValueError("No initial node set. Call set_initial_node() first.")

        # Create root exploration node
        root = ExplorationNode(
            state_id=self._initial_node,
            parent=None,
            edge=None,
            response=None,
            duration_ms=0.0,
            error=None,
            depth=0,
            invariant_violations=[],
        )

        # DFS with explicit stack - O(depth) memory
        stack: list[ExplorationNode] = [root]

        while stack:
            current = stack.pop()
            current_node = self.nodes[current.state_id]

            # Reconstruct context for invariant checking
            # This is O(depth) but only done once per node visit
            context = current.get_context()

            # Check invariants at current node
            violations = self._check_invariants(
                client, db, context, current_node,
                current.edge
            )

            if violations:
                current.invariant_violations = violations
                if stop_on_violation:
                    yield current.to_path_result()
                    continue

            # Get outgoing edges
            outgoing = self.get_edges_from(current.state_id)

            # Check if this is a leaf (end of path)
            if not outgoing or current.depth >= max_depth:
                yield current.to_path_result()
                continue

            # Explore each outgoing edge - push children to stack
            for edge in outgoing:
                # Reset state if provided (for clean exploration at root)
                if reset_state and current.depth == 0:
                    try:
                        reset_state()
                    except Exception as e:
                        logger.warning(f"Reset state failed: {e}")

                # Execute the edge action
                response, duration_ms, error = self._execute_edge(edge, client, context)

                # Create child node with parent pointer (O(1) - no copying!)
                child = ExplorationNode(
                    state_id=edge.to_node,
                    parent=current,
                    edge=edge,
                    response=response,
                    duration_ms=duration_ms,
                    error=error,
                    depth=current.depth + 1,
                    invariant_violations=[],
                )

                if error:
                    # Edge failed - this path ends here
                    yield child.to_path_result()
                else:
                    # Continue exploration from this child
                    stack.append(child)

    def explore(
        self,
        client: Any,
        db: Any = None,
        max_depth: int = 10,
        stop_on_violation: bool = False,
        reset_state: Callable[[], None] | None = None,
    ) -> ExplorationResult:
        """Explore all paths through the state graph.

        This method uses DFS with parent-pointer trees internally for memory
        efficiency, then accumulates results into an ExplorationResult.

        For very large state spaces where memory is a concern, use explore_iter()
        to stream results without accumulation.

        Args:
            client: HTTP client for making requests.
            db: Database connection for invariant checks.
            max_depth: Maximum path length to explore.
            stop_on_violation: Stop exploration on first invariant violation.
            reset_state: Function to reset app state between paths.

        Returns:
            ExplorationResult with all findings.
        """
        started_at = datetime.now()
        all_paths: list[PathResult] = []
        all_violations: list[InvariantViolation] = []
        nodes_visited: set[str] = set()
        edges_executed: set[str] = set()

        # Use the streaming iterator internally
        for path_result in self.explore_iter(
            client=client,
            db=db,
            max_depth=max_depth,
            stop_on_violation=stop_on_violation,
            reset_state=reset_state,
        ):
            all_paths.append(path_result)
            all_violations.extend(path_result.invariant_violations)

            # Track visited nodes and executed edges
            for node_id in path_result.path:
                nodes_visited.add(node_id)
            for edge in path_result.edges_taken:
                edges_executed.add(edge.name)

        finished_at = datetime.now()

        return ExplorationResult(
            graph_name=self.name,
            started_at=started_at,
            finished_at=finished_at,
            paths_explored=all_paths,
            nodes_visited=nodes_visited,
            edges_executed=edges_executed,
            invariant_violations=all_violations,
        )

    def to_mermaid(self) -> str:
        """Generate Mermaid diagram of the state graph."""
        lines = ["stateDiagram-v2"]

        for node_id, node in self.nodes.items():
            if node.description:
                lines.append(f"    {node_id}: {node.description}")

        if self._initial_node:
            lines.append(f"    [*] --> {self._initial_node}")

        for from_node, edges in self.edges.items():
            for edge in edges:
                lines.append(f"    {from_node} --> {edge.to_node}: {edge.name}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"StateGraph(name='{self.name}', "
            f"nodes={len(self.nodes)}, "
            f"edges={sum(len(e) for e in self.edges.values())}, "
            f"invariants={len(self.invariants)})"
        )
