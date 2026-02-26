"""Agent Haymaker - Universal workload orchestration platform.

Agent Haymaker provides a platform for deploying and managing workloads
that generate telemetry for Azure tenants and M365 environments.

Key components:
    - WorkloadBase: Base class all workloads inherit from
    - WorkloadRegistry: Discovers and manages workload implementations
    - CLI: Universal commands for lifecycle management

Quick start:
    # Install the platform
    pip install agent-haymaker

    # Install a workload
    haymaker workload install https://github.com/org/haymaker-m365-workloads

    # Deploy
    haymaker deploy m365-knowledge-worker --config workers=25

    # Manage
    haymaker status <deployment-id>
    haymaker logs <deployment-id> --follow
    haymaker stop <deployment-id>
    haymaker cleanup <deployment-id>
"""

from .workloads import (
    WorkloadBase,
    WorkloadRegistry,
    DeploymentState,
    DeploymentConfig,
    WorkloadManifest,
)

# LLM abstraction - lazy imports to avoid requiring LLM deps for basic usage
# Use: from agent_haymaker.llm import create_llm_client, LLMConfig

__version__ = "0.2.0"

__all__ = [
    "WorkloadBase",
    "WorkloadRegistry",
    "DeploymentState",
    "DeploymentConfig",
    "WorkloadManifest",
    "__version__",
]
