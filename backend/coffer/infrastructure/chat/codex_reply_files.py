"""What a Codex reply changed in each file (spec chat "Record what each reply
changed in each file").

Codex's ``fileChange`` items already say what changed: each change carries its
diff. A file's diffs within one reply are kept in order and its counts summed.
For an added or deleted file the app-server sends the file's content rather than
a diff, which becomes all-added or all-removed lines.
"""

from __future__ import annotations

from typing import Any

from coffer.domain.chat.reply_file import MAX_REPLY_FILES, ReplyFile


def _kind(change: dict[str, Any]) -> str:
    kind = change.get("kind")
    if isinstance(kind, dict):
        kind = kind.get("type")
    return str(kind or "").lower()


def _hunks(change: dict[str, Any]) -> str:
    """The change's diff as hunks only (headers dropped), or ``""``."""
    diff = change.get("diff")
    if not isinstance(diff, str) or not diff:
        return ""
    lines = diff.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("@@"):
            return "\n".join(lines[i:]) + "\n"
    kind = _kind(change)
    if kind in ("add", "added", "create"):
        return f"@@ -0,0 +1,{len(lines)} @@\n" + "".join(f"+{ln}\n" for ln in lines)
    if kind in ("delete", "deleted", "remove"):
        return f"@@ -1,{len(lines)} +0,0 @@\n" + "".join(f"-{ln}\n" for ln in lines)
    return ""


def _counts(hunks: str) -> tuple[int, int]:
    lines = hunks.splitlines()
    return (
        sum(1 for ln in lines if ln.startswith("+")),
        sum(1 for ln in lines if ln.startswith("-")),
    )


class CodexReplyFiles:
    """The diffs a reply's file-change items carried, per path."""

    def __init__(self) -> None:
        self._hunks: dict[str, list[str]] = {}

    def add(self, changes: list[Any]) -> None:
        for change in changes:
            if not isinstance(change, dict):
                continue
            path = change.get("path")
            hunks = _hunks(change)
            if not isinstance(path, str) or not path or not hunks:
                continue
            if path not in self._hunks and len(self._hunks) >= MAX_REPLY_FILES:
                continue
            self._hunks.setdefault(path, []).append(hunks)

    def files(self) -> list[ReplyFile]:
        out: list[ReplyFile] = []
        for path, chunks in self._hunks.items():
            counts = [_counts(c) for c in chunks]
            name = path.lstrip("/")
            diff = f"--- a/{name}\n+++ b/{name}\n" + "".join(chunks)
            out.append(ReplyFile(path, sum(a for a, _ in counts), sum(r for _, r in counts), diff))
        return out
