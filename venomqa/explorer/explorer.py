"""
State Explorer for the VenomQA State Explorer module.

This module provides the StateExplorer class which is the main orchestrator
for automated state space exploration. It coordinates the discoverer,
detector, engine, visualizer, and reporter to provide a complete
exploration workflow.

The StateExplorer is the primary entry point for users of this module.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from venomqa.explorer.models import (
    Action,
    CoverageReport,
    ExplorationConfig,
    ExplorationResult,
    Issue,
    State,
    StateGraph,
)
from venomqa.explorer.discoverer import APIDiscoverer
from venomqa.explorer.detector import StateDetector
from venomqa.explorer.engine import ExplorationEngine, ExplorationStrategy
from venomqa.explorer.visualizer import GraphVisualizer, OutputFormat
from venomqa.explorer.reporter import ExplorationReporter, ReportFormat


class StateExplorer:
    """
    Main orchestrator for automated state space exploration.

    The StateExplorer coordinates all components of the exploration system
    to provide a simple, unified interface for exploring API state spaces.

    Workflow:
    1. Discover available API endpoints
    2. Start from an initial state (e.g., after authentication)
    3. Systematically explore states and transitions
    4. Detect issues and anomalies
    5. Generate reports and visualizations

    Features:
    - Automatic endpoint discovery
    - Multiple exploration strategies
    - Issue detection and reporting
    - Coverage analysis
    - Visual state graph generation
    - Export to multiple formats

    Attributes:
        base_url: Base URL of the API to explore
        config: Exploration configuration
        discoverer: API endpoint discoverer
        detector: State detector
        engine: Exploration engine
        visualizer: Graph visualizer
        reporter: Report generator

    Example:
        explorer = StateExplorer(
            base_url="http://api.example.com",
            config=ExplorationConfig(
                max_depth=5,
                strategy=ExplorationStrategy.BFS,
            ),
        )

        # Authenticate and set initial state
        await explorer.authenticate(token="...")

        # Run exploration
        result = await explorer.explore()

        # Generate reports
        explorer.generate_report("report.html", ReportFormat.HTML)
        explorer.visualize("graph.svg", OutputFormat.SVG)

        print(f"Found {result.coverage.states_found} states")
        print(f"Coverage: {result.coverage.coverage_percent:.1f}%")
    """

    def __init__(
        self,
        base_url: str,
        config: Optional[ExplorationConfig] = None,
        strategy: ExplorationStrategy = ExplorationStrategy.BFS,
    ) -> None:
        """
        Initialize the state explorer.

        Args:
            base_url: Base URL of the API to explore
            config: Optional exploration configuration
            strategy: Exploration strategy to use
        """
        self.base_url = base_url.rstrip("/")
        self.config = config or ExplorationConfig()
        self.strategy = strategy

        # Initialize components
        self.discoverer = APIDiscoverer(self.base_url, self.config)
        self.detector = StateDetector()
        self.engine = ExplorationEngine(self.config, strategy)
        self.visualizer = GraphVisualizer()
        self.reporter = ExplorationReporter()

        # State
        self._initial_state: Optional[State] = None
        self._result: Optional[ExplorationResult] = None
        self._http_client: Optional[Any] = None
        self._auth_token: Optional[str] = None
        self._auth_headers: Dict[str, str] = {}

        # Hooks
        self._pre_action_hooks: List[Callable[[Action], None]] = []
        self._post_action_hooks: List[Callable[[Action, Any], None]] = []

        # TODO: Initialize HTTP client
        # TODO: Set up engine callbacks

    async def explore(
        self,
        initial_actions: Optional[List[Action]] = None,
    ) -> ExplorationResult:
        """
        Run the full exploration process.

        This is the main entry point for exploration. It will:
        1. Discover endpoints (if not already done)
        2. Initialize the exploration engine
        3. Execute the exploration strategy
        4. Collect and analyze results
        5. Generate coverage report

        Args:
            initial_actions: Optional list of actions to start with

        Returns:
            ExplorationResult containing the complete results

        Raises:
            ExplorationError: If exploration fails
        """
        # Record start time
        started_at = datetime.now()
        error_msg: Optional[str] = None
        success = True

        try:
            # Set up engine with callbacks
            self.engine.set_state_detector(self.detector.detect_state)

            # Ensure initial state is set
            if not self._initial_state:
                # Create a default initial state
                self._initial_state = State(
                    id="initial",
                    name="Initial",
                    properties={"authenticated": bool(self._auth_token)},
                    available_actions=initial_actions or [],
                    discovered_at=datetime.now(),
                )
                self.engine.graph.add_state(self._initial_state)
                self.engine.graph.initial_state = self._initial_state.id

            # Add initial actions to the state if provided
            if initial_actions:
                self._initial_state.available_actions.extend(initial_actions)

            # Run exploration
            await self.engine.explore(self._initial_state, initial_actions)

        except Exception as e:
            success = False
            error_msg = str(e)

        # Record end time
        finished_at = datetime.now()
        duration = finished_at - started_at

        # Generate coverage report
        coverage = self.engine.get_coverage_report()

        # Create ExplorationResult
        self._result = ExplorationResult(
            graph=self.engine.graph,
            issues=self.engine.issues,
            coverage=coverage,
            duration=duration,
            started_at=started_at,
            finished_at=finished_at,
            config=self.config,
            error=error_msg,
            success=success,
        )

        return self._result

    async def discover_endpoints(self) -> List[Action]:
        """
        Discover available API endpoints.

        Returns:
            List of discovered Action objects
        """
        # TODO: Implement endpoint discovery
        # 1. Call discoverer.discover()
        # 2. Cache results
        # 3. Return actions
        raise NotImplementedError("discover_endpoints() not yet implemented")

    async def authenticate(
        self,
        token: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        login_action: Optional[Action] = None,
    ) -> None:
        """
        Set up authentication for exploration.

        Args:
            token: Bearer token for authentication
            headers: Custom authentication headers
            login_action: Action to execute for authentication
        """
        # TODO: Implement authentication setup
        # 1. Store token/headers
        # 2. Update config
        # 3. Execute login action if provided
        # 4. Set initial state from login response
        raise NotImplementedError("authenticate() not yet implemented")

    def set_initial_state(self, state: State) -> None:
        """
        Set the initial state for exploration.

        Args:
            state: The initial state to start from
        """
        self._initial_state = state
        self.engine.graph.add_state(state)
        self.engine.graph.initial_state = state.id

    async def explore_from_state(
        self,
        state: State,
    ) -> ExplorationResult:
        """
        Explore starting from a specific state.

        Args:
            state: The state to start exploration from

        Returns:
            ExplorationResult from exploration
        """
        # TODO: Implement exploration from state
        # 1. Set state as current
        # 2. Run exploration
        # 3. Return results
        raise NotImplementedError("explore_from_state() not yet implemented")

    async def execute_action(
        self,
        action: Action,
    ) -> Dict[str, Any]:
        """
        Execute a single action and return the response.

        Args:
            action: The action to execute

        Returns:
            Response data from the action

        Raises:
            ActionExecutionError: If action execution fails
        """
        # TODO: Implement action execution
        # 1. Call pre-action hooks
        # 2. Build HTTP request
        # 3. Execute request
        # 4. Call post-action hooks
        # 5. Return response data
        raise NotImplementedError("execute_action() not yet implemented")

    def generate_report(
        self,
        output_path: str,
        format: ReportFormat = ReportFormat.HTML,
    ) -> str:
        """
        Generate an exploration report.

        Args:
            output_path: Path to save the report
            format: Report format to use

        Returns:
            Path to the generated report

        Raises:
            ValueError: If no exploration has been run
        """
        if not self._result:
            raise ValueError("No exploration result available. Run explore() first.")

        self.reporter.set_result(self._result)
        return self.reporter.generate(output_path, format)

    def visualize(
        self,
        output_path: str,
        format: OutputFormat = OutputFormat.SVG,
    ) -> str:
        """
        Generate a visualization of the state graph.

        Args:
            output_path: Path to save the visualization
            format: Output format to use

        Returns:
            Path to the generated visualization

        Raises:
            ValueError: If no exploration has been run
        """
        if not self._result:
            raise ValueError("No exploration result available. Run explore() first.")

        self.visualizer.set_graph(self._result.graph)
        self.visualizer.highlight_issues(self._result.issues)
        return self.visualizer.render(output_path, format)

    def add_pre_action_hook(
        self,
        hook: Callable[[Action], None],
    ) -> None:
        """
        Add a hook to be called before each action.

        Args:
            hook: Function to call with the action before execution
        """
        self._pre_action_hooks.append(hook)

    def add_post_action_hook(
        self,
        hook: Callable[[Action, Any], None],
    ) -> None:
        """
        Add a hook to be called after each action.

        Args:
            hook: Function to call with action and response after execution
        """
        self._post_action_hooks.append(hook)

    def add_state_key_field(self, field: str) -> None:
        """
        Add a field to use for state identification.

        Args:
            field: Field name to use for identifying states
        """
        self.detector.add_state_key_field(field)

    def add_seed_endpoint(self, method: str, path: str) -> None:
        """
        Add a seed endpoint for discovery.

        Args:
            method: HTTP method
            path: Endpoint path
        """
        self.discoverer.add_seed_endpoints([(method, path)])

    def set_strategy(self, strategy: ExplorationStrategy) -> None:
        """
        Set the exploration strategy.

        Args:
            strategy: Strategy to use for exploration
        """
        self.strategy = strategy
        self.engine.strategy = strategy

    def get_result(self) -> Optional[ExplorationResult]:
        """
        Get the latest exploration result.

        Returns:
            The most recent ExplorationResult, or None if not explored
        """
        return self._result

    def get_graph(self) -> Optional[StateGraph]:
        """
        Get the current state graph.

        Returns:
            The StateGraph, or None if not explored
        """
        return self._result.graph if self._result else None

    def get_issues(self) -> List[Issue]:
        """
        Get all discovered issues.

        Returns:
            List of Issue objects
        """
        return self._result.issues if self._result else []

    def get_coverage(self) -> Optional[CoverageReport]:
        """
        Get the coverage report.

        Returns:
            CoverageReport, or None if not explored
        """
        return self._result.coverage if self._result else None

    def reset(self) -> None:
        """Reset the explorer state for a new exploration."""
        self._initial_state = None
        self._result = None
        self.engine.reset()
        self.detector.clear_cache()
        self.discoverer.clear()

    async def close(self) -> None:
        """Clean up resources."""
        # TODO: Implement cleanup
        # 1. Close HTTP client
        # 2. Clean up any temporary files
        raise NotImplementedError("close() not yet implemented")

    async def __aenter__(self) -> "StateExplorer":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
