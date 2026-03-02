"""Event emission helpers for workloads.

Provides EventEmitterMixin -- a mixin class that adds emit_event,
emit_progress, and emit_log convenience methods to any workload.

The mixin duck-types on ``self._platform`` (Platform | None) and
``self.name`` (str), both of which WorkloadBase already provides.

Public API:
    EventEmitterMixin
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..events import DEPLOYMENT_LOG, WORKLOAD_PROGRESS


class EventEmitterMixin:
    """Mixin that adds event-emission helpers to a workload.

    Expects the host class to supply:
        self._platform  - a Platform instance (or None)
        self.name       - the workload name string
    """

    # Declare the attributes that the mixin relies on so static
    # analysis tools understand the duck-typed contract.
    _platform: Any
    name: str

    async def emit_event(self, topic: str, deployment_id: str, **data: Any) -> None:
        """Publish an event via the platform event bus.

        Args:
            topic: Event topic (use constants from agent_haymaker.events)
            deployment_id: Associated deployment ID
            **data: Additional event data
        """
        if self._platform:
            event = {
                "topic": topic,
                "deployment_id": deployment_id,
                "workload_name": self.name,
                "timestamp": datetime.now(UTC).isoformat(),
                **data,
            }
            await self._platform.publish_event(topic, event)

    async def emit_progress(
        self, deployment_id: str, phase: str, message: str, percent: float | None = None
    ) -> None:
        """Emit a progress event for a deployment.

        Args:
            deployment_id: Deployment ID
            phase: Current execution phase
            message: Human-readable progress message
            percent: Optional completion percentage (0.0-100.0)
        """
        await self.emit_event(
            WORKLOAD_PROGRESS,
            deployment_id,
            phase=phase,
            message=message,
            percent=percent,
        )

    async def emit_log(self, deployment_id: str, line: str, level: str = "INFO") -> None:
        """Emit a log event for a deployment.

        Args:
            deployment_id: Deployment ID
            line: Log line content
            level: Log level (INFO, WARNING, ERROR, DEBUG)
        """
        await self.emit_event(
            DEPLOYMENT_LOG,
            deployment_id,
            line=line,
            level=level,
        )


__all__ = ["EventEmitterMixin"]
