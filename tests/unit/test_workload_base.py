"""Tests for WorkloadBase and workload exceptions."""

import pytest

from agent_haymaker.workloads.base import (
    DeploymentError,
    DeploymentNotFoundError,
    WorkloadBase,
)
from agent_haymaker.workloads.models import DeploymentConfig


class TestWorkloadBase:
    """Tests for WorkloadBase abstract class."""

    def test_cannot_instantiate_directly(self):
        """WorkloadBase is abstract and cannot be instantiated."""
        with pytest.raises(TypeError):
            WorkloadBase()

    def test_name_attribute(self):
        assert WorkloadBase.name == "base"

    def test_init_with_none_platform(self):
        """Concrete subclass with None platform should work."""

        class ConcreteWorkload(WorkloadBase):
            name = "concrete"

            async def deploy(self, config):
                return "dep-1"

            async def get_status(self, deployment_id):
                pass

            async def stop(self, deployment_id):
                return True

            async def cleanup(self, deployment_id):
                pass

            async def get_logs(self, deployment_id, follow=False, lines=100):
                yield "log line"

        wl = ConcreteWorkload(platform=None)
        assert wl.name == "concrete"
        assert wl._platform is None


class TestWorkloadBaseUtilities:
    """Tests for WorkloadBase utility methods with None platform."""

    @pytest.fixture()
    def workload(self):
        class StubWorkload(WorkloadBase):
            name = "stub"

            async def deploy(self, config):
                return "dep-1"

            async def get_status(self, deployment_id):
                pass

            async def stop(self, deployment_id):
                return True

            async def cleanup(self, deployment_id):
                pass

            async def get_logs(self, deployment_id, follow=False, lines=100):
                yield "log"

        return StubWorkload(platform=None)

    async def test_validate_config_default(self, workload):
        """Default validate_config checks workload_name."""
        config = DeploymentConfig(workload_name="test")
        errors = await workload.validate_config(config)
        assert errors == []

    async def test_save_state_with_none_platform(self, workload):
        """save_state should be a no-op with None platform."""
        await workload.save_state(None)  # Should not raise

    async def test_load_state_with_none_platform(self, workload):
        """load_state returns None with no platform."""
        result = await workload.load_state("dep-1")
        assert result is None

    async def test_get_credential_with_none_platform(self, workload):
        """get_credential returns None with no platform."""
        result = await workload.get_credential("some-secret")
        assert result is None

    def test_log_with_none_platform(self, workload):
        """log should be a no-op with None platform."""
        workload.log("test message")  # Should not raise

    async def test_list_deployments_with_none_platform(self, workload):
        """list_deployments returns empty list with no platform."""
        result = await workload.list_deployments()
        assert result == []


class TestDeploymentExceptions:
    """Tests for deployment exception classes."""

    def test_deployment_error_is_exception(self):
        assert issubclass(DeploymentError, Exception)

    def test_deployment_not_found_error_is_exception(self):
        assert issubclass(DeploymentNotFoundError, Exception)

    def test_deployment_error_message(self):
        err = DeploymentError("deploy failed")
        assert str(err) == "deploy failed"

    def test_deployment_not_found_error_message(self):
        err = DeploymentNotFoundError("dep-123 not found")
        assert str(err) == "dep-123 not found"

    def test_exceptions_are_catchable(self):
        with pytest.raises(DeploymentError):
            raise DeploymentError("test")

        with pytest.raises(DeploymentNotFoundError):
            raise DeploymentNotFoundError("test")
