#!/usr/bin/env python3
"""Enforce file-size limits documented in agents/stack.md.

Limits (see agents/stack.md "Code Style"):
  * Backend Python file:    <= 400 lines
  * Frontend page (.tsx):   <= 200 lines
  * Frontend component:     <= 250 lines
  * Frontend hook:          <= 300 lines

Each rule is (glob, limit, label); first match wins. Generated dirs and lock
files are excluded. Stdlib-only.

Exits non-zero on any file that exceeds its limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Order matters: a file is classified by the first rule it matches.
# Hooks come before components, components before pages, only so that a
# more-specific path wins if the directory naming ever overlaps.
RULES: list[tuple[str, int, str]] = [
    ("frontend/src/hooks/**/*.ts", 300, "frontend hook"),
    ("frontend/src/hooks/**/*.tsx", 300, "frontend hook"),
    ("frontend/src/components/**/*.tsx", 250, "frontend component"),
    ("frontend/src/components/**/*.ts", 250, "frontend component"),
    ("frontend/src/pages/**/*.tsx", 200, "frontend page"),
    ("frontend/src/pages/**/*.ts", 200, "frontend page"),
    ("backend/coffer/**/*.py", 400, "backend Python"),
]

EXCLUDED_DIR_PARTS = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".vite",
    ".next",
}


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_PARTS for part in path.parts)


def count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        return 0


def find_violations() -> list[tuple[Path, int, int, str]]:
    seen: set[Path] = set()
    violations: list[tuple[Path, int, int, str]] = []

    for glob, limit, label in RULES:
        for path in REPO_ROOT.glob(glob):
            if path in seen or not path.is_file() or is_excluded(path):
                continue
            seen.add(path)
            lines = count_lines(path)
            if lines > limit:
                violations.append((path, lines, limit, label))

    return violations


def main() -> int:
    violations = find_violations()
    if not violations:
        print("check_file_sizes: OK")
        return 0

    print("check_file_sizes: FAIL — files exceed their tier limit:", file=sys.stderr)
    for path, lines, limit, label in violations:
        rel = path.relative_to(REPO_ROOT)
        print(f"  {rel}: {lines} lines > {limit} ({label})", file=sys.stderr)
    print(
        "\n  Limits are guidance for splitting. See agents/stack.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
