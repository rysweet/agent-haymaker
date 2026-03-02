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
import subprocess
from typing import Any

from ..workloads.file_platform import FilePlatform
from .config import AzureConfig

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

        # Replace local event bus with Service Bus dual-write when configured
        sb_cfg = config.service_bus
        if sb_cfg and (sb_cfg.connection_string or sb_cfg.namespace):
            from .service_bus import ServiceBusEventBus

            conn_str = (
                sb_cfg.connection_string.get_secret_value() if sb_cfg.connection_string else None
            )
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

        Checks Azure CLI auth, subscription access, resource group exists,
        and container registry accessibility.

        Returns:
            Dict with check results: {"check_name": {"status": "passed"|"failed", "message": "..."}}
        """
        results: dict[str, Any] = {}

        # Check Azure CLI is available and authenticated
        rc, stdout, stderr = self._az_cli(["account", "show"])
        if rc == 0:
            account = json.loads(stdout)
            results["azure_auth"] = {
                "status": "passed",
                "message": f"Authenticated as {account.get('user', {}).get('name', 'unknown')}",
            }
        else:
            results["azure_auth"] = {
                "status": "failed",
                "message": stderr.strip(),
            }
            return results  # No point continuing if not authenticated

        # Check subscription
        rc, stdout, _ = self._az_cli(
            [
                "account",
                "show",
                "--subscription",
                self._config.subscription_id,
            ]
        )
        results["subscription"] = {
            "status": "passed" if rc == 0 else "failed",
            "message": f"Subscription {self._config.subscription_id}",
        }

        # Check resource group
        rc, stdout, _ = self._az_cli(
            [
                "group",
                "show",
                "--name",
                self._config.resource_group,
                "--subscription",
                self._config.subscription_id,
            ]
        )
        if rc == 0:
            results["resource_group"] = {
                "status": "passed",
                "message": f"Resource group {self._config.resource_group} exists",
            }
        else:
            results["resource_group"] = {
                "status": "create_needed",
                "message": f"Resource group {self._config.resource_group} does not exist",
            }

        # Check container registry (if configured)
        if self._config.container and self._config.container.registry:
            registry_url = self._config.container.registry
            # Public registries (mcr, docker.io, ghcr.io) don't need ACR validation
            public_registries = ("mcr.microsoft.com", "docker.io", "ghcr.io")
            if any(registry_url.startswith(pub) for pub in public_registries):
                results["container_registry"] = {
                    "status": "passed",
                    "message": f"Public registry {registry_url}",
                }
            else:
                registry = registry_url.split(".")[0]
                rc, _, _ = self._az_cli(["acr", "show", "--name", registry])
                results["container_registry"] = {
                    "status": "passed" if rc == 0 else "failed",
                    "message": f"Registry {registry_url}",
                }

        # Check Key Vault (if configured)
        if self._config.key_vault_url:
            vault_name = self._config.key_vault_url.split("//")[1].split(".")[0]
            rc, _, _ = self._az_cli(["keyvault", "show", "--name", vault_name])
            results["key_vault"] = {
                "status": "passed" if rc == 0 else "failed",
                "message": f"Key Vault {vault_name}",
            }

        overall = all(r.get("status") in ("passed", "create_needed") for r in results.values())
        results["overall"] = {"status": "passed" if overall else "failed"}
        return results

    # -----------------------------------------------------------------
    # Resource group management
    # -----------------------------------------------------------------

    async def ensure_resource_group(self) -> bool:
        """Create resource group if it doesn't exist."""
        rc, _, _ = self._az_cli(
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

        rc, stdout, stderr = self._az_cli(
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
            raise RuntimeError(f"Failed to create SP '{name}': {stderr}")

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
            self._az_cli(
                [
                    "keyvault",
                    "secret",
                    "set",
                    "--vault-name",
                    vault_name,
                    "--name",
                    secret_name,
                    "--value",
                    sp_info["password"],
                ]
            )
            _logger.info("Stored SP secret in Key Vault: %s", secret_name)

        return sp_info

    async def delete_service_principal(self, app_id: str) -> bool:
        """Delete a service principal by app ID."""
        rc, _, stderr = self._az_cli(["ad", "sp", "delete", "--id", app_id])
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

        Args:
            deployment_id: Unique deployment identifier
            workload_name: Workload name (used for app naming)
            image: Container image (defaults to config)
            env_vars: Environment variables to inject
            cpu: CPU cores (defaults to config)
            memory_gb: Memory in GB (defaults to config)

        Returns:
            Dict with container app details (fqdn, resourceId, etc.)
        """
        cfg = self._config.container
        if cfg is None and image is None:
            raise ValueError(
                "No container configuration. Set container config or pass image parameter."
            )

        resolved_image = image or (cfg.image if cfg else "")
        resolved_cpu = cpu or (cfg.cpu_cores if cfg else 1.0)
        resolved_memory = memory_gb or (cfg.memory_gb if cfg else 4)
        app_name = f"{workload_name}-{deployment_id[:8]}".lower().replace("_", "-")

        # Ensure resource group exists
        await self.ensure_resource_group()

        # Build the az containerapp create command
        cmd = [
            "containerapp",
            "create",
            "--name",
            app_name,
            "--resource-group",
            self._config.resource_group,
            "--subscription",
            self._config.subscription_id,
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

        # Add container environment if configured
        if cfg and cfg.environment_name:
            cmd.extend(["--environment", cfg.environment_name])

        # Add private registry credentials (public registries don't need this)
        if cfg and cfg.registry:
            public_registries = ("mcr.microsoft.com", "docker.io", "ghcr.io")
            if not any(cfg.registry.startswith(pub) for pub in public_registries):
                cmd.extend(["--registry-server", cfg.registry])

        # Add environment variables (each as separate key=value arg)
        if env_vars:
            cmd.append("--env-vars")
            cmd.extend(f"{k}={v}" for k, v in env_vars.items())

        rc, stdout, stderr = self._az_cli(cmd)
        if rc != 0:
            raise RuntimeError(f"Failed to deploy container app '{app_name}': {stderr}")

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

    async def get_container_app_status(self, app_name: str) -> dict[str, Any]:
        """Get the status of a container app."""
        rc, stdout, stderr = self._az_cli(
            [
                "containerapp",
                "show",
                "--name",
                app_name,
                "--resource-group",
                self._config.resource_group,
                "--subscription",
                self._config.subscription_id,
            ]
        )
        if rc != 0:
            return {"status": "not_found", "error": stderr.strip()}
        data = json.loads(stdout)
        return {
            "status": data.get("properties", {}).get("provisioningState", "Unknown"),
            "running_status": data.get("properties", {}).get("runningStatus", "Unknown"),
        }

    async def delete_container_app(self, app_name: str) -> bool:
        """Delete a container app."""
        rc, _, stderr = self._az_cli(
            [
                "containerapp",
                "delete",
                "--name",
                app_name,
                "--resource-group",
                self._config.resource_group,
                "--subscription",
                self._config.subscription_id,
                "--yes",
            ]
        )
        if rc != 0:
            _logger.error("Failed to delete container app %s: %s", app_name, stderr)
            return False
        _logger.info("Deleted container app: %s", app_name)
        return True

    async def list_managed_resources(self, deployment_id: str | None = None) -> list[dict]:
        """List all resources tagged as haymaker-managed."""
        cmd = [
            "resource",
            "list",
            "--resource-group",
            self._config.resource_group,
            "--subscription",
            self._config.subscription_id,
            "--tag",
            "haymaker-managed=true",
        ]
        if deployment_id:
            cmd.extend(["--tag", f"deployment-id={deployment_id}"])

        rc, stdout, _ = self._az_cli(cmd)
        if rc != 0:
            return []
        return json.loads(stdout) if stdout.strip() else []

    # -----------------------------------------------------------------
    # Azure CLI helper
    # -----------------------------------------------------------------

    @staticmethod
    def _az_cli(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
        """Run an Azure CLI command and return (returncode, stdout, stderr).

        Searches common locations for the Azure CLI binary.
        """
        import shutil
        from pathlib import Path

        # Prefer well-known working locations before falling back to PATH
        az_path = None
        for candidate in [
            Path.home() / "bin" / "az",
            Path("/usr/local/bin/az"),
        ]:
            if candidate.exists():
                az_path = str(candidate)
                break
        if az_path is None:
            az_path = shutil.which("az") or "az"
        cmd = [az_path] + args + ["--output", "json"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except FileNotFoundError:
            return (
                127,
                "",
                "Azure CLI (az) not found. Install: https://aka.ms/installazurecli",
            )
        except subprocess.TimeoutExpired:
            return (
                124,
                "",
                f"Azure CLI command timed out after {timeout}s",
            )


__all__ = ["AzurePlatform"]
