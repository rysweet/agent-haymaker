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
from importlib.metadata import version as pkg_version
from typing import Any

import click

from ..workloads import WorkloadRegistry


def get_registry() -> WorkloadRegistry:
    """Get the workload registry from Click context, or create one.

    Uses Click context when running inside the CLI. Falls back to
    creating a new registry for non-Click contexts (testing, programmatic use).
    """
    ctx = click.get_current_context(silent=True)
    if ctx and ctx.obj and "registry" in ctx.obj:
        return ctx.obj["registry"]
    # Fallback for non-Click contexts
    registry = WorkloadRegistry()
    registry.discover_workloads()
    return registry


def run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


@click.group()
@click.version_option(version=pkg_version("agent-haymaker"), prog_name="agent-haymaker")
@click.pass_context
def cli(ctx: click.Context) -> None:
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
    ctx.ensure_object(dict)
    registry = WorkloadRegistry()
    registry.discover_workloads()
    ctx.obj["registry"] = registry


# Import command modules to register commands with the cli group.
# These imports must happen after cli is defined since the modules
# import cli from this module.
from . import deploy, lifecycle, workload_mgmt  # noqa: E402, F401


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
