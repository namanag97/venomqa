"""Docker CLI commands for VenomQA."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click

# Exit codes
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_CONFIG_ERROR = 2


def find_compose_file(config: dict[str, Any]) -> Path | None:
    """Find the docker-compose file to use.

    Looks for files in order:
    1. Config-specified compose file
    2. docker-compose.qa.yml in current directory
    3. docker-compose.yml in current directory
    4. qa/docker-compose.qa.yml

    Args:
        config: VenomQA configuration dict.

    Returns:
        Path to compose file or None if not found.
    """
    # Check config first
    if "docker" in config:
        docker_config = config["docker"]
        if "compose_file" in docker_config:
            compose_path = Path(docker_config["compose_file"])
            if compose_path.exists():
                return compose_path

    # Check standard locations
    locations = [
        Path("docker-compose.qa.yml"),
        Path("docker-compose.yml"),
        Path("qa/docker-compose.qa.yml"),
        Path("docker/docker-compose.yml"),
    ]

    for location in locations:
        if location.exists():
            return location

    return None


def get_docker_manager(config: dict[str, Any], compose_file: str | None = None):
    """Get a configured Docker infrastructure manager.

    Args:
        config: VenomQA configuration dict.
        compose_file: Optional override for compose file path.

    Returns:
        DockerInfrastructureManager instance.
    """
    from venomqa.infra.docker import DockerInfrastructureManager, DockerNotFoundError

    # Find compose file
    if compose_file:
        compose_path = Path(compose_file)
    else:
        compose_path = find_compose_file(config)

    if compose_path is None:
        click.echo(
            "No docker-compose file found. Create docker-compose.qa.yml or specify with --file.",
            err=True,
        )
        sys.exit(EXIT_CONFIG_ERROR)

    if not compose_path.exists():
        click.echo(f"Docker compose file not found: {compose_path}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)

    # Get docker config
    docker_config = config.get("docker", {})
    project_name = docker_config.get("project_name", "venomqa")
    services = docker_config.get("services", [])
    env_file = docker_config.get("env_file")
    profiles = docker_config.get("profiles", [])

    try:
        return DockerInfrastructureManager(
            compose_file=str(compose_path),
            project_name=project_name,
            services=services,
            env_file=env_file,
            profiles=profiles,
        )
    except DockerNotFoundError as e:
        click.echo(f"Docker error: {e}", err=True)
        if e.stderr:
            click.echo(f"Details: {e.stderr}", err=True)
        sys.exit(EXIT_CONFIG_ERROR)


@click.group()
@click.pass_context
def docker(ctx: click.Context) -> None:
    """Manage Docker test infrastructure.

    Commands for starting, stopping, and monitoring Docker-based
    test infrastructure defined in docker-compose files.

    \b
    Examples:
        venomqa docker up              # Start test infrastructure
        venomqa docker down            # Stop test infrastructure
        venomqa docker health          # Check service health
        venomqa docker logs api        # View logs for 'api' service
        venomqa docker ps              # List running services
    """
    pass


@docker.command("up")
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True),
    help="Path to docker-compose file",
)
@click.option("--build", "-b", is_flag=True, help="Build images before starting")
@click.option("--force-recreate", is_flag=True, help="Recreate containers even if unchanged")
@click.option("--wait", "-w", is_flag=True, default=True, help="Wait for services to be healthy")
@click.option(
    "--timeout",
    "-t",
    type=int,
    default=60,
    help="Timeout in seconds for health check (default: 60)",
)
@click.option(
    "--service",
    "-s",
    "services",
    multiple=True,
    help="Specific service(s) to start",
)
@click.pass_context
def docker_up(
    ctx: click.Context,
    compose_file: str | None,
    build: bool,
    force_recreate: bool,
    wait: bool,
    timeout: int,
    services: tuple[str, ...],
) -> None:
    """Start test infrastructure.

    Starts all services defined in the docker-compose file (or specified
    services) and optionally waits for them to become healthy.

    \b
    Examples:
        venomqa docker up                    # Start all services
        venomqa docker up --build            # Build and start
        venomqa docker up -s api -s db       # Start specific services
        venomqa docker up --timeout 120      # Wait up to 2 minutes
        venomqa docker up --no-wait          # Don't wait for health
    """
    from rich.console import Console

    console = Console()
    config: dict[str, Any] = ctx.obj.get("config", {})

    # Override services if specified
    if services:
        config.setdefault("docker", {})["services"] = list(services)

    manager = get_docker_manager(config, compose_file)

    console.print(f"[bold]Starting Docker infrastructure...[/bold]")
    console.print(f"  Compose file: {manager.compose_file}")

    try:
        manager.start(build=build, force_recreate=force_recreate)
        console.print("[green]Services started[/green]")

        if wait:
            console.print(f"[dim]Waiting for services to be healthy (timeout: {timeout}s)...[/dim]")
            if manager.wait_healthy(timeout=timeout):
                console.print("[bold green]All services are healthy![/bold green]")
            else:
                console.print("[bold yellow]Warning: Some services may not be healthy[/bold yellow]")
                # Show status
                statuses = manager.get_service_statuses()
                for status in statuses:
                    health_color = "green" if status.is_healthy else "red"
                    console.print(
                        f"  [{health_color}]{status.name}[/{health_color}]: "
                        f"{status.state} ({status.health.value})"
                    )
                sys.exit(EXIT_FAILURE)

    except Exception as e:
        console.print(f"[bold red]Failed to start infrastructure: {e}[/bold red]", err=True)
        sys.exit(EXIT_FAILURE)


@docker.command("down")
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True),
    help="Path to docker-compose file",
)
@click.option("--volumes", "-v", is_flag=True, help="Remove volumes")
@click.option("--timeout", "-t", type=int, default=10, help="Timeout for stopping (default: 10s)")
@click.pass_context
def docker_down(
    ctx: click.Context,
    compose_file: str | None,
    volumes: bool,
    timeout: int,
) -> None:
    """Stop test infrastructure.

    Stops and removes all containers defined in the docker-compose file.
    Optionally removes volumes.

    \b
    Examples:
        venomqa docker down              # Stop all services
        venomqa docker down --volumes    # Stop and remove volumes
    """
    from rich.console import Console

    console = Console()
    config: dict[str, Any] = ctx.obj.get("config", {})

    manager = get_docker_manager(config, compose_file)

    console.print("[bold]Stopping Docker infrastructure...[/bold]")

    try:
        manager.stop(remove_volumes=volumes, timeout=timeout)
        console.print("[bold green]Infrastructure stopped[/bold green]")
        if volumes:
            console.print("[dim]Volumes removed[/dim]")
    except Exception as e:
        console.print(f"[bold red]Failed to stop infrastructure: {e}[/bold red]", err=True)
        sys.exit(EXIT_FAILURE)


@docker.command("logs")
@click.argument("service", required=False)
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True),
    help="Path to docker-compose file",
)
@click.option("--tail", "-n", type=int, default=100, help="Number of lines to show (default: 100)")
@click.option("--follow", is_flag=True, help="Follow log output")
@click.option("--timestamps", "-t", is_flag=True, help="Show timestamps")
@click.pass_context
def docker_logs(
    ctx: click.Context,
    service: str | None,
    compose_file: str | None,
    tail: int,
    follow: bool,
    timestamps: bool,
) -> None:
    """View container logs.

    Shows logs from all services or a specific service.

    \b
    Examples:
        venomqa docker logs              # All service logs
        venomqa docker logs api          # Logs for 'api' service
        venomqa docker logs api -n 50    # Last 50 lines
        venomqa docker logs --follow     # Follow log output
    """
    config: dict[str, Any] = ctx.obj.get("config", {})

    manager = get_docker_manager(config, compose_file)

    try:
        logs = manager.logs(
            service_name=service,
            tail=tail,
            follow=follow,
            timestamps=timestamps,
        )
        click.echo(logs)
    except KeyboardInterrupt:
        pass  # Normal exit from follow mode
    except Exception as e:
        click.echo(f"Failed to get logs: {e}", err=True)
        sys.exit(EXIT_FAILURE)


@docker.command("health")
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True),
    help="Path to docker-compose file",
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def docker_health(
    ctx: click.Context,
    compose_file: str | None,
    output_json: bool,
) -> None:
    """Check container health status.

    Shows the health status of all running services.

    \b
    Examples:
        venomqa docker health            # Show health status
        venomqa docker health --json     # Output as JSON
    """
    import json

    from rich.console import Console
    from rich.table import Table

    console = Console()
    config: dict[str, Any] = ctx.obj.get("config", {})

    manager = get_docker_manager(config, compose_file)

    try:
        statuses = manager.get_service_statuses()

        if not statuses:
            console.print("[yellow]No services running[/yellow]")
            sys.exit(EXIT_FAILURE)

        if output_json:
            data = [
                {
                    "name": s.name,
                    "state": s.state,
                    "health": s.health.value,
                    "healthy": s.is_healthy,
                    "ports": s.ports,
                    "image": s.image,
                }
                for s in statuses
            ]
            click.echo(json.dumps(data, indent=2))
        else:
            table = Table(title="Service Health")
            table.add_column("Service", style="cyan")
            table.add_column("State")
            table.add_column("Health")
            table.add_column("Ports")
            table.add_column("Image")

            all_healthy = True
            for status in statuses:
                if status.is_healthy:
                    health_style = "green"
                    state_style = "green"
                else:
                    health_style = "red"
                    state_style = "yellow"
                    all_healthy = False

                table.add_row(
                    status.name,
                    f"[{state_style}]{status.state}[/{state_style}]",
                    f"[{health_style}]{status.health.value}[/{health_style}]",
                    ", ".join(status.ports[:3]) if status.ports else "-",
                    status.image[:40] if status.image else "-",
                )

            console.print(table)

            if all_healthy:
                console.print("\n[bold green]All services healthy[/bold green]")
            else:
                console.print("\n[bold yellow]Some services are not healthy[/bold yellow]")
                sys.exit(EXIT_FAILURE)

    except Exception as e:
        console.print(f"[bold red]Failed to check health: {e}[/bold red]", err=True)
        sys.exit(EXIT_FAILURE)


@docker.command("ps")
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True),
    help="Path to docker-compose file",
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def docker_ps(
    ctx: click.Context,
    compose_file: str | None,
    output_json: bool,
) -> None:
    """List running services.

    Shows all services defined in the docker-compose file and their status.

    \b
    Examples:
        venomqa docker ps                # List services
        venomqa docker ps --json         # Output as JSON
    """
    import json

    from rich.console import Console
    from rich.table import Table

    console = Console()
    config: dict[str, Any] = ctx.obj.get("config", {})

    manager = get_docker_manager(config, compose_file)

    try:
        statuses = manager.get_service_statuses()

        if output_json:
            data = [
                {
                    "name": s.name,
                    "state": s.state,
                    "health": s.health.value,
                    "ports": s.ports,
                    "image": s.image,
                    "created": s.created,
                }
                for s in statuses
            ]
            click.echo(json.dumps(data, indent=2))
        else:
            if not statuses:
                console.print("[yellow]No services running[/yellow]")
                return

            table = Table(title="Docker Services")
            table.add_column("Service", style="cyan")
            table.add_column("State")
            table.add_column("Health")
            table.add_column("Ports")

            for status in statuses:
                state_style = "green" if status.state == "running" else "yellow"
                health_style = "green" if status.is_healthy else "red"

                table.add_row(
                    status.name,
                    f"[{state_style}]{status.state}[/{state_style}]",
                    f"[{health_style}]{status.health.value}[/{health_style}]",
                    ", ".join(status.ports[:3]) if status.ports else "-",
                )

            console.print(table)

    except Exception as e:
        console.print(f"[bold red]Failed to list services: {e}[/bold red]", err=True)
        sys.exit(EXIT_FAILURE)


@docker.command("restart")
@click.argument("service", required=False)
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True),
    help="Path to docker-compose file",
)
@click.pass_context
def docker_restart(
    ctx: click.Context,
    service: str | None,
    compose_file: str | None,
) -> None:
    """Restart services.

    Restarts all services or a specific service.

    \b
    Examples:
        venomqa docker restart           # Restart all services
        venomqa docker restart api       # Restart 'api' service
    """
    from rich.console import Console

    console = Console()
    config: dict[str, Any] = ctx.obj.get("config", {})

    manager = get_docker_manager(config, compose_file)

    target = service if service else "all services"
    console.print(f"[bold]Restarting {target}...[/bold]")

    try:
        manager.restart(service_name=service)
        console.print(f"[bold green]Restarted {target}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to restart: {e}[/bold red]", err=True)
        sys.exit(EXIT_FAILURE)


@docker.command("exec")
@click.argument("service")
@click.argument("command", nargs=-1, required=True)
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True),
    help="Path to docker-compose file",
)
@click.option("--user", "-u", help="User to run command as")
@click.option("--workdir", "-w", help="Working directory inside container")
@click.pass_context
def docker_exec(
    ctx: click.Context,
    service: str,
    command: tuple[str, ...],
    compose_file: str | None,
    user: str | None,
    workdir: str | None,
) -> None:
    """Execute command in a running container.

    \b
    Examples:
        venomqa docker exec api ls -la
        venomqa docker exec db psql -U user -d testdb
        venomqa docker exec api python manage.py shell
    """
    config: dict[str, Any] = ctx.obj.get("config", {})

    manager = get_docker_manager(config, compose_file)

    try:
        exit_code, stdout, stderr = manager.exec(
            service_name=service,
            command=list(command),
            user=user,
            workdir=workdir,
        )
        if stdout:
            click.echo(stdout)
        if stderr:
            click.echo(stderr, err=True)
        sys.exit(exit_code)
    except Exception as e:
        click.echo(f"Failed to execute command: {e}", err=True)
        sys.exit(EXIT_FAILURE)


@docker.command("pull")
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True),
    help="Path to docker-compose file",
)
@click.option("--ignore-failures", is_flag=True, help="Ignore pull failures")
@click.pass_context
def docker_pull(
    ctx: click.Context,
    compose_file: str | None,
    ignore_failures: bool,
) -> None:
    """Pull service images.

    Downloads the latest images for all services defined in the compose file.

    \b
    Examples:
        venomqa docker pull              # Pull all images
        venomqa docker pull --ignore-failures
    """
    from rich.console import Console

    console = Console()
    config: dict[str, Any] = ctx.obj.get("config", {})

    manager = get_docker_manager(config, compose_file)

    console.print("[bold]Pulling images...[/bold]")

    try:
        manager.pull(ignore_pull_failures=ignore_failures)
        console.print("[bold green]Images pulled successfully[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to pull images: {e}[/bold red]", err=True)
        sys.exit(EXIT_FAILURE)


@docker.command("build")
@click.option(
    "--file",
    "-f",
    "compose_file",
    type=click.Path(exists=True),
    help="Path to docker-compose file",
)
@click.option("--no-cache", is_flag=True, help="Build without cache")
@click.option("--pull", "pull_base", is_flag=True, help="Pull base images")
@click.pass_context
def docker_build(
    ctx: click.Context,
    compose_file: str | None,
    no_cache: bool,
    pull_base: bool,
) -> None:
    """Build service images.

    Builds images for services defined in the compose file.

    \b
    Examples:
        venomqa docker build             # Build all images
        venomqa docker build --no-cache  # Build without cache
        venomqa docker build --pull      # Pull base images first
    """
    from rich.console import Console

    console = Console()
    config: dict[str, Any] = ctx.obj.get("config", {})

    manager = get_docker_manager(config, compose_file)

    console.print("[bold]Building images...[/bold]")

    try:
        manager.build(no_cache=no_cache, pull=pull_base)
        console.print("[bold green]Images built successfully[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Failed to build images: {e}[/bold red]", err=True)
        sys.exit(EXIT_FAILURE)


@docker.command("check")
def docker_check() -> None:
    """Check Docker environment.

    Verifies that Docker and Docker Compose are installed and working.

    \b
    Examples:
        venomqa docker check
    """
    from rich.console import Console
    from rich.table import Table

    from venomqa.infra.docker import DockerInfrastructureManager

    console = Console()

    console.print("[bold]Checking Docker environment...[/bold]\n")

    health = DockerInfrastructureManager.check_docker_health()

    table = Table()
    table.add_column("Component", style="cyan")
    table.add_column("Status")
    table.add_column("Details")

    # Docker
    if health.docker_available:
        table.add_row("Docker", "[green]Available[/green]", health.docker_version)
    else:
        table.add_row("Docker", "[red]Not Available[/red]", "Docker not found or not running")

    # Docker Compose
    if health.compose_available:
        table.add_row("Docker Compose", "[green]Available[/green]", health.compose_version)
    else:
        table.add_row("Docker Compose", "[red]Not Available[/red]", "Install with: docker compose")

    console.print(table)

    if health.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for error in health.errors:
            console.print(f"  [red]- {error}[/red]")

    if health.is_healthy:
        console.print("\n[bold green]Docker environment is ready![/bold green]")
        sys.exit(EXIT_SUCCESS)
    else:
        console.print("\n[bold red]Docker environment has issues.[/bold red]")
        console.print("\nPlease ensure Docker Desktop is installed and running.")
        sys.exit(EXIT_FAILURE)
