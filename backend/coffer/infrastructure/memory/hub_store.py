"""The memory hub on disk: ``vault/memory/`` (spec memory "Keep every agent's
memories in a hub in the vault").

One Markdown file per memory, frontmatter first, under ``global/`` or
``projects/<folder>/``. The hub is vault content: every change a sync makes is
one vault commit through the vault's single write path, naming the memory sync
as its writer, and vault sync carries the hub to the person's other machines
like any other vault file.

Reading is from disk, not ``HEAD``: a sync round may have merged another
machine's entries a moment ago, and the working tree is what the person's
machines agree on.
"""

from __future__ import annotations

import logging
import os
import pathlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from coffer.domain.memory.errors import UnsafeMemoryPath
from coffer.domain.memory.hub import (
    GLOBAL,
    HUB_TYPES,
    PROJECTS,
    TYPE_PROJECT,
    HubEntry,
    Origin,
    check_id,
)
from coffer.domain.vault.content_ids import fingerprint
from coffer.domain.vault.layout import MEMORY
from coffer.domain.vault.writers import WRITER_MEMORY_SYNC, CommitMeta
from coffer.domain.vault.writes import Expect
from coffer.infrastructure.memory.frontmatter import render_frontmatter, split_frontmatter
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.writer import VaultWriter

logger = logging.getLogger(__name__)

#: The operation every hub commit names; its writer is ``memory-sync``.
OP_MEMORY_SYNC = "memory-sync"


def render_entry(entry: HubEntry) -> str:
    """The file a hub entry is stored as."""
    fm: dict[str, Any] = {
        "id": entry.id,
        "origin": {
            "machine": entry.origin.machine,
            "agent": entry.origin.agent,
            "source": entry.origin.source,
        },
    }
    if entry.project:
        fm["project"] = entry.project
    fm.update(
        {
            "type": entry.type,
            "title": entry.title,
            "description": entry.description,
        }
    )
    if entry.search_terms:
        fm["search_terms"] = list(entry.search_terms)
    fm["created_at"] = entry.created_at
    fm["updated_at"] = entry.updated_at
    body = entry.body.strip("\n")
    return render_frontmatter(fm, f"\n{body}\n")


def parse_entry(text: str) -> HubEntry | None:
    """A hub file read back, or ``None`` when it is not one (a person's own
    file under ``vault/memory/`` is kept, and ignored)."""
    fm, body = split_frontmatter(text)
    origin = fm.get("origin")
    if not isinstance(origin, dict):
        return None
    try:
        entry_id = check_id(str(fm.get("id", "")))
    except UnsafeMemoryPath:
        return None
    entry_type = str(fm.get("type", "") or "")
    terms = fm.get("search_terms") or []
    return HubEntry(
        id=entry_id,
        origin=Origin(
            machine=str(origin.get("machine", "") or ""),
            agent=str(origin.get("agent", "") or ""),
            source=str(origin.get("source", "") or ""),
        ),
        project=str(fm.get("project", "") or ""),
        type=entry_type if entry_type in HUB_TYPES else TYPE_PROJECT,
        title=str(fm.get("title", "") or ""),
        description=str(fm.get("description", "") or ""),
        body=body.strip("\n"),
        created_at=str(fm.get("created_at", "") or ""),
        updated_at=str(fm.get("updated_at", "") or ""),
        search_terms=tuple(str(t) for t in terms) if isinstance(terms, list) else (),
    )


@dataclass
class HubChanges:
    """One sync's changes to the hub, committed together."""

    upserts: list[HubEntry] = field(default_factory=list)
    deletes: list[HubEntry] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.upserts or self.deletes)


class HubStore:
    """``vault/memory/``, read from disk and written through the vault."""

    def __init__(self, writer: Callable[[], VaultWriter] = vault_writer) -> None:
        self._writer = writer

    def root(self) -> pathlib.Path:
        return self._writer().repo.root / MEMORY

    def entries(self) -> dict[str, HubEntry]:
        """Every hub entry, by id. A file that does not parse is skipped."""
        root = self.root()
        found: dict[str, HubEntry] = {}
        for path in _md_files(root):
            try:
                entry = parse_entry(path.read_bytes().decode("utf-8"))
            except (OSError, UnicodeDecodeError):
                logger.warning("memory.hub.unreadable path=%s", path)
                continue
            if entry is None:
                continue
            found[entry.id] = entry
        return found

    def located(self) -> dict[str, str]:
        """Each entry id's hub-relative path as found on disk."""
        root = self.root()
        out: dict[str, str] = {}
        for path in _md_files(root):
            stem = path.stem
            try:
                out[check_id(stem)] = path.relative_to(root).as_posix()
            except UnsafeMemoryPath:
                continue
        return out

    def apply(self, changes: HubChanges, summary: str, actor: str | None) -> str | None:
        """Write ``changes`` as one vault commit; answer the commit or ``None``."""
        if not changes:
            return None
        writer = self._writer()
        located = self.located()
        meta = CommitMeta(
            writer=WRITER_MEMORY_SYNC, operation=OP_MEMORY_SYNC, summary=summary, actor=actor
        )
        with writer.begin(meta) as txn:
            for entry in changes.deletes:
                rel = located.get(entry.id, entry.path)
                path = f"{MEMORY}/{rel}"
                if writer.read_disk(path) is not None:
                    txn.delete(path, _any(writer, path))
            for entry in changes.upserts:
                old = located.get(entry.id)
                if old and old != entry.path:
                    stale = f"{MEMORY}/{old}"
                    txn.delete(stale, _any(writer, stale))
                path = f"{MEMORY}/{entry.path}"
                data = render_entry(entry).encode("utf-8")
                current = writer.read_disk(path)
                if current == data:
                    continue
                txn.write(path, data, _any(writer, path) if current is not None else Expect.ABSENT)
        return txn.version


def _any(writer: VaultWriter, path: str) -> str | Expect:
    """What ``path`` holds now: the hub is Coffer's to rewrite, so a sync
    states the bytes it found rather than refusing a file a round just merged."""
    current = writer.read_disk(path)
    return Expect.ABSENT if current is None else fingerprint(current)


def _md_files(root: pathlib.Path) -> Iterable[pathlib.Path]:
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        rel = pathlib.Path(folder).relative_to(root).parts
        if rel and rel[0] not in (GLOBAL, PROJECTS):
            continue
        for name in files:
            if name.endswith(".md") and not name.startswith("."):
                yield pathlib.Path(folder) / name


__all__ = [
    "OP_MEMORY_SYNC",
    "HubChanges",
    "HubStore",
    "parse_entry",
    "render_entry",
]
