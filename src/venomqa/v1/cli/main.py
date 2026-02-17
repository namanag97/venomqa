"""CLI commands for VenomQA v1."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

from venomqa.v1.reporters.console import ConsoleReporter
from venomqa.v1.reporters.html_trace import HTMLTraceReporter
from venomqa.v1.reporters.json import JSONReporter
from venomqa.v1.reporters.junit import JUnitReporter
from venomqa.v1.reporters.markdown import MarkdownReporter


def _validate_coverage_target(value: str) -> float:
    """Validate coverage target is between 0.0 and 1.0."""
    try:
        f = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid float value: {value!r}")
    if not 0.0 <= f <= 1.0:
        raise argparse.ArgumentTypeError(f"coverage-target must be between 0.0 and 1.0, got {f}")
    return f


def _validate_max_steps(value: str) -> int:
    """Validate max steps is positive."""
    try:
        i = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid int value: {value!r}")
    if i <= 0:
        raise argparse.ArgumentTypeError(f"max-steps must be positive, got {i}")
    return i


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
    explore_parser.add_argument(
        "--strategy",
        choices=["bfs", "dfs", "random", "coverage", "weighted", "dimension"],
        default="bfs",
        help=(
            "Exploration strategy: "
            "bfs (breadth-first, default), "
            "dfs (depth-first), "
            "random (random order), "
            "coverage (least-tried actions first), "
            "weighted (probability weights per action), "
            "dimension (hypergraph novelty, explores unseen dimension combos)"
        ),
    )
    explore_parser.add_argument("--max-steps", type=_validate_max_steps, default=1000)
    explore_parser.add_argument(
        "--coverage-target",
        type=_validate_coverage_target,
        default=None,
        metavar="0.0-1.0",
        help="Stop exploration once action coverage reaches this fraction (e.g. 0.8 = 80%%)",
    )
    explore_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Print progress every 100 steps (step count, states, coverage, violations)",
    )
    explore_parser.add_argument("--format", "-f", choices=["console", "json", "markdown", "junit", "html"], default="console")
    explore_parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    # validate command
    validate_parser = subparsers.add_parser("validate", help="Validate journey syntax")
    validate_parser.add_argument("journey_file", help="Path to journey definition file")

    # scaffold command
    scaffold_parser = subparsers.add_parser(
        "scaffold", help="Generate VenomQA action files from a spec"
    )
    scaffold_sub = scaffold_parser.add_subparsers(dest="scaffold_command")

    openapi_parser = scaffold_sub.add_parser(
        "openapi", help="Scaffold from an OpenAPI 3.x spec (YAML or JSON)"
    )
    openapi_parser.add_argument("spec_file", help="Path to the OpenAPI spec file (.yaml/.yml/.json)")
    openapi_parser.add_argument(
        "--output", "-o",
        help="Output file for generated code (default: stdout)",
    )
    openapi_parser.add_argument(
        "--base-url", "-u",
        default="http://localhost:8000",
        help="Base URL of the API (used in generated code)",
    )
    openapi_parser.add_argument(
        "--name", "-n",
        default="generated_journey",
        help="Journey name in generated code",
    )

    # record command
    record_parser = subparsers.add_parser(
        "record", help="Proxy HTTP calls and generate a Journey skeleton"
    )
    record_parser.add_argument("journey_file", help="Path to existing journey to replay (or '-' to skip)")
    record_parser.add_argument("--base-url", "-u", required=True, help="Base URL of API to record")
    record_parser.add_argument("--output", "-o", help="Output file for generated code (default: stdout)")
    record_parser.add_argument("--name", default="recorded_journey", help="Journey name in generated code")

    # replay command
    replay_parser = subparsers.add_parser(
        "replay", help="Re-run a violation's reproduction path from a report JSON"
    )
    replay_parser.add_argument("report_file", help="Path to a JSONReporter output file")
    replay_parser.add_argument(
        "--violation", "-V",
        type=int,
        default=0,
        metavar="INDEX",
        help="Index into unique_violations (0-based, default: 0 = first/shortest)",
    )
    replay_parser.add_argument("--base-url", "-u", required=True, help="Base URL of the API")
    replay_parser.add_argument(
        "--actions", "-a",
        required=True,
        metavar="FILE",
        help="Python file that defines the action functions (same file used for the original run)",
    )
    replay_parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        default=False,
        help="Pause after each step and wait for Enter",
    )

    parsed = parser.parse_args(args)

    if parsed.command == "explore":
        return cmd_explore(parsed)
    elif parsed.command == "validate":
        return cmd_validate(parsed)
    elif parsed.command == "record":
        return cmd_record(parsed)
    elif parsed.command == "scaffold":
        return cmd_scaffold(parsed)
    elif parsed.command == "replay":
        return cmd_replay(parsed)
    else:
        parser.print_help()
        return 1


def cmd_explore(args: Any) -> int:
    """Run exploration command."""
    from venomqa.v1 import BFS, CoverageGuided, DFS, Random, Weighted, explore
    from venomqa.v1.agent.dimension_strategy import DimensionNoveltyStrategy

    # Load journey from file
    journey = load_journey(args.journey_file)
    if journey is None:
        print(f"Error: Could not load journey from {args.journey_file}", file=sys.stderr)
        return 1

    # Select strategy
    strategy_map = {
        "bfs": BFS(),
        "dfs": DFS(),
        "random": Random(),
        "coverage": CoverageGuided(),
        "weighted": Weighted(),
        "dimension": DimensionNoveltyStrategy(),
    }
    strategy = strategy_map[args.strategy]

    # Run exploration
    result = explore(
        base_url=args.base_url,
        journey=journey,
        db_url=args.db_url,
        redis_url=args.redis_url,
        strategy=strategy,
        max_steps=args.max_steps,
        coverage_target=getattr(args, "coverage_target", None),
        progress_every=100 if getattr(args, "verbose", False) else 0,
    )

    # Format output
    if args.format == "console":
        if args.output:
            # Write console output to file
            import io
            buffer = io.StringIO()
            reporter = ConsoleReporter(file=buffer, color=False)
            reporter.report(result)
            _write_output(buffer.getvalue(), args.output)
        else:
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
    elif args.format == "html":
        reporter = HTMLTraceReporter()
        output = reporter.report(result)
        _write_output(output, args.output)

    return 0 if result.success else 1


def cmd_validate(args: Any) -> int:
    """Validate journey syntax."""
    from venomqa.v1.dsl.compiler import compile

    journey = load_journey(args.journey_file)
    if journey is None:
        print(
            f"Error: No Journey found in {args.journey_file}.\n"
            "  venomqa validate only works with DSL-style Journey files.\n"
            "  Files using the flat Action/Agent API don't need validation —\n"
            "  run them directly with: venomqa explore <file> --base-url <url>",
            file=sys.stderr,
        )
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


def cmd_scaffold(args: Any) -> int:
    """Scaffold command dispatcher."""
    if not hasattr(args, "scaffold_command") or args.scaffold_command is None:
        print("Usage: venomqa scaffold openapi <spec_file>", file=sys.stderr)
        return 1
    if args.scaffold_command == "openapi":
        return cmd_scaffold_openapi(args)
    print(f"Unknown scaffold subcommand: {args.scaffold_command}", file=sys.stderr)
    return 1


def cmd_scaffold_openapi(args: Any) -> int:
    """Generate VenomQA actions from an OpenAPI 3.x spec."""
    from venomqa.v1.cli.scaffold import generate_actions_code, load_spec, parse_openapi

    try:
        spec = load_spec(args.spec_file)
    except (FileNotFoundError, ValueError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        endpoints = parse_openapi(spec)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    base_url = getattr(args, "base_url", "http://localhost:8000")
    name = getattr(args, "name", "generated_journey")

    code = generate_actions_code(endpoints, base_url=base_url, journey_name=name)
    _write_output(code, getattr(args, "output", None))

    n = len(endpoints)
    if getattr(args, "output", None):
        print(f"Scaffolded {n} action(s) → {args.output}")
    return 0


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


def cmd_replay(args: Any) -> int:
    """Re-run a violation reproduction path step-by-step."""
    import json as _json
    from pathlib import Path as _Path

    from venomqa.v1.adapters.http import HttpClient
    from venomqa.v1.core.context import Context

    # Load report
    report_path = _Path(args.report_file)
    if not report_path.exists():
        print(f"Error: report file not found: {report_path}", file=sys.stderr)
        return 1
    try:
        report = _json.loads(report_path.read_text())
    except Exception as exc:
        print(f"Error: could not parse report JSON: {exc}", file=sys.stderr)
        return 1

    # Pull unique_violations (preferred — shortest paths) or fall back to violations
    all_violations = report.get("unique_violations") or report.get("violations", [])
    if not all_violations:
        print("No violations found in report.", file=sys.stderr)
        return 1

    idx = args.violation
    if idx >= len(all_violations):
        print(
            f"Error: violation index {idx} out of range "
            f"(report has {len(all_violations)} unique violation(s)).",
            file=sys.stderr,
        )
        return 1

    violation = all_violations[idx]
    path_actions: list[str] = violation.get("reproduction_path", [])
    if not path_actions:
        print("Violation has an empty reproduction path — nothing to replay.", file=sys.stderr)
        return 1

    # Load actions from the actions file
    actions_module = _load_module(args.actions)
    if actions_module is None:
        print(f"Error: could not load actions from {args.actions}", file=sys.stderr)
        return 1

    # Build name→callable map from any Action objects or plain functions in the module
    from venomqa.v1.core.action import Action as _Action
    action_map: dict[str, Any] = {}
    for attr_name in dir(actions_module):
        obj = getattr(actions_module, attr_name)
        if isinstance(obj, _Action):
            action_map[obj.name] = obj
        elif callable(obj) and attr_name in path_actions:
            action_map[attr_name] = obj

    missing = [name for name in path_actions if name not in action_map]
    if missing:
        print(
            f"Error: action(s) not found in {args.actions}: {missing}\n"
            "Make sure the file defines Action objects or functions with matching names.",
            file=sys.stderr,
        )
        return 1

    # Print preamble
    print(f"\n=== VenomQA Replay ===")
    print(f"Violation #{idx}: [{violation.get('severity','?').upper()}] {violation.get('invariant','?')}")
    print(f"Message:  {violation.get('message','')}")
    print(f"Path:     {' -> '.join(path_actions)}")
    print(f"Target:   {args.base_url}")
    print(f"Steps:    {len(path_actions)}")
    print()

    api = HttpClient(args.base_url)
    context = Context()
    interactive = getattr(args, "interactive", False)

    for step_num, action_name in enumerate(path_actions, 1):
        action_obj = action_map[action_name]
        is_last = step_num == len(path_actions)

        print(f"--- Step {step_num}/{len(path_actions)}: {action_name} ---")

        # Execute
        if isinstance(action_obj, _Action):
            result = action_obj.invoke(api, context)
        else:
            # plain function
            import inspect
            sig = inspect.signature(action_obj)
            if len(sig.parameters) >= 2:
                result = action_obj(api, context)
            else:
                result = action_obj(api)

        # Print request / response
        if hasattr(result, "request") and result.request:
            req = result.request
            print(f"  Request:  {req.method} {req.url}")
            if req.body:
                body_str = repr(req.body)[:200]
                print(f"  Req body: {body_str}")
        if hasattr(result, "response") and result.response:
            resp = result.response
            status_label = "OK" if resp.ok else "FAIL"
            print(f"  Response: HTTP {resp.status_code} ({status_label})")
            if resp.body is not None:
                body_str = repr(resp.body)[:300]
                print(f"  Res body: {body_str}")
        elif hasattr(result, "error") and result.error:
            print(f"  Error:    {result.error}")

        if is_last:
            print()
            print(f"[Replay complete — violation should have triggered on this step]")
        elif interactive:
            try:
                input("\n  Press Enter for next step (Ctrl-C to quit)...")
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                return 0
        print()

    return 0


def _load_module(path: str) -> Any:
    """Load a Python module from a file path."""
    import importlib.util as _ilu
    p = Path(path)
    if not p.exists():
        return None
    spec = _ilu.spec_from_file_location("_replay_actions", p)
    if spec is None or spec.loader is None:
        return None
    module = _ilu.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    """Write content to file or stdout.

    Auto-creates parent directories if they don't exist.
    Prints errors to stderr instead of raising exceptions.
    """
    if path:
        try:
            output_path = Path(path)
            # Create parent directories if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content)
        except PermissionError:
            print(f"Error: Permission denied writing to {path}", file=sys.stderr)
        except IsADirectoryError:
            print(f"Error: {path} is a directory, not a file", file=sys.stderr)
        except OSError as e:
            print(f"Error writing to {path}: {e}", file=sys.stderr)
    else:
        print(content)


def cli() -> None:
    """Entry point for console script."""
    sys.exit(main())


if __name__ == "__main__":
    cli()
