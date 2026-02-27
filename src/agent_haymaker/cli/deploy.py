"""Deploy command for Agent Haymaker CLI.

Handles deployment of workloads with configuration parsing and validation.
Supports both CLI flags and YAML config files, with CLI taking precedence.
"""

import sys
from pathlib import Path
from typing import Any

import click
import yaml

from ..workloads.base import DeploymentError
from ..workloads.models import DeploymentConfig
from .main import cli, get_registry, run_async


def _load_config_file(config_file: str) -> dict[str, Any]:
    """Load and validate a YAML config file.

    Args:
        config_file: Path to the YAML config file

    Returns:
        Parsed config dictionary

    Raises:
        click.ClickException: If file not found or invalid YAML
    """
    path = Path(config_file)
    if not path.exists():
        raise click.ClickException(f"Config file not found: {config_file}")

    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise click.ClickException(f"Invalid YAML in config file: {e}") from None

    if not isinstance(data, dict):
        raise click.ClickException("Config file must contain a YAML mapping (dict)")

    return data


@cli.command()
@click.argument("workload_name")
@click.option("--duration", "-d", type=int, help="Duration in hours (default: indefinite)")
@click.option("--tag", "-t", multiple=True, help="Tags in key=value format")
@click.option("--config", "-c", multiple=True, help="Workload config in key=value format")
@click.option(
    "--config-file",
    type=click.Path(exists=False),
    help="YAML config file (CLI --config flags take precedence)",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def deploy(
    workload_name: str,
    duration: int | None,
    tag: tuple[str, ...],
    config: tuple[str, ...],
    config_file: str | None,
    yes: bool,
) -> None:
    """Deploy a workload.

    Start a new deployment of the specified workload.

    \b
    Examples:
        haymaker deploy m365-knowledge-worker --config workers=25
        haymaker deploy azure-infrastructure --config scenario=linux-vm
        haymaker deploy m365-knowledge-worker --config-file deploy.yaml
        haymaker deploy m365-knowledge-worker --config-file deploy.yaml --config workers=50
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

    # Load config file defaults if provided
    file_config: dict[str, Any] = {}
    file_duration: int | None = None
    if config_file:
        file_config = _load_config_file(config_file)

        # Extract top-level fields from file config (remove so they don't leak
        # into workload_config)
        file_config.pop("workload_name", None)
        file_duration_raw = file_config.pop("duration_hours", None)
        if file_duration_raw is not None:
            try:
                file_duration = int(file_duration_raw)
            except (ValueError, TypeError):
                raise click.ClickException(
                    f"Invalid duration_hours in config file: {file_duration_raw!r}"
                ) from None

    # Start with file config as base workload config
    workload_config: dict[str, Any] = dict(file_config)

    # Parse CLI workload config (overrides file config)
    for c in config:
        if "=" not in c:
            raise click.UsageError(f"Invalid --config format {c!r}. Expected key=value")
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

    # Parse tags
    tags = {}
    for t in tag:
        if "=" not in t:
            raise click.UsageError(f"Invalid --tag format {t!r}. Expected key=value")
        k, v = t.split("=", 1)
        tags[k] = v

    # CLI duration takes precedence over file duration
    effective_duration = duration if duration is not None else file_duration

    # Build config
    deploy_config = DeploymentConfig(
        workload_name=workload_name,
        duration_hours=effective_duration,
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
    except DeploymentError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: Unexpected failure: {e}", err=True)
        sys.exit(1)
