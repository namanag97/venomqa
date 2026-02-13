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

    def start(self) -> None:
        """Spin up services via docker compose."""
        cmd_args = ["up", "-d"]
        if self.services:
            cmd_args.extend(self.services)
        self._run_command(*cmd_args)
        self._running = True

    def stop(self) -> None:
        """Tear down services."""
        self._run_command("down")
        self._running = False

    def wait_healthy(self, timeout: float = 60.0) -> bool:
        """Wait for services to be healthy.

        Uses docker compose ps to check service health status.
        """
        start_time = time.time()
        poll_interval = 1.0

        while time.time() - start_time < timeout:
            try:
                result = self._run_command("ps", "--format", "json", check=False)
                if result.returncode == 0 and self._check_health(result.stdout):
                    return True
            except Exception:
                pass
            time.sleep(poll_interval)

        return False

    def _check_health(self, ps_output: str) -> bool:
        """Check if all services are healthy from ps output."""
        import json

        if not ps_output.strip():
            return False

        try:
            lines = ps_output.strip().split("\n")
            for line in lines:
                if not line.strip():
                    continue
                service = json.loads(line)
                health = service.get("Health", "")
                if health and health.lower() != "healthy":
                    return False
                state = service.get("State", "")
                if state and state.lower() != "running":
                    return False
            return len(lines) > 0
        except json.JSONDecodeError:
            result = self._run_command("ps", "--format", "{{.Status}}", check=False)
            if result.returncode != 0:
                return False
            return "running" in result.stdout.lower() and "unhealthy" not in result.stdout.lower()

    def logs(self, service_name: str) -> str:
        """Get logs from a specific service."""
        result = self._run_command("logs", service_name, check=False)
        return result.stdout

    def is_running(self) -> bool:
        """Check if infrastructure is up by inspecting container status."""
        try:
            result = self._run_command("ps", "-q", check=False)
            return bool(result.stdout.strip())
        except Exception:
            return False

    def restart(self) -> None:
        """Restart all services."""
        self._run_command("restart")

    def pull(self) -> None:
        """Pull images for services."""
        self._run_command("pull")

    def build(self) -> None:
        """Build images for services."""
        self._run_command("build")
