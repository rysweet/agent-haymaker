"""Core phase implementations for the orchestration workflow.

Phases 1-3 (validation, selection, provisioning) plus shared enums
and event helpers. Phases 4-7 (monitoring, cleanup, reporting) are
in monitoring.py.

Public API:
    PhaseStatus: Enum of phase outcomes
    OrchestrationPhase: Enum of workflow phases
    emit_phase_change: Publish phase-changed event
    emit_log: Log + publish event
    phase_validation: Phase 1
    phase_selection: Phase 2
    phase_provisioning: Phase 3
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from ..events import (
    DEPLOYMENT_LOG,
    DEPLOYMENT_PHASE_CHANGED,
)

_logger = logging.getLogger(__name__)


class PhaseStatus(StrEnum):
    """Possible statuses for a completed phase."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    PARTIAL = "partial"
    NEEDS_CLEANUP = "needs_cleanup"


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


# -----------------------------------------------------------------
# Event emission helpers
# -----------------------------------------------------------------


async def emit_phase_change(platform: Any, run_id: str, phase: str) -> None:
    """Publish a DEPLOYMENT_PHASE_CHANGED event if the platform supports it."""
    if hasattr(platform, "publish_event"):
        await platform.publish_event(
            DEPLOYMENT_PHASE_CHANGED,
            {
                "topic": DEPLOYMENT_PHASE_CHANGED,
                "deployment_id": run_id,
                "phase": phase,
            },
        )


async def emit_log(platform: Any, run_id: str, message: str) -> None:
    """Log a message and publish a DEPLOYMENT_LOG event if supported."""
    _logger.info("[%s] %s", run_id, message)
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


# -----------------------------------------------------------------
# Phase implementations
# -----------------------------------------------------------------


async def phase_validation(platform: Any, run_id: str) -> dict[str, Any]:
    """Phase 1: Validate Azure environment.

    Returns:
        Dict with keys: phase, status, started_at, completed_at, details, error.
    """
    started = datetime.now(UTC)
    await emit_log(platform, run_id, "Phase 1: Validating Azure environment...")

    try:
        checks = await platform.validate_environment()
        overall = checks.get("overall", {}).get("status", "failed")

        for name, check in checks.items():
            if name != "overall":
                status = check.get("status", "unknown")
                msg = check.get("message", "")
                await emit_log(platform, run_id, f"  {name}: {status} - {msg}")

        return {
            "phase": OrchestrationPhase.VALIDATION,
            "status": PhaseStatus.PASSED if overall == "passed" else PhaseStatus.FAILED,
            "started_at": started,
            "completed_at": datetime.now(UTC),
            "details": checks,
            "error": None,
        }
    except Exception as exc:
        return {
            "phase": OrchestrationPhase.VALIDATION,
            "status": PhaseStatus.FAILED,
            "started_at": started,
            "completed_at": datetime.now(UTC),
            "details": {},
            "error": str(exc),
        }


async def phase_selection(workloads: list[dict], run_id: str) -> dict[str, Any]:
    """Phase 2: Validate and confirm workload selection.

    Checks that every workload dict has a non-empty ``name`` key.
    """
    started = datetime.now(UTC)

    invalid: list[int] = []
    for idx, w in enumerate(workloads):
        name = w.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            invalid.append(idx)

    if invalid:
        return {
            "phase": OrchestrationPhase.SELECTION,
            "status": PhaseStatus.FAILED,
            "started_at": started,
            "completed_at": datetime.now(UTC),
            "details": {"invalid_indices": invalid},
            "error": f"Workloads at indices {invalid} missing a non-empty 'name'",
        }

    return {
        "phase": OrchestrationPhase.SELECTION,
        "status": PhaseStatus.PASSED,
        "started_at": started,
        "completed_at": datetime.now(UTC),
        "details": {
            "workload_count": len(workloads),
            "workloads": [w.get("name", "unknown") for w in workloads],
        },
        "error": None,
    }


async def phase_provisioning(
    platform: Any,
    workloads: list[dict],
    run_id: str,
) -> dict[str, Any]:
    """Phase 3: Provision SPs and deploy Container Apps."""
    from ..azure.provisioning import provision_workload

    started = datetime.now(UTC)
    await emit_log(platform, run_id, f"Phase 3: Provisioning {len(workloads)} workloads...")

    deployments: list[dict[str, Any]] = []
    sp_created = 0
    sp_failed = 0
    containers_deployed = 0
    containers_failed = 0

    for workload in workloads:
        wl_name = workload.get("name", "unknown")
        try:
            await emit_log(platform, run_id, f"  Provisioning workload: {wl_name}")
            result = await provision_workload(
                platform=platform,
                workload_name=wl_name,
                image=workload.get("image"),
                env_vars=workload.get("env_vars"),
                run_id=run_id,
            )
            sp_created += 1
            containers_deployed += 1
            deployments.append(result)

        except Exception as exc:
            _logger.error("Failed to provision %s: %s", wl_name, exc)
            sp_failed += 1
            containers_failed += 1
            deployments.append(
                {
                    "deployment_id": "",
                    "workload_name": wl_name,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    await emit_log(
        platform,
        run_id,
        f"Phase 3 complete: {sp_created} SPs, {containers_deployed} containers deployed",
    )

    failed = sp_failed + containers_failed
    if failed == 0:
        status = PhaseStatus.PASSED
    elif containers_deployed > 0:
        status = PhaseStatus.PARTIAL
    else:
        status = PhaseStatus.FAILED

    return {
        "phase": OrchestrationPhase.PROVISIONING,
        "status": status,
        "started_at": started,
        "completed_at": datetime.now(UTC),
        "details": {
            "deployments": deployments,
            "service_principals": {"created": sp_created, "failed": sp_failed},
            "container_apps": {"deployed": containers_deployed, "failed": containers_failed},
        },
        "error": None,
    }
