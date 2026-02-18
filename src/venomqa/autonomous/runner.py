"""Autonomous runner - zero-config API testing."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from venomqa import ExplorationResult


class AutonomousRunner:
    """Runs VenomQA exploration autonomously from project discovery.

    Usage:
        runner = AutonomousRunner()
        result = runner.run()

    The runner will:
    1. Discover docker-compose.yml and openapi.yaml in the current directory
    2. Spin up isolated test containers (won't touch your real database)
    3. Generate actions from your OpenAPI spec
    4. Run state hypergraph exploration
    5. Report any bugs found
    6. Tear down containers
    """

    def __init__(
        self,
        project_dir: Path | str = ".",
        max_steps: int = 500,
        strategy: str = "auto",  # auto, bfs, dfs, mcts, coverage
        hypergraph: bool = True,
        verbose: bool = True,
    ) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.max_steps = max_steps
        self.strategy_name = strategy
        self.hypergraph = hypergraph
        self.verbose = verbose

        self._discovery = None
        self._infra = None
        self._console = None

    def _log(self, message: str, style: str = "") -> None:
        """Log a message if verbose mode is on."""
        if not self.verbose:
            return

        if self._console is None:
            from rich.console import Console
            self._console = Console()

        if style:
            self._console.print(f"[{style}]{message}[/{style}]")
        else:
            self._console.print(message)

    def _log_step(self, step: int, total: int, message: str) -> None:
        """Log a step in the process."""
        self._log(f"\n [{step}/{total}] {message}", "bold cyan")

    def run(self) -> "ExplorationResult":
        """Run autonomous exploration.

        Returns:
            ExplorationResult with all findings
        """
        from venomqa.autonomous.discovery import ProjectDiscovery
        from venomqa.autonomous.isolated_infra import IsolatedInfrastructureManager
        from venomqa.autonomous.invariants import create_default_invariants

        self._log("\n [bold cyan]VenomQA - Autonomous API Testing[/bold cyan]")
        self._log(" " + "─" * 40)

        # Step 1: Discover project structure
        self._log_step(1, 6, "Discovering project structure...")

        self._discovery = ProjectDiscovery(self.project_dir)

        compose_path = self._discovery.find_compose_file()
        if not compose_path:
            raise RuntimeError(
                f"No docker-compose.yml found in {self.project_dir}\n"
                "VenomQA needs a docker-compose file to understand your stack."
            )
        self._log(f"       ✓ Found {compose_path.name}", "green")

        openapi_path = self._discovery.find_openapi_spec()
        if not openapi_path:
            raise RuntimeError(
                f"No OpenAPI spec found in {self.project_dir}\n"
                "VenomQA needs an OpenAPI spec to generate test actions.\n"
                "Expected: openapi.yaml, openapi.json, swagger.yaml, swagger.json"
            )
        self._log(f"       ✓ Found {openapi_path.name}", "green")

        db_config = self._discovery.detect_database()
        if db_config:
            self._log(f"       ✓ Detected {db_config.type} database", "green")

        api_service = self._discovery.detect_api_service()
        if api_service:
            self._log(f"       ✓ Detected API service: {api_service.name}", "green")

        # Step 2: Create isolated test environment
        self._log_step(2, 6, "Creating isolated test environment...")

        self._infra = IsolatedInfrastructureManager(compose_path)
        test_compose = self._infra.create_test_compose()
        self._log(f"       ✓ Generated isolated compose file", "green")
        self._log(f"       ✓ Using random ports to avoid conflicts", "green")

        try:
            # Step 3: Start containers
            self._log_step(3, 6, "Starting containers...")

            endpoints = self._infra.start(timeout=120.0)

            for name, endpoint in endpoints.items():
                self._log(
                    f"       ✓ {name}: healthy ({endpoint.original_port} → {endpoint.port})",
                    "green"
                )

            # Step 4: Generate actions from OpenAPI
            self._log_step(4, 6, "Generating test actions from OpenAPI...")

            from venomqa.v1.generators.openapi_actions import generate_actions

            # Get API endpoint URL
            api_endpoint = None
            if api_service and api_service.name in endpoints:
                api_endpoint = endpoints[api_service.name].url
            else:
                # Try common names
                for name in ["api", "app", "web", "backend"]:
                    if name in endpoints:
                        api_endpoint = endpoints[name].url
                        break

            if not api_endpoint:
                # Fallback to first non-database endpoint
                for name, ep in endpoints.items():
                    if name not in ["postgres", "mysql", "redis", "db"]:
                        api_endpoint = ep.url
                        break

            if not api_endpoint:
                raise RuntimeError("Could not determine API endpoint URL")

            actions = generate_actions(openapi_path, base_url=api_endpoint)
            self._log(f"       ✓ Created {len(actions)} actions", "green")

            # Create default invariants
            invariants = create_default_invariants()
            self._log(f"       ✓ Created {len(invariants)} default invariants", "green")

            # Step 5: Run exploration
            self._log_step(5, 6, f"Exploring API sequences ({self._get_strategy_name()} strategy)...")

            from venomqa import Agent, World, DFS, BFS, CoverageGuided
            from venomqa.adapters import HttpClient

            # Create World with API client
            api = HttpClient(base_url=api_endpoint)

            # Try to set up database adapter for real rollback
            world_kwargs = {"api": api}

            if db_config:
                db_dsn = self._infra.get_database_dsn()
                if db_dsn:
                    try:
                        from venomqa.adapters.postgres import PostgresAdapter
                        db_adapter = PostgresAdapter(db_dsn)
                        world_kwargs["systems"] = {"db": db_adapter}
                        self._log(f"       ✓ Connected to test database", "green")
                    except Exception as e:
                        self._log(f"       ⚠ Database adapter failed: {e}", "yellow")
                        world_kwargs["state_from_context"] = ["resource_id"]
            else:
                world_kwargs["state_from_context"] = ["resource_id"]

            world = World(**world_kwargs)

            # Select strategy
            strategy = self._select_strategy(db_config)

            # Create and run agent
            agent = Agent(
                world=world,
                actions=actions,
                invariants=invariants,
                strategy=strategy,
                max_steps=self.max_steps,
                hypergraph=self.hypergraph,
            )

            # Run with progress reporting
            result = agent.explore()

            # Report violations
            if result.violations:
                self._log("")
                from rich.panel import Panel
                for v in result.violations:
                    self._console.print(Panel(
                        f"[bold]{v.invariant_name}[/bold]\n\n"
                        f"{v.message}\n\n"
                        f"Path: {' → '.join(v.action_path) if v.action_path else 'N/A'}",
                        title=f"[red][{v.severity.value.upper()}][/red]",
                        border_style="red",
                    ))

            return result

        finally:
            # Step 6: Cleanup
            self._log_step(6, 6, "Cleaning up...")

            if self._infra:
                self._infra.teardown(remove_volumes=True)
                self._log("       ✓ Containers stopped", "green")
                self._log("       ✓ Volumes removed", "green")

            # Print summary
            if 'result' in locals():
                self._log("")
                self._log(
                    f" Summary: {result.states_visited} states | "
                    f"{result.transitions_taken} steps | "
                    f"{result.action_coverage_percent:.0f}% coverage | "
                    f"{len(result.violations)} bug(s) found",
                    "bold"
                )

    def _get_strategy_name(self) -> str:
        """Get human-readable strategy name."""
        if self.strategy_name == "auto":
            return "auto-selected"
        return self.strategy_name.upper()

    def _select_strategy(self, db_config):
        """Select exploration strategy based on database type."""
        from venomqa import BFS, DFS, CoverageGuided

        if self.strategy_name == "dfs":
            return DFS()
        elif self.strategy_name == "bfs":
            return BFS()
        elif self.strategy_name == "coverage":
            return CoverageGuided()
        elif self.strategy_name == "auto":
            # Auto-select based on database
            if db_config and db_config.type == "postgres":
                # PostgreSQL only works with DFS (savepoints are stack-based)
                return DFS()
            else:
                # SQLite or context-only mode can use BFS
                return BFS()

        return BFS()
