"""Shared provisioning logic for Azure deployments.

Used by both the CLI ``azure deploy`` command and the orchestration
workflow's provisioning phase so the SP + container deploy sequence
lives in exactly one place.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

_logger = logging.getLogger(__name__)


async def provision_workload(
    platform: Any,
    workload_name: str,
    image: str | None = None,
    env_vars: dict[str, str] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Provision a single workload: create SP, deploy container.

    Args:
        platform: AzurePlatform instance.
        workload_name: Name of the workload.
        image: Container image (optional, uses platform config default).
        env_vars: Additional environment variables.
        run_id: Optional orchestration run ID injected as env var.

    Returns:
        Dict with deployment_id, workload_name, app_name, sp_app_id, status.
    """
    dep_id = f"{workload_name}-{uuid4().hex[:8]}"
    all_env_vars = dict(env_vars or {})

    # Create service principal
    sp_name = f"haymaker-{dep_id}"
    _logger.info("Creating service principal: %s", sp_name)
    sp_info = await platform.create_service_principal(sp_name)

    # Inject credentials into container env
    all_env_vars.update(
        {
            "AZURE_TENANT_ID": platform.config.tenant_id,
            "AZURE_CLIENT_ID": sp_info.get("appId", ""),
            "AZURE_CLIENT_SECRET": sp_info.get("password", ""),
            "HAYMAKER_DEPLOYMENT_ID": dep_id,
        }
    )
    if run_id:
        all_env_vars["HAYMAKER_RUN_ID"] = run_id
        all_env_vars["HAYMAKER_WORKLOAD_NAME"] = workload_name

    # Deploy container app
    _logger.info("Deploying container app: %s", dep_id)
    container_info = await platform.deploy_container_app(
        deployment_id=dep_id,
        workload_name=workload_name,
        image=image,
        env_vars=all_env_vars,
    )

    return {
        "deployment_id": dep_id,
        "workload_name": workload_name,
        "app_name": container_info.get("app_name", ""),
        "sp_app_id": sp_info.get("appId", ""),
        "status": "deployed",
    }
