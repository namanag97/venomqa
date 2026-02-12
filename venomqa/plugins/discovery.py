"""Journey discovery via decorators and file scanning."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path

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
