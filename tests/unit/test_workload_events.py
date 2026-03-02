"""Tests for workload event emission and FilePlatform event integration."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from agent_haymaker.events import (
    DEPLOYMENT_COMPLETED,
    DEPLOYMENT_LOG,
    DEPLOYMENT_STARTED,
    WORKLOAD_PROGRESS,
    LocalEventBus,
)
from agent_haymaker.workloads.base import WorkloadBase
from agent_haymaker.workloads.file_platform import FilePlatform
from agent_haymaker.workloads.models import (
    CleanupReport,
    DeploymentConfig,
    DeploymentState,
    DeploymentStatus,
)


class _StubWorkload(WorkloadBase):
    """Minimal concrete workload for testing event helpers."""

    name = "stub-for-events"

    async def deploy(self, config: DeploymentConfig) -> str:
        return "dep-stub"

    async def get_status(self, deployment_id: str) -> DeploymentState:
        return DeploymentState(
            deployment_id=deployment_id,
            workload_name=self.name,
            status=DeploymentStatus.RUNNING,
        )

    async def stop(self, deployment_id: str) -> bool:
        return True

    async def cleanup(self, deployment_id: str) -> CleanupReport:
        return CleanupReport(deployment_id=deployment_id)

    async def get_logs(
        self, deployment_id: str, follow: bool = False, lines: int = 100
    ) -> AsyncIterator[str]:
        yield "test log"


class TestWorkloadBaseEventEmission:
    """Test emit_event, emit_progress, emit_log on WorkloadBase."""

    @pytest.mark.asyncio
    async def test_emit_event_with_platform(self):
        """emit_event should publish through the platform event bus."""
        with TemporaryDirectory() as td:
            platform = FilePlatform(state_dir=Path(td))
            workload = _StubWorkload(platform=platform)
            received: list[dict] = []

            sub_id = await platform.subscribe(DEPLOYMENT_STARTED, lambda e: received.append(e))
            await workload.emit_event(DEPLOYMENT_STARTED, "dep-1", custom_key="val")
            await asyncio.sleep(0.05)
            await platform.unsubscribe(sub_id)

            assert len(received) == 1
            assert received[0]["topic"] == DEPLOYMENT_STARTED
            assert received[0]["deployment_id"] == "dep-1"
            assert received[0]["workload_name"] == "stub-for-events"
            assert received[0]["custom_key"] == "val"
            assert "timestamp" in received[0]

    @pytest.mark.asyncio
    async def test_emit_event_without_platform(self):
        """emit_event should be a no-op when platform is None."""
        workload = _StubWorkload(platform=None)
        # Should not raise
        await workload.emit_event(DEPLOYMENT_STARTED, "dep-1")

    @pytest.mark.asyncio
    async def test_emit_event_includes_workload_name(self):
        """emit_event should include workload_name in every event payload."""
        with TemporaryDirectory() as td:
            platform = FilePlatform(state_dir=Path(td))
            workload = _StubWorkload(platform=platform)
            received: list[dict] = []

            sub_id = await platform.subscribe(DEPLOYMENT_COMPLETED, lambda e: received.append(e))
            await workload.emit_event(DEPLOYMENT_COMPLETED, "dep-2")
            await asyncio.sleep(0.05)
            await platform.unsubscribe(sub_id)

            assert received[0]["workload_name"] == "stub-for-events"

    @pytest.mark.asyncio
    async def test_emit_progress(self):
        """emit_progress should publish a WORKLOAD_PROGRESS event."""
        with TemporaryDirectory() as td:
            platform = FilePlatform(state_dir=Path(td))
            workload = _StubWorkload(platform=platform)
            received: list[dict] = []

            sub_id = await platform.subscribe(WORKLOAD_PROGRESS, lambda e: received.append(e))
            await workload.emit_progress("dep-1", "init", "Starting", percent=25.0)
            await asyncio.sleep(0.05)
            await platform.unsubscribe(sub_id)

            assert len(received) == 1
            assert received[0]["topic"] == WORKLOAD_PROGRESS
            assert received[0]["phase"] == "init"
            assert received[0]["message"] == "Starting"
            assert received[0]["percent"] == 25.0

    @pytest.mark.asyncio
    async def test_emit_progress_without_percent(self):
        """emit_progress should work without an explicit percent value."""
        with TemporaryDirectory() as td:
            platform = FilePlatform(state_dir=Path(td))
            workload = _StubWorkload(platform=platform)
            received: list[dict] = []

            sub_id = await platform.subscribe(WORKLOAD_PROGRESS, lambda e: received.append(e))
            await workload.emit_progress("dep-1", "setup", "Configuring")
            await asyncio.sleep(0.05)
            await platform.unsubscribe(sub_id)

            assert len(received) == 1
            assert received[0]["percent"] is None

    @pytest.mark.asyncio
    async def test_emit_log(self):
        """emit_log should publish a DEPLOYMENT_LOG event."""
        with TemporaryDirectory() as td:
            platform = FilePlatform(state_dir=Path(td))
            workload = _StubWorkload(platform=platform)
            received: list[dict] = []

            sub_id = await platform.subscribe(DEPLOYMENT_LOG, lambda e: received.append(e))
            await workload.emit_log("dep-1", "Something happened", level="WARNING")
            await asyncio.sleep(0.05)
            await platform.unsubscribe(sub_id)

            assert len(received) == 1
            assert received[0]["topic"] == DEPLOYMENT_LOG
            assert received[0]["line"] == "Something happened"
            assert received[0]["level"] == "WARNING"

    @pytest.mark.asyncio
    async def test_emit_log_default_level(self):
        """emit_log should default to INFO level."""
        with TemporaryDirectory() as td:
            platform = FilePlatform(state_dir=Path(td))
            workload = _StubWorkload(platform=platform)
            received: list[dict] = []

            sub_id = await platform.subscribe(DEPLOYMENT_LOG, lambda e: received.append(e))
            await workload.emit_log("dep-1", "default level line")
            await asyncio.sleep(0.05)
            await platform.unsubscribe(sub_id)

            assert received[0]["level"] == "INFO"


class TestFilePlatformEvents:
    """Test FilePlatform event bus integration."""

    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self):
        """FilePlatform should relay events through its LocalEventBus."""
        with TemporaryDirectory() as td:
            platform = FilePlatform(state_dir=Path(td))
            received: list[dict] = []

            sub_id = await platform.subscribe("test.topic", lambda e: received.append(e))
            await platform.publish_event("test.topic", {"key": "value"})
            await asyncio.sleep(0.05)
            await platform.unsubscribe(sub_id)

            assert len(received) == 1
            assert received[0]["key"] == "value"

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self):
        """After unsubscribe, events should not be delivered."""
        with TemporaryDirectory() as td:
            platform = FilePlatform(state_dir=Path(td))
            received: list[dict] = []

            sub_id = await platform.subscribe("test.topic", lambda e: received.append(e))
            await platform.publish_event("test.topic", {"msg": "first"})
            await asyncio.sleep(0.05)
            await platform.unsubscribe(sub_id)
            await platform.publish_event("test.topic", {"msg": "second"})
            await asyncio.sleep(0.05)

            assert len(received) == 1
            assert received[0]["msg"] == "first"

    @pytest.mark.asyncio
    async def test_has_event_bus_attribute(self):
        """FilePlatform should have a LocalEventBus instance."""
        with TemporaryDirectory() as td:
            platform = FilePlatform(state_dir=Path(td))
            assert hasattr(platform, "_event_bus")
            assert isinstance(platform._event_bus, LocalEventBus)

    @pytest.mark.asyncio
    async def test_multiple_subscribers_same_topic(self):
        """Multiple subscribers on the same topic should each receive events."""
        with TemporaryDirectory() as td:
            platform = FilePlatform(state_dir=Path(td))
            received_a: list[dict] = []
            received_b: list[dict] = []

            sub_a = await platform.subscribe("test.topic", lambda e: received_a.append(e))
            sub_b = await platform.subscribe("test.topic", lambda e: received_b.append(e))
            await platform.publish_event("test.topic", {"msg": "broadcast"})
            await asyncio.sleep(0.05)
            await platform.unsubscribe(sub_a)
            await platform.unsubscribe(sub_b)

            assert len(received_a) == 1
            assert len(received_b) == 1
            assert received_a[0]["msg"] == "broadcast"

    @pytest.mark.asyncio
    async def test_publish_to_topic_with_no_subscribers(self):
        """Publishing to a topic with no subscribers should not raise."""
        with TemporaryDirectory() as td:
            platform = FilePlatform(state_dir=Path(td))
            await platform.publish_event("nobody.listening", {"data": 42})
