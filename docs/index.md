---
layout: default
title: Home
---

# Agent Haymaker

Universal workload orchestration platform for Azure and M365 telemetry generation.

Agent Haymaker deploys and manages **workloads** -- specialized agents that generate realistic telemetry in Azure tenants and M365 environments. It provides a single CLI and a standard interface so that any workload, whether it simulates Azure infrastructure scenarios or M365 knowledge workers, plugs in and behaves the same way.

## Guides

- [LLM Provider Configuration](llm-providers.md) -- Set up Anthropic Claude, Azure OpenAI, or Azure AI Foundry for AI-powered workloads
- [Creating Workloads](creating-workloads.md) -- Build a custom workload package that implements the WorkloadBase interface
- [CLI Reference](cli-reference.md) -- Complete reference for every `haymaker` command and option

## Quick Start

### Install

```bash
pip install agent-haymaker
```

### Install a workload

```bash
# From a git repository
haymaker workload install https://github.com/rysweet/haymaker-m365-workloads

# From a local path
haymaker workload install ./my-workload
```

### Deploy

```bash
# Deploy M365 knowledge workers
haymaker deploy m365-knowledge-worker --config workers=25 --config department=sales

# Deploy an Azure infrastructure scenario
haymaker deploy azure-infrastructure --config scenario=linux-vm-web-server
```

### Manage

```bash
haymaker status dep-abc123          # Check status
haymaker logs dep-abc123 --follow   # Stream logs
haymaker stop dep-abc123            # Stop a deployment
haymaker start dep-abc123           # Resume a stopped deployment
haymaker cleanup dep-abc123         # Delete all resources
haymaker list --status running      # List active deployments
```

See the [CLI Reference](cli-reference.md) for the full set of commands and options.

## Architecture

```
+------------------------------------------------------------------+
|                    AGENT HAYMAKER PLATFORM                        |
|                                                                   |
|  WorkloadBase (interface)         Universal CLI                   |
|  +-- deploy()                     +-- haymaker deploy             |
|  +-- get_status()                 +-- haymaker status             |
|  +-- stop()                       +-- haymaker stop               |
|  +-- start()                      +-- haymaker start              |
|  +-- cleanup()                    +-- haymaker cleanup            |
|  +-- get_logs()                   +-- haymaker logs               |
|                                                                   |
|  Workload Registry    State Storage    Credential Management      |
+------------------------------------------------------------------+
                              |
                   implements | WorkloadBase
                              v
+------------------------------------------------------------------+
|                    WORKLOAD PACKAGES                              |
|                                                                   |
|  haymaker-azure-workloads       haymaker-m365-workloads           |
|  +-- Azure infrastructure       +-- Knowledge workers             |
|  +-- Goal-seeking agents        +-- M365 operations               |
|  +-- Scenario execution         +-- Entra identity mgmt           |
+------------------------------------------------------------------+
```

The platform provides the **WorkloadBase** interface, a **registry** for discovering installed workloads, **state storage** for tracking deployments, and **credential management** via Azure Key Vault. Workload packages are separate repositories that implement the interface and can be installed via `haymaker workload install`.

## LLM Integration

Workloads can use the built-in multi-provider LLM abstraction layer for AI-powered content generation, adaptive agent behavior, and intelligent operations. See the [LLM Provider Configuration](llm-providers.md) guide for details.

```python
from agent_haymaker.llm import create_llm_client, LLMConfig, LLMMessage

config = LLMConfig.from_env()
client = create_llm_client(config)

messages = [LLMMessage(role="user", content="Write a professional email about Q4 results")]
response = client.create_message(messages, system="You are a business writer.")
```

Supported providers: Anthropic Claude, Azure OpenAI, and Azure AI Foundry.

## Workload Repositories

| Workload | Description | Repository |
|----------|-------------|------------|
| `azure-infrastructure` | Azure scenario execution with goal-seeking agents | [haymaker-azure-workloads](https://github.com/rysweet/haymaker-azure-workloads) |
| `m365-knowledge-worker` | M365 knowledge worker simulation | [haymaker-m365-workloads](https://github.com/rysweet/haymaker-m365-workloads) |

## Development

```bash
git clone https://github.com/rysweet/agent-haymaker
cd agent-haymaker
pip install -e ".[dev]"
pytest
```

## License

MIT
