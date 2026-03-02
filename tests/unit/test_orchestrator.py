"""Tests for the orchestrator module.

Testing pyramid:
- 70% unit tests (types, state transitions)
- 30% integration tests (FanOutController execution)
"""

import asyncio

import pytest

from agent_haymaker.orchestrator import (
    ExecutionResult,
    ExecutionState,
    ExecutionStatus,
    FailureMode,
    FanOutController,
)


class TestFailureMode:
    def test_values(self):
        assert FailureMode.CONTINUE == "continue"
        assert FailureMode.FAIL_FAST == "fail_fast"


class TestExecutionState:
    def test_all_states(self):
        assert ExecutionState.PENDING == "pending"
        assert ExecutionState.RUNNING == "running"
        assert ExecutionState.COMPLETED == "completed"
        assert ExecutionState.FAILED == "failed"
        assert ExecutionState.SKIPPED == "skipped"


class TestExecutionStatus:
    def test_create(self):
        status = ExecutionStatus(deployment_id="dep-1", workload_name="test")
        assert status.state == "pending"
        assert status.started_at is None
        assert status.error_message is None


class TestExecutionResult:
    def test_all_succeeded(self):
        from datetime import datetime

        result = ExecutionResult(
            execution_id="exec-1",
            started_at=datetime.now(),
            total_count=2,
            succeeded_count=2,
            failure_mode=FailureMode.CONTINUE,
        )
        assert result.all_succeeded is True

    def test_not_all_succeeded(self):
        from datetime import datetime

        result = ExecutionResult(
            execution_id="exec-1",
            started_at=datetime.now(),
            total_count=2,
            succeeded_count=1,
            failed_count=1,
            failure_mode=FailureMode.CONTINUE,
        )
        assert result.all_succeeded is False

    def test_duration_seconds(self):
        from datetime import datetime, timedelta

        start = datetime.now()
        result = ExecutionResult(
            execution_id="exec-1",
            started_at=start,
            completed_at=start + timedelta(seconds=5),
            total_count=1,
            failure_mode=FailureMode.CONTINUE,
        )
        assert result.duration_seconds == pytest.approx(5.0)

    def test_duration_none_when_not_completed(self):
        from datetime import datetime

        result = ExecutionResult(
            execution_id="exec-1",
            started_at=datetime.now(),
            total_count=1,
            failure_mode=FailureMode.CONTINUE,
        )
        assert result.duration_seconds is None


class TestFanOutController:
    @pytest.mark.asyncio
    async def test_execute_success(self):
        """All items succeed."""

        async def execute_fn(**kwargs):
            await asyncio.sleep(0.01)

        controller = FanOutController(max_parallelism=2)
        result = await controller.execute(
            items=[
                {"deployment_id": "dep-1", "workload_name": "w1"},
                {"deployment_id": "dep-2", "workload_name": "w2"},
            ],
            execute_fn=execute_fn,
        )
        assert result.succeeded_count == 2
        assert result.failed_count == 0
        assert result.all_succeeded is True

    @pytest.mark.asyncio
    async def test_execute_with_failure_continue(self):
        """Failures in CONTINUE mode don't stop other items."""

        async def execute_fn(**kwargs):
            if kwargs["deployment_id"] == "dep-1":
                raise RuntimeError("boom")
            await asyncio.sleep(0.01)

        controller = FanOutController(max_parallelism=5)
        result = await controller.execute(
            items=[
                {"deployment_id": "dep-1", "workload_name": "w1"},
                {"deployment_id": "dep-2", "workload_name": "w2"},
            ],
            execute_fn=execute_fn,
            failure_mode=FailureMode.CONTINUE,
        )
        assert result.succeeded_count == 1
        assert result.failed_count == 1
        assert result.all_succeeded is False

    @pytest.mark.asyncio
    async def test_execute_with_failure_fail_fast(self):
        """FAIL_FAST mode skips remaining items after first failure."""

        call_order = []

        async def execute_fn(**kwargs):
            call_order.append(kwargs["deployment_id"])
            if kwargs["deployment_id"] == "dep-1":
                raise RuntimeError("boom")
            # Longer sleep so dep-2 hasn't started yet when dep-1 fails
            await asyncio.sleep(0.5)

        controller = FanOutController(max_parallelism=1)  # Serial execution
        result = await controller.execute(
            items=[
                {"deployment_id": "dep-1", "workload_name": "w1"},
                {"deployment_id": "dep-2", "workload_name": "w2"},
            ],
            execute_fn=execute_fn,
            failure_mode=FailureMode.FAIL_FAST,
        )
        assert result.failed_count >= 1
        assert result.aborted_early is True

    @pytest.mark.asyncio
    async def test_parallelism_limit(self):
        """Semaphore should limit concurrent executions."""
        max_concurrent = 0
        current_concurrent = 0
        lock = asyncio.Lock()

        async def execute_fn(**kwargs):
            nonlocal max_concurrent, current_concurrent
            async with lock:
                current_concurrent += 1
                max_concurrent = max(max_concurrent, current_concurrent)
            await asyncio.sleep(0.05)
            async with lock:
                current_concurrent -= 1

        controller = FanOutController(max_parallelism=2)
        items = [{"deployment_id": f"dep-{i}", "workload_name": "w"} for i in range(5)]
        await controller.execute(items=items, execute_fn=execute_fn)
        assert max_concurrent <= 2

    @pytest.mark.asyncio
    async def test_empty_items(self):
        """Empty items list should return empty result."""

        async def execute_fn(**kwargs):
            pass

        controller = FanOutController()
        result = await controller.execute(items=[], execute_fn=execute_fn)
        assert result.total_count == 0
        assert result.all_succeeded is True

    @pytest.mark.asyncio
    async def test_invalid_items_missing_keys(self):
        """Items missing required keys should fail with ValueError."""

        async def execute_fn(**kwargs):
            pass

        controller = FanOutController()
        with pytest.raises(ValueError, match="deployment_id"):
            await controller.execute(
                items=[{"wrong_key": "value"}],
                execute_fn=execute_fn,
            )
