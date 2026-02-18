"""Project discovery - auto-detect docker-compose and OpenAPI specs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ServiceInfo:
    """Information about a Docker Compose service."""

    name: str
    image: str | None = None
    ports: list[str] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    healthcheck: dict[str, Any] | None = None
    volumes: list[str] = field(default_factory=list)


@dataclass
class DatabaseConfig:
    """Detected database configuration."""

    type: str  # postgres, mysql, sqlite, redis
    port: int
    user: str = "postgres"
    password: str = "postgres"
    database: str = "testdb"

    @property
    def dsn(self) -> str:
        """Generate connection string."""
        if self.type == "postgres":
            return f"postgresql://{self.user}:{self.password}@localhost:{self.port}/{self.database}"
        elif self.type == "mysql":
            return f"mysql://{self.user}:{self.password}@localhost:{self.port}/{self.database}"
        return ""


class ProjectDiscovery:
    """Discovers project configuration from the current directory."""

    COMPOSE_FILES = [
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
        "docker-compose.qa.yml",
    ]

    OPENAPI_PATTERNS = [
        "openapi.yaml",
        "openapi.yml",
        "openapi.json",
        "swagger.yaml",
        "swagger.yml",
        "swagger.json",
        "api/openapi.yaml",
        "api/openapi.json",
        "spec/openapi.yaml",
        "spec/openapi.json",
        "docs/openapi.yaml",
        "docs/openapi.json",
    ]

    def __init__(self, project_dir: Path | str = ".") -> None:
        self.project_dir = Path(project_dir).resolve()
        self._compose_path: Path | None = None
        self._openapi_path: Path | None = None
        self._services: dict[str, ServiceInfo] = {}

    def find_compose_file(self) -> Path | None:
        """Find docker-compose file in project."""
        if self._compose_path:
            return self._compose_path

        for name in self.COMPOSE_FILES:
            path = self.project_dir / name
            if path.exists():
                self._compose_path = path
                return path
        return None

    def find_openapi_spec(self) -> Path | None:
        """Find OpenAPI/Swagger spec in project."""
        if self._openapi_path:
            return self._openapi_path

        for pattern in self.OPENAPI_PATTERNS:
            path = self.project_dir / pattern
            if path.exists():
                self._openapi_path = path
                return path
        return None

    def has_compose_file(self) -> bool:
        """Check if project has a compose file."""
        return self.find_compose_file() is not None

    def has_openapi_spec(self) -> bool:
        """Check if project has an OpenAPI spec."""
        return self.find_openapi_spec() is not None

    def parse_compose_services(self) -> dict[str, ServiceInfo]:
        """Parse services from docker-compose file."""
        if self._services:
            return self._services

        compose_path = self.find_compose_file()
        if not compose_path:
            return {}

        with open(compose_path) as f:
            data = yaml.safe_load(f)

        services = data.get("services", {})

        for name, config in services.items():
            # Parse ports
            ports = []
            for port in config.get("ports", []):
                if isinstance(port, str):
                    ports.append(port)
                elif isinstance(port, dict):
                    ports.append(f"{port.get('published', '')}:{port.get('target', '')}")

            # Parse environment
            env = {}
            env_config = config.get("environment", {})
            if isinstance(env_config, dict):
                env = env_config
            elif isinstance(env_config, list):
                for item in env_config:
                    if "=" in item:
                        k, v = item.split("=", 1)
                        env[k] = v

            # Parse depends_on
            depends = config.get("depends_on", [])
            if isinstance(depends, dict):
                depends = list(depends.keys())

            self._services[name] = ServiceInfo(
                name=name,
                image=config.get("image"),
                ports=ports,
                environment=env,
                depends_on=depends,
                healthcheck=config.get("healthcheck"),
                volumes=config.get("volumes", []),
            )

        return self._services

    def detect_database(self) -> DatabaseConfig | None:
        """Detect database from compose services."""
        services = self.parse_compose_services()

        for name, info in services.items():
            image = (info.image or "").lower()

            # PostgreSQL
            if "postgres" in image or "postgres" in name:
                port = 5432
                for p in info.ports:
                    if "5432" in p:
                        port = int(p.split(":")[0])
                        break
                return DatabaseConfig(
                    type="postgres",
                    port=port,
                    user=info.environment.get("POSTGRES_USER", "postgres"),
                    password=info.environment.get("POSTGRES_PASSWORD", "postgres"),
                    database=info.environment.get("POSTGRES_DB", "testdb"),
                )

            # MySQL
            if "mysql" in image or "mysql" in name:
                port = 3306
                for p in info.ports:
                    if "3306" in p:
                        port = int(p.split(":")[0])
                        break
                return DatabaseConfig(
                    type="mysql",
                    port=port,
                    user=info.environment.get("MYSQL_USER", "root"),
                    password=info.environment.get("MYSQL_PASSWORD", "root"),
                    database=info.environment.get("MYSQL_DATABASE", "testdb"),
                )

        return None

    def detect_api_service(self) -> ServiceInfo | None:
        """Detect the main API service."""
        services = self.parse_compose_services()

        # Priority 1: Service named "api" or "app"
        for name in ["api", "app", "web", "backend", "server"]:
            if name in services:
                return services[name]

        # Priority 2: Service with port 8000, 3000, 5000
        api_ports = ["8000", "3000", "5000", "8080", "80"]
        for info in services.values():
            for port in info.ports:
                for api_port in api_ports:
                    if api_port in port:
                        return info

        # Priority 3: Service that depends on database
        db_names = ["postgres", "mysql", "db", "database", "redis"]
        for info in services.values():
            for dep in info.depends_on:
                if any(db in dep.lower() for db in db_names):
                    return info

        return None

    def get_api_port(self) -> int:
        """Get the API service's exposed port."""
        api = self.detect_api_service()
        if not api:
            return 8000

        for port_mapping in api.ports:
            if ":" in port_mapping:
                host_port = port_mapping.split(":")[0]
                try:
                    return int(host_port)
                except ValueError:
                    pass

        return 8000
