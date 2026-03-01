"""In-process async event bus using asyncio primitives.

Provides a simple queue-based pub/sub mechanism with no external
dependencies beyond the standard library and typing support.

Public API:
    LocalEventBus: The event bus singleton you create and pass around.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal subscription record
# ---------------------------------------------------------------------------


@dataclass
class _Subscription:
    """Internal bookkeeping for a single subscriber."""

    id: str
    callback: Callable[[dict[str, Any]], Any]
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=10_000)
    )
    task: asyncio.Task[None] | None = None


# ---------------------------------------------------------------------------
# LocalEventBus
# ---------------------------------------------------------------------------


class LocalEventBus:
    """Lightweight async event bus backed by ``asyncio.Queue``.

    Each subscription gets its own queue and a background task that
    drains it, so publishers never block waiting for slow consumers.

    Example::

        bus = LocalEventBus()
        sid = await bus.subscribe("deployment.started", my_handler)
        await bus.publish("deployment.started", {"name": "web-app"})
        await bus.unsubscribe(sid)
        await bus.close()
    """

    def __init__(self) -> None:
        # topic -> {subscription_id -> _Subscription}
        self._subscribers: dict[str, dict[str, _Subscription]] = {}

    # ------------------------------------------------------------------
    # publish
    # ------------------------------------------------------------------

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        """Put *event* into every subscriber queue for *topic*.

        Non-blocking. If there are no subscribers the event is silently
        dropped.
        """
        subs = self._subscribers.get(topic)
        if not subs:
            return
        for sub in subs.values():
            try:
                sub.queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "Dropping event for subscription %s on topic %r: queue full",
                    sub.id,
                    topic,
                )

    # ------------------------------------------------------------------
    # subscribe
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[dict[str, Any]], Any],
    ) -> str:
        """Register *callback* for *topic* and return a subscription ID.

        The callback may be a regular function or an async coroutine
        function -- both are handled transparently.
        """
        sub_id = str(uuid.uuid4())
        sub = _Subscription(id=sub_id, callback=callback)
        sub.task = asyncio.create_task(self._run_subscriber(sub))

        self._subscribers.setdefault(topic, {})[sub_id] = sub
        return sub_id

    # ------------------------------------------------------------------
    # unsubscribe
    # ------------------------------------------------------------------

    async def unsubscribe(self, subscription_id: str) -> None:
        """Cancel the subscriber task and remove it from the registry."""
        for topic, subs in self._subscribers.items():
            if subscription_id in subs:
                sub = subs.pop(subscription_id)
                if sub.task is not None:
                    sub.task.cancel()
                    try:
                        await sub.task
                    except asyncio.CancelledError:
                        pass
                # Clean up empty topic buckets
                if not subs:
                    del self._subscribers[topic]
                return

    # ------------------------------------------------------------------
    # close
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Cancel every subscriber task and clear all subscriptions."""
        tasks: list[asyncio.Task[None]] = []
        for subs in self._subscribers.values():
            for sub in subs.values():
                if sub.task is not None:
                    sub.task.cancel()
                    tasks.append(sub.task)
        # Wait for all cancellations to settle
        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._subscribers.clear()

    # ------------------------------------------------------------------
    # subscriber_count
    # ------------------------------------------------------------------

    def subscriber_count(self, topic: str) -> int:
        """Return the number of active subscribers for *topic*."""
        return len(self._subscribers.get(topic, {}))

    # ------------------------------------------------------------------
    # internal loop
    # ------------------------------------------------------------------

    async def _run_subscriber(self, sub: _Subscription) -> None:
        """Forever-loop: pull events from the queue and invoke callback."""
        is_async = inspect.iscoroutinefunction(sub.callback)
        while True:
            event = await sub.queue.get()
            try:
                if is_async:
                    await sub.callback(event)
                else:
                    sub.callback(event)
            except Exception:
                logger.exception(
                    "Error in event callback for subscription %s",
                    sub.id,
                )
