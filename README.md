# Agent Haymaker

Event-driven workload orchestration platform for deploying and managing agents in Azure.

## Overview

Agent Haymaker is the platform layer that deploys **workloads** (specialized agents that generate telemetry) to Azure Container Apps, manages their lifecycle, and streams events in real-time via Azure Service Bus. The platform provides:

- **Azure deployment** - Container Apps, Service Principals, Key Vault credential storage
- **7-phase orchestration** - validate, provision, monitor, cleanup, report
- **Event-driven architecture** - Azure Service Bus for real-time streaming, local event bus for development
- **Universal CLI** - deploy, status, watch, logs, stop, cleanup
- **WorkloadBase interface** - plug-in any workload package

```
┌─────────────────────────────────────────────────────────────────────┐
│                     AGENT HAYMAKER PLATFORM                         │
│                                                                     │
│  AzurePlatform (cloud)              FilePlatform (local dev)        │
│  ├── Container App deployment       ├── File-based state            │
│  ├── Service Principal mgmt         ├── Local event bus             │
│  ├── Key Vault credentials          └── Env var credentials         │
│  ├── Service Bus event streaming                                    │
│  └── Resource lifecycle mgmt                                        │
│                                                                     │
│  Orchestrator                       Event Bus                       │
│  ├── 7-phase workflow               ├── ServiceBusEventBus (Azure)  │
│  ├── FanOutController               └── LocalEventBus (local)       │
│  └── Execution tracking                                             │
│                                                                     │
│  CLI: haymaker                                                      │
│  ├── deploy / status / stop / start / cleanup / logs                │
│  ├── watch (real-time event streaming)                              │
│  └── azure validate / deploy / run / status / cleanup               │
└─────────────────────────────────────────────────────────────────────┘
                              │
                   implements │ WorkloadBase
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       WORKLOAD PACKAGES                             │
│                                                                     │
│  haymaker-azure-workloads         haymaker-m365-workloads           │
│  ├── 15 Azure infra scenarios     ├── Knowledge workers             │
│  ├── Goal-seeking agents          ├── Email/Teams/Docs generation   │
│  └── az CLI-based provisioning    └── Entra identity management     │
└─────────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Core platform
pip install agent-haymaker

# With Azure deployment support (Container Apps, Service Bus, Key Vault)
pip install agent-haymaker[azure]

# With LLM provider support (Anthropic, Azure OpenAI, Azure AI Foundry)
pip install agent-haymaker[llm]

# Everything
pip install agent-haymaker[azure,llm]
```

## Quick Start

### Local Development (no Azure required)

```bash
# Install a workload
haymaker workload install https://github.com/rysweet/haymaker-workload-starter

# Deploy locally
haymaker deploy my-workload --config goal_file=goals/sample.md

# Watch events in real-time
haymaker watch <deployment-id>

# Check status
haymaker status <deployment-id>
haymaker status <deployment-id> --follow

# View logs
haymaker logs <deployment-id> --follow

# Clean up
haymaker cleanup <deployment-id>
```

### Azure Deployment

```bash
# Configure Azure (env vars or ~/.haymaker/azure.yaml)
export AZURE_TENANT_ID="00000000-..."
export AZURE_SUBSCRIPTION_ID="00000000-..."
export HAYMAKER_RESOURCE_GROUP="haymaker-rg"
export HAYMAKER_CONTAINER_REGISTRY="myregistry.azurecr.io"
export HAYMAKER_CONTAINER_IMAGE="myregistry.azurecr.io/agent:latest"
export HAYMAKER_CONTAINER_ENV_NAME="haymaker-env"
export HAYMAKER_SERVICEBUS_CONNECTION="Endpoint=sb://..."  # REQUIRED for Azure

# Validate environment
haymaker azure validate

# Deploy a workload to Azure Container Apps
haymaker azure deploy azure-infrastructure --image myregistry.azurecr.io/agent:latest

# Run full 7-phase orchestration
haymaker azure run \
  -w azure-infrastructure \
  -w m365-knowledge-worker \
  --duration 8 \
  --interval 15

# Check Azure container status
haymaker azure status <app-name>

# Clean up Azure resources
haymaker azure cleanup --all
```

### Configuration

Azure settings can be provided via environment variables or `~/.haymaker/azure.yaml`:

```yaml
tenant_id: "00000000-..."
subscription_id: "00000000-..."
resource_group: "haymaker-rg"
location: "eastus"

container:
  registry: "myregistry.azurecr.io"
  image: "haymaker-agent:latest"
  environment_name: "haymaker-env"
  memory_gb: 2
  cpu_cores: 1.0

service_bus:
  connection_string: "Endpoint=sb://..."
  topic_name: "agent-logs"

key_vault_url: "https://myvault.vault.azure.net/"
```

## Architecture

### Two Platforms

| Platform | Event Bus | Use Case |
|----------|-----------|----------|
| `FilePlatform` | `LocalEventBus` (asyncio) | Local development, testing, no Azure |
| `AzurePlatform` | `ServiceBusEventBus` (Azure Service Bus) | Cloud deployment (Service Bus **required**) |

`AzurePlatform` refuses to start without Service Bus configuration. There is no silent fallback to local events - if you're on Azure, you get Service Bus. For local development, use `FilePlatform`.

### Event Bus

Events flow through the bus using a dual-write pattern (when on Azure):

```
WorkloadBase.emit_event()
       │
       ▼
Platform.publish_event()
       │
       ▼
ServiceBusEventBus.publish()
       ├── WRITE 1: Azure Service Bus topic (real-time, external consumers)
       └── WRITE 2: Local asyncio bus (CLI watch, status --follow)
```

**Event types:**
- `deployment.started` / `deployment.completed` / `deployment.failed`
- `deployment.phase_changed` / `deployment.stopped`
- `deployment.log` / `workload.progress`
- `resource.created` / `resource.deleted`

### 7-Phase Orchestration Workflow

The `haymaker azure run` command executes a complete deployment pipeline:

1. **Validation** - Check Azure CLI auth, subscription, resource group, registry
2. **Selection** - Validate workload list
3. **Provisioning** - Create Service Principals + deploy Container Apps (parallel)
4. **Monitoring** - Periodic status checks for configured duration
5. **Cleanup Verification** - Check all managed resources are deleted
6. **Forced Cleanup** - Delete remaining resources if needed
7. **Reporting** - Generate execution summary

### FanOutController

For parallel workload execution with concurrency control:

```python
from agent_haymaker.orchestrator import FanOutController, FailureMode

controller = FanOutController(max_parallelism=5)
result = await controller.execute(
    items=[
        {"deployment_id": "dep-1", "workload_name": "w1"},
        {"deployment_id": "dep-2", "workload_name": "w2"},
    ],
    execute_fn=my_async_function,
    failure_mode=FailureMode.CONTINUE,  # or FAIL_FAST
)
print(f"Succeeded: {result.succeeded_count}/{result.total_count}")
```

## Creating a Workload

Workloads are Python packages that implement the `WorkloadBase` interface and register via entry points.

### Implement WorkloadBase

```python
from agent_haymaker import WorkloadBase, DeploymentConfig, DeploymentState
from agent_haymaker.workloads.models import CleanupReport, DeploymentStatus

class MyWorkload(WorkloadBase):
    name = "my-workload"

    async def deploy(self, config: DeploymentConfig) -> str:
        deployment_id = f"{self.name}-{uuid4().hex[:8]}"
        await self.emit_event("deployment.started", deployment_id)
        # ... your deployment logic ...
        await self.emit_progress(deployment_id, "running", "Deployed", percent=100.0)
        return deployment_id

    async def get_status(self, deployment_id: str) -> DeploymentState: ...
    async def stop(self, deployment_id: str) -> bool: ...
    async def cleanup(self, deployment_id: str) -> CleanupReport: ...
    async def get_logs(self, deployment_id, follow=False, lines=100): ...
```

### Event Emission Helpers

Workloads can emit structured events through the platform:

```python
# Generic event
await self.emit_event("deployment.phase_changed", deployment_id, phase="executing")

# Progress update
await self.emit_progress(deployment_id, "phase-2", "Processing items", percent=45.0)

# Log line
await self.emit_log(deployment_id, "Created 5 resources", level="INFO")
```

### Register via Entry Point

```toml
# pyproject.toml
[project.entry-points."agent_haymaker.workloads"]
my-workload = "my_workload:MyWorkload"
```

## Available Workloads

| Workload | Description | Repository |
|----------|-------------|------------|
| `azure-infrastructure` | 15 Azure infra scenarios with goal-seeking agents | [haymaker-azure-workloads](https://github.com/rysweet/haymaker-azure-workloads) |
| `m365-knowledge-worker` | M365 knowledge worker simulation | [haymaker-m365-workloads](https://github.com/rysweet/haymaker-m365-workloads) |
| `my-workload` | Goal-seeking agent workload starter template | [haymaker-workload-starter](https://github.com/rysweet/haymaker-workload-starter) |

## LLM Integration

Multi-provider LLM abstraction for AI-powered workloads.

```bash
pip install agent-haymaker[llm]
```

```python
from agent_haymaker.llm import create_llm_client, LLMConfig, LLMMessage

config = LLMConfig.from_env()  # Reads LLM_PROVIDER, API keys from env
client = create_llm_client(config)
response = client.create_message(
    [LLMMessage(role="user", content="Write a status report")],
    system="You are a business writer.",
)
```

Supported: Anthropic Claude, Azure OpenAI, Azure AI Foundry.

## Project Structure

```
src/agent_haymaker/
├── __init__.py              # Top-level public API
├── cli/                     # CLI commands
│   ├── main.py              # haymaker root group
│   ├── deploy.py            # haymaker deploy
│   ├── lifecycle.py         # status, list, logs, stop, start, cleanup
│   ├── watch.py             # haymaker watch (real-time events)
│   ├── azure_commands.py    # haymaker azure validate/deploy/run/status/cleanup
│   ├── lookup.py            # Deployment lookup helper
│   └── workload_mgmt.py     # haymaker workload list/install/info
├── events/                  # Event bus infrastructure
│   ├── bus.py               # LocalEventBus (asyncio queues)
│   └── types.py             # Event type constants, EventData model
├── orchestrator/            # Execution control
│   ├── fan_out.py           # FanOutController (parallel with semaphore)
│   ├── workflow.py          # 7-phase orchestration pipeline
│   └── types.py             # ExecutionState, ExecutionResult models
├── azure/                   # Azure deployment infrastructure
│   ├── config.py            # AzureConfig (env/YAML loading)
│   ├── platform.py          # AzurePlatform (Container Apps, SPs, Key Vault)
│   └── service_bus.py       # ServiceBusEventBus (dual-write)
├── workloads/               # Workload plugin system
│   ├── platform.py          # Platform protocol
│   ├── base.py              # WorkloadBase ABC
│   ├── event_helpers.py     # EventEmitterMixin
│   ├── file_platform.py     # FilePlatform (local development)
│   ├── models.py            # DeploymentState, DeploymentConfig, etc.
│   └── registry.py          # WorkloadRegistry (entry-point discovery)
└── llm/                     # LLM abstraction layer
    ├── config.py            # LLMConfig
    ├── factory.py           # create_llm_client()
    └── providers/           # Anthropic, Azure OpenAI, Azure AI Foundry
```

## Development

```bash
git clone https://github.com/rysweet/agent-haymaker
cd agent-haymaker
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
ruff format --check src/
```

## License

MIT
