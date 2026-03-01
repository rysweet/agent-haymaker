"""Orchestrator module for parallel execution and Azure deployment workflows.

Provides:
- FanOutController for parallel async operations with concurrency limits
- 7-phase orchestration workflow for Azure deployments
- Execution state tracking via Pydantic models

Public API:
    FanOutController: Parallel execution controller with semaphore limiting.
    FailureMode: Enum for CONTINUE vs FAIL_FAST behavior.
    ExecutionState: Enum for per-item execution states.
    ExecutionStatus: Pydantic model for per-item status tracking.
    ExecutionResult: Pydantic model for aggregated fan-out results.
    run_orchestration: Execute the 7-phase Azure deployment workflow.
    OrchestrationResult: Result of the orchestration run.
"""

from .fan_out import FanOutController
from .types import ExecutionResult, ExecutionState, ExecutionStatus, FailureMode
from .workflow import OrchestrationPhase, OrchestrationResult, run_orchestration

__all__ = [
    "FanOutController",
    "FailureMode",
    "ExecutionState",
    "ExecutionStatus",
    "ExecutionResult",
    "run_orchestration",
    "OrchestrationResult",
    "OrchestrationPhase",
]
