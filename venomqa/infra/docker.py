"""Docker/docker-compose backend for infrastructure management."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from venomqa.infra.base import BaseInfrastructureManager


class DockerInfrastructureManager(BaseInfrastructureManager):
    """Infrastructure manager using docker compose."""

    def __init__(
        self,
        compose_file: str | Path | None = None,
        project_name: str | None = None,
        services: list[str] | None = None,
    ) -> None:
        super().__init__(
            compose_file=str(compose_file) if compose_file else None,
            project_name=project_name,
        )
        self.services = services or []
        self._compose_cmd = self._detect_compose_command()

    def _detect_compose_command(self) -> list[str]:
        """Detect whether to use 'docker compose' or 'docker-compose'."""
        try:
            subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                check=True,
            )
            return ["docker", "compose"]
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ["docker-compose"]

    def _build_command(self, *args: str) -> list[str]:
        """Build a docker compose command with common options."""
        cmd = self._compose_cmd.copy()
        if self.compose_file:
            cmd.extend(["-f", self.compose_file])
        if self.project_name:
            cmd.extend(["-p", self.project_name])
        cmd.extend(args)
        return cmd

    def _run_command(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a docker compose command."""
        cmd = self._build_command(*args)
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

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
