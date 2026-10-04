"""Writing ciphertext, the machine-local settings and the derived tables out
of the old tables (plan q9 §3 step 3; D10, D11).

- **Ciphertext** goes to ``vault/secret/<ref>.enc`` (machine-local refs to
  ``local/secret/``) exactly as the secret store files a token it
  encrypted itself: the token, a newline, ``0600`` in ``0700`` directories.
  It is copied, never decrypted, so the upgrade needs no key. When this
  machine first stored each ref goes into the store's ``times.json``, and
  when it was last used here (revision 0135's ``last_used_at``) into its
  ``last-used.json``.
- **The secret boundary's** bindings, approvals and switches go through the
  boundary store itself.
- **Retention**, **skill source status** and **the sync remote** go to their
  JSON files under ``local/``; the old convergence pointer and held paths are
  not carried — the remote is rebuilt from the first migrated machine, so
  there is nothing for them to point at.
- **Derived tables** (capability seen-times, health, skill deliveries) are
  copied into ``derived/derived.db`` rather than left to be rebuilt: an
  empty seen-times table would make every capability "new" at the next
  connect, and an empty delivery table would lose where each delivered copy
  is, so it could not be reclaimed.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import os
import sqlite3
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

from coffer.domain.secrets import SecretApproval, SecretBinding
from coffer.domain.skill.source_status import SourceStatus
from coffer.domain.sync.remote import SyncRemote, SyncRemoteInvalid
from coffer.domain.vault.layout import SECRET
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.persistence.derived_db import (
    DerivedBase,
    derived_db_path,
    prepare_derived_db,
)
from coffer.infrastructure.persistence.retention_repo import retention_path
from coffer.infrastructure.secret.boundary_store import FileBoundaryStore
from coffer.infrastructure.secret.encrypted_store import _make_dirs as secret_dirs
from coffer.infrastructure.secret.ref_paths import is_local_ref, ref_to_relpath
from coffer.infrastructure.skill.source_status_repo import SkillSourceStatusRepo
from coffer.infrastructure.sync.local_state import JsonRemoteStore
from coffer.infrastructure.vault.atomic import atomic_write
from coffer.infrastructure.vault.home import local_root, vault_root
from coffer.infrastructure.vault.json_store import JsonStore
from coffer.infrastructure.vault.migration.export_vault import when
from coffer.infrastructure.vault.migration.legacy_db import LegacyState
from coffer.infrastructure.vault.migration.staging import LayoutCommit

_FILE_MODE = 0o600


def _iso(raw: Any) -> str | None:
    return when(raw).isoformat() if raw is not None else None


def write_secrets(txn: LayoutCommit, home: Path, state: LegacyState) -> int:
    """Every ref's ciphertext file, and when this machine first stored and last used it."""
    times: dict[str, str] = {}
    used: dict[str, str] = {}
    carried = 0
    for row in state.secrets:
        ref = str(row["ref"])
        try:
            rel = ref_to_relpath(ref)
        except ValueError:
            state.skipped.append(f"secret {ref!r}: not a ref this build can file")
            continue
        token = bytes(row["ciphertext"]).strip() + b"\n"
        if is_local_ref(ref):
            base = local_root(home) / SECRET
            secret_dirs((base / rel).parent, stop_at=local_root(home))
            atomic_write(base / rel, token, mode=_FILE_MODE)
        else:
            root = vault_root(home)
            secret_dirs((root / SECRET / rel).parent, stop_at=root)
            txn.write(f"{SECRET}/{rel}", token, Expect.ABSENT)
            os.chmod(root / SECRET / rel, _FILE_MODE)
        times[ref] = str(row["created_at"])
        if row.get("last_used_at"):
            used[ref] = str(row["last_used_at"])
        carried += 1
    if times:
        JsonStore(local_root(home) / "secret-boundary" / "times.json").write(times)
    if used:
        JsonStore(local_root(home) / "secret-boundary" / "last-used.json").write(used)
    return carried


#: A value awaiting approval is stored at once now, so only these approvals are carried.
_KEPT_APPROVALS = ("bind", "disable_protection")


def write_boundary(home: Path, state: LegacyState) -> int:
    """Bindings, approvals and switches, through the boundary store."""
    store = FileBoundaryStore(home)
    for row in state.secret_bindings:
        binding: dict[str, Any] = {
            f.name: row.get(f.name) for f in dataclasses.fields(SecretBinding)
        }
        store.put_binding(SecretBinding(**binding))
    carried = [r for r in state.secret_approvals if r.get("op") in _KEPT_APPROVALS]
    for row in carried:
        fields: dict[str, Any] = {
            f.name: row.get(f.name) for f in dataclasses.fields(SecretApproval)
        }
        store.create_approval(SecretApproval(**fields))
    for key, value in sorted(state.secret_settings.items()):
        store.set_setting(key, value)
    return len(state.secret_bindings) + len(carried) + len(state.secret_settings)


def write_retention(state: LegacyState) -> int:
    """``retention_policies`` into ``local/retention.json``, in the repo's shape."""
    doc = {
        str(r["table_name"]): {
            "retention_days": r.get("retention_days"),
            "last_pruned_at": _iso(r.get("last_pruned_at")),
            "last_pruned_rows": int(r.get("last_pruned_rows") or 0),
            "updated_at": _iso(r.get("updated_at")),
        }
        for r in state.retention
    }
    if doc:
        JsonStore(retention_path()).write(doc)
    return len(doc)


def write_source_status(state: LegacyState) -> int:
    repo = SkillSourceStatusRepo()
    for r in state.source_status:
        status = SourceStatus(
            skill_uid=r["uid"],
            checked_at=when(r["checked_at"]) if r.get("checked_at") else None,
            last_success_at=when(r["last_success_at"]) if r.get("last_success_at") else None,
            error=r.get("error"),
            latest_commit=r.get("latest_commit"),
            commits_ahead=int(r.get("commits_ahead") or 0),
            files_changed=int(r.get("files_changed") or 0),
            dismissed_commit=r.get("dismissed_commit"),
        )
        asyncio.run(repo.put(status))
    return len(state.source_status)


def write_sync_remote(state: LegacyState) -> SyncRemote | None:
    """The remote row into ``local/sync/remote.json``. Its old layout is not
    converted: after the upgrade its first round is refused until it is
    rebuilt from this machine (an empty branch or remote)."""
    row = state.sync_remote
    if row is None:
        return None
    try:
        remote = SyncRemote(
            url=str(row["url"]),
            branch=str(row.get("branch") or "main"),
            secret_ref=row.get("secret_ref"),
            include_secret=bool(row.get("include_secrets")),
            interval_seconds=int(row.get("interval_seconds") or 3600),
            enabled=bool(row.get("enabled", 1)),
        )
    except SyncRemoteInvalid as exc:
        state.skipped.append(f"sync remote: {exc}")
        return None
    JsonRemoteStore().put(remote)
    return remote


def _copy_rows(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0])
    marks = ", ".join("?" for _ in columns)
    conn.executemany(
        f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({marks})",
        [tuple(r[c] for c in columns) for r in rows],
    )


def write_derived(home: Path, state: LegacyState) -> int:
    """The three derived tables, copied verbatim (timestamps as SQLite held them)."""
    path = derived_db_path(home)
    prepare_derived_db(path)
    engine = create_engine(f"sqlite:///{path}")
    try:
        DerivedBase.metadata.create_all(engine)
    finally:
        engine.dispose()
    seen = [
        {
            "server_uid": r["uid"],
            "capability_type": r["capability_type"],
            "capability_key": r["capability_key"],
            "first_seen_at": r["first_seen_at"],
            "last_seen_at": r["last_seen_at"],
        }
        for r in state.capabilities
    ]
    health = [
        {"resource_uid": r["resource_uid"], "status": r["status"], "checked_at": r["checked_at"]}
        for r in state.health
    ]
    with contextlib.closing(sqlite3.connect(path)) as conn:
        _copy_rows(conn, "mcp_capability_seen", seen)
        _copy_rows(conn, "mcp_server_health", health)
        _copy_rows(conn, "skill_agent_bindings", state.skill_bindings)
        conn.commit()
    return len(seen) + len(health) + len(state.skill_bindings)


__all__ = [
    "write_boundary",
    "write_derived",
    "write_retention",
    "write_secrets",
    "write_source_status",
    "write_sync_remote",
]
