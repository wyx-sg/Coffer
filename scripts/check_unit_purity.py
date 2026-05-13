#!/usr/bin/env python3
"""Enforce unit-tier purity: no I/O imports in backend/tests/unit/.

The unit tier (see agents/testing.md) tests pure logic — value objects,
domain functions, single-class behavior. Any test that needs to spawn a
subprocess, hit a real database, make HTTP calls, or boot the FastAPI
app belongs in the integration tier instead.

This script AST-scans `backend/tests/unit/**/*.py` and fails on imports
of modules associated with real I/O. Stdlib-only.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
UNIT_DIR = REPO_ROOT / "backend" / "tests" / "unit"

# Banned module roots. A key 'X' matches `import X`, `from X import ...`,
# `import X.Y`, and `from X.Y import ...`. Dotted keys (e.g. 'fastapi.testclient')
# ban a specific submodule but leave the parent package usable.
BANNED: dict[str, str] = {
    "subprocess": "spawns processes — belongs in integration tier",
    "sqlite3": "real database access — belongs in integration tier",
    "httpx": "HTTP client — belongs in integration tier",
    "fastapi.testclient": "boots the FastAPI app — belongs in integration tier",
    "socket": "network access — belongs in integration tier",
    "requests": "HTTP client — belongs in integration tier",
    "urllib.request": "HTTP client — belongs in integration tier",
    "aiohttp": "HTTP client — belongs in integration tier",
    "keyring": "real keyring access — belongs in integration tier (use a fake here)",
}


def banned_match(module: str) -> str | None:
    for banned in BANNED:
        if module == banned or module.startswith(banned + "."):
            return banned
    return None


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"check_unit_purity: cannot parse {path}: {e}", file=sys.stderr)
        return []
    hits: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                match = banned_match(alias.name)
                if match:
                    hits.append((node.lineno, alias.name, BANNED[match]))
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            match = banned_match(node.module)
            if match:
                hits.append((node.lineno, node.module, BANNED[match]))
    return hits


def main() -> int:
    if not UNIT_DIR.exists():
        print(f"check_unit_purity: {UNIT_DIR.relative_to(REPO_ROOT)} not present — skipping.")
        return 0

    files = sorted(UNIT_DIR.rglob("*.py"))
    all_hits: list[tuple[Path, int, str, str]] = []
    for py in files:
        for lineno, module, reason in scan_file(py):
            all_hits.append((py, lineno, module, reason))

    if not all_hits:
        print(
            f"check_unit_purity: OK — {len(files)} file(s) under "
            f"{UNIT_DIR.relative_to(REPO_ROOT)} are pure."
        )
        return 0

    print("check_unit_purity: FAIL — banned imports in unit tier:", file=sys.stderr)
    for path, lineno, module, reason in all_hits:
        print(f"  {path.relative_to(REPO_ROOT)}:{lineno}: `{module}` — {reason}", file=sys.stderr)
    print("\n  Move these tests to backend/tests/integration/.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
