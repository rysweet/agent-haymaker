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
import sys
from typing import Any

import click

from ..workloads import DeploymentConfig, WorkloadRegistry

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


# =============================================================================
# Deploy Command
# =============================================================================


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
    except Exception as e:
        click.echo(f"Error: Deployment failed: {e}")
        sys.exit(1)


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
            except Exception:
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
            except Exception:
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
                    async for line in wl.get_logs(deployment_id, follow=follow, lines=lines):
                        click.echo(line.rstrip())

                run_async(stream_logs())
                return
            except Exception:
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
            except Exception:
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
            except Exception:
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
            except Exception:
                continue

    click.echo(f"Error: Deployment '{deployment_id}' not found.")
    sys.exit(1)


# =============================================================================
# Workload Management Commands
# =============================================================================


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


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
