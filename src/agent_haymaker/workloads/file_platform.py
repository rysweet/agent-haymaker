"""File-based Platform implementation.

Stores deployment state as JSON files on the local filesystem.
Reads credentials from environment variables. Logs via stdlib logging.

Public API (the "studs"):
    FilePlatform: Concrete Platform implementation using local files
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from .models import DeploymentState

_logger = logging.getLogger(__name__)

# Pattern for valid deployment IDs: alphanumeric, hyphens, underscores, dots
_SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def _sanitize_deployment_id(deployment_id: str) -> str:
    """Sanitize a deployment ID to prevent path traversal.

    Args:
        deployment_id: Raw deployment ID

    Returns:
        Sanitized deployment ID safe for use as a filename

    Raises:
        ValueError: If deployment_id is empty or contains path traversal
    """
    if not deployment_id:
        raise ValueError("deployment_id must not be empty")

    # Reject any path separator characters
    if "/" in deployment_id or "\\" in deployment_id:
        raise ValueError(f"deployment_id contains path separators: {deployment_id!r}")

    # Reject path traversal patterns
    if ".." in deployment_id:
        raise ValueError(f"deployment_id contains path traversal: {deployment_id!r}")

    # Validate against safe pattern
    if not _SAFE_ID_PATTERN.match(deployment_id):
        raise ValueError(
            f"deployment_id contains invalid characters: {deployment_id!r}. "
            "Only alphanumeric, hyphens, underscores, and dots are allowed."
        )

    return deployment_id


class FilePlatform:
    """File-based Platform implementation.

    Stores deployment state as JSON in ~/.haymaker/state/{deployment_id}.json.
    Reads credentials from environment variables.
    Logs via stdlib logging.

    This implementation satisfies the Platform protocol without requiring
    any cloud services, making it suitable for local development and testing.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        """Initialize FilePlatform.

        Args:
            state_dir: Directory for state files. Defaults to ~/.haymaker/state/
        """
        if state_dir is None:
            state_dir = Path.home() / ".haymaker" / "state"
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _state_path(self, deployment_id: str) -> Path:
        """Get the file path for a deployment's state.

        Args:
            deployment_id: Deployment identifier (will be sanitized)

        Returns:
            Path to the state JSON file
        """
        safe_id = _sanitize_deployment_id(deployment_id)
        return self._state_dir / f"{safe_id}.json"

    async def save_deployment_state(self, state: DeploymentState) -> None:
        """Persist deployment state to a JSON file.

        Args:
            state: Deployment state to save
        """
        path = self._state_path(state.deployment_id)
        data = state.model_dump_json(indent=2)
        path.write_text(data)
        _logger.debug("Saved deployment state to %s", path)

    async def load_deployment_state(self, deployment_id: str) -> DeploymentState | None:
        """Load deployment state from a JSON file.

        Args:
            deployment_id: ID of the deployment to load

        Returns:
            DeploymentState if found, None otherwise
        """
        path = self._state_path(deployment_id)
        if not path.exists():
            _logger.debug("No state file found at %s", path)
            return None

        raw = path.read_text()
        return DeploymentState.model_validate_json(raw)

    async def list_deployments(self, workload_name: str) -> list[DeploymentState]:
        """List all deployments for a given workload.

        Scans all state files and filters by workload_name.

        Args:
            workload_name: Name of the workload to filter by

        Returns:
            List of matching deployment states
        """
        results: list[DeploymentState] = []
        if not self._state_dir.exists():
            return results

        for state_file in self._state_dir.glob("*.json"):
            try:
                raw = state_file.read_text()
                state = DeploymentState.model_validate_json(raw)
                if state.workload_name == workload_name:
                    results.append(state)
            except Exception:
                _logger.warning("Failed to read state file %s", state_file, exc_info=True)

        return results

    async def get_credential(self, name: str) -> str | None:
        """Get a credential from environment variables.

        Looks up the credential by name as an environment variable.
        The name is converted to uppercase with hyphens replaced by underscores.

        Args:
            name: Credential name (e.g., "azure-tenant-id" -> AZURE_TENANT_ID)

        Returns:
            Credential value or None if not found
        """
        env_key = name.upper().replace("-", "_")
        value = os.environ.get(env_key)
        if value is None:
            _logger.debug("Credential %r (env: %s) not found", name, env_key)
        return value

    def log(self, message: str, level: str = "INFO", workload: str = "") -> None:
        """Log a message via stdlib logging.

        Args:
            message: Log message
            level: Log level name (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            workload: Workload name for logger context
        """
        logger_name = f"haymaker.workload.{workload}" if workload else "haymaker"
        logger = logging.getLogger(logger_name)
        log_level = getattr(logging, level.upper(), logging.INFO)
        logger.log(log_level, message)


__all__ = ["FilePlatform"]
