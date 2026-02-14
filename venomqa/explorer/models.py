"""
Data models for the VenomQA State Explorer module.

This module defines all the core data structures used throughout the
state exploration system, including states, transitions, actions,
the state graph, issues, and coverage reports.

All models use Pydantic for validation and serialization.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Type alias for state identifiers
StateID = str


class IssueSeverity(str, Enum):
    """Severity levels for discovered issues."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Action(BaseModel):
    """
    Represents an API action that can be performed.

    An action encapsulates an HTTP request that can trigger state transitions
    in the application under test.

    Attributes:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH, etc.)
        endpoint: The API endpoint path (e.g., "/api/users/{id}")
        params: Query parameters for the request
        body: Request body payload
        headers: Additional headers for the request
        description: Human-readable description of the action
        requires_auth: Whether this action requires authentication
    """

    method: str = Field(..., description="HTTP method")
    endpoint: str = Field(..., description="API endpoint path")
    params: Optional[Dict[str, Any]] = Field(
        default=None, description="Query parameters"
    )
    body: Optional[Dict[str, Any]] = Field(default=None, description="Request body")
    headers: Optional[Dict[str, str]] = Field(
        default=None, description="Additional headers"
    )
    description: Optional[str] = Field(
        default=None, description="Human-readable description"
    )
    requires_auth: bool = Field(default=False, description="Requires authentication")

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        """Ensure HTTP method is uppercase."""
        return v.upper()

    def __hash__(self) -> int:
        """Allow Action to be used in sets and as dict keys."""
        return hash((self.method, self.endpoint, str(self.params), str(self.body)))

    def __eq__(self, other: object) -> bool:
        """Check equality based on method, endpoint, params, and body."""
        if not isinstance(other, Action):
            return False
        return (
            self.method == other.method
            and self.endpoint == other.endpoint
            and self.params == other.params
            and self.body == other.body
        )


class State(BaseModel):
    """
    Represents an application state.

    A state captures a snapshot of the application at a particular point,
    including any relevant properties and available actions that can be
    performed from this state.

    Attributes:
        id: Unique identifier for this state
        name: Human-readable name for the state
        properties: Key-value properties that characterize this state
        available_actions: List of actions that can be performed from this state
        metadata: Additional metadata about the state
        discovered_at: Timestamp when this state was first discovered
    """

    id: StateID = Field(..., description="Unique state identifier")
    name: str = Field(..., description="Human-readable state name")
    properties: Dict[str, Any] = Field(
        default_factory=dict, description="State properties"
    )
    available_actions: List[Action] = Field(
        default_factory=list, description="Available actions from this state"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    discovered_at: Optional[datetime] = Field(
        default=None, description="Discovery timestamp"
    )

    def __hash__(self) -> int:
        """Allow State to be used in sets and as dict keys."""
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        """Check equality based on state ID."""
        if not isinstance(other, State):
            return False
        return self.id == other.id


class Transition(BaseModel):
    """
    Represents a state transition.

    A transition captures the movement from one state to another
    as a result of performing an action.

    Attributes:
        from_state: The source state ID
        action: The action that triggered the transition
        to_state: The destination state ID
        response: The API response data from the transition
        status_code: HTTP status code of the response
        duration_ms: Time taken for the transition in milliseconds
        success: Whether the transition was successful
        error: Error message if the transition failed
        discovered_at: Timestamp when this transition was discovered
    """

    from_state: StateID = Field(..., description="Source state ID")
    action: Action = Field(..., description="Action that triggered the transition")
    to_state: StateID = Field(..., description="Destination state ID")
    response: Optional[Dict[str, Any]] = Field(
        default=None, description="API response data"
    )
    status_code: Optional[int] = Field(default=None, description="HTTP status code")
    duration_ms: Optional[float] = Field(
        default=None, description="Transition duration in milliseconds"
    )
    success: bool = Field(default=True, description="Whether transition succeeded")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    discovered_at: Optional[datetime] = Field(
        default=None, description="Discovery timestamp"
    )

    def __hash__(self) -> int:
        """Allow Transition to be used in sets and as dict keys."""
        return hash((self.from_state, hash(self.action), self.to_state))

    def __eq__(self, other: object) -> bool:
        """Check equality based on from_state, action, and to_state."""
        if not isinstance(other, Transition):
            return False
        return (
            self.from_state == other.from_state
            and self.action == other.action
            and self.to_state == other.to_state
        )


class StateGraph(BaseModel):
    """
    Graph representation of discovered states and transitions.

    This class provides a complete graph structure for the explored
    state space, with methods for manipulation and querying.

    Attributes:
        states: Dictionary mapping state IDs to State objects
        transitions: List of all discovered transitions
        initial_state: ID of the initial/starting state
        metadata: Additional graph metadata
    """

    states: Dict[StateID, State] = Field(
        default_factory=dict, description="Map of state IDs to states"
    )
    transitions: List[Transition] = Field(
        default_factory=list, description="All transitions"
    )
    initial_state: Optional[StateID] = Field(
        default=None, description="Initial state ID"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Graph metadata"
    )
    # Internal adjacency list for efficient graph operations
    _adjacency: Dict[StateID, List[StateID]] = {}

    def model_post_init(self, __context: Any) -> None:
        """Initialize the adjacency list after model creation."""
        self._rebuild_adjacency()

    def _rebuild_adjacency(self) -> None:
        """Rebuild the adjacency list from transitions."""
        self._adjacency = {}
        for state_id in self.states:
            self._adjacency[state_id] = []
        for transition in self.transitions:
            if transition.from_state not in self._adjacency:
                self._adjacency[transition.from_state] = []
            if transition.to_state not in self._adjacency[transition.from_state]:
                self._adjacency[transition.from_state].append(transition.to_state)

    def add_state(self, state: State) -> None:
        """
        Add a state to the graph.

        Args:
            state: The state to add

        Note:
            If a state with the same ID already exists, it will be updated.
        """
        self.states[state.id] = state
        if state.id not in self._adjacency:
            self._adjacency[state.id] = []
        if self.initial_state is None:
            self.initial_state = state.id

    def add_transition(self, transition: Transition) -> None:
        """
        Add a transition to the graph.

        Args:
            transition: The transition to add

        Note:
            This will also add any states referenced by the transition
            if they don't already exist (as minimal placeholder states).
        """
        # Ensure referenced states exist
        if transition.from_state not in self.states:
            self.states[transition.from_state] = State(
                id=transition.from_state,
                name=f"State_{transition.from_state}",
            )
            self._adjacency[transition.from_state] = []
        if transition.to_state not in self.states:
            self.states[transition.to_state] = State(
                id=transition.to_state,
                name=f"State_{transition.to_state}",
            )
            self._adjacency[transition.to_state] = []

        # Avoid duplicate transitions
        if transition not in self.transitions:
            self.transitions.append(transition)
            # Update adjacency list
            if transition.to_state not in self._adjacency[transition.from_state]:
                self._adjacency[transition.from_state].append(transition.to_state)

    def get_neighbors(self, state_id: StateID) -> List[StateID]:
        """
        Get all states reachable from the given state.

        Args:
            state_id: The source state ID

        Returns:
            List of state IDs that can be reached from the given state
        """
        return list(self._adjacency.get(state_id, []))

    def get_transitions_from(self, state_id: StateID) -> List[Transition]:
        """
        Get all transitions originating from the given state.

        Args:
            state_id: The source state ID

        Returns:
            List of transitions from the given state
        """
        return [t for t in self.transitions if t.from_state == state_id]

    def get_transitions_to(self, state_id: StateID) -> List[Transition]:
        """
        Get all transitions leading to the given state.

        Args:
            state_id: The destination state ID

        Returns:
            List of transitions to the given state
        """
        return [t for t in self.transitions if t.to_state == state_id]

    def get_state(self, state_id: StateID) -> Optional[State]:
        """
        Get a state by its ID.

        Args:
            state_id: The state ID to look up

        Returns:
            The State object if found, None otherwise
        """
        return self.states.get(state_id)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the graph to a dictionary representation.

        Returns:
            Dictionary containing all states and transitions
        """
        return {
            "states": {
                state_id: state.model_dump() for state_id, state in self.states.items()
            },
            "transitions": [t.model_dump() for t in self.transitions],
            "initial_state": self.initial_state,
            "metadata": self.metadata,
            "stats": {
                "total_states": len(self.states),
                "total_transitions": len(self.transitions),
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateGraph":
        """
        Create a StateGraph from a dictionary representation.

        Args:
            data: Dictionary containing states, transitions, initial_state, and metadata

        Returns:
            A new StateGraph instance
        """
        graph = cls(
            initial_state=data.get("initial_state"),
            metadata=data.get("metadata", {}),
        )

        # Restore states
        states_data = data.get("states", {})
        for state_id, state_dict in states_data.items():
            state = State(**state_dict)
            graph.add_state(state)

        # Restore transitions
        transitions_data = data.get("transitions", [])
        for transition_dict in transitions_data:
            transition = Transition(**transition_dict)
            graph.add_transition(transition)

        return graph

    def get_all_actions(self) -> Set[Action]:
        """
        Get all unique actions in the graph.

        Returns:
            Set of all unique actions
        """
        actions: Set[Action] = set()
        for transition in self.transitions:
            actions.add(transition.action)
        return actions

    def has_path(self, from_state: StateID, to_state: StateID) -> bool:
        """
        Check if there is a path between two states using BFS.

        Args:
            from_state: Source state ID
            to_state: Destination state ID

        Returns:
            True if a path exists, False otherwise
        """
        if from_state == to_state:
            return True

        if from_state not in self.states:
            return False

        visited: Set[StateID] = set()
        queue: List[StateID] = [from_state]

        while queue:
            current = queue.pop(0)
            if current == to_state:
                return True
            if current in visited:
                continue
            visited.add(current)
            queue.extend(self.get_neighbors(current))

        return False

    def find_cycles(self) -> List[List[StateID]]:
        """
        Find all cycles in the graph using Tarjan's algorithm.

        This implementation uses Tarjan's strongly connected components (SCC)
        algorithm to find all cycles. Each SCC with more than one node or
        a self-loop represents a cycle.

        Returns:
            List of cycles, where each cycle is a list of state IDs
        """
        # Tarjan's algorithm data structures
        index_counter = [0]
        stack: List[StateID] = []
        lowlinks: Dict[StateID, int] = {}
        index: Dict[StateID, int] = {}
        on_stack: Dict[StateID, bool] = {}
        sccs: List[List[StateID]] = []

        def strongconnect(node: StateID) -> None:
            # Set the depth index for node
            index[node] = index_counter[0]
            lowlinks[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack[node] = True

            # Consider successors
            for successor in self.get_neighbors(node):
                if successor not in index:
                    # Successor has not yet been visited; recurse on it
                    strongconnect(successor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[successor])
                elif on_stack.get(successor, False):
                    # Successor is on stack and hence in the current SCC
                    lowlinks[node] = min(lowlinks[node], index[successor])

            # If node is a root node, pop the stack and generate an SCC
            if lowlinks[node] == index[node]:
                scc: List[StateID] = []
                while True:
                    successor = stack.pop()
                    on_stack[successor] = False
                    scc.append(successor)
                    if successor == node:
                        break
                # Only report SCCs that form cycles (size > 1 or self-loop)
                if len(scc) > 1:
                    sccs.append(scc)
                elif len(scc) == 1:
                    # Check for self-loop
                    if scc[0] in self.get_neighbors(scc[0]):
                        sccs.append(scc)

        # Run algorithm for all unvisited nodes
        for state_id in self.states:
            if state_id not in index:
                strongconnect(state_id)

        return sccs

    def find_dead_ends(self) -> List[StateID]:
        """
        Find all states with no outgoing transitions (dead ends).

        A dead end is a state from which no other state can be reached,
        meaning it has no outgoing transitions.

        Returns:
            List of state IDs that are dead ends
        """
        dead_ends: List[StateID] = []
        for state_id in self.states:
            neighbors = self.get_neighbors(state_id)
            if len(neighbors) == 0:
                dead_ends.append(state_id)
        return dead_ends

    def find_unreachable_states(self) -> List[StateID]:
        """
        Find all states that are not reachable from the initial state.

        Returns:
            List of state IDs that cannot be reached from the initial state
        """
        if self.initial_state is None:
            return list(self.states.keys())

        # BFS from initial state to find all reachable states
        visited: Set[StateID] = set()
        queue: List[StateID] = [self.initial_state]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            queue.extend(self.get_neighbors(current))

        # Return states not in visited set
        unreachable = [s for s in self.states if s not in visited]
        return unreachable

    def get_shortest_path(
        self, from_state: StateID, to_state: StateID
    ) -> Optional[List[StateID]]:
        """
        Find the shortest path between two states using BFS.

        Args:
            from_state: Source state ID
            to_state: Destination state ID

        Returns:
            List of state IDs representing the path, or None if no path exists
        """
        if from_state == to_state:
            return [from_state]

        if from_state not in self.states:
            return None

        visited: Set[StateID] = set()
        queue: List[List[StateID]] = [[from_state]]

        while queue:
            path = queue.pop(0)
            current = path[-1]

            if current in visited:
                continue
            visited.add(current)

            for neighbor in self.get_neighbors(current):
                new_path = path + [neighbor]
                if neighbor == to_state:
                    return new_path
                queue.append(new_path)

        return None


class Issue(BaseModel):
    """
    Represents an issue discovered during exploration.

    Issues capture potential problems, bugs, or anomalies found
    during state exploration.

    Attributes:
        severity: The severity level of the issue
        state: The state where the issue was discovered
        action: The action that triggered the issue (if applicable)
        error: Error message or description
        suggestion: Suggested fix or investigation
        category: Category of the issue (e.g., "validation", "auth", "performance")
        response_data: Relevant response data for debugging
        discovered_at: Timestamp when the issue was discovered
    """

    severity: IssueSeverity = Field(..., description="Issue severity level")
    state: Optional[StateID] = Field(
        default=None, description="State where issue was found"
    )
    action: Optional[Action] = Field(
        default=None, description="Action that triggered the issue"
    )
    error: str = Field(..., description="Error description")
    suggestion: Optional[str] = Field(
        default=None, description="Suggested fix or investigation"
    )
    category: Optional[str] = Field(default=None, description="Issue category")
    response_data: Optional[Dict[str, Any]] = Field(
        default=None, description="Relevant response data"
    )
    discovered_at: Optional[datetime] = Field(
        default=None, description="Discovery timestamp"
    )


class CoverageReport(BaseModel):
    """
    Report on exploration coverage.

    This captures metrics about how much of the application's
    state space has been explored.

    Attributes:
        states_found: Total number of unique states discovered
        transitions_found: Total number of unique transitions discovered
        endpoints_discovered: Total number of API endpoints discovered
        endpoints_tested: Number of endpoints that were actually tested
        coverage_percent: Overall coverage percentage (0-100)
        uncovered_actions: Actions that were discovered but not executed
        state_breakdown: Breakdown of states by type/category
        transition_breakdown: Breakdown of transitions by outcome
    """

    states_found: int = Field(default=0, description="Number of states discovered")
    transitions_found: int = Field(
        default=0, description="Number of transitions discovered"
    )
    endpoints_discovered: int = Field(
        default=0, description="Number of endpoints discovered"
    )
    endpoints_tested: int = Field(
        default=0, description="Number of endpoints tested"
    )
    coverage_percent: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Coverage percentage"
    )
    uncovered_actions: List[Action] = Field(
        default_factory=list, description="Actions not executed"
    )
    state_breakdown: Dict[str, int] = Field(
        default_factory=dict, description="States by category"
    )
    transition_breakdown: Dict[str, int] = Field(
        default_factory=dict, description="Transitions by outcome"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return self.model_dump()


class ChainState(BaseModel):
    """
    State in the exploration chain with context tracking.

    This is the core state model for context-aware state exploration.
    It tracks accumulated context (IDs, tokens) through the exploration chain,
    allowing proper substitution of path parameters in subsequent requests.

    Attributes:
        id: Unique identifier for this state
        name: Human-readable name based on context
        context: Accumulated IDs, tokens, and other extracted data
        response: Response data that led to this state
        available_actions: Actions that can be performed from this state
        depth: How deep in the exploration chain (0 = initial)
        parent_state: ID of the state this was reached from
        parent_action: The action that led to this state
        metadata: Additional metadata about the state
        discovered_at: Timestamp when this state was first discovered
    """

    id: StateID = Field(..., description="Unique state identifier")
    name: str = Field(..., description="Human-readable state name based on context")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Accumulated context (IDs, tokens, etc.)"
    )
    response: Optional[Dict[str, Any]] = Field(
        default=None, description="Response that led to this state"
    )
    available_actions: List[Action] = Field(
        default_factory=list, description="Available actions from this state"
    )
    depth: int = Field(default=0, ge=0, description="Depth in exploration chain")
    parent_state: Optional[StateID] = Field(
        default=None, description="Parent state ID"
    )
    parent_action: Optional[Action] = Field(
        default=None, description="Action that led to this state"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    discovered_at: Optional[datetime] = Field(
        default=None, description="Discovery timestamp"
    )

    def __hash__(self) -> int:
        """Allow ChainState to be used in sets and as dict keys."""
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        """Check equality based on state ID."""
        if not isinstance(other, ChainState):
            return False
        return self.id == other.id

    def to_state(self) -> "State":
        """Convert to basic State for compatibility."""
        return State(
            id=self.id,
            name=self.name,
            properties={"context": self.context, "depth": self.depth},
            available_actions=self.available_actions,
            metadata=self.metadata,
            discovered_at=self.discovered_at,
        )

    @classmethod
    def from_state(
        cls,
        state: "State",
        context: Optional[Dict[str, Any]] = None,
        depth: int = 0,
        parent_state: Optional[StateID] = None,
        parent_action: Optional[Action] = None,
    ) -> "ChainState":
        """Create a ChainState from a basic State."""
        return cls(
            id=state.id,
            name=state.name,
            context=context or {},
            response=state.properties,
            available_actions=state.available_actions,
            depth=depth,
            parent_state=parent_state,
            parent_action=parent_action,
            metadata=state.metadata,
            discovered_at=state.discovered_at,
        )


class ExplorationConfig(BaseModel):
    """
    Configuration for state exploration.

    Attributes:
        max_depth: Maximum exploration depth
        max_states: Maximum number of states to explore
        max_transitions: Maximum number of transitions to explore
        timeout_seconds: Overall exploration timeout
        request_timeout_seconds: Timeout for individual requests
        include_patterns: Endpoint patterns to include
        exclude_patterns: Endpoint patterns to exclude
        auth_token: Authentication token if required
        headers: Additional headers for all requests
        follow_redirects: Whether to follow HTTP redirects
        verify_ssl: Whether to verify SSL certificates
    """

    max_depth: int = Field(default=10, ge=1, description="Maximum exploration depth")
    max_states: int = Field(
        default=100, ge=1, description="Maximum states to explore"
    )
    max_transitions: int = Field(
        default=500, ge=1, description="Maximum transitions to explore"
    )
    timeout_seconds: int = Field(
        default=300, ge=1, description="Overall timeout in seconds"
    )
    request_timeout_seconds: int = Field(
        default=30, ge=1, description="Per-request timeout in seconds"
    )
    include_patterns: List[str] = Field(
        default_factory=list, description="Endpoint patterns to include"
    )
    exclude_patterns: List[str] = Field(
        default_factory=list, description="Endpoint patterns to exclude"
    )
    auth_token: Optional[str] = Field(
        default=None, description="Authentication token"
    )
    headers: Dict[str, str] = Field(
        default_factory=dict, description="Additional headers"
    )
    follow_redirects: bool = Field(
        default=True, description="Follow HTTP redirects"
    )
    verify_ssl: bool = Field(default=True, description="Verify SSL certificates")


class ExplorationResult(BaseModel):
    """
    Complete result of a state exploration run.

    This is the main output of the StateExplorer, containing
    the full graph, any discovered issues, coverage metrics,
    and timing information.

    Attributes:
        graph: The complete state graph
        issues: List of discovered issues
        coverage: Coverage report
        duration: Total exploration duration
        started_at: Exploration start timestamp
        finished_at: Exploration end timestamp
        config: Configuration used for exploration
        error: Error message if exploration failed
        success: Whether exploration completed successfully
    """

    graph: StateGraph = Field(..., description="The explored state graph")
    issues: List[Issue] = Field(default_factory=list, description="Discovered issues")
    coverage: CoverageReport = Field(..., description="Coverage report")
    duration: timedelta = Field(..., description="Total exploration duration")
    started_at: datetime = Field(..., description="Start timestamp")
    finished_at: datetime = Field(..., description="End timestamp")
    config: Optional[ExplorationConfig] = Field(
        default=None, description="Exploration configuration"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if failed"
    )
    success: bool = Field(default=True, description="Whether exploration succeeded")

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "graph": self.graph.to_dict(),
            "issues": [issue.model_dump() for issue in self.issues],
            "coverage": self.coverage.to_dict(),
            "duration_seconds": self.duration.total_seconds(),
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "config": self.config.model_dump() if self.config else None,
            "error": self.error,
            "success": self.success,
        }

    def get_critical_issues(self) -> List[Issue]:
        """Get all critical severity issues."""
        return [i for i in self.issues if i.severity == IssueSeverity.CRITICAL]

    def get_issues_by_severity(self, severity: IssueSeverity) -> List[Issue]:
        """Get issues filtered by severity."""
        return [i for i in self.issues if i.severity == severity]
