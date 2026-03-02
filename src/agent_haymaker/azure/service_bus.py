"""Azure Service Bus event bus implementation.

Provides ServiceBusEventBus that wraps LocalEventBus with Azure Service Bus
for real-time event streaming when deployed to Azure. Implements the same
publish/subscribe interface as LocalEventBus.

Dual-write pattern (matching AzureHayMaker):
- WRITE 1: Azure Service Bus topic (real-time streaming to external consumers)
- WRITE 2: Local event bus (in-process subscribers, CLI watch, etc.)

When Service Bus is not configured or unavailable, falls back gracefully
to local-only event delivery.

Public API:
    ServiceBusEventBus: Event bus with Azure Service Bus backend
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from ..events.bus import LocalEventBus

_logger = logging.getLogger(__name__)


class ServiceBusEventBus(LocalEventBus):
    """Event bus that publishes to Azure Service Bus AND local subscribers.

    Extends LocalEventBus with dual-write: every published event goes to
    both Azure Service Bus (for external consumers) and the local in-process
    bus (for CLI watch, status --follow, etc.).

    If Service Bus is unavailable, events still flow locally with a warning.

    Args:
        connection_string: Azure Service Bus connection string.
            If None, behaves identically to LocalEventBus.
        topic_name: Service Bus topic name (default: "agent-logs").
        namespace: Service Bus namespace (alternative to connection string,
            uses Azure CLI for auth).
    """

    def __init__(
        self,
        connection_string: str | None = None,
        topic_name: str = "agent-logs",
        namespace: str | None = None,
    ) -> None:
        super().__init__()
        self._connection_string = connection_string
        self._topic_name = topic_name
        self._namespace = namespace
        self._sb_available = connection_string is not None or namespace is not None

        if self._sb_available:
            _logger.info("ServiceBusEventBus: dual-write enabled (topic=%s)", topic_name)
        else:
            _logger.info("ServiceBusEventBus: local-only mode (no Service Bus configured)")

    async def publish(self, topic: str, event: dict[str, Any]) -> None:
        """Dual-write: publish to Service Bus AND local subscribers.

        Service Bus write is best-effort: failures are logged but don't
        prevent local delivery.
        """
        # WRITE 1: Azure Service Bus (real-time streaming)
        if self._sb_available:
            await self._publish_to_service_bus(topic, event)

        # WRITE 2: Local in-process subscribers (always)
        await super().publish(topic, event)

    async def _publish_to_service_bus(self, topic: str, event: dict[str, Any]) -> None:
        """Publish event to Azure Service Bus topic.

        Uses azure-servicebus SDK if available, falls back to Azure CLI.
        """
        event_json = json.dumps(event, default=str)

        # Try SDK first (fast, async)
        if await self._try_sdk_publish(event_json):
            return

        # Fallback: Azure CLI (slower, subprocess)
        self._cli_publish(event_json)

    async def _try_sdk_publish(self, event_json: str) -> bool:
        """Try publishing via azure-servicebus SDK. Returns True if successful."""
        try:
            from azure.servicebus import ServiceBusMessage
            from azure.servicebus.aio import ServiceBusClient
        except ImportError:
            return False  # SDK not installed, fall back to CLI

        if not self._connection_string:
            return False  # Need connection string for SDK

        client = None
        try:
            client = ServiceBusClient.from_connection_string(self._connection_string)
            sender = client.get_topic_sender(self._topic_name)
            async with sender:
                message = ServiceBusMessage(event_json, content_type="application/json")
                await sender.send_messages(message)
            return True
        except Exception as exc:
            _logger.warning("Service Bus SDK publish failed: %s", exc)
            return False
        finally:
            if client:
                await client.close()

    def _cli_publish(self, event_json: str) -> None:
        """Fallback: publish via Azure CLI servicebus command."""
        import shutil

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

        cmd = [az_path, "servicebus", "topic", "send"]

        if self._connection_string:
            cmd.extend(["--connection-string", self._connection_string])
        elif self._namespace:
            cmd.extend(["--namespace-name", self._namespace])
        else:
            return

        cmd.extend(["--topic-name", self._topic_name, "--body", event_json])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                _logger.warning("Service Bus CLI publish failed: %s", result.stderr.strip())
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            _logger.warning("Service Bus CLI publish error: %s", exc)


__all__ = ["ServiceBusEventBus"]
