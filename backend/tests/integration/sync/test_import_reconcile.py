"""Import gates + post-import hooks (spec 010 import reconciliation)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from pydantic import BaseModel

from coffer.application.audit_service import AuditService
from coffer.application.channel.kind import make_channel_kind
from coffer.application.resource_service import ResourceService
from coffer.application.sync.importer import SyncImporter
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import Kind, ResourceRef
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


def _default_kinds() -> dict[str, Kind]:
    return {"mcp_server": Kind(name="mcp_server", display_name="X", config_schema=_Cfg)}


def _channel_kinds() -> dict[str, Kind]:
    """A channel-like kind whose registration default is `{}` (dormant), not
    `None` — the shape that exposed the importer's hardcoded-None bug (Fix 1).

    Reuses the REAL `make_channel_kind().validate_scope_shape` (ADR-045
    review Fix 1) — not a re-implementation — so a doc carrying an invalid
    multi-machine channel scope quarantines here exactly as it would through
    production wiring, while still using the lightweight `_Cfg` schema (not
    `ChannelConfigModel`) so the hand-crafted YAML docs in this module don't
    need real channel_type/credential-ref fields.
    """
    return {
        "channel": Kind(
            name="channel",
            display_name="Channel",
            config_schema=_Cfg,
            scope_axes=("machine",),
            default_scope={},
            validate_scope_shape=make_channel_kind().validate_scope_shape,
        )
    }


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


async def _make(tmp_path: Path, *, gates=(), hooks=(), kinds=None):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "c.db"
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = session_maker(engine)
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds=kinds if kinds is not None else _default_kinds(),
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


_NO_SCOPE_KEY = object()  # sentinel: omit the "scope" key entirely (pre-v4 doc)


def _write_channel_doc(
    ws_root: Path,
    name: str,
    *,
    scope: object = _NO_SCOPE_KEY,
    value: str = "v1",
) -> None:
    """Hand-craft a `resources/channel/<name>.yaml` doc, with fine control over
    whether the "scope" key is present at all (simulating a pre-v4 peer's doc,
    which lacks the key entirely) vs. present-and-null vs. present-and-set."""
    target = ws_root / "resources" / "channel"
    target.mkdir(parents=True, exist_ok=True)
    lines = [
        "config:",
        f"  value: {value}",
        "description: null",
        "enabled: true",
        "kind: channel",
        f"name: {name}",
    ]
    if scope is not _NO_SCOPE_KEY:
        if scope is None:
            lines.append("scope: null")
        else:
            assert isinstance(scope, dict)
            lines.append("scope:")
            for k, v in scope.items():
                # Key quoted too: an unquoted `*` is a YAML alias indicator,
                # not a literal string, and would fail to parse as a scope
                # wildcard key (ADR-045 review Fix 1 tests below).
                lines.append(f"  '{k}': '{v}'")
    (target / f"{name}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


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


# ---------------------------------------------------------------------------
# Scope reconciliation (Task 13 review Fix 1): a channel's Kind.default_scope
# is `{}` (dormant), not None — the importer must never hardcode None as "the
# fresh-register scope", and must tell an absent "scope" key (pre-v4 peer, no
# opinion) apart from an explicit `scope: null` (an opinion: unscoped).
# ---------------------------------------------------------------------------


async def test_doc_without_scope_key_leaves_local_scope_untouched(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A pre-v4 doc (no "scope" key at all) imported over a locally-scoped
    channel must NOT reset it — the doc has no opinion on scope. Resetting it
    to None would flip the channel to active-everywhere, reintroducing the
    double-adapter race ADR-043 exists to prevent."""
    resources, _ws, importer = await _make(tmp_path, kinds=_channel_kinds())
    await resources.register("channel", "tg", {"value": "v1"}, "test", allow_lifecycle_kind=True)
    await resources.update_scope(ResourceRef("channel", "tg"), {"M-1": "*"}, actor="test")

    _write_channel_doc(tmp_path / "ws", "tg", scope=_NO_SCOPE_KEY)
    await importer.import_()

    got = await resources.get(ResourceRef("channel", "tg"))
    assert got.scope == {"M-1": "*"}


async def test_doc_with_explicit_null_scope_overrides_local_scope(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """An explicit `scope: null` IS an opinion (unscoped) — unlike the
    missing-key case above, it must win over the local value."""
    resources, _ws, importer = await _make(tmp_path, kinds=_channel_kinds())
    await resources.register("channel", "tg", {"value": "v1"}, "test", allow_lifecycle_kind=True)
    await resources.update_scope(ResourceRef("channel", "tg"), {"M-1": "*"}, actor="test")

    _write_channel_doc(tmp_path / "ws", "tg", scope=None)
    await importer.import_()

    got = await resources.get(ResourceRef("channel", "tg"))
    assert got.scope is None


async def test_fresh_register_applies_doc_scope_over_kind_default(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A resource that does not exist locally yet (register path) whose doc
    carries an explicit scope must end up with THAT scope, not the kind's
    registration default (`{}` for channel) — the importer must compare
    against the just-created row's actual scope, never a hardcoded None."""
    resources, _ws, importer = await _make(tmp_path, kinds=_channel_kinds())
    _write_channel_doc(tmp_path / "ws", "fresh", scope={"M-1": "*"})

    result = await importer.import_()

    assert result.quarantined_refs == []
    got = await resources.get(ResourceRef("channel", "fresh"))
    assert got.scope == {"M-1": "*"}


async def test_fresh_register_explicit_null_overrides_kind_dormant_default(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A fresh register whose doc has an explicit `scope: null` ends up
    unscoped (None) — the exporting machine had an explicit opinion that
    overrides the kind's own dormant registration default."""
    resources, _ws, importer = await _make(tmp_path, kinds=_channel_kinds())
    _write_channel_doc(tmp_path / "ws", "fresh", scope=None)

    result = await importer.import_()

    assert result.quarantined_refs == []
    got = await resources.get(ResourceRef("channel", "fresh"))
    assert got.scope is None


async def test_multi_entry_channel_scope_doc_quarantines(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A synced doc carrying a channel scope with two machine entries fails
    `Kind.validate_scope_shape` (ADR-045 review Fix 1: a channel's platform
    identity tolerates only ONE machine consumer, ADR-043) — `update_scope`
    raises `ScopeInvalidError`, a `CofferError` subclass, so the importer's
    broad `except CofferError` quarantines the whole doc exactly like any
    other gate failure. No importer change was needed for this — the generic
    quarantine path already covers it.

    For a FRESH register the row itself still gets created (the kind's own
    dormant `{}` default needs no shape validation) — only the doc's invalid
    scope write fails — so the row exists but stuck at that dormant default,
    never the requested (invalid) scope; the doc keeps retrying every run
    until it's fixed, same as any other quarantine."""
    resources, _ws, importer = await _make(tmp_path, kinds=_channel_kinds())
    _write_channel_doc(tmp_path / "ws", "fresh", scope={"M-1": "*", "M-2": "*"})

    result = await importer.import_()

    assert result.quarantined_refs == ["channel:fresh"]
    got = await resources.get(ResourceRef("channel", "fresh"))
    assert got.scope == {}


async def test_wildcard_key_channel_scope_doc_quarantines(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Same as above, via the `"*"` wildcard key instead of a second entry —
    both shapes would start the adapter on every machine at once."""
    resources, _ws, importer = await _make(tmp_path, kinds=_channel_kinds())
    _write_channel_doc(tmp_path / "ws", "fresh", scope={"*": "*"})

    result = await importer.import_()

    assert result.quarantined_refs == ["channel:fresh"]
    got = await resources.get(ResourceRef("channel", "fresh"))
    assert got.scope == {}
