"""Journey discovery via decorators and file scanning."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from typing import Any

from venomqa.core.models import Journey
from venomqa.plugins.registry import get_registry


def journey(name: str) -> Callable[[Callable[[], Journey]], Callable[[], Journey]]:
    """Decorator to register a journey factory function.

    Usage:
        @journey("user_login")
        def create_login_journey() -> Journey:
            return Journey(name="user_login", steps=[...])
    """

    def decorator(func: Callable[[], Journey]) -> Callable[[], Journey]:
        registry = get_registry()

        def wrapper() -> Journey:
            j = func()
            if j.name != name:
                j.name = name
            registry.register_journey(j)
            return j

        wrapper._journey_name = name
        wrapper._is_journey_factory = True
        return wrapper

    return decorator


def action(name: str) -> Callable:
    """Decorator to register a reusable action.

    Usage:
        @action("click_button")
        def click_button(client, ctx):
            client.click("#submit")
    """
    registry = get_registry()

    def decorator(func: Callable) -> Callable:
        registry.register_action(name, func)
        func._action_name = name
        func._is_action = True
        return func

    return decorator


def fixture(
    name: str | Callable | None = None,
    *,
    depends: list[str] | None = None,
    scope: str = "function",
) -> Callable:
    """Decorator to register a fixture with dependency injection.

    Args:
        name: Fixture name (defaults to function name).
        depends: List of other fixture names this fixture depends on.
        scope: Fixture scope - "function", "journey", or "session".

    Usage:
        @fixture
        def db():
            return Database()

        @fixture(depends=["db"])
        def user(db):
            return db.create_user()

        @fixture("client", depends=["user"])
        def http_client(user):
            return Client(user.token)
    """
    registry = get_registry()

    # Handle @fixture without parentheses - name is actually the function
    if callable(name):
        func = name
        fixture_name = func.__name__
        registry.register_fixture(
            name=fixture_name,
            factory=func,
            depends=depends or [],
            scope=scope,
        )
        func._fixture_name = fixture_name
        func._is_fixture = True
        func._fixture_depends = []
        func._fixture_scope = scope
        return func

    def decorator(func: Callable) -> Callable:
        fixture_name = name or func.__name__
        registry.register_fixture(
            name=fixture_name,
            factory=func,
            depends=depends,
            scope=scope,
        )
        func._fixture_name = fixture_name
        func._is_fixture = True
        func._fixture_depends = depends or []
        func._fixture_scope = scope
        return func

    return decorator


def extension(name: str) -> Callable:
    """Decorator to register a plugin extension.

    Usage:
        @extension("custom_reporter")
        class CustomReporter:
            ...
    """
    registry = get_registry()

    def decorator(obj: Callable) -> Callable:
        registry.register_extension(name, obj)
        obj._extension_name = name
        obj._is_extension = True
        return obj

    return decorator


def _load_module_from_file(file_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def discover_journeys(path: str | Path) -> dict[str, Journey]:
    """Scan a directory for journey files and register them.

    Looks for:
    - Python files matching pattern: *_journey.py or journey_*.py
    - Functions decorated with @journey
    - Direct Journey instances assigned to module-level variables

    Args:
        path: Directory path to scan for journey files

    Returns:
        Dictionary mapping journey names to Journey instances
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Journey path does not exist: {path}")

    registry = get_registry()

    patterns = ["*_journey.py", "journey_*.py"]
    journey_files: list[Path] = []

    if path.is_file() and path.suffix == ".py":
        journey_files = [path]
    elif path.is_dir():
        for pattern in patterns:
            journey_files.extend(path.glob(pattern))
        journey_files = list(set(journey_files))

    for file_path in journey_files:
        _load_module_from_file(file_path)

    return registry.get_all_journeys()


def discover_from_journeys_dir(base_path: str | Path | None = None) -> dict[str, Journey]:
    """Discover journeys from the standard 'journeys/' directory.

    Args:
        base_path: Base directory containing 'journeys/' folder.
                   Defaults to current working directory.

    Returns:
        Dictionary mapping journey names to Journey instances
    """
    if base_path is None:
        base_path = Path.cwd()
    else:
        base_path = Path(base_path)

    journeys_path = base_path / "journeys"
    if not journeys_path.exists():
        return {}

    return discover_journeys(journeys_path)


def discover_actions(path: str | Path) -> dict[str, Callable]:
    """Scan a directory for action files and register them.

    Looks for Python files in the given path and registers functions
    decorated with @action.

    Args:
        path: Directory path to scan for action files.

    Returns:
        Dictionary mapping action names to functions.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Action path does not exist: {path}")

    registry = get_registry()
    action_files: list[Path] = []

    if path.is_file() and path.suffix == ".py":
        action_files = [path]
    elif path.is_dir():
        action_files = list(path.glob("*.py"))
        action_files = [f for f in action_files if not f.name.startswith("_")]

    for file_path in action_files:
        _load_module_from_file(file_path)

    return registry.get_all_actions()


def discover_from_actions_dir(base_path: str | Path | None = None) -> dict[str, Callable]:
    """Discover actions from the standard 'actions/' directory.

    Args:
        base_path: Base directory containing 'actions/' folder.
                   Defaults to current working directory.

    Returns:
        Dictionary mapping action names to functions.
    """
    if base_path is None:
        base_path = Path.cwd()
    else:
        base_path = Path(base_path)

    actions_path = base_path / "actions"
    if not actions_path.exists():
        return {}

    return discover_actions(actions_path)


def discover_fixtures(path: str | Path) -> dict[str, Any]:
    """Scan a directory for fixture files and register them.

    Looks for Python files in the given path and registers functions
    decorated with @fixture.

    Args:
        path: Directory path to scan for fixture files.

    Returns:
        Dictionary mapping fixture names to FixtureInfo objects.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Fixture path does not exist: {path}")

    registry = get_registry()
    fixture_files: list[Path] = []

    if path.is_file() and path.suffix == ".py":
        fixture_files = [path]
    elif path.is_dir():
        fixture_files = list(path.glob("*.py"))
        fixture_files = [f for f in fixture_files if not f.name.startswith("_")]

    for file_path in fixture_files:
        _load_module_from_file(file_path)

    return registry.get_all_fixtures()


def discover_from_fixtures_dir(base_path: str | Path | None = None) -> dict[str, Any]:
    """Discover fixtures from the standard 'fixtures/' directory.

    Args:
        base_path: Base directory containing 'fixtures/' folder.
                   Defaults to current working directory.

    Returns:
        Dictionary mapping fixture names to FixtureInfo objects.
    """
    if base_path is None:
        base_path = Path.cwd()
    else:
        base_path = Path(base_path)

    fixtures_path = base_path / "fixtures"
    if not fixtures_path.exists():
        return {}

    return discover_fixtures(fixtures_path)


def discover_all(base_path: str | Path | None = None) -> dict[str, Any]:
    """Discover all journeys, actions, and fixtures from standard directories.

    Args:
        base_path: Base directory containing 'journeys/', 'actions/', 'fixtures/' folders.
                   Defaults to current working directory.

    Returns:
        Dictionary with 'journeys', 'actions', and 'fixtures' keys.
    """
    return {
        "journeys": discover_from_journeys_dir(base_path),
        "actions": discover_from_actions_dir(base_path),
        "fixtures": discover_from_fixtures_dir(base_path),
    }
