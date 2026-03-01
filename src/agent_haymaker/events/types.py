"""Event type constants and data model for agent-haymaker.

Defines the standard event topics and the EventData model used
across the event bus. Topics follow a dotted namespace convention
matching AzureHayMaker patterns.

Public API:
    EventData: Pydantic model for event payloads
    DEPLOYMENT_STARTED, DEPLOYMENT_COMPLETED, etc.: Topic constants
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Event topic constants
# ---------------------------------------------------------------------------

DEPLOYMENT_STARTED = "deployment.started"
DEPLOYMENT_COMPLETED = "deployment.completed"
DEPLOYMENT_FAILED = "deployment.failed"
DEPLOYMENT_PHASE_CHANGED = "deployment.phase_changed"
DEPLOYMENT_LOG = "deployment.log"
WORKLOAD_PROGRESS = "workload.progress"
RESOURCE_CREATED = "resource.created"
RESOURCE_DELETED = "resource.deleted"

ALL_TOPICS: list[str] = [
    DEPLOYMENT_STARTED,
    DEPLOYMENT_COMPLETED,
    DEPLOYMENT_FAILED,
    DEPLOYMENT_PHASE_CHANGED,
    DEPLOYMENT_LOG,
    WORKLOAD_PROGRESS,
    RESOURCE_CREATED,
    RESOURCE_DELETED,
]

# ---------------------------------------------------------------------------
# Event data model
# ---------------------------------------------------------------------------


class EventData(BaseModel):
    """Payload wrapper carried through the event bus.

    Attributes:
        topic: Dotted event topic string (e.g. ``deployment.started``).
        deployment_id: Identifier for the deployment this event belongs to.
        timestamp: UTC timestamp; auto-generated when omitted.
        data: Arbitrary key/value payload for the event.
    """

    topic: str
    deployment_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)
