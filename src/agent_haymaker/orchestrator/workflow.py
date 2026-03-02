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
    OrchestrationPhase: StrEnum of workflow phases
    PhaseResult: Result of a single phase
    PhaseStatus: StrEnum of phase outcome statuses
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from ..events import (
    DEPLOYMENT_COMPLETED,
    DEPLOYMENT_FAILED,
    DEPLOYMENT_STARTED,
)
from .monitoring import (
    phase_cleanup_verification,
    phase_forced_cleanup,
    phase_monitoring,
    phase_reporting,
)
from .phases import (
    OrchestrationPhase,
    PhaseStatus,
    emit_phase_change,
    phase_provisioning,
    phase_selection,
    phase_validation,
)

logger = logging.getLogger(__name__)


class PhaseResult(BaseModel):
    """Result of a single workflow phase."""

    phase: str
    status: PhaseStatus = PhaseStatus.PASSED
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


def _make_phase_result(data: dict[str, Any]) -> PhaseResult:
    """Convert a phase function return dict into a PhaseResult model."""
    return PhaseResult(**data)


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
            pr = _make_phase_result(await phase_validation(platform, run_id))
            result.phases.append(pr)
            if pr.status == PhaseStatus.FAILED:
                result.status = "failed"
                result.completed_at = datetime.now(UTC)
                return result
            await emit_phase_change(platform, run_id, OrchestrationPhase.VALIDATION)

        # Phase 2: Selection
        pr = _make_phase_result(await phase_selection(workloads, run_id))
        result.phases.append(pr)
        if pr.status == PhaseStatus.FAILED:
            result.status = "failed"
            result.completed_at = datetime.now(UTC)
            return result
        await emit_phase_change(platform, run_id, OrchestrationPhase.SELECTION)

        # Phase 3: Provisioning
        pr = _make_phase_result(await phase_provisioning(platform, workloads, run_id))
        result.phases.append(pr)
        result.deployments = pr.details.get("deployments", [])
        if pr.status == PhaseStatus.FAILED:
            result.status = "failed"
            result.completed_at = datetime.now(UTC)
            return result
        await emit_phase_change(platform, run_id, OrchestrationPhase.PROVISIONING)

        # Phase 4: Monitoring
        pr = _make_phase_result(
            await phase_monitoring(
                platform,
                result.deployments,
                run_id,
                duration_hours,
                monitoring_interval_minutes,
            )
        )
        result.phases.append(pr)
        await emit_phase_change(platform, run_id, OrchestrationPhase.MONITORING)

        # Phase 5: Cleanup Verification
        pr = _make_phase_result(await phase_cleanup_verification(platform, run_id))
        result.phases.append(pr)
        await emit_phase_change(platform, run_id, OrchestrationPhase.CLEANUP_VERIFICATION)

        # Phase 6: Forced Cleanup (if needed)
        remaining = pr.details.get("remaining_resources", [])
        if remaining:
            pr = _make_phase_result(await phase_forced_cleanup(platform, remaining, run_id))
            result.phases.append(pr)
            await emit_phase_change(platform, run_id, OrchestrationPhase.FORCED_CLEANUP)

        # Phase 7: Reporting
        pr = _make_phase_result(await phase_reporting(result, run_id))
        result.phases.append(pr)
        await emit_phase_change(platform, run_id, OrchestrationPhase.REPORTING)

        result.status = "completed"

    except Exception as exc:
        logger.error("Orchestration %s failed: %s", run_id, exc, exc_info=True)
        result.status = "failed"
        result.phases.append(
            PhaseResult(
                phase="error",
                status=PhaseStatus.FAILED,
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


__all__ = [
    "run_orchestration",
    "OrchestrationResult",
    "OrchestrationPhase",
    "PhaseResult",
    "PhaseStatus",
]
