"""No upstream child outlives the registration it was spawned for (MCP-011).

Deleting an ``mcp_server`` runs the kind's ``on_delete`` hook BEFORE the row is
removed, and the hook awaits each live session's eviction in turn — a stdio
close waits for its child to exit, so the hook can be busy for a second or more.
A listing or call landing in that window used to read the still-present row and
spawn a fresh child that nothing would ever evict: its supervisor had already
been visited (or did not exist yet). Ending a session while one of its spawns
was in flight left the same kind of orphan.

Each race is pinned with events rather than sleeps, and every assertion is on
the real child processes of this test, by pid.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import psutil
import pytest

from coffer.application.audit_service import AuditService
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.mcp.supervisor import SubprocessSupervisor, UpstreamHealth
from coffer.application.resource_service import ResourceService
from coffer.application.secret.resolver import SecretResolver
from coffer.domain.errors import UpstreamUnavailable
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.infrastructure.secret.keyring_adapter import KeyringAdapter
from tests.fixtures.keyring import install_in_memory_keyring
from tests.support.vault_stores import make_resource_repo

_FAKE = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


def _config() -> dict[str, Any]:
    return {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE), "--scenario", "basic", "--tools", "read_file"],
        }
    }


def _live_children() -> set[int]:
    """PIDs of this test's running (non-zombie) fake upstream children."""
    live: set[int] = set()
    for child in psutil.Process().children(recursive=True):
        with contextlib.suppress(psutil.Error):
            if child.status() == psutil.STATUS_ZOMBIE:
                continue
            if str(_FAKE) in " ".join(child.cmdline()):
                live.add(child.pid)
    return live


class _BusyEviction:
    """Stands in for another session whose eviction is still closing a child.

    Registered after the real supervisor, its ``evict`` is the moment the hook
    has already evicted the real one and the row still exists. It opens that
    window to the test and holds it until the test says the concurrent work is
    done — the interleaving the hook's sequential, awaited closes allow.
    """

    def __init__(self) -> None:
        self.opened = asyncio.Event()
        self.close = asyncio.Event()

    async def evict(self, name: str) -> None:
        self.opened.set()
        await self.close.wait()


async def _services(tmp_path: Path, supervisor_for: dict[str, Any]) -> tuple[ResourceService, Any]:
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    rsvc = ResourceService(
        kinds={"mcp_server": make_mcp_kind(supervisor_for)},
        repo=make_resource_repo(),
        audit=AuditService(SqlAlchemyAuditRepo(session_maker(engine))),
    )
    return rsvc, engine


def _supervisor(rsvc: ResourceService, factory: Any = build_upstream) -> SubprocessSupervisor:
    return SubprocessSupervisor(
        upstream_factory=factory,
        resource_service=rsvc,
        secret_resolver=SecretResolver(KeyringAdapter()),
        retry_delays=(),
    )


async def _delete_while(
    rsvc: ResourceService,
    uid: str,
    window: _BusyEviction,
    during: Callable[[], Awaitable[None]],
) -> None:
    """Delete ``uid`` and run ``during`` inside the hook's eviction window."""

    async def concurrent() -> None:
        await window.opened.wait()
        try:
            with contextlib.suppress(UpstreamUnavailable):
                await during()
        finally:
            window.close.set()

    task = asyncio.create_task(concurrent())
    await rsvc.delete(uid, actor="test")
    await task


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a listing during a delete does not revive the deleted server"
)
@pytest.mark.asyncio
async def test_a_spawn_inside_the_delete_window_does_not_survive_the_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session already visited by the hook spawns again before the row goes.

    Its spawn reads the generation AFTER the eviction bumped it and the row
    BEFORE the delete removes it, so nothing invalidates it — the child used to
    stay cached, parented by the daemon, for a server that no longer exists.
    """
    install_in_memory_keyring(monkeypatch)
    pre = _live_children()
    window = _BusyEviction()
    supervisor_for: dict[str, Any] = {}
    rsvc, engine = await _services(tmp_path, supervisor_for)
    sup = _supervisor(rsvc)
    supervisor_for["session-a"] = sup
    supervisor_for["session-b"] = window
    try:
        fs = await rsvc.register(kind="mcp_server", name="fs", config=_config(), actor="test")
        await sup.get_or_spawn("fs")
        (first,) = _live_children() - pre

        async def respawn() -> None:
            await sup.get_or_spawn("fs")

        await _delete_while(rsvc, fs.uid, window, respawn)

        assert first not in _live_children()
        assert _live_children() - pre == set(), "a child outlived its deleted server"
        assert sup.health("fs") != UpstreamHealth.HEALTHY
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_session_started_inside_the_delete_window_cannot_spawn_the_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session created while the hook runs is not in the list the hook walks.

    The hook walks a snapshot of the registry, so a supervisor registered
    mid-delete is never evicted; its spawn read the still-present row and kept
    the child for the life of the session.
    """
    install_in_memory_keyring(monkeypatch)
    pre = _live_children()
    window = _BusyEviction()
    supervisor_for: dict[str, Any] = {"session-b": window}
    rsvc, engine = await _services(tmp_path, supervisor_for)
    late = _supervisor(rsvc)
    try:
        fs = await rsvc.register(kind="mcp_server", name="fs", config=_config(), actor="test")

        async def new_session_lists() -> None:
            supervisor_for["session-late"] = late
            await late.get_or_spawn("fs")

        await _delete_while(rsvc, fs.uid, window, new_session_lists)

        assert _live_children() - pre == set(), "a child outlived its deleted server"
        assert late.health("fs") != UpstreamHealth.HEALTHY
    finally:
        await late.dispose()
        await engine.dispose()


def _held_after_start(started: asyncio.Event, release: asyncio.Event) -> Any:
    """A real factory whose connection, once its child is up, waits for a word.

    That holds a finished spawn between ``spawn_and_initialize`` and the
    supervisor caching it — the moment something else can end its reason to
    exist.
    """

    def factory(*args: Any) -> Any:
        conn = build_upstream(*args)
        start = conn.spawn_and_initialize

        async def held() -> None:
            await start()
            started.set()
            await release.wait()

        conn.spawn_and_initialize = held  # type: ignore[method-assign]
        return conn

    return factory


@pytest.mark.asyncio
async def test_a_spawn_that_read_the_row_before_the_delete_is_closed_when_it_lands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The in-flight case the generation counter already covers, kept pinned."""
    install_in_memory_keyring(monkeypatch)
    pre = _live_children()
    started, release = asyncio.Event(), asyncio.Event()
    supervisor_for: dict[str, Any] = {}
    rsvc, engine = await _services(tmp_path, supervisor_for)
    sup = _supervisor(rsvc, _held_after_start(started, release))
    supervisor_for["session-a"] = sup
    try:
        fs = await rsvc.register(kind="mcp_server", name="fs", config=_config(), actor="test")
        spawn = asyncio.create_task(sup.get_or_spawn("fs"))
        await started.wait()
        assert len(_live_children() - pre) == 1

        await rsvc.delete(fs.uid, actor="test")
        release.set()
        with pytest.raises(UpstreamUnavailable):
            await spawn

        assert _live_children() - pre == set(), "a child outlived its deleted server"
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="ending a session closes a spawn still in flight"
)
@pytest.mark.asyncio
async def test_ending_a_session_closes_a_spawn_still_in_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``dispose`` used to clear its entries and leave a spawn in flight to
    cache its child on an entry nobody held any more — a child that no delete,
    disable or session end could reach again."""
    install_in_memory_keyring(monkeypatch)
    pre = _live_children()
    started, release = asyncio.Event(), asyncio.Event()
    rsvc, engine = await _services(tmp_path, {})
    sup = _supervisor(rsvc, _held_after_start(started, release))
    try:
        await rsvc.register(kind="mcp_server", name="fs", config=_config(), actor="test")
        spawn = asyncio.create_task(sup.get_or_spawn("fs"))
        await started.wait()

        await sup.dispose()
        release.set()
        with pytest.raises(UpstreamUnavailable):
            await spawn

        assert _live_children() - pre == set(), "a child outlived its session"
        with pytest.raises(UpstreamUnavailable):
            await sup.get_or_spawn("fs")
        assert _live_children() - pre == set(), "a disposed supervisor spawned again"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_evicted_start_is_not_retried_or_backed_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evicted while starting is the caller's answer, not the server failing:
    the ladder used to spawn it again after the delete and then put its name in
    backoff, so a server re-added under that name was refused for a minute."""
    install_in_memory_keyring(monkeypatch)
    pre = _live_children()
    started, release = asyncio.Event(), asyncio.Event()
    built: list[object] = []
    held = _held_after_start(started, release)

    def counting(*args: Any) -> Any:
        built.append(args)
        return held(*args)

    rsvc, engine = await _services(tmp_path, {})
    sup = SubprocessSupervisor(
        upstream_factory=counting,
        resource_service=rsvc,
        secret_resolver=SecretResolver(KeyringAdapter()),
        retry_delays=(0.0, 0.0),
    )
    try:
        await rsvc.register(kind="mcp_server", name="fs", config=_config(), actor="test")
        spawn = asyncio.create_task(sup.get_or_spawn("fs"))
        await started.wait()
        await sup.evict("fs")
        release.set()
        with pytest.raises(UpstreamUnavailable):
            await spawn

        assert len(built) == 1, "an evicted start was retried"
        assert sup.failures.get("fs") is None, "an evicted start was recorded as a failure"
        assert _live_children() - pre == set()
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_server_whose_delete_did_not_complete_can_spawn_again_after_an_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The hook retires the uid before the row goes; if the delete then fails
    the server is still registered, and the next edit lifts the retirement."""
    install_in_memory_keyring(monkeypatch)
    supervisor_for: dict[str, Any] = {}
    rsvc, engine = await _services(tmp_path, supervisor_for)
    sup = _supervisor(rsvc)
    supervisor_for["session-a"] = sup
    try:
        fs = await rsvc.register(kind="mcp_server", name="fs", config=_config(), actor="test")
        kind = rsvc._require_kind("mcp_server")
        assert kind.on_delete is not None
        await kind.on_delete(fs)  # type: ignore[misc]  # the hook ran; the removal did not

        with pytest.raises(UpstreamUnavailable, match="being deleted"):
            await sup.get_or_spawn("fs")

        await rsvc.update_config(fs.uid, _config(), actor="test")
        await sup.get_or_spawn("fs")
        assert sup.health("fs") == UpstreamHealth.HEALTHY
    finally:
        await sup.dispose()
        await engine.dispose()
