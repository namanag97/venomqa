"""CLI commands for journey run history management.

This module provides CLI commands for viewing and managing journey run history,
including listing past runs, viewing run details, comparing runs, and cleanup.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from typing import Any

import click


@click.group()
@click.pass_context
def history(ctx: click.Context) -> None:
    """View and manage journey run history."""
    pass


@history.command("list")
@click.option("--limit", "-n", default=20, help="Number of runs to show")
@click.option("--journey", "-j", "journey_name", help="Filter by journey name")
@click.option("--status", "-s", type=click.Choice(["passed", "failed"]), help="Filter by status")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.pass_context
def history_list(
    ctx: click.Context,
    limit: int,
    journey_name: str | None,
    status: str | None,
    output_format: str,
) -> None:
    """List past journey runs.

    Shows recent journey executions with their status, duration, and summary.

    Examples:
        venomqa history list
        venomqa history list --limit 50
        venomqa history list --journey checkout_flow
        venomqa history list --status failed
    """
    from venomqa.storage import ResultsRepository
    from venomqa.cli.output import CLIOutput, ProgressConfig

    config: dict[str, Any] = ctx.obj.get("config", {})
    db_url = config.get("results_database", "sqlite:///venomqa_results.db")
    output = CLIOutput(ProgressConfig())

    try:
        repo = ResultsRepository(db_url)
        repo.initialize()
        from venomqa.storage.models import RunStatus

        status_filter = RunStatus(status) if status else None
        runs = repo.list_runs(limit=limit, journey_name=journey_name, status=status_filter)

        if not runs:
            output.console.print("[yellow]No runs found.[/yellow]")
            return

        if output_format == "json":
            import json

            click.echo(json.dumps([run.to_dict() for run in runs], indent=2, default=str))
        else:
            output.console.print(f"\n[bold]Journey Run History[/bold] (showing {len(runs)} runs)\n")
            from rich.table import Table

            table = Table(show_header=True, header_style="bold")
            table.add_column("ID", style="dim", width=12)
            table.add_column("Journey")
            table.add_column("Status")
            table.add_column("Steps")
            table.add_column("Duration")
            table.add_column("Started At")

            for run in runs:
                status_style = "green" if run.status.value == "passed" else "red"
                steps_str = f"{run.passed_steps}/{run.total_steps}"
                duration_str = f"{run.duration_ms:.0f}ms"
                started_str = (
                    run.started_at.strftime("%Y-%m-%d %H:%M") if run.started_at else "N/A"
                )
                table.add_row(
                    run.id[:12] if run.id else "N/A",
                    run.journey_name,
                    f"[{status_style}]{run.status.value}[/{status_style}]",
                    steps_str,
                    duration_str,
                    started_str,
                )
            output.console.print(table)
        repo.close()
    except Exception as e:
        output.console.print(f"[red]Error loading history: {e}[/red]", err=True)
        sys.exit(1)


@history.command("show")
@click.argument("run_id")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.pass_context
def history_show(ctx: click.Context, run_id: str, output_format: str) -> None:
    """Show details of a specific run.

    Displays comprehensive information about a journey run including
    all step results and issues.

    Examples:
        venomqa history show abc123def456
    """
    from venomqa.storage import ResultsRepository
    from venomqa.cli.output import CLIOutput, ProgressConfig

    config: dict[str, Any] = ctx.obj.get("config", {})
    db_url = config.get("results_database", "sqlite:///venomqa_results.db")
    output = CLIOutput(ProgressConfig())

    try:
        repo = ResultsRepository(db_url)
        repo.initialize()
        runs = repo.list_runs(limit=100)
        matching_run = None
        for run in runs:
            if run.id.startswith(run_id):
                matching_run = run
                break

        if not matching_run:
            output.console.print(f"[red]Run not found: {run_id}[/red]", err=True)
            sys.exit(1)

        steps = repo.get_step_results(matching_run.id)
        issues = repo.get_issues(matching_run.id)

        if output_format == "json":
            import json

            data = matching_run.to_dict()
            data["steps"] = [
                {
                    "step_name": s.step_name,
                    "status": s.status,
                    "duration_ms": s.duration_ms,
                    "error": s.error,
                }
                for s in steps
            ]
            data["issues"] = [
                {"severity": i.severity, "step_name": i.step_name, "message": i.message}
                for i in issues
            ]
            click.echo(json.dumps(data, indent=2, default=str))
        else:
            status_style = "green" if matching_run.status.value == "passed" else "red"
            output.console.print(f"\n[bold]Journey Run Details[/bold]\n")
            output.console.print(f"  [bold]ID:[/bold] {matching_run.id}")
            output.console.print(f"  [bold]Journey:[/bold] {matching_run.journey_name}")
            output.console.print(
                f"  [bold]Status:[/bold] [{status_style}]{matching_run.status.value}[/{status_style}]"
            )
            output.console.print(f"  [bold]Duration:[/bold] {matching_run.duration_ms:.0f}ms")
            output.console.print(f"  [bold]Started:[/bold] {matching_run.started_at}")
            output.console.print(f"  [bold]Finished:[/bold] {matching_run.finished_at}")
            output.console.print(
                f"  [bold]Steps:[/bold] {matching_run.passed_steps}/{matching_run.total_steps} passed"
            )

            if steps:
                output.console.print(f"\n[bold]Step Results:[/bold]")
                from rich.table import Table

                table = Table(show_header=True, header_style="bold")
                table.add_column("#", width=3)
                table.add_column("Step Name")
                table.add_column("Status")
                table.add_column("Duration")
                table.add_column("Error")

                for i, step in enumerate(steps, 1):
                    step_status_style = "green" if step.status == "passed" else "red"
                    error_str = (
                        (step.error[:50] + "...")
                        if step.error and len(step.error) > 50
                        else (step.error or "")
                    )
                    table.add_row(
                        str(i),
                        step.step_name,
                        f"[{step_status_style}]{step.status}[/{step_status_style}]",
                        f"{step.duration_ms:.0f}ms",
                        error_str,
                    )
                output.console.print(table)

            if issues:
                output.console.print(f"\n[bold]Issues ({len(issues)}):[/bold]")
                for issue in issues:
                    sev_style = "red" if issue.severity in ("critical", "high") else "yellow"
                    output.console.print(
                        f"  [{sev_style}][{issue.severity}][/{sev_style}] {issue.step_name}: {issue.message}"
                    )
        repo.close()
    except Exception as e:
        output.console.print(f"[red]Error: {e}[/red]", err=True)
        sys.exit(1)


@history.command("compare")
@click.argument("run1_id")
@click.argument("run2_id")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.pass_context
def history_compare(ctx: click.Context, run1_id: str, run2_id: str, output_format: str) -> None:
    """Compare two journey runs.

    Shows differences between two runs including status changes,
    duration differences, and issue changes.

    Examples:
        venomqa history compare abc123 def456
    """
    from venomqa.storage import ResultsRepository
    from venomqa.cli.output import CLIOutput, ProgressConfig

    config: dict[str, Any] = ctx.obj.get("config", {})
    db_url = config.get("results_database", "sqlite:///venomqa_results.db")
    output = CLIOutput(ProgressConfig())

    try:
        repo = ResultsRepository(db_url)
        repo.initialize()
        runs = repo.list_runs(limit=100)
        resolved_id1 = None
        resolved_id2 = None

        for run in runs:
            if run.id.startswith(run1_id):
                resolved_id1 = run.id
            if run.id.startswith(run2_id):
                resolved_id2 = run.id

        if not resolved_id1:
            output.console.print(f"[red]Run not found: {run1_id}[/red]", err=True)
            sys.exit(1)
        if not resolved_id2:
            output.console.print(f"[red]Run not found: {run2_id}[/red]", err=True)
            sys.exit(1)

        comparison = repo.compare_runs(resolved_id1, resolved_id2)

        if "error" in comparison:
            output.console.print(f"[red]{comparison['error']}[/red]", err=True)
            sys.exit(1)

        if output_format == "json":
            import json

            click.echo(json.dumps(comparison, indent=2, default=str))
        else:
            output.console.print(f"\n[bold]Run Comparison[/bold]\n")
            run1 = comparison["run1"]
            run2 = comparison["run2"]
            r1_style = "green" if run1["status"] == "passed" else "red"
            r2_style = "green" if run2["status"] == "passed" else "red"
            output.console.print(
                f"  [bold]Run 1:[/bold] {run1['id'][:12]} - [{r1_style}]{run1['status']}[/{r1_style}] - {run1['duration_ms']:.0f}ms"
            )
            output.console.print(
                f"  [bold]Run 2:[/bold] {run2['id'][:12]} - [{r2_style}]{run2['status']}[/{r2_style}] - {run2['duration_ms']:.0f}ms"
            )

            duration_diff = comparison["duration_diff_ms"]
            duration_pct = comparison["duration_diff_pct"]
            diff_style = "red" if duration_diff > 0 else "green"
            sign = "+" if duration_diff > 0 else ""
            output.console.print(
                f"\n  [bold]Duration Change:[/bold] [{diff_style}]{sign}{duration_diff:.0f}ms ({sign}{duration_pct:.1f}%)[/{diff_style}]"
            )

            if comparison.get("regression"):
                output.console.print(
                    "\n  [bold red]REGRESSION DETECTED[/bold red]: Run 1 passed but Run 2 failed"
                )
            elif comparison.get("improvement"):
                output.console.print(
                    "\n  [bold green]IMPROVEMENT[/bold green]: Run 1 failed but Run 2 passed"
                )

            step_changes = [
                s
                for s in comparison.get("step_comparison", [])
                if s.get("status_changed") or s.get("added") or s.get("removed")
            ]
            if step_changes:
                output.console.print(f"\n[bold]Step Changes ({len(step_changes)}):[/bold]")
                for step in step_changes:
                    if step.get("added"):
                        output.console.print(f"  [green]+[/green] {step['step_name']} (new)")
                    elif step.get("removed"):
                        output.console.print(f"  [red]-[/red] {step['step_name']} (removed)")
                    elif step.get("status_changed"):
                        output.console.print(
                            f"  [yellow]~[/yellow] {step['step_name']}: {step['run1_status']} -> {step['run2_status']}"
                        )

            resolved = comparison.get("resolved_issues", [])
            new_issues = comparison.get("new_issues", [])

            if resolved:
                output.console.print(f"\n[bold green]Resolved Issues ({len(resolved)}):[/bold green]")
                for issue in resolved:
                    msg = (
                        issue["message"][:60] + "..."
                        if len(issue["message"]) > 60
                        else issue["message"]
                    )
                    output.console.print(f"  [green]-[/green] {issue['step_name']}: {msg}")

            if new_issues:
                output.console.print(f"\n[bold red]New Issues ({len(new_issues)}):[/bold red]")
                for issue in new_issues:
                    msg = (
                        issue["message"][:60] + "..."
                        if len(issue["message"]) > 60
                        else issue["message"]
                    )
                    output.console.print(f"  [red]+[/red] {issue['step_name']}: {msg}")

        repo.close()
    except Exception as e:
        output.console.print(f"[red]Error: {e}[/red]", err=True)
        sys.exit(1)


@history.command("stats")
@click.option("--days", "-d", default=30, help="Number of days to analyze")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.pass_context
def history_stats(ctx: click.Context, days: int, output_format: str) -> None:
    """Show statistics for journey runs.

    Displays aggregate statistics including pass rates, average duration,
    and trend data.

    Examples:
        venomqa history stats
        venomqa history stats --days 7
    """
    from venomqa.storage import ResultsRepository
    from venomqa.cli.output import CLIOutput, ProgressConfig

    config: dict[str, Any] = ctx.obj.get("config", {})
    db_url = config.get("results_database", "sqlite:///venomqa_results.db")
    output = CLIOutput(ProgressConfig())

    try:
        repo = ResultsRepository(db_url)
        repo.initialize()
        stats = repo.get_dashboard_stats(days=days)

        if output_format == "json":
            import json

            data = {
                "total_journeys": stats.total_journeys,
                "total_runs": stats.total_runs,
                "total_passed": stats.total_passed,
                "total_failed": stats.total_failed,
                "pass_rate": stats.pass_rate,
                "avg_duration_ms": stats.avg_duration_ms,
                "min_duration_ms": stats.min_duration_ms,
                "max_duration_ms": stats.max_duration_ms,
                "total_issues": stats.total_issues,
                "critical_issues": stats.critical_issues,
                "high_issues": stats.high_issues,
                "top_failing_journeys": stats.top_failing_journeys,
                "slowest_journeys": stats.slowest_journeys,
            }
            click.echo(json.dumps(data, indent=2))
        else:
            output.console.print(f"\n[bold]Journey Statistics[/bold] (last {days} days)\n")
            pass_style = (
                "green" if stats.pass_rate >= 80 else ("yellow" if stats.pass_rate >= 50 else "red")
            )
            output.console.print(f"  [bold]Total Runs:[/bold] {stats.total_runs}")
            output.console.print(f"  [bold]Passed:[/bold] [green]{stats.total_passed}[/green]")
            output.console.print(f"  [bold]Failed:[/bold] [red]{stats.total_failed}[/red]")
            output.console.print(
                f"  [bold]Pass Rate:[/bold] [{pass_style}]{stats.pass_rate:.1f}%[/{pass_style}]"
            )
            output.console.print(f"\n  [bold]Avg Duration:[/bold] {stats.avg_duration_ms:.0f}ms")
            output.console.print(f"  [bold]Min Duration:[/bold] {stats.min_duration_ms:.0f}ms")
            output.console.print(f"  [bold]Max Duration:[/bold] {stats.max_duration_ms:.0f}ms")

            if stats.total_issues > 0:
                output.console.print(f"\n[bold]Issues:[/bold]")
                output.console.print(f"  Total: {stats.total_issues}")
                if stats.critical_issues:
                    output.console.print(f"  [red]Critical: {stats.critical_issues}[/red]")
                if stats.high_issues:
                    output.console.print(f"  [red]High: {stats.high_issues}[/red]")

            if stats.top_failing_journeys:
                output.console.print(f"\n[bold]Top Failing Journeys:[/bold]")
                for name, count in stats.top_failing_journeys[:5]:
                    output.console.print(f"  [red]{name}[/red]: {count} failures")

            if stats.slowest_journeys:
                output.console.print(f"\n[bold]Slowest Journeys:[/bold]")
                for name, duration in stats.slowest_journeys[:5]:
                    output.console.print(f"  {name}: {duration:.0f}ms avg")

        repo.close()
    except Exception as e:
        output.console.print(f"[red]Error: {e}[/red]", err=True)
        sys.exit(1)


@history.command("cleanup")
@click.option("--days", "-d", default=90, help="Delete runs older than this many days")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def history_cleanup(ctx: click.Context, days: int, dry_run: bool, yes: bool) -> None:
    """Clean up old journey runs.

    Deletes journey runs older than the specified number of days.

    Examples:
        venomqa history cleanup --days 30
        venomqa history cleanup --dry-run
    """
    from venomqa.storage import ResultsRepository
    from venomqa.cli.output import CLIOutput, ProgressConfig

    config: dict[str, Any] = ctx.obj.get("config", {})
    db_url = config.get("results_database", "sqlite:///venomqa_results.db")
    output = CLIOutput(ProgressConfig())

    try:
        repo = ResultsRepository(db_url)
        repo.initialize()
        cutoff = datetime.now() - timedelta(days=days)
        runs = repo.list_runs(limit=10000)
        old_runs = [r for r in runs if r.started_at and r.started_at < cutoff]

        if not old_runs:
            output.console.print(f"[green]No runs older than {days} days found.[/green]")
            repo.close()
            return

        output.console.print(f"\nFound [bold]{len(old_runs)}[/bold] runs older than {days} days.")

        if dry_run:
            output.console.print("\n[yellow]Dry run - no changes made.[/yellow]")
            output.console.print("\nRuns that would be deleted:")
            for run in old_runs[:10]:
                output.console.print(
                    f"  - {run.id[:12]} ({run.journey_name}) from {run.started_at}"
                )
            if len(old_runs) > 10:
                output.console.print(f"  ... and {len(old_runs) - 10} more")
        else:
            if not yes:
                if not click.confirm(f"Delete {len(old_runs)} runs?"):
                    output.console.print("[yellow]Cancelled.[/yellow]")
                    repo.close()
                    return
            deleted = repo.delete_old_runs(days=days)
            output.console.print(f"[green]Deleted {deleted} runs.[/green]")

        repo.close()
    except Exception as e:
        output.console.print(f"[red]Error: {e}[/red]", err=True)
        sys.exit(1)
