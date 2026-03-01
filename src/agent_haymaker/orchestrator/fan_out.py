"""Fan-out controller for parallel workload execution.

Provides controlled parallel execution of async operations with
concurrency limiting via asyncio.Semaphore and two failure modes
(CONTINUE / FAIL_FAST).

Adapted from AzureHayMaker's FanOutController for local use
without Azure-specific dependencies.

Public API:
    FanOutController: Main controller class.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .types import ExecutionResult, ExecutionState, ExecutionStatus, FailureMode

logger = logging.getLogger(__name__)


class FanOutController:
    """Controls parallel execution of multiple async operations.

    Uses asyncio.Semaphore to limit concurrent executions.
    Supports CONTINUE and FAIL_FAST failure modes.

    Adapted from AzureHayMaker's FanOutController for local use
    without Azure-specific dependencies.

    Args:
        max_parallelism: Maximum number of concurrent executions.
            Defaults to 10.

    Example::

        controller = FanOutController(max_parallelism=5)
        items = [
            {"deployment_id": "d1", "workload_name": "w1", "config": {...}},
            {"deployment_id": "d2", "workload_name": "w2", "config": {...}},
        ]

        async def run_workload(deployment_id, workload_name, **kwargs):
            ...

        result = await controller.execute(items, run_workload)
        print(f"Succeeded: {result.succeeded_count}/{result.total_count}")
    """

    def __init__(self, max_parallelism: int = 10) -> None:
        if max_parallelism < 1:
            raise ValueError("max_parallelism must be >= 1")
        self._max_parallelism = max_parallelism

    async def execute(
        self,
        items: list[dict[str, Any]],
        execute_fn: Callable[..., Coroutine],
        failure_mode: FailureMode = FailureMode.CONTINUE,
    ) -> ExecutionResult:
        """Execute an async function for each item in parallel.

        Args:
            items: List of dicts, each passed as kwargs to execute_fn.
                Each must have ``deployment_id`` and ``workload_name`` keys.
            execute_fn: Async callable to execute for each item.
            failure_mode: How to handle failures (CONTINUE or FAIL_FAST).

        Returns:
            ExecutionResult with aggregated status for all items.

        Raises:
            ValueError: If any item is missing required keys.
        """
        # Per-execution state (not shared across concurrent execute() calls)
        semaphore = asyncio.Semaphore(self._max_parallelism)
        abort_event = asyncio.Event()

        execution_id = str(uuid4())
        started_at = datetime.now(UTC)

        for item in items:
            if "deployment_id" not in item or "workload_name" not in item:
                raise ValueError("Each item must have 'deployment_id' and 'workload_name' keys")

        result = ExecutionResult(
            execution_id=execution_id,
            started_at=started_at,
            total_count=len(items),
            failure_mode=failure_mode,
        )

        if not items:
            result.completed_at = datetime.now(UTC)
            return result

        tasks = [
            asyncio.create_task(
                self._execute_single(
                    item,
                    execute_fn,
                    failure_mode,
                    semaphore,
                    abort_event,
                )
            )
            for item in items
        ]

        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, entry in enumerate(raw_results):
            if isinstance(entry, BaseException):
                # Task raised an unhandled exception (e.g. CancelledError)
                status = ExecutionStatus(
                    deployment_id=items[i]["deployment_id"],
                    workload_name=items[i]["workload_name"],
                    state=ExecutionState.FAILED,
                    error_message=f"{type(entry).__name__}: {entry}",
                )
            else:
                status = entry
            result.statuses.append(status)
            if status.state == ExecutionState.COMPLETED:
                result.succeeded_count += 1
            elif status.state == ExecutionState.FAILED:
                result.failed_count += 1
            elif status.state == ExecutionState.SKIPPED:
                result.skipped_count += 1

        result.completed_at = datetime.now(UTC)
        result.aborted_early = abort_event.is_set()

        return result

    async def _execute_single(
        self,
        item: dict[str, Any],
        execute_fn: Callable[..., Coroutine],
        failure_mode: FailureMode,
        semaphore: asyncio.Semaphore,
        abort_event: asyncio.Event,
    ) -> ExecutionStatus:
        """Execute a single item with semaphore-based concurrency control."""
        deployment_id = item["deployment_id"]
        workload_name = item["workload_name"]

        status = ExecutionStatus(
            deployment_id=deployment_id,
            workload_name=workload_name,
        )

        if abort_event.is_set():
            status.state = ExecutionState.SKIPPED
            logger.info("Skipping %s/%s: abort signalled", workload_name, deployment_id)
            return status

        async with semaphore:
            if abort_event.is_set():
                status.state = ExecutionState.SKIPPED
                logger.info(
                    "Skipping %s/%s: abort signalled after semaphore acquire",
                    workload_name,
                    deployment_id,
                )
                return status

            status.state = ExecutionState.RUNNING
            status.started_at = datetime.now(UTC)
            logger.info("Starting %s/%s", workload_name, deployment_id)

            try:
                await execute_fn(**item)
                status.state = ExecutionState.COMPLETED
                status.completed_at = datetime.now(UTC)
                logger.info("Completed %s/%s", workload_name, deployment_id)
            except Exception as exc:
                status.state = ExecutionState.FAILED
                status.completed_at = datetime.now(UTC)
                status.error_message = f"{type(exc).__name__}: {exc}"
                logger.error(
                    "Failed %s/%s: %s",
                    workload_name,
                    deployment_id,
                    exc,
                    exc_info=True,
                )

                if failure_mode == FailureMode.FAIL_FAST:
                    abort_event.set()

        return status
