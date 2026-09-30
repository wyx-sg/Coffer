"""Writing the vault class and reach out of the old tables (plan q9 §3 step 3).

Every file is produced by the serializer of the store that will read it —
``ResourceDocument`` for resource files, the state stores' own encoders for
state documents — so the bytes are exactly the ones the running daemon would
write for the same values. A migrated resource on two machines is therefore
byte-identical, and a new join between them has nothing to choose.

Resource files carry no ``created_at``: the old row's value is when *that*
machine registered it (or received it from sync), so two machines would write
two values for one resource and every resource would differ between them.
The store answers the first time this machine saw the uid instead.

Vault writes go into the upgrade's one commit (``staging``); ``local/`` and
``derived/`` files are written directly, as their stores do.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from coffer.application.channel.store_ports import ChannelPeer
from coffer.domain.internal_engine_config import GlobalInternalEngineConfig
from coffer.domain.vault.document import ResourceDocument
from coffer.domain.vault.layout import StorageClass, resource_path, state_path
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.channel.persistence import AREA as PEERS_AREA
from coffer.infrastructure.channel.persistence import _entry as peer_entry
from coffer.infrastructure.mcp.persistence import AREA as PREFS_AREA
from coffer.infrastructure.mcp.tool_reach_repo import MCPToolReachStore, tool_reach_path
from coffer.infrastructure.persistence.internal_engine_repo import (
    _DEFAULT_DOC as ENGINE_DEFAULTS,
)
from coffer.infrastructure.persistence.internal_engine_repo import AREA as ENGINE_AREA
from coffer.infrastructure.persistence.internal_engine_repo import DOC as ENGINE_DOC
from coffer.infrastructure.persistence.internal_engine_repo import _to_doc as engine_doc
from coffer.infrastructure.persistence.internal_engine_repo import engine_local_path
from coffer.infrastructure.vault.atomic import atomic_write
from coffer.infrastructure.vault.json_store import JsonStore
from coffer.infrastructure.vault.migration.legacy_db import LegacyState, OldResource, Row
from coffer.infrastructure.vault.migration.staging import LayoutCommit
from coffer.infrastructure.vault.reach_store import Reach, ReachStore, reach_path
from coffer.infrastructure.vault.resource_config import for_file
from coffer.infrastructure.vault.resource_files import class_root
from coffer.infrastructure.vault.state_documents import StateDocuments
from coffer.infrastructure.vault.state_documents import _encode_over as state_bytes
from coffer.infrastructure.vault.writer import Transaction

#: ``storage_of(kind, config)``: the class a resource is filed in.
StorageOf = Callable[[str, dict[str, Any]], StorageClass]


def when(raw: Any) -> datetime:
    """A timestamp as SQLite held it, as an aware ``datetime`` (naive: UTC)."""
    if isinstance(raw, datetime):
        value = raw
    else:
        try:
            value = datetime.fromisoformat(str(raw))
        except ValueError:
            return datetime.fromtimestamp(0, tz=UTC)
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _as_txn(staging: LayoutCommit) -> Transaction:
    """The state stores stage into a transaction and call only its
    ``write``; the layout commit writes exactly as one does."""
    return cast(Transaction, staging)


def _document(r: OldResource) -> bytes:
    doc = ResourceDocument(
        uid=r.uid,
        kind=r.kind,
        name=r.name,
        description=r.description,
        title=r.title,
        config=for_file(r.config),
    )
    return doc.to_bytes()


def write_resources(
    txn: LayoutCommit, home: Path, state: LegacyState, storage_of: StorageOf
) -> dict[str, int]:
    """Every resource file and its reach; answers how many went to each class."""
    counts = {c.value: 0 for c in (StorageClass.VAULT, StorageClass.LOCAL, StorageClass.DERIVED)}
    taken: set[tuple[StorageClass, str]] = set()
    reach = ReachStore(reach_path(home))
    for r in sorted(state.resources, key=lambda r: (r.kind, r.name)):
        storage = storage_of(r.kind, r.config)
        path = resource_path(r.kind, r.name)
        if (storage, path) in taken:
            path = resource_path(r.kind, f"{r.name}-{r.uid[:8]}")
        taken.add((storage, path))
        data = _document(r)
        if storage is StorageClass.VAULT:
            txn.write(path, data, Expect.ABSENT)
        else:
            atomic_write(class_root(storage, home) / path, data)
        scope = r.scope if r.scope is not None and r.scope.agents is not None else None
        reach.put(r.uid, Reach(enabled=r.enabled, scope=scope))
        counts[storage.value] += 1
    return counts


def write_tool_reach(home: Path, state: LegacyState) -> int:
    """``mcp_tool_reach`` into ``local/tool-reach.json``, through its store."""
    store = MCPToolReachStore(tool_reach_path(home))
    carried = 0
    for row in state.tool_reach:
        try:
            agents = json.loads(row["agents_json"])
        except (TypeError, ValueError):
            state.skipped.append(f"tool reach {row['resource_uid']}/{row['tool']}: not JSON")
            continue
        if not isinstance(agents, list):
            state.skipped.append(f"tool reach {row['resource_uid']}/{row['tool']}: not a list")
            continue
        asyncio.run(store.set_override(row["resource_uid"], row["tool"], [str(a) for a in agents]))
        carried += 1
    return carried


def write_capability_switches(txn: LayoutCommit, home: Path, state: LegacyState) -> int:
    """One ``state/mcp-preferences/<server>.json`` per server with a switch off."""
    off: dict[str, dict[str, set[str]]] = {}
    for row in state.capabilities:
        if not row["enabled"]:
            off.setdefault(row["uid"], {}).setdefault(row["capability_type"], set()).add(
                row["capability_key"]
            )
    docs = StateDocuments(PREFS_AREA, "server_uid", home=home)
    for uid, types in sorted(off.items()):
        listed = {t: sorted(keys) for t, keys in sorted(types.items()) if keys}
        docs.stage(_as_txn(txn), uid, state.name_of(uid) or uid, {"disabled": listed})
    return len(off)


def write_channel_peers(txn: LayoutCommit, home: Path, state: LegacyState) -> int:
    """One ``state/channel-peers/<channel>.json`` per paired channel, in pairing order."""
    by_channel: dict[str, list[Row]] = {}
    for row in state.peers:
        by_channel.setdefault(row["uid"], []).append(row)
    docs = StateDocuments(PEERS_AREA, "channel_uid", home=home)
    for uid, rows in sorted(by_channel.items()):
        rows.sort(key=lambda r: (when(r["paired_at"]), r.get("id") or 0))
        peers = [
            peer_entry(
                ChannelPeer(
                    resource_uid=uid,
                    chat_id=r["chat_id"],
                    display_name=str(r.get("display_name") or ""),
                    paired_at=when(r["paired_at"]),
                    sender_id=r.get("sender_id") or None,
                )
            )
            for r in rows
        ]
        docs.stage(_as_txn(txn), uid, state.name_of(uid) or uid, {"peers": peers})
    return len(by_channel)


def write_engine_settings(txn: LayoutCommit, state: LegacyState) -> bool:
    """``state/settings/internal-engine.json`` — absent when every value is the
    default, which is how the store says "never chose anything"."""
    row = state.engine
    if row is None:
        return False
    updated = when(row["updated_at"])
    config = GlobalInternalEngineConfig(
        model=row.get("model"),
        updated_at=updated,
        auto_curate_enabled=bool(row.get("auto_curate_enabled", 1)),
        curate_owner_machine_id=row.get("curate_owner_machine_id"),
        auto_aggregate_enabled=bool(row.get("auto_aggregate_enabled", 1)),
        aggregate_interval_s=row.get("aggregate_interval_s"),
        auto_distil_enabled=bool(row.get("auto_distil_enabled", 1)),
        distil_interval_s=row.get("distil_interval_s"),
        curate_interval_s=row.get("curate_interval_s"),
        model_timeout_s=row.get("model_timeout_s"),
        transcribe_model=row.get("transcribe_model"),
    )
    JsonStore(engine_local_path()).write({"updated_at": updated.isoformat()})
    doc = engine_doc(config)
    if doc == ENGINE_DEFAULTS:
        return False
    txn.write(state_path(ENGINE_AREA, ENGINE_DOC), state_bytes(None, doc), Expect.ABSENT)
    return True


__all__ = [
    "StorageOf",
    "when",
    "write_capability_switches",
    "write_channel_peers",
    "write_engine_settings",
    "write_resources",
    "write_tool_reach",
]
