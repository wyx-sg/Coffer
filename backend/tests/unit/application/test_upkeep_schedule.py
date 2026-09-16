"""Waiting for the next pass, when the interval can change mid-wait.

A worker that sleeps for six hours does not learn that the operator set the
interval to fifteen minutes until the six hours are up — which reads as the
setting not working. The wait is therefore sliced and the interval re-read.
"""

from __future__ import annotations

from coffer.application.upkeep_schedule import wait_for_next_pass


class FakeClock:
    """Records the naps instead of taking them."""

    def __init__(self) -> None:
        self.naps: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.naps.append(seconds)


async def test_an_unset_interval_waits_the_passs_own_default() -> None:
    # The default stays in the worker that owns the pass, so raising it later
    # reaches every vault that never chose one.
    clock = FakeClock()

    async def unset() -> int | None:
        return None

    await wait_for_next_pass(unset, default_s=90, slice_s=30, sleep=clock.sleep)

    assert clock.naps == [30, 30, 30]


async def test_a_configured_interval_replaces_the_default() -> None:
    clock = FakeClock()

    async def every_minute() -> int | None:
        return 60

    await wait_for_next_pass(every_minute, default_s=6 * 60 * 60, slice_s=30, sleep=clock.sleep)

    assert clock.naps == [30, 30]


async def test_shortening_the_interval_mid_wait_can_make_the_pass_due_now() -> None:
    # The whole point: the operator asked for sooner, so sooner must mean now
    # rather than at the end of the wait already under way.
    clock = FakeClock()
    answers = iter([6 * 60 * 60, 6 * 60 * 60, 30])

    async def changing() -> int | None:
        return next(answers)

    await wait_for_next_pass(changing, default_s=6 * 60 * 60, slice_s=30, sleep=clock.sleep)

    # Two slices elapsed, then the new 30s interval was already satisfied.
    assert clock.naps == [30, 30]


async def test_lengthening_the_interval_extends_the_wait_in_progress() -> None:
    clock = FakeClock()
    answers = iter([30, 90, 90, 90])

    async def changing() -> int | None:
        return next(answers)

    await wait_for_next_pass(changing, default_s=30, slice_s=30, sleep=clock.sleep)

    assert clock.naps == [30, 30, 30]


async def test_a_nonsense_interval_falls_back_to_the_default() -> None:
    # Zero and negatives would busy-loop a pass over the user's files.
    clock = FakeClock()

    async def zero() -> int | None:
        return 0

    await wait_for_next_pass(zero, default_s=60, slice_s=30, sleep=clock.sleep)

    assert clock.naps == [30, 30]


async def test_the_last_slice_is_cut_to_the_time_that_is_left() -> None:
    # A pass is never started later than it was asked for, even when the
    # interval is not a whole number of slices.
    clock = FakeClock()

    async def forty_five() -> int | None:
        return 45

    await wait_for_next_pass(forty_five, default_s=60, slice_s=30, sleep=clock.sleep)

    assert clock.naps == [30, 15]


async def test_a_zero_interval_still_yields_once() -> None:
    """A caller's loop is `pass; wait; pass; …`. A wait that returns without
    ever handing control back is not a fast timer — it is a loop that never
    lets the daemon serve a request again."""
    clock = FakeClock()

    async def unset() -> int | None:
        return None

    await wait_for_next_pass(unset, default_s=0, slice_s=30, sleep=clock.sleep)

    assert clock.naps == [0]
