#!/usr/bin/env python3
"""Decide whether a change needs the test jobs, from the paths it touches.

`.github/workflows/verify.yml` feeds this the files a pull request changes (one
per line on stdin) and skips the backend and frontend test jobs when every one
of them is prose that no test reads. The static gates (`lint`, the acceptance
audit, the secrets scan) run on every change regardless — they are the ones
that check prose: ADR numbering, spec citations, the architecture doc, removed
commands, OpenSpec scenarios.

Prose here is a Markdown file, or anything under `docs/` or `docs-site/`, that
is NOT one of:

- under a tree whose Markdown is data a test or a gate reads — `openspec/`
  (specs are validated and their scenarios audited), `.agents/`, `.claude/`,
  `backend/` (skill bodies ship inside the package), `frontend/`, `e2e/`,
  `evals/`;
- the root `README.md`, which a distribution test asserts on;
- `docs-site/public/`, which serves the install script a test runs.

Anything unlisted counts as code, so a new kind of file errs on the side of
running the tests. An empty change list counts as code for the same reason.

Prints ``code=true`` or ``code=false`` (the `$GITHUB_OUTPUT` line format).
"""

from __future__ import annotations

import sys
from collections.abc import Iterable

#: Trees whose Markdown is read by a test or a gate, so editing it is a code change.
_DATA_TREES: tuple[str, ...] = (
    "openspec/",
    ".agents/",
    ".claude/",
    "backend/",
    "frontend/",
    "e2e/",
    "evals/",
    "docs-site/public/",
)

#: Individual prose-looking files a test reads.
_DATA_FILES: frozenset[str] = frozenset({"README.md"})

#: Trees that hold nothing but documentation.
_DOC_TREES: tuple[str, ...] = ("docs/", "docs-site/")


def is_prose(path: str) -> bool:
    """True when ``path`` is documentation no test reads."""
    path = path.strip().removeprefix("./")
    if not path or path in _DATA_FILES or path.startswith(_DATA_TREES):
        return False
    return path.startswith(_DOC_TREES) or path.endswith(".md")


def needs_tests(paths: Iterable[str]) -> bool:
    """True unless every (non-blank) path is prose; an empty change needs tests."""
    changed = [p for p in (line.strip() for line in paths) if p]
    return not changed or not all(is_prose(p) for p in changed)


def main() -> int:
    print(f"code={'true' if needs_tests(sys.stdin) else 'false'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
