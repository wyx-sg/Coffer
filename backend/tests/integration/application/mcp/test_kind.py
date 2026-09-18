"""TEST-015 — make_mcp_kind.on_delete evicts active supervisor sessions.

When the user deletes an MCP server resource, every session that has a
live subprocess for that name must lose it so the next call doesn't hit a
stale connection.  This wires a real ResourceService + a fake supervisor
and asserts evict() lands.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from datetime import UTC, datetime
from pathlib import Path

import psutil
import pytest

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.mcp.kind import make_mcp_kind
from coffer.application.mcp.supervisor import SubprocessSupervisor, UpstreamHealth
from coffer.application.resource_service import ResourceService
from coffer.domain.resource import Resource
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.mcp.factory import build_upstream
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from tests.fixtures.keyring import install_in_memory_keyring

_FAKE = Path(__file__).resolve().parents[3] / "fixtures" / "fake_mcp_server.py"


def _stdio_config(*tools: str) -> dict:  # type: ignore[type-arg]
    return {
        "transport": {
            "type": "stdio",
            "command": sys.executable,
            "args": [str(_FAKE), "--scenario", "basic", "--tools", *tools],
        }
    }


async def _services(tmp_path: Path, supervisor_for: dict[str, object]):  # type: ignore[no-untyped-def]
    """A ResourceService whose mcp_server Kind carries the production hooks.

    ``supervisor_for`` is handed to ``make_mcp_kind`` while still empty and
    filled by the caller afterwards — the registry is captured by closure, which
    is exactly how the composition root registers a session's supervisor after
    the Kind already exists.
    """
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    rsvc = ResourceService(
        kinds={"mcp_server": make_mcp_kind(supervisor_for)},  # type: ignore[arg-type]
        repo=SqlAlchemyResourceRepo(sm),
        audit=AuditService(SqlAlchemyAuditRepo(sm)),
    )
    return rsvc, engine


def _resource(name: str) -> Resource:
    """A stand-in row for the hook, which is handed the resource itself now
    rather than an identifier to look it up with. The hook evicts by NAME —
    the key a session's live connections are held under — while the identity it
    carries is the uid."""
    now = datetime.now(tz=UTC)
    return Resource(
        id=1,
        uid="aa11bb22cc33dd44ee55ff6677889900",
        kind="mcp_server",
        name=name,
        description=None,
        config={},
        enabled=True,
        created_at=now,
        updated_at=now,
    )


class _Boom:
    """A supervisor whose eviction fails — a fault in Coffer, since the real
    ``evict`` suppresses everything a live connection can legitimately do."""

    async def evict(self, name: str) -> None:
        raise RuntimeError("boom")


class _RecordingSupervisor:
    """Captures every evict() call so we can assert the delete hook fired."""

    def __init__(self) -> None:
        self.evicted: list[str] = []

    async def evict(self, name: str) -> None:
        self.evicted.append(name)


@pytest.mark.asyncio
async def test_delete_evicts_active_supervisor_sessions(tmp_path: Path) -> None:
    """Deleting an mcp_server resource must trigger on_delete, which
    schedules an async evict against every registered supervisor.
    """
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    repo = SqlAlchemyResourceRepo(sm)
    audit = AuditService(SqlAlchemyAuditRepo(sm))

    # Wire a real Kind whose on_delete is the production hook.
    sup_a = _RecordingSupervisor()
    sup_b = _RecordingSupervisor()
    supervisor_for: dict[str, object] = {"session-a": sup_a, "session-b": sup_b}
    mcp_kind = make_mcp_kind(supervisor_for)  # type: ignore[arg-type]

    rsvc = ResourceService(
        kinds={"mcp_server": mcp_kind},
        repo=repo,
        audit=audit,
    )

    await rsvc.register(
        kind="mcp_server",
        name="fs",
        config={
            "transport": {
                "type": "stdio",
                "command": "/bin/true",
                "args": [],
            }
        },
        actor="test",
    )

    # Delete the resource — CODE-033: the kind hook is now an async hook that
    # ResourceService.delete AWAITS before removing the row, so eviction is
    # complete the instant delete() returns (no fire-and-forget polling).
    fs = await rsvc.get_by_name("mcp_server", "fs")
    await rsvc.delete(fs.uid, actor="test")

    assert sup_a.evicted == ["fs"], f"session-a never received evict: {sup_a.evicted}"
    assert sup_b.evicted == ["fs"], f"session-b never received evict: {sup_b.evicted}"

    await engine.dispose()


@pytest.mark.asyncio
async def test_on_delete_awaitable_and_suppresses_supervisor_errors() -> None:
    """CODE-033: on_delete is an awaitable coroutine; awaiting it evicts every
    registered supervisor, and a single supervisor whose evict() raises is
    suppressed so it can't abort the others or the deletion.
    """

    good = _RecordingSupervisor()
    supervisor_for: dict[str, object] = {"bad": _Boom(), "good": good}
    mcp_kind = make_mcp_kind(supervisor_for)  # type: ignore[arg-type]

    assert mcp_kind.on_delete is not None
    result = mcp_kind.on_delete(_resource("fs"))
    assert asyncio.iscoroutine(result), "on_delete must be an awaitable async hook"
    await result  # must not raise despite the failing supervisor

    assert good.evicted == ["fs"], "a failing supervisor must not block eviction of the rest"


def test_validate_name_rejects_double_underscore() -> None:
    """CODE-030: mcp_server names may not contain '__' (reserved separator)."""
    mcp_kind = make_mcp_kind({})  # type: ignore[arg-type]
    assert mcp_kind.validate_name is not None
    mcp_kind.validate_name("ok_name")  # single underscore is fine
    mcp_kind.validate_name("dotted.name-ok")
    with pytest.raises(ValueError, match="__"):
        mcp_kind.validate_name("my__server")


# --------------------------------------------------------------------------- #
# on_rename — the name a live connection is held under changes                 #
# --------------------------------------------------------------------------- #


def _live_fake_servers() -> set[int]:
    """PIDs of running ``fake_mcp_server`` children of this test process.

    Zombies are excluded: a just-terminated child can sit unreaped for a moment
    and ``is_running()`` still answers True for it, which would make "the old
    subprocess is gone" flaky in exactly the direction that hides the bug.
    """
    live: set[int] = set()
    for child in psutil.Process().children(recursive=True):
        with contextlib.suppress(psutil.Error):
            if child.status() == psutil.STATUS_ZOMBIE:
                continue
            if str(_FAKE) in " ".join(child.cmdline()):
                live.add(child.pid)
    return live


@pytest.mark.asyncio
async def test_rename_leaves_one_reachable_upstream_and_strands_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The defect this hook exists for, end to end with a real subprocess.

    A supervisor holds its live connections under the server's NAME. Renaming
    the row used to leave that entry addressed by a name nothing would ask for
    again — its subprocess alive, unreachable, and duplicated the moment the
    next call came in under the new name. After the rename there must be exactly
    one fake server running, it must answer under the new name, and the process
    that was serving the old one must be gone.
    """
    install_in_memory_keyring(monkeypatch)
    pre_existing = _live_fake_servers()

    supervisor_for: dict[str, object] = {}
    rsvc, engine = await _services(tmp_path, supervisor_for)

    sup = SubprocessSupervisor(
        upstream_factory=build_upstream,
        resource_service=rsvc,
        credential_resolver=CredentialResolver(KeyringAdapter()),
    )
    supervisor_for["session-1"] = sup
    try:
        await rsvc.register(
            kind="mcp_server",
            name="fs",
            config=_stdio_config("read_file"),
            actor="test",
        )
        conn = await sup.get_or_spawn("fs")
        assert {t.name for t in (await conn.request("tools/list", {})).tools} == {"read_file"}
        spawned = _live_fake_servers() - pre_existing
        assert len(spawned) == 1, f"expected one upstream for 'fs', got {spawned}"
        (old_pid,) = spawned

        before = await rsvc.get_by_name("mcp_server", "fs")
        await rsvc.rename(before.uid, "files", actor="test")

        # The old key no longer holds a connection...
        assert sup.health("fs") == UpstreamHealth.UNHEALTHY
        # ...and the process it held is gone, not merely unreferenced.
        assert old_pid not in _live_fake_servers()

        # The server is fully reachable under its new label, on one process.
        renamed = await sup.get_or_spawn("files")
        assert {t.name for t in (await renamed.request("tools/list", {})).tools} == {"read_file"}
        now_live = _live_fake_servers() - pre_existing
        assert len(now_live) == 1, f"a rename must not duplicate the upstream, got {now_live}"
        assert old_pid not in now_live
    finally:
        await sup.dispose()
        await engine.dispose()


@pytest.mark.asyncio
async def test_rename_evicts_every_registered_session(tmp_path: Path) -> None:
    """Every session holds its own supervisor, so every one of them is carrying
    a connection under the outgoing name."""
    sup_a, sup_b = _RecordingSupervisor(), _RecordingSupervisor()
    supervisor_for: dict[str, object] = {"a": sup_a, "b": sup_b}
    rsvc, engine = await _services(tmp_path, supervisor_for)
    try:
        await rsvc.register(
            kind="mcp_server", name="fs", config=_stdio_config("read_file"), actor="test"
        )
        before = await rsvc.get_by_name("mcp_server", "fs")

        renamed = await rsvc.rename(before.uid, "files", actor="test")

        assert renamed.name == "files"
        assert renamed.uid == before.uid, "a rename changes the label, never the identity"
        # Evicted under the OLD name — the only key those connections answer to.
        assert sup_a.evicted == ["fs"]
        assert sup_b.evicted == ["fs"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_failed_eviction_aborts_the_rename(tmp_path: Path) -> None:
    """Unlike on_delete, this hook can refuse — and does.

    Renaming on top of a connection that could not be released would leave a
    live subprocess addressed by a name the row no longer carries. Keeping the
    old name is what keeps it reachable, so the row must not move. The healthy
    supervisor is still attempted first, because eviction costs nothing to redo:
    its session simply respawns on its next call, under the name it already had.
    """
    good = _RecordingSupervisor()
    supervisor_for: dict[str, object] = {"good": good, "bad": _Boom()}
    rsvc, engine = await _services(tmp_path, supervisor_for)
    try:
        await rsvc.register(
            kind="mcp_server", name="fs", config=_stdio_config("read_file"), actor="test"
        )
        before = await rsvc.get_by_name("mcp_server", "fs")

        with pytest.raises(RuntimeError, match="boom"):
            await rsvc.rename(before.uid, "files", actor="test")

        still = await rsvc.get(before.uid)
        assert still.name == "fs", "the row must not move while a connection is unreleased"
        assert await rsvc.find_by_name("mcp_server", "files") is None
        assert good.evicted == ["fs"], "the reachable sessions are still attempted"
    finally:
        await engine.dispose()
