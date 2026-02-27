"""Main CLI entry point for Agent Haymaker.

Provides universal lifecycle commands that work with any workload:
    haymaker deploy <workload> [options]
    haymaker status <deployment-id>
    haymaker list [--workload <name>]
    haymaker logs <deployment-id> [--follow]
    haymaker stop <deployment-id>
    haymaker start <deployment-id>
    haymaker cleanup <deployment-id>
    haymaker workload list
    haymaker workload install <source>
"""

import asyncio
from typing import Any

import click

from ..workloads import WorkloadRegistry

# Global registry instance
_registry: WorkloadRegistry | None = None


def get_registry() -> WorkloadRegistry:
    """Get or create the workload registry."""
    global _registry
    if _registry is None:
        _registry = WorkloadRegistry()
        _registry.discover_workloads()
    return _registry


def run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


@click.group()
@click.version_option(version="0.1.0", prog_name="agent-haymaker")
def cli() -> None:
    """Agent Haymaker - Universal workload orchestration platform.

    Deploy and manage workloads that generate telemetry for Azure tenants
    and M365 environments.

    \b
    Universal commands work with any installed workload:
        haymaker deploy <workload> [options]
        haymaker status <deployment-id>
        haymaker list
        haymaker logs <deployment-id>
        haymaker stop <deployment-id>
        haymaker cleanup <deployment-id>

    \b
    Manage workloads:
        haymaker workload list
        haymaker workload install <git-url>
    """
    pass


# Import command modules to register commands with the cli group.
# These imports must happen after cli is defined since the modules
# import cli from this module.
from . import deploy, lifecycle, workload_mgmt  # noqa: E402, F401


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
