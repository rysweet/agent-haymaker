"""Lifecycle commands for Agent Haymaker CLI.

Provides status, list, logs, stop, start, and cleanup commands
for managing deployment lifecycles across all workloads.
"""

import sys

import click

from ..workloads import DeploymentStatus
from ..workloads.base import DeploymentNotFoundError
from ..workloads.models import DeploymentState
from .lookup import find_deployment_async
from .main import cli, get_registry, run_async


@cli.command()
@click.argument("deployment_id")
@click.option(
    "--format", "-f", "output_format", type=click.Choice(["text", "json"]), default="text"
)
@click.option("--follow", is_flag=True, help="Follow status changes in real-time")
def status(deployment_id: str, output_format: str, follow: bool) -> None:
    """Get deployment status.

    \b
    Examples:
        haymaker status dep-abc123
        haymaker status dep-abc123 --format json
        haymaker status dep-abc123 --follow
    """

    async def _run() -> None:
        registry = get_registry()
        _workload, state = await find_deployment_async(registry, deployment_id)

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

        if follow:
            import asyncio

            from ..events import DEPLOYMENT_COMPLETED, DEPLOYMENT_FAILED, DEPLOYMENT_PHASE_CHANGED

            platform = click.get_current_context().obj.get("platform")
            if not platform or not hasattr(platform, "subscribe"):
                click.echo("\nNote: Platform does not support event-based following.", err=True)
                return

            done = asyncio.Event()

            async def _on_status_change(event: dict) -> None:
                if event.get("deployment_id") != deployment_id:
                    return
                topic = event.get("topic", "")
                if topic == DEPLOYMENT_PHASE_CHANGED:
                    click.echo(f"  Phase:    {event.get('phase', 'unknown')}")
                elif topic in (DEPLOYMENT_COMPLETED, DEPLOYMENT_FAILED):
                    status_str = "completed" if topic == DEPLOYMENT_COMPLETED else "failed"
                    click.echo(f"  Status:   {status_str}")
                    done.set()

            sub_ids = []
            for t in [DEPLOYMENT_PHASE_CHANGED, DEPLOYMENT_COMPLETED, DEPLOYMENT_FAILED]:
                sub_ids.append(await platform.subscribe(t, _on_status_change))

            click.echo("\nFollowing status changes (Ctrl+C to stop)...")
            try:
                await done.wait()
            except KeyboardInterrupt:
                click.echo("\nStopped following.")
            finally:
                for sid in sub_ids:
                    await platform.unsubscribe(sid)

    run_async(_run())


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

    async def _run() -> None:
        registry = get_registry()
        all_deployments: list[DeploymentState] = []

        workloads_to_check = [workload] if workload else registry.list_workloads()

        for name in workloads_to_check:
            wl = registry.get_workload(name)
            if wl:
                try:
                    deployments = await wl.list_deployments()
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
                click.echo(
                    f"{d.deployment_id:<20} {d.workload_name:<25} {d.status:<12} {d.phase:<15}"
                )

    run_async(_run())


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

    async def _run() -> None:
        registry = get_registry()
        wl, _state = await find_deployment_async(registry, deployment_id)
        try:
            async for line in wl.get_logs(deployment_id, follow=follow, lines=lines):
                click.echo(line.rstrip())
        except Exception as e:
            click.echo(f"Error streaming logs: {e}", err=True)
            sys.exit(1)

    run_async(_run())


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

    async def _run() -> None:
        registry = get_registry()
        wl, state = await find_deployment_async(registry, deployment_id)

        if state.status != DeploymentStatus.RUNNING:
            click.echo(f"Deployment is not running (status: {state.status})")
            sys.exit(1)

        if not yes and not click.confirm(f"Stop deployment {deployment_id}?"):
            click.echo("Aborted.")
            sys.exit(0)

        success = await wl.stop(deployment_id)
        if success:
            click.echo(f"Deployment {deployment_id} stopped.")
        else:
            click.echo("Failed to stop deployment.")
            sys.exit(1)

    run_async(_run())


@cli.command()
@click.argument("deployment_id")
def start(deployment_id: str) -> None:
    """Start/resume a stopped deployment.

    \b
    Examples:
        haymaker start dep-abc123
    """

    async def _run() -> None:
        registry = get_registry()
        wl, state = await find_deployment_async(registry, deployment_id)

        if state.status == DeploymentStatus.RUNNING:
            click.echo("Deployment is already running.")
            return

        try:
            success = await wl.start(deployment_id)
        except NotImplementedError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        if success:
            click.echo(f"Deployment {deployment_id} started.")
        else:
            click.echo("Failed to start deployment.")
            sys.exit(1)

    run_async(_run())


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

    async def _run() -> None:
        registry = get_registry()
        wl, state = await find_deployment_async(registry, deployment_id)

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

        report = await wl.cleanup(deployment_id)
        click.echo(f"Cleanup complete for {deployment_id}")
        click.echo(f"  Resources deleted: {report.resources_deleted}")
        if report.errors:
            click.echo("  Errors:")
            for err in report.errors:
                click.echo(f"    - {err}")

    run_async(_run())
