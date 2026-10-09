"""ProviderAttentionSource: failing connections something runs on."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.attention import AttentionAction, Severity
from coffer.application.provider.attention import ProviderAttentionSource
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.health import HealthSource, HealthStatus, ProviderHealth
from coffer.domain.resource import Resource
from tests.unit.application._attention_fakes import FakeResources, resource

T0 = datetime(2026, 10, 9, tzinfo=UTC)


def _connection(uid: str, *, transcribe: bool = False, enabled: bool = True) -> Resource:
    cfg = ProviderConfig(
        protocol="openai",
        base_url=f"https://{uid}/v1",
        secret_ref=f"ref-{uid}",
        transcribe_default=transcribe,
    )
    return resource(
        uid, "provider", cfg.model_dump(mode="json"), title=f"{uid} title", enabled=enabled
    )


def _agent(uid: str, connection_uid: str | None) -> Resource:
    return resource(uid, "agent", {"type": "claude_code", "connection_uid": connection_uid})


class _Health:
    def __init__(self, verdicts: dict[str, ProviderHealth]) -> None:
        self.verdicts = verdicts

    async def all(self) -> dict[str, ProviderHealth]:
        return self.verdicts


def _verdict(status: HealthStatus, message: str = "") -> ProviderHealth:
    return ProviderHealth(status, T0 + timedelta(minutes=30), HealthSource.CHECK, message, since=T0)


def _source(rows: list[Resource], verdicts: dict[str, ProviderHealth]) -> ProviderAttentionSource:
    return ProviderAttentionSource(resources=FakeResources(rows), health=_Health(verdicts))


def test_the_source_belongs_to_no_feature() -> None:
    assert _source([], {}).feature is None


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a connection an agent runs on that fails is listed"
)
async def test_only_a_failing_connection_in_use_is_listed() -> None:
    rows = [_connection("a"), _connection("b"), _agent("cc", "a")]
    source = _source(
        rows,
        {
            "a": _verdict(HealthStatus.UNREACHABLE, "Connection error."),
            "b": _verdict(HealthStatus.KEY_REJECTED),
        },
    )
    [item] = await source.items()
    assert (item.kind, item.uid, item.title) == ("provider", "a", "a title")
    assert item.reason_code == "provider_unreachable"
    assert item.reason == "Its endpoint does not answer: Connection error."
    assert item.severity is Severity.ERROR
    assert item.since == T0
    assert item.action == AttentionAction(
        verb="check", method="POST", path="/api/v1/providers/a/check"
    )

    source = _source(rows, {"a": _verdict(HealthStatus.KEY_REJECTED)})
    [item] = await source.items()
    assert item.reason_code == "provider_key_rejected"
    assert item.action == AttentionAction(
        verb="replace_key", method="GET", path="/api/v1/providers/a"
    )


async def test_the_speech_to_text_connection_counts_as_in_use() -> None:
    rows = [_connection("s", transcribe=True)]
    [item] = await _source(rows, {"s": _verdict(HealthStatus.UNREACHABLE)}).items()
    assert item.uid == "s"
    assert item.reason == "Its endpoint does not answer."


async def test_a_switched_off_or_reachable_connection_is_not_listed() -> None:
    rows = [
        _connection("off", enabled=False),
        _connection("ok"),
        _agent("cc", "off"),
        _agent("cx", "ok"),
    ]
    verdicts = {
        "off": _verdict(HealthStatus.UNREACHABLE),
        "ok": _verdict(HealthStatus.REACHABLE),
    }
    assert await _source(rows, verdicts).items() == []
