"""Tests for FilePlatform - file-based state persistence."""

import asyncio
import os
from unittest.mock import patch

import pytest

from agent_haymaker.workloads.file_platform import FilePlatform, _sanitize_deployment_id
from agent_haymaker.workloads.models import DeploymentState, DeploymentStatus


def _run(coro):
    """Helper to run async coroutines in tests."""
    return asyncio.run(coro)


class TestSanitizeDeploymentId:
    """Tests for deployment ID sanitization."""

    def test_valid_simple_id(self):
        assert _sanitize_deployment_id("dep-001") == "dep-001"

    def test_valid_id_with_dots(self):
        assert _sanitize_deployment_id("dep.001.test") == "dep.001.test"

    def test_valid_id_with_underscores(self):
        assert _sanitize_deployment_id("dep_001_test") == "dep_001_test"

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="must not be empty"):
            _sanitize_deployment_id("")

    def test_rejects_path_traversal_dotdot(self):
        # ../etc/passwd contains slashes so it hits the path separator check first
        with pytest.raises(ValueError, match="path separators"):
            _sanitize_deployment_id("../etc/passwd")

    def test_rejects_dotdot_without_slash(self):
        with pytest.raises(ValueError, match="path traversal"):
            _sanitize_deployment_id("..evil")

    def test_rejects_forward_slash(self):
        with pytest.raises(ValueError, match="path separators"):
            _sanitize_deployment_id("foo/bar")

    def test_rejects_backslash(self):
        with pytest.raises(ValueError, match="path separators"):
            _sanitize_deployment_id("foo\\bar")

    def test_rejects_leading_dot(self):
        with pytest.raises(ValueError, match="invalid characters"):
            _sanitize_deployment_id(".hidden")

    def test_rejects_spaces(self):
        with pytest.raises(ValueError, match="invalid characters"):
            _sanitize_deployment_id("dep 001")


class TestFilePlatformSaveLoad:
    """Tests for save and load operations."""

    def test_save_and_load_roundtrip(self, tmp_path):
        platform = FilePlatform(state_dir=tmp_path)
        state = DeploymentState(
            deployment_id="dep-001",
            workload_name="test-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
        )
        _run(platform.save_deployment_state(state))
        loaded = _run(platform.load_deployment_state("dep-001"))
        assert loaded is not None
        assert loaded.deployment_id == "dep-001"
        assert loaded.workload_name == "test-workload"
        assert loaded.status == DeploymentStatus.RUNNING
        assert loaded.phase == "executing"

    def test_load_nonexistent_returns_none(self, tmp_path):
        platform = FilePlatform(state_dir=tmp_path)
        result = _run(platform.load_deployment_state("nonexistent"))
        assert result is None

    def test_save_creates_json_file(self, tmp_path):
        platform = FilePlatform(state_dir=tmp_path)
        state = DeploymentState(
            deployment_id="dep-002",
            workload_name="test",
            status=DeploymentStatus.PENDING,
        )
        _run(platform.save_deployment_state(state))
        assert (tmp_path / "dep-002.json").exists()

    def test_save_overwrites_existing(self, tmp_path):
        platform = FilePlatform(state_dir=tmp_path)
        state1 = DeploymentState(
            deployment_id="dep-003",
            workload_name="test",
            status=DeploymentStatus.PENDING,
        )
        state2 = DeploymentState(
            deployment_id="dep-003",
            workload_name="test",
            status=DeploymentStatus.RUNNING,
        )
        _run(platform.save_deployment_state(state1))
        _run(platform.save_deployment_state(state2))
        loaded = _run(platform.load_deployment_state("dep-003"))
        assert loaded is not None
        assert loaded.status == DeploymentStatus.RUNNING


class TestFilePlatformListDeployments:
    """Tests for listing deployments."""

    def test_list_empty_directory(self, tmp_path):
        platform = FilePlatform(state_dir=tmp_path)
        result = _run(platform.list_deployments("test-workload"))
        assert result == []

    def test_list_filters_by_workload_name(self, tmp_path):
        platform = FilePlatform(state_dir=tmp_path)
        states = [
            DeploymentState(
                deployment_id="dep-a",
                workload_name="workload-a",
                status=DeploymentStatus.RUNNING,
            ),
            DeploymentState(
                deployment_id="dep-b",
                workload_name="workload-b",
                status=DeploymentStatus.RUNNING,
            ),
            DeploymentState(
                deployment_id="dep-c",
                workload_name="workload-a",
                status=DeploymentStatus.STOPPED,
            ),
        ]
        for s in states:
            _run(platform.save_deployment_state(s))

        result = _run(platform.list_deployments("workload-a"))
        assert len(result) == 2
        ids = {d.deployment_id for d in result}
        assert ids == {"dep-a", "dep-c"}

    def test_list_ignores_corrupt_files(self, tmp_path):
        platform = FilePlatform(state_dir=tmp_path)
        # Write a valid state
        state = DeploymentState(
            deployment_id="dep-good",
            workload_name="test",
            status=DeploymentStatus.RUNNING,
        )
        _run(platform.save_deployment_state(state))
        # Write a corrupt file
        (tmp_path / "corrupt.json").write_text("not valid json{{{")

        result = _run(platform.list_deployments("test"))
        assert len(result) == 1
        assert result[0].deployment_id == "dep-good"


class TestFilePlatformCredentials:
    """Tests for credential retrieval from environment."""

    def test_get_credential_from_env(self, tmp_path):
        platform = FilePlatform(state_dir=tmp_path)
        with patch.dict(os.environ, {"AZURE_TENANT_ID": "test-tenant-123"}):
            result = _run(platform.get_credential("azure-tenant-id"))
            assert result == "test-tenant-123"

    def test_get_credential_missing_returns_none(self, tmp_path):
        platform = FilePlatform(state_dir=tmp_path)
        # Ensure the env var is not set
        env = dict(os.environ)
        env.pop("NONEXISTENT_CREDENTIAL", None)
        with patch.dict(os.environ, env, clear=True):
            result = _run(platform.get_credential("nonexistent-credential"))
            assert result is None

    def test_credential_name_conversion(self, tmp_path):
        platform = FilePlatform(state_dir=tmp_path)
        with patch.dict(os.environ, {"MY_SECRET_KEY": "secret-value"}):  # pragma: allowlist secret
            result = _run(platform.get_credential("my-secret-key"))
            assert result == "secret-value"


class TestFilePlatformLogging:
    """Tests for the log method."""

    def test_log_default_level(self, tmp_path, caplog):
        platform = FilePlatform(state_dir=tmp_path)
        import logging

        with caplog.at_level(logging.INFO, logger="haymaker.workload.test-wl"):
            platform.log("Hello world", workload="test-wl")
        assert "Hello world" in caplog.text

    def test_log_with_level(self, tmp_path, caplog):
        platform = FilePlatform(state_dir=tmp_path)
        import logging

        with caplog.at_level(logging.WARNING, logger="haymaker"):
            platform.log("A warning", level="WARNING")
        assert "A warning" in caplog.text

    def test_log_without_workload(self, tmp_path, caplog):
        platform = FilePlatform(state_dir=tmp_path)
        import logging

        with caplog.at_level(logging.INFO, logger="haymaker"):
            platform.log("Generic message")
        assert "Generic message" in caplog.text


class TestFilePlatformInit:
    """Tests for initialization."""

    def test_default_state_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        platform = FilePlatform()
        assert platform._state_dir == tmp_path / ".haymaker" / "state"
        assert platform._state_dir.exists()

    def test_custom_state_dir(self, tmp_path):
        custom = tmp_path / "custom" / "state"
        platform = FilePlatform(state_dir=custom)
        assert platform._state_dir == custom
        assert custom.exists()
