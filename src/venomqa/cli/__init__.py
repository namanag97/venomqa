"""VenomQA CLI - Command line interface for VenomQA."""

from venomqa.cli.commands import cli
from venomqa.cli.doctor import HealthCheck, doctor, get_health_checks, run_health_checks
from venomqa.cli.output import CLIOutput, ProgressConfig, create_output


def main() -> None:
    """Main entry point for the venomqa CLI."""
    cli()


# Lazy import for watch module to avoid import errors when watchdog is not installed
def __getattr__(name: str):
    if name in ("run_watch_mode", "WatchRunner", "FileWatcher", "DependencyAnalyzer"):
        from venomqa.cli.watch import (
            DependencyAnalyzer,
            FileWatcher,
            WatchRunner,
            run_watch_mode,
        )
        return {
            "run_watch_mode": run_watch_mode,
            "WatchRunner": WatchRunner,
            "FileWatcher": FileWatcher,
            "DependencyAnalyzer": DependencyAnalyzer,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "main",
    "cli",
    "CLIOutput",
    "ProgressConfig",
    "create_output",
    "run_watch_mode",
    "WatchRunner",
    "FileWatcher",
    "DependencyAnalyzer",
    "doctor",
    "HealthCheck",
    "get_health_checks",
    "run_health_checks",
]
