"""What changes between two versions of a skill folder.

Used by the update preview (spec skill-manager "Update a Git-imported skill
from its source"): the pinned commit's folder against the new commit's, and —
when the person edited the skill — the pinned folder against the master. Each
changed file is ``added``, ``removed`` or ``modified``, with a unified diff for
a text file (capped, so a regenerated data file does not ship megabytes to a
dialog) and a ``binary`` flag instead for anything that is not UTF-8 text.

Stdlib only, over directories Coffer owns (a staging checkout, the master).
"""

from __future__ import annotations

import difflib
import pathlib
from dataclasses import dataclass

from coffer.domain.skill.content_hash import iter_content_files

#: Lines of unified diff kept per file before it is cut.
MAX_DIFF_LINES = 400
#: Bytes of one version read for a diff or a compare view.
MAX_TEXT_BYTES = 256 * 1024


@dataclass(frozen=True)
class FileChange:
    path: str
    status: str  # "added" | "removed" | "modified"
    diff: str
    binary: bool
    additions: int
    deletions: int
    truncated: bool


@dataclass(frozen=True)
class TextVersion:
    """One version of one file, for a side-by-side compare."""

    text: str | None
    binary: bool
    truncated: bool


def read_text(path: pathlib.Path | None) -> TextVersion:
    """``path``'s text (``None`` when it does not exist), capped and binary-aware."""
    if path is None or not path.is_file() or path.is_symlink():
        return TextVersion(None, False, False)
    raw = path.read_bytes()
    truncated = len(raw) > MAX_TEXT_BYTES
    raw = raw[:MAX_TEXT_BYTES]
    if b"\x00" in raw:
        return TextVersion("", True, truncated)
    try:
        return TextVersion(raw.decode("utf-8"), False, truncated)
    except UnicodeDecodeError:
        if truncated:  # cut inside a multi-byte character
            return TextVersion(raw.decode("utf-8", "ignore"), False, True)
        return TextVersion("", True, False)


def _same(a: pathlib.Path, b: pathlib.Path) -> bool:
    if a.is_symlink() or b.is_symlink():
        return a.is_symlink() and b.is_symlink() and a.readlink() == b.readlink()
    return a.read_bytes() == b.read_bytes()


def _change(
    rel: str, old: pathlib.Path | None, new: pathlib.Path | None, status: str
) -> FileChange:
    before, after = read_text(old), read_text(new)
    if before.binary or after.binary:
        return FileChange(rel, status, "", True, 0, 0, False)
    a = (before.text or "").splitlines(keepends=True)
    b = (after.text or "").splitlines(keepends=True)
    lines = list(difflib.unified_diff(a, b, fromfile=f"a/{rel}", tofile=f"b/{rel}", n=3))
    adds = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
    dels = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))
    truncated = len(lines) > MAX_DIFF_LINES or before.truncated or after.truncated
    text = "".join(ln if ln.endswith("\n") else ln + "\n" for ln in lines[:MAX_DIFF_LINES])
    return FileChange(rel, status, text, False, adds, dels, truncated)


def diff_folders(old: pathlib.Path | None, new: pathlib.Path | None) -> list[FileChange]:
    """Every file that differs from ``old`` to ``new``, sorted by path.

    ``None`` (or a missing directory) on either side is an empty folder, so a
    skill whose pinned commit cannot be checked out shows every file as added.
    """
    old_files = set(iter_content_files(old)) if old and old.is_dir() else set()
    new_files = set(iter_content_files(new)) if new and new.is_dir() else set()
    changes: list[FileChange] = []
    for rel in sorted(old_files | new_files):
        if rel not in old_files:
            assert new is not None
            changes.append(_change(rel, None, new / rel, "added"))
        elif rel not in new_files:
            assert old is not None
            changes.append(_change(rel, old / rel, None, "removed"))
        else:
            assert old is not None and new is not None
            if not _same(old / rel, new / rel):
                changes.append(_change(rel, old / rel, new / rel, "modified"))
    return changes


__all__ = ["MAX_DIFF_LINES", "FileChange", "TextVersion", "diff_folders", "read_text"]
