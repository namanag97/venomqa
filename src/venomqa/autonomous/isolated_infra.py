"""Isolated infrastructure - spin up test containers that don't touch user's real database."""

from __future__ import annotations

import hashlib
import os
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ServiceEndpoint:
    """Endpoint information for a running service."""

    name: str
    host: str
    port: int
    original_port: int

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


class IsolatedInfrastructureManager:
    """Creates ISOLATED test infrastructure from user's docker-compose.

    Key principles:
    - Never touch user's real database
    - Use random high ports to avoid conflicts
    - Create anonymous volumes (no persistence)
    - Clean up completely on teardown
    """

    def __init__(
        self,
        compose_path: Path,
        project_name: str | None = None,
    ) -> None:
        self.compose_path = Path(compose_path)
        self._original_config: dict[str, Any] = {}
        self._test_config: dict[str, Any] = {}
        self._test_compose_path: Path | None = None
        self._endpoints: dict[str, ServiceEndpoint] = {}

        # Generate unique project name to isolate from user's real containers
        hash_input = f"{compose_path}:{os.getpid()}:{random.random()}"
        short_hash = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        self.project_name = project_name or f"venomqa_test_{short_hash}"

    def create_test_compose(self) -> Path:
        """Create an isolated docker-compose for testing.

        Modifications:
        1. Random high ports (avoid conflicts with running services)
        2. Anonymous volumes (no data persistence)
        3. Unique network name
        4. Test-specific environment variables
        """
        with open(self.compose_path) as f:
            self._original_config = yaml.safe_load(f)

        self._test_config = self._transform_for_testing(self._original_config)

        # Write to temp file
        fd, path = tempfile.mkstemp(suffix=".yml", prefix="venomqa_compose_")
        os.close(fd)
        self._test_compose_path = Path(path)

        with open(self._test_compose_path, "w") as f:
            yaml.dump(self._test_config, f, default_flow_style=False)

        return self._test_compose_path

    def _transform_for_testing(self, config: dict[str, Any]) -> dict[str, Any]:
        """Transform compose config for isolated testing."""
        result = {
            "services": {},
        }

        # Remove version key (deprecated in compose v2)
        # Don't copy networks/volumes from original - we'll create anonymous ones

        services = config.get("services", {})

        for name, service in services.items():
            test_service = self._transform_service(name, service)
            result["services"][name] = test_service

        return result

    def _transform_service(self, name: str, service: dict[str, Any]) -> dict[str, Any]:
        """Transform a single service for testing."""
        result: dict[str, Any] = {}

        # Copy essential fields
        if "image" in service:
            result["image"] = service["image"]
        if "build" in service:
            result["build"] = service["build"]
        if "command" in service:
            result["command"] = service["command"]
        if "healthcheck" in service:
            result["healthcheck"] = service["healthcheck"]

        # Transform ports to random high ports
        if "ports" in service:
            result["ports"] = self._randomize_ports(name, service["ports"])

        # Transform environment - add test markers
        env = service.get("environment", {})
        if isinstance(env, list):
            env = dict(item.split("=", 1) for item in env if "=" in item)
        env = dict(env)  # Copy
        env["VENOMQA_TEST_MODE"] = "true"
        result["environment"] = env

        # Remove named volumes, use anonymous
        if "volumes" in service:
            result["volumes"] = self._anonymize_volumes(service["volumes"])

        # Keep depends_on
        if "depends_on" in service:
            result["depends_on"] = service["depends_on"]

        return result

    def _randomize_ports(self, service_name: str, ports: list) -> list[str]:
        """Replace host ports with random high ports."""
        result = []

        for port in ports:
            if isinstance(port, str):
                if ":" in port:
                    parts = port.split(":")
                    container_port = parts[-1]
                    original_host_port = int(parts[0]) if parts[0].isdigit() else 0

                    # Use random high port
                    new_host_port = random.randint(30000, 60000)
                    result.append(f"{new_host_port}:{container_port}")

                    # Track endpoint
                    self._endpoints[service_name] = ServiceEndpoint(
                        name=service_name,
                        host="localhost",
                        port=new_host_port,
                        original_port=original_host_port or int(container_port.split("/")[0]),
                    )
                else:
                    # Just container port, assign random host port
                    container_port = port
                    new_host_port = random.randint(30000, 60000)
                    result.append(f"{new_host_port}:{container_port}")

                    self._endpoints[service_name] = ServiceEndpoint(
                        name=service_name,
                        host="localhost",
                        port=new_host_port,
                        original_port=int(port.split("/")[0]),
                    )
            elif isinstance(port, dict):
                # Complex port definition
                target = port.get("target", 8000)
                new_host_port = random.randint(30000, 60000)
                result.append(f"{new_host_port}:{target}")

                self._endpoints[service_name] = ServiceEndpoint(
                    name=service_name,
                    host="localhost",
                    port=new_host_port,
                    original_port=port.get("published", target),
                )

        return result

    def _anonymize_volumes(self, volumes: list) -> list[str]:
        """Convert named volumes to anonymous volumes."""
        result = []

        for vol in volumes:
            if isinstance(vol, str):
                if ":" in vol:
                    parts = vol.split(":")
                    # Keep only the container path (creates anonymous volume)
                    container_path = parts[1] if len(parts) > 1 else parts[0]
                    result.append(container_path)
                else:
                    result.append(vol)
            elif isinstance(vol, dict):
                # Just keep target (container path)
                if "target" in vol:
                    result.append(vol["target"])

        return result

    def start(self, timeout: float = 120.0) -> dict[str, ServiceEndpoint]:
        """Start isolated test containers."""
        if not self._test_compose_path:
            self.create_test_compose()

        from venomqa.infra.docker import DockerInfrastructureManager

        self._docker = DockerInfrastructureManager(
            compose_file=str(self._test_compose_path),
            project_name=self.project_name,
        )

        self._docker.start()

        if not self._docker.wait_healthy(timeout=timeout):
            raise RuntimeError("Test containers failed to become healthy")

        # Update endpoints with actual ports from running containers
        self._update_endpoints_from_running()

        return self._endpoints

    def _update_endpoints_from_running(self) -> None:
        """Update endpoints from running containers (in case ports differ)."""
        try:
            for service_name in self._endpoints:
                ports = self._docker.get_service_ports(service_name)
                if ports:
                    self._endpoints[service_name].port = int(ports[0]["host_port"])
        except Exception:
            pass  # Keep estimated ports if lookup fails

    def get_endpoint(self, service_name: str) -> ServiceEndpoint | None:
        """Get endpoint for a specific service."""
        return self._endpoints.get(service_name)

    def get_database_dsn(self, db_service: str = "postgres") -> str | None:
        """Get connection string for test database."""
        endpoint = self._endpoints.get(db_service)
        if not endpoint:
            # Try common names
            for name in ["postgres", "db", "database", "mysql"]:
                if name in self._endpoints:
                    endpoint = self._endpoints[name]
                    break

        if not endpoint:
            return None

        # Detect database type from service name
        if "postgres" in db_service.lower():
            return f"postgresql://postgres:postgres@localhost:{endpoint.port}/postgres"
        elif "mysql" in db_service.lower():
            return f"mysql://root:root@localhost:{endpoint.port}/test"

        return None

    def teardown(self, remove_volumes: bool = True) -> None:
        """Stop and remove all test containers."""
        if hasattr(self, "_docker"):
            try:
                self._docker.stop(remove_volumes=remove_volumes)
            except Exception:
                pass

        # Clean up temp compose file
        if self._test_compose_path and self._test_compose_path.exists():
            try:
                self._test_compose_path.unlink()
            except Exception:
                pass
