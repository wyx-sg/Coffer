"""A plaintext finding in its file (spec vault-sync "Show a plaintext finding in
its file").

The Sync page lists where a round found a plaintext secret; this is what a
person reads to decide whether it is one. It is computed from the vault's git
history when asked, and nothing is stored:

* the flagged line with a few lines either side, read from the blob the round
  found the value in, every plaintext value on them masked (the value's shape
  stands in for it — see ``coffer.domain.plaintext_shape``). The whole file is
  masked once, by the bundled rules (spec secret "Detect plaintext secrets with
  the bundled rules"), so a value spanning lines is masked on each;
* whether the remote holds the file already (``added`` / ``modified``) and
  whether it holds the flagged line already;
* for a modified file, its change against the remote's copy, masked the
  same way, its changed lines taken from the original files.

The remote's copy is the one the round would have pushed on top of: the
newest commit it pulled, else the commit it recorded as ``from_commit`` — the
pair "Show what a round changed in each file" reads for a push.
"""

from __future__ import annotations

import difflib

from coffer.application.sync.round_deps import RoundDeps
from coffer.application.sync.round_diff import MAX_BYTES, MAX_LINES
from coffer.domain.plaintext_shape import split_rows
from coffer.domain.sync.errors import SyncPlaintextNotListed, SyncRoundDiffUnavailable
from coffer.domain.sync.plaintext import MaskedLine, PlaintextContext, PlaintextFinding
from coffer.domain.sync.rounds import RoundRecord

#: Lines shown on each side of the flagged one.
CONTEXT = 3


def _text(raw: bytes | None) -> str | None:
    if raw is None or b"\0" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _remote_commit(record: RoundRecord) -> str | None:
    return record.pulled[0].version if record.pulled else record.from_commit


def _range(start: int, size: int) -> str:
    """A unified-diff hunk range, as ``difflib`` writes it."""
    begin = start + 1
    if size == 1:
        return str(begin)
    return f"{begin - 1 if size == 0 else begin},{size}"


def _masked_diff(
    old: list[str], new: list[str], path: str, masked: tuple[list[str], list[str]]
) -> tuple[str | None, int, int]:
    """The unified diff of ``old`` against ``new`` — their opcodes decide which
    lines changed — showing each line masked (``masked`` is the two files'
    lines, masked as whole files)."""
    old_masked, new_masked = masked
    out = [f"--- remote/{path}\n", f"+++ local/{path}\n"]
    added = removed = 0
    for group in difflib.SequenceMatcher(None, old, new).get_grouped_opcodes(3):
        first, last = group[0], group[-1]
        out.append(
            f"@@ -{_range(first[1], last[2] - first[1])} "
            f"+{_range(first[3], last[4] - first[3])} @@\n"
        )
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                out.extend(" " + line + "\n" for line in new_masked[j1:j2])
                continue
            if tag in ("replace", "delete"):
                out.extend("-" + line + "\n" for line in old_masked[i1:i2])
                removed += i2 - i1
            if tag in ("replace", "insert"):
                out.extend("+" + line + "\n" for line in new_masked[j1:j2])
                added += j2 - j1
        if len(out) > MAX_LINES:
            return None, 0, 0
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
    mask = d.mask_plaintext
    text = _text(d.git.blobs([found.blob]).get(found.blob))
    if text is None:
        raise SyncRoundDiffUnavailable
    rows = split_rows(text)
    new_masked = mask(text, path)
    lo, hi = max(1, line - CONTEXT), min(len(rows), line + CONTEXT)
    shown = [MaskedLine(n, *new_masked[n - 1]) for n in range(lo, hi + 1)]

    remote = _remote_commit(record)
    old_raw = d.git.read(remote, path) if remote and d.git.files(remote) else None
    if old_raw is None:
        return PlaintextContext(found, "added", False, tuple(shown))
    old = _text(old_raw) if len(old_raw) <= MAX_BYTES else None
    old_rows = split_rows(old) if old is not None else []
    on_remote = old is not None and 0 < line <= len(rows) and rows[line - 1] in old_rows
    diff: str | None = None
    added = removed = 0
    if old is not None and len(text.encode()) <= MAX_BYTES:
        old_masked = [m for m, _ in mask(old, path)]
        diff, added, removed = _masked_diff(
            old_rows, rows, path, (old_masked, [m for m, _ in new_masked])
        )
    return PlaintextContext(found, "modified", on_remote, tuple(shown), diff, added, removed)


__all__ = ["CONTEXT", "context"]
