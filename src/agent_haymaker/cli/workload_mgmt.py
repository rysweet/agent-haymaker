"""Workload management commands for Agent Haymaker CLI.

Provides commands for listing, installing, and inspecting workloads.
"""

import sys

import click

from .main import cli, get_registry


@cli.group()
def workload() -> None:
    """Manage workloads.

    \b
    Commands:
        haymaker workload list
        haymaker workload install <source>
        haymaker workload info <name>
    """
    pass


@workload.command("list")
def workload_list() -> None:
    """List installed workloads."""
    registry = get_registry()
    workloads = registry.list_workloads()

    if not workloads:
        click.echo("No workloads installed.")
        click.echo("Install a workload with: haymaker workload install <git-url>")
        return

    click.echo("Installed workloads:")
    for name in workloads:
        click.echo(f"  - {name}")


@workload.command("install")
@click.argument("source")
def workload_install(source: str) -> None:
    """Install a workload from git URL or local path.

    \b
    Examples:
        haymaker workload install https://github.com/org/haymaker-m365-workloads
        haymaker workload install ./my-workload
    """
    registry = get_registry()

    try:
        if source.startswith("https://") or source.startswith("git@"):
            click.echo(f"Installing from git: {source}")
            name = registry.install_from_git(source)
        else:
            click.echo(f"Installing from path: {source}")
            name = registry.install_from_path(source)

        click.echo(f"Workload '{name}' installed successfully.")
    except Exception as e:
        click.echo(f"Error: Failed to install workload: {e}")
        sys.exit(1)


@workload.command("info")
@click.argument("name")
def workload_info(name: str) -> None:
    """Show information about a workload."""
    registry = get_registry()
    wl = registry.get_workload(name)

    if not wl:
        click.echo(f"Error: Workload '{name}' not found.")
        sys.exit(1)

    click.echo(f"Workload: {wl.name}")
    click.echo(f"  Class: {wl.__class__.__name__}")
    click.echo(f"  Module: {wl.__class__.__module__}")
