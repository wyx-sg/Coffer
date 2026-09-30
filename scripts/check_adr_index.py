#!/usr/bin/env python3
"""Keep the ADR directory and its index level with each other.

`docs/decisions/` records the live design, one ADR per decision, and
`docs/decisions/README.md` is its index. ADRs get rewritten, merged and deleted
as decisions change, and two things drift silently when they do:

  1. A relative markdown link inside `docs/decisions/` points at an ADR (or
     any other file) that is gone. Links inside a fenced block are examples
     (the README's own template) and are skipped.
  2. The index stops listing exactly the ADRs that exist: a new ADR without a
     row, or a row for one that was deleted or renamed.

Stdlib only. Exits non-zero with one line per problem.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DECISIONS = REPO_ROOT / "docs" / "decisions"

MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
#: An index row links the ADR file as its first cell: `| [Title](slug.md) | … |`
INDEX_ROW = re.compile(r"^\|\s*\[[^\]]+\]\(([^)]+\.md)\)")


def adr_files(decisions: Path) -> list[Path]:
    """Every ADR, which is one per decision."""
    return sorted(p for p in decisions.glob("*.md") if p.name != "README.md")


def check_links(decisions: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(decisions.glob("*.md")):
        fenced = False
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                continue
            for match in MD_LINK.finditer(line):
                target = match.group(1).split("#")[0]
                if not target or target.startswith(("http://", "https://", "mailto:", "/")):
                    continue
                if not (path.parent / target).resolve().exists():
                    errors.append(f"{path.name}:{lineno}: dead link {target}")
    return errors


def check_index(decisions: Path) -> list[str]:
    readme = decisions / "README.md"
    if not readme.is_file():
        return ["README.md: the ADR index is missing"]
    expected = {p.name for p in adr_files(decisions)}
    listed = {
        match.group(1)
        for line in readme.read_text(encoding="utf-8").splitlines()
        if (match := INDEX_ROW.match(line))
    }
    errors = [f"README.md: index has no row for {name}" for name in sorted(expected - listed)]
    errors += [
        f"README.md: index lists {name}, which is not an ADR file"
        for name in sorted(listed - expected)
    ]
    return errors


def main() -> int:
    adrs = adr_files(DECISIONS)
    if not adrs:
        print("check_adr_index: no ADRs found — is docs/decisions/ present?", file=sys.stderr)
        return 1
    errors = check_links(DECISIONS) + check_index(DECISIONS)
    if errors:
        for error in errors:
            print(f"docs/decisions/{error}", file=sys.stderr)
        print(f"\ncheck_adr_index: {len(errors)} problem(s)", file=sys.stderr)
        return 1
    print(f"check_adr_index: {len(adrs)} ADRs, all indexed, all links resolve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
