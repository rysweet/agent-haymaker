"""WorkloadBase - Universal interface for all workloads.

All workload implementations must inherit from this base class
and implement the abstract methods. The platform provides universal
CLI commands that work with any workload through this interface.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Any

from .models import DeploymentState, DeploymentConfig, CleanupReport


class WorkloadBase(ABC):
    """Base class all workloads inherit from.

    Platform handles lifecycle commands universally through this interface.
    Workloads implement the specific operations for their domain.

    Universal CLI commands (provided by platform):
        haymaker deploy <workload> [options]  -> calls deploy()
        haymaker status <deployment-id>       -> calls get_status()
        haymaker list [--workload <name>]     -> calls list_deployments()
        haymaker logs <deployment-id>         -> calls get_logs()
        haymaker stop <deployment-id>         -> calls stop()
        haymaker start <deployment-id>        -> calls start()
        haymaker cleanup <deployment-id>      -> calls cleanup()

    Example implementation:
        class M365KnowledgeWorkerWorkload(WorkloadBase):
            name = "m365-knowledge-worker"

            async def deploy(self, config: DeploymentConfig) -> str:
                # Create Entra users, start activity generation
                return deployment_id

            async def cleanup(self, deployment_id: str) -> CleanupReport:
                # Delete Entra users, endpoints
                return CleanupReport(...)
    """

    # Workload name - must be unique across all workloads
    name: str = "base"

    # Platform services - injected by the platform
    _platform: Any = None

    def __init__(self, platform: Any = None) -> None:
        """Initialize workload with platform services.

        Args:
            platform: Platform instance providing state storage,
                     credentials, container orchestration, etc.
        """
        self._platform = platform

    # =========================================================================
    # REQUIRED: Workloads MUST implement these abstract methods
    # =========================================================================

    @abstractmethod
    async def deploy(self, config: DeploymentConfig) -> str:
        """Start a new deployment.

        This is the main entry point for running a workload. The workload
        should perform all necessary setup and start execution.

        Args:
            config: Deployment configuration including workload-specific options

        Returns:
            deployment_id: Unique identifier for this deployment

        Raises:
            DeploymentError: If deployment fails to start
        """
        ...

    @abstractmethod
    async def get_status(self, deployment_id: str) -> DeploymentState:
        """Get current deployment state.

        Returns the current state of a deployment including status,
        phase, and any relevant metadata.

        Args:
            deployment_id: ID of the deployment to query

        Returns:
            Current deployment state

        Raises:
            DeploymentNotFoundError: If deployment doesn't exist
        """
        ...

    @abstractmethod
    async def stop(self, deployment_id: str) -> bool:
        """Stop a running deployment.

        Gracefully stops execution. The deployment can be resumed
        later with start().

        Args:
            deployment_id: ID of the deployment to stop

        Returns:
            True if stopped successfully, False otherwise

        Raises:
            DeploymentNotFoundError: If deployment doesn't exist
        """
        ...

    @abstractmethod
    async def cleanup(self, deployment_id: str) -> CleanupReport:
        """Clean up all resources for a deployment.

        Removes all resources created by this deployment. This is
        a destructive operation - the deployment cannot be resumed
        after cleanup.

        Args:
            deployment_id: ID of the deployment to clean up

        Returns:
            Report of cleanup operations performed

        Raises:
            DeploymentNotFoundError: If deployment doesn't exist
        """
        ...

    @abstractmethod
    async def get_logs(
        self, deployment_id: str, follow: bool = False, lines: int = 100
    ) -> AsyncIterator[str]:
        """Stream logs for a deployment.

        Yields log lines from the deployment. Can optionally follow
        logs in real-time.

        Args:
            deployment_id: ID of the deployment
            follow: If True, continue streaming new logs
            lines: Number of historical lines to return first

        Yields:
            Log lines as strings

        Raises:
            DeploymentNotFoundError: If deployment doesn't exist
        """
        ...

    # =========================================================================
    # OPTIONAL: Workloads can override these with custom implementations
    # =========================================================================

    async def start(self, deployment_id: str) -> bool:
        """Resume a stopped deployment.

        Default implementation re-deploys with the same config.
        Override for custom resume behavior.

        Args:
            deployment_id: ID of the deployment to resume

        Returns:
            True if started successfully, False otherwise
        """
        state = await self.get_status(deployment_id)
        if state.status == "running":
            return True  # Already running

        # Re-deploy with same config
        config = DeploymentConfig(
            workload_name=self.name,
            workload_config=state.config,
        )
        await self.deploy(config)
        return True

    async def list_deployments(self) -> list[DeploymentState]:
        """List all deployments for this workload.

        Default implementation uses platform state storage.
        Override if workload manages its own state.

        Returns:
            List of deployment states
        """
        if self._platform is None:
            return []

        return await self._platform.list_deployments(self.name)

    async def validate_config(self, config: DeploymentConfig) -> list[str]:
        """Validate deployment configuration before deploy.

        Override to add workload-specific validation.

        Args:
            config: Configuration to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        if not config.workload_name:
            errors.append("workload_name is required")

        return errors

    # =========================================================================
    # Utility methods available to all workloads
    # =========================================================================

    async def save_state(self, state: DeploymentState) -> None:
        """Persist deployment state via platform storage."""
        if self._platform:
            await self._platform.save_deployment_state(state)

    async def load_state(self, deployment_id: str) -> DeploymentState | None:
        """Load deployment state from platform storage."""
        if self._platform:
            return await self._platform.load_deployment_state(deployment_id)
        return None

    async def get_credential(self, name: str) -> str | None:
        """Get a credential from platform credential storage (Key Vault)."""
        if self._platform:
            return await self._platform.get_credential(name)
        return None

    def log(self, message: str, level: str = "INFO") -> None:
        """Log a message via platform logging."""
        if self._platform:
            self._platform.log(message, level=level, workload=self.name)


class DeploymentError(Exception):
    """Raised when deployment fails."""

    pass


class DeploymentNotFoundError(Exception):
    """Raised when deployment doesn't exist."""

    pass
