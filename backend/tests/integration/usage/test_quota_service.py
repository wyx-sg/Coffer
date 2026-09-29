"""QuotaService: latest per window, never older, stale after reset, read floors."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from coffer.application.usage.quota import QuotaService
from coffer.infrastructure.persistence.usage_repo import SqlAlchemyQuotaRepo

from .conftest import NOW, FakeClock

_LATER = int((NOW + timedelta(hours=3)).timestamp())


class FakeCodexReader:
    def __init__(self, result: dict[str, Any] | None) -> None:
        self.result = result
        self.calls = 0

    async def read(self) -> dict[str, Any] | None:
        self.calls += 1
        return self.result


def _codex_result(used: int) -> dict[str, Any]:
    return {
        "rateLimits": {
            "primary": {"usedPercent": used, "windowDurationMins": 300, "resetsAt": _LATER},
            "secondary": {"usedPercent": 3, "windowDurationMins": 10080, "resetsAt": _LATER},
        }
    }


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="no fresh value shows no number",
)
async def test_agent_with_no_value_says_so(sm) -> None:  # type: ignore[no-untyped-def]
    svc = QuotaService(repo=SqlAlchemyQuotaRepo(sm), clock=FakeClock())
    views = {v.agent_type: v for v in await svc.latest()}
    assert set(views) == {"claude_code", "codex"}
    assert views["codex"].windows == [] and views["codex"].last_observed_at is None


async def test_latest_per_window_and_older_observations_never_win(sm) -> None:  # type: ignore[no-untyped-def]
    clock = FakeClock()
    svc = QuotaService(repo=SqlAlchemyQuotaRepo(sm), clock=clock)
    await svc.observe_agent_event(
        "claude_code",
        {
            "unifiedWindows": {
                "five_hour": {"utilization": 0.2, "resetsAt": _LATER},
                "seven_day": {"utilization": 0.5, "resetsAt": _LATER},
            }
        },
    )
    clock.current = NOW + timedelta(minutes=1)
    # A top-level-only event updates just its own window.
    await svc.observe_claude_event(
        {"rateLimitType": "five_hour", "utilization": 0.3, "resetsAt": _LATER}
    )
    clock.current = NOW - timedelta(minutes=5)  # a delayed, older report
    await svc.observe_statusline({"five_hour": {"used_percentage": 99, "resets_at": _LATER}})
    clock.current = NOW + timedelta(minutes=2)
    (claude,) = [v for v in await svc.latest() if v.agent_type == "claude_code"]
    windows = {w.key: w for w in claude.windows}
    assert windows["five_hour"].used_percent == 30.0
    assert windows["five_hour"].as_of == NOW + timedelta(minutes=1)
    assert windows["seven_day"].used_percent == 50.0
    assert [w.key for w in claude.windows] == ["five_hour", "seven_day"]


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="no fresh value shows no number",
)
async def test_a_window_past_its_reset_shows_no_number(sm) -> None:  # type: ignore[no-untyped-def]
    clock = FakeClock()
    svc = QuotaService(repo=SqlAlchemyQuotaRepo(sm), clock=clock)
    await svc.observe_codex_update(_codex_result(40))
    clock.current = NOW + timedelta(hours=4)
    (codex,) = [v for v in await svc.latest() if v.agent_type == "codex"]
    assert all(w.stale and w.used_percent is None for w in codex.windows)
    assert codex.last_observed_at == NOW


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="Codex is not read more often than every five minutes",
)
async def test_codex_reads_respect_the_five_minute_and_thirty_second_floors(sm) -> None:  # type: ignore[no-untyped-def]
    clock = FakeClock()
    reader = FakeCodexReader(_codex_result(10))
    svc = QuotaService(repo=SqlAlchemyQuotaRepo(sm), codex_reader=reader, clock=clock)

    assert (await svc.refresh_codex()).refreshed is True
    clock.current = NOW + timedelta(minutes=2)
    assert (await svc.refresh_codex()).reason == "too_soon"  # background: 5 min floor
    assert (await svc.refresh_codex(force=True)).refreshed is True  # manual may read
    clock.current += timedelta(seconds=10)
    assert (await svc.refresh_codex(force=True)).reason == "too_soon"  # 30 s floor
    clock.current += timedelta(minutes=6)
    reader.result = None  # not signed in with ChatGPT
    assert (await svc.refresh_codex()).reason == "no_subscription"
    assert reader.calls == 3
    none = QuotaService(repo=SqlAlchemyQuotaRepo(sm), clock=clock)
    assert (await none.refresh_codex(force=True)).reason == "codex_unavailable"
