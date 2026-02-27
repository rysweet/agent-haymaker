"""Tests for CLI commands using Click's CliRunner."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import yaml
from click.testing import CliRunner

from agent_haymaker.cli.main import cli
from agent_haymaker.workloads.models import (
    CleanupReport,
    DeploymentState,
    DeploymentStatus,
)
from agent_haymaker.workloads.registry import WorkloadRegistry

runner = CliRunner()


def _make_mock_workload():
    """Create a mock workload with realistic return values."""
    wl = MagicMock()
    wl.name = "test-workload"
    wl.validate_config = AsyncMock(return_value=[])
    wl.deploy = AsyncMock(return_value="dep-test-001")
    wl.get_status = AsyncMock(
        return_value=DeploymentState(
            deployment_id="dep-test-001",
            workload_name="test-workload",
            status=DeploymentStatus.RUNNING,
        )
    )
    wl.list_deployments = AsyncMock(
        return_value=[
            DeploymentState(
                deployment_id="dep-test-001",
                workload_name="test-workload",
                status=DeploymentStatus.RUNNING,
            )
        ]
    )
    wl.stop = AsyncMock(return_value=True)
    wl.cleanup = AsyncMock(return_value=CleanupReport(deployment_id="dep-test-001"))

    async def _mock_get_logs(deployment_id, follow=False, lines=100):
        yield "log line 1"
        yield "log line 2"

    wl.get_logs = _mock_get_logs
    return wl


def _make_mock_registry(mock_wl):
    """Create a mock registry that returns the given workload."""
    registry = MagicMock()
    registry.get_workload.return_value = mock_wl
    registry.list_workloads.return_value = ["test-workload"]
    return registry


class TestCLIBasic:
    """Tests for basic CLI functionality."""

    def test_version(self):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "agent-haymaker" in result.output
        # Version should come from package metadata, not hardcoded
        assert "0.2.0" in result.output

    def test_help(self):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "deploy" in result.output
        assert "status" in result.output
        assert "list" in result.output
        assert "logs" in result.output
        assert "stop" in result.output
        assert "start" in result.output
        assert "cleanup" in result.output
        assert "workload" in result.output


class TestDeployCommand:
    """Tests for the deploy command."""

    def test_deploy_nonexistent_workload(self):
        result = runner.invoke(cli, ["deploy", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_deploy_no_workloads_installed(self):
        result = runner.invoke(cli, ["deploy", "missing-workload"])
        assert result.exit_code != 0
        assert "not found" in result.output

    @patch("agent_haymaker.cli.deploy.get_registry")
    def test_deploy_success(self, mock_get_registry):
        """Deploy succeeds with a valid workload and --yes flag."""
        mock_wl = _make_mock_workload()
        mock_get_registry.return_value = _make_mock_registry(mock_wl)

        result = runner.invoke(
            cli,
            ["deploy", "test-workload", "--config", "workers=10", "--yes"],
        )
        assert result.exit_code == 0
        assert "dep-test-001" in result.output

    @patch("agent_haymaker.cli.deploy.get_registry")
    def test_deploy_with_config_file(self, mock_get_registry):
        """Deploy reads config from YAML file."""
        mock_wl = _make_mock_workload()
        mock_get_registry.return_value = _make_mock_registry(mock_wl)

        config_data = {
            "workers": 25,
            "scenario": "email-flood",
            "duration_hours": 8,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            result = runner.invoke(
                cli,
                ["deploy", "test-workload", "--config-file", config_path, "--yes"],
            )
            assert result.exit_code == 0
            assert "dep-test-001" in result.output
            # Verify the deploy was called with config from file
            call_args = mock_wl.deploy.call_args[0][0]
            assert call_args.workload_config["workers"] == 25
            assert call_args.workload_config["scenario"] == "email-flood"
            assert call_args.duration_hours == 8
        finally:
            Path(config_path).unlink(missing_ok=True)

    @patch("agent_haymaker.cli.deploy.get_registry")
    def test_deploy_config_file_cli_precedence(self, mock_get_registry):
        """CLI --config flags take precedence over config file values."""
        mock_wl = _make_mock_workload()
        mock_get_registry.return_value = _make_mock_registry(mock_wl)

        config_data = {
            "workers": 25,
            "scenario": "email-flood",
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            result = runner.invoke(
                cli,
                [
                    "deploy",
                    "test-workload",
                    "--config-file",
                    config_path,
                    "--config",
                    "workers=50",
                    "--yes",
                ],
            )
            assert result.exit_code == 0
            call_args = mock_wl.deploy.call_args[0][0]
            # CLI overrides file
            assert call_args.workload_config["workers"] == 50
            # File value preserved where no CLI override
            assert call_args.workload_config["scenario"] == "email-flood"
        finally:
            Path(config_path).unlink(missing_ok=True)

    def test_deploy_config_file_not_found(self):
        """Deploy fails gracefully when config file doesn't exist."""
        result = runner.invoke(
            cli,
            ["deploy", "test-workload", "--config-file", "/nonexistent/path.yaml", "--yes"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "Config file not found" in result.output

    @patch("agent_haymaker.cli.deploy.get_registry")
    def test_deploy_config_file_workload_name_field(self, mock_get_registry):
        """Config file workload_name field is extracted but CLI arg is used."""
        mock_wl = _make_mock_workload()
        mock_get_registry.return_value = _make_mock_registry(mock_wl)

        config_data = {
            "workload_name": "ignored-workload",
            "workers": 10,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name

        try:
            result = runner.invoke(
                cli,
                ["deploy", "test-workload", "--config-file", config_path, "--yes"],
            )
            assert result.exit_code == 0
            call_args = mock_wl.deploy.call_args[0][0]
            # workload_name should not leak into workload_config
            assert "workload_name" not in call_args.workload_config
        finally:
            Path(config_path).unlink(missing_ok=True)


class TestWorkloadCommands:
    """Tests for workload management commands."""

    def test_workload_list_empty(self):
        mock_registry = MagicMock(spec=WorkloadRegistry)
        mock_registry.list_workloads.return_value = []
        with patch("agent_haymaker.cli.workload_mgmt.get_registry", return_value=mock_registry):
            runner = CliRunner()
            result = runner.invoke(cli, ["workload", "list"])
            assert result.exit_code == 0
            assert "No workloads" in result.output

    def test_workload_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["workload", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "install" in result.output
        assert "info" in result.output

    def test_workload_info_nonexistent(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["workload", "info", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestStatusCommand:
    """Tests for the status command."""

    def test_status_nonexistent_deployment(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "nonexistent-id"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_status_help(self):
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0
        assert "deployment_id" in result.output.lower() or "DEPLOYMENT_ID" in result.output

    @patch("agent_haymaker.cli.lifecycle.get_registry")
    def test_status_success(self, mock_get_registry):
        """Status succeeds when deployment is found."""
        mock_wl = _make_mock_workload()
        mock_get_registry.return_value = _make_mock_registry(mock_wl)

        result = runner.invoke(cli, ["status", "dep-test-001"])
        assert result.exit_code == 0
        assert "dep-test-001" in result.output
        assert "test-workload" in result.output


class TestListCommand:
    """Tests for the list command."""

    def test_list_no_deployments(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "No deployments" in result.output

    def test_list_help(self):
        result = runner.invoke(cli, ["list", "--help"])
        assert result.exit_code == 0
        assert "--workload" in result.output
        assert "--status" in result.output

    @patch("agent_haymaker.cli.lifecycle.get_registry")
    def test_list_success(self, mock_get_registry):
        """List shows deployments when they exist."""
        mock_wl = _make_mock_workload()
        mock_get_registry.return_value = _make_mock_registry(mock_wl)

        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "dep-test-001" in result.output


class TestLogsCommand:
    """Tests for the logs command."""

    def test_logs_nonexistent_deployment(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["logs", "nonexistent-id"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestStopCommand:
    """Tests for the stop command."""

    def test_stop_nonexistent_deployment(self):
        result = runner.invoke(cli, ["stop", "nonexistent-id", "--yes"])
        assert result.exit_code != 0
        assert "not found" in result.output

    @patch("agent_haymaker.cli.lifecycle.get_registry")
    def test_stop_success(self, mock_get_registry):
        """Stop succeeds with --yes flag for a running deployment."""
        mock_wl = _make_mock_workload()
        mock_get_registry.return_value = _make_mock_registry(mock_wl)

        result = runner.invoke(cli, ["stop", "dep-test-001", "--yes"])
        assert result.exit_code == 0
        assert "stopped" in result.output


class TestStartCommand:
    """Tests for the start command."""

    def test_start_nonexistent_deployment(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["start", "nonexistent-id"])
        assert result.exit_code != 0
        assert "not found" in result.output

    @patch("agent_haymaker.cli.lifecycle.get_registry")
    def test_start_success(self, mock_get_registry):
        """Start succeeds for a stopped deployment."""
        mock_wl = _make_mock_workload()
        mock_wl.get_status = AsyncMock(
            return_value=DeploymentState(
                deployment_id="dep-test-001",
                workload_name="test-workload",
                status=DeploymentStatus.STOPPED,
            )
        )
        mock_wl.start = AsyncMock(return_value=True)
        mock_get_registry.return_value = _make_mock_registry(mock_wl)

        result = runner.invoke(cli, ["start", "dep-test-001"])
        assert result.exit_code == 0
        assert "started" in result.output

    @patch("agent_haymaker.cli.lifecycle.get_registry")
    def test_start_already_running(self, mock_get_registry):
        """Start exits early when deployment is already running."""
        mock_wl = _make_mock_workload()
        mock_get_registry.return_value = _make_mock_registry(mock_wl)

        result = runner.invoke(cli, ["start", "dep-test-001"])
        assert result.exit_code == 0
        assert "already running" in result.output

    @patch("agent_haymaker.cli.lifecycle.get_registry")
    def test_start_not_implemented(self, mock_get_registry):
        """Start shows error when workload raises NotImplementedError."""
        mock_wl = _make_mock_workload()
        mock_wl.get_status = AsyncMock(
            return_value=DeploymentState(
                deployment_id="dep-test-001",
                workload_name="test-workload",
                status=DeploymentStatus.STOPPED,
            )
        )
        mock_wl.start = AsyncMock(
            side_effect=NotImplementedError(
                "Workload test-workload does not implement start/resume."
            )
        )
        mock_get_registry.return_value = _make_mock_registry(mock_wl)

        result = runner.invoke(cli, ["start", "dep-test-001"])
        assert result.exit_code != 0


class TestCleanupCommand:
    """Tests for the cleanup command."""

    def test_cleanup_nonexistent_deployment(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cleanup", "nonexistent-id", "--yes"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_cleanup_help(self):
        result = runner.invoke(cli, ["cleanup", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--yes" in result.output

    @patch("agent_haymaker.cli.lifecycle.get_registry")
    def test_cleanup_success(self, mock_get_registry):
        """Cleanup succeeds with --yes flag."""
        mock_wl = _make_mock_workload()
        # Set stopped status so cleanup proceeds normally
        mock_wl.get_status = AsyncMock(
            return_value=DeploymentState(
                deployment_id="dep-test-001",
                workload_name="test-workload",
                status=DeploymentStatus.STOPPED,
            )
        )
        mock_get_registry.return_value = _make_mock_registry(mock_wl)

        result = runner.invoke(cli, ["cleanup", "dep-test-001", "--yes"])
        assert result.exit_code == 0
        assert "Cleanup complete" in result.output
