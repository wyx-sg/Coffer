"""What this machine wrote into its agents: ``local/memory-sync.json``
(spec memory "Add no table or resource kind").

Machine-local and never synced: which native sources were read and at what
digest, every copy Coffer wrote into each agent with its state, the sentence
fingerprints of what Coffer delivered to each agent (spec memory "Never
republish Coffer's own copies"), whether the first sync's preview was
confirmed, and the person's answer to "Codex imports Claude Code's memories
itself". Beside it, ``local/memory-sync-preview.json`` holds a pending
preview (spec memory "Preview a first or large sync").

Losing the ledger is safe: the next sync treats nothing as written, plans
every copy again, and the preview shows the rewrite before it happens.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from coffer.domain.memory.sync_plan import STATE_WRITTEN, CopyOp, CopyRecord
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore

LEDGER_VERSION = 1


def ledger_path() -> Path:
    return local_root() / "memory-sync.json"


def preview_path() -> Path:
    return local_root() / "memory-sync-preview.json"


@dataclass
class SourceRecord:
    """One native source as last read: its digest and the hub entries it produced."""

    digest: str
    entries: list[str] = field(default_factory=list)


@dataclass
class Ledger:
    previewed: bool = False
    #: The person's answer to "Codex imports Claude Code's memories itself";
    #: ``None`` until they give one (spec memory "Defer to Codex's own import
    #: from Claude Code").
    codex_imports_claude: bool | None = None
    sources: dict[str, SourceRecord] = field(default_factory=dict)
    #: ``<agent type>@<config dir> → path → record``.
    copies: dict[str, dict[str, CopyRecord]] = field(default_factory=dict)
    #: ``agent type → sentence fingerprints`` Coffer delivered to it.
    delivered: dict[str, list[str]] = field(default_factory=dict)
    #: When this machine last synced, and the last sync's short report.
    last_synced_at: str = ""
    last_report: dict[str, Any] = field(default_factory=dict)

    def agent_copies(self, agent: str) -> dict[str, CopyRecord]:
        return self.copies.setdefault(agent, {})

    def deliver(self, agent: str, fingerprints: set[str]) -> None:
        current = set(self.delivered.get(agent, []))
        self.delivered[agent] = sorted(current | fingerprints)


def _to_dict(ledger: Ledger) -> dict[str, Any]:
    return {
        "version": LEDGER_VERSION,
        "previewed": ledger.previewed,
        "codex_imports_claude": ledger.codex_imports_claude,
        "sources": {p: asdict(s) for p, s in ledger.sources.items()},
        "copies": {
            agent: {p: _record_dict(r) for p, r in recs.items()}
            for agent, recs in ledger.copies.items()
        },
        "delivered": ledger.delivered,
        "last_synced_at": ledger.last_synced_at,
        "last_report": ledger.last_report,
    }


def _record_dict(rec: CopyRecord) -> dict[str, str]:
    return {
        "entry": rec.entry,
        "entry_updated_at": rec.entry_updated_at,
        "digest": rec.digest,
        "state": rec.state,
    }


def _from_dict(raw: dict[str, Any]) -> Ledger:
    ledger = Ledger()
    ledger.previewed = bool(raw.get("previewed", False))
    imports = raw.get("codex_imports_claude")
    ledger.codex_imports_claude = imports if isinstance(imports, bool) else None
    for path, src in (raw.get("sources") or {}).items():
        if isinstance(src, dict):
            ledger.sources[str(path)] = SourceRecord(
                digest=str(src.get("digest", "")),
                entries=[str(e) for e in src.get("entries") or []],
            )
    for agent, recs in (raw.get("copies") or {}).items():
        if not isinstance(recs, dict):
            continue
        ledger.copies[str(agent)] = {
            str(path): CopyRecord(
                path=str(path),
                entry=str(rec.get("entry", "")),
                entry_updated_at=str(rec.get("entry_updated_at", "")),
                digest=str(rec.get("digest", "")),
                state=str(rec.get("state", STATE_WRITTEN)),
            )
            for path, rec in recs.items()
            if isinstance(rec, dict)
        }
    for agent, prints in (raw.get("delivered") or {}).items():
        if isinstance(prints, list):
            ledger.delivered[str(agent)] = [str(p) for p in prints]
    ledger.last_synced_at = str(raw.get("last_synced_at", "") or "")
    report = raw.get("last_report")
    ledger.last_report = report if isinstance(report, dict) else {}
    return ledger


class LedgerStore:
    """The ledger file, read whole and written whole."""

    def __init__(self, path: Callable[[], Path] = ledger_path) -> None:
        self._store = JsonStore(path)

    def load(self) -> Ledger:
        return _from_dict(self._store.read())

    def save(self, ledger: Ledger) -> None:
        self._store.write(_to_dict(ledger))


class PreviewStore:
    """The pending preview: the copy operations a sync planned and held."""

    def __init__(self, path: Callable[[], Path] = preview_path) -> None:
        self._path = path
        self._store = JsonStore(path)

    def load(self) -> tuple[str, list[CopyOp]] | None:
        raw = self._store.read()
        ops = raw.get("ops")
        if not isinstance(ops, list):
            return None
        out = [CopyOp(**{k: str(v) for k, v in op.items()}) for op in ops if isinstance(op, dict)]
        return str(raw.get("created_at", "")), out

    def save(self, created_at: str, ops: list[CopyOp]) -> None:
        self._store.write({"created_at": created_at, "ops": [asdict(op) for op in ops]})

    def clear(self) -> None:
        self._path().unlink(missing_ok=True)


__all__ = ["Ledger", "LedgerStore", "PreviewStore", "SourceRecord", "ledger_path", "preview_path"]
