# Agent Haymaker

Universal workload orchestration platform for Azure and M365 telemetry generation.

## Overview

Agent Haymaker is a platform that enables deploying and managing **workloads** - specialized agents that generate realistic telemetry in Azure tenants and M365 environments. The platform provides:

- **Universal CLI** for lifecycle management (deploy, status, stop, cleanup)
- **WorkloadBase** interface that all workloads implement
- **Workload Registry** for discovering and installing workloads
- **State management** for tracking deployments
- **Credential management** integration with Azure Key Vault

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT HAYMAKER PLATFORM                       │
│                                                                  │
│  WorkloadBase (interface)         Universal CLI                  │
│  ├── deploy()                     ├── haymaker deploy            │
│  ├── get_status()                 ├── haymaker status            │
│  ├── stop()                       ├── haymaker stop              │
│  ├── start()                      ├── haymaker start             │
│  ├── cleanup()                    ├── haymaker cleanup           │
│  └── get_logs()                   └── haymaker logs              │
│                                                                  │
│  Workload Registry    State Storage    Credential Management     │
└─────────────────────────────────────────────────────────────────┘
                              │
                   implements │ WorkloadBase
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    WORKLOAD PACKAGES                             │
│                                                                  │
│  haymaker-azure-workloads       haymaker-m365-workloads          │
│  ├── Azure infrastructure       ├── Knowledge workers            │
│  ├── Goal-seeking agents        ├── M365 operations              │
│  └── Scenario execution         └── Entra identity mgmt          │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
pip install agent-haymaker
```

## Quick Start

### 1. Install a Workload

```bash
# From git repository
haymaker workload install https://github.com/rysweet/haymaker-m365-workloads

# From local path
haymaker workload install ./my-workload
```

### 2. Deploy

```bash
# Deploy M365 knowledge workers
haymaker deploy m365-knowledge-worker --config workers=25 --config department=sales

# Deploy Azure infrastructure scenario
haymaker deploy azure-infrastructure --config scenario=linux-vm-web-server
```

### 3. Manage

```bash
# Check status
haymaker status dep-abc123

# View logs
haymaker logs dep-abc123 --follow

# Stop
haymaker stop dep-abc123

# Resume
haymaker start dep-abc123

# Clean up resources
haymaker cleanup dep-abc123
```

### 4. List

```bash
# List all deployments
haymaker list

# Filter by workload
haymaker list --workload m365-knowledge-worker

# Filter by status
haymaker list --status running
```

## Creating a Workload

Workloads are Python packages that implement the `WorkloadBase` interface.

### 1. Create the Package Structure

```
my-workload/
├── pyproject.toml
├── workload.yaml
├── src/
│   └── my_workload/
│       ├── __init__.py
│       └── workload.py
└── README.md
```

### 2. Implement WorkloadBase

```python
# src/my_workload/workload.py
from agent_haymaker import WorkloadBase, DeploymentState, DeploymentConfig, CleanupReport

class MyWorkload(WorkloadBase):
    name = "my-workload"

    async def deploy(self, config: DeploymentConfig) -> str:
        # Start deployment, return deployment_id
        deployment_id = generate_id()
        # ... your deployment logic
        return deployment_id

    async def get_status(self, deployment_id: str) -> DeploymentState:
        # Return current state
        return DeploymentState(
            deployment_id=deployment_id,
            workload_name=self.name,
            status="running",
            phase="executing",
        )

    async def stop(self, deployment_id: str) -> bool:
        # Stop the deployment
        return True

    async def cleanup(self, deployment_id: str) -> CleanupReport:
        # Clean up all resources
        return CleanupReport(
            deployment_id=deployment_id,
            resources_deleted=10,
        )

    async def get_logs(self, deployment_id: str, follow: bool = False, lines: int = 100):
        # Yield log lines
        yield "Log line 1"
        yield "Log line 2"
```

### 3. Register via Entry Point

```toml
# pyproject.toml
[project.entry-points."agent_haymaker.workloads"]
my-workload = "my_workload:MyWorkload"
```

### 4. Create workload.yaml

```yaml
name: my-workload
version: "1.0.0"
type: runtime
description: "My custom workload"

entrypoint: my_workload:MyWorkload

targets:
  - type: azure_subscription
    required_roles:
      - Contributor
```

## Available Workloads

| Workload | Description | Repository |
|----------|-------------|------------|
| `azure-infrastructure` | Azure scenario execution with goal-seeking agents | [haymaker-azure-workloads](https://github.com/rysweet/haymaker-azure-workloads) |
| `m365-knowledge-worker` | M365 knowledge worker simulation | [haymaker-m365-workloads](https://github.com/rysweet/haymaker-m365-workloads) |

## Development

```bash
# Clone
git clone https://github.com/rysweet/agent-haymaker
cd agent-haymaker

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
pyright
```

## License

MIT
