"""VenomQA Doctor - System health checks and diagnostics."""

from __future__ import annotations

import importlib.metadata
import os
import shutil
import subprocess
import sys
from collections.abc import Callable

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# Common fix suggestions
# ---------------------------------------------------------------------------

FIXES = {
    "postgres_not_running": """
[bold yellow]To fix PostgreSQL connectivity:[/bold yellow]

  [cyan]# If using Docker:[/cyan]
  docker run -d --name postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:15

  [cyan]# Or start local PostgreSQL:[/cyan]
  brew services start postgresql  # macOS
  sudo systemctl start postgresql  # Linux

  [cyan]# Then set DATABASE_URL:[/cyan]
  export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/venomqa"
""",
    "redis_not_running": """
[bold yellow]To fix Redis connectivity:[/bold yellow]

  [cyan]# If using Docker:[/cyan]
  docker run -d --name redis -p 6379:6379 redis:7

  [cyan]# Or start local Redis:[/cyan]
  brew services start redis  # macOS
  sudo systemctl start redis  # Linux

  [cyan]# Then set REDIS_URL:[/cyan]
  export REDIS_URL="redis://localhost:6379"
""",
    "psycopg_missing": """
[bold yellow]To fix psycopg3 installation:[/bold yellow]

  pip install 'psycopg[binary]'

  [dim]# Or for source build (slower):[/dim]
  pip install psycopg
""",
    "redis_py_missing": """
[bold yellow]To fix redis-py installation:[/bold yellow]

  pip install redis
""",
    "env_vars_missing": """
[bold yellow]To set up environment variables:[/bold yellow]

  [cyan]# Create a .env file or export directly:[/cyan]
  export DATABASE_URL="postgresql://user:pass@localhost:5432/dbname"
  export REDIS_URL="redis://localhost:6379"
  export VENOMQA_API_TOKEN="your-api-token"  # if using auth

  [cyan]# Or create venomqa.env:[/cyan]
  echo 'DATABASE_URL=postgresql://localhost/venomqa' > venomqa.env
  source venomqa.env
""",
}


class HealthCheck:
    """A single health check with name, check function, and required flag."""

    def __init__(
        self,
        name: str,
        check_fn: Callable[[], tuple[bool, str]],
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

    def run(self) -> tuple[bool, str]:
        """Run the health check and return (success, message)."""
        try:
            return self.check_fn()
        except Exception as e:
            return False, str(e)


def check_python_version() -> tuple[bool, str]:
    """Check if Python version meets minimum requirements (>= 3.10)."""
    version = sys.version_info
    if version >= (3, 10):
        return True, f"Python {version.major}.{version.minor}.{version.micro}"
    return False, f"Python {version.major}.{version.minor} (requires >= 3.10)"


def check_docker() -> tuple[bool, str]:
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


def check_docker_compose() -> tuple[bool, str]:
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


def check_package(package: str) -> tuple[bool, str]:
    """Check if a Python package is installed and return its version.

    Args:
        package: The import name of the package to check.

    Returns:
        Tuple of (success, message) indicating if package is installed.
    """
    try:
        __import__(package)
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            version = "installed"
        return True, f"{package} {version}"
    except ImportError:
        return False, f"{package} not installed"


def check_graphviz() -> tuple[bool, str]:
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


def check_postgresql_client() -> tuple[bool, str]:
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


def check_git() -> tuple[bool, str]:
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


def check_redis_client() -> tuple[bool, str]:
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


def check_disk_space() -> tuple[bool, str]:
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


def check_common_ports() -> tuple[bool, str]:
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


# ---------------------------------------------------------------------------
# Database Connectivity Checks (new)
# ---------------------------------------------------------------------------


def check_psycopg3() -> tuple[bool, str]:
    """Check if psycopg3 is installed (required for PostgreSQL support)."""
    try:
        import psycopg
        version = getattr(psycopg, "__version__", "installed")
        return True, f"psycopg {version}"
    except ImportError:
        return False, "psycopg3 not installed (pip install 'psycopg[binary]')"


def check_postgres_connection() -> tuple[bool, str]:
    """Check actual PostgreSQL connectivity using DATABASE_URL or defaults."""
    db_url = os.environ.get("DATABASE_URL")

    if not db_url:
        # Try common local defaults
        defaults = [
            "postgresql://postgres:postgres@localhost:5432/postgres",
            "postgresql://localhost:5432/postgres",
        ]
    else:
        defaults = [db_url]

    try:
        import psycopg
    except ImportError:
        return False, "psycopg3 not installed (cannot test connection)"

    last_error = None
    for url in defaults:
        try:
            with psycopg.connect(url, connect_timeout=3) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT version()")
                    version = cur.fetchone()[0]
                    # Extract just the version number
                    version_short = version.split(",")[0] if version else "connected"
                    return True, version_short
        except Exception as e:
            last_error = str(e)
            continue

    error_msg = last_error or "Connection failed"
    if "connection refused" in error_msg.lower():
        return False, "PostgreSQL not running (connection refused)"
    elif "password authentication failed" in error_msg.lower():
        return False, "PostgreSQL auth failed (check DATABASE_URL credentials)"
    elif "does not exist" in error_msg.lower():
        return False, "Database does not exist (create it first)"
    else:
        return False, f"PostgreSQL connection failed: {error_msg[:50]}"


def check_redis_connection() -> tuple[bool, str]:
    """Check actual Redis connectivity using REDIS_URL or defaults."""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")

    try:
        import redis
    except ImportError:
        return False, "redis-py not installed (pip install redis)"

    try:
        client = redis.from_url(redis_url, socket_connect_timeout=2)
        info = client.info("server")
        version = info.get("redis_version", "connected")
        client.close()
        return True, f"Redis {version}"
    except redis.ConnectionError as e:
        error_msg = str(e)
        if "connection refused" in error_msg.lower():
            return False, "Redis not running (connection refused)"
        return False, f"Redis connection failed: {error_msg[:40]}"
    except Exception as e:
        return False, f"Redis error: {str(e)[:40]}"


def check_environment_vars() -> tuple[bool, str]:
    """Check if common environment variables are set."""
    env_vars = {
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "REDIS_URL": os.environ.get("REDIS_URL"),
    }

    set_vars = [k for k, v in env_vars.items() if v]
    missing_vars = [k for k, v in env_vars.items() if not v]

    if set_vars and not missing_vars:
        return True, f"All env vars set ({', '.join(set_vars)})"
    elif set_vars:
        return True, f"Set: {', '.join(set_vars)} | Missing: {', '.join(missing_vars)}"
    else:
        return False, f"No env vars set ({', '.join(missing_vars)})"


def check_v1_quick_start() -> tuple[bool, str]:
    """Check if v1 module can be imported and is working."""
    try:
        from venomqa.v1 import State, Action, World, Agent, explore
        return True, "v1 module ready"
    except ImportError as e:
        return False, f"v1 import failed: {e}"
    except Exception as e:
        return False, f"v1 error: {e}"


def check_config_file() -> tuple[bool, str]:
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


def check_journeys_directory() -> tuple[bool, str]:
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


def get_health_checks(include_connectivity: bool = True) -> list[HealthCheck]:
    """Return the list of health checks to run.

    Args:
        include_connectivity: If True, include database connectivity checks.

    Returns:
        List of HealthCheck instances ordered by importance.
    """
    checks = [
        # Required checks - Core Python environment
        HealthCheck("Python Version", check_python_version, required=True),
        HealthCheck("httpx", lambda: check_package("httpx"), required=True),
        HealthCheck("pydantic", lambda: check_package("pydantic"), required=True),
        HealthCheck("rich", lambda: check_package("rich"), required=True),
        HealthCheck("pyyaml", lambda: check_package("yaml"), required=True),
        HealthCheck("click", lambda: check_package("click"), required=True),
        # v1 Module check
        HealthCheck("v1 Module", check_v1_quick_start, required=True),
        # Docker checks (optional for v1 mocks)
        HealthCheck("Docker", check_docker, required=False),
        HealthCheck("Docker Compose", check_docker_compose, required=False),
        # Database packages
        HealthCheck("psycopg3", check_psycopg3, required=False),
        HealthCheck("redis-py", check_redis_client, required=False),
    ]

    if include_connectivity:
        checks.extend([
            # Environment checks
            HealthCheck("Environment Vars", check_environment_vars, required=False),
            # Connectivity checks (these actually try to connect)
            HealthCheck("PostgreSQL", check_postgres_connection, required=False),
            HealthCheck("Redis", check_redis_connection, required=False),
        ])

    checks.extend([
        # Project structure checks
        HealthCheck("Config File", check_config_file, required=False),
        HealthCheck("Journeys Directory", check_journeys_directory, required=False),
        # System checks
        HealthCheck("Graphviz", check_graphviz, required=False),
        HealthCheck("PostgreSQL Client", check_postgresql_client, required=False),
        HealthCheck("Git", check_git, required=False),
        HealthCheck("Disk Space", check_disk_space, required=False),
        HealthCheck("Port Scan", check_common_ports, required=False),
    ])

    return checks


def run_health_checks(
    checks: list[HealthCheck] | None = None,
    verbose: bool = False,
) -> tuple[int, int, int]:
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
@click.option(
    "--skip-connectivity",
    is_flag=True,
    help="Skip database connectivity checks (faster)",
)
@click.option(
    "--fix",
    "show_fixes",
    is_flag=True,
    help="Show fix suggestions for failed checks",
)
def doctor(verbose: bool, output_json: bool, skip_connectivity: bool, show_fixes: bool) -> None:
    """Run system health checks and diagnostics.

    This command checks that all required dependencies are installed
    and properly configured for VenomQA to function correctly.

    Exit codes:
        0 - All required checks passed
        1 - One or more required checks failed

    Examples:
        venomqa doctor              # Full health check
        venomqa doctor --fix        # Show fix suggestions
        venomqa doctor --skip-connectivity  # Skip DB checks (faster)
    """
    import json as json_module

    checks = get_health_checks(include_connectivity=not skip_connectivity)

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

    # Collect failed check names for fix suggestions
    failed_names = set()
    for check in checks:
        success, _ = check.run()
        if not success:
            failed_names.add(check.name.lower())

    if failed_required == 0:
        if failed_optional > 0:
            console.print(
                f"[green]Ready to use[/green] "
                f"({failed_optional} optional dependencies missing)"
            )
        else:
            console.print("[green]All checks passed - Ready to use![/green]")

        # Show tips even when passing
        if show_fixes and failed_optional > 0:
            _show_fix_suggestions(failed_names)

        raise SystemExit(0)
    else:
        console.print(f"[red]{failed_required} required dependencies missing[/red]")

        if show_fixes:
            _show_fix_suggestions(failed_names)
        else:
            console.print("\n[dim]Run 'venomqa doctor --fix' for detailed fix suggestions[/dim]")

        raise SystemExit(1)


def _show_fix_suggestions(failed_names: set[str]) -> None:
    """Show fix suggestions based on failed checks."""
    console.print()

    suggestions_shown = set()

    # PostgreSQL fixes
    if "postgresql" in failed_names or "postgres" in "".join(failed_names):
        if "psycopg3" in failed_names:
            if "psycopg_missing" not in suggestions_shown:
                console.print(Panel(FIXES["psycopg_missing"], title="Install psycopg3"))
                suggestions_shown.add("psycopg_missing")
        else:
            if "postgres_not_running" not in suggestions_shown:
                console.print(Panel(FIXES["postgres_not_running"], title="Fix PostgreSQL"))
                suggestions_shown.add("postgres_not_running")

    # Redis fixes
    if "redis" in "".join(failed_names):
        if "redis-py" in failed_names:
            if "redis_py_missing" not in suggestions_shown:
                console.print(Panel(FIXES["redis_py_missing"], title="Install redis-py"))
                suggestions_shown.add("redis_py_missing")
        else:
            if "redis_not_running" not in suggestions_shown:
                console.print(Panel(FIXES["redis_not_running"], title="Fix Redis"))
                suggestions_shown.add("redis_not_running")

    # Environment variable fixes
    if "environment" in "".join(failed_names) or "env" in "".join(failed_names):
        if "env_vars_missing" not in suggestions_shown:
            console.print(Panel(FIXES["env_vars_missing"], title="Set Environment Variables"))
            suggestions_shown.add("env_vars_missing")

    # Generic fix for other failures
    if not suggestions_shown:
        console.print("\n[bold]To fix:[/bold]")
        console.print("  1. Install missing Python packages: pip install 'venomqa[all]'")
        console.print("  2. Install and start Docker: https://docs.docker.com/get-docker/")


if __name__ == "__main__":
    doctor()
