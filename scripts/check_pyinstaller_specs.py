#!/usr/bin/env python3
"""Keep the PyInstaller specs level with the tree.

The four specs under `backend/` name paths as strings: the entry script each
binary is frozen from, and the data files it has to carry because they are not
importable modules. Nothing imports those strings, so when the file they point
at is deleted or moved the spec keeps naming it and every gate stays green —
PyInstaller is the only thing that reads them, and no CI job runs it. The cost
lands on whoever next builds a release: `Unable to find '<path>' when adding
binary and data files`, after the earlier binaries have already been built.

That is how `coffer.spec` went on carrying
`coffer/application/knowledge/skill_assets` for the whole time the knowledge
skill had been rendered in code instead of shipped as a file.

Checks, for each `backend/*.spec`:

  1. The `Analysis([...])` entry script exists.
  2. Every source path in `datas=[...]` exists.

Both are resolved from `backend/`, which is where the specs' own paths are
relative to and where `scripts/build_binaries.sh` runs PyInstaller.

Stdlib only. Exits non-zero with one line per stale path.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"


def _analysis_call(tree: ast.Module) -> ast.Call | None:
    """The spec's `Analysis(...)` call, or None when it has none."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Analysis"
        ):
            return node
    return None


def _string(node: ast.expr) -> str | None:
    """The literal value of `node`, or None when it is not a plain string.

    A computed path (a join, a variable) is out of this gate's reach — it
    reports nothing rather than guessing at what it would evaluate to.
    """
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def declared_paths(spec: Path) -> list[str]:
    """Every literal path `spec` asks PyInstaller to read.

    The entry script (`Analysis`'s first positional argument, a list) and the
    source half of each `datas` pair. `binaries` follows the same shape but is
    empty in every spec here; it is read too, so that stays true.
    """
    call = _analysis_call(ast.parse(spec.read_text(encoding="utf-8")))
    if call is None:
        return []

    paths: list[str] = []
    if call.args and isinstance(call.args[0], ast.List):
        paths.extend(p for p in (_string(e) for e in call.args[0].elts) if p)
    for keyword in call.keywords:
        if keyword.arg not in {"datas", "binaries"}:
            continue
        if not isinstance(keyword.value, ast.List):
            continue
        for entry in keyword.value.elts:
            if isinstance(entry, ast.Tuple) and entry.elts:
                source = _string(entry.elts[0])
                if source:
                    paths.append(source)
    return paths


def main() -> int:
    specs = sorted(BACKEND.glob("*.spec"))
    if not specs:
        print("check_pyinstaller_specs: no backend/*.spec found", file=sys.stderr)
        return 1

    stale: list[str] = []
    checked = 0
    for spec in specs:
        for path in declared_paths(spec):
            checked += 1
            if not (BACKEND / path).exists():
                stale.append(f"{spec.name}: names '{path}', which does not exist under backend/")

    if stale:
        for line in stale:
            print(line, file=sys.stderr)
        return 1

    print(f"check_pyinstaller_specs: OK — {len(specs)} spec(s), {checked} path(s) all present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
