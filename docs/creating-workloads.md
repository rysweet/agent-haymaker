---
layout: default
title: Creating Workloads
---

# Creating Workloads

Workloads are Python packages that implement the `WorkloadBase` interface. Each workload is a self-contained unit that the platform discovers, deploys, and manages through a standard contract.

[Back to Home](index.md)

## Overview

A workload is responsible for:

- **Deploying** resources (VMs, containers, identities, etc.)
- **Reporting status** so the CLI and platform can monitor progress
- **Stopping and starting** on demand
- **Cleaning up** all resources it created
- **Streaming logs** for observability

The platform handles discovery, state tracking, credential management, and CLI routing. You only implement the workload logic.

## Package Structure

```
my-workload/
+-- pyproject.toml        # Package metadata and entry point registration
+-- workload.yaml         # Workload descriptor (name, type, targets)
+-- README.md             # Documentation
+-- src/
|   +-- my_workload/
|       +-- __init__.py
|       +-- workload.py   # WorkloadBase implementation
+-- tests/
    +-- test_workload.py
```

## Step 1: Implement WorkloadBase

Create a class that inherits from `WorkloadBase` and implements all required methods.

```python
# src/my_workload/workload.py
from agent_haymaker import WorkloadBase, DeploymentState, DeploymentConfig, CleanupReport


class MyWorkload(WorkloadBase):
    name = "my-workload"

    async def deploy(self, config: DeploymentConfig) -> str:
        """Start a new deployment. Return the deployment ID."""
        deployment_id = generate_id()
        # Create resources, start processes, etc.
        return deployment_id

    async def get_status(self, deployment_id: str) -> DeploymentState:
        """Return the current state of a deployment."""
        return DeploymentState(
            deployment_id=deployment_id,
            workload_name=self.name,
            status="running",
            phase="executing",
        )

    async def stop(self, deployment_id: str) -> bool:
        """Stop a running deployment. Return True on success."""
        # Pause processes, deallocate ephemeral resources
        return True

    async def start(self, deployment_id: str) -> bool:
        """Resume a stopped deployment. Return True on success."""
        # Re-acquire resources, resume processes
        return True

    async def cleanup(self, deployment_id: str) -> CleanupReport:
        """Delete all resources created by this deployment."""
        # Remove VMs, delete resource groups, revoke credentials, etc.
        return CleanupReport(
            deployment_id=deployment_id,
            resources_deleted=10,
        )

    async def get_logs(self, deployment_id: str, follow: bool = False, lines: int = 100):
        """Yield log lines. If follow=True, stream continuously."""
        yield "2024-01-01T00:00:00Z Starting deployment..."
        yield "2024-01-01T00:00:01Z Resources provisioned"
```

### Method Contract

| Method | Called by | Must return | Notes |
|--------|-----------|-------------|-------|
| `deploy(config)` | `haymaker deploy` | `str` (deployment ID) | Should be idempotent if called again with same config |
| `get_status(id)` | `haymaker status` | `DeploymentState` | Raise if deployment ID is unknown |
| `stop(id)` | `haymaker stop` | `bool` | Return `False` if already stopped |
| `start(id)` | `haymaker start` | `bool` | Return `False` if already running |
| `cleanup(id)` | `haymaker cleanup` | `CleanupReport` | Must remove all created resources |
| `get_logs(id)` | `haymaker logs` | async generator of `str` | Support `follow` for real-time streaming |
| `validate_config(config)` | Before `deploy` | `list[str]` (errors) | Return empty list if config is valid |
| `list_deployments()` | `haymaker list` | `list[DeploymentState]` | All deployments for this workload |

### DeploymentConfig Fields

The `DeploymentConfig` object passed to `deploy()` contains:

| Field | Type | Description |
|-------|------|-------------|
| `workload_name` | `str` | Name of the workload |
| `duration_hours` | `int | None` | Duration limit (None = indefinite) |
| `tags` | `dict[str, str]` | User-provided key=value tags |
| `workload_config` | `dict[str, Any]` | Workload-specific configuration |

Access workload-specific settings via `config.workload_config`:

```python
async def deploy(self, config: DeploymentConfig) -> str:
    num_workers = config.workload_config.get("workers", 10)
    department = config.workload_config.get("department", "engineering")
    # ...
```

## Step 2: Register via Entry Point

Add an entry point in `pyproject.toml` so the platform discovers your workload automatically:

```toml
[project]
name = "my-workload"
version = "1.0.0"
dependencies = ["agent-haymaker"]

[project.entry-points."agent_haymaker.workloads"]
my-workload = "my_workload:MyWorkload"
```

The key (`my-workload`) is the name users will pass to `haymaker deploy`. The value is the import path to your class.

## Step 3: Create workload.yaml

The `workload.yaml` file describes your workload metadata and what Azure resources or permissions it needs:

```yaml
name: my-workload
version: "1.0.0"
type: runtime
description: "My custom workload description"

entrypoint: my_workload:MyWorkload

targets:
  - type: azure_subscription
    required_roles:
      - Contributor

config_schema:
  workers:
    type: integer
    default: 10
    description: "Number of worker instances"
  department:
    type: string
    default: "engineering"
    description: "Target department"
```

### Target Types

| Type | Description | Common Roles |
|------|-------------|--------------|
| `azure_subscription` | Azure subscription access | Contributor, Reader |
| `m365_tenant` | Microsoft 365 tenant access | Exchange Admin, SharePoint Admin |
| `entra_directory` | Entra ID directory operations | User Administrator |

## Step 4: Using LLM Integration

Workloads that need AI capabilities can use the built-in LLM abstraction layer:

```python
from agent_haymaker.llm import create_llm_client, LLMConfig, LLMMessage


class SmartWorkload(WorkloadBase):
    name = "smart-workload"

    async def deploy(self, config: DeploymentConfig) -> str:
        # Create LLM client from environment
        llm_config = LLMConfig.from_env()
        llm = create_llm_client(llm_config)

        # Use it to generate realistic content
        messages = [LLMMessage(role="user", content="Write a status update email")]
        response = llm.create_message(messages, system="You are a project manager.")

        # Use response.content in your workload logic
        # ...
```

See the [LLM Provider Configuration](llm-providers.md) guide for provider setup details.

## Step 5: Install and Test

```bash
# Install your workload in development mode
pip install -e ./my-workload

# Verify it appears in the registry
haymaker workload list
haymaker workload info my-workload

# Deploy
haymaker deploy my-workload --config workers=5

# Check status
haymaker status <deployment-id>
```

You can also install workloads from a git repository:

```bash
haymaker workload install https://github.com/org/my-workload
```

## Testing

Write tests that verify your workload fulfills the contract:

```python
import pytest
from my_workload import MyWorkload
from agent_haymaker import DeploymentConfig


@pytest.mark.asyncio
async def test_deploy_returns_id():
    workload = MyWorkload()
    config = DeploymentConfig(
        workload_name="my-workload",
        workload_config={"workers": 5},
    )
    deployment_id = await workload.deploy(config)
    assert isinstance(deployment_id, str)
    assert len(deployment_id) > 0


@pytest.mark.asyncio
async def test_status_after_deploy():
    workload = MyWorkload()
    config = DeploymentConfig(workload_name="my-workload", workload_config={})
    deployment_id = await workload.deploy(config)

    state = await workload.get_status(deployment_id)
    assert state.deployment_id == deployment_id
    assert state.workload_name == "my-workload"
    assert state.status in ("running", "deploying")


@pytest.mark.asyncio
async def test_cleanup_removes_resources():
    workload = MyWorkload()
    config = DeploymentConfig(workload_name="my-workload", workload_config={})
    deployment_id = await workload.deploy(config)

    report = await workload.cleanup(deployment_id)
    assert report.deployment_id == deployment_id
    assert report.resources_deleted >= 0
```

## Example Workload Repositories

For complete working examples, see:

- [haymaker-azure-workloads](https://github.com/rysweet/haymaker-azure-workloads) -- Azure infrastructure scenarios with goal-seeking agents
- [haymaker-m365-workloads](https://github.com/rysweet/haymaker-m365-workloads) -- M365 knowledge worker simulation
