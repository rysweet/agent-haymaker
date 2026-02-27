"""Lifecycle commands for Agent Haymaker CLI.

Provides status, list, logs, stop, start, and cleanup commands
for managing deployment lifecycles across all workloads.
"""

import sys

import click

from ..workloads.base import DeploymentNotFoundError
from .main import cli, get_registry, run_async

# =============================================================================
# Status Command
# =============================================================================


@cli.command()
@click.argument("deployment_id")
@click.option(
    "--format", "-f", "output_format", type=click.Choice(["text", "json"]), default="text"
)
def status(deployment_id: str, output_format: str) -> None:
    """Get deployment status.

    \b
    Examples:
        haymaker status dep-abc123
        haymaker status dep-abc123 --format json
    """
    registry = get_registry()

    # Try each workload to find the deployment
    for name in registry.list_workloads():
        workload = registry.get_workload(name)
        if workload:
            try:
                state = run_async(workload.get_status(deployment_id))
                if output_format == "json":
                    click.echo(state.model_dump_json(indent=2))
                else:
                    click.echo(f"Deployment: {state.deployment_id}")
                    click.echo(f"  Workload: {state.workload_name}")
                    click.echo(f"  Status:   {state.status}")
                    click.echo(f"  Phase:    {state.phase}")
                    if state.started_at:
                        click.echo(f"  Started:  {state.started_at}")
                    if state.error:
                        click.echo(f"  Error:    {state.error}")
                return
            except DeploymentNotFoundError:
                continue

    click.echo(f"Error: Deployment '{deployment_id}' not found.")
    sys.exit(1)


# =============================================================================
# List Command
# =============================================================================


@cli.command("list")
@click.option("--workload", "-w", help="Filter by workload name")
@click.option("--status", "-s", help="Filter by status")
@click.option("--limit", "-l", type=int, default=20, help="Maximum results")
@click.option(
    "--format", "-f", "output_format", type=click.Choice(["text", "json"]), default="text"
)
def list_deployments(
    workload: str | None, status: str | None, limit: int, output_format: str
) -> None:
    """List all deployments.

    \b
    Examples:
        haymaker list
        haymaker list --workload m365-knowledge-worker
        haymaker list --status running
    """
    registry = get_registry()
    all_deployments = []

    workloads_to_check = [workload] if workload else registry.list_workloads()

    for name in workloads_to_check:
        wl = registry.get_workload(name)
        if wl:
            try:
                deployments = run_async(wl.list_deployments())
                all_deployments.extend(deployments)
            except DeploymentNotFoundError:
                continue

    # Filter by status
    if status:
        all_deployments = [d for d in all_deployments if d.status == status]

    # Limit
    all_deployments = all_deployments[:limit]

    if not all_deployments:
        click.echo("No deployments found.")
        return

    if output_format == "json":
        import json

        click.echo(json.dumps([d.model_dump() for d in all_deployments], indent=2, default=str))
    else:
        click.echo(f"{'ID':<20} {'Workload':<25} {'Status':<12} {'Phase':<15}")
        click.echo("-" * 75)
        for d in all_deployments:
            click.echo(f"{d.deployment_id:<20} {d.workload_name:<25} {d.status:<12} {d.phase:<15}")


# =============================================================================
# Logs Command
# =============================================================================


@cli.command()
@click.argument("deployment_id")
@click.option("--follow", "-f", is_flag=True, help="Follow logs in real-time")
@click.option("--lines", "-n", type=int, default=100, help="Number of lines to show")
def logs(deployment_id: str, follow: bool, lines: int) -> None:
    """View deployment logs.

    \b
    Examples:
        haymaker logs dep-abc123
        haymaker logs dep-abc123 --follow
        haymaker logs dep-abc123 -n 50
    """
    registry = get_registry()

    # Find the workload for this deployment
    for name in registry.list_workloads():
        workload = registry.get_workload(name)
        if workload:
            try:
                # Check if deployment exists
                run_async(workload.get_status(deployment_id))

                # Stream logs - capture workload in closure
                async def stream_logs(wl=workload) -> None:
                    try:
                        async for line in wl.get_logs(deployment_id, follow=follow, lines=lines):
                            click.echo(line.rstrip())
                    except Exception as e:
                        click.echo(f"Error streaming logs: {e}", err=True)

                run_async(stream_logs())
                return
            except DeploymentNotFoundError:
                continue

    click.echo(f"Error: Deployment '{deployment_id}' not found.")
    sys.exit(1)


# =============================================================================
# Stop Command
# =============================================================================


@cli.command()
@click.argument("deployment_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def stop(deployment_id: str, yes: bool) -> None:
    """Stop a running deployment.

    \b
    Examples:
        haymaker stop dep-abc123
        haymaker stop dep-abc123 --yes
    """
    registry = get_registry()

    for name in registry.list_workloads():
        workload = registry.get_workload(name)
        if workload:
            try:
                state = run_async(workload.get_status(deployment_id))

                if state.status != "running":
                    click.echo(f"Deployment is not running (status: {state.status})")
                    sys.exit(1)

                if not yes and not click.confirm(f"Stop deployment {deployment_id}?"):
                    click.echo("Aborted.")
                    sys.exit(0)

                success = run_async(workload.stop(deployment_id))
                if success:
                    click.echo(f"Deployment {deployment_id} stopped.")
                else:
                    click.echo("Failed to stop deployment.")
                    sys.exit(1)
                return
            except DeploymentNotFoundError:
                continue

    click.echo(f"Error: Deployment '{deployment_id}' not found.")
    sys.exit(1)


# =============================================================================
# Start Command
# =============================================================================


@cli.command()
@click.argument("deployment_id")
def start(deployment_id: str) -> None:
    """Start/resume a stopped deployment.

    \b
    Examples:
        haymaker start dep-abc123
    """
    registry = get_registry()

    for name in registry.list_workloads():
        workload = registry.get_workload(name)
        if workload:
            try:
                state = run_async(workload.get_status(deployment_id))

                if state.status == "running":
                    click.echo("Deployment is already running.")
                    return

                success = run_async(workload.start(deployment_id))
                if success:
                    click.echo(f"Deployment {deployment_id} started.")
                else:
                    click.echo("Failed to start deployment.")
                    sys.exit(1)
                return
            except DeploymentNotFoundError:
                continue

    click.echo(f"Error: Deployment '{deployment_id}' not found.")
    sys.exit(1)


# =============================================================================
# Cleanup Command
# =============================================================================


@cli.command()
@click.argument("deployment_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
def cleanup(deployment_id: str, yes: bool, dry_run: bool) -> None:
    """Clean up deployment resources.

    Removes all resources created by the deployment. This is destructive
    and cannot be undone.

    \b
    Examples:
        haymaker cleanup dep-abc123
        haymaker cleanup dep-abc123 --dry-run
    """
    registry = get_registry()

    for name in registry.list_workloads():
        workload = registry.get_workload(name)
        if workload:
            try:
                state = run_async(workload.get_status(deployment_id))

                if dry_run:
                    click.echo(f"Would clean up deployment: {deployment_id}")
                    click.echo(f"  Workload: {state.workload_name}")
                    click.echo(f"  Status: {state.status}")
                    click.echo("(Dry run - no changes made)")
                    return

                if not yes:
                    click.echo(f"This will delete all resources for deployment: {deployment_id}")
                    if not click.confirm("Are you sure?"):
                        click.echo("Aborted.")
                        sys.exit(0)

                report = run_async(workload.cleanup(deployment_id))
                click.echo(f"Cleanup complete for {deployment_id}")
                click.echo(f"  Resources deleted: {report.resources_deleted}")
                if report.errors:
                    click.echo("  Errors:")
                    for err in report.errors:
                        click.echo(f"    - {err}")
                return
            except DeploymentNotFoundError:
                continue

    click.echo(f"Error: Deployment '{deployment_id}' not found.")
    sys.exit(1)
