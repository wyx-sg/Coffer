"""Unit tests for the transcript summary cache's warm worker.

The worker exists so the first visit to Conversations after an install is never
the one that pays for the cold parse. These cover the catch-up pass it runs on
start, and its refusal to let one bad agent cost the others theirs.
"""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.agent.transcript_warm_worker import AgentTarget, TranscriptWarmWorker


def _worker(
    targets: list[AgentTarget],
    warmed: list[AgentTarget],
    *,
    fail_on: str | None = None,
) -> TranscriptWarmWorker:
    async def list_targets() -> list[AgentTarget]:
        return targets

    def warm(agent_type_value: str, config_dir: str) -> int:
        if agent_type_value == fail_on:
            raise OSError("config dir went away")
        warmed.append((agent_type_value, config_dir))
        return 7

    return TranscriptWarmWorker(warm=warm, list_targets=list_targets, interval_seconds=0.01)


@pytest.mark.asyncio
async def test_catch_up_pass_warms_every_target() -> None:
    warmed: list[AgentTarget] = []
    await _worker([("claude_code", "/cfg/claude"), ("codex", "/cfg/codex")], warmed).run_once()
    assert warmed == [("claude_code", "/cfg/claude"), ("codex", "/cfg/codex")]


@pytest.mark.asyncio
async def test_one_failing_agent_does_not_cost_the_others_their_pass() -> None:
    warmed: list[AgentTarget] = []
    worker = _worker(
        [("claude_code", "/gone"), ("codex", "/cfg/codex")], warmed, fail_on="claude_code"
    )
    await worker.run_once()
    assert warmed == [("codex", "/cfg/codex")]


@pytest.mark.asyncio
async def test_a_failing_listing_is_logged_not_fatal() -> None:
    async def list_targets() -> list[AgentTarget]:
        raise RuntimeError("no database")

    def warm(agent_type_value: str, config_dir: str) -> int:  # pragma: no cover
        raise AssertionError("must not be reached")

    await TranscriptWarmWorker(warm=warm, list_targets=list_targets).run_once()


@pytest.mark.asyncio
async def test_run_does_a_catch_up_pass_then_stops_cleanly() -> None:
    warmed: list[AgentTarget] = []
    worker = _worker([("codex", "/cfg/codex")], warmed)
    task = asyncio.create_task(worker.run())
    while not warmed:  # the catch-up pass runs before the first interval wait
        await asyncio.sleep(0)
    worker.stop()
    await asyncio.wait_for(task, timeout=2.0)
