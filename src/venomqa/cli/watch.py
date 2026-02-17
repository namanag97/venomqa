"""Watch mode for VenomQA - automatically re-run journeys on file changes."""

from __future__ import annotations

import importlib.util
import re
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

if TYPE_CHECKING:
    from watchdog.events import FileSystemEvent

# Debounce delay in seconds
DEBOUNCE_DELAY = 0.5


@dataclass
class FileChange:
    """Represents a file change event."""

    path: Path
    event_type: str  # created, modified, deleted
    timestamp: float = field(default_factory=time.time)


@dataclass
class WatchState:
    """State for the watch mode."""

    # Maps: action_name -> set of journey names that use it
    action_to_journeys: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # Maps: fixture_name -> set of journey names that use it
    fixture_to_journeys: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # Maps: journey_file -> journey_name
    journey_files: dict[Path, str] = field(default_factory=dict)
    # Maps: action_file -> set of action names
    action_files: dict[Path, set[str]] = field(default_factory=lambda: defaultdict(set))
    # Maps: fixture_file -> set of fixture names
    fixture_files: dict[Path, set[str]] = field(default_factory=lambda: defaultdict(set))
    # All discovered journeys
    journeys: dict[str, Any] = field(default_factory=dict)
    # Run count for statistics
    run_count: int = 0
    # Last run time
    last_run: datetime | None = None


class DependencyAnalyzer:
    """Analyzes dependencies between actions, fixtures, and journeys."""

    # Patterns to detect action and fixture usage in journey files
    ACTION_PATTERN = re.compile(r'action\s*=\s*["\']([^"\']+)["\']')
    REQUIRES_PATTERN = re.compile(r'requires\s*=\s*\[([^\]]+)\]')
    FIXTURE_USE_PATTERN = re.compile(r'@fixture\s*(?:\(.*?\))?\s*\ndef\s+(\w+)')
    ACTION_DECORATOR_PATTERN = re.compile(r'@action\s*\(["\']([^"\']+)["\']\)')

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path
        self.actions_dir = base_path / "actions"
        self.fixtures_dir = base_path / "fixtures"
        self.journeys_dir = base_path / "journeys"

    def analyze(self) -> WatchState:
        """Analyze all files and build dependency graph."""
        state = WatchState()

        # Discover actions
        if self.actions_dir.exists():
            for action_file in self.actions_dir.glob("**/*.py"):
                if action_file.name.startswith("_"):
                    continue
                actions = self._extract_actions(action_file)
                state.action_files[action_file] = actions

        # Discover fixtures
        if self.fixtures_dir.exists():
            for fixture_file in self.fixtures_dir.glob("**/*.py"):
                if fixture_file.name.startswith("_"):
                    continue
                fixtures = self._extract_fixtures(fixture_file)
                state.fixture_files[fixture_file] = fixtures

        # Discover journeys and their dependencies
        if self.journeys_dir.exists():
            for journey_file in self.journeys_dir.glob("**/*.py"):
                if journey_file.name.startswith("_"):
                    continue
                journey_name = journey_file.stem
                state.journey_files[journey_file] = journey_name

                # Load and analyze journey
                journey = self._load_journey(journey_name, journey_file)
                if journey:
                    state.journeys[journey_name] = journey

                    # Analyze action dependencies
                    actions_used = self._extract_actions_from_journey(journey_file)
                    for action_name in actions_used:
                        state.action_to_journeys[action_name].add(journey_name)

                    # Analyze fixture dependencies
                    fixtures_used = self._extract_fixtures_from_journey(journey_file, journey)
                    for fixture_name in fixtures_used:
                        state.fixture_to_journeys[fixture_name].add(journey_name)

        return state

    def _extract_actions(self, file_path: Path) -> set[str]:
        """Extract action names from an action file."""
        actions = set()
        try:
            content = file_path.read_text()
            # Find @action("name") decorators
            matches = self.ACTION_DECORATOR_PATTERN.findall(content)
            actions.update(matches)
        except Exception:
            pass
        return actions

    def _extract_fixtures(self, file_path: Path) -> set[str]:
        """Extract fixture names from a fixture file."""
        fixtures = set()
        try:
            content = file_path.read_text()
            # Find @fixture decorated functions
            matches = self.FIXTURE_USE_PATTERN.findall(content)
            fixtures.update(matches)
        except Exception:
            pass
        return fixtures

    def _extract_actions_from_journey(self, journey_file: Path) -> set[str]:
        """Extract action names used in a journey file."""
        actions = set()
        try:
            content = journey_file.read_text()
            # Find action="name" patterns
            matches = self.ACTION_PATTERN.findall(content)
            actions.update(matches)
        except Exception:
            pass
        return actions

    def _extract_fixtures_from_journey(self, journey_file: Path, journey: Any) -> set[str]:
        """Extract fixture names used in a journey."""
        fixtures = set()

        # From journey.requires attribute
        if hasattr(journey, "requires"):
            fixtures.update(journey.requires)

        # From file content (requires=[...])
        try:
            content = journey_file.read_text()
            matches = self.REQUIRES_PATTERN.findall(content)
            for match in matches:
                # Parse the list items
                items = re.findall(r'["\']([^"\']+)["\']', match)
                fixtures.update(items)
        except Exception:
            pass

        return fixtures

    def _load_journey(self, name: str, path: Path) -> Any:
        """Load a journey from a Python file."""
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Look for journey object
            if hasattr(module, "journey"):
                return module.journey
            elif hasattr(module, name):
                return getattr(module, name)

            # Find any Journey-like object
            for attr_name in dir(module):
                if not attr_name.startswith("_"):
                    attr = getattr(module, attr_name)
                    if hasattr(attr, "steps"):
                        return attr

            return None
        except Exception:
            return None


class FileWatcher:
    """Watches files for changes using watchdog."""

    def __init__(
        self,
        paths: list[Path],
        on_change: callable,
        debounce_delay: float = DEBOUNCE_DELAY,
    ) -> None:
        self.paths = paths
        self.on_change = on_change
        self.debounce_delay = debounce_delay
        self._pending_changes: list[FileChange] = []
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._observer = None

    def start(self) -> None:
        """Start watching for file changes."""
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        class Handler(FileSystemEventHandler):
            def __init__(handler_self, watcher: FileWatcher) -> None:  # noqa: N805
                handler_self.watcher = watcher

            def on_any_event(handler_self, event: FileSystemEvent) -> None:  # noqa: N805
                if event.is_directory:
                    return
                if not event.src_path.endswith(".py"):
                    return
                # Ignore __pycache__ and hidden files
                if "__pycache__" in event.src_path or "/." in event.src_path:
                    return

                change = FileChange(
                    path=Path(event.src_path),
                    event_type=event.event_type,
                )
                handler_self.watcher._add_change(change)

        self._observer = Observer()
        handler = Handler(self)

        for path in self.paths:
            if path.exists():
                self._observer.schedule(handler, str(path), recursive=True)

        self._observer.start()

    def stop(self) -> None:
        """Stop watching for file changes."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
        if self._timer:
            self._timer.cancel()

    def _add_change(self, change: FileChange) -> None:
        """Add a change to pending changes with debouncing."""
        with self._lock:
            self._pending_changes.append(change)

            # Reset timer
            if self._timer:
                self._timer.cancel()

            self._timer = threading.Timer(self.debounce_delay, self._flush_changes)
            self._timer.start()

    def _flush_changes(self) -> None:
        """Process pending changes after debounce delay."""
        with self._lock:
            changes = self._pending_changes.copy()
            self._pending_changes.clear()

        if changes:
            # Deduplicate changes by path
            unique_changes = {}
            for change in changes:
                unique_changes[change.path] = change

            self.on_change(list(unique_changes.values()))


class WatchRunner:
    """Runs journeys in watch mode with smart re-running."""

    def __init__(
        self,
        base_path: Path,
        journey_names: list[str] | None = None,
        run_all: bool = False,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.base_path = base_path
        self.journey_names = journey_names or []
        self.run_all = run_all
        self.config = config or {}
        self.console = Console()
        self.state: WatchState | None = None
        self.watcher: FileWatcher | None = None
        self._running = False
        self._services_started = False

    def start(self) -> None:
        """Start watch mode."""
        self._running = True

        # Initial analysis
        self.console.print("\n[bold cyan]VenomQA Watch Mode[/bold cyan]")
        self.console.print("[dim]Analyzing project structure...[/dim]\n")

        analyzer = DependencyAnalyzer(self.base_path)
        self.state = analyzer.analyze()

        # Validate journey names
        if self.journey_names:
            for name in self.journey_names:
                if name not in self.state.journeys:
                    self.console.print(f"[red]Journey not found: {name}[/red]")
                    return

        # Display initial state
        self._display_state()

        # Start file watcher
        watch_paths = [
            self.base_path / "actions",
            self.base_path / "fixtures",
            self.base_path / "journeys",
        ]
        watch_paths = [p for p in watch_paths if p.exists()]

        if not watch_paths:
            self.console.print("[red]No watch directories found (actions/, fixtures/, journeys/)[/red]")
            return

        self.watcher = FileWatcher(watch_paths, self._on_file_changes)
        self.watcher.start()

        self.console.print(f"[green]Watching {len(watch_paths)} directories for changes...[/green]")
        self.console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        # Initial run
        self._run_journeys(self._get_journeys_to_run())

        # Keep running until interrupted
        try:
            while self._running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Stop watch mode."""
        self._running = False
        if self.watcher:
            self.watcher.stop()
        self.console.print("\n[yellow]Watch mode stopped[/yellow]")

    def _display_state(self) -> None:
        """Display the current state summary."""
        if not self.state:
            return

        table = Table(title="Project Structure", show_header=True, header_style="bold")
        table.add_column("Type", style="cyan")
        table.add_column("Count", style="green")
        table.add_column("Items", style="dim")

        # Journeys
        journey_names = list(self.state.journeys.keys())[:5]
        journey_str = ", ".join(journey_names)
        if len(self.state.journeys) > 5:
            journey_str += f", ... (+{len(self.state.journeys) - 5} more)"
        table.add_row("Journeys", str(len(self.state.journeys)), journey_str)

        # Actions
        all_actions = set()
        for actions in self.state.action_files.values():
            all_actions.update(actions)
        action_names = list(all_actions)[:5]
        action_str = ", ".join(action_names) if action_names else "(none)"
        if len(all_actions) > 5:
            action_str += f", ... (+{len(all_actions) - 5} more)"
        table.add_row("Actions", str(len(all_actions)), action_str)

        # Fixtures
        all_fixtures = set()
        for fixtures in self.state.fixture_files.values():
            all_fixtures.update(fixtures)
        fixture_names = list(all_fixtures)[:5]
        fixture_str = ", ".join(fixture_names) if fixture_names else "(none)"
        if len(all_fixtures) > 5:
            fixture_str += f", ... (+{len(all_fixtures) - 5} more)"
        table.add_row("Fixtures", str(len(all_fixtures)), fixture_str)

        self.console.print(table)
        self.console.print()

    def _get_journeys_to_run(self) -> list[str]:
        """Get the list of journeys to run based on configuration."""
        if not self.state:
            return []

        if self.run_all:
            return list(self.state.journeys.keys())

        if self.journey_names:
            return [n for n in self.journey_names if n in self.state.journeys]

        # Default to all journeys
        return list(self.state.journeys.keys())

    def _on_file_changes(self, changes: list[FileChange]) -> None:
        """Handle file changes."""
        if not self.state:
            return

        # Clear screen
        self.console.clear()

        # Show what changed
        self.console.print(f"\n[bold yellow]File changes detected at {datetime.now().strftime('%H:%M:%S')}[/bold yellow]")

        for change in changes:
            icon = {"created": "+", "modified": "~", "deleted": "-"}.get(change.event_type, "?")
            color = {"created": "green", "modified": "yellow", "deleted": "red"}.get(
                change.event_type, "white"
            )
            rel_path = change.path.relative_to(self.base_path) if self.base_path in change.path.parents else change.path
            self.console.print(f"  [{color}]{icon} {rel_path}[/{color}]")

        self.console.print()

        # Determine which journeys to re-run
        journeys_to_run = self._determine_affected_journeys(changes)

        if journeys_to_run:
            # Re-analyze if needed (for new files or deleted files)
            needs_reanalysis = any(c.event_type in ("created", "deleted") for c in changes)
            if needs_reanalysis:
                analyzer = DependencyAnalyzer(self.base_path)
                self.state = analyzer.analyze()

            self._run_journeys(journeys_to_run)
        else:
            self.console.print("[dim]No affected journeys to re-run[/dim]")

    def _determine_affected_journeys(self, changes: list[FileChange]) -> list[str]:
        """Determine which journeys are affected by the file changes."""
        if not self.state:
            return []

        affected = set()
        configured_journeys = set(self._get_journeys_to_run())

        for change in changes:
            path = change.path

            # Check if it's a journey file
            if path in self.state.journey_files:
                journey_name = self.state.journey_files[path]
                if journey_name in configured_journeys:
                    affected.add(journey_name)
                continue

            # Check if it's an action file
            if path in self.state.action_files:
                actions = self.state.action_files[path]
                for action_name in actions:
                    journeys_using_action = self.state.action_to_journeys.get(action_name, set())
                    affected.update(journeys_using_action & configured_journeys)
                continue

            # Check if it's a fixture file
            if path in self.state.fixture_files:
                fixtures = self.state.fixture_files[path]
                for fixture_name in fixtures:
                    journeys_using_fixture = self.state.fixture_to_journeys.get(fixture_name, set())
                    affected.update(journeys_using_fixture & configured_journeys)
                continue

            # Check by directory for new files
            try:
                rel_path = path.relative_to(self.base_path)
                parts = rel_path.parts

                if parts and parts[0] == "journeys":
                    # New journey file - re-run all configured journeys
                    if change.event_type == "created":
                        affected.update(configured_journeys)
                elif parts and parts[0] == "actions":
                    # New action file - re-run all configured journeys
                    if change.event_type == "created":
                        affected.update(configured_journeys)
                elif parts and parts[0] == "fixtures":
                    # New fixture file - re-run all configured journeys
                    if change.event_type == "created":
                        affected.update(configured_journeys)
            except ValueError:
                pass

        return list(affected)

    def _run_journeys(self, journey_names: list[str]) -> None:
        """Run the specified journeys."""
        if not journey_names:
            self.console.print("[dim]No journeys to run[/dim]")
            return

        if not self.state:
            return

        self.state.run_count += 1
        self.state.last_run = datetime.now()

        # Display run header
        run_header = f"Run #{self.state.run_count} - {len(journey_names)} journey(s)"
        self.console.print(Panel(run_header, style="bold blue"))
        self.console.print()

        start_time = time.time()
        results: list[dict[str, Any]] = []
        all_passed = True

        # Import here to avoid circular imports
        from venomqa.cli.commands import _execute_journey, _parse_ports

        for journey_name in journey_names:
            journey_file = None
            for file_path, name in self.state.journey_files.items():
                if name == journey_name:
                    journey_file = file_path
                    break

            if not journey_file:
                self.console.print(f"[red]Journey file not found: {journey_name}[/red]")
                continue

            # Reload the journey module to pick up changes
            journey = self._reload_journey(journey_name, journey_file)
            if journey is None:
                self.console.print(f"[red]Failed to load journey: {journey_name}[/red]")
                results.append({
                    "journey_name": journey_name,
                    "success": False,
                    "error": "Failed to load journey",
                })
                all_passed = False
                continue

            # Execute journey
            try:
                ports = _parse_ports((), self.config)
                result = _execute_journey(journey, self.config, no_infra=True, ports=ports)
                results.append(result)
                if not result.get("success", False):
                    all_passed = False
            except Exception as e:
                self.console.print(f"[red]Error running {journey_name}: {e}[/red]")
                results.append({
                    "journey_name": journey_name,
                    "success": False,
                    "error": str(e),
                })
                all_passed = False

        # Show summary
        elapsed = time.time() - start_time
        self._display_run_summary(results, elapsed, all_passed)

    def _reload_journey(self, name: str, path: Path) -> Any:
        """Reload a journey module to pick up changes."""
        # Remove from sys.modules to force reload
        module_name = f"journey_{name}"
        if module_name in sys.modules:
            del sys.modules[module_name]

        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Look for journey object
            if hasattr(module, "journey"):
                return module.journey
            elif hasattr(module, name):
                return getattr(module, name)

            # Find any Journey-like object
            for attr_name in dir(module):
                if not attr_name.startswith("_"):
                    attr = getattr(module, attr_name)
                    if hasattr(attr, "steps"):
                        return attr

            return None
        except Exception as e:
            self.console.print(f"[red]Error loading journey {name}: {e}[/red]")
            return None

    def _display_run_summary(
        self,
        results: list[dict[str, Any]],
        elapsed: float,
        all_passed: bool,
    ) -> None:
        """Display a summary of the run."""
        passed = sum(1 for r in results if r.get("success"))
        failed = len(results) - passed

        # Summary table
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold")
        table.add_column()

        table.add_row("Total:", str(len(results)))
        table.add_row("Passed:", f"[green]{passed}[/green]")
        table.add_row("Failed:", f"[red]{failed}[/red]")
        table.add_row("Duration:", f"{elapsed:.2f}s")

        status_color = "green" if all_passed else "red"
        status_text = "ALL PASSED" if all_passed else "SOME FAILED"
        status_symbol = "[check]" if all_passed else "[cross]"

        panel = Panel(
            table,
            title=f"[bold]{status_symbol} {status_text}[/bold]",
            border_style=status_color,
            padding=(1, 2),
        )

        self.console.print()
        self.console.print(panel)

        # Show failed journeys
        if failed > 0:
            self.console.print("\n[bold red]Failed journeys:[/bold red]")
            for result in results:
                if not result.get("success"):
                    name = result.get("journey_name", "unknown")
                    error = result.get("error", "Unknown error")
                    self.console.print(f"  [red]- {name}[/red]")
                    if error:
                        self.console.print(f"    [dim]{error}[/dim]")

        self.console.print("\n[dim]Watching for changes... (Ctrl+C to stop)[/dim]")


def run_watch_mode(
    base_path: Path,
    journey_names: list[str] | None = None,
    run_all: bool = False,
    config: dict[str, Any] | None = None,
) -> None:
    """Run VenomQA in watch mode.

    Args:
        base_path: Base path to watch (should contain actions/, fixtures/, journeys/)
        journey_names: Specific journey names to watch and run
        run_all: If True, run all discovered journeys
        config: Configuration dictionary
    """
    runner = WatchRunner(
        base_path=base_path,
        journey_names=journey_names,
        run_all=run_all,
        config=config,
    )
    runner.start()
