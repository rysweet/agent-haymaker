"""Azure Platform implementation.

Extends FilePlatform with Azure deployment capabilities:
- Container App deployment via Azure CLI
- Service principal management
- Key Vault credential storage
- Service Bus event streaming (optional)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..workloads.file_platform import FilePlatform
from .az_cli import run_az, sanitize_az_error
from .config import AzureConfig
from .container_apps import (
    delete_container_app as _delete_container_app,
)
from .container_apps import (
    deploy_container_app as _deploy_container_app,
)
from .container_apps import (
    get_container_app_status as _get_container_app_status,
)
from .container_apps import (
    list_managed_resources as _list_managed_resources,
)

_logger = logging.getLogger(__name__)


class AzurePlatform(FilePlatform):
    """Platform implementation that deploys workloads to Azure.

    Extends FilePlatform (file-based state + local event bus) with
    Azure deployment capabilities. Uses Azure CLI for all Azure
    operations to minimize SDK dependencies.

    Requires: Azure CLI (`az`) installed and authenticated.

    Usage:
        config = AzureConfig.load()
        platform = AzurePlatform(config=config)

        # All FilePlatform methods still work (local state, events, credentials)
        # Plus Azure-specific operations:
        await platform.deploy_container_app(deployment_id, workload_name, image, env_vars)
        await platform.create_service_principal(name, scope)
        await platform.delete_container_app(deployment_id)
        await platform.validate_environment()
    """

    def __init__(self, config: AzureConfig) -> None:
        super().__init__()
        self._config = config

        # AzurePlatform REQUIRES Service Bus - no silent local fallback.
        # Use FilePlatform if you want local-only events.
        sb_cfg = config.service_bus
        if not sb_cfg or not (sb_cfg.connection_string or sb_cfg.namespace):
            raise ValueError(
                "AzurePlatform requires Service Bus configuration. "
                "Set HAYMAKER_SERVICEBUS_CONNECTION or HAYMAKER_SERVICEBUS_NAMESPACE, "
                "or add service_bus.connection_string to ~/.haymaker/azure.yaml. "
                "For local-only development, use FilePlatform instead."
            )

        from .service_bus import ServiceBusEventBus

        conn_str = sb_cfg.connection_string.get_secret_value() if sb_cfg.connection_string else None
        self._event_bus = ServiceBusEventBus(
            connection_string=conn_str,
            topic_name=sb_cfg.topic_name,
            namespace=sb_cfg.namespace,
        )

    @property
    def config(self) -> AzureConfig:
        return self._config

    # -----------------------------------------------------------------
    # Environment validation
    # -----------------------------------------------------------------

    async def validate_environment(self) -> dict[str, Any]:
        """Validate Azure environment is ready for deployment.

        Returns dict of check results: {"check": {"status": "passed"|"failed", "message": ...}}
        """
        results: dict[str, Any] = {}
        sub_id = self._config.subscription_id

        # Azure CLI auth
        rc, stdout, stderr = run_az(["account", "show"])
        if rc != 0:
            results["azure_auth"] = {"status": "failed", "message": stderr.strip()}
            return results
        account = json.loads(stdout)
        results["azure_auth"] = {
            "status": "passed",
            "message": f"Authenticated as {account.get('user', {}).get('name', 'unknown')}",
        }

        # Subscription
        rc, _, _ = run_az(["account", "show", "--subscription", sub_id])
        results["subscription"] = {
            "status": "passed" if rc == 0 else "failed",
            "message": f"Subscription {sub_id}",
        }

        # Resource group
        rg = self._config.resource_group
        rc, _, _ = run_az(["group", "show", "--name", rg, "--subscription", sub_id])
        results["resource_group"] = {
            "status": "passed" if rc == 0 else "create_needed",
            "message": f"Resource group {rg} {'exists' if rc == 0 else 'does not exist'}",
        }

        # Container registry (if configured)
        if self._config.container and self._config.container.registry:
            reg_url = self._config.container.registry
            public = ("mcr.microsoft.com", "docker.io", "ghcr.io")
            if any(reg_url.startswith(p) for p in public):
                results["container_registry"] = {
                    "status": "passed",
                    "message": f"Public registry {reg_url}",
                }
            else:
                rc, _, _ = run_az(["acr", "show", "--name", reg_url.split(".")[0]])
                results["container_registry"] = {
                    "status": "passed" if rc == 0 else "failed",
                    "message": f"Registry {reg_url}",
                }

        # Key Vault (if configured)
        if self._config.key_vault_url:
            vault = self._config.key_vault_url.split("//")[1].split(".")[0]
            rc, _, _ = run_az(["keyvault", "show", "--name", vault])
            results["key_vault"] = {
                "status": "passed" if rc == 0 else "failed",
                "message": f"Key Vault {vault}",
            }

        ok = all(r.get("status") in ("passed", "create_needed") for r in results.values())
        results["overall"] = {"status": "passed" if ok else "failed"}
        return results

    # -----------------------------------------------------------------
    # Resource group management
    # -----------------------------------------------------------------

    async def ensure_resource_group(self) -> bool:
        """Create resource group if it doesn't exist."""
        rc, _, _ = run_az(
            [
                "group",
                "create",
                "--name",
                self._config.resource_group,
                "--location",
                self._config.location,
                "--subscription",
                self._config.subscription_id,
                "--tags",
                "haymaker-managed=true",
            ]
        )
        return rc == 0

    # -----------------------------------------------------------------
    # Service Principal management
    # -----------------------------------------------------------------

    async def create_service_principal(self, name: str, scope: str | None = None) -> dict[str, str]:
        """Create a service principal with Contributor role.

        Args:
            name: Display name for the SP
            scope: RBAC scope (defaults to resource group)

        Returns:
            Dict with appId, password, tenant
        """
        if scope is None:
            scope = (
                f"/subscriptions/{self._config.subscription_id}"
                f"/resourceGroups/{self._config.resource_group}"
            )

        rc, stdout, stderr = run_az(
            [
                "ad",
                "sp",
                "create-for-rbac",
                "--name",
                name,
                "--role",
                "Contributor",
                "--scopes",
                scope,
            ]
        )
        if rc != 0:
            raise RuntimeError(f"Failed to create SP '{name}': {sanitize_az_error(stderr)}")

        sp_info = json.loads(stdout)
        _logger.info(
            "Created service principal: %s (appId=%s)",
            name,
            sp_info.get("appId"),
        )

        # Store secret in Key Vault if configured
        if self._config.key_vault_url and sp_info.get("password"):
            vault_name = self._config.key_vault_url.split("//")[1].split(".")[0]
            secret_name = name.replace(" ", "-").lower()
            rc, _, kv_stderr = run_az(
                [
                    "keyvault",
                    "secret",
                    "set",
                    "--vault-name",
                    vault_name,
                    "--name",
                    secret_name,
                    "--value",
                    "@-",
                ],
                stdin_data=sp_info["password"],
            )
            if rc != 0:
                _logger.warning(
                    "Failed to store SP secret in Key Vault: %s",
                    sanitize_az_error(kv_stderr),
                )
            else:
                _logger.info("Stored SP secret in Key Vault: %s", secret_name)

        # Redact password before returning -- callers should use Key Vault
        sp_info.pop("password", None)

        return sp_info

    async def delete_service_principal(self, app_id: str) -> bool:
        """Delete a service principal by app ID."""
        rc, _, stderr = run_az(["ad", "sp", "delete", "--id", app_id])
        if rc != 0:
            _logger.error("Failed to delete SP %s: %s", app_id, stderr)
            return False
        _logger.info("Deleted service principal: %s", app_id)
        return True

    # -----------------------------------------------------------------
    # Container App deployment
    # -----------------------------------------------------------------

    async def deploy_container_app(
        self,
        deployment_id: str,
        workload_name: str,
        image: str | None = None,
        env_vars: dict[str, str] | None = None,
        cpu: float | None = None,
        memory_gb: int | None = None,
    ) -> dict[str, Any]:
        """Deploy a workload as an Azure Container App.

        Delegates to container_apps.deploy_container_app().
        """
        return await _deploy_container_app(
            config=self._config,
            deployment_id=deployment_id,
            workload_name=workload_name,
            image=image,
            env_vars=env_vars,
            cpu=cpu,
            memory_gb=memory_gb,
            ensure_rg=self.ensure_resource_group,
        )

    async def get_container_app_status(self, app_name: str) -> dict[str, Any]:
        """Get the status of a container app."""
        return await _get_container_app_status(self._config, app_name)

    async def delete_container_app(self, app_name: str) -> bool:
        """Delete a container app."""
        return await _delete_container_app(self._config, app_name)

    async def list_managed_resources(self, deployment_id: str | None = None) -> list[dict]:
        """List all resources tagged as haymaker-managed."""
        return await _list_managed_resources(self._config, deployment_id)


__all__ = ["AzurePlatform"]
