"""Tests for WorkloadRegistry."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from agent_haymaker.workloads.base import WorkloadBase
from agent_haymaker.workloads.models import (
    CleanupReport,
    DeploymentState,
    DeploymentStatus,
)
from agent_haymaker.workloads.registry import WorkloadRegistry


class ConcreteWorkload(WorkloadBase):
    """Concrete workload for testing registry operations."""

    name = "test-workload"

    async def deploy(self, config):
        return "deploy-test-001"

    async def get_status(self, deployment_id):
        return DeploymentState(
            deployment_id=deployment_id,
            workload_name=self.name,
            status=DeploymentStatus.PENDING,
        )

    async def stop(self, deployment_id):
        return True

    async def cleanup(self, deployment_id):
        return CleanupReport(deployment_id=deployment_id)

    async def get_logs(self, deployment_id, follow=False, lines=100):
        yield "test log line"

    async def start(self, deployment_id):
        return True


class TestWorkloadRegistry:
    """Tests for WorkloadRegistry."""

    def test_init_default(self):
        registry = WorkloadRegistry()
        assert registry._platform is None
        assert registry._workloads == {}

    def test_discover_workloads_returns_dict(self):
        registry = WorkloadRegistry()
        result = registry.discover_workloads()
        assert isinstance(result, dict)

    def test_list_workloads_returns_list(self):
        registry = WorkloadRegistry()
        result = registry.list_workloads()
        assert isinstance(result, list)

    def test_get_workload_returns_none_for_unknown(self):
        registry = WorkloadRegistry()
        result = registry.get_workload("nonexistent-workload")
        assert result is None

    def test_register_workload(self):
        registry = WorkloadRegistry()
        registry.register_workload("test-workload", ConcreteWorkload)
        assert "test-workload" in registry._workloads

    def test_register_then_get_workload(self):
        registry = WorkloadRegistry()
        registry.register_workload("test-workload", ConcreteWorkload)
        instance = registry.get_workload("test-workload")
        assert instance is not None
        assert isinstance(instance, ConcreteWorkload)
        assert instance.name == "test-workload"

    def test_register_then_list_workloads(self):
        registry = WorkloadRegistry()
        registry.register_workload("wl-a", ConcreteWorkload)
        registry.register_workload("wl-b", ConcreteWorkload)
        names = registry.list_workloads()
        assert "wl-a" in names
        assert "wl-b" in names

    def test_register_then_discover_includes_workload(self):
        """After registering a workload, list_workloads includes it by name."""
        registry = WorkloadRegistry()
        registry.register_workload("my-workload", ConcreteWorkload)
        names = registry.list_workloads()
        assert "my-workload" in names

    def test_init_with_platform(self):
        platform = object()
        registry = WorkloadRegistry(platform=platform)
        assert registry._platform is platform

    def test_get_workload_injects_platform(self):
        platform = object()
        registry = WorkloadRegistry(platform=platform)
        registry.register_workload("test", ConcreteWorkload)
        instance = registry.get_workload("test")
        assert instance._platform is platform


def _write_manifest(directory: str, source: str | None = None) -> None:
    """Write a minimal workload.yaml into directory."""
    manifest = {
        "name": "test-workload",
        "version": "0.1.0",
        "type": "runtime",
        "description": "Test workload",
    }
    if source is not None:
        manifest["package"] = {"source": source}
    else:
        manifest["package"] = {"source": "."}
    path = Path(directory) / "workload.yaml"
    path.write_text(yaml.dump(manifest))


class TestInstallFromGitSourceValidation:
    """Tests that install_from_git validates the manifest source field."""

    def test_rejects_path_traversal_with_dot_dot(self):
        """Source '../../etc/passwd' escapes the clone directory."""
        registry = WorkloadRegistry()

        with tempfile.TemporaryDirectory() as fake_clone:
            _write_manifest(fake_clone, source="../../etc/passwd")

            with (
                patch("subprocess.run") as mock_run,
                patch("tempfile.TemporaryDirectory") as mock_td,
            ):
                mock_td.return_value.__enter__ = MagicMock(return_value=fake_clone)
                mock_td.return_value.__exit__ = MagicMock(return_value=False)
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                with pytest.raises(ValueError, match="escapes the clone directory"):
                    registry.install_from_git("https://example.com/repo.git")

    def test_rejects_absolute_path_outside_clone(self):
        """Source '/tmp/evil' escapes the clone directory."""
        registry = WorkloadRegistry()

        with tempfile.TemporaryDirectory() as fake_clone:
            _write_manifest(fake_clone, source="/tmp/evil")

            with (
                patch("subprocess.run") as mock_run,
                patch("tempfile.TemporaryDirectory") as mock_td,
            ):
                mock_td.return_value.__enter__ = MagicMock(return_value=fake_clone)
                mock_td.return_value.__exit__ = MagicMock(return_value=False)
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                with pytest.raises(ValueError, match="escapes the clone directory"):
                    registry.install_from_git("https://example.com/repo.git")

    def test_rejects_url_in_source(self):
        """Source containing a URL should be rejected."""
        registry = WorkloadRegistry()

        with tempfile.TemporaryDirectory() as fake_clone:
            _write_manifest(fake_clone, source="https://evil.com/package.tar.gz")

            with (
                patch("subprocess.run") as mock_run,
                patch("tempfile.TemporaryDirectory") as mock_td,
            ):
                mock_td.return_value.__enter__ = MagicMock(return_value=fake_clone)
                mock_td.return_value.__exit__ = MagicMock(return_value=False)
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                with pytest.raises(ValueError, match="must be a local path, not a URL"):
                    registry.install_from_git("https://example.com/repo.git")

    def test_rejects_ftp_url_in_source(self):
        """Source containing an ftp:// URL should be rejected."""
        registry = WorkloadRegistry()

        with tempfile.TemporaryDirectory() as fake_clone:
            _write_manifest(fake_clone, source="ftp://evil.com/package.tar.gz")

            with (
                patch("subprocess.run") as mock_run,
                patch("tempfile.TemporaryDirectory") as mock_td,
            ):
                mock_td.return_value.__enter__ = MagicMock(return_value=fake_clone)
                mock_td.return_value.__exit__ = MagicMock(return_value=False)
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                with pytest.raises(ValueError, match="must be a local path, not a URL"):
                    registry.install_from_git("https://example.com/repo.git")

    def test_accepts_dot_source(self):
        """Source '.' (current dir) is valid and should not raise."""
        registry = WorkloadRegistry()

        with tempfile.TemporaryDirectory() as fake_clone:
            _write_manifest(fake_clone, source=".")

            with (
                patch("subprocess.run") as mock_run,
                patch("tempfile.TemporaryDirectory") as mock_td,
                patch.object(registry, "discover_workloads"),
            ):
                mock_td.return_value.__enter__ = MagicMock(return_value=fake_clone)
                mock_td.return_value.__exit__ = MagicMock(return_value=False)
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                name = registry.install_from_git("https://example.com/repo.git")
                assert name == "test-workload"

    def test_accepts_subdirectory_source(self):
        """Source 'subdir' within the clone is valid."""
        registry = WorkloadRegistry()

        with tempfile.TemporaryDirectory() as fake_clone:
            subdir = Path(fake_clone) / "subdir"
            subdir.mkdir()
            _write_manifest(fake_clone, source="subdir")

            with (
                patch("subprocess.run") as mock_run,
                patch("tempfile.TemporaryDirectory") as mock_td,
                patch.object(registry, "discover_workloads"),
            ):
                mock_td.return_value.__enter__ = MagicMock(return_value=fake_clone)
                mock_td.return_value.__exit__ = MagicMock(return_value=False)
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                name = registry.install_from_git("https://example.com/repo.git")
                assert name == "test-workload"

    def test_rejects_symlink_escape(self):
        """A symlink pointing outside the clone dir should be caught."""
        registry = WorkloadRegistry()

        with tempfile.TemporaryDirectory() as fake_clone:
            link_path = Path(fake_clone) / "escape_link"
            link_path.symlink_to("/tmp")
            _write_manifest(fake_clone, source="escape_link")

            with (
                patch("subprocess.run") as mock_run,
                patch("tempfile.TemporaryDirectory") as mock_td,
            ):
                mock_td.return_value.__enter__ = MagicMock(return_value=fake_clone)
                mock_td.return_value.__exit__ = MagicMock(return_value=False)
                mock_run.return_value = MagicMock(returncode=0, stderr="")

                with pytest.raises(ValueError, match="escapes the clone directory"):
                    registry.install_from_git("https://example.com/repo.git")
