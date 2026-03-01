"""Public API for the agent-haymaker events module.

Exports:
    LocalEventBus: In-process async event bus.
    EventData: Pydantic model for structured event payloads.
    Event topic constants (DEPLOYMENT_STARTED, etc.).
"""

from .bus import LocalEventBus
from .types import (
    ALL_TOPICS,
    DEPLOYMENT_COMPLETED,
    DEPLOYMENT_FAILED,
    DEPLOYMENT_LOG,
    DEPLOYMENT_PHASE_CHANGED,
    DEPLOYMENT_STARTED,
    DEPLOYMENT_STOPPED,
    RESOURCE_CREATED,
    RESOURCE_DELETED,
    WORKLOAD_PROGRESS,
    EventData,
)

__all__ = [
    "LocalEventBus",
    "EventData",
    "DEPLOYMENT_STARTED",
    "DEPLOYMENT_COMPLETED",
    "DEPLOYMENT_FAILED",
    "DEPLOYMENT_PHASE_CHANGED",
    "DEPLOYMENT_LOG",
    "DEPLOYMENT_STOPPED",
    "WORKLOAD_PROGRESS",
    "RESOURCE_CREATED",
    "RESOURCE_DELETED",
    "ALL_TOPICS",
]
