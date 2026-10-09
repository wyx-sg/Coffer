"""ProviderHealthService: who writes a connection's verdict, and when."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from coffer.application.provider import health as health_module
from coffer.application.provider.health import ProviderHealthService
from coffer.application.provider.ports import ModelList
from coffer.domain.errors import ResourceNotFound
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.health import HealthSource, HealthStatus, ProviderHealth
from coffer.domain.reconcile import Changed
from coffer.domain.resource import Resource
from coffer.domain.secret_errors import SecretBindingPending
from coffer.domain.usage.records import Outcome, UsageRecord, Wire
from tests.unit.application._attention_fakes import resource

T0 = datetime(2026, 10, 9, tzinfo=UTC)


def _connection(uid: str, *, url: str = "https://gw/v1", enabled: bool = True) -> Resource:
    cfg = ProviderConfig(protocol="openai", base_url=url, secret_ref=f"ref-{uid}")
    return resource(uid, "provider", cfg.model_dump(mode="json"), enabled=enabled)


class _Store:
    def __init__(self) -> None:
        self.rows: dict[str, ProviderHealth] = {}

    async def upsert(self, uid: str, health: ProviderHealth) -> None:
        self.rows[uid] = health

    async def get(self, uid: str) -> ProviderHealth | None:
        return self.rows.get(uid)

    async def list_all(self) -> dict[str, ProviderHealth]:
        return dict(self.rows)

    async def forget(self, uid: str) -> None:
        self.rows.pop(uid, None)


class _Connections:
    def __init__(self, *rows: Resource) -> None:
        self.rows = {r.uid: r for r in rows}

    async def list(self) -> list[Resource]:
        return list(self.rows.values())

    async def get(self, uid: str) -> Resource:
        if uid not in self.rows:
            raise ResourceNotFound(f"no {uid}")
        return self.rows[uid]


class _Endpoints:
    """What each base URL answers a listing with; records who was called."""

    def __init__(self, answers: dict[str, ModelList]) -> None:
        self.answers = answers
        self.called: list[str | None] = []

    async def __call__(self, protocol: str, base_url: str | None, ref: str | None) -> ModelList:
        self.called.append(base_url)
        return self.answers[base_url or ""]


OK = ModelList(models=[])
REFUSED = ModelList(models=[], message="Error code: 401 - invalid api key", reachable=False)
DOWN = ModelList(models=[], message="Connection error.", reachable=False)


def _service(
    connections: _Connections,
    endpoints: _Endpoints,
    *,
    pending: set[str] = frozenset(),  # type: ignore[assignment]
    store: _Store | None = None,
    enabled: bool = True,
    now: datetime = T0,
) -> tuple[ProviderHealthService, _Store, list[str]]:
    async def authorize(row: Resource, _cfg: ProviderConfig) -> None:
        if row.uid in pending:
            raise SecretBindingPending(["a1"], ["waits"])

    kept = store or _Store()
    svc = ProviderHealthService(
        store=kept,
        connections=connections,
        list_models=endpoints,
        authorize=authorize,
        is_enabled=lambda: enabled,
        clock=lambda: now,
    )
    moved: list[str] = []
    svc.on_change = moved.append
    return svc, kept, moved


def _usage(status: int | None, outcome: Outcome, at: datetime, uid: str = "c1") -> UsageRecord:
    return UsageRecord(
        dedupe_key=f"{uid}-{at.isoformat()}",
        attempt_id="a",
        started_at=at,
        connection_uid=uid,
        wire=Wire.OPENAI,
        endpoint="/v1/responses",
        status=status,
        outcome=outcome,
    )


async def test_the_sweep_checks_every_enabled_connection() -> None:
    connections = _Connections(
        _connection("c1", url="https://a/v1"),
        _connection("c2", url="https://b/v1"),
        _connection("c3", url="https://c/v1", enabled=False),
    )
    endpoints = _Endpoints({"https://a/v1": REFUSED, "https://b/v1": OK})
    svc, store, moved = _service(connections, endpoints)
    await svc.check_all()
    assert endpoints.called == ["https://a/v1", "https://b/v1"]
    assert store.rows["c1"].status is HealthStatus.KEY_REJECTED
    assert store.rows["c2"].status is HealthStatus.REACHABLE
    assert sorted(moved) == ["c1", "c2"]


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a key waiting for approval is not sent by a check"
)
async def test_a_key_waiting_for_approval_is_not_sent() -> None:
    endpoints = _Endpoints({"https://gw/v1": OK})
    svc, store, _ = _service(_Connections(_connection("c1")), endpoints, pending={"c1"})
    await svc.check_all()
    assert await svc.check("c1") is None
    assert endpoints.called == []
    assert store.rows == {}


@pytest.mark.acceptance(
    spec="provider-switching", scenario="an agent's refused request marks its connection"
)
async def test_a_refused_request_marks_the_connection_and_older_records_do_not_undo_it() -> None:
    endpoints = _Endpoints({"https://gw/v1": OK})
    svc, store, moved = _service(_Connections(_connection("c1")), endpoints)
    await svc.check("c1")
    assert store.rows["c1"].status is HealthStatus.REACHABLE

    later = T0 + timedelta(minutes=1)
    await svc.observe([_usage(401, Outcome.UPSTREAM_ERROR, later)])
    assert store.rows["c1"].status is HealthStatus.KEY_REJECTED
    assert store.rows["c1"].source is HealthSource.REQUEST
    assert moved == ["c1", "c1"]

    # A file ingested late, from before that verdict, changes nothing.
    await svc.observe([_usage(200, Outcome.COMPLETED, T0 + timedelta(seconds=30))])
    assert store.rows["c1"].status is HealthStatus.KEY_REJECTED


async def test_since_stays_while_the_status_does() -> None:
    endpoints = _Endpoints({"https://gw/v1": DOWN})
    svc, store, moved = _service(_Connections(_connection("c1")), endpoints)
    await svc.check("c1")
    svc._clock = lambda: T0 + timedelta(minutes=30)
    await svc.check("c1")
    kept = store.rows["c1"]
    assert kept.checked_at == T0 + timedelta(minutes=30)
    assert kept.started == T0
    assert moved == ["c1"]  # the second check moved nothing


async def test_nothing_is_checked_or_kept_while_models_is_off() -> None:
    endpoints = _Endpoints({"https://gw/v1": DOWN})
    svc, store, _ = _service(_Connections(_connection("c1")), endpoints, enabled=False)
    await svc.check_all()
    assert await svc.check("c1") is None
    await svc.observe([_usage(401, Outcome.UPSTREAM_ERROR, T0)])
    assert endpoints.called == []
    assert store.rows == {}


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a replaced key is checked again at once"
)
async def test_an_edited_connection_is_checked_again_and_a_deleted_one_forgotten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_module, "RECHECK_SETTLE_SECONDS", 0)
    endpoints = _Endpoints({"https://gw/v1": REFUSED})
    svc, store, _ = _service(_Connections(_connection("c1")), endpoints)
    await svc.check("c1")
    assert store.rows["c1"].status is HealthStatus.KEY_REJECTED

    endpoints.answers["https://gw/v1"] = OK  # the key was replaced
    svc.on_changed(Changed(kind="provider", uid="c1"))
    svc.on_changed(Changed(kind="agent", uid="c1"))  # another kind is not a provider edit
    await asyncio.sleep(0.05)
    assert store.rows["c1"].status is HealthStatus.REACHABLE
    assert endpoints.called == ["https://gw/v1", "https://gw/v1"]

    svc.on_changed(Changed(kind="provider", uid="c1", op="delete"))
    await asyncio.sleep(0.05)
    assert store.rows == {}


async def test_no_background_check_runs_when_pinned_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_module, "RECHECK_SETTLE_SECONDS", 0)
    endpoints = _Endpoints({"https://gw/v1": OK})
    svc = ProviderHealthService(
        store=_Store(),
        connections=_Connections(_connection("c1")),
        list_models=endpoints,
        authorize=lambda _r, _c: asyncio.sleep(0),
        background=False,
    )
    await svc.run(interval=0.01)
    svc.on_changed(Changed(kind="provider", uid="c1"))
    await asyncio.sleep(0.05)
    assert endpoints.called == []
