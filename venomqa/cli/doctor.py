"""VenomQA Doctor - System health checks and diagnostics."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Callable, Tuple

import click
from rich.console import Console
from rich.table import Table

console = Console()


class HealthCheck:
    """A single health check with name, check function, and required flag."""

    def __init__(
        self,
        name: str,
        check_fn: Callable[[], Tuple[bool, str]],
        required: bool = True,
    ) -> None:
        """Initialize a health check.

        Args:
            name: Display name for the check.
            check_fn: Function that returns (success, message) tuple.
            required: Whether this check is required for VenomQA to function.
        """
        self.name = name
        self.check_fn = check_fn
        self.required = required

    def run(self) -> Tuple[bool, str]:
        """Run the health check and return (success, message)."""
        try:
            return self.check_fn()
        except Exception as e:
            return False, str(e)


def check_python_version() -> Tuple[bool, str]:
    """Check if Python version meets minimum requirements (>= 3.10)."""
    version = sys.version_info
    if version >= (3, 10):
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    return False, f"Python {version.major}.{version.minor} (requires >= 3.10)"


def check_docker() -> Tuple[bool, str]:
    """Check if Docker is installed and daemon is running."""
    if not shutil.which("docker"):
        return False, "Docker not found in PATH"

    result = subprocess.run(
        ["docker", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return False, "Docker check failed"

    version = result.stdout.strip()

    # Check if daemon is running
    ping = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        timeout=10,
    )
    if ping.returncode == 0:
        return True, version
    return False, "Docker installed but daemon not running"


def check_docker_compose() -> Tuple[bool, str]:
    """Check if Docker Compose is available (v2 or v1)."""
    # Try docker compose (v2)
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Try docker-compose (v1)
    if shutil.which("docker-compose"):
        try:
            result = subprocess.run(
                ["docker-compose", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return False, "Docker Compose not found"


def check_package(package: str) -> Tuple[bool, str]:
    """Check if a Python package is installed and return its version.

    Args:
        package: The import name of the package to check.

    Returns:
        Tuple of (success, message) indicating if package is installed.
    """
    try:
        mod = __import__(package)
        version = getattr(mod, "__version__", "installed")
        return True, f"{package} {version}"
    except ImportError:
        return False, f"{package} not installed"


def check_graphviz() -> Tuple[bool, str]:
    """Check if Graphviz is installed (optional, for journey visualization)."""
    if shutil.which("dot"):
        try:
            result = subprocess.run(
                ["dot", "-V"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # dot -V outputs to stderr
            version_info = result.stderr.strip() or result.stdout.strip()
            return True, f"graphviz available ({version_info})"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True, "graphviz available"
    return False, "graphviz not installed (optional, for journey visualization)"


def check_postgresql_client() -> Tuple[bool, str]:
    """Check if PostgreSQL client (psql) is available."""
    if shutil.which("psql"):
        try:
            result = subprocess.run(
                ["psql", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            version = result.stdout.strip()
            return True, f"psql available ({version})"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True, "psql available"
    return False, "psql not found (optional, for database state management)"


def check_git() -> Tuple[bool, str]:
    """Check if Git is installed (optional, for version tracking)."""
    if shutil.which("git"):
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return True, result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return True, "git available"
    return False, "git not found (optional)"


def check_redis_client() -> Tuple[bool, str]:
    """Check if Redis client is available."""
    # Check Python redis package
    try:
        import redis
        version = getattr(redis, "__version__", "installed")
        return True, f"redis-py {version}"
    except ImportError:
        pass

    # Check redis-cli
    if shutil.which("redis-cli"):
        return True, "redis-cli available"

    return False, "Redis client not found (optional, for cache state management)"


def check_disk_space() -> Tuple[bool, str]:
    """Check available disk space (recommend at least 5GB free)."""
    try:
        total, used, free = shutil.disk_usage("/")
        free_gb = free / (1024 ** 3)
        total_gb = total / (1024 ** 3)

        if free_gb >= 5:
            return True, f"{free_gb:.1f} GB free of {total_gb:.1f} GB"
        elif free_gb >= 1:
            return False, f"Low disk space: {free_gb:.1f} GB free (recommend 5GB+)"
        else:
            return False, f"Very low disk space: {free_gb:.1f} GB free"
    except Exception as e:
        return False, f"Could not check disk space: {e}"


def check_common_ports() -> Tuple[bool, str]:
    """Check if common testing ports are available or services are running."""
    import socket

    ports_info = []
    common_ports = [
        (5432, "PostgreSQL"),
        (6379, "Redis"),
        (8000, "API"),
    ]

    for port, service in common_ports:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            result = sock.connect_ex(("localhost", port))
            if result == 0:
                ports_info.append(f"{service}:{port}")
        except Exception:
            pass
        finally:
            sock.close()

    if ports_info:
        return True, f"Services detected: {', '.join(ports_info)}"
    return True, "No services detected on common ports"


def check_config_file() -> Tuple[bool, str]:
    """Check if a VenomQA configuration file exists."""
    from pathlib import Path

    config_files = [
        "venomqa.yaml",
        "venomqa.yml",
        ".venomqa.yaml",
        "config/venomqa.yaml",
    ]

    for config_file in config_files:
        if Path(config_file).exists():
            return True, f"Found {config_file}"

    return False, "No venomqa.yaml found (run 'venomqa init' to create one)"


def check_journeys_directory() -> Tuple[bool, str]:
    """Check if journeys directory exists with journey files."""
    from pathlib import Path

    journeys_dir = Path("journeys")

    if not journeys_dir.exists():
        return False, "journeys/ directory not found"

    journey_files = list(journeys_dir.glob("*.py"))
    journey_files = [f for f in journey_files if not f.name.startswith("_")]

    if not journey_files:
        return False, "journeys/ exists but no journey files found"

    return True, f"Found {len(journey_files)} journey file(s)"


def get_health_checks() -> list[HealthCheck]:
    """Return the list of health checks to run.

    Returns:
        List of HealthCheck instances ordered by importance.
    """
    return [
        # Required checks
        HealthCheck("Python Version", check_python_version, required=True),
        HealthCheck("Docker", check_docker, required=True),
        HealthCheck("Docker Compose", check_docker_compose, required=True),
        HealthCheck("httpx", lambda: check_package("httpx"), required=True),
        HealthCheck("pydantic", lambda: check_package("pydantic"), required=True),
        HealthCheck("rich", lambda: check_package("rich"), required=True),
        HealthCheck("pyyaml", lambda: check_package("yaml"), required=True),
        HealthCheck("click", lambda: check_package("click"), required=True),
        # Optional checks
        HealthCheck("Config File", check_config_file, required=False),
        HealthCheck("Journeys Directory", check_journeys_directory, required=False),
        HealthCheck("Graphviz", check_graphviz, required=False),
        HealthCheck("PostgreSQL Client", check_postgresql_client, required=False),
        HealthCheck("Git", check_git, required=False),
    ]


def run_health_checks(
    checks: list[HealthCheck] | None = None,
    verbose: bool = False,
) -> Tuple[int, int, int]:
    """Run all health checks and display results.

    Args:
        checks: List of health checks to run. If None, uses default checks.
        verbose: Whether to show additional information.

    Returns:
        Tuple of (passed, failed_required, failed_optional) counts.
    """
    if checks is None:
        checks = get_health_checks()

    console.print("\n[bold blue]VenomQA Doctor[/bold blue]")
    console.print("=" * 40)

    table = Table(show_header=False, box=None)
    table.add_column("Status", width=3)
    table.add_column("Check", width=22)
    table.add_column("Result")

    passed = 0
    failed_required = 0
    failed_optional = 0

    for check in checks:
        success, message = check.run()
        if success:
            table.add_row("[green]OK[/green]", check.name, f"[green]{message}[/green]")
            passed += 1
        elif check.required:
            table.add_row("[red]!![/red]", check.name, f"[red]{message}[/red]")
            failed_required += 1
        else:
            table.add_row("[yellow]--[/yellow]", check.name, f"[yellow]{message}[/yellow]")
            failed_optional += 1

    console.print(table)
    console.print()

    return passed, failed_required, failed_optional


@click.command()
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show additional diagnostic information",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output results as JSON",
)
def doctor(verbose: bool, output_json: bool) -> None:
    """Run system health checks and diagnostics.

    This command checks that all required dependencies are installed
    and properly configured for VenomQA to function correctly.

    Exit codes:
        0 - All required checks passed
        1 - One or more required checks failed
    """
    import json as json_module

    checks = get_health_checks()

    if output_json:
        results = []
        for check in checks:
            success, message = check.run()
            results.append({
                "name": check.name,
                "required": check.required,
                "success": success,
                "message": message,
            })

        passed = sum(1 for r in results if r["success"])
        failed_required = sum(1 for r in results if not r["success"] and r["required"])
        failed_optional = sum(1 for r in results if not r["success"] and not r["required"])

        output = {
            "checks": results,
            "summary": {
                "passed": passed,
                "failed_required": failed_required,
                "failed_optional": failed_optional,
                "ready": failed_required == 0,
            },
        }
        click.echo(json_module.dumps(output, indent=2))
        raise SystemExit(0 if failed_required == 0 else 1)

    passed, failed_required, failed_optional = run_health_checks(checks, verbose)

    if failed_required == 0:
        if failed_optional > 0:
            console.print(
                f"[green]Ready to use[/green] "
                f"({failed_optional} optional dependencies missing)"
            )
        else:
            console.print("[green]All checks passed - Ready to use![/green]")
        raise SystemExit(0)
    else:
        console.print(f"[red]{failed_required} required dependencies missing[/red]")
        console.print("\n[bold]To fix:[/bold]")
        console.print("  1. Install missing Python packages: pip install venomqa[all]")
        console.print("  2. Install and start Docker: https://docs.docker.com/get-docker/")
        raise SystemExit(1)


if __name__ == "__main__":
    doctor()
