"""Container App deployment operations via Azure CLI.

Standalone async functions for managing Azure Container Apps.
Used by AzurePlatform but decoupled from the class hierarchy.

Public API:
    deploy_container_app: Create/update a Container App
    get_container_app_status: Query provisioning state
    delete_container_app: Remove a Container App
    list_managed_resources: List haymaker-tagged resources
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .az_cli import run_az, sanitize_az_error, validate_resource_name
from .config import AzureConfig

_logger = logging.getLogger(__name__)


async def deploy_container_app(
    config: AzureConfig,
    deployment_id: str,
    workload_name: str,
    image: str | None = None,
    env_vars: dict[str, str] | None = None,
    cpu: float | None = None,
    memory_gb: int | None = None,
    *,
    ensure_rg: Any | None = None,
) -> dict[str, Any]:
    """Deploy a workload as an Azure Container App.

    Args:
        config: Azure configuration
        deployment_id: Unique deployment identifier
        workload_name: Workload name (used for app naming)
        image: Container image (defaults to config)
        env_vars: Environment variables to inject
        cpu: CPU cores (defaults to config)
        memory_gb: Memory in GB (defaults to config)
        ensure_rg: Async callable to ensure resource group exists.
                   If None, resource group must already exist.

    Returns:
        Dict with container app details (fqdn, resourceId, etc.)
    """
    cfg = config.container
    if cfg is None and image is None:
        raise ValueError(
            "No container configuration. Set container config or pass image parameter."
        )

    resolved_image = image or (cfg.image if cfg else "")
    resolved_cpu = cpu or (cfg.cpu_cores if cfg else 1.0)
    resolved_memory = memory_gb or (cfg.memory_gb if cfg else 4)
    app_name = validate_resource_name(f"{workload_name}-{deployment_id[:8]}", field="app_name")

    if ensure_rg is not None:
        await ensure_rg()

    cmd = [
        "containerapp",
        "create",
        "--name",
        app_name,
        "--resource-group",
        config.resource_group,
        "--subscription",
        config.subscription_id,
        "--image",
        resolved_image,
        "--cpu",
        str(resolved_cpu),
        "--memory",
        f"{resolved_memory}Gi",
        "--min-replicas",
        "1",
        "--max-replicas",
        "1",
        "--tags",
        f"haymaker-managed=true deployment-id={deployment_id} workload={workload_name}",
    ]

    if cfg and cfg.environment_name:
        cmd.extend(["--environment", cfg.environment_name])

    if cfg and cfg.registry:
        public_registries = ("mcr.microsoft.com", "docker.io", "ghcr.io")
        if not any(cfg.registry.startswith(pub) for pub in public_registries):
            cmd.extend(["--registry-server", cfg.registry])

    if env_vars:
        cmd.append("--env-vars")
        cmd.extend(f"{k}={v}" for k, v in env_vars.items())

    rc, stdout, stderr = run_az(cmd)
    if rc != 0:
        msg = f"Failed to deploy container app '{app_name}': {sanitize_az_error(stderr)}"
        raise RuntimeError(msg)

    result = json.loads(stdout) if stdout.strip() else {}
    _logger.info(
        "Deployed container app: %s (image=%s, cpu=%s, mem=%sGi)",
        app_name,
        resolved_image,
        resolved_cpu,
        resolved_memory,
    )
    props = result.get("properties") or {}
    config_section = props.get("configuration") or {}
    ingress = config_section.get("ingress") or {}
    return {
        "app_name": app_name,
        "resource_id": result.get("id", ""),
        "fqdn": ingress.get("fqdn", ""),
        "provisioning_state": props.get("provisioningState", ""),
    }


async def get_container_app_status(config: AzureConfig, app_name: str) -> dict[str, Any]:
    """Get the status of a container app."""
    rc, stdout, stderr = run_az(
        [
            "containerapp",
            "show",
            "--name",
            app_name,
            "--resource-group",
            config.resource_group,
            "--subscription",
            config.subscription_id,
        ]
    )
    if rc != 0:
        return {"status": "not_found", "error": stderr.strip()}
    data = json.loads(stdout)
    return {
        "status": data.get("properties", {}).get("provisioningState", "Unknown"),
        "running_status": data.get("properties", {}).get("runningStatus", "Unknown"),
    }


async def delete_container_app(config: AzureConfig, app_name: str) -> bool:
    """Delete a container app."""
    rc, _, stderr = run_az(
        [
            "containerapp",
            "delete",
            "--name",
            app_name,
            "--resource-group",
            config.resource_group,
            "--subscription",
            config.subscription_id,
            "--yes",
        ]
    )
    if rc != 0:
        _logger.error("Failed to delete container app %s: %s", app_name, stderr)
        return False
    _logger.info("Deleted container app: %s", app_name)
    return True


async def list_managed_resources(
    config: AzureConfig, deployment_id: str | None = None
) -> list[dict]:
    """List all resources tagged as haymaker-managed."""
    cmd = [
        "resource",
        "list",
        "--resource-group",
        config.resource_group,
        "--subscription",
        config.subscription_id,
        "--tag",
        "haymaker-managed=true",
    ]
    if deployment_id:
        cmd.extend(["--tag", f"deployment-id={deployment_id}"])

    rc, stdout, _ = run_az(cmd)
    if rc != 0:
        return []
    return json.loads(stdout) if stdout.strip() else []


__all__ = [
    "deploy_container_app",
    "get_container_app_status",
    "delete_container_app",
    "list_managed_resources",
]
