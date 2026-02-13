"""Docker/docker-compose backend for infrastructure management."""

from __future__ import annotations

import json as json_module
import logging
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from venomqa.infra.base import BaseInfrastructureManager

logger = logging.getLogger(__name__)


class DockerError(Exception):
    """Base exception for Docker operations."""

    def __init__(self, message: str, command: list[str] | None = None, stderr: str = "") -> None:
        super().__init__(message)
        self.command = command
        self.stderr = stderr


class DockerNotFoundError(DockerError):
    """Raised when Docker is not installed or not running."""

    pass


class DockerComposeError(DockerError):
    """Raised when docker compose command fails."""

    pass


class ServiceHealthStatus(Enum):
    """Service health status."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    UNKNOWN = "unknown"


@dataclass
class ServiceStatus:
    """Status of a Docker service."""

    name: str
    state: str
    health: ServiceHealthStatus
    ports: list[str]
    image: str
    created: str

    @property
    def is_healthy(self) -> bool:
        """Check if service is healthy or running without healthcheck."""
        return self.health in (ServiceHealthStatus.HEALTHY, ServiceHealthStatus.RUNNING)


@dataclass
class DockerHealthCheck:
    """Result of a Docker health check."""

    docker_available: bool
    compose_available: bool
    compose_version: str
    docker_version: str
    errors: list[str]

    @property
    def is_healthy(self) -> bool:
        """Check if Docker environment is healthy."""
        return self.docker_available and self.compose_available and not self.errors


class DockerInfrastructureManager(BaseInfrastructureManager):
    """Infrastructure manager using docker compose.

    This manager provides full lifecycle management for Docker Compose based
    test infrastructure including:
    - Starting/stopping services
    - Health checking with configurable timeouts
    - Log retrieval
    - Service status monitoring
    - Graceful error handling
    """

    def __init__(
        self,
        compose_file: str | Path | None = None,
        project_name: str | None = None,
        services: list[str] | None = None,
        env_file: str | Path | None = None,
        profiles: list[str] | None = None,
    ) -> None:
        """Initialize Docker infrastructure manager.

        Args:
            compose_file: Path to docker-compose.yml file.
            project_name: Docker Compose project name.
            services: List of specific services to manage (default: all).
            env_file: Path to environment file for docker compose.
            profiles: Docker Compose profiles to activate.
        """
        super().__init__(
            compose_file=str(compose_file) if compose_file else None,
            project_name=project_name,
        )
        self.services = services or []
        self.env_file = str(env_file) if env_file else None
        self.profiles = profiles or []
        self._compose_cmd = self._detect_compose_command()
        self._docker_available = False
        self._compose_available = False

    def _detect_compose_command(self) -> list[str]:
        """Detect whether to use 'docker compose' or 'docker-compose'.

        Returns:
            List of command components for docker compose.

        Raises:
            DockerNotFoundError: If Docker is not installed.
        """
        # First check if docker is available
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise DockerNotFoundError(
                    "Docker is not installed or not running",
                    command=["docker", "--version"],
                    stderr=result.stderr,
                )
            self._docker_available = True
        except FileNotFoundError:
            raise DockerNotFoundError(
                "Docker command not found. Please install Docker.",
                command=["docker", "--version"],
            )
        except subprocess.TimeoutExpired:
            raise DockerNotFoundError(
                "Docker command timed out. Docker may not be running.",
                command=["docker", "--version"],
            )

        # Check for docker compose (v2 - preferred)
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                self._compose_available = True
                return ["docker", "compose"]
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fall back to docker-compose (v1)
        try:
            result = subprocess.run(
                ["docker-compose", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                self._compose_available = True
                return ["docker-compose"]
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass

        logger.warning("Docker Compose not found, using 'docker compose' anyway")
        return ["docker", "compose"]

    def _build_command(self, *args: str) -> list[str]:
        """Build a docker compose command with common options."""
        cmd = self._compose_cmd.copy()
        if self.compose_file:
            cmd.extend(["-f", self.compose_file])
        if self.project_name:
            cmd.extend(["-p", self.project_name])
        if self.env_file:
            cmd.extend(["--env-file", self.env_file])
        for profile in self.profiles:
            cmd.extend(["--profile", profile])
        cmd.extend(args)
        return cmd

    def _run_command(
        self,
        *args: str,
        check: bool = True,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a docker compose command.

        Args:
            *args: Command arguments.
            check: Whether to raise on non-zero exit code.
            timeout: Command timeout in seconds.

        Returns:
            CompletedProcess with command results.

        Raises:
            DockerComposeError: If command fails and check=True.
        """
        cmd = self._build_command(*args)
        logger.debug(f"Running docker command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )

            if check and result.returncode != 0:
                raise DockerComposeError(
                    f"Docker compose command failed: {' '.join(args)}",
                    command=cmd,
                    stderr=result.stderr,
                )

            return result

        except subprocess.TimeoutExpired as e:
            raise DockerComposeError(
                f"Docker compose command timed out: {' '.join(args)}",
                command=cmd,
            ) from e

    def start(self, build: bool = False, force_recreate: bool = False) -> None:
        """Spin up services via docker compose.

        Args:
            build: Whether to build images before starting.
            force_recreate: Whether to force recreate containers.
        """
        cmd_args = ["up", "-d"]
        if build:
            cmd_args.append("--build")
        if force_recreate:
            cmd_args.append("--force-recreate")
        if self.services:
            cmd_args.extend(self.services)

        logger.info(f"Starting Docker services: {self.services or 'all'}")
        self._run_command(*cmd_args, timeout=300)  # 5 min timeout for startup
        self._running = True
        logger.info("Docker services started successfully")

    def stop(self, remove_volumes: bool = False, timeout: int = 10) -> None:
        """Tear down services.

        Args:
            remove_volumes: Whether to remove volumes.
            timeout: Timeout in seconds for stopping containers.
        """
        cmd_args = ["down"]
        if remove_volumes:
            cmd_args.append("-v")
        cmd_args.extend(["--timeout", str(timeout)])

        logger.info("Stopping Docker services")
        self._run_command(*cmd_args, timeout=120)
        self._running = False
        logger.info("Docker services stopped")

    def wait_healthy(self, timeout: float = 60.0, poll_interval: float = 1.0) -> bool:
        """Wait for services to be healthy.

        Uses docker compose ps to check service health status.

        Args:
            timeout: Maximum time to wait in seconds.
            poll_interval: Time between health checks in seconds.

        Returns:
            True if all services are healthy within timeout.
        """
        start_time = time.time()
        logger.info(f"Waiting for services to be healthy (timeout: {timeout}s)")

        while time.time() - start_time < timeout:
            try:
                statuses = self.get_service_statuses()
                if statuses and all(s.is_healthy for s in statuses):
                    elapsed = time.time() - start_time
                    logger.info(f"All services healthy after {elapsed:.1f}s")
                    return True

                # Log unhealthy services
                unhealthy = [s.name for s in statuses if not s.is_healthy]
                if unhealthy:
                    logger.debug(f"Waiting for services: {', '.join(unhealthy)}")

            except DockerComposeError as e:
                logger.debug(f"Health check failed: {e}")
            except Exception as e:
                logger.debug(f"Unexpected error during health check: {e}")

            time.sleep(poll_interval)

        logger.warning(f"Services did not become healthy within {timeout}s")
        return False

    def _check_health(self, ps_output: str) -> bool:
        """Check if all services are healthy from ps output."""
        if not ps_output.strip():
            return False

        try:
            lines = ps_output.strip().split("\n")
            for line in lines:
                if not line.strip():
                    continue
                service = json_module.loads(line)
                health = service.get("Health", "")
                if health and health.lower() != "healthy":
                    return False
                state = service.get("State", "")
                if state and state.lower() != "running":
                    return False
            return len(lines) > 0
        except json_module.JSONDecodeError:
            result = self._run_command("ps", "--format", "{{.Status}}", check=False)
            if result.returncode != 0:
                return False
            return "running" in result.stdout.lower() and "unhealthy" not in result.stdout.lower()

    def get_service_statuses(self) -> list[ServiceStatus]:
        """Get detailed status of all services.

        Returns:
            List of ServiceStatus objects.
        """
        result = self._run_command("ps", "--format", "json", check=False)
        if result.returncode != 0:
            return []

        statuses: list[ServiceStatus] = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json_module.loads(line)
                health_str = data.get("Health", data.get("State", "unknown")).lower()

                if health_str == "healthy":
                    health = ServiceHealthStatus.HEALTHY
                elif health_str == "unhealthy":
                    health = ServiceHealthStatus.UNHEALTHY
                elif health_str in ("starting", "health: starting"):
                    health = ServiceHealthStatus.STARTING
                elif health_str == "running":
                    health = ServiceHealthStatus.RUNNING
                elif health_str in ("stopped", "exited"):
                    health = ServiceHealthStatus.STOPPED
                else:
                    health = ServiceHealthStatus.UNKNOWN

                statuses.append(
                    ServiceStatus(
                        name=data.get("Service", data.get("Name", "unknown")),
                        state=data.get("State", "unknown"),
                        health=health,
                        ports=data.get("Ports", "").split(", ") if data.get("Ports") else [],
                        image=data.get("Image", ""),
                        created=data.get("CreatedAt", ""),
                    )
                )
            except json_module.JSONDecodeError:
                continue

        return statuses

    def logs(
        self,
        service_name: str | None = None,
        tail: int | None = None,
        follow: bool = False,
        timestamps: bool = False,
    ) -> str:
        """Get logs from services.

        Args:
            service_name: Specific service to get logs from (None for all).
            tail: Number of lines to show from end.
            follow: Whether to follow log output (blocks).
            timestamps: Whether to show timestamps.

        Returns:
            Log output as string.
        """
        cmd_args = ["logs"]
        if tail is not None:
            cmd_args.extend(["--tail", str(tail)])
        if follow:
            cmd_args.append("-f")
        if timestamps:
            cmd_args.append("-t")
        if service_name:
            cmd_args.append(service_name)

        result = self._run_command(*cmd_args, check=False)
        return result.stdout + result.stderr

    def is_running(self) -> bool:
        """Check if infrastructure is up by inspecting container status."""
        try:
            result = self._run_command("ps", "-q", check=False, timeout=10)
            return bool(result.stdout.strip())
        except (DockerComposeError, Exception):
            return False

    def restart(self, service_name: str | None = None) -> None:
        """Restart services.

        Args:
            service_name: Specific service to restart (None for all).
        """
        cmd_args = ["restart"]
        if service_name:
            cmd_args.append(service_name)
        self._run_command(*cmd_args, timeout=120)

    def pull(self, ignore_pull_failures: bool = False) -> None:
        """Pull images for services.

        Args:
            ignore_pull_failures: Whether to ignore pull failures.
        """
        cmd_args = ["pull"]
        if ignore_pull_failures:
            cmd_args.append("--ignore-pull-failures")
        self._run_command(*cmd_args, timeout=600)  # 10 min for pulls

    def build(self, no_cache: bool = False, pull: bool = False) -> None:
        """Build images for services.

        Args:
            no_cache: Whether to disable cache.
            pull: Whether to pull base images.
        """
        cmd_args = ["build"]
        if no_cache:
            cmd_args.append("--no-cache")
        if pull:
            cmd_args.append("--pull")
        self._run_command(*cmd_args, timeout=1200)  # 20 min for builds

    def exec(
        self,
        service_name: str,
        command: str | list[str],
        user: str | None = None,
        workdir: str | None = None,
    ) -> tuple[int, str, str]:
        """Execute a command in a running container.

        Args:
            service_name: Service to exec into.
            command: Command to execute.
            user: User to run command as.
            workdir: Working directory.

        Returns:
            Tuple of (exit_code, stdout, stderr).
        """
        cmd_args = ["exec", "-T"]  # -T to disable pseudo-TTY
        if user:
            cmd_args.extend(["-u", user])
        if workdir:
            cmd_args.extend(["-w", workdir])
        cmd_args.append(service_name)

        if isinstance(command, str):
            cmd_args.extend(["sh", "-c", command])
        else:
            cmd_args.extend(command)

        result = self._run_command(*cmd_args, check=False, timeout=300)
        return result.returncode, result.stdout, result.stderr

    def run(
        self,
        service_name: str,
        command: str | list[str] | None = None,
        remove: bool = True,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str, str]:
        """Run a one-off command in a new container.

        Args:
            service_name: Service to run.
            command: Command to run (uses default if None).
            remove: Whether to remove container after run.
            env: Additional environment variables.

        Returns:
            Tuple of (exit_code, stdout, stderr).
        """
        cmd_args = ["run", "-T"]  # -T to disable pseudo-TTY
        if remove:
            cmd_args.append("--rm")
        if env:
            for key, value in env.items():
                cmd_args.extend(["-e", f"{key}={value}"])
        cmd_args.append(service_name)

        if command:
            if isinstance(command, str):
                cmd_args.extend(["sh", "-c", command])
            else:
                cmd_args.extend(command)

        result = self._run_command(*cmd_args, check=False, timeout=600)
        return result.returncode, result.stdout, result.stderr

    def scale(self, service_name: str, replicas: int) -> None:
        """Scale a service to specified number of replicas.

        Args:
            service_name: Service to scale.
            replicas: Number of replicas.
        """
        self._run_command("up", "-d", "--scale", f"{service_name}={replicas}")

    @classmethod
    def check_docker_health(cls) -> DockerHealthCheck:
        """Check if Docker and Docker Compose are available.

        Returns:
            DockerHealthCheck with status information.
        """
        errors: list[str] = []
        docker_available = False
        compose_available = False
        docker_version = ""
        compose_version = ""

        # Check Docker
        try:
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                docker_available = True
                docker_version = result.stdout.strip()
            else:
                errors.append(f"Docker check failed: {result.stderr}")
        except FileNotFoundError:
            errors.append("Docker not found in PATH")
        except subprocess.TimeoutExpired:
            errors.append("Docker command timed out - is Docker running?")

        # Check Docker daemon is running
        if docker_available:
            try:
                result = subprocess.run(
                    ["docker", "info"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    errors.append("Docker daemon is not running")
                    docker_available = False
            except subprocess.TimeoutExpired:
                errors.append("Docker daemon not responding")
                docker_available = False

        # Check Docker Compose v2
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                compose_available = True
                compose_version = result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Fall back to v1 if v2 not available
        if not compose_available:
            try:
                result = subprocess.run(
                    ["docker-compose", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    compose_available = True
                    compose_version = result.stdout.strip()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                errors.append("Docker Compose not found (tried v2 and v1)")

        return DockerHealthCheck(
            docker_available=docker_available,
            compose_available=compose_available,
            docker_version=docker_version,
            compose_version=compose_version,
            errors=errors,
        )

    def get_config(self) -> dict[str, Any]:
        """Get the resolved docker compose configuration.

        Returns:
            Parsed docker-compose configuration.
        """
        result = self._run_command("config", check=False)
        if result.returncode != 0:
            return {}

        try:
            import yaml

            return yaml.safe_load(result.stdout)
        except Exception:
            return {}

    def get_service_ports(self, service_name: str) -> list[dict[str, Any]]:
        """Get published ports for a service.

        Args:
            service_name: Service name.

        Returns:
            List of port mappings.
        """
        result = self._run_command("port", service_name, check=False)
        if result.returncode != 0:
            return []

        ports = []
        for line in result.stdout.strip().split("\n"):
            if "->" in line:
                parts = line.split("->")
                if len(parts) == 2:
                    host_port = parts[0].strip().split(":")[-1]
                    container_port = parts[1].strip().split("/")[0]
                    protocol = parts[1].strip().split("/")[1] if "/" in parts[1] else "tcp"
                    ports.append({
                        "host_port": host_port,
                        "container_port": container_port,
                        "protocol": protocol,
                    })
        return ports
