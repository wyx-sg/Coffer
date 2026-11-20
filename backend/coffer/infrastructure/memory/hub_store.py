"""The memory hub on disk: ``vault/memory/`` (spec memory "Keep memory in one
place in the vault").

Agents write the hub's files themselves, with their own file tools; the vault
scanner commits what they wrote as ``disk`` writes, as it does any edit made
outside Coffer. This module reads the files from disk (the working tree is
what the person's machines agree on), writes a person's edit from the Memory
page through the vault's one write path, keeps a tidy's edits together as one
commit, and converts the one-file-per-memory entries an older build published.
"""

from __future__ import annotations

import logging
import os
import pathlib
from collections.abc import Callable
from dataclasses import dataclass

from coffer.domain.memory.errors import MemoryFileNotFound, MemoryFileStale
from coffer.domain.memory.hub import (
    PROJECTS,
    TYPE_PROJECT,
    TYPES,
    Topic,
    check_file_name,
    check_segment,
    read_topic,
)
from coffer.domain.vault.content_ids import fingerprint
from coffer.domain.vault.layout import MEMORY
from coffer.domain.vault.writers import (
    OP_DELETE,
    OP_LAYOUT,
    OP_UPDATE,
    WRITER_DAEMON,
    WRITER_USER,
    CommitMeta,
)
from coffer.infrastructure.memory.frontmatter import render_frontmatter, split_frontmatter
from coffer.infrastructure.vault import git
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.writer import VaultWriter

logger = logging.getLogger(__name__)

#: What a recording failure looks like; logged, and the files stand.
_RECORDING_ERRORS = (git.VaultGitError, git.GitMissing, OSError)
#: The vault-relative prefix every hub path starts with.
PREFIX = f"{MEMORY}/"


@dataclass(frozen=True)
class TopicFile:
    """One file with its raw text and the token a write must quote."""

    topic: Topic
    text: str
    digest: str


class HubStore:
    """``vault/memory/``, read from disk and written through the vault."""

    def __init__(self, writer: Callable[[], VaultWriter] = vault_writer) -> None:
        self._writer = writer

    def root(self) -> pathlib.Path:
        return self._writer().repo.root / MEMORY

    def projects_root(self) -> pathlib.Path:
        return self.root() / PROJECTS

    # --- reading -----------------------------------------------------------------

    def projects(self) -> list[str]:
        """Every project folder that holds at least one Markdown file."""
        base = self.projects_root()
        if not base.is_dir():
            return []
        return sorted(
            d.name
            for d in base.iterdir()
            if d.is_dir() and not d.name.startswith(".") and any(_md_files(d))
        )

    def topics(self, project: str) -> list[Topic]:
        """Every topic of ``project``, in file-name order."""
        return read_topics(self.projects_root() / check_segment(project), project)

    def read(self, project: str, name: str) -> TopicFile:
        path = self._path(project, name)
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            raise MemoryFileNotFound(f"{project}/{name}") from None
        text = data.decode("utf-8", errors="replace")
        fm, body = split_frontmatter(text)
        return TopicFile(read_topic(project, name, fm, body), text, fingerprint(data))

    # --- a person's edit -----------------------------------------------------------

    def write(self, project: str, name: str, text: str, *, expected: str, actor: str) -> str | None:
        """Replace the file with ``text`` as one commit; refused
        :class:`MemoryFileStale` when it no longer holds ``expected``."""
        rel = self._rel(project, name)
        writer = self._writer()
        self._check_current(writer, rel, expected)
        meta = CommitMeta(WRITER_USER, OP_UPDATE, f"Edited memory {project}/{name}", actor=actor)
        with writer.begin(meta) as txn:
            txn.write(rel, text.encode("utf-8"), expected)
        return txn.version

    def delete(self, project: str, name: str, *, expected: str, actor: str) -> str | None:
        rel = self._rel(project, name)
        writer = self._writer()
        self._check_current(writer, rel, expected)
        meta = CommitMeta(WRITER_USER, OP_DELETE, f"Deleted memory {project}/{name}", actor=actor)
        with writer.begin(meta) as txn:
            txn.delete(rel, expected)
        return txn.version

    def _check_current(self, writer: VaultWriter, rel: str, expected: str) -> None:
        current = writer.read_disk(rel)
        if current is None:
            raise MemoryFileNotFound(rel.removeprefix(f"{PREFIX}{PROJECTS}/"))
        if fingerprint(current) != expected:
            raise MemoryFileStale(rel.removeprefix(f"{PREFIX}{PROJECTS}/"))

    # --- a tidy ----------------------------------------------------------------------

    def pause(self, running: Callable[[], bool]) -> None:
        """Leave edits under ``vault/memory/`` uncommitted while ``running()``:
        neither the vault scanner nor a sync round settles them until the tidy
        closes. Idempotent."""
        try:
            self._writer().set_paused(lambda: [PREFIX] if running() else [], owner="memory")
        except _RECORDING_ERRORS:
            logger.warning("memory.hub.pause_failed", exc_info=True)

    def settle(self) -> None:
        """Commit what changed under ``vault/memory/`` as ``disk`` writes."""
        try:
            writer = self._writer()
            pending = [p for p in writer.pending() if p.startswith(PREFIX)]
            if pending:
                writer.settle(pending)
        except _RECORDING_ERRORS:
            logger.warning("memory.hub.settle_failed", exc_info=True)

    def pending(self) -> tuple[tuple[str, str | None], ...]:
        """The hub's uncommitted paths and digests, paused ones included: what
        a tidy watches to tell whether its agent is still at work."""
        try:
            pending = self._writer().pending(include_paused=True)
        except _RECORDING_ERRORS:
            logger.warning("memory.hub.pending_failed", exc_info=True)
            return ()
        return tuple(sorted((p, d) for p, d in pending.items() if p.startswith(PREFIX)))

    def settle_as(self, meta: CommitMeta) -> str | None:
        """Commit everything that changed under ``vault/memory/`` as one commit
        carrying ``meta``; ``None`` when nothing had changed."""
        try:
            writer = self._writer()
            pending = [p for p in writer.pending(include_paused=True) if p.startswith(PREFIX)]
            if not pending:
                return None
            result = writer.settle(pending, meta=meta)
        except _RECORDING_ERRORS:
            logger.warning("memory.hub.settle_failed", exc_info=True)
            return None
        return result.version if result is not None else None

    # --- converting an older build's entries ------------------------------------------

    def convert_legacy(self) -> int:
        """Rewrite every hub entry an older build published (one memory per
        file, with ``id`` and ``origin`` in its frontmatter) into the topic
        format, as one ``daemon`` commit; the number converted. A file in the
        topic format, or anyone's own file, is left alone."""
        writer = self._writer()
        changes: list[tuple[str, bytes, str]] = []
        for path in _md_files(self.projects_root(), recursive=True):
            try:
                data = path.read_bytes()
            except OSError:
                continue
            new = _converted(data.decode("utf-8", errors="replace"))
            if new is None:
                continue
            rel = f"{PREFIX}{path.relative_to(self.root()).as_posix()}"
            changes.append((rel, new.encode("utf-8"), fingerprint(data)))
        if not changes:
            return 0
        meta = CommitMeta(
            WRITER_DAEMON,
            OP_LAYOUT,
            f"Converted {len(changes)} memories to the topic format",
            actor="daemon",
        )
        try:
            with writer.begin(meta) as txn:
                for rel, data, expected in changes:
                    txn.write(rel, data, expected)
        except _RECORDING_ERRORS:
            logger.warning("memory.hub.convert_failed", exc_info=True)
            return 0
        return len(changes)

    # --- paths -------------------------------------------------------------------------

    def _path(self, project: str, name: str) -> pathlib.Path:
        return self.projects_root() / check_segment(project) / check_file_name(name)

    def _rel(self, project: str, name: str) -> str:
        return f"{PREFIX}{PROJECTS}/{check_segment(project)}/{check_file_name(name)}"


def read_topics(folder: pathlib.Path, project: str) -> list[Topic]:
    """Every topic file in ``folder``, in file-name order. A file that cannot
    be read is skipped and logged. Needs no vault writer, so the session-start
    hook can call it without a daemon."""
    out: list[Topic] = []
    for path in _md_files(folder):
        try:
            text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            logger.warning("memory.hub.unreadable path=%s", path)
            continue
        fm, body = split_frontmatter(text)
        out.append(read_topic(project, path.name, fm, body))
    return out


def _converted(text: str) -> str | None:
    """An older build's entry in the topic format, or ``None`` when ``text``
    is not one."""
    fm, body = split_frontmatter(text)
    if not isinstance(fm.get("origin"), dict) or not fm.get("id"):
        return None
    kind = str(fm.get("type") or "")
    updated = str(fm.get("updated_at") or fm.get("created_at") or "")[:10]
    lines = body.strip("\n").splitlines()
    return render_frontmatter(
        {
            "title": str(fm.get("title") or fm.get("id")),
            "type": kind if kind in TYPES else TYPE_PROJECT,
            "updated": updated,
        },
        "\n" + "\n".join(lines) + "\n",
    )


def _md_files(folder: pathlib.Path, *, recursive: bool = False) -> list[pathlib.Path]:
    if not folder.is_dir():
        return []
    if not recursive:
        return sorted(
            p
            for p in folder.iterdir()
            if p.is_file() and p.suffix == ".md" and not p.name.startswith(".")
        )
    found: list[pathlib.Path] = []
    for here, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        found.extend(
            pathlib.Path(here) / f for f in files if f.endswith(".md") and not f.startswith(".")
        )
    return sorted(found)


__all__ = ["PREFIX", "HubStore", "TopicFile", "read_topics"]
