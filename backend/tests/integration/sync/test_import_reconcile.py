"""Import gates + post-import hooks (spec 010 import reconciliation)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.importer import SyncImporter
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import (
    SqlAlchemyAuditRepo,
    SqlAlchemyResourceRepo,
)
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.infrastructure.sync.workspace import Workspace


class _Cfg(BaseModel):
    value: str = ""


class _NoKeyring:
    def get(self, ref: str) -> str | None:
        return None

    def set(self, ref: str, value: str) -> None:  # pragma: no cover
        pass

    def delete(self, ref: str) -> None:  # pragma: no cover
        pass


class _RejectMarkedGate:
    kind = "mcp_server"

    async def validate(self, config: Mapping[str, object], *, scope: dict | None = None) -> None:
        if config.get("value") == "not-installable-here":
            raise ConfigValidationError("machine-local precondition failed")


class _RecordingHook:
    kind = "mcp_server"

    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.rows_seen: list[str] = []
        self._fail = fail

    async def reconcile(self) -> list[str]:
        self.calls += 1
        return ["side-effect failed"] if self._fail else []


async def _make(tmp_path: Path, *, gates=(), hooks=()):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "c.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={"mcp_server": Kind(name="mcp_server", display_name="X", config_schema=_Cfg)},
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
    )
    master_key = MasterKeyManager(tmp_path / "master.key", _NoKeyring())
    master_key.resolve(allow_create=True)
    workspace = Workspace(tmp_path / "ws", trees=[])
    importer = SyncImporter(
        resources,
        CredentialSyncAdapter(db_path, master_key),
        workspace,
        import_gates=gates,
        post_import_hooks=hooks,
        home=None,
    )
    return resources, workspace, importer


def _write_doc(ws_root: Path, name: str, value: str) -> None:
    target = ws_root / "resources" / "mcp_server"
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{name}.yaml").write_text(
        f"config:\n  value: {value}\ndescription: null\nenabled: true\n"
        f"kind: mcp_server\nname: {name}\n",
        encoding="utf-8",
    )


@pytest.mark.acceptance(
    spec="010-sync", scenario="an agent not installed on this machine quarantines at import"
)
async def test_gate_failure_quarantines_and_retries(tmp_path) -> None:  # type: ignore[no-untyped-def]
    gate = _RejectMarkedGate()
    resources, _ws, importer = await _make(tmp_path, gates=(gate,))
    _write_doc(tmp_path / "ws", "blocked", "not-installable-here")
    _write_doc(tmp_path / "ws", "fine", "ok")

    result = await importer.import_()

    # The gated doc quarantines; the other imports; no row for the gated one.
    assert result.quarantined_refs == ["mcp_server:blocked"]
    names = {r.name for r in await resources.list()}
    assert names == {"fine"}

    # The machine-local precondition clears (simulate by changing the doc) —
    # the next run's import succeeds by itself.
    _write_doc(tmp_path / "ws", "blocked", "now-fine")
    result = await importer.import_()
    assert result.quarantined_refs == []
    assert {r.name for r in await resources.list()} == {"fine", "blocked"}


@pytest.mark.acceptance(
    spec="010-sync", scenario="imported config re-applies its side-effects on this machine"
)
async def test_hooks_run_after_rows_and_report_errors(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ok_hook = _RecordingHook()
    bad_hook = _RecordingHook(fail=True)
    _resources, _ws, importer = await _make(tmp_path, hooks=(ok_hook, bad_hook))
    _write_doc(tmp_path / "ws", "svc", "v1")

    result = await importer.import_()

    assert ok_hook.calls == 1
    assert result.errors == ["reconcile[mcp_server]: side-effect failed"]
    # Hook failures retry on every import (current-state reconciliation).
    result = await importer.import_()
    assert ok_hook.calls == 2
    assert result.errors == ["reconcile[mcp_server]: side-effect failed"]


class _RaisingHook:
    kind = "mcp_server"

    async def reconcile(self) -> list[str]:
        raise RuntimeError("hook blew up")


async def test_raising_hook_does_not_void_the_import(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A hook that RAISES (not just returns errors) must not discard the
    import result — rows already applied (review #291 finding 3)."""
    resources, _ws, importer = await _make(tmp_path, hooks=(_RaisingHook(),))
    _write_doc(tmp_path / "ws", "svc", "v1")

    result = await importer.import_()

    assert result.applied == 1
    assert {r.name for r in await resources.list()} == {"svc"}
    assert result.errors == ["reconcile[mcp_server]: hook blew up"]
