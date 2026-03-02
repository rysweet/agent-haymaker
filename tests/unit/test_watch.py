"""Tests for the watch CLI command."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from agent_haymaker.cli.main import cli
from agent_haymaker.events import (
    DEPLOYMENT_COMPLETED,
    DEPLOYMENT_FAILED,
    DEPLOYMENT_LOG,
    DEPLOYMENT_PHASE_CHANGED,
    DEPLOYMENT_STARTED,
    DEPLOYMENT_STOPPED,
    WORKLOAD_PROGRESS,
)
from agent_haymaker.workloads.models import DeploymentState, DeploymentStatus


@pytest.fixture
def runner():
    return CliRunner()


def _make_mock_state(dep_id: str = "dep-1") -> DeploymentState:
    return DeploymentState(
        deployment_id=dep_id,
        workload_name="test",
        status=DeploymentStatus.RUNNING,
    )


class TestWatchCommand:
    """Tests for the 'haymaker watch' CLI command."""

    def test_watch_help(self, runner):
        """watch --help should show usage info with --wait-for and --timeout options."""
        result = runner.invoke(cli, ["watch", "--help"])
        assert result.exit_code == 0
        assert "--wait-for" in result.output
        assert "--timeout" in result.output

    def test_watch_deployment_not_found(self, runner):
        """watch should fail when the deployment ID does not exist in any workload."""
        result = runner.invoke(cli, ["watch", "nonexistent-dep-id"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_watch_no_platform_event_support(self, runner):
        """watch should fail when the platform lacks subscribe/event support."""
        mock_state = _make_mock_state()
        mock_workload = MagicMock()
        mock_workload.get_status = AsyncMock(return_value=mock_state)
        mock_workload.name = "test"

        mock_registry = MagicMock()
        mock_registry.list_workloads.return_value = ["test"]
        mock_registry.get_workload.return_value = mock_workload
        mock_registry.discover_workloads.return_value = {}

        # Platform without subscribe method (no event support)
        platform_without_events = MagicMock(spec=[])

        with (
            patch(
                "agent_haymaker.cli.lookup.find_deployment_async",
                new_callable=AsyncMock,
                return_value=(mock_workload, mock_state),
            ),
            patch(
                "agent_haymaker.cli.main.get_registry",
                return_value=mock_registry,
            ),
            patch(
                "agent_haymaker.cli.main.FilePlatform",
                return_value=platform_without_events,
            ),
            patch(
                "agent_haymaker.cli.main.WorkloadRegistry",
                return_value=mock_registry,
            ),
        ):
            result = runner.invoke(cli, ["watch", "dep-1"])
            # Should exit with error about event/platform support
            assert result.exit_code != 0

    def test_watch_subscribes_to_all_topics(self, runner):
        """watch should subscribe to all deployment event topics."""
        mock_state = _make_mock_state()
        mock_workload = MagicMock()
        mock_workload.get_status = AsyncMock(return_value=mock_state)
        mock_workload.name = "test"

        mock_registry = MagicMock()
        mock_registry.list_workloads.return_value = ["test"]
        mock_registry.get_workload.return_value = mock_workload
        mock_registry.discover_workloads.return_value = {}

        subscribed_topics: list[str] = []
        sub_counter = 0

        async def mock_subscribe(topic, callback):
            nonlocal sub_counter
            subscribed_topics.append(topic)
            sub_counter += 1
            return f"sub-{sub_counter}"

        async def mock_unsubscribe(sub_id):
            pass

        mock_platform = MagicMock()
        mock_platform.subscribe = mock_subscribe
        mock_platform.unsubscribe = mock_unsubscribe

        # Patch the lookup function AND the cli group setup so that
        # the watch command gets our mock platform from ctx.obj.
        with (
            patch(
                "agent_haymaker.cli.lookup.find_deployment_async",
                new_callable=AsyncMock,
                return_value=(mock_workload, mock_state),
            ),
            patch(
                "agent_haymaker.cli.main.FilePlatform",
                return_value=mock_platform,
            ),
            patch(
                "agent_haymaker.cli.main.WorkloadRegistry",
                return_value=mock_registry,
            ),
        ):
            runner.invoke(
                cli,
                ["watch", "dep-1", "--wait-for", "completed", "--timeout", "1"],
            )

        expected_topics = [
            DEPLOYMENT_STARTED,
            DEPLOYMENT_COMPLETED,
            DEPLOYMENT_FAILED,
            DEPLOYMENT_STOPPED,
            DEPLOYMENT_PHASE_CHANGED,
            DEPLOYMENT_LOG,
            WORKLOAD_PROGRESS,
        ]
        for topic in expected_topics:
            assert topic in subscribed_topics, f"Missing subscription to {topic}"

    def test_watch_wait_for_choices(self, runner):
        """--wait-for should only accept completed, failed, stopped."""
        result = runner.invoke(cli, ["watch", "dep-1", "--wait-for", "invalid"])
        assert result.exit_code != 0
        assert "invalid" in result.output.lower() or "Invalid value" in result.output

    def test_watch_timeout_option_accepts_int(self, runner):
        """--timeout should accept an integer value."""
        # Just verify the option parsing works; the command will fail on deployment lookup
        result = runner.invoke(cli, ["watch", "dep-1", "--timeout", "300"])
        # It fails because deployment not found, not because of bad option
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_watch_outputs_watching_message(self, runner):
        """watch should print 'Watching deployment ...' on successful subscribe."""
        mock_state = _make_mock_state()
        mock_workload = MagicMock()
        mock_workload.get_status = AsyncMock(return_value=mock_state)
        mock_workload.name = "test"

        mock_registry = MagicMock()
        mock_registry.list_workloads.return_value = ["test"]
        mock_registry.get_workload.return_value = mock_workload
        mock_registry.discover_workloads.return_value = {}

        async def mock_subscribe(topic, callback):
            return "sub-1"

        async def mock_unsubscribe(sub_id):
            pass

        mock_platform = MagicMock()
        mock_platform.subscribe = mock_subscribe
        mock_platform.unsubscribe = mock_unsubscribe

        with (
            patch(
                "agent_haymaker.cli.lookup.find_deployment_async",
                new_callable=AsyncMock,
                return_value=(mock_workload, mock_state),
            ),
            patch(
                "agent_haymaker.cli.main.FilePlatform",
                return_value=mock_platform,
            ),
            patch(
                "agent_haymaker.cli.main.WorkloadRegistry",
                return_value=mock_registry,
            ),
        ):
            watch_result = runner.invoke(
                cli,
                ["watch", "dep-1", "--wait-for", "completed", "--timeout", "1"],
            )

        assert "Watching deployment dep-1" in watch_result.output
