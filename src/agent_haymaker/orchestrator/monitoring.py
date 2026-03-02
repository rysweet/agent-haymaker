"""Monitoring, cleanup, and reporting phases for the orchestration workflow.

Phases 4-7 extracted from phases.py to keep modules under 300 LOC.

Public API:
    phase_monitoring: Phase 4 - periodic status checks
    phase_cleanup_verification: Phase 5 - verify resource cleanup
    phase_forced_cleanup: Phase 6 - force-delete remaining resources
    phase_reporting: Phase 7 - generate execution report
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from ..azure.az_cli import run_az
from .phases import OrchestrationPhase, PhaseStatus, emit_log

if TYPE_CHECKING:
    from .workflow import OrchestrationResult

_logger = logging.getLogger(__name__)


async def phase_monitoring(
    platform: Any,
    deployments: list[dict],
    run_id: str,
    duration_hours: int,
    interval_minutes: int,
) -> dict[str, Any]:
    """Phase 4: Monitor workloads for the configured duration."""
    started = datetime.now(UTC)
    total_seconds = duration_hours * 3600
    interval_seconds = interval_minutes * 60
    checks: list[dict[str, Any]] = []

    await emit_log(
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
            except Exception as exc:
                _logger.warning("Status check failed for %s: %s", app_name, exc)
                running += 1  # Assume still running on check failure

        check = {
            "timestamp": datetime.now(UTC).isoformat(),
            "running": running,
            "completed": completed,
            "failed": failed,
            "elapsed_minutes": elapsed // 60,
        }
        checks.append(check)
        await emit_log(
            platform,
            run_id,
            f"  Status check: running={running}, completed={completed}, "
            f"failed={failed} ({elapsed // 60}min elapsed)",
        )

        if running == 0:
            await emit_log(platform, run_id, "  All workloads finished - ending monitoring early")
            break

        await asyncio.sleep(interval_seconds)
        elapsed += interval_seconds

    return {
        "phase": OrchestrationPhase.MONITORING,
        "status": PhaseStatus.PASSED,
        "started_at": started,
        "completed_at": datetime.now(UTC),
        "details": {"status_checks": checks, "total_checks": len(checks)},
        "error": None,
    }


async def phase_cleanup_verification(platform: Any, run_id: str) -> dict[str, Any]:
    """Phase 5: Verify all managed resources have been cleaned up."""
    started = datetime.now(UTC)
    await emit_log(platform, run_id, "Phase 5: Verifying resource cleanup...")

    remaining = await platform.list_managed_resources(deployment_id=None)
    run_resources = [
        r for r in remaining if r.get("tags", {}).get("deployment-id", "").startswith(run_id[:8])
    ]

    await emit_log(
        platform,
        run_id,
        f"  Found {len(run_resources)} remaining managed resources",
    )

    return {
        "phase": OrchestrationPhase.CLEANUP_VERIFICATION,
        "status": PhaseStatus.PASSED if len(run_resources) == 0 else PhaseStatus.NEEDS_CLEANUP,
        "started_at": started,
        "completed_at": datetime.now(UTC),
        "details": {"remaining_resources": run_resources, "count": len(run_resources)},
        "error": None,
    }


async def phase_forced_cleanup(
    platform: Any,
    resources: list[dict],
    run_id: str,
) -> dict[str, Any]:
    """Phase 6: Force-delete remaining resources via ``run_az``."""
    started = datetime.now(UTC)
    await emit_log(platform, run_id, f"Phase 6: Force-cleaning {len(resources)} resources...")

    deleted = 0
    failed = 0
    for resource in resources:
        resource_id = resource.get("id", "")
        try:
            rc, _, stderr = run_az(["resource", "delete", "--ids", resource_id])
            if rc == 0:
                deleted += 1
            else:
                failed += 1
                _logger.warning("Failed to delete %s: %s", resource_id, stderr)
        except Exception as exc:
            failed += 1
            _logger.warning("Error deleting %s: %s", resource_id, exc)

    await emit_log(platform, run_id, f"  Deleted {deleted}, failed {failed}")

    return {
        "phase": OrchestrationPhase.FORCED_CLEANUP,
        "status": PhaseStatus.PASSED if failed == 0 else PhaseStatus.PARTIAL,
        "started_at": started,
        "completed_at": datetime.now(UTC),
        "details": {"deleted": deleted, "failed": failed},
        "error": None,
    }


async def phase_reporting(result: OrchestrationResult, run_id: str) -> dict[str, Any]:
    """Phase 7: Generate execution report."""
    started = datetime.now(UTC)

    successful = sum(1 for d in result.deployments if d.get("status") == "deployed")
    failed_count = sum(1 for d in result.deployments if d.get("status") == "failed")

    summary = {
        "run_id": run_id,
        "workloads_deployed": successful,
        "workloads_failed": failed_count,
        "total_workloads": len(result.deployments),
        "phases_completed": sum(1 for p in result.phases if p.status == PhaseStatus.PASSED),
        "phases_total": len(result.phases) + 1,  # +1 for this reporting phase
    }
    result.summary = summary

    return {
        "phase": OrchestrationPhase.REPORTING,
        "status": PhaseStatus.PASSED,
        "started_at": started,
        "completed_at": datetime.now(UTC),
        "details": summary,
        "error": None,
    }


__all__ = [
    "phase_monitoring",
    "phase_cleanup_verification",
    "phase_forced_cleanup",
    "phase_reporting",
]
