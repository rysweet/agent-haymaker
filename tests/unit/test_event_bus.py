"""Tests for the local event bus.

Testing pyramid:
- 80% unit tests (async event bus operations)
- 20% integration tests (end-to-end pub/sub flows)
"""

import asyncio

import pytest

from agent_haymaker.events import (
    ALL_TOPICS,
    DEPLOYMENT_COMPLETED,
    DEPLOYMENT_FAILED,
    DEPLOYMENT_LOG,
    DEPLOYMENT_STARTED,
    WORKLOAD_PROGRESS,
    EventData,
    LocalEventBus,
)


class TestLocalEventBus:
    """Unit tests for LocalEventBus."""

    @pytest.fixture
    def bus(self):
        return LocalEventBus()

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self, bus):
        """Publishing with no subscribers should not raise."""
        await bus.publish("test.topic", {"key": "value"})

    @pytest.mark.asyncio
    async def test_subscribe_returns_id(self, bus):
        """Subscribe should return a unique subscription ID."""
        sub_id = await bus.subscribe("test.topic", lambda e: None)
        assert isinstance(sub_id, str)
        assert len(sub_id) > 0
        await bus.close()

    @pytest.mark.asyncio
    async def test_subscribe_multiple_returns_unique_ids(self, bus):
        """Each subscription gets a unique ID."""
        id1 = await bus.subscribe("test.topic", lambda e: None)
        id2 = await bus.subscribe("test.topic", lambda e: None)
        assert id1 != id2
        await bus.close()

    @pytest.mark.asyncio
    async def test_publish_delivers_to_subscriber(self, bus):
        """Published events should be delivered to subscribers."""
        received = []

        async def callback(event):
            received.append(event)

        await bus.subscribe("test.topic", callback)
        await bus.publish("test.topic", {"key": "value"})
        await asyncio.sleep(0.05)  # Let the subscriber task process

        assert len(received) == 1
        assert received[0]["key"] == "value"
        await bus.close()

    @pytest.mark.asyncio
    async def test_publish_delivers_to_multiple_subscribers(self, bus):
        """Published events should be delivered to all subscribers."""
        received1 = []
        received2 = []

        await bus.subscribe("test.topic", lambda e: received1.append(e))
        await bus.subscribe("test.topic", lambda e: received2.append(e))
        await bus.publish("test.topic", {"key": "value"})
        await asyncio.sleep(0.05)

        assert len(received1) == 1
        assert len(received2) == 1
        await bus.close()

    @pytest.mark.asyncio
    async def test_publish_only_delivers_to_matching_topic(self, bus):
        """Events should only go to subscribers of the matching topic."""
        received_a = []
        received_b = []

        await bus.subscribe("topic.a", lambda e: received_a.append(e))
        await bus.subscribe("topic.b", lambda e: received_b.append(e))
        await bus.publish("topic.a", {"for": "a"})
        await asyncio.sleep(0.05)

        assert len(received_a) == 1
        assert len(received_b) == 0
        await bus.close()

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus):
        """Unsubscribed callback should not receive further events."""
        received = []
        sub_id = await bus.subscribe("test.topic", lambda e: received.append(e))
        await bus.publish("test.topic", {"msg": "first"})
        await asyncio.sleep(0.05)

        await bus.unsubscribe(sub_id)
        await bus.publish("test.topic", {"msg": "second"})
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0]["msg"] == "first"

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent(self, bus):
        """Unsubscribing a nonexistent ID should not raise."""
        await bus.unsubscribe("nonexistent-id")

    @pytest.mark.asyncio
    async def test_subscriber_count(self, bus):
        """subscriber_count should track subscribers per topic."""
        assert bus.subscriber_count("test.topic") == 0
        id1 = await bus.subscribe("test.topic", lambda e: None)
        assert bus.subscriber_count("test.topic") == 1
        await bus.subscribe("test.topic", lambda e: None)
        assert bus.subscriber_count("test.topic") == 2
        await bus.unsubscribe(id1)
        assert bus.subscriber_count("test.topic") == 1
        await bus.close()

    @pytest.mark.asyncio
    async def test_close_cancels_all(self, bus):
        """close() should cancel all subscriber tasks."""
        await bus.subscribe("a", lambda e: None)
        await bus.subscribe("b", lambda e: None)
        assert bus.subscriber_count("a") == 1
        assert bus.subscriber_count("b") == 1

        await bus.close()
        assert bus.subscriber_count("a") == 0
        assert bus.subscriber_count("b") == 0

    @pytest.mark.asyncio
    async def test_sync_callback(self, bus):
        """Sync callbacks should work."""
        received = []

        def sync_cb(event):
            received.append(event)

        await bus.subscribe("test.topic", sync_cb)
        await bus.publish("test.topic", {"sync": True})
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0]["sync"] is True
        await bus.close()

    @pytest.mark.asyncio
    async def test_callback_error_does_not_stop_subscriber(self, bus):
        """A failing callback should not stop the subscriber from receiving future events."""
        received = []
        call_count = 0

        async def flaky_callback(event):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First call fails")
            received.append(event)

        await bus.subscribe("test.topic", flaky_callback)
        await bus.publish("test.topic", {"msg": "fail"})
        await asyncio.sleep(0.05)
        await bus.publish("test.topic", {"msg": "succeed"})
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0]["msg"] == "succeed"
        await bus.close()


class TestEventData:
    """Tests for EventData model."""

    def test_create_event_data(self):
        event = EventData(topic="test.topic", deployment_id="dep-123", data={"key": "value"})
        assert event.topic == "test.topic"
        assert event.deployment_id == "dep-123"
        assert event.data == {"key": "value"}
        assert event.timestamp is not None

    def test_event_data_auto_timestamp(self):
        e1 = EventData(topic="t", deployment_id="d")
        e2 = EventData(topic="t", deployment_id="d")
        assert e1.timestamp <= e2.timestamp


class TestEventTypeConstants:
    """Tests for event type constants."""

    def test_constants_are_strings(self):
        assert isinstance(DEPLOYMENT_STARTED, str)
        assert isinstance(DEPLOYMENT_COMPLETED, str)
        assert isinstance(DEPLOYMENT_FAILED, str)
        assert isinstance(DEPLOYMENT_LOG, str)
        assert isinstance(WORKLOAD_PROGRESS, str)

    def test_all_topics_list(self):
        assert len(ALL_TOPICS) >= 5
        assert DEPLOYMENT_STARTED in ALL_TOPICS
        assert DEPLOYMENT_LOG in ALL_TOPICS
