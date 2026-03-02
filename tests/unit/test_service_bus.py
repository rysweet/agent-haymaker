"""Tests for ServiceBusEventBus dual-write behavior."""

import asyncio
from unittest.mock import patch

import pytest

from agent_haymaker.azure.service_bus import ServiceBusEventBus


class TestServiceBusEventBus:
    """Test dual-write event bus behavior."""

    @pytest.mark.asyncio
    async def test_local_delivery_without_connection(self):
        """Events should be delivered locally even without Service Bus."""
        bus = ServiceBusEventBus()  # No connection string
        received = []

        await bus.subscribe("test.topic", lambda e: received.append(e))
        await bus.publish("test.topic", {"key": "value"})
        await asyncio.sleep(0.05)
        await bus.close()

        assert len(received) == 1
        assert received[0]["key"] == "value"

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
    async def test_sb_available_flag_with_connection_string(self):
        """Service Bus should be marked available when connection string is set."""
        bus = ServiceBusEventBus(connection_string="fake-conn-str")
        assert bus._sb_available is True
        await bus.close()

    @pytest.mark.asyncio
    async def test_sb_available_flag_with_namespace(self):
        """Service Bus should be marked available when namespace is set."""
        bus = ServiceBusEventBus(namespace="my-namespace")
        assert bus._sb_available is True
        await bus.close()

    @pytest.mark.asyncio
    async def test_sb_not_available_without_config(self):
        """Service Bus should not be available without config."""
        bus = ServiceBusEventBus()
        assert bus._sb_available is False
        await bus.close()

    @pytest.mark.asyncio
    async def test_inherits_local_bus_functionality(self):
        """ServiceBusEventBus should support all LocalEventBus operations."""
        bus = ServiceBusEventBus()

        # Subscribe, publish, unsubscribe, subscriber_count - all inherited
        sub_id = await bus.subscribe("topic.a", lambda e: None)
        assert bus.subscriber_count("topic.a") == 1

        await bus.unsubscribe(sub_id)
        assert bus.subscriber_count("topic.a") == 0

        await bus.close()

    @pytest.mark.asyncio
    async def test_dual_write_calls_service_bus(self):
        """When SB is available, publish should call _publish_to_service_bus."""
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
    async def test_no_service_bus_call_without_config(self):
        """When SB is not available, _publish_to_service_bus should not be called."""
        bus = ServiceBusEventBus()  # No config
        received = []

        await bus.subscribe("test", lambda e: received.append(e))

        with patch.object(bus, "_publish_to_service_bus") as mock_sb:
            await bus.publish("test", {"msg": "hello"})

        await asyncio.sleep(0.05)

        mock_sb.assert_not_called()
        assert len(received) == 1

        await bus.close()
