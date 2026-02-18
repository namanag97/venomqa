"""Runtime Context - Service lifecycle and orchestration.

The Runtime context is responsible for:
- Coordinating the full test lifecycle (init -> discover -> explore -> report -> cleanup)
- Tracking running services and their health status
- Providing a high-level API for running explorations

Core abstractions:
- Orchestrator: Coordinates the full exploration lifecycle
- Service: A running service (name, type, endpoint, health)
- HealthStatus: Service health states
"""

from venomqa.runtime.orchestrator import Orchestrator
from venomqa.runtime.service import HealthStatus, Service, ServiceType

__all__ = [
    "Orchestrator",
    "Service",
    "ServiceType",
    "HealthStatus",
]
