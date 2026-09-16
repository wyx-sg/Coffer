#!/usr/bin/env python3
"""Enforce per-tier file-size limits.

Limits:
  * Backend Python file:    <= 400 lines  (agents/stack.md "Code Style")
  * Desktop shell (.rs):    <= 400 lines  (agents/stack.md "Desktop Shell")
  * Frontend page (.tsx):   <= 200 lines
  * Frontend component:     <= 250 lines
  * Frontend hook:          <= 300 lines
  * Frontend utility:       <= 300 lines

The frontend tiers have no prose home — RULES below is their definition, and
the directories it names are the ones agents/frontend.md §2 mandates.

Each rule is (glob, limit, label); first match wins. Generated dirs and lock
files are excluded. Stdlib-only.

Exits non-zero on any file that exceeds its limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Order matters: a file is classified by the first rule it matches.
# More-specific paths must appear before catch-all patterns for the same tree.
#
# The globs track the layout agents/frontend.md §2 mandates — pages in
# `src/pages/`, feature components in `src/components/<x>/`, every query and
# mutation in `src/lib/hooks/useX.ts`, and feature-owned pure helpers elsewhere
# under `src/lib/`. There were once rules for `src/lib/components/**` and
# `src/hooks/**` as well; the first moved to `src/components/` and the second
# never existed, and both left globs that matched nothing while the directories
# they should have named were already ruled below. A glob for a path the
# convention does not allow is worse than no glob: it reads as permission.
RULES: list[tuple[str, int, str]] = [
    # --- frontend/src/lib --- (specific first, catch-all last)
    ("frontend/src/lib/hooks/**/*.ts", 300, "frontend hook"),
    ("frontend/src/lib/hooks/**/*.tsx", 300, "frontend hook"),
    ("frontend/src/lib/**/*.ts", 300, "frontend utility"),
    ("frontend/src/lib/**/*.tsx", 300, "frontend utility"),
    # --- frontend/src/{components,pages} ---
    ("frontend/src/components/**/*.tsx", 250, "frontend component"),
    ("frontend/src/components/**/*.ts", 250, "frontend component"),
    ("frontend/src/pages/**/*.tsx", 200, "frontend page"),
    ("frontend/src/pages/**/*.ts", 200, "frontend page"),
    # --- backend ---
    ("backend/coffer/**/*.py", 400, "backend Python"),
    # --- desktop shell (Tauri/Rust) ---
    # Same 400-line cap as backend Python. The shell was split across modules
    # to stay under it; without a rule here that split was honoured by hand.
    ("desktop/src/**/*.rs", 400, "desktop Rust"),
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

# Marker present in the first 5 lines of openapi-typescript generated files.
_GENERATED_MARKER = "Do not make direct changes"


# The generated marker only ever appears in openapi-typescript output, which
# is always TypeScript. Restricting the marker check to .ts/.tsx files closes
# the evasion where any source file (e.g. a bloated backend .py) could dodge
# the size cap merely by quoting the marker string in a top-of-file comment
# (CODE-045).
_GENERATED_SUFFIXES = {".ts", ".tsx"}


def _is_generated(path: Path) -> bool:
    """Return True if the file is auto-generated (should not be size-checked)."""
    if path.suffix not in _GENERATED_SUFFIXES:
        return False
    try:
        with path.open(encoding="utf-8") as fh:
            for _ in range(5):
                line = fh.readline()
                if not line:
                    break
                if _GENERATED_MARKER in line:
                    return True
    except (OSError, UnicodeDecodeError):
        pass
    return False


def is_excluded(path: Path) -> bool:
    # Never size-check actual test files — they grow with the breadth of
    # coverage, not with the complexity of a single production module. Only
    # genuine *.test.ts/.tsx / *.spec.ts/.tsx names qualify (a bare ".test."
    # substring elsewhere does not), so a production module can't dodge the cap
    # by smuggling ".test." into its name (CODE-045).
    if path.suffix in _GENERATED_SUFFIXES and (
        ".test." in path.name or ".spec." in path.name
    ):
        return True
    if any(part in EXCLUDED_DIR_PARTS for part in path.parts):
        return True
    return _is_generated(path)


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
