"""Orchestrator - Coordinates the full test lifecycle."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from venomqa.runtime.service import HealthStatus, Service, ServiceType

if TYPE_CHECKING:
    from venomqa.exploration import ExplorationResult, ExplorationStrategy
    from venomqa.reporting.protocol import Reporter
    from venomqa.v1.core.action import Action
    from venomqa.v1.core.invariant import Invariant

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Configuration for the Orchestrator.

    Attributes:
        max_steps: Maximum exploration steps.
        strategy_name: Name of the default strategy ("bfs", "dfs", "random", "mcts").
        coverage_target: Target action coverage percentage (0.0 to 1.0).
        progress_every: Print progress every N steps (0 = disabled).
        health_timeout: Seconds to wait for services to be healthy.
    """

    max_steps: int = 1000
    strategy_name: str = "bfs"
    coverage_target: float | None = None
    progress_every: int = 0
    health_timeout: float = 60.0


class Orchestrator:
    """Coordinates the full exploration lifecycle.

    The Orchestrator provides a high-level API for running explorations.
    It manages the lifecycle:
    1. **Register services** -- Track what's running and where
    2. **Discover endpoints** -- (Optional) Parse OpenAPI specs
    3. **Explore** -- Run the Agent with the configured strategy
    4. **Report** -- Format and output results
    5. **Cleanup** -- Tear down resources

    This is the "conductor" that ties together the bounded contexts
    (Sandbox, Exploration, Discovery, Reporting, Runtime).

    Example::

        orchestrator = Orchestrator()
        orchestrator.register_service(Service(
            name="api",
            type=ServiceType.API,
            endpoint="http://localhost:8000",
        ))
        orchestrator.set_actions(my_actions)
        orchestrator.set_invariants(my_invariants)
        result = orchestrator.explore()
        print(orchestrator.report(result))

    Args:
        config: Optional orchestrator configuration.
    """

    def __init__(self, config: OrchestratorConfig | None = None) -> None:
        self._config = config or OrchestratorConfig()
        self._services: dict[str, Service] = {}
        self._actions: list[Action] = []
        self._invariants: list[Invariant] = []
        self._reporters: list[Reporter] = []
        self._strategy: ExplorationStrategy | None = None
        self._started_at: datetime | None = None
        self._last_result: ExplorationResult | None = None

    @property
    def config(self) -> OrchestratorConfig:
        """Current orchestrator configuration."""
        return self._config

    @property
    def services(self) -> dict[str, Service]:
        """All registered services, keyed by name."""
        return dict(self._services)

    @property
    def last_result(self) -> ExplorationResult | None:
        """The result of the last exploration run."""
        return self._last_result

    def register_service(self, service: Service) -> None:
        """Register a service for tracking.

        Args:
            service: The service to register.
        """
        self._services[service.name] = service
        logger.info(f"Registered service: {service.name} ({service.type.value}) at {service.endpoint}")

    def get_service(self, name: str) -> Service | None:
        """Get a registered service by name.

        Args:
            name: The service name.

        Returns:
            The Service, or None if not registered.
        """
        return self._services.get(name)

    def get_api_service(self) -> Service | None:
        """Get the first registered API service.

        Returns:
            The first API-type service, or None.
        """
        for svc in self._services.values():
            if svc.type == ServiceType.API:
                return svc
        return None

    def set_actions(self, actions: list[Action]) -> None:
        """Set the actions for exploration.

        Args:
            actions: List of Action objects.
        """
        self._actions = list(actions)

    def set_invariants(self, invariants: list[Invariant]) -> None:
        """Set the invariants for exploration.

        Args:
            invariants: List of Invariant objects.
        """
        self._invariants = list(invariants)

    def set_strategy(self, strategy: ExplorationStrategy) -> None:
        """Set the exploration strategy.

        Args:
            strategy: The strategy to use.
        """
        self._strategy = strategy

    def add_reporter(self, reporter: Reporter) -> None:
        """Add a reporter for formatting results.

        Args:
            reporter: The reporter to add.
        """
        self._reporters.append(reporter)

    def check_health(self) -> dict[str, HealthStatus]:
        """Check health of all registered services.

        Returns a dict of service name -> health status. This is a
        lightweight check that just returns current tracked status.

        Returns:
            Dict mapping service name to current HealthStatus.
        """
        return {name: svc.health for name, svc in self._services.items()}

    def all_healthy(self) -> bool:
        """Check if all registered services are healthy.

        Returns:
            True if all services are healthy.
        """
        if not self._services:
            return True
        return all(svc.is_healthy for svc in self._services.values())

    def explore(self, **kwargs: Any) -> ExplorationResult:
        """Run the exploration.

        Creates an Agent with the configured actions, invariants, and
        strategy, then runs the exploration.

        Args:
            **kwargs: Additional keyword arguments passed to Agent.

        Returns:
            ExplorationResult from the exploration.

        Raises:
            RuntimeError: If no actions have been configured.
        """
        from venomqa.exploration.strategies import BFS, DFS, MCTS, Random
        from venomqa.v1.agent import Agent
        from venomqa.v1.adapters.http import HttpClient
        from venomqa.sandbox import World

        if not self._actions:
            raise RuntimeError("No actions configured. Call set_actions() first.")

        # Determine strategy
        strategy = self._strategy
        if strategy is None:
            strategy_map: dict[str, Any] = {
                "bfs": BFS,
                "dfs": DFS,
                "random": Random,
                "mcts": MCTS,
            }
            strategy_cls = strategy_map.get(self._config.strategy_name.lower(), BFS)
            strategy = strategy_cls()

        # Create World from API service
        api_service = self.get_api_service()
        if api_service:
            api = HttpClient(api_service.endpoint)
        else:
            # Create a minimal client for in-process testing
            api = HttpClient("http://localhost")

        world = World(api=api)

        # Create and run agent
        self._started_at = datetime.now()

        agent = Agent(
            world=world,
            actions=self._actions,
            invariants=self._invariants,
            strategy=strategy,
            max_steps=kwargs.get("max_steps", self._config.max_steps),
            coverage_target=kwargs.get("coverage_target", self._config.coverage_target),
            progress_every=kwargs.get("progress_every", self._config.progress_every),
            **{k: v for k, v in kwargs.items() if k not in ("max_steps", "coverage_target", "progress_every")},
        )

        result = agent.explore()
        self._last_result = result
        return result

    def report(self, result: ExplorationResult | None = None) -> list[str]:
        """Generate reports from all configured reporters.

        Args:
            result: The exploration result to report on.
                If None, uses the last exploration result.

        Returns:
            List of report strings (one per reporter).

        Raises:
            RuntimeError: If no result available and no result passed.
        """
        target = result or self._last_result
        if target is None:
            raise RuntimeError("No exploration result available. Run explore() first.")

        reports = []
        for reporter in self._reporters:
            reports.append(reporter.report(target))
        return reports

    def cleanup(self) -> None:
        """Clean up resources.

        Marks all services as stopped and resets internal state.
        """
        for svc in self._services.values():
            svc.mark_stopped()
        self._last_result = None
        logger.info("Orchestrator cleanup complete")


__all__ = ["Orchestrator", "OrchestratorConfig"]
