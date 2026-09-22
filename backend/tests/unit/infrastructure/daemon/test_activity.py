"""The idle clock — what counts as the daemon being wanted, and what holds it.

spec daemon FR-029. The interesting decisions here are not arithmetic: they
are which evidence of use is admitted (holds, not just requests) and which
clock is consulted (monotonic, so a sleeping laptop is not nine hours of
disuse).
"""

from __future__ import annotations

import pytest

from coffer.infrastructure.daemon import activity


@pytest.fixture(autouse=True)
def _clean_clock() -> None:
    activity.reset()


def test_a_fresh_daemon_is_barely_idle() -> None:
    assert activity.idle_seconds() < 1.0


class _Clock:
    """A monotonic clock the test drives.

    Wall-clock arithmetic would be wrong here for the same reason the module
    refuses it, and the real monotonic clock is the machine's uptime — which
    on a host that has been up for a fortnight is a larger number than any
    constant a test would pick, so patching it with one reads as "idle for a
    negative time".
    """

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    c = _Clock()
    monkeypatch.setattr(activity.time, "monotonic", c)
    activity.reset()
    return c


def test_a_finished_request_restarts_the_clock(clock: _Clock) -> None:
    clock.now = 1_000.0
    activity.request_started()
    activity.request_ended()
    clock.now = 1_100.0
    assert activity.idle_seconds() == pytest.approx(100.0)


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a daemon nothing has wanted stands down",
)
def test_a_hold_means_the_daemon_is_never_idle(clock: _Clock) -> None:
    """The channel listener's case: hours with no request is exactly what it
    is for, because the message that justifies it arrives the next morning.
    A hold is not weighed against elapsed time — it settles the question."""
    activity.request_started()
    activity.request_ended()
    clock.now += 86_400.0  # a day with nothing asking
    activity.hold("channel-listener")
    assert activity.idle_seconds() == 0.0
    assert activity.holds() == frozenset({"channel-listener"})

    activity.release("channel-listener")
    assert activity.idle_seconds() == pytest.approx(86_400.0)


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a daemon nothing has wanted stands down",
)
def test_a_request_still_open_is_not_idleness(clock: _Clock) -> None:
    """`/mcp` is SSE, and an agent's shim holds that stream for a whole
    session. Counting only the instant a request arrived would read a
    connected agent that has not called a tool since last night as nobody at
    all — and then stand down waiting on the very stream that should have
    stopped it."""
    activity.request_started()
    clock.now += 86_400.0  # a day, with the stream still open
    assert activity.in_flight() == 1
    assert activity.idle_seconds() == 0.0

    activity.request_ended()
    clock.now += 60.0
    assert activity.idle_seconds() == pytest.approx(60.0)


def test_the_in_flight_count_never_goes_negative() -> None:
    # An unbalanced end (a middleware that raised before its start, a test
    # that reset mid-request) must not leave the daemon permanently "busy"
    # by wrapping around.
    activity.request_ended()
    assert activity.in_flight() == 0


def test_holds_are_idempotent_by_name() -> None:
    # The channel runtime re-asserts its hold on every reconcile tick rather
    # than tracking whether it already has one, so both halves must be safe
    # to repeat.
    activity.hold("channel-listener")
    activity.hold("channel-listener")
    activity.release("channel-listener")
    activity.release("channel-listener")
    assert activity.holds() == frozenset()


def test_the_clock_is_monotonic_not_wall_clock() -> None:
    """A laptop that slept did not go unused for the length of the nap.

    Read off the module rather than behaviour: the difference only shows on a
    machine that actually suspends, and the point is that nothing here ever
    reaches for ``time.time``.
    """
    import inspect

    source = inspect.getsource(activity)
    assert "time.monotonic()" in source
    assert "time.time()" not in source
