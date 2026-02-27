"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _clear_deployment_index_cache():
    """Clear the lifecycle deployment index cache between tests."""
    from agent_haymaker.cli import lifecycle

    lifecycle._deployment_index.clear()
    yield
    lifecycle._deployment_index.clear()
