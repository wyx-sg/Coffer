"""A plaintext finding in its file (spec vault-sync "Show a plaintext finding in
its file").

The Sync page lists where a round found a plaintext secret; this is what a
person reads to decide whether it is one. It is computed from the vault's git
history when asked, and nothing is stored:

* the flagged line with a few lines either side, read from the blob the round
  found the value in, every plaintext value on them masked (the value's shape
  stands in for it — see ``coffer.domain.plaintext_shape``);
* whether the remote holds the file already (``added`` / ``modified``) and
  whether it holds the flagged line already;
* for a modified file, its change against the remote's copy, masked line by
  line the same way.

The remote's copy is the one the round would have pushed on top of: the
newest commit it pulled, else the commit it recorded as ``from_commit`` — the
pair "Show what a round changed in each file" reads for a push.
"""

from __future__ import annotations

import difflib
from collections.abc import Callable

from coffer.application.sync.round_deps import RoundDeps
from coffer.application.sync.round_diff import MAX_BYTES, MAX_LINES
from coffer.domain.plaintext_shape import MaskedValue
from coffer.domain.sync.errors import SyncPlaintextNotListed, SyncRoundDiffUnavailable
from coffer.domain.sync.plaintext import MaskedLine, PlaintextContext, PlaintextFinding
from coffer.domain.sync.rounds import RoundRecord

#: Lines shown on each side of the flagged one.
CONTEXT = 3

Masker = Callable[[str], tuple[str, tuple[MaskedValue, ...]]]


def _text(raw: bytes | None) -> str | None:
    if raw is None or b"\0" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _remote_commit(record: RoundRecord) -> str | None:
    return record.pulled[0].version if record.pulled else record.from_commit


def _masked_diff(old: str, new: str, path: str, masker: Masker) -> tuple[str | None, int, int]:
    lines = list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"remote/{path}",
            tofile=f"local/{path}",
        )
    )
    if len(lines) > MAX_LINES:
        return None, 0, 0
    out: list[str] = []
    added = removed = 0
    for line in lines:
        if line.startswith(("---", "+++", "@@")) or not line:
            out.append(line)
            continue
        mark, body = line[0], line[1:]
        end = "\n" if body.endswith("\n") else ""
        out.append(mark + masker(body.removesuffix("\n"))[0] + end)
        added += mark == "+"
        removed += mark == "-"
    return "".join(out), added, removed


def context(d: RoundDeps, record: RoundRecord, path: str, line: int) -> PlaintextContext:
    """``path``:``line`` of what ``record`` found, as the person may see it."""
    found: PlaintextFinding | None = next(
        (f for f in record.plaintext if f.path == path and f.line == line and f.current), None
    )
    if found is None:
        raise SyncPlaintextNotListed(path, line)
    if d.mask_plaintext is None:
        raise SyncRoundDiffUnavailable
    masker = d.mask_plaintext
    text = _text(d.git.blobs([found.blob]).get(found.blob))
    if text is None:
        raise SyncRoundDiffUnavailable
    rows = text.splitlines()
    lo, hi = max(1, line - CONTEXT), min(len(rows), line + CONTEXT)
    shown = []
    for n in range(lo, hi + 1):
        masked, values = masker(rows[n - 1])
        shown.append(MaskedLine(n, masked, values))

    remote = _remote_commit(record)
    old_raw = d.git.read(remote, path) if remote and d.git.files(remote) else None
    if old_raw is None:
        return PlaintextContext(found, "added", False, tuple(shown))
    old = _text(old_raw) if len(old_raw) <= MAX_BYTES else None
    on_remote = old is not None and 0 < line <= len(rows) and rows[line - 1] in old.splitlines()
    diff: str | None = None
    added = removed = 0
    if old is not None and len(text.encode()) <= MAX_BYTES:
        diff, added, removed = _masked_diff(old, text, path, masker)
    return PlaintextContext(found, "modified", on_remote, tuple(shown), diff, added, removed)


__all__ = ["CONTEXT", "context"]
