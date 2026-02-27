"""Tests for CLI commands using Click's CliRunner."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from agent_haymaker.cli.main import cli
from agent_haymaker.workloads.registry import WorkloadRegistry


class TestCLIBasic:
    """Tests for basic CLI functionality."""

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "agent-haymaker" in result.output
        assert "0.1.0" in result.output

    def test_help(self):
        runner = CliRunner()
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
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_deploy_no_workloads_installed(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "missing-workload"])
        assert result.exit_code != 0
        assert "not found" in result.output


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
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0
        assert "deployment_id" in result.output.lower() or "DEPLOYMENT_ID" in result.output


class TestListCommand:
    """Tests for the list command."""

    def test_list_no_deployments(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["list"])
        assert result.exit_code == 0
        assert "No deployments" in result.output

    def test_list_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["list", "--help"])
        assert result.exit_code == 0
        assert "--workload" in result.output
        assert "--status" in result.output


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
        runner = CliRunner()
        result = runner.invoke(cli, ["stop", "nonexistent-id", "--yes"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestStartCommand:
    """Tests for the start command."""

    def test_start_nonexistent_deployment(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["start", "nonexistent-id"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestCleanupCommand:
    """Tests for the cleanup command."""

    def test_cleanup_nonexistent_deployment(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cleanup", "nonexistent-id", "--yes"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_cleanup_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["cleanup", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
        assert "--yes" in result.output
