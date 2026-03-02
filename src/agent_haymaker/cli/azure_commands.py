"""Azure deployment commands for Agent Haymaker CLI.

Provides commands for deploying workloads to Azure Container Apps,
validating Azure environment, and running the full orchestration workflow.
"""

from __future__ import annotations

import sys
from typing import Any

import click

from .main import cli, run_async


def _load_platform(config_file: str | None) -> tuple[Any, Any]:
    """Load Azure config and create platform instance, or exit on error."""
    from ..azure import AzureConfig, AzurePlatform

    try:
        config = AzureConfig.from_yaml(config_file) if config_file else AzureConfig.load()
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(1)
    return config, AzurePlatform(config=config)


def _print_orchestration_result(result: Any) -> None:
    """Print orchestration result summary to stdout."""
    click.echo(f"\n{'=' * 60}")
    click.echo(f"Orchestration {result.status.upper()}")
    click.echo(f"{'=' * 60}")
    click.echo(f"  Run ID: {result.run_id}")
    if result.duration_seconds:
        click.echo(f"  Duration: {result.duration_seconds:.0f}s")
    for phase in result.phases:
        icon = "OK" if phase.status == "passed" else "FAIL"
        click.echo(f"  [{icon}] {phase.phase}")
        if phase.error:
            click.echo(f"         Error: {phase.error}")
    if result.summary:
        click.echo(f"\n  Deployed: {result.summary.get('workloads_deployed', 0)}")
        click.echo(f"  Failed: {result.summary.get('workloads_failed', 0)}")


@cli.group()
def azure() -> None:
    """Azure deployment commands (validate, deploy, run, status, cleanup)."""
    pass


@azure.command()
@click.option("--config", "-c", "config_file", help="Path to azure.yaml config file")
def validate(config_file: str | None) -> None:
    """Validate Azure environment (CLI auth, subscription, ACR, Key Vault)."""

    async def _run() -> None:
        _, platform = _load_platform(config_file)
        click.echo("Validating Azure environment...\n")

        results = await platform.validate_environment()
        all_passed = True
        for name, check in results.items():
            if name == "overall":
                continue
            status = check.get("status", "unknown")
            message = check.get("message", "")
            icon = "OK" if status == "passed" else ("!!" if status == "create_needed" else "FAIL")
            click.echo(f"  [{icon}] {name}: {message}")
            if status == "failed":
                all_passed = False

        click.echo()
        if all_passed:
            click.echo("All checks passed. Ready for deployment.")
        else:
            click.echo("Some checks failed. Fix the issues above before deploying.", err=True)
            sys.exit(1)

    run_async(_run())


@azure.command("deploy")
@click.argument("workload_name")
@click.option("--image", "-i", help="Container image to deploy")
@click.option("--config", "-c", "config_file", help="Path to azure.yaml config file")
@click.option("--env", "-e", multiple=True, help="Environment variable (KEY=VALUE)")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def azure_deploy(
    workload_name: str,
    image: str | None,
    config_file: str | None,
    env: tuple[str, ...],
    yes: bool,
) -> None:
    """Deploy a workload to Azure Container Apps.

    \b
    Examples:
        haymaker azure deploy azure-infrastructure --image myregistry.azurecr.io/agent:latest
        haymaker azure deploy m365-knowledge-worker -e WORKERS=25 -e DEPARTMENT=engineering
    """

    async def _run() -> None:
        config, platform = _load_platform(config_file)

        # Parse env vars
        env_vars = {}
        for e_str in env:
            if "=" not in e_str:
                click.echo(f"Invalid env var format: {e_str} (expected KEY=VALUE)", err=True)
                sys.exit(1)
            key, val = e_str.split("=", 1)
            env_vars[key] = val

        if not yes:
            click.echo(f"Deploy {workload_name} to Azure?")
            click.echo(f"  Resource Group: {config.resource_group}")
            click.echo(f"  Location: {config.location}")
            if image:
                click.echo(f"  Image: {image}")
            if env_vars:
                click.echo(f"  Env vars: {', '.join(env_vars.keys())}")
            if not click.confirm("\nProceed?"):
                click.echo("Aborted.")
                sys.exit(0)

        click.echo(f"Deploying {workload_name} to Azure...")

        # Validate environment first
        checks = await platform.validate_environment()
        if checks.get("overall", {}).get("status") != "passed":
            click.echo(
                "Azure validation failed. Run 'haymaker azure validate'.",
                err=True,
            )
            sys.exit(1)

        from ..azure.provisioning import provision_workload

        click.echo("  Provisioning workload...")
        result = await provision_workload(
            platform=platform,
            workload_name=workload_name,
            image=image,
            env_vars=env_vars,
        )

        dep_id = result["deployment_id"]
        click.echo(f"\nDeployment started: {dep_id}")
        click.echo(f"  App name: {result.get('app_name', 'N/A')}")
        click.echo(f"  Status: {result.get('status', 'N/A')}")
        click.echo(f"\nMonitor with: haymaker azure status {result.get('app_name', dep_id)}")

    run_async(_run())


@azure.command("run")
@click.option("--config", "-c", "config_file", help="Path to azure.yaml config file")
@click.option("--workload", "-w", multiple=True, help="Workload to deploy (can specify multiple)")
@click.option("--image", "-i", help="Default container image for all workloads")
@click.option("--duration", type=int, default=8, help="Execution duration in hours (default: 8)")
@click.option("--interval", type=int, default=15, help="Monitoring interval in min")
@click.option("--skip-validation", is_flag=True, help="Skip environment validation")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def azure_run(
    config_file: str | None,
    workload: tuple[str, ...],
    image: str | None,
    duration: int,
    interval: int,
    skip_validation: bool,
    yes: bool,
) -> None:
    """Run full orchestration workflow (7-phase pipeline).

    Executes the complete deployment pipeline: validate -> provision ->
    monitor -> cleanup -> report.

    \b
    Examples:
        haymaker azure run -w azure-infrastructure -i myregistry.azurecr.io/agent:latest
        haymaker azure run -w azure-infrastructure --duration 4 --skip-validation
    """

    async def _run() -> None:
        from ..orchestrator.workflow import run_orchestration

        if not workload:
            click.echo("Error: At least one --workload is required.", err=True)
            sys.exit(1)

        config, platform = _load_platform(config_file)

        workloads = [{"name": w, "image": image} for w in workload]

        if not yes:
            click.echo("Azure Orchestration Run")
            click.echo(f"  Workloads: {', '.join(workload)}")
            click.echo(f"  Duration: {duration}h")
            click.echo(f"  Monitoring: every {interval}min")
            click.echo(f"  Resource Group: {config.resource_group}")
            if not click.confirm("\nProceed?"):
                click.echo("Aborted.")
                sys.exit(0)

        click.echo("Starting orchestration workflow...\n")

        result = await run_orchestration(
            platform=platform,
            workloads=workloads,
            duration_hours=duration,
            monitoring_interval_minutes=interval,
            skip_validation=skip_validation,
        )

        _print_orchestration_result(result)

    run_async(_run())


@azure.command("status")
@click.argument("app_name")
@click.option("--config", "-c", "config_file", help="Path to azure.yaml config file")
def azure_status(app_name: str, config_file: str | None) -> None:
    """Check status of an Azure Container App deployment.

    \b
    Examples:
        haymaker azure status my-workload-abc12345
    """

    async def _run() -> None:
        _, platform = _load_platform(config_file)
        status = await platform.get_container_app_status(app_name)

        if status.get("status") == "not_found":
            click.echo(f"Container app '{app_name}' not found.")
            sys.exit(1)

        click.echo(f"Container App: {app_name}")
        click.echo(f"  Provisioning: {status.get('status', 'Unknown')}")
        click.echo(f"  Running: {status.get('running_status', 'Unknown')}")

    run_async(_run())


@azure.command("cleanup")
@click.option("--config", "-c", "config_file", help="Path to azure.yaml config file")
@click.option("--deployment-id", "-d", help="Clean up specific deployment")
@click.option("--all", "clean_all", is_flag=True, help="Clean up all managed resources")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def azure_cleanup(
    config_file: str | None,
    deployment_id: str | None,
    clean_all: bool,
    yes: bool,
) -> None:
    """Clean up Azure resources.

    \b
    Examples:
        haymaker azure cleanup --deployment-id my-workload-abc12345
        haymaker azure cleanup --all
    """

    async def _run() -> None:
        _, platform = _load_platform(config_file)
        resources = await platform.list_managed_resources(deployment_id=deployment_id)
        if not resources:
            click.echo("No managed resources found.")
            return

        click.echo(f"Found {len(resources)} managed resources:")
        for r in resources[:10]:
            click.echo(f"  - {r.get('name', 'unknown')} ({r.get('type', 'unknown')})")
        if len(resources) > 10:
            click.echo(f"  ... and {len(resources) - 10} more")

        if not yes and not click.confirm("\nDelete these resources?"):
            click.echo("Aborted.")
            sys.exit(0)

        from ..azure.az_cli import run_az

        deleted = 0
        for r in resources:
            rid = r.get("id", "")
            rc, _, _ = run_az(["resource", "delete", "--ids", rid])
            if rc == 0:
                deleted += 1
                click.echo(f"  Deleted: {r.get('name', rid)}")

        click.echo(f"\nDeleted {deleted}/{len(resources)} resources.")

    run_async(_run())
