"""Pure-Python literal search, for a machine with no ripgrep on its PATH.

``rg`` is the mechanism (see ``grep``), not a requirement: an installation
without it still has a knowledge directory, and an agent asking which line
mentions a phrase must get the same answer, just slower. So this module walks
the same files ripgrep would — every non-hidden file under the roots, in
order — and applies the same rules: a regex matched line by line, at most
``cap`` hits per file so "more exist" stays visible, hidden entries skipped
(FR-052), binary files skipped, and a wall-clock budget that reports
truncation rather than "no matches" when it runs out.

Ripgrep's regex dialect (Rust's) and Python's ``re`` agree on everything a
knowledge search plausibly contains — literals, classes, anchors, ``(?i)`` —
so callers see one behaviour from both engines.
"""

from __future__ import annotations

import os
import pathlib
import re
import time

from coffer.domain.errors import GrepPatternInvalid
from coffer.domain.knowledge.entry import GrepMatch
from coffer.infrastructure.knowledge import paths

#: How much of a file to read before deciding it is binary. Ripgrep looks for a
#: NUL byte in the first buffer it fills; knowledge files are small enough
#: that reading the head and then the whole file costs nothing.
_BINARY_PROBE_BYTES = 8192


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """The regex ripgrep would have been handed, or the error it would raise."""
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise GrepPatternInvalid(pattern, f"regex parse error: {exc}") from exc


def _files(root: pathlib.Path) -> list[pathlib.Path]:
    """Every non-hidden regular file under ``root``, in a stable order."""
    if root.is_file():
        return [root] if not root.name.startswith(".") else []
    found: list[pathlib.Path] = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            candidate = pathlib.Path(directory) / name
            if candidate.is_file():
                found.append(candidate)
    return found


def _lines_of(path: pathlib.Path) -> list[str] | None:
    """A file's lines, or ``None`` when it is unreadable or binary."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:_BINARY_PROBE_BYTES]:
        return None
    text = data.decode("utf-8", errors="replace")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def grep_tree(
    roots: list[pathlib.Path],
    pattern: str,
    cap: int,
    *,
    timeout_s: float,
) -> tuple[list[GrepMatch], bool]:
    """Search ``roots`` for ``pattern``; ``(matches, timed_out)``.

    Collects at most ``cap`` matches in total and at most ``cap`` per file —
    ripgrep's ``--max-count`` applied the same way — so the caller can tell
    truncation from exhaustion exactly as it does with ``rg``'s output.
    """
    regex = compile_pattern(pattern)
    deadline = time.monotonic() + timeout_s
    matches: list[GrepMatch] = []
    for root in roots:
        for path in _files(root):
            if time.monotonic() > deadline:
                return matches, True
            lines = _lines_of(path)
            if lines is None:
                continue
            per_file = 0
            relpath = paths.relative_of(path)
            for number, line in enumerate(lines, start=1):
                if regex.search(line) is None:
                    continue
                matches.append(GrepMatch(path=relpath, line_number=number, line=line))
                per_file += 1
                if len(matches) >= cap:
                    return matches, False
                if per_file >= cap:
                    break
    return matches, False
