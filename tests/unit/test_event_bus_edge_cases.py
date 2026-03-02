"""Edge case tests for LocalEventBus."""

import asyncio
import logging

import pytest

from agent_haymaker.events import (
    ALL_TOPICS,
    DEPLOYMENT_PHASE_CHANGED,
    DEPLOYMENT_STOPPED,
    RESOURCE_CREATED,
    RESOURCE_DELETED,
)
from agent_haymaker.events.bus import LocalEventBus


class TestQueueFullBehavior:
    """Test behavior when subscriber queue is full."""

    @pytest.mark.asyncio
    async def test_publish_drops_event_on_full_queue(self, caplog):
        """When queue is full, event should be dropped with a warning."""
        bus = LocalEventBus()

        # Subscribe with a callback that blocks forever, preventing the
        # consumer task from draining the queue. This means put_nowait
        # will eventually hit QueueFull (maxsize=10_000).
        blocker = asyncio.Event()

        async def slow_callback(event):
            await blocker.wait()

        await bus.subscribe("test.topic", slow_callback)

        # Publish enough events to fill the queue (10_000) plus one more
        # to trigger the QueueFull drop. The first event goes into the
        # queue and blocks the consumer; remaining 10_000 fill the queue.
        with caplog.at_level(logging.WARNING):
            for i in range(10_001):
                await bus.publish("test.topic", {"i": i})

        await bus.close()

        # Verify that at least one QueueFull warning was logged
        assert any(
            "queue full" in r.message.lower()
            for r in caplog.records
            if r.levelno >= logging.WARNING
        )

    @pytest.mark.asyncio
    async def test_publish_succeeds_when_queue_not_full(self):
        """Normal publish should not trigger any warnings."""
        bus = LocalEventBus()
        received: list[dict] = []

        await bus.subscribe("test.topic", lambda e: received.append(e))
        await bus.publish("test.topic", {"i": 1})
        await asyncio.sleep(0.05)

        assert len(received) == 1
        await bus.close()


class TestAllTopicsConstant:
    """Test ALL_TOPICS completeness and immutability."""

    def test_all_topics_is_tuple(self):
        """ALL_TOPICS should be immutable (tuple, not list)."""
        assert isinstance(ALL_TOPICS, tuple)

    def test_all_topics_contains_all_constants(self):
        """ALL_TOPICS should contain every defined topic constant."""
        assert DEPLOYMENT_PHASE_CHANGED in ALL_TOPICS
        assert RESOURCE_CREATED in ALL_TOPICS
        assert RESOURCE_DELETED in ALL_TOPICS
        assert DEPLOYMENT_STOPPED in ALL_TOPICS

    def test_all_topics_has_no_duplicates(self):
        """ALL_TOPICS should not contain duplicate entries."""
        assert len(ALL_TOPICS) == len(set(ALL_TOPICS))

    def test_all_topics_is_immutable(self):
        """Tuple cannot be mutated via append."""
        with pytest.raises(AttributeError):
            ALL_TOPICS.append("bad.topic")  # type: ignore[attr-defined]

    def test_all_topics_elements_are_strings(self):
        """Every element in ALL_TOPICS should be a non-empty string."""
        for topic in ALL_TOPICS:
            assert isinstance(topic, str)
            assert len(topic) > 0

    def test_all_topics_elements_follow_dotted_convention(self):
        """Topic constants should follow the dotted namespace pattern."""
        for topic in ALL_TOPICS:
            assert "." in topic, f"Topic {topic!r} does not follow dotted convention"


class TestBusCloseIdempotent:
    """Test that close() is safe to call multiple times."""

    @pytest.mark.asyncio
    async def test_close_twice(self):
        """Calling close() twice should not raise."""
        bus = LocalEventBus()
        await bus.subscribe("t", lambda e: None)
        await bus.close()
        await bus.close()  # Second close should be a no-op

    @pytest.mark.asyncio
    async def test_subscribe_after_close(self):
        """Subscribing after close should still work (bus is reusable)."""
        bus = LocalEventBus()
        await bus.subscribe("t", lambda e: None)
        await bus.close()

        received: list[dict] = []
        await bus.subscribe("t", lambda e: received.append(e))
        await bus.publish("t", {"after": "close"})
        await asyncio.sleep(0.05)

        assert len(received) == 1
        assert received[0]["after"] == "close"
        await bus.close()


class TestCallbackExceptionIsolation:
    """Test that one subscriber's exception does not affect others."""

    @pytest.mark.asyncio
    async def test_error_in_one_subscriber_does_not_affect_another(self):
        """A raising callback should not prevent other subscribers from receiving."""
        bus = LocalEventBus()
        good_received: list[dict] = []

        async def bad_callback(event):
            raise RuntimeError("I always fail")

        def good_callback(event):
            good_received.append(event)

        await bus.subscribe("test.topic", bad_callback)
        await bus.subscribe("test.topic", good_callback)

        await bus.publish("test.topic", {"msg": "hello"})
        await asyncio.sleep(0.05)

        # The good subscriber should still have received the event
        assert len(good_received) == 1
        assert good_received[0]["msg"] == "hello"
        await bus.close()
