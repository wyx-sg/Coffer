"""The health verdict vocabulary: a listing's answer and a relayed request's outcome."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.domain.provider.health import (
    MESSAGE_MAX,
    HealthSource,
    HealthStatus,
    from_listing,
    from_request,
    latest_per_connection,
)
from coffer.domain.usage.records import Outcome, UsageRecord, Wire

T0 = datetime(2026, 10, 9, tzinfo=UTC)


def _record(
    *, status: int | None, outcome: Outcome, at: datetime = T0, uid: str | None = "c1"
) -> UsageRecord:
    return UsageRecord(
        dedupe_key=f"k-{at.isoformat()}-{status}",
        attempt_id="a",
        started_at=at,
        connection_uid=uid,
        wire=Wire.ANTHROPIC,
        endpoint="/v1/messages",
        status=status,
        outcome=outcome,
    )


def test_an_answered_listing_is_reachable_even_when_empty() -> None:
    health = from_listing(reachable=True, message="the endpoint listed no models", at=T0)
    assert health.status is HealthStatus.REACHABLE
    assert health.message == ""
    assert not health.failing


@pytest.mark.parametrize(
    "message",
    [
        "Error code: 401 - {'error': 'invalid api key'}",
        "Client error '403 Forbidden' for url",
        "Incorrect API key provided: invalid_api_key",
        "authentication_error",
    ],
)
def test_a_refused_listing_is_key_rejected(message: str) -> None:
    assert from_listing(reachable=False, message=message, at=T0).status is (
        HealthStatus.KEY_REJECTED
    )


def test_any_other_failed_listing_is_unreachable_with_its_reason_cut() -> None:
    health = from_listing(reachable=False, message="Connection error. " * 40, at=T0)
    assert health.status is HealthStatus.UNREACHABLE
    assert len(health.message) == MESSAGE_MAX
    assert health.source is HealthSource.CHECK


@pytest.mark.parametrize(
    ("status", "outcome", "expected"),
    [
        (401, Outcome.UPSTREAM_ERROR, HealthStatus.KEY_REJECTED),
        (403, Outcome.UPSTREAM_ERROR, HealthStatus.KEY_REJECTED),
        (None, Outcome.CONNECT_ERROR, HealthStatus.UNREACHABLE),
        (200, Outcome.COMPLETED, HealthStatus.REACHABLE),
    ],
)
def test_a_request_that_says_something_about_its_connection(
    status: int | None, outcome: Outcome, expected: HealthStatus
) -> None:
    health = from_request(_record(status=status, outcome=outcome))
    assert health is not None
    assert health.status is expected
    assert health.source is HealthSource.REQUEST


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (429, Outcome.UPSTREAM_ERROR),
        (529, Outcome.UPSTREAM_ERROR),
        (200, Outcome.TRUNCATED),
        (200, Outcome.CLIENT_CANCEL),
        (200, Outcome.ERROR_EVENT),
    ],
)
def test_a_request_that_says_nothing_changes_nothing(status: int, outcome: Outcome) -> None:
    assert from_request(_record(status=status, outcome=outcome)) is None


def test_a_request_with_no_connection_says_nothing() -> None:
    assert from_request(_record(status=401, outcome=Outcome.UPSTREAM_ERROR, uid=None)) is None


def test_the_newest_request_per_connection_wins() -> None:
    later = T0 + timedelta(seconds=5)
    verdicts = latest_per_connection(
        [
            _record(status=200, outcome=Outcome.COMPLETED, at=later),
            _record(status=401, outcome=Outcome.UPSTREAM_ERROR, at=T0),
            _record(status=429, outcome=Outcome.UPSTREAM_ERROR, at=later, uid="c2"),
        ]
    )
    assert set(verdicts) == {"c1"}
    assert verdicts["c1"].status is HealthStatus.REACHABLE
