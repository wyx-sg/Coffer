"""How long Coffer waits for its own model, when the operator has a say.

The bound used to be a constant per call site. Making it a setting is only
worth anything if three things hold, and each test below is one of them: an
unchosen value still behaves exactly as the constant did, a chosen one is read
at the moment of the call rather than captured at wiring time, and a value that
cannot be honoured is clamped rather than raised on — a background pass is the
wrong place to take itself down over a number.
"""

from __future__ import annotations

from coffer.application.engine_timeout import (
    DEFAULT_MODEL_TIMEOUT_S,
    MAX_MODEL_TIMEOUT_S,
    MIN_MODEL_TIMEOUT_S,
    resolve_timeout,
)


async def test_no_reader_at_all_is_the_built_in_default() -> None:
    # The construction a unit test and a pass built before the singleton exists
    # both take. Making the bound configurable must not make it mandatory.
    assert await resolve_timeout(None) == DEFAULT_MODEL_TIMEOUT_S


async def test_an_unchosen_bound_is_the_built_in_default() -> None:
    # NULL means "whatever Coffer ships with", the same thing it means for an
    # upkeep interval — so the default stays in one place and raising it later
    # reaches every vault that never chose.
    async def unchosen() -> int | None:
        return None

    assert await resolve_timeout(unchosen) == DEFAULT_MODEL_TIMEOUT_S


async def test_a_chosen_bound_is_used() -> None:
    async def chosen() -> int | None:
        return 180

    assert await resolve_timeout(chosen) == 180.0


async def test_the_bound_is_re_read_per_call_not_captured() -> None:
    # The whole point: the operator changes this on the Settings page, or on
    # another machine whose row converges here, and the next call must feel it
    # without a daemon restart.
    answers = iter([60, 300])

    async def changing() -> int | None:
        return next(answers)

    assert await resolve_timeout(changing) == 60.0
    assert await resolve_timeout(changing) == 300.0


async def test_a_bound_below_the_floor_is_clamped_not_raised() -> None:
    # Such a value cannot come from a surface — those refuse it — so it came
    # from an older build or a hand-edited synced document. Raising here would
    # take down a pass that could have run.
    async def far_too_small() -> int | None:
        return 1

    assert await resolve_timeout(far_too_small) == float(MIN_MODEL_TIMEOUT_S)


async def test_a_bound_above_the_ceiling_is_clamped() -> None:
    # The ceiling is what stops a typo from reintroducing the failure this
    # module exists to prevent: an unattended pass holding a wedged connection.
    async def far_too_large() -> int | None:
        return 99999

    assert await resolve_timeout(far_too_large) == float(MAX_MODEL_TIMEOUT_S)
