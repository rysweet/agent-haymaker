"""Tests for workload data models."""

from datetime import datetime

from agent_haymaker.workloads.models import (
    CleanupReport,
    DeploymentConfig,
    DeploymentState,
    DeploymentStatus,
    WorkloadManifest,
)


class TestDeploymentStatus:
    """Tests for DeploymentStatus enum."""

    def test_enum_values(self):
        assert DeploymentStatus.PENDING == "pending"
        assert DeploymentStatus.RUNNING == "running"
        assert DeploymentStatus.STOPPED == "stopped"
        assert DeploymentStatus.COMPLETED == "completed"
        assert DeploymentStatus.FAILED == "failed"
        assert DeploymentStatus.CLEANING_UP == "cleaning_up"

    def test_all_values(self):
        values = [s.value for s in DeploymentStatus]
        assert len(values) == 6


class TestDeploymentState:
    """Tests for DeploymentState model."""

    def test_required_fields(self):
        state = DeploymentState(
            deployment_id="dep-123",
            workload_name="test-workload",
            status=DeploymentStatus.RUNNING,
        )
        assert state.deployment_id == "dep-123"
        assert state.workload_name == "test-workload"
        assert state.status == "running"

    def test_defaults(self):
        state = DeploymentState(
            deployment_id="dep-1",
            workload_name="test",
            status=DeploymentStatus.PENDING,
        )
        assert state.phase == "unknown"
        assert state.started_at is None
        assert state.stopped_at is None
        assert state.completed_at is None
        assert state.config == {}
        assert state.metadata == {}
        assert state.error is None

    def test_full_state(self):
        now = datetime.now()
        state = DeploymentState(
            deployment_id="dep-full",
            workload_name="full-workload",
            status=DeploymentStatus.FAILED,
            phase="initialization",
            started_at=now,
            error="something went wrong",
            config={"workers": 5},
            metadata={"region": "eastus"},
        )
        assert state.phase == "initialization"
        assert state.started_at == now
        assert state.error == "something went wrong"

    def test_serialization(self):
        state = DeploymentState(
            deployment_id="dep-ser",
            workload_name="ser-workload",
            status=DeploymentStatus.RUNNING,
        )
        data = state.model_dump()
        assert data["deployment_id"] == "dep-ser"
        assert data["status"] == "running"
        assert isinstance(data, dict)


class TestDeploymentConfig:
    """Tests for DeploymentConfig model."""

    def test_required_fields(self):
        config = DeploymentConfig(workload_name="test")
        assert config.workload_name == "test"

    def test_defaults(self):
        config = DeploymentConfig(workload_name="test")
        assert config.duration_hours is None
        assert config.tags == {}
        assert config.workload_config == {}

    def test_full_config(self):
        config = DeploymentConfig(
            workload_name="test",
            duration_hours=24,
            tags={"env": "dev"},
            workload_config={"workers": 10},
        )
        assert config.duration_hours == 24
        assert config.tags == {"env": "dev"}
        assert config.workload_config == {"workers": 10}

    def test_serialization(self):
        config = DeploymentConfig(workload_name="test", duration_hours=8)
        data = config.model_dump()
        assert data["workload_name"] == "test"
        assert data["duration_hours"] == 8


class TestWorkloadManifest:
    """Tests for WorkloadManifest model."""

    def test_required_fields(self):
        manifest = WorkloadManifest(name="test-workload", version="1.0.0", type="prompt")
        assert manifest.name == "test-workload"
        assert manifest.version == "1.0.0"
        assert manifest.workload_type == "prompt"

    def test_defaults(self):
        manifest = WorkloadManifest(name="test", version="0.1.0", type="runtime")
        assert manifest.description == ""
        assert manifest.package is None
        assert manifest.entrypoint is None
        assert manifest.extensions == {}
        assert manifest.targets == []

    def test_serialization(self):
        manifest = WorkloadManifest(name="test", version="1.0.0", type="prompt")
        data = manifest.model_dump()
        assert data["name"] == "test"
        assert data["version"] == "1.0.0"


class TestCleanupReport:
    """Tests for CleanupReport model."""

    def test_required_fields(self):
        report = CleanupReport(deployment_id="dep-123")
        assert report.deployment_id == "dep-123"

    def test_defaults(self):
        report = CleanupReport(deployment_id="dep-1")
        assert report.resources_deleted == 0
        assert report.resources_failed == 0
        assert report.details == []
        assert report.errors == []
        assert report.duration_seconds == 0.0

    def test_full_report(self):
        report = CleanupReport(
            deployment_id="dep-full",
            resources_deleted=5,
            resources_failed=1,
            details=["Deleted VM", "Deleted NIC"],
            errors=["Failed to delete disk"],
            duration_seconds=12.5,
        )
        assert report.resources_deleted == 5
        assert report.resources_failed == 1
        assert len(report.details) == 2
        assert len(report.errors) == 1

    def test_serialization(self):
        report = CleanupReport(deployment_id="dep-ser", resources_deleted=3)
        data = report.model_dump()
        assert data["deployment_id"] == "dep-ser"
        assert data["resources_deleted"] == 3
