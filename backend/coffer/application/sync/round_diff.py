"""What a round changed in one file (spec vault-sync "Show what a round
changed in each file").

Nothing is stored for this: the diff is computed from the vault's git history
when asked, between two commits the round already records.

* ``applied`` — this machine's version before the round (``from_commit``) and
  after it (``to_commit``). The descriptor commit and a plaintext fold written
  after the merge change no content file, so the pair holds for every applied
  path.
* ``pushed`` — the remote tip the push went on top of, and ``to_commit``. That
  tip is the newest commit the round pulled (``pulled[0]``); a round that only
  pushed has no pulled commits and recorded the tip as ``from_commit``.

The path must be one the round lists for that side. A secret is never read.
"""

from __future__ import annotations

import difflib

from coffer.application.sync.round_deps import RoundDeps
from coffer.application.sync.views import RoundFileDiff
from coffer.domain.sync.errors import SyncRoundDiffUnavailable, SyncRoundFileNotListed
from coffer.domain.sync.rounds import RoundRecord
from coffer.domain.vault.layout import SECRET

#: A file bigger than this, or a diff longer, is not shown line by line.
MAX_BYTES = 200_000
MAX_LINES = 2_000

SIDES = ("applied", "pushed")


def _pair(record: RoundRecord, side: str) -> tuple[str | None, str | None]:
    if side == "applied":
        return record.from_commit, record.to_commit
    before = record.pulled[0].version if record.pulled else record.from_commit
    return before, record.to_commit


def _text(raw: bytes | None) -> str | None:
    """``""`` for an absent file, the text, or ``None`` when it is not text."""
    if raw is None:
        return ""
    if b"\0" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def file_diff(d: RoundDeps, record: RoundRecord, path: str, side: str) -> RoundFileDiff:
    listed = record.applied if side == "applied" else record.pushed
    if path not in {c.path for c in listed}:
        raise SyncRoundFileNotListed(path, "apply" if side == "applied" else "push")
    if path.startswith(SECRET + "/"):
        return RoundFileDiff(path, side, "secret")
    before, after = _pair(record, side)
    if not before or not after or not d.git.files(after) or not d.git.files(before):
        raise SyncRoundDiffUnavailable
    return between(d, path, side, before, after)


def between(
    d: RoundDeps, path: str, side: str, before: str | None, after: str | None
) -> RoundFileDiff:
    """``path`` from commit ``before`` to commit ``after``, line by line. A
    missing commit reads as an absent file; a secret is never read."""
    if path.startswith(SECRET + "/"):
        return RoundFileDiff(path, side, "secret")
    old = d.git.read(before, path) if before else None
    new = d.git.read(after, path) if after else None
    if max(len(old or b""), len(new or b"")) > MAX_BYTES:
        return RoundFileDiff(path, side, "too_large")
    old_text, new_text = _text(old), _text(new)
    if old_text is None or new_text is None:
        return RoundFileDiff(path, side, "binary")
    lines = list(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"before/{path}",
            tofile=f"after/{path}",
        )
    )
    if len(lines) > MAX_LINES:
        return RoundFileDiff(path, side, "too_large")
    added = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
    removed = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
    return RoundFileDiff(path, side, "text", "".join(lines), added, removed)


__all__ = ["MAX_BYTES", "MAX_LINES", "SIDES", "between", "file_diff"]
