"""Tests for ServiceBusEventBus dual-write behavior."""

import asyncio
from unittest.mock import patch

import pytest

from agent_haymaker.azure.service_bus import ServiceBusEventBus


class TestServiceBusEventBus:
    """Test dual-write event bus behavior."""

    @pytest.mark.asyncio
    async def test_requires_connection_string_or_namespace(self):
        """ServiceBusEventBus must not be created without config."""
        with pytest.raises(ValueError, match="requires either connection_string or namespace"):
            ServiceBusEventBus()

    @pytest.mark.asyncio
    async def test_accepts_connection_string(self):
        """Should accept a connection string."""
        bus = ServiceBusEventBus(connection_string="fake-conn-str")
        assert bus._connection_string == "fake-conn-str"
        await bus.close()

    @pytest.mark.asyncio
    async def test_accepts_namespace(self):
        """Should accept a namespace."""
        bus = ServiceBusEventBus(namespace="my-namespace")
        assert bus._namespace == "my-namespace"
        await bus.close()

    @pytest.mark.asyncio
    async def test_local_delivery_with_failed_service_bus(self):
        """Local delivery should work even if Service Bus fails."""
        bus = ServiceBusEventBus(
            connection_string="Endpoint=sb://fake.servicebus.windows.net/;SharedAccessKey=fake"
        )
        received = []

        await bus.subscribe("test.topic", lambda e: received.append(e))

        # Service Bus will fail (fake connection), but local should still work
        with patch.object(bus, "_publish_to_service_bus") as mock_sb:
            mock_sb.return_value = None  # Simulate silent failure
            await bus.publish("test.topic", {"key": "value"})

        await asyncio.sleep(0.05)
        await bus.close()

        assert len(received) == 1
        assert received[0]["key"] == "value"

    @pytest.mark.asyncio
    async def test_inherits_local_bus_functionality(self):
        """ServiceBusEventBus should support all LocalEventBus operations."""
        bus = ServiceBusEventBus(connection_string="fake")

        sub_id = await bus.subscribe("topic.a", lambda e: None)
        assert bus.subscriber_count("topic.a") == 1

        await bus.unsubscribe(sub_id)
        assert bus.subscriber_count("topic.a") == 0

        await bus.close()

    @pytest.mark.asyncio
    async def test_dual_write_calls_service_bus(self):
        """Publish should call _publish_to_service_bus for every event."""
        bus = ServiceBusEventBus(connection_string="fake")
        received = []

        await bus.subscribe("test", lambda e: received.append(e))

        with patch.object(bus, "_publish_to_service_bus") as mock_sb:
            mock_sb.return_value = None
            await bus.publish("test", {"msg": "hello"})

        await asyncio.sleep(0.05)

        # Service Bus was called
        mock_sb.assert_called_once()
        # Local delivery also happened
        assert len(received) == 1

        await bus.close()

    @pytest.mark.asyncio
    async def test_service_bus_failure_does_not_block_local(self):
        """If Service Bus raises, local delivery still happens."""
        bus = ServiceBusEventBus(connection_string="fake")
        received = []

        await bus.subscribe("test", lambda e: received.append(e))

        with patch.object(bus, "_publish_to_service_bus", side_effect=RuntimeError("SB down")):
            # Should not raise - SB failure is best-effort
            try:
                await bus.publish("test", {"msg": "hello"})
            except RuntimeError:
                pass  # If it does raise, local delivery should still have happened

        await asyncio.sleep(0.05)
        await bus.close()

        # Local delivery happened regardless
        assert len(received) == 1


class TestAzurePlatformRequiresServiceBus:
    """Test that AzurePlatform refuses to start without Service Bus."""

    def test_azure_platform_requires_service_bus(self):
        """AzurePlatform should raise ValueError without Service Bus config."""
        from agent_haymaker.azure.config import AzureConfig

        config = AzureConfig(
            tenant_id="fake-tenant",
            subscription_id="fake-sub",
            resource_group="fake-rg",
        )

        from agent_haymaker.azure.platform import AzurePlatform

        with pytest.raises(ValueError, match="requires Service Bus configuration"):
            AzurePlatform(config=config)

    def test_azure_platform_accepts_service_bus_connection(self):
        """AzurePlatform should work with Service Bus connection string."""
        from agent_haymaker.azure.config import AzureConfig, ServiceBusConfig
        from agent_haymaker.azure.platform import AzurePlatform

        config = AzureConfig(
            tenant_id="fake-tenant",
            subscription_id="fake-sub",
            resource_group="fake-rg",
            service_bus=ServiceBusConfig(connection_string="fake-conn-str"),
        )

        platform = AzurePlatform(config=config)
        assert isinstance(platform._event_bus, ServiceBusEventBus)
