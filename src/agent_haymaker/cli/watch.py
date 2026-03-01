"""Watch command for Agent Haymaker CLI.

Provides real-time event streaming for deployments via the local event bus.
"""

import sys

import click

from ..events import (
    DEPLOYMENT_COMPLETED,
    DEPLOYMENT_FAILED,
    DEPLOYMENT_LOG,
    DEPLOYMENT_PHASE_CHANGED,
    DEPLOYMENT_STARTED,
    DEPLOYMENT_STOPPED,
    WORKLOAD_PROGRESS,
)
from .main import cli, get_registry, run_async


@cli.command()
@click.argument("deployment_id")
@click.option(
    "--wait-for",
    type=click.Choice(["completed", "failed", "stopped"]),
    help="Exit when deployment reaches this state",
)
@click.option("--timeout", type=int, default=0, help="Timeout in seconds (0 = no timeout)")
def watch(deployment_id: str, wait_for: str | None, timeout: int) -> None:
    """Watch deployment events in real-time.

    Subscribes to all events for a deployment and streams them
    to the terminal. Optionally waits for a specific state.

    \b
    Examples:
        haymaker watch dep-abc123
        haymaker watch dep-abc123 --wait-for completed
        haymaker watch dep-abc123 --wait-for completed --timeout 300
    """
    import asyncio

    async def _run() -> None:
        registry = get_registry()

        # Verify deployment exists by looking it up
        # Import the find helper from lifecycle
        from .lifecycle import find_deployment_async

        _wl, state = await find_deployment_async(registry, deployment_id)

        # Get the platform's event bus from CLI context
        platform = click.get_current_context().obj.get("platform")
        if platform is None or not hasattr(platform, "subscribe"):
            click.echo(
                "Error: No event-capable platform available. "
                "The watch command requires a platform with event bus support.",
                err=True,
            )
            sys.exit(1)

        done_event = asyncio.Event()
        target_state = wait_for

        def _format_event(event: dict) -> str:
            """Format an event for terminal display."""
            topic = event.get("topic", "unknown")
            ts = event.get("timestamp", "")
            # Shorten timestamp for display
            if ts and len(ts) > 19:
                ts = ts[:19]

            if topic == DEPLOYMENT_LOG:
                level = event.get("level", "INFO")
                line = event.get("line", "")
                return f"[{ts}] [{level}] {line}"
            elif topic == WORKLOAD_PROGRESS:
                phase = event.get("phase", "")
                message = event.get("message", "")
                percent = event.get("percent")
                pct_str = f" ({percent:.0f}%)" if percent is not None else ""
                return f"[{ts}] PROGRESS: {phase} - {message}{pct_str}"
            elif topic == DEPLOYMENT_PHASE_CHANGED:
                phase = event.get("phase", "")
                return f"[{ts}] PHASE: {phase}"
            elif topic == DEPLOYMENT_STARTED:
                return f"[{ts}] STARTED: {deployment_id}"
            elif topic in (DEPLOYMENT_COMPLETED, DEPLOYMENT_FAILED):
                status = "COMPLETED" if topic == DEPLOYMENT_COMPLETED else "FAILED"
                error = event.get("error", "")
                suffix = f" - {error}" if error else ""
                return f"[{ts}] {status}: {deployment_id}{suffix}"
            else:
                return f"[{ts}] {topic}: {event.get('data', event)}"

        async def _on_event(event: dict) -> None:
            """Handle incoming events."""
            # Filter to only this deployment
            if event.get("deployment_id") != deployment_id:
                return

            click.echo(_format_event(event))

            # Check if we should stop watching
            if target_state:
                topic = event.get("topic", "")
                state_to_topic = {
                    "completed": DEPLOYMENT_COMPLETED,
                    "failed": DEPLOYMENT_FAILED,
                    "stopped": DEPLOYMENT_STOPPED,
                }
                if topic == state_to_topic.get(target_state):
                    done_event.set()

        # Subscribe to all deployment-related topics
        topics_to_watch = [
            DEPLOYMENT_STARTED,
            DEPLOYMENT_COMPLETED,
            DEPLOYMENT_FAILED,
            DEPLOYMENT_STOPPED,
            DEPLOYMENT_PHASE_CHANGED,
            DEPLOYMENT_LOG,
            WORKLOAD_PROGRESS,
        ]

        subscription_ids: list[str] = []
        for topic in topics_to_watch:
            sub_id = await platform.subscribe(topic, _on_event)
            subscription_ids.append(sub_id)

        click.echo(f"Watching deployment {deployment_id}...")
        if target_state:
            click.echo(f"Will exit when state reaches: {target_state}")
        click.echo("Press Ctrl+C to stop.\n")

        try:
            if target_state:
                if timeout > 0:
                    try:
                        await asyncio.wait_for(done_event.wait(), timeout=timeout)
                        click.echo(f"\nDeployment reached state: {target_state}")
                    except TimeoutError:
                        msg = f"\nTimeout after {timeout}s waiting for {target_state}"
                        click.echo(msg, err=True)
                        sys.exit(1)
                else:
                    await done_event.wait()
                    click.echo(f"\nDeployment reached state: {target_state}")
            else:
                # Watch indefinitely until Ctrl+C
                await asyncio.Event().wait()  # blocks forever
        except KeyboardInterrupt:
            click.echo("\nStopped watching.")
        finally:
            # Unsubscribe from all topics
            for sub_id in subscription_ids:
                await platform.unsubscribe(sub_id)

    run_async(_run())
