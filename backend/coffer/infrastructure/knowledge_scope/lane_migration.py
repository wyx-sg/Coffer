"""One-time on-disk migration to the two-lane scope layout (2026-09-11).

A knowledge scope used to keep seven lanes. It now keeps two content lanes plus
two hidden archives::

    knowledge/inbox/*.md + knowledge/*.md  ->  notes/
    inbox/                                 ->  docs/
    .raw/                                  ->  unchanged
    rules/, handoff/, superseded/          ->  DELETED
    consolidation-log.md, knowledge/INDEX.md -> DELETED

The deletions are destructive by explicit decision — there is no holding pen and
no way back. Everything else moves; no note and no ingested document is lost.

Runs best-effort at daemon start, like the sibling worktree-scope consolidation.
Idempotent: a scope already on the new layout has no ``knowledge/`` and no
``inbox/`` to act on, so a second boot does nothing. A failure on one scope is
logged and the sweep continues — a half-migrated vault is still readable,
because the lazy reindex-on-read derives every path from the files on disk.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger(__name__)

#: Lanes that do not survive the collapse to two. Removed whole.
_RETIRED_DIRS = ("rules", "handoff", "superseded")
#: Files that do not survive. ``INDEX.md`` sits inside the old entry lane.
_RETIRED_SCOPE_FILES = ("consolidation-log.md",)
_RETIRED_LANE_FILES = ("INDEX.md", "MEMORY.md")


@dataclass
class LaneMigrationReport:
    """What one sweep did, for the boot log."""

    scopes_migrated: int = 0
    notes_moved: int = 0
    docs_lane_renamed: int = 0
    retired_removed: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def did_work(self) -> bool:
        return bool(
            self.scopes_migrated
            or self.notes_moved
            or self.docs_lane_renamed
            or self.retired_removed
        )


def _unique_target(directory: Path, name: str) -> Path:
    """``directory/name``, suffixed if taken.

    Flattening two source directories into one can collide: a staged item at
    ``knowledge/inbox/git-notes.md`` and a topic doc at ``knowledge/git-notes.md``
    are different files with the same basename. Neither may be dropped, so the
    second one landing keeps its content under ``git-notes-2.md``.
    """
    target = directory / name
    if not target.exists():
        return target
    stem, suffix = Path(name).stem, Path(name).suffix
    for n in range(2, 1000):
        candidate = directory / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
    raise OSError(f"cannot find a free name for {name!r} in {directory}")


def _move_markdown(src_dir: Path, dest_dir: Path) -> int:
    """Move every ``*.md`` directly inside ``src_dir`` into ``dest_dir``."""
    moved = 0
    for entry in sorted(src_dir.glob("*.md")):
        if not entry.is_file() or entry.name in _RETIRED_LANE_FILES:
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(entry), str(_unique_target(dest_dir, entry.name)))
        moved += 1
    return moved


def _remove(path: Path) -> bool:
    """Delete a file or a whole directory. True when something was there."""
    if not path.exists():
        return False
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True


def migrate_scope(scope_dir: Path, report: LaneMigrationReport) -> None:
    """Bring one scope directory to the two-lane layout."""
    touched = False

    # 1. knowledge/ (+ its nested inbox/) -> notes/. The topic docs move first
    #    so that on a name collision it is the consolidated text — the more
    #    considered of the two — that keeps the unsuffixed name, and the staged
    #    item it collided with that gets suffixed.
    old_notes = scope_dir / "knowledge"
    if old_notes.is_dir():
        notes = scope_dir / "notes"
        report.notes_moved += _move_markdown(old_notes, notes)
        staged = old_notes / "inbox"
        if staged.is_dir():
            report.notes_moved += _move_markdown(staged, notes)
        _remove(old_notes)
        touched = True

    # 2. inbox/ -> docs/. A plain rename: the ingested markdown is unchanged.
    old_docs = scope_dir / "inbox"
    if old_docs.is_dir():
        docs = scope_dir / "docs"
        if docs.is_dir():
            report.docs_lane_renamed += _move_markdown(old_docs, docs)
            _remove(old_docs)
        else:
            old_docs.rename(docs)
            report.docs_lane_renamed += 1
        touched = True

    # 3. The lanes that do not survive.
    for name in (*_RETIRED_DIRS, *_RETIRED_SCOPE_FILES):
        if _remove(scope_dir / name):
            report.retired_removed += 1
            touched = True

    if touched:
        report.scopes_migrated += 1


def migrate_knowledge_root(root: Path) -> LaneMigrationReport:
    """Sweep every scope under ``~/.coffer/knowledge/``. Never raises."""
    report = LaneMigrationReport()
    if not root.is_dir():
        return report
    for scope_dir in sorted(root.iterdir()):
        if not scope_dir.is_dir() or scope_dir.name.startswith("."):
            continue
        try:
            migrate_scope(scope_dir, report)
        except OSError as exc:
            report.failures.append(f"{scope_dir.name}: {exc}")
            _log.warning(
                "knowledge.lane_migration.scope_failed",
                extra={"scope": scope_dir.name},
                exc_info=True,
            )
    return report


__all__ = ["LaneMigrationReport", "migrate_knowledge_root", "migrate_scope"]
