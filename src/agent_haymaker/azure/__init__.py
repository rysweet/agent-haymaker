"""Azure deployment infrastructure for agent-haymaker.

Provides Azure Container Apps deployment, Service Principal management,
credential storage via Key Vault, Service Bus event streaming, and
environment validation.

Install with: pip install agent-haymaker[azure]

Public API:
    AzureConfig: Configuration for Azure deployment
    AzurePlatform: Platform implementation using Azure services
    ServiceBusEventBus: Event bus with Azure Service Bus dual-write
"""

from .config import AzureConfig
from .platform import AzurePlatform
from .service_bus import ServiceBusEventBus

__all__ = [
    "AzureConfig",
    "AzurePlatform",
    "ServiceBusEventBus",
]
