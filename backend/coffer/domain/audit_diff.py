"""What a text edit changed, sized for an audit row.

An audit row about an edit to knowledge or a skill carries the unified diff of
that edit, so a reader of the activity log sees what changed rather than only
that something did. The diff is capped: a row is a record, not a copy of the
file, and the vault's history keeps the full version anyway.

Only text a person reads as content is ever diffed — knowledge documents,
collection READMEs, a skill's files. A resource's config (which may carry an
MCP server's env or headers), state documents, machine descriptors and
anything under ``secret/`` are never diffed: a diff would copy into the log
whatever the file holds, and the audit log must never hold a secret.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable, Iterable
from typing import Any

from coffer.domain.vault.layout import KNOWLEDGE, SKILLS

#: The most diff an audit row keeps, in UTF-8 bytes.
MAX_DIFF_BYTES = 8 * 1024
#: Lines of context around each change, as ``diff -u``.
CONTEXT_LINES = 3

#: The vault areas whose files are content a person writes, never config.
_DIFFABLE_AREAS = (f"{KNOWLEDGE}/", f"{SKILLS}/")
#: The suffixes of those files that are text worth showing line by line.
_TEXT_SUFFIXES = (".md", ".markdown", ".txt", ".rst", ".py", ".sh", ".js", ".ts")


def capped_diff(diff: str) -> dict[str, Any]:
    """``{"diff": diff}``, cut to :data:`MAX_DIFF_BYTES` when longer; a cut
    diff adds ``diff_truncated`` and ``diff_bytes`` (the uncut size)."""
    raw = diff.encode("utf-8")
    if len(raw) <= MAX_DIFF_BYTES:
        return {"diff": diff}
    # ``ignore`` drops a multi-byte character the cut split in half.
    kept = raw[:MAX_DIFF_BYTES].decode("utf-8", errors="ignore")
    return {"diff": kept, "diff_truncated": True, "diff_bytes": len(raw)}


def text_diff(before: str, after: str, path: str) -> dict[str, Any]:
    """The capped unified diff from ``before`` to ``after``; ``{}`` when they
    are the same text."""
    if before == after:
        return {}
    return capped_diff(_unified(before, after, path))


def as_text(data: bytes | None) -> str | None:
    """``data`` as text, or ``None`` when absent or not UTF-8 text."""
    if data is None or b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def is_diffable(path: str) -> bool:
    """Whether a vault path is content whose edits are shown as a diff."""
    name = path.rsplit("/", 1)[-1].lower()
    return (
        path.startswith(_DIFFABLE_AREAS)
        and not name.startswith(".env")
        and name.endswith(_TEXT_SUFFIXES)
    )


def _change(before: bytes | None, after: bytes | None) -> str:
    return "added" if before is None else "deleted" if after is None else "modified"


def _file_diff(before: bytes | None, after: bytes | None, path: str) -> str:
    """The uncut diff of a diffable text file present on both sides, else ""."""
    if before is None or after is None or before == after or not is_diffable(path):
        return ""
    old, new = as_text(before), as_text(after)
    return _unified(old, new, path) if old is not None and new is not None else ""


def commit_change(
    read: Callable[[str, str], bytes | None], version: str, paths: Iterable[str]
) -> dict[str, Any]:
    """What the vault commit ``version`` did to ``paths``, for one audit row.

    ``read(ref, path)`` returns a file's bytes at a ref (``None`` where it did
    not exist). One path gives its ``change`` and diff; several give the
    count of each change and one diff of every diffable file, capped together.
    """
    changes: dict[str, str] = {}
    diffs: list[str] = []
    for path in paths:
        before, after = read(f"{version}^", path), read(version, path)
        if before is None and after is None:
            continue
        changes[path] = _change(before, after)
        # Joined uncut, so the cap applies to the whole row.
        diffs.append(_file_diff(before, after, path))
    out: dict[str, Any] = {}
    if len(changes) == 1:
        out["change"] = next(iter(changes.values()))
    elif changes:
        for kind in ("added", "deleted", "modified"):
            count = sum(1 for c in changes.values() if c == kind)
            if count:
                out[kind] = count
    joined = "".join(diffs)
    if joined:
        out.update(capped_diff(joined))
    return out


def _unified(before: str, after: str, path: str) -> str:
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=CONTEXT_LINES,
    )
    # A last line without a newline would run into the next file's header.
    return "".join(line if line.endswith("\n") else line + "\n" for line in lines)


__all__ = [
    "CONTEXT_LINES",
    "MAX_DIFF_BYTES",
    "as_text",
    "capped_diff",
    "commit_change",
    "is_diffable",
    "text_diff",
]
