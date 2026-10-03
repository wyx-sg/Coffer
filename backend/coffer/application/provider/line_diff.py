"""A unified line diff of one file's before and after, as the change preview shows it.

Pure: text in, numbered lines out. Three lines of context around each hunk, the
hunk header worded the way ``diff -u`` words it (``@@ -12,9 +12,4 @@``).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Literal

_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")


@dataclass(frozen=True)
class DiffRow:
    kind: Literal["context", "add", "remove", "hunk"]
    text: str
    old_no: int | None = None
    new_no: int | None = None


def line_diff(before: str | None, after: str | None) -> list[DiffRow]:
    """The rows of the diff from ``before`` to ``after`` (``None``: no file)."""
    old = (before or "").splitlines()
    new = (after or "").splitlines()
    rows: list[DiffRow] = []
    old_no = new_no = 0
    for line in difflib.unified_diff(old, new, lineterm="", n=3):
        if line.startswith(("---", "+++")):
            continue
        hunk = _HUNK.match(line)
        if hunk:
            old_no, new_no = int(hunk.group(1)), int(hunk.group(2))
            rows.append(DiffRow("hunk", line))
        elif line.startswith("+"):
            rows.append(DiffRow("add", line[1:], None, new_no))
            new_no += 1
        elif line.startswith("-"):
            rows.append(DiffRow("remove", line[1:], old_no, None))
            old_no += 1
        else:
            rows.append(DiffRow("context", line[1:], old_no, new_no))
            old_no += 1
            new_no += 1
    return rows


__all__ = ["DiffRow", "line_diff"]
