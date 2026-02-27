"""Deploy command for Agent Haymaker CLI.

Handles deployment of workloads with configuration parsing and validation.
"""

import sys
from typing import Any

import click

from ..workloads.base import DeploymentError
from ..workloads.models import DeploymentConfig
from .main import cli, get_registry, run_async


@cli.command()
@click.argument("workload_name")
@click.option("--duration", "-d", type=int, help="Duration in hours (default: indefinite)")
@click.option("--tag", "-t", multiple=True, help="Tags in key=value format")
@click.option("--config", "-c", multiple=True, help="Workload config in key=value format")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def deploy(
    workload_name: str,
    duration: int | None,
    tag: tuple[str, ...],
    config: tuple[str, ...],
    yes: bool,
) -> None:
    """Deploy a workload.

    Start a new deployment of the specified workload.

    \b
    Examples:
        haymaker deploy m365-knowledge-worker --config workers=25
        haymaker deploy azure-infrastructure --config scenario=linux-vm
    """
    registry = get_registry()
    workload = registry.get_workload(workload_name)

    if not workload:
        available = registry.list_workloads()
        click.echo(f"Error: Workload '{workload_name}' not found.")
        if available:
            click.echo(f"Available workloads: {', '.join(available)}")
        else:
            click.echo("No workloads installed. Use 'haymaker workload install' first.")
        sys.exit(1)

    # Parse tags
    tags = {}
    for t in tag:
        if "=" in t:
            k, v = t.split("=", 1)
            tags[k] = v

    # Parse workload config
    workload_config: dict[str, Any] = {}
    for c in config:
        if "=" in c:
            k, v = c.split("=", 1)
            # Try to parse as int/float/bool
            try:
                workload_config[k] = int(v)
            except ValueError:
                try:
                    workload_config[k] = float(v)
                except ValueError:
                    if v.lower() in ("true", "false"):
                        workload_config[k] = v.lower() == "true"
                    else:
                        workload_config[k] = v

    # Build config
    deploy_config = DeploymentConfig(
        workload_name=workload_name,
        duration_hours=duration,
        tags=tags,
        workload_config=workload_config,
    )

    # Validate
    errors = run_async(workload.validate_config(deploy_config))
    if errors:
        click.echo("Configuration errors:")
        for err in errors:
            click.echo(f"  - {err}")
        sys.exit(1)

    # Confirm
    if not yes:
        click.echo(f"Deploying workload: {workload_name}")
        if workload_config:
            click.echo("Configuration:")
            for k, v in workload_config.items():
                click.echo(f"  {k}: {v}")
        if not click.confirm("Proceed?"):
            click.echo("Aborted.")
            sys.exit(0)

    # Deploy
    try:
        deployment_id = run_async(workload.deploy(deploy_config))
        click.echo(f"Deployment started: {deployment_id}")
    except (DeploymentError, Exception) as e:
        click.echo(f"Error: Deployment failed: {e}")
        sys.exit(1)
