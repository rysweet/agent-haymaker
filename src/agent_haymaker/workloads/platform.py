"""Platform protocol - defines the contract workloads expect from the platform.

Public API (the "studs"):
    Platform: Protocol defining platform services available to workloads
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .models import DeploymentState


@runtime_checkable
class Platform(Protocol):
    """Protocol defining platform services available to workloads.

    Workloads receive a Platform instance at construction time and use it
    for state persistence, credential management, and logging.

    Implementations must provide all methods defined here.
    """

    async def save_deployment_state(self, state: DeploymentState) -> None:
        """Persist deployment state."""
        ...

    async def load_deployment_state(self, deployment_id: str) -> DeploymentState | None:
        """Load deployment state by ID."""
        ...

    async def list_deployments(self, workload_name: str) -> list[DeploymentState]:
        """List all deployments for a workload."""
        ...

    async def get_credential(self, name: str) -> str | None:
        """Get a credential by name (e.g., from Key Vault)."""
        ...

    def log(self, message: str, level: str = "INFO", workload: str = "") -> None:
        """Log a message."""
        ...


__all__ = ["Platform"]
