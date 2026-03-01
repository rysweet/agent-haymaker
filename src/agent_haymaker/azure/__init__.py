"""Azure deployment infrastructure for agent-haymaker.

Provides Azure Container Apps deployment, Service Principal management,
credential storage via Key Vault, and environment validation.

Install with: pip install agent-haymaker[azure]

Public API:
    AzureConfig: Configuration for Azure deployment
    AzurePlatform: Platform implementation using Azure services
    ContainerManager: Deploy/manage Container Apps
    ServicePrincipalManager: SP lifecycle management
    validate_environment: Check Azure connectivity
"""

from .config import AzureConfig
from .platform import AzurePlatform

__all__ = [
    "AzureConfig",
    "AzurePlatform",
]
