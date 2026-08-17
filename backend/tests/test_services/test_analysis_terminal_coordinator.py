from __future__ import annotations

import asyncio

import pytest

from backend.services.analysis.task_lifecycle import AnalysisTaskStatus, TerminalCoordinator, TerminalResult


@pytest.mark.asyncio
async def test_terminal_coordinator_runs_cleanup_once_under_race():
    coordinator = TerminalCoordinator()
    cleanup_calls = 0
    entered = asyncio.Event()
    release = asyncio.Event()

    async def cleanup() -> None:
        nonlocal cleanup_calls
        cleanup_calls += 1
        entered.set()
        await release.wait()

    result = TerminalResult(AnalysisTaskStatus.COMPLETED)
    first = asyncio.create_task(coordinator.run_once("task", result, cleanup))
    await entered.wait()
    second = asyncio.create_task(coordinator.run_once("task", result, cleanup))
    release.set()

    assert await first is True
    assert await second is False
    assert cleanup_calls == 1
    assert coordinator.result("task") == result


@pytest.mark.asyncio
async def test_terminal_coordinator_retries_after_cleanup_failure():
    coordinator = TerminalCoordinator()
    calls = 0

    async def cleanup() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("redis temporarily unavailable")

    result = TerminalResult(AnalysisTaskStatus.FAILED, reason="runtime failure")
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        await coordinator.run_once("task", result, cleanup)

    assert coordinator.result("task") is None
    assert await coordinator.run_once("task", result, cleanup) is True
    assert calls == 2


@pytest.mark.asyncio
async def test_terminal_coordinator_reset_allows_fresh_registration():
    coordinator = TerminalCoordinator()
    calls = 0

    async def cleanup() -> None:
        nonlocal calls
        calls += 1

    completed = TerminalResult(AnalysisTaskStatus.COMPLETED)
    cancelled = TerminalResult(AnalysisTaskStatus.CANCELLED)

    assert await coordinator.run_once("task", completed, cleanup) is True
    assert await coordinator.run_once("task", cancelled, cleanup) is False

    coordinator.reset("task")

    assert await coordinator.run_once("task", cancelled, cleanup) is True
    assert calls == 2
    assert coordinator.result("task") == cancelled
