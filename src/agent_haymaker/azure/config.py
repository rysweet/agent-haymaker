"""Azure deployment configuration.

Loads from environment variables or a YAML config file.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ContainerConfig(BaseModel):
    """Container App sizing and deployment settings."""

    registry: str = Field(..., description="Azure Container Registry URL")
    image: str = Field(..., description="Container image name:tag")
    memory_gb: int = Field(default=2, ge=1, le=128, description="Memory in GB")
    cpu_cores: float = Field(default=1.0, ge=0.25, le=16, description="CPU cores")
    environment_name: str | None = Field(
        default=None, description="Container Apps Environment name"
    )
    timeout_hours: int = Field(default=10, ge=1, le=24, description="Container timeout")

    model_config = ConfigDict(extra="forbid")


class NetworkConfig(BaseModel):
    """VNet and networking settings."""

    vnet_enabled: bool = Field(default=False, description="Enable VNet integration")
    vnet_resource_group: str | None = Field(default=None)
    vnet_name: str | None = Field(default=None)
    subnet_name: str | None = Field(default=None)

    model_config = ConfigDict(extra="forbid")


class StorageConfig(BaseModel):
    """Azure Storage settings for state and logs."""

    account_name: str | None = Field(default=None, description="Storage account name")
    connection_string: SecretStr | None = Field(default=None)
    logs_container: str = Field(default="logs")
    reports_container: str = Field(default="reports")
    state_container: str = Field(default="state")

    model_config = ConfigDict(extra="forbid")


class ServiceBusConfig(BaseModel):
    """Azure Service Bus settings for event streaming."""

    connection_string: SecretStr | None = Field(default=None)
    namespace: str | None = Field(default=None)
    topic_name: str = Field(default="agent-logs")

    model_config = ConfigDict(extra="forbid")


class AzureConfig(BaseModel):
    """Root configuration for Azure deployment.

    Can be loaded from environment variables or a YAML file.

    Example YAML:
        tenant_id: "00000000-..."
        subscription_id: "00000000-..."
        resource_group: "haymaker-rg"
        location: "eastus"
        container:
          registry: "myregistry.azurecr.io"
          image: "haymaker-agent:latest"
        key_vault_url: "https://myvault.vault.azure.net/"

    Example env vars:
        AZURE_TENANT_ID=00000000-...
        AZURE_SUBSCRIPTION_ID=00000000-...
        HAYMAKER_RESOURCE_GROUP=haymaker-rg
        HAYMAKER_LOCATION=eastus
        HAYMAKER_CONTAINER_REGISTRY=myregistry.azurecr.io
        HAYMAKER_CONTAINER_IMAGE=haymaker-agent:latest
        HAYMAKER_KEY_VAULT_URL=https://myvault.vault.azure.net/
    """

    # Azure identity
    tenant_id: str = Field(..., description="Azure AD tenant ID")
    subscription_id: str = Field(..., description="Azure subscription ID")
    resource_group: str = Field(..., description="Resource group for deployments")
    location: str = Field(default="eastus", description="Azure region")

    # Credentials (optional - uses DefaultAzureCredential if not set)
    client_id: str | None = Field(default=None, description="SP client ID")
    client_secret: SecretStr | None = Field(default=None, description="SP client secret")

    # Key Vault
    key_vault_url: str | None = Field(
        default=None, description="Key Vault URL for credential storage"
    )

    # Sub-configs
    container: ContainerConfig | None = Field(default=None)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    service_bus: ServiceBusConfig = Field(default_factory=ServiceBusConfig)

    # Execution settings
    execution_duration_hours: int = Field(default=8, ge=1, le=24)
    monitoring_interval_minutes: int = Field(default=15, ge=1, le=60)

    model_config = ConfigDict(extra="forbid")

    @classmethod
    def from_env(cls) -> AzureConfig:
        """Load configuration from environment variables."""
        container = None
        registry = os.environ.get("HAYMAKER_CONTAINER_REGISTRY")
        image = os.environ.get("HAYMAKER_CONTAINER_IMAGE")
        if registry and image:
            container = ContainerConfig(
                registry=registry,
                image=image,
                memory_gb=int(os.environ.get("HAYMAKER_CONTAINER_MEMORY_GB", "2")),
                cpu_cores=float(os.environ.get("HAYMAKER_CONTAINER_CPU_CORES", "1.0")),
                environment_name=os.environ.get("HAYMAKER_CONTAINER_ENV_NAME"),
            )

        return cls(
            tenant_id=os.environ["AZURE_TENANT_ID"],
            subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
            resource_group=os.environ.get("HAYMAKER_RESOURCE_GROUP", "haymaker-rg"),
            location=os.environ.get("HAYMAKER_LOCATION", "eastus"),
            client_id=os.environ.get("AZURE_CLIENT_ID"),
            client_secret=os.environ.get("AZURE_CLIENT_SECRET"),
            key_vault_url=os.environ.get("HAYMAKER_KEY_VAULT_URL"),
            container=container,
            network=NetworkConfig(
                vnet_enabled=os.environ.get("HAYMAKER_VNET_ENABLED", "").lower() == "true",
                vnet_resource_group=os.environ.get("HAYMAKER_VNET_RESOURCE_GROUP"),
                vnet_name=os.environ.get("HAYMAKER_VNET_NAME"),
                subnet_name=os.environ.get("HAYMAKER_SUBNET_NAME"),
            ),
            service_bus=ServiceBusConfig(
                connection_string=os.environ.get("HAYMAKER_SERVICEBUS_CONNECTION"),
                namespace=os.environ.get("HAYMAKER_SERVICEBUS_NAMESPACE"),
            ),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> AzureConfig:
        """Load configuration from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    @classmethod
    def load(cls) -> AzureConfig:
        """Load config from YAML file (if exists) or environment variables.

        Checks for ~/.haymaker/azure.yaml first, then falls back to env vars.
        """
        yaml_path = Path.home() / ".haymaker" / "azure.yaml"
        if yaml_path.exists():
            return cls.from_yaml(yaml_path)
        return cls.from_env()


__all__ = [
    "AzureConfig",
    "ContainerConfig",
    "NetworkConfig",
    "StorageConfig",
    "ServiceBusConfig",
]
