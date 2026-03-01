"""Deployment lookup helpers for Agent Haymaker CLI.

Provides cached deployment lookup across all registered workloads.
"""

import click

from ..workloads.base import DeploymentNotFoundError, WorkloadBase
from ..workloads.models import DeploymentState
from ..workloads.registry import WorkloadRegistry

# Module-level cache: deployment_id -> workload_name
# Provides O(1) lookup on repeated access to the same deployment.
_deployment_index: dict[str, str] = {}


async def find_deployment_async(
    registry: WorkloadRegistry, deployment_id: str
) -> tuple[WorkloadBase, DeploymentState]:
    """Find the workload and state for a deployment ID.

    Checks the module-level _deployment_index cache first for O(1) lookup,
    falling back to scanning all registered workloads on cache miss.

    Args:
        registry: Workload registry to search
        deployment_id: Deployment ID to find

    Returns:
        Tuple of (workload, state)

    Raises:
        click.ClickException: If deployment not found in any workload
    """
    # Check cache first for O(1) lookup
    if deployment_id in _deployment_index:
        cached_name = _deployment_index[deployment_id]
        workload = registry.get_workload(cached_name)
        if workload:
            try:
                state = await workload.get_status(deployment_id)
                return workload, state
            except DeploymentNotFoundError:
                # Stale cache entry - remove and fall through to scan
                del _deployment_index[deployment_id]

    # Cache miss: scan all workloads
    for name in registry.list_workloads():
        workload = registry.get_workload(name)
        if workload:
            try:
                state = await workload.get_status(deployment_id)
                # Cache the result for future lookups
                _deployment_index[deployment_id] = name
                return workload, state
            except DeploymentNotFoundError:
                continue
    raise click.ClickException(f"Deployment '{deployment_id}' not found.")
