"""CLI commands for VenomQA."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import click

from venomqa.config import QAConfig, load_config
from venomqa.runner import JourneyRunner


def setup_logging(verbose: bool) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def discover_journeys() -> dict[str, Any]:
    """Discover available journeys from the journeys directory."""
    journeys: dict[str, Any] = {}
    journeys_dir = Path("journeys")

    if not journeys_dir.exists():
        return journeys

    for journey_file in journeys_dir.glob("*.py"):
        if journey_file.name.startswith("_"):
            continue
        journey_name = journey_file.stem
        journeys[journey_name] = {
            "name": journey_name,
            "path": str(journey_file),
        }

    return journeys


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.option("--config", "-c", type=click.Path(exists=True), help="Path to config file")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, config: str | None) -> None:
    """VenomQA - Stateful Journey QA Framework."""
    ctx.ensure_object(dict)

    config_obj = load_config(config)
    if verbose:
        config_obj.verbose = True

    ctx.obj["config"] = config_obj
    ctx.obj["verbose"] = verbose

    setup_logging(verbose)


@cli.command()
@click.argument("journey_names", nargs=-1)
@click.option("--no-infra", is_flag=True, help="Skip infrastructure setup/teardown")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.option("--fail-fast", is_flag=True, help="Stop on first failure")
@click.pass_context
def run(
    ctx: click.Context,
    journey_names: tuple[str, ...],
    no_infra: bool,
    output_format: str,
    fail_fast: bool,
) -> None:
    """Run journeys (optionally filtered by name).

    If no journey names are provided, runs all discovered journeys.
    """
    config: QAConfig = ctx.obj["config"]
    config.fail_fast = fail_fast

    journeys = discover_journeys()

    if not journeys:
        click.echo("No journeys found. Create journeys in the 'journeys/' directory.", err=True)
        sys.exit(1)

    to_run = list(journey_names) if journey_names else list(journeys.keys())

    for name in to_run:
        if name not in journeys:
            click.echo(f"Journey not found: {name}", err=True)
            sys.exit(1)

    click.echo(f"Running {len(to_run)} journey(s)...")

    results: list[dict[str, Any]] = []
    all_passed = True

    for journey_name in to_run:
        click.echo(f"\n→ Running journey: {journey_name}")

        journey_data = _load_journey(journey_name, journeys[journey_name]["path"])
        if journey_data is None:
            click.echo(f"  ✗ Failed to load journey: {journey_name}", err=True)
            all_passed = False
            continue

        result = _execute_journey(journey_data, config, no_infra)
        results.append(result)

        if result.get("success"):
            click.echo(f"  ✓ Passed ({result.get('duration_ms', 0):.0f}ms)")
        else:
            click.echo(f"  ✗ Failed ({result.get('duration_ms', 0):.0f}ms)")
            all_passed = False

            if fail_fast:
                click.echo("\nFail-fast triggered, stopping.")
                break

    ctx.obj["last_results"] = results

    if output_format == "json":
        import json

        click.echo(json.dumps(results, indent=2, default=str))
    else:
        _print_summary(results)

    sys.exit(0 if all_passed else 1)


def _load_journey(name: str, path: str) -> Any:
    """Load a journey from a Python file."""
    import importlib.util

    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, "journey"):
            return module.journey
        elif hasattr(module, name):
            return getattr(module, name)

        for attr_name in dir(module):
            if not attr_name.startswith("_"):
                attr = getattr(module, attr_name)
                if hasattr(attr, "steps"):
                    return attr

        return None
    except Exception:
        logging.exception(f"Failed to load journey {name}")
        return None


def _execute_journey(journey: Any, config: QAConfig, no_infra: bool) -> dict[str, Any]:
    """Execute a journey and return results."""
    from venomqa import Client

    client = Client(base_url=config.base_url, timeout=config.timeout)

    runner = JourneyRunner(
        client=client,
        fail_fast=config.fail_fast,
        capture_logs=config.capture_logs,
        log_lines=config.log_lines,
    )

    try:
        result = runner.run(journey)
        return {
            "journey_name": result.journey_name,
            "success": result.success,
            "started_at": result.started_at.isoformat(),
            "finished_at": result.finished_at.isoformat(),
            "duration_ms": result.duration_ms,
            "step_count": len(result.step_results),
            "issues_count": len(result.issues),
            "issues": [
                {
                    "step": i.step,
                    "path": i.path,
                    "error": i.error,
                    "severity": i.severity.value
                    if hasattr(i.severity, "value")
                    else str(i.severity),
                }
                for i in result.issues
            ],
        }
    except Exception as e:
        logging.exception("Journey execution failed")
        return {
            "journey_name": journey.name if hasattr(journey, "name") else "unknown",
            "success": False,
            "error": str(e),
        }


def _print_summary(results: list[dict[str, Any]]) -> None:
    """Print a summary of results."""
    passed = sum(1 for r in results if r.get("success"))
    failed = len(results) - passed

    click.echo(f"\n{'=' * 50}")
    click.echo(f"Summary: {passed} passed, {failed} failed")

    if failed > 0:
        click.echo("\nFailed journeys:")
        for r in results:
            if not r.get("success"):
                click.echo(f"  - {r.get('journey_name', 'unknown')}")
                for issue in r.get("issues", []):
                    click.echo(f"    • {issue.get('step')}: {issue.get('error')}")


@cli.command("list")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.pass_context
def list_journeys(ctx: click.Context, output_format: str) -> None:
    """List available journeys."""
    journeys = discover_journeys()

    if not journeys:
        click.echo("No journeys found. Create journeys in the 'journeys/' directory.")
        return

    if output_format == "json":
        import json

        click.echo(json.dumps(journeys, indent=2))
    else:
        click.echo(f"Found {len(journeys)} journey(s):\n")
        for name, info in journeys.items():
            click.echo(f"  • {name} ({info['path']})")


@cli.command()
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["markdown", "json", "junit", "html"]),
    default="markdown",
    help="Report format",
)
@click.option(
    "--output", "-o", "output_path", type=click.Path(), default=None, help="Output file path"
)
@click.pass_context
def report(ctx: click.Context, output_format: str, output_path: str | None) -> None:
    """Generate report from last run."""
    results = ctx.obj.get("last_results")

    if not results:
        click.echo("No results available. Run a journey first with 'venomqa run'.", err=True)
        sys.exit(1)

    config: QAConfig = ctx.obj["config"]
    report_dir = Path(config.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    if output_path is None:
        ext_map = {"markdown": "md", "json": "json", "junit": "xml", "html": "html"}
        output_path = str(report_dir / f"report.{ext_map.get(output_format, 'txt')}")

    report_content = _generate_report(results, output_format)

    with open(output_path, "w") as f:
        f.write(report_content)

    click.echo(f"Report generated: {output_path}")


def _generate_report(results: list[dict[str, Any]], output_format: str) -> str:
    """Generate report in specified format."""
    if output_format == "json":
        import json

        return json.dumps(results, indent=2, default=str)

    if output_format == "junit":
        return _generate_junit_report(results)

    if output_format == "html":
        return _generate_html_report(results)

    return _generate_markdown_report(results)


def _generate_markdown_report(results: list[dict[str, Any]]) -> str:
    """Generate markdown report."""
    lines = ["# VenomQA Test Report\n"]
    lines.append(f"**Total Journeys**: {len(results)}")
    passed = sum(1 for r in results if r.get("success"))
    lines.append(f"**Passed**: {passed}")
    lines.append(f"**Failed**: {len(results) - passed}\n")

    for result in results:
        status = "✓" if result.get("success") else "✗"
        lines.append(f"## {status} {result.get('journey_name', 'unknown')}\n")
        lines.append(f"- **Duration**: {result.get('duration_ms', 0):.0f}ms")
        lines.append(f"- **Steps**: {result.get('step_count', 0)}")

        issues = result.get("issues", [])
        if issues:
            lines.append(f"- **Issues**: {len(issues)}\n")
            for issue in issues:
                lines.append(f"  - `{issue.get('step')}`: {issue.get('error')}")
        lines.append("")

    return "\n".join(lines)


def _generate_junit_report(results: list[dict[str, Any]]) -> str:
    """Generate JUnit XML report."""
    import xml.etree.ElementTree as ET

    testsuites = ET.Element("testsuites")
    testsuite = ET.SubElement(testsuites, "testsuite")
    testsuite.set("name", "VenomQA")
    testsuite.set("tests", str(len(results)))

    failures = sum(1 for r in results if not r.get("success"))
    testsuite.set("failures", str(failures))

    for result in results:
        testcase = ET.SubElement(testsuite, "testcase")
        testcase.set("name", result.get("journey_name", "unknown"))
        testcase.set("time", str(result.get("duration_ms", 0) / 1000))

        if not result.get("success"):
            failure = ET.SubElement(testcase, "failure")
            issues = result.get("issues", [])
            if issues:
                failure.set("message", issues[0].get("error", "Unknown error"))
                failure.text = "\n".join(f"{i.get('step')}: {i.get('error')}" for i in issues)

    return ET.tostring(testsuites, encoding="unicode")


def _generate_html_report(results: list[dict[str, Any]]) -> str:
    """Generate HTML report."""
    passed = sum(1 for r in results if r.get("success"))
    failed = len(results) - passed

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>VenomQA Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 40px; }}
        .summary {{ background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .passed {{ color: #22c55e; }}
        .failed {{ color: #ef4444; }}
        .journey {{ border: 1px solid #e5e5e5; padding: 16px; margin-bottom: 12px;
                    border-radius: 8px; }}
        .issue {{ background: #fef2f2; padding: 8px; margin-top: 8px; border-radius: 4px; }}
    </style>
</head>
<body>
    <h1>VenomQA Report</h1>
    <div class="summary">
        <strong>Total:</strong> {len(results)} |
        <span class="passed">Passed: {passed}</span> |
        <span class="failed">Failed: {failed}</span>
    </div>
"""

    for result in results:
        status_class = "passed" if result.get("success") else "failed"
        status_icon = "✓" if result.get("success") else "✗"
        html += f"""
    <div class="journey">
        <h3><span class="{status_class}">{status_icon}</span> \
{result.get("journey_name", "unknown")}</h3>
        <p>Duration: {result.get("duration_ms", 0):.0f}ms | Steps: {result.get("step_count", 0)}</p>
"""
        for issue in result.get("issues", []):
            html += f"""
        <div class="issue">
            <strong>{issue.get("step")}</strong>: {issue.get("error")}
        </div>
"""
        html += "    </div>"

    html += """
</body>
</html>"""
    return html
