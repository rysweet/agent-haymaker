"""Orchestrator module for fan-out parallel workload execution.

Provides the FanOutController for running multiple async operations
in parallel with concurrency limits and configurable failure modes.
Adapted from AzureHayMaker's MetaOrchestrator/FanOutController
patterns for local use without Azure dependencies.

Public API:
    FanOutController: Parallel execution controller with semaphore limiting.
    FailureMode: Enum for CONTINUE vs FAIL_FAST behavior.
    ExecutionState: Enum for per-item execution states.
    ExecutionStatus: Pydantic model for per-item status tracking.
    ExecutionResult: Pydantic model for aggregated fan-out results.
"""

from .fan_out import FanOutController
from .types import ExecutionResult, ExecutionState, ExecutionStatus, FailureMode

__all__ = [
    "FanOutController",
    "FailureMode",
    "ExecutionState",
    "ExecutionStatus",
    "ExecutionResult",
]
