"""The registry that says which upkeep passes are in flight.

The bug it exists to make impossible: a long pass (memory organise, knowledge
tidy) whose "am I running?" answer lived in a browser component, so leaving the
page and coming back started a second one over the same files.
"""

from __future__ import annotations

import pytest

from coffer.application.upkeep_runs import UpkeepRunRegistry
from coffer.domain.errors import UpkeepAlreadyRunning


def test_a_free_key_is_claimed_and_a_taken_one_is_not() -> None:
    runs = UpkeepRunRegistry()

    assert runs.claim("memory", "coffer") is True
    assert runs.claim("memory", "coffer") is False


def test_the_same_name_under_a_different_kind_is_a_different_key() -> None:
    """A partition and a collection may share a name; they are not one target."""
    runs = UpkeepRunRegistry()

    assert runs.claim("memory", "coffer") is True
    assert runs.claim("knowledge", "coffer") is True


def test_release_frees_the_key_and_releasing_an_unheld_one_is_a_no_op() -> None:
    runs = UpkeepRunRegistry()
    runs.claim("memory", "coffer")

    runs.release("memory", "coffer")
    runs.release("memory", "coffer")  # nobody holds it; must not raise

    assert runs.claim("memory", "coffer") is True


def test_a_claimed_run_reports_what_it_is_and_since_when() -> None:
    runs = UpkeepRunRegistry()
    runs.claim("knowledge", "shopee")

    run = runs.running("knowledge", "shopee")
    assert run is not None
    assert (run.kind, run.name) == ("knowledge", "shopee")
    assert run.started_at.tzinfo is not None  # the surface renders it as a time
    assert runs.running("knowledge", "absent") is None


def test_list_running_names_every_kind_at_once() -> None:
    runs = UpkeepRunRegistry()
    runs.claim("memory", "coffer")
    runs.claim("knowledge", "shopee")

    assert {(r.kind, r.name) for r in runs.list_running()} == {
        ("memory", "coffer"),
        ("knowledge", "shopee"),
    }


def test_guard_holds_the_key_for_the_block_and_gives_it_back() -> None:
    runs = UpkeepRunRegistry()

    with runs.guard("memory", "coffer"):
        assert runs.claim("memory", "coffer") is False

    assert runs.claim("memory", "coffer") is True


def test_guard_refuses_a_second_pass_over_the_same_target() -> None:
    runs = UpkeepRunRegistry()
    runs.claim("memory", "coffer")

    with pytest.raises(UpkeepAlreadyRunning), runs.guard("memory", "coffer"):
        raise AssertionError("the block must not run")


def test_a_pass_that_raises_does_not_wedge_its_key() -> None:
    """The release is in a ``finally``; without it one failure would make a
    partition permanently un-organisable until the daemon restarted."""
    runs = UpkeepRunRegistry()

    with pytest.raises(RuntimeError), runs.guard("memory", "coffer"):
        raise RuntimeError("the pass blew up")

    assert runs.running("memory", "coffer") is None


def test_guard_refusing_does_not_release_the_holder_s_key() -> None:
    """The refusal path must not run the ``finally``: a second caller being
    turned away cannot be allowed to free the first caller's claim."""
    runs = UpkeepRunRegistry()
    runs.claim("knowledge", "shopee")

    with pytest.raises(UpkeepAlreadyRunning), runs.guard("knowledge", "shopee"):
        pass

    assert runs.running("knowledge", "shopee") is not None


async def test_claimed_reports_whether_it_got_the_key_instead_of_raising() -> None:
    """What a timer wants: busy is an ordinary state, not a fault."""
    runs = UpkeepRunRegistry()

    async with runs.claimed("memory", "coffer") as first:
        assert first is True
        async with runs.claimed("memory", "coffer") as second:
            assert second is False
        # The failed claim must not have released the outer one on its way out.
        assert runs.running("memory", "coffer") is not None

    assert runs.running("memory", "coffer") is None
