"""Orchestrator type definitions and data models.

Pydantic models and enums for fan-out execution tracking, adapted
from AzureHayMaker's meta_orchestrator types for local use without
Azure-specific dependencies.

Public API:
    FailureMode: Enum controlling behavior on workload failure.
    ExecutionState: Enum for individual workload execution state.
    ExecutionStatus: Status model for a single workload execution.
    ExecutionResult: Aggregated result model for a fan-out execution.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FailureMode(StrEnum):
    """Controls behavior when a workload execution fails.

    CONTINUE: Keep executing remaining workloads (default).
    FAIL_FAST: Abort remaining workloads on first failure.
    """

    CONTINUE = "continue"
    FAIL_FAST = "fail_fast"


class ExecutionState(StrEnum):
    """State of a single workload execution within a fan-out."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionStatus(BaseModel):
    """Status for a single workload execution within a fan-out.

    Tracks the lifecycle of one item passed to FanOutController.execute().

    Attributes:
        deployment_id: Identifier for this particular execution.
        workload_name: Name of the workload being executed.
        state: Current execution state.
        started_at: When execution began (None if still pending).
        completed_at: When execution finished (None if still running).
        error_message: Error details if state is FAILED.
    """

    deployment_id: str
    workload_name: str
    state: ExecutionState = ExecutionState.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None

    model_config = ConfigDict(use_enum_values=True)


class ExecutionResult(BaseModel):
    """Aggregated result of a fan-out execution.

    Collects status from all workload executions and provides
    summary counts and timing information.

    Attributes:
        execution_id: Unique identifier for this fan-out run.
        started_at: When the fan-out began.
        completed_at: When the fan-out finished (None if still running).
        total_count: Total number of items in the fan-out.
        succeeded_count: Number of items that completed successfully.
        failed_count: Number of items that failed.
        skipped_count: Number of items skipped (due to FAIL_FAST abort).
        statuses: Per-item execution status records.
        failure_mode: The failure mode used for this execution.
        aborted_early: Whether execution was aborted due to FAIL_FAST.
    """

    execution_id: str
    started_at: datetime
    completed_at: datetime | None = None
    total_count: int
    succeeded_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    statuses: list[ExecutionStatus] = Field(default_factory=list)
    failure_mode: FailureMode = FailureMode.CONTINUE
    aborted_early: bool = False

    model_config = ConfigDict(use_enum_values=True)

    @property
    def all_succeeded(self) -> bool:
        """True when every item completed without failure or skip."""
        return self.failed_count == 0 and self.skipped_count == 0

    @property
    def duration_seconds(self) -> float | None:
        """Wall-clock duration in seconds, or None if still running."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()
