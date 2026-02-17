"""CLI commands for VenomQA v1."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

from venomqa.v1.reporters.console import ConsoleReporter
from venomqa.v1.reporters.json import JSONReporter
from venomqa.v1.reporters.junit import JUnitReporter
from venomqa.v1.reporters.markdown import MarkdownReporter


def main(args: list[str] | None = None) -> int:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        prog="venomqa",
        description="VenomQA v1 - Stateful exploration testing",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # explore command
    explore_parser = subparsers.add_parser("explore", help="Run exploration")
    explore_parser.add_argument("journey_file", help="Path to journey definition file")
    explore_parser.add_argument("--base-url", "-u", required=True, help="Base URL of API")
    explore_parser.add_argument("--db-url", help="PostgreSQL connection string")
    explore_parser.add_argument("--redis-url", help="Redis connection string")
    explore_parser.add_argument("--strategy", choices=["bfs", "dfs", "random"], default="bfs")
    explore_parser.add_argument("--max-steps", type=int, default=1000)
    explore_parser.add_argument("--format", "-f", choices=["console", "json", "markdown", "junit"], default="console")
    explore_parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    # validate command
    validate_parser = subparsers.add_parser("validate", help="Validate journey syntax")
    validate_parser.add_argument("journey_file", help="Path to journey definition file")

    # record command
    record_parser = subparsers.add_parser(
        "record", help="Proxy HTTP calls and generate a Journey skeleton"
    )
    record_parser.add_argument("journey_file", help="Path to existing journey to replay (or '-' to skip)")
    record_parser.add_argument("--base-url", "-u", required=True, help="Base URL of API to record")
    record_parser.add_argument("--output", "-o", help="Output file for generated code (default: stdout)")
    record_parser.add_argument("--name", default="recorded_journey", help="Journey name in generated code")

    parsed = parser.parse_args(args)

    if parsed.command == "explore":
        return cmd_explore(parsed)
    elif parsed.command == "validate":
        return cmd_validate(parsed)
    elif parsed.command == "record":
        return cmd_record(parsed)
    else:
        parser.print_help()
        return 1


def cmd_explore(args: Any) -> int:
    """Run exploration command."""
    from venomqa.v1 import BFS, DFS, Random, explore

    # Load journey from file
    journey = load_journey(args.journey_file)
    if journey is None:
        print(f"Error: Could not load journey from {args.journey_file}", file=sys.stderr)
        return 1

    # Select strategy
    strategy_map = {"bfs": BFS(), "dfs": DFS(), "random": Random()}
    strategy = strategy_map[args.strategy]

    # Run exploration
    result = explore(
        base_url=args.base_url,
        journey=journey,
        db_url=args.db_url,
        redis_url=args.redis_url,
        strategy=strategy,
        max_steps=args.max_steps,
    )

    # Format output
    if args.format == "console":
        reporter = ConsoleReporter()
        reporter.report(result)
    elif args.format == "json":
        reporter = JSONReporter()
        output = reporter.report(result)
        _write_output(output, args.output)
    elif args.format == "markdown":
        reporter = MarkdownReporter()
        output = reporter.report(result)
        _write_output(output, args.output)
    elif args.format == "junit":
        reporter = JUnitReporter()
        output = reporter.report(result)
        _write_output(output, args.output)

    return 0 if result.success else 1


def cmd_validate(args: Any) -> int:
    """Validate journey syntax."""
    from venomqa.v1.dsl.compiler import compile

    journey = load_journey(args.journey_file)
    if journey is None:
        print(f"Error: Could not load journey from {args.journey_file}", file=sys.stderr)
        return 1

    try:
        compiled = compile(journey)
        print(f"Journey '{journey.name}' is valid")
        print(f"  Steps: {len(compiled.actions)}")
        print(f"  Checkpoints: {len(compiled.checkpoints)}")
        print(f"  Invariants: {len(compiled.invariants)}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_record(args: Any) -> int:
    """Record HTTP traffic from a journey replay and generate a new journey."""
    from venomqa.v1.adapters.http import HttpClient
    from venomqa.v1.recording import RequestRecorder, generate_journey_code

    api = HttpClient(args.base_url)
    recorder = RequestRecorder(api)

    if args.journey_file != "-":
        # Replay the journey so we capture real traffic
        journey = load_journey(args.journey_file)
        if journey is None:
            print(f"Error: Could not load journey from {args.journey_file}", file=sys.stderr)
            return 1

        from venomqa.v1.agent import Agent
        from venomqa.v1.dsl.compiler import compile
        from venomqa.v1.world import World

        compiled = compile(journey)
        world = World(api=recorder, systems={})
        agent = Agent(world=world, actions=compiled.actions, max_steps=len(compiled.actions) * 2)
        agent.explore()

    code = generate_journey_code(
        recorder.captured,
        journey_name=args.name,
        base_url=args.base_url,
    )
    _write_output(code, getattr(args, "output", None))
    return 0


def load_journey(path: str) -> Any:
    """Load a journey from a Python file."""
    p = Path(path)
    if not p.exists():
        return None

    spec = importlib.util.spec_from_file_location("journey_module", p)
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Look for 'journey' attribute
    if hasattr(module, "journey"):
        return module.journey

    # Look for any Journey instance
    from venomqa.v1 import Journey
    for attr in dir(module):
        obj = getattr(module, attr)
        if isinstance(obj, Journey):
            return obj

    return None


def _write_output(content: str, path: str | None) -> None:
    """Write content to file or stdout."""
    if path:
        Path(path).write_text(content)
    else:
        print(content)


def cli() -> None:
    """Entry point for console script."""
    sys.exit(main())


if __name__ == "__main__":
    cli()
