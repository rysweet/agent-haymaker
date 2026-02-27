"""Tests for WorkloadRegistry."""

from agent_haymaker.workloads.base import WorkloadBase
from agent_haymaker.workloads.registry import WorkloadRegistry


class ConcreteWorkload(WorkloadBase):
    """Concrete workload for testing registry operations."""

    name = "test-workload"

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
