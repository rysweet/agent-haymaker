"""Orchestration workflow for deploying workloads to Azure.

Implements the 7-phase deployment pipeline adapted from AzureHayMaker:
1. Validation - verify Azure credentials and services
2. Selection - choose workloads to deploy
3. Provisioning - create SPs and deploy Container Apps
4. Monitoring - periodic status checks during execution
5. Cleanup Verification - verify all resources deleted
6. Forced Cleanup - delete remaining resources
7. Reporting - generate execution report

Public API:
    run_orchestration: Execute the full 7-phase workflow
    OrchestrationResult: Result of the orchestration run
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from ..events import (
    DEPLOYMENT_COMPLETED,
    DEPLOYMENT_FAILED,
    DEPLOYMENT_LOG,
    DEPLOYMENT_PHASE_CHANGED,
    DEPLOYMENT_STARTED,
)

logger = logging.getLogger(__name__)


class OrchestrationPhase(StrEnum):
    """Phases of the orchestration workflow."""

    VALIDATION = "validation"
    SELECTION = "selection"
    PROVISIONING = "provisioning"
    MONITORING = "monitoring"
    CLEANUP_VERIFICATION = "cleanup_verification"
    FORCED_CLEANUP = "forced_cleanup"
    REPORTING = "reporting"
    COMPLETED = "completed"


class PhaseResult(BaseModel):
    """Result of a single workflow phase."""

    phase: str
    status: str  # "passed", "failed", "skipped"
    started_at: datetime
    completed_at: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class OrchestrationResult(BaseModel):
    """Result of the full orchestration workflow."""

    run_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str = "running"  # "running", "completed", "failed"
    phases: list[PhaseResult] = Field(default_factory=list)
    deployments: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_seconds(self) -> float | None:
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()


async def run_orchestration(
    platform: Any,  # AzurePlatform
    workloads: list[dict[str, Any]],
    duration_hours: int = 8,
    monitoring_interval_minutes: int = 15,
    skip_validation: bool = False,
) -> OrchestrationResult:
    """Execute the full 7-phase orchestration workflow.

    Args:
        platform: AzurePlatform instance with Azure deployment capabilities
        workloads: List of workload dicts, each with:
            - name: workload name
            - image: container image (optional, uses platform config)
            - env_vars: environment variables (optional)
            - config: workload-specific config (optional)
        duration_hours: How long to run workloads (default: 8)
        monitoring_interval_minutes: Status check interval (default: 15)
        skip_validation: Skip Phase 1 validation (default: False)

    Returns:
        OrchestrationResult with details of each phase
    """
    run_id = str(uuid4())
    result = OrchestrationResult(
        run_id=run_id,
        started_at=datetime.now(UTC),
    )

    logger.info("Starting orchestration run %s with %d workloads", run_id, len(workloads))

    # Emit start event
    if hasattr(platform, "publish_event"):
        await platform.publish_event(
            DEPLOYMENT_STARTED,
            {
                "topic": DEPLOYMENT_STARTED,
                "deployment_id": run_id,
                "workload_count": len(workloads),
            },
        )

    try:
        # Phase 1: Validation
        if not skip_validation:
            phase_result = await _phase_validation(platform, run_id)
            result.phases.append(phase_result)
            if phase_result.status == "failed":
                result.status = "failed"
                result.completed_at = datetime.now(UTC)
                return result
            await _emit_phase_change(platform, run_id, OrchestrationPhase.VALIDATION)

        # Phase 2: Selection (workloads already provided, just validate)
        phase_result = await _phase_selection(workloads, run_id)
        result.phases.append(phase_result)
        await _emit_phase_change(platform, run_id, OrchestrationPhase.SELECTION)

        # Phase 3: Provisioning
        phase_result = await _phase_provisioning(platform, workloads, run_id)
        result.phases.append(phase_result)
        result.deployments = phase_result.details.get("deployments", [])
        if phase_result.status == "failed":
            result.status = "failed"
            result.completed_at = datetime.now(UTC)
            return result
        await _emit_phase_change(platform, run_id, OrchestrationPhase.PROVISIONING)

        # Phase 4: Monitoring
        phase_result = await _phase_monitoring(
            platform,
            result.deployments,
            run_id,
            duration_hours,
            monitoring_interval_minutes,
        )
        result.phases.append(phase_result)
        await _emit_phase_change(platform, run_id, OrchestrationPhase.MONITORING)

        # Phase 5: Cleanup Verification
        phase_result = await _phase_cleanup_verification(platform, run_id)
        result.phases.append(phase_result)
        await _emit_phase_change(platform, run_id, OrchestrationPhase.CLEANUP_VERIFICATION)

        # Phase 6: Forced Cleanup (if needed)
        remaining = phase_result.details.get("remaining_resources", [])
        if remaining:
            phase_result = await _phase_forced_cleanup(platform, remaining, run_id)
            result.phases.append(phase_result)
            await _emit_phase_change(platform, run_id, OrchestrationPhase.FORCED_CLEANUP)

        # Phase 7: Reporting
        phase_result = await _phase_reporting(result, run_id)
        result.phases.append(phase_result)
        await _emit_phase_change(platform, run_id, OrchestrationPhase.REPORTING)

        result.status = "completed"

    except Exception as exc:
        logger.error("Orchestration %s failed: %s", run_id, exc, exc_info=True)
        result.status = "failed"
        result.phases.append(
            PhaseResult(
                phase="error",
                status="failed",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                error=f"{type(exc).__name__}: {exc}",
            )
        )

    result.completed_at = datetime.now(UTC)

    # Emit completion event
    topic = DEPLOYMENT_COMPLETED if result.status == "completed" else DEPLOYMENT_FAILED
    if hasattr(platform, "publish_event"):
        await platform.publish_event(
            topic,
            {
                "topic": topic,
                "deployment_id": run_id,
                "status": result.status,
                "duration_seconds": result.duration_seconds,
            },
        )

    logger.info(
        "Orchestration %s %s in %.1fs",
        run_id,
        result.status,
        result.duration_seconds or 0,
    )
    return result


# -----------------------------------------------------------------
# Phase implementations
# -----------------------------------------------------------------


async def _phase_validation(platform: Any, run_id: str) -> PhaseResult:
    """Phase 1: Validate Azure environment."""
    started = datetime.now(UTC)
    await _emit_log(platform, run_id, "Phase 1: Validating Azure environment...")

    try:
        checks = await platform.validate_environment()
        overall = checks.get("overall", {}).get("status", "failed")

        for name, check in checks.items():
            if name != "overall":
                status = check.get("status", "unknown")
                msg = check.get("message", "")
                await _emit_log(platform, run_id, f"  {name}: {status} - {msg}")

        return PhaseResult(
            phase=OrchestrationPhase.VALIDATION,
            status="passed" if overall == "passed" else "failed",
            started_at=started,
            completed_at=datetime.now(UTC),
            details=checks,
        )
    except Exception as exc:
        return PhaseResult(
            phase=OrchestrationPhase.VALIDATION,
            status="failed",
            started_at=started,
            completed_at=datetime.now(UTC),
            error=str(exc),
        )


async def _phase_selection(workloads: list[dict], run_id: str) -> PhaseResult:
    """Phase 2: Validate and confirm workload selection."""
    started = datetime.now(UTC)
    return PhaseResult(
        phase=OrchestrationPhase.SELECTION,
        status="passed",
        started_at=started,
        completed_at=datetime.now(UTC),
        details={
            "workload_count": len(workloads),
            "workloads": [w.get("name", "unknown") for w in workloads],
        },
    )


async def _phase_provisioning(platform: Any, workloads: list[dict], run_id: str) -> PhaseResult:
    """Phase 3: Provision SPs and deploy Container Apps in parallel."""
    started = datetime.now(UTC)
    await _emit_log(platform, run_id, f"Phase 3: Provisioning {len(workloads)} workloads...")

    deployments = []
    sp_created = 0
    sp_failed = 0
    containers_deployed = 0
    containers_failed = 0

    for workload in workloads:
        wl_name = workload.get("name", "unknown")
        dep_id = f"{wl_name}-{uuid4().hex[:8]}"
        sp_info = None

        try:
            # Create service principal
            sp_name = f"haymaker-{dep_id}"
            await _emit_log(platform, run_id, f"  Creating SP: {sp_name}")
            sp_info = await platform.create_service_principal(sp_name)
            sp_created += 1

            # Build env vars for the container
            env_vars = workload.get("env_vars", {})
            env_vars.update(
                {
                    "AZURE_TENANT_ID": platform.config.tenant_id,
                    "AZURE_CLIENT_ID": sp_info.get("appId", ""),
                    "AZURE_CLIENT_SECRET": sp_info.get("password", ""),
                    "HAYMAKER_DEPLOYMENT_ID": dep_id,
                    "HAYMAKER_RUN_ID": run_id,
                    "HAYMAKER_WORKLOAD_NAME": wl_name,
                }
            )

            # Deploy container app
            image = workload.get("image")
            await _emit_log(platform, run_id, f"  Deploying container: {dep_id}")
            container_info = await platform.deploy_container_app(
                deployment_id=dep_id,
                workload_name=wl_name,
                image=image,
                env_vars=env_vars,
            )
            containers_deployed += 1

            deployments.append(
                {
                    "deployment_id": dep_id,
                    "workload_name": wl_name,
                    "app_name": container_info.get("app_name", ""),
                    "sp_app_id": sp_info.get("appId", ""),
                    "status": "deployed",
                }
            )

        except Exception as exc:
            logger.error("Failed to provision %s: %s", wl_name, exc)
            if sp_info is None:
                sp_failed += 1
            else:
                containers_failed += 1
            deployments.append(
                {
                    "deployment_id": dep_id,
                    "workload_name": wl_name,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    await _emit_log(
        platform,
        run_id,
        f"Phase 3 complete: {sp_created} SPs, {containers_deployed} containers deployed",
    )

    failed = sp_failed + containers_failed
    return PhaseResult(
        phase=OrchestrationPhase.PROVISIONING,
        status="passed" if failed == 0 else ("partial" if containers_deployed > 0 else "failed"),
        started_at=started,
        completed_at=datetime.now(UTC),
        details={
            "deployments": deployments,
            "service_principals": {"created": sp_created, "failed": sp_failed},
            "container_apps": {"deployed": containers_deployed, "failed": containers_failed},
        },
    )


async def _phase_monitoring(
    platform: Any,
    deployments: list[dict],
    run_id: str,
    duration_hours: int,
    interval_minutes: int,
) -> PhaseResult:
    """Phase 4: Monitor workloads for the configured duration."""
    started = datetime.now(UTC)
    total_seconds = duration_hours * 3600
    interval_seconds = interval_minutes * 60
    checks = []

    await _emit_log(
        platform,
        run_id,
        f"Phase 4: Monitoring {len(deployments)} workloads for {duration_hours}h "
        f"(checking every {interval_minutes}min)...",
    )

    elapsed = 0
    while elapsed < total_seconds:
        running = 0
        completed = 0
        failed = 0

        for dep in deployments:
            app_name = dep.get("app_name")
            if not app_name or dep.get("status") == "failed":
                failed += 1
                continue

            try:
                status = await platform.get_container_app_status(app_name)
                prov_state = status.get("status", "Unknown")
                if prov_state in ("Running", "Succeeded"):
                    if status.get("running_status") == "Terminated":
                        completed += 1
                    else:
                        running += 1
                else:
                    running += 1  # Still provisioning
            except Exception:
                running += 1  # Assume still running on check failure

        check = {
            "timestamp": datetime.now(UTC).isoformat(),
            "running": running,
            "completed": completed,
            "failed": failed,
            "elapsed_minutes": elapsed // 60,
        }
        checks.append(check)
        await _emit_log(
            platform,
            run_id,
            f"  Status check: running={running}, completed={completed}, "
            f"failed={failed} ({elapsed // 60}min elapsed)",
        )

        if running == 0:
            await _emit_log(platform, run_id, "  All workloads finished - ending monitoring early")
            break

        await asyncio.sleep(interval_seconds)
        elapsed += interval_seconds

    return PhaseResult(
        phase=OrchestrationPhase.MONITORING,
        status="passed",
        started_at=started,
        completed_at=datetime.now(UTC),
        details={"status_checks": checks, "total_checks": len(checks)},
    )


async def _phase_cleanup_verification(platform: Any, run_id: str) -> PhaseResult:
    """Phase 5: Verify all managed resources have been cleaned up."""
    started = datetime.now(UTC)
    await _emit_log(platform, run_id, "Phase 5: Verifying resource cleanup...")

    remaining = await platform.list_managed_resources(deployment_id=None)
    # Filter to resources from this run
    run_resources = [
        r for r in remaining if r.get("tags", {}).get("deployment-id", "").startswith(run_id[:8])
    ]

    await _emit_log(
        platform,
        run_id,
        f"  Found {len(run_resources)} remaining managed resources",
    )

    return PhaseResult(
        phase=OrchestrationPhase.CLEANUP_VERIFICATION,
        status="passed" if len(run_resources) == 0 else "needs_cleanup",
        started_at=started,
        completed_at=datetime.now(UTC),
        details={"remaining_resources": run_resources, "count": len(run_resources)},
    )


async def _phase_forced_cleanup(platform: Any, resources: list[dict], run_id: str) -> PhaseResult:
    """Phase 6: Force-delete remaining resources."""
    started = datetime.now(UTC)
    await _emit_log(platform, run_id, f"Phase 6: Force-cleaning {len(resources)} resources...")

    deleted = 0
    failed = 0
    for resource in resources:
        resource_id = resource.get("id", "")
        try:
            rc, _, stderr = platform._az_cli(["resource", "delete", "--ids", resource_id])
            if rc == 0:
                deleted += 1
            else:
                failed += 1
                logger.warning("Failed to delete %s: %s", resource_id, stderr)
        except Exception as exc:
            failed += 1
            logger.warning("Error deleting %s: %s", resource_id, exc)

    await _emit_log(platform, run_id, f"  Deleted {deleted}, failed {failed}")

    return PhaseResult(
        phase=OrchestrationPhase.FORCED_CLEANUP,
        status="passed" if failed == 0 else "partial",
        started_at=started,
        completed_at=datetime.now(UTC),
        details={"deleted": deleted, "failed": failed},
    )


async def _phase_reporting(result: OrchestrationResult, run_id: str) -> PhaseResult:
    """Phase 7: Generate execution report."""
    started = datetime.now(UTC)

    successful = sum(1 for d in result.deployments if d.get("status") == "deployed")
    failed = sum(1 for d in result.deployments if d.get("status") == "failed")

    result.summary = {
        "run_id": run_id,
        "workloads_deployed": successful,
        "workloads_failed": failed,
        "total_workloads": len(result.deployments),
        "phases_completed": sum(1 for p in result.phases if p.status == "passed"),
        "phases_total": len(result.phases) + 1,  # +1 for this reporting phase
    }

    return PhaseResult(
        phase=OrchestrationPhase.REPORTING,
        status="passed",
        started_at=started,
        completed_at=datetime.now(UTC),
        details=result.summary,
    )


# -----------------------------------------------------------------
# Event emission helpers
# -----------------------------------------------------------------


async def _emit_phase_change(platform: Any, run_id: str, phase: str) -> None:
    if hasattr(platform, "publish_event"):
        await platform.publish_event(
            DEPLOYMENT_PHASE_CHANGED,
            {
                "topic": DEPLOYMENT_PHASE_CHANGED,
                "deployment_id": run_id,
                "phase": phase,
            },
        )


async def _emit_log(platform: Any, run_id: str, message: str) -> None:
    logger.info("[%s] %s", run_id, message)
    if hasattr(platform, "publish_event"):
        await platform.publish_event(
            DEPLOYMENT_LOG,
            {
                "topic": DEPLOYMENT_LOG,
                "deployment_id": run_id,
                "line": message,
                "level": "INFO",
            },
        )


__all__ = [
    "run_orchestration",
    "OrchestrationResult",
    "OrchestrationPhase",
    "PhaseResult",
]
