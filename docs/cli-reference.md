---
layout: default
title: CLI Reference
---

# CLI Reference

Complete reference for the `haymaker` command-line interface.

[Back to Home](index.md)

## Global Options

```
haymaker --version    Show version and exit
haymaker --help       Show help and exit
```

---

## Lifecycle Commands

These commands manage the lifecycle of workload deployments.

### haymaker deploy

Start a new deployment of the specified workload.

```
haymaker deploy <workload_name> [OPTIONS]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `workload_name` | Yes | Name of the installed workload to deploy |

**Options:**

| Option | Short | Type | Description |
|--------|-------|------|-------------|
| `--duration` | `-d` | integer | Duration in hours (default: indefinite) |
| `--tag` | `-t` | key=value | Tags for the deployment (repeatable) |
| `--config` | `-c` | key=value | Workload-specific configuration (repeatable) |
| `--yes` | `-y` | flag | Skip confirmation prompt |

**Examples:**

```bash
haymaker deploy m365-knowledge-worker --config workers=25
haymaker deploy azure-infrastructure --config scenario=linux-vm
haymaker deploy my-workload -c workers=10 -c department=sales -d 24 -y
haymaker deploy my-workload --tag env=staging --tag team=platform
```

**Behavior:**

1. Looks up the workload in the registry
2. Parses `--config` values (auto-converts to int, float, or bool where possible)
3. Validates the configuration via `workload.validate_config()`
4. Prompts for confirmation (unless `--yes`)
5. Calls `workload.deploy()` and prints the deployment ID

---

### haymaker status

Get the current status of a deployment.

```
haymaker status <deployment_id> [OPTIONS]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `deployment_id` | Yes | The deployment identifier |

**Options:**

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--format` | `-f` | choice: text, json | text | Output format |

**Examples:**

```bash
haymaker status dep-abc123
haymaker status dep-abc123 --format json
```

**Output (text format):**

```
Deployment: dep-abc123
  Workload: m365-knowledge-worker
  Status:   running
  Phase:    executing
  Started:  2024-01-15T10:30:00Z
```

---

### haymaker list

List all deployments, optionally filtered.

```
haymaker list [OPTIONS]
```

**Options:**

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--workload` | `-w` | string | all | Filter by workload name |
| `--status` | `-s` | string | all | Filter by deployment status |
| `--limit` | `-l` | integer | 20 | Maximum number of results |
| `--format` | `-f` | choice: text, json | text | Output format |

**Examples:**

```bash
haymaker list
haymaker list --workload m365-knowledge-worker
haymaker list --status running
haymaker list --status running --limit 5
haymaker list --format json
```

**Output (text format):**

```
ID                   Workload                  Status       Phase
---------------------------------------------------------------------------
dep-abc123           m365-knowledge-worker     running      executing
dep-def456           azure-infrastructure      stopped      paused
```

---

### haymaker logs

View logs from a deployment.

```
haymaker logs <deployment_id> [OPTIONS]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `deployment_id` | Yes | The deployment identifier |

**Options:**

| Option | Short | Type | Default | Description |
|--------|-------|------|---------|-------------|
| `--follow` | `-f` | flag | false | Follow logs in real-time (stream continuously) |
| `--lines` | `-n` | integer | 100 | Number of historical lines to show |

**Examples:**

```bash
haymaker logs dep-abc123
haymaker logs dep-abc123 --follow
haymaker logs dep-abc123 -n 50
haymaker logs dep-abc123 -f -n 200
```

---

### haymaker stop

Stop a running deployment.

```
haymaker stop <deployment_id> [OPTIONS]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `deployment_id` | Yes | The deployment identifier |

**Options:**

| Option | Short | Type | Description |
|--------|-------|------|-------------|
| `--yes` | `-y` | flag | Skip confirmation prompt |

**Examples:**

```bash
haymaker stop dep-abc123
haymaker stop dep-abc123 --yes
```

**Behavior:**

- Checks that the deployment is currently running
- Prompts for confirmation (unless `--yes`)
- Calls `workload.stop()` and reports success or failure

---

### haymaker start

Resume a stopped deployment.

```
haymaker start <deployment_id>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `deployment_id` | Yes | The deployment identifier |

**Examples:**

```bash
haymaker start dep-abc123
```

**Behavior:**

- Checks whether the deployment is already running
- Calls `workload.start()` and reports success or failure

---

### haymaker cleanup

Delete all resources created by a deployment. This is destructive and cannot be undone.

```
haymaker cleanup <deployment_id> [OPTIONS]
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `deployment_id` | Yes | The deployment identifier |

**Options:**

| Option | Short | Type | Description |
|--------|-------|------|-------------|
| `--yes` | `-y` | flag | Skip confirmation prompt |
| `--dry-run` | | flag | Show what would be deleted without making changes |

**Examples:**

```bash
haymaker cleanup dep-abc123
haymaker cleanup dep-abc123 --dry-run
haymaker cleanup dep-abc123 --yes
```

**Output:**

```
Cleanup complete for dep-abc123
  Resources deleted: 10
```

**Dry-run output:**

```
Would clean up deployment: dep-abc123
  Workload: m365-knowledge-worker
  Status: stopped
(Dry run - no changes made)
```

---

## Workload Management Commands

These commands manage the set of installed workload packages.

### haymaker workload list

List all installed workloads.

```
haymaker workload list
```

**Output:**

```
Installed workloads:
  - azure-infrastructure
  - m365-knowledge-worker
```

---

### haymaker workload install

Install a workload from a git repository URL or a local file path.

```
haymaker workload install <source>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `source` | Yes | Git URL (https:// or git@) or local directory path |

**Examples:**

```bash
haymaker workload install https://github.com/org/haymaker-m365-workloads
haymaker workload install git@github.com:org/my-workload.git
haymaker workload install ./my-local-workload
```

**Behavior:**

- Detects whether the source is a git URL or local path
- Clones/copies the workload package
- Registers it in the workload registry
- Reports the installed workload name

---

### haymaker workload info

Show detailed information about an installed workload.

```
haymaker workload info <name>
```

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `name` | Yes | Name of the installed workload |

**Examples:**

```bash
haymaker workload info m365-knowledge-worker
```

**Output:**

```
Workload: m365-knowledge-worker
  Class: M365KnowledgeWorker
  Module: haymaker_m365_workloads.knowledge_worker
```

---

## Command Summary

| Command | Description |
|---------|-------------|
| `haymaker deploy <workload> [opts]` | Start a new deployment |
| `haymaker status <id> [--format]` | Get deployment status |
| `haymaker list [--workload] [--status]` | List deployments |
| `haymaker logs <id> [--follow] [-n]` | View deployment logs |
| `haymaker stop <id> [--yes]` | Stop a running deployment |
| `haymaker start <id>` | Resume a stopped deployment |
| `haymaker cleanup <id> [--yes] [--dry-run]` | Delete deployment resources |
| `haymaker workload list` | List installed workloads |
| `haymaker workload install <source>` | Install a workload |
| `haymaker workload info <name>` | Show workload details |
