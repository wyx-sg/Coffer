"""What one assistant reply changed in one file (spec chat "Record what each
reply changed in each file").

The diff is the reply's whole effect on the file — Claude Code's content before
the reply's first write against its content when the reply ended, Codex's
per-change diffs in order — as unified text. A file too large to keep or not
text keeps only its counts and says why the diff is left out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: Why a file has counts but no diff.
DiffOmitted = Literal["binary", "too_large"]

#: A file over this many bytes is recorded without a diff.
MAX_DIFF_FILE_BYTES = 1024 * 1024

#: A reply that writes more files than this records the first ones only.
MAX_REPLY_FILES = 200


@dataclass(frozen=True)
class ReplyFile:
    """One file a reply changed, with its added and removed line counts."""

    path: str
    added: int
    removed: int
    diff: str | None = None
    diff_omitted: DiffOmitted | None = None


@dataclass(frozen=True)
class ReplyFileSummary:
    """A recorded file as the reply's list shows it: counts, and whether a diff
    can be opened — without the diff text itself."""

    path: str
    added: int
    removed: int
    has_diff: bool
