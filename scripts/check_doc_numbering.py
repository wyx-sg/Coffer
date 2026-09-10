#!/usr/bin/env python3
"""ADRs and specs are named, not numbered — keep it that way.

Both directories used to use a zero-padded ordinal, and both kept deleting
things: three specs and thirteen ADRs went away in one simplification pass
alone. Every deletion left a hole, every hole invited compaction, and
compaction would have re-pointed each surviving mention of a retired number at
whatever inherited it. That is not hypothetical — one ADR spent months linking
`ADR-026-per-agent-mcp-scoping.md` after a different decision had taken 026.

A name cannot do that. A reference to a deleted name is visibly dead; a
reference to a recycled number is quietly wrong. So the numbers are gone, and
this script holds the line:

  1. No `ADR-<digits>` and no `spec <digits>` token survives in a tracked file.
     Text about something that no longer has a directory says what it *was*.
  2. No ADR filename and no spec directory carries a number.
  3. Every relative markdown link inside `docs/decisions/` resolves.
  4. The ADR README index lists exactly the ADRs that exist, in both
     languages, each linking its own language's file.

Stdlib only. Exits non-zero on any failure.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DECISIONS = REPO_ROOT / "docs" / "decisions"
SPECS = REPO_ROOT / "specs"

NUMBERED_ADR = re.compile(r"ADR-\d+")
#: `spec 001`, `Specs 004`, `spec-009` — every shape the prose used to take.
NUMBERED_SPEC = re.compile(r"\b[Ss]pecs?[ -](00[1-9]|0[1-9][0-9])\b")
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
#: An index row links the ADR file as its first cell: `| [Title](slug.md) | … |`
INDEX_ROW = re.compile(r"^\|\s*\[[^\]]+\]\(([^)]+\.md)\)")

EXCLUDED_PREFIXES = ("docs-site/node_modules/", "frontend/node_modules/")
#: This file names the retired patterns on purpose, in the docstring above.
SELF = "scripts/check_doc_numbering.py"


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [f for f in out if not f.startswith(EXCLUDED_PREFIXES) and f != SELF]


def adr_files() -> list[Path]:
    """Every English ADR, which is one per decision."""
    return sorted(
        p
        for p in DECISIONS.glob("*.md")
        if not p.name.endswith(".zh.md") and p.name != "README.md"
    )


def check_no_numbers(files: list[str]) -> list[str]:
    errors: list[str] = []
    for rel in files:
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if NUMBERED_ADR.search(line):
                errors.append(
                    f"{rel}:{lineno}: ADRs are named, not numbered — "
                    f"name the decision instead"
                )
            if NUMBERED_SPEC.search(line):
                errors.append(
                    f"{rel}:{lineno}: specs are named, not numbered — "
                    f"name the spec instead"
                )
    for path in DECISIONS.glob("ADR-*"):
        errors.append(f"{path.relative_to(REPO_ROOT)}: filename still carries a number")
    for path in SPECS.iterdir():
        if path.is_dir() and re.match(r"^\d", path.name):
            errors.append(
                f"{path.relative_to(REPO_ROOT)}: directory still carries a number"
            )
    return errors


def check_links() -> list[str]:
    errors: list[str] = []
    for path in sorted(DECISIONS.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        fenced = False
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            # A link inside a fence is an example — the README's own ADR
            # template writes `[<title>](<file>.md)` there.
            if fenced:
                continue
            for match in MD_LINK.finditer(line):
                target = match.group(1).split("#")[0]
                if not target or target.startswith(
                    ("http://", "https://", "mailto:", "/")
                ):
                    continue
                if not (path.parent / target).resolve().exists():
                    errors.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno}: dead link {target}"
                    )
    return errors


def check_index() -> list[str]:
    errors: list[str] = []
    english = {p.name for p in adr_files()}
    for readme, expected in (
        (DECISIONS / "README.md", english),
        (DECISIONS / "README.zh.md", {n.replace(".md", ".zh.md") for n in english}),
    ):
        listed = {
            match.group(1)
            for line in readme.read_text(encoding="utf-8").splitlines()
            if (match := INDEX_ROW.match(line))
        }
        rel = readme.relative_to(REPO_ROOT)
        for name in sorted(expected - listed):
            errors.append(f"{rel}: index has no row for {name}")
        for name in sorted(listed - expected):
            errors.append(f"{rel}: index lists {name}, which is not an ADR file")
    return errors


def main() -> int:
    adrs = adr_files()
    if not adrs:
        print(
            "check_doc_numbering: no ADRs found — is docs/decisions/ present?",
            file=sys.stderr,
        )
        return 1

    errors = check_no_numbers(tracked_files()) + check_links() + check_index()
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"\ncheck_doc_numbering: {len(errors)} problem(s)", file=sys.stderr)
        return 1
    specs = sum(1 for p in SPECS.iterdir() if p.is_dir())
    print(
        f"check_doc_numbering: {len(adrs)} ADRs and {specs} specs, all named, all links resolve"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
