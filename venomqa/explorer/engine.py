"""
Exploration Engine for the VenomQA State Explorer module.

This module provides the ExplorationEngine class which implements the core
exploration algorithms. It supports multiple exploration strategies including
Breadth-First Search (BFS), Depth-First Search (DFS), and random walk.

The engine manages the exploration process, tracking visited states and
transitions, and handling the execution of actions.
"""

from __future__ import annotations

import logging
import random
import time
from collections import deque
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Set, Tuple

import httpx

from venomqa.explorer.models import (
    Action,
    CoverageReport,
    ExplorationConfig,
    Issue,
    IssueSeverity,
    State,
    StateGraph,
    StateID,
    Transition,
)

logger = logging.getLogger(__name__)


class ExplorationStrategy(str, Enum):
    """Supported exploration strategies."""

    BFS = "bfs"  # Breadth-First Search - explores level by level
    DFS = "dfs"  # Depth-First Search - explores deeply first
    RANDOM = "random"  # Random walk - randomly selects next action
    GREEDY = "greedy"  # Greedy - prioritizes unexplored actions
    HYBRID = "hybrid"  # Hybrid - combines multiple strategies


class ExplorationError(Exception):
    """Exception raised when exploration fails."""

    pass


class ExplorationEngine:
    """
    Core exploration engine implementing state space traversal.

    The ExplorationEngine is responsible for systematically exploring
    the application's state space by executing actions and tracking
    the resulting state transitions.

    Features:
    - Multiple exploration strategies (BFS, DFS, Random, Greedy, Hybrid)
    - Configurable depth and breadth limits
    - Action execution with error handling
    - Automatic state detection and graph building
    - Issue detection during exploration
    - Cycle detection to avoid infinite loops

    Attributes:
        config: Exploration configuration
        strategy: Current exploration strategy
        graph: The state graph being built
        issues: List of discovered issues
        visited_states: Set of visited state IDs
        visited_transitions: Set of explored transitions
        action_executor: Function to execute actions
        state_detector: Function to detect state from responses

    Example:
        engine = ExplorationEngine(strategy=ExplorationStrategy.BFS)
        engine.set_action_executor(http_client.execute)
        engine.set_state_detector(detector.detect_state)
        await engine.explore(initial_state)
    """

    def __init__(
        self,
        config: Optional[ExplorationConfig] = None,
        strategy: ExplorationStrategy = ExplorationStrategy.BFS,
        base_url: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        """
        Initialize the exploration engine.

        Args:
            config: Exploration configuration
            strategy: Exploration strategy to use
            base_url: Base URL for HTTP requests (used if no action executor set)
            http_client: Optional httpx AsyncClient for HTTP requests
        """
        self.config = config or ExplorationConfig()
        self.strategy = strategy
        self.base_url = base_url or ""
        self._http_client = http_client
        self._owns_client = False
        self.graph = StateGraph()
        self.issues: List[Issue] = []
        self.visited_states: Set[StateID] = set()
        self.visited_transitions: Set[Tuple[StateID, str, str]] = set()
        self._action_executor: Optional[Callable[[Action], Any]] = None
        self._state_detector: Optional[
            Callable[[Dict[str, Any], Optional[str], Optional[str]], State]
        ] = None
        self._exploration_queue: Deque[Tuple[State, int]] = deque()
        self._exploration_stack: List[Tuple[State, int]] = []
        self._current_depth = 0
        self._all_discovered_actions: Set[Action] = set()
        self._executed_actions: Set[Action] = set()

    def set_action_executor(
        self,
        executor: Callable[[Action], Any],
    ) -> None:
        """
        Set the function used to execute actions.

        Args:
            executor: Async function that takes an Action and returns response data
        """
        self._action_executor = executor

    def set_state_detector(
        self,
        detector: Callable[[Dict[str, Any], Optional[str], Optional[str]], State],
    ) -> None:
        """
        Set the function used to detect state from responses.

        Args:
            detector: Function that takes response data and returns a State
        """
        self._state_detector = detector

    async def _ensure_http_client(self) -> httpx.AsyncClient:
        """Ensure we have an HTTP client available."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.config.request_timeout_seconds,
                follow_redirects=self.config.follow_redirects,
                verify=self.config.verify_ssl,
                headers=self.config.headers,
            )
            self._owns_client = True
        return self._http_client

    async def _close_http_client(self) -> None:
        """Close the HTTP client if we own it."""
        if self._owns_client and self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
            self._owns_client = False

    async def explore(
        self,
        initial_state: State,
        initial_actions: Optional[List[Action]] = None,
    ) -> StateGraph:
        """
        Start exploration from an initial state.

        Args:
            initial_state: The starting state for exploration
            initial_actions: Optional list of initial actions to try

        Returns:
            The completed StateGraph

        Raises:
            ExplorationError: If exploration fails
            ValueError: If required components are not configured
        """
        # Add initial state to graph
        self.graph.add_state(initial_state)
        self.visited_states.add(initial_state.id)

        # Track all discovered actions
        for action in initial_state.available_actions:
            self._all_discovered_actions.add(action)

        # Add any additional initial actions
        if initial_actions:
            for action in initial_actions:
                if action not in initial_state.available_actions:
                    initial_state.available_actions.append(action)
                    self._all_discovered_actions.add(action)

        try:
            # Execute exploration based on strategy
            if self.strategy == ExplorationStrategy.BFS:
                await self._explore_bfs(initial_state)
            elif self.strategy == ExplorationStrategy.DFS:
                await self._explore_dfs(initial_state)
            elif self.strategy == ExplorationStrategy.RANDOM:
                await self._explore_random(initial_state)
            elif self.strategy == ExplorationStrategy.GREEDY:
                await self._explore_greedy(initial_state)
            elif self.strategy == ExplorationStrategy.HYBRID:
                await self._explore_hybrid(initial_state)
            else:
                # Default to BFS
                await self._explore_bfs(initial_state)
        finally:
            await self._close_http_client()

        return self.graph

    async def explore_from_state(
        self,
        state: State,
        depth: int = 0,
    ) -> List[Tuple[State, Transition]]:
        """
        Explore from a specific state.

        Args:
            state: The state to explore from
            depth: Current exploration depth

        Returns:
            List of (new_state, transition) tuples discovered
        """
        discovered: List[Tuple[State, Transition]] = []

        # Check depth limits
        if depth >= self.config.max_depth:
            logger.debug(f"Max depth {self.config.max_depth} reached at state {state.id}")
            return discovered

        # Check other limits
        if not self._check_limits():
            logger.debug("Exploration limits reached")
            return discovered

        self._current_depth = max(self._current_depth, depth)

        # Get available actions from the state
        available_actions = state.available_actions

        for action in available_actions:
            # Check if we should skip this action based on patterns
            if not self._should_explore_action(action):
                continue

            # Check if this action from this state has been executed
            action_key = (state.id, f"{action.method}:{action.endpoint}")
            if action_key in [(t[0], t[1]) for t in self.visited_transitions]:
                # We've already tried this action from this state
                continue

            # Execute the action
            result_state, transition = await self.execute_action(action, state)

            if result_state and transition:
                discovered.append((result_state, transition))

                # Mark transition as visited
                self._mark_transition_visited(state.id, action, result_state.id)
                self._executed_actions.add(action)

                # Track new actions from the result state
                for new_action in result_state.available_actions:
                    self._all_discovered_actions.add(new_action)

            # Check limits after each action
            if not self._check_limits():
                break

        return discovered

    async def execute_action(
        self,
        action: Action,
        from_state: State,
    ) -> Tuple[Optional[State], Optional[Transition]]:
        """
        Execute an action and detect the resulting state.

        Args:
            action: The action to execute
            from_state: The current state before action

        Returns:
            Tuple of (resulting state, transition) or (None, None) on failure
        """
        start_time = time.time()
        response_data: Dict[str, Any] = {}
        status_code: Optional[int] = None
        error_msg: Optional[str] = None
        success = True

        try:
            # Use custom action executor if provided
            if self._action_executor:
                response = await self._action_executor(action)
                if isinstance(response, dict):
                    response_data = response
                    status_code = response.get("status_code")
                else:
                    # Try to extract data from response object
                    if hasattr(response, "json"):
                        try:
                            response_data = response.json()
                        except Exception:
                            response_data = {"raw": str(response)}
                    if hasattr(response, "status_code"):
                        status_code = response.status_code
            else:
                # Use built-in HTTP client
                response_data, status_code = await self._execute_http_action(action)

            # Check for error status codes
            if status_code and status_code >= 400:
                success = False
                error_msg = f"HTTP {status_code}"
                self._record_issue(
                    severity=IssueSeverity.MEDIUM if status_code < 500 else IssueSeverity.HIGH,
                    error=f"Action {action.method} {action.endpoint} returned {status_code}",
                    state=from_state.id,
                    action=action,
                    suggestion="Check if the endpoint requires authentication or different parameters",
                )

        except httpx.TimeoutException as e:
            success = False
            error_msg = f"Timeout: {e}"
            self._record_issue(
                severity=IssueSeverity.MEDIUM,
                error=f"Timeout executing {action.method} {action.endpoint}",
                state=from_state.id,
                action=action,
                suggestion="Consider increasing request timeout",
            )
        except httpx.HTTPStatusError as e:
            success = False
            status_code = e.response.status_code
            error_msg = f"HTTP error: {e}"
            self._record_issue(
                severity=IssueSeverity.HIGH,
                error=str(e),
                state=from_state.id,
                action=action,
            )
        except Exception as e:
            success = False
            error_msg = str(e)
            self._record_issue(
                severity=IssueSeverity.HIGH,
                error=f"Failed to execute {action.method} {action.endpoint}: {e}",
                state=from_state.id,
                action=action,
            )
            logger.exception(f"Error executing action: {action}")

        duration_ms = (time.time() - start_time) * 1000

        # Detect resulting state
        result_state: Optional[State] = None
        if self._state_detector:
            try:
                result_state = self._state_detector(
                    response_data,
                    action.endpoint,
                    str(status_code) if status_code else None,
                )
            except Exception as e:
                logger.warning(f"State detection failed: {e}")

        if result_state is None:
            # Create a default state based on the response
            result_state = self._create_default_state(
                action, from_state, response_data, status_code, success
            )

        # Add state to graph if new
        if result_state.id not in self.visited_states:
            self.graph.add_state(result_state)
            self.visited_states.add(result_state.id)

        # Create transition
        transition = Transition(
            from_state=from_state.id,
            action=action,
            to_state=result_state.id,
            response=response_data,
            status_code=status_code,
            duration_ms=duration_ms,
            success=success,
            error=error_msg,
            discovered_at=datetime.now(),
        )

        # Add transition to graph
        self.graph.add_transition(transition)

        return result_state, transition

    async def _execute_http_action(
        self, action: Action
    ) -> Tuple[Dict[str, Any], int]:
        """
        Execute an HTTP action using the built-in client.

        Args:
            action: The action to execute

        Returns:
            Tuple of (response_data, status_code)
        """
        client = await self._ensure_http_client()

        # Build URL
        url = action.endpoint
        if not url.startswith("http"):
            url = f"{self.base_url.rstrip('/')}/{url.lstrip('/')}"

        # Build headers
        headers = dict(self.config.headers)
        if action.headers:
            headers.update(action.headers)
        if self.config.auth_token:
            headers["Authorization"] = f"Bearer {self.config.auth_token}"

        # Execute request
        response = await client.request(
            method=action.method,
            url=url,
            params=action.params,
            json=action.body,
            headers=headers,
        )

        # Parse response
        try:
            response_data = response.json()
        except Exception:
            response_data = {"raw": response.text}

        return response_data, response.status_code

    def _create_default_state(
        self,
        action: Action,
        from_state: State,
        response_data: Dict[str, Any],
        status_code: Optional[int],
        success: bool,
    ) -> State:
        """
        Create a default state based on response characteristics.

        Args:
            action: The action that was executed
            from_state: The state the action was executed from
            response_data: The response data
            status_code: HTTP status code
            success: Whether the action succeeded

        Returns:
            A new State object
        """
        # Generate state ID based on action and response characteristics
        if not success:
            state_id = f"error_{status_code}_{action.endpoint.replace('/', '_')}"
            state_name = f"Error State ({status_code})"
        else:
            # Try to derive state from response
            state_type = response_data.get("type", response_data.get("state", ""))
            if state_type:
                state_id = f"state_{state_type}"
                state_name = f"State: {state_type}"
            else:
                # Use a hash of relevant response properties
                import hashlib
                content_hash = hashlib.md5(
                    str(sorted(response_data.keys())).encode()
                ).hexdigest()[:8]
                state_id = f"state_{action.endpoint.replace('/', '_')}_{content_hash}"
                state_name = f"State after {action.method} {action.endpoint}"

        # Determine available actions from the response (if any)
        available_actions: List[Action] = []

        # Look for links/actions in the response (HATEOAS pattern)
        links = response_data.get("_links", response_data.get("links", []))
        if isinstance(links, dict):
            for rel, link_data in links.items():
                if isinstance(link_data, dict) and "href" in link_data:
                    available_actions.append(
                        Action(
                            method=link_data.get("method", "GET"),
                            endpoint=link_data["href"],
                            description=rel,
                        )
                    )
                elif isinstance(link_data, str):
                    available_actions.append(
                        Action(
                            method="GET",
                            endpoint=link_data,
                            description=rel,
                        )
                    )
        elif isinstance(links, list):
            for link in links:
                if isinstance(link, dict) and "href" in link:
                    available_actions.append(
                        Action(
                            method=link.get("method", "GET"),
                            endpoint=link["href"],
                            description=link.get("rel", ""),
                        )
                    )

        return State(
            id=state_id,
            name=state_name,
            properties={
                "status_code": status_code,
                "success": success,
                "from_action": f"{action.method} {action.endpoint}",
            },
            available_actions=available_actions,
            metadata={"response_keys": list(response_data.keys())},
            discovered_at=datetime.now(),
        )

    def _should_explore_action(self, action: Action) -> bool:
        """
        Check if an action should be explored based on include/exclude patterns.

        Args:
            action: The action to check

        Returns:
            True if the action should be explored
        """
        endpoint = action.endpoint

        # Check exclude patterns
        for pattern in self.config.exclude_patterns:
            if pattern in endpoint or endpoint.startswith(pattern):
                return False

        # Check include patterns (if any)
        if self.config.include_patterns:
            for pattern in self.config.include_patterns:
                if pattern in endpoint or endpoint.startswith(pattern):
                    return True
            return False

        return True

    async def _explore_bfs(self, initial_state: State) -> None:
        """
        Implement Breadth-First Search exploration.

        BFS explores all states at the current depth before moving deeper.
        This is useful for finding the shortest paths to states.

        Args:
            initial_state: The starting state for exploration
        """
        # Initialize queue with initial state at depth 0
        self._exploration_queue.clear()
        self._exploration_queue.append((initial_state, 0))

        while self._exploration_queue:
            # Check overall limits
            if not self._check_limits():
                logger.info("Exploration limits reached, stopping BFS")
                break

            # Get next state from queue (FIFO for BFS)
            current_state, depth = self._exploration_queue.popleft()

            # Skip if we've exceeded depth
            if depth >= self.config.max_depth:
                continue

            # Explore from current state
            discovered = await self.explore_from_state(current_state, depth)

            # Add newly discovered states to queue
            for new_state, _ in discovered:
                if new_state.id not in self.visited_states:
                    self._exploration_queue.append((new_state, depth + 1))
                elif new_state.available_actions:
                    # Even if visited, might have new actions to explore
                    # Check if there are unexplored actions
                    for action in new_state.available_actions:
                        key = (new_state.id, f"{action.method}:{action.endpoint}")
                        if key not in [(t[0], t[1]) for t in self.visited_transitions]:
                            self._exploration_queue.append((new_state, depth + 1))
                            break

    async def _explore_dfs(self, initial_state: State) -> None:
        """
        Implement Depth-First Search exploration.

        DFS explores as deeply as possible before backtracking.
        This is useful for finding deep state sequences.

        Args:
            initial_state: The starting state for exploration
        """
        # Initialize stack with initial state at depth 0
        self._exploration_stack.clear()
        self._exploration_stack.append((initial_state, 0))

        while self._exploration_stack:
            # Check overall limits
            if not self._check_limits():
                logger.info("Exploration limits reached, stopping DFS")
                break

            # Get next state from stack (LIFO for DFS)
            current_state, depth = self._exploration_stack.pop()

            # Skip if we've exceeded depth
            if depth >= self.config.max_depth:
                continue

            # Explore from current state
            discovered = await self.explore_from_state(current_state, depth)

            # Add newly discovered states to stack (reverse order to maintain left-to-right exploration)
            for new_state, _ in reversed(discovered):
                if new_state.id not in self.visited_states:
                    self._exploration_stack.append((new_state, depth + 1))

    async def _explore_random(self, initial_state: State) -> None:
        """
        Implement random walk exploration.

        Random walk randomly selects actions to execute.
        This can help discover unexpected state paths.

        Args:
            initial_state: The starting state for exploration
        """
        current_state = initial_state
        depth = 0
        max_iterations = self.config.max_states * 2  # Limit iterations

        for _ in range(max_iterations):
            # Check limits
            if not self._check_limits():
                break

            if depth >= self.config.max_depth:
                # Reset to initial state for another random walk
                current_state = initial_state
                depth = 0
                continue

            # Get unexplored actions from current state
            unexplored_actions = []
            for action in current_state.available_actions:
                key = (current_state.id, f"{action.method}:{action.endpoint}")
                if key not in [(t[0], t[1]) for t in self.visited_transitions]:
                    unexplored_actions.append(action)

            if not unexplored_actions:
                # No more unexplored actions, pick a random visited state
                if self.graph.states:
                    random_state_id = random.choice(list(self.graph.states.keys()))
                    current_state = self.graph.states[random_state_id]
                    depth = 0
                else:
                    break
                continue

            # Randomly select an action
            action = random.choice(unexplored_actions)

            # Execute the action
            result_state, transition = await self.execute_action(action, current_state)

            if result_state and transition:
                self._mark_transition_visited(current_state.id, action, result_state.id)
                self._executed_actions.add(action)
                current_state = result_state
                depth += 1
            else:
                # Action failed, try another
                continue

    async def _explore_greedy(self, initial_state: State) -> None:
        """
        Implement greedy exploration.

        Greedy exploration prioritizes unexplored actions and states.
        This maximizes coverage quickly.

        Args:
            initial_state: The starting state for exploration
        """
        # Use a priority-based approach: states with more unexplored actions get priority
        states_to_explore: List[Tuple[int, State, int]] = [
            (-len(initial_state.available_actions), initial_state, 0)
        ]

        while states_to_explore:
            if not self._check_limits():
                break

            # Sort by priority (negative count means more actions = higher priority)
            states_to_explore.sort(key=lambda x: x[0])

            _, current_state, depth = states_to_explore.pop(0)

            if depth >= self.config.max_depth:
                continue

            # Explore from current state
            discovered = await self.explore_from_state(current_state, depth)

            # Add discovered states with their priority
            for new_state, _ in discovered:
                if new_state.id not in self.visited_states:
                    # Count unexplored actions
                    unexplored_count = 0
                    for action in new_state.available_actions:
                        key = (new_state.id, f"{action.method}:{action.endpoint}")
                        if key not in [(t[0], t[1]) for t in self.visited_transitions]:
                            unexplored_count += 1
                    priority = -unexplored_count
                    states_to_explore.append((priority, new_state, depth + 1))

    async def _explore_hybrid(self, initial_state: State) -> None:
        """
        Implement hybrid exploration combining multiple strategies.

        Uses BFS for initial breadth, then switches to greedy for deep exploration.

        Args:
            initial_state: The starting state for exploration
        """
        # First, do shallow BFS exploration (up to depth 2)
        original_max_depth = self.config.max_depth
        self.config.max_depth = min(2, original_max_depth)
        await self._explore_bfs(initial_state)

        # Then, use greedy exploration for the rest
        self.config.max_depth = original_max_depth
        await self._explore_greedy(initial_state)

    def _record_issue(
        self,
        severity: IssueSeverity,
        error: str,
        state: Optional[StateID] = None,
        action: Optional[Action] = None,
        suggestion: Optional[str] = None,
    ) -> None:
        """
        Record an issue discovered during exploration.

        Args:
            severity: Issue severity level
            error: Error description
            state: State where issue occurred
            action: Action that triggered the issue
            suggestion: Suggested fix
        """
        issue = Issue(
            severity=severity,
            state=state,
            action=action,
            error=error,
            suggestion=suggestion,
            discovered_at=datetime.now(),
        )
        self.issues.append(issue)

    def _is_transition_visited(
        self,
        from_state: StateID,
        action: Action,
        to_state: StateID,
    ) -> bool:
        """
        Check if a transition has already been visited.

        Args:
            from_state: Source state ID
            action: The action
            to_state: Destination state ID

        Returns:
            True if transition was already visited
        """
        key = (from_state, f"{action.method}:{action.endpoint}", to_state)
        return key in self.visited_transitions

    def _mark_transition_visited(
        self,
        from_state: StateID,
        action: Action,
        to_state: StateID,
    ) -> None:
        """
        Mark a transition as visited.

        Args:
            from_state: Source state ID
            action: The action
            to_state: Destination state ID
        """
        key = (from_state, f"{action.method}:{action.endpoint}", to_state)
        self.visited_transitions.add(key)

    def _check_limits(self) -> bool:
        """
        Check if exploration limits have been reached.

        Returns:
            True if exploration should continue, False if limits reached
        """
        if len(self.visited_states) >= self.config.max_states:
            return False
        if len(self.visited_transitions) >= self.config.max_transitions:
            return False
        if self._current_depth >= self.config.max_depth:
            return False
        return True

    def get_coverage_report(self) -> CoverageReport:
        """
        Generate a coverage report from exploration results.

        Returns:
            CoverageReport with exploration metrics
        """
        # Calculate unique endpoints
        endpoints_discovered: Set[str] = set()
        endpoints_tested: Set[str] = set()

        for action in self._all_discovered_actions:
            endpoints_discovered.add(action.endpoint)

        for action in self._executed_actions:
            endpoints_tested.add(action.endpoint)

        # Calculate coverage percentage
        if endpoints_discovered:
            coverage_percent = (len(endpoints_tested) / len(endpoints_discovered)) * 100
        else:
            coverage_percent = 0.0

        # Find uncovered actions
        uncovered_actions = [
            action for action in self._all_discovered_actions
            if action not in self._executed_actions
        ]

        # State breakdown
        state_breakdown: Dict[str, int] = {}
        for state in self.graph.states.values():
            state_type = state.properties.get("success", True)
            key = "success" if state_type else "error"
            state_breakdown[key] = state_breakdown.get(key, 0) + 1

        # Transition breakdown
        transition_breakdown: Dict[str, int] = {}
        for transition in self.graph.transitions:
            key = "success" if transition.success else "failed"
            transition_breakdown[key] = transition_breakdown.get(key, 0) + 1

        return CoverageReport(
            states_found=len(self.visited_states),
            transitions_found=len(self.visited_transitions),
            endpoints_discovered=len(endpoints_discovered),
            endpoints_tested=len(endpoints_tested),
            coverage_percent=min(100.0, coverage_percent),
            uncovered_actions=uncovered_actions,
            state_breakdown=state_breakdown,
            transition_breakdown=transition_breakdown,
        )

    def reset(self) -> None:
        """Reset the engine state for a new exploration."""
        self.graph = StateGraph()
        self.issues.clear()
        self.visited_states.clear()
        self.visited_transitions.clear()
        self._exploration_queue.clear()
        self._exploration_stack.clear()
        self._current_depth = 0
        self._all_discovered_actions.clear()
        self._executed_actions.clear()
