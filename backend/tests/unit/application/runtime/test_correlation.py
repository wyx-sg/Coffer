"""Correlation ids: bind, nest, reset, and what a turn gets."""

from __future__ import annotations

import asyncio

from coffer.application.runtime import correlation


def test_nothing_bound_reads_as_no_trace() -> None:
    correlation.bind_trace_id(None)
    assert correlation.current() == correlation.Correlation()
    assert correlation.get_trace_id() == "-"
    assert correlation.current().log_fields() == {"trace_id": "-"}


def test_a_bind_adds_ids_and_its_reset_restores_the_outer_ones() -> None:
    with correlation.correlated(trace_id="req-1"):
        with correlation.correlated(session_id="sess-9"):
            assert correlation.current().log_fields() == {
                "trace_id": "req-1",
                "session_id": "sess-9",
            }
        assert correlation.current().session_id is None
        assert correlation.get_trace_id() == "req-1"
    assert correlation.get_trace_id() == "-"


def test_a_turn_keeps_the_request_trace_id() -> None:
    with correlation.correlated(trace_id="req-1"), correlation.turn("conv-1") as bound:
        assert bound.trace_id == "req-1"
        assert bound.conversation_id == "conv-1"
        assert bound.turn_id is not None and len(bound.turn_id) == 16
    assert correlation.current().turn_id is None


def test_a_turn_with_no_request_uses_its_own_id_as_the_trace() -> None:
    correlation.bind_trace_id(None)
    with correlation.turn("conv-2") as bound:
        assert bound.trace_id == bound.turn_id
    assert correlation.current() == correlation.Correlation()


async def test_a_task_spawned_inside_a_turn_keeps_its_ids_after_the_turn_unbinds() -> None:
    seen: list[correlation.Correlation] = []
    release = asyncio.Event()

    async def child() -> None:
        await release.wait()
        seen.append(correlation.current())

    with correlation.turn("conv-3") as bound:
        task = asyncio.create_task(child())
    release.set()
    await task
    assert seen == [bound]


def test_clearing_the_trace_clears_every_id() -> None:
    correlation.bind(trace_id="req-1", session_id="s", conversation_id="c", turn_id="t")
    correlation.bind_trace_id(None)
    assert correlation.current() == correlation.Correlation()
