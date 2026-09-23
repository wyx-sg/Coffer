#!/usr/bin/env python3
"""Keep `docs/architecture.md` level with the tree.

Two things drift silently in that document, and both have: the code-layout
tree (packages get added, moved or deleted without the tree following) and
the builtin-tool roster (a slice registers a tool the document never names).
This gate fails `make lint` on either.

Checks:

  1. Every package directory one level under `backend/coffer/{domain,
     application,infrastructure,surfaces}` is named, under its own layer, in
     the first fenced block that starts with `backend/coffer/`.
  2. Every file or directory that block names under a layer exists on disk —
     so a deleted module cannot linger in the tree.
  3. Every builtin tool declared as `BuiltinTool(name="<x>")` anywhere under
     `backend/coffer/application/`, plus the gateway's own `search_tools`,
     appears as `coffer__<x>` somewhere in the document.

Stdlib only. Exits non-zero with one line per drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPO_ROOT / "backend" / "coffer"
LAYERS = ("domain", "application", "infrastructure", "surfaces")
DOCS = (REPO_ROOT / "docs" / "architecture.md",)
TOOL_PREFIX = "coffer__"
_SKIP_DIRS = {"__pycache__"}
_TOOL_DECL = re.compile(r"BuiltinTool\(\s*name=\"([a-z_]+)\"")
# One tree "cell" is four columns: `│   `, `    `, `├── ` or `└── `.
_TREE_CELL = re.compile(r"(?:│   |    |├── |└── )")


def packages_on_disk() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for layer in LAYERS:
        found[layer] = {
            child.name
            for child in (PACKAGE_ROOT / layer).iterdir()
            if child.is_dir()
            and child.name not in _SKIP_DIRS
            and not child.name.startswith(".")
        }
    return found


def builtin_tool_names() -> set[str]:
    names: set[str] = set()
    for path in (PACKAGE_ROOT / "application").rglob("*.py"):
        names.update(_TOOL_DECL.findall(path.read_text(encoding="utf-8")))
    gateway = PACKAGE_ROOT / "application" / "mcp" / "gateway_builtin.py"
    if gateway.exists() and '"search_tools"' in gateway.read_text(encoding="utf-8"):
        names.add("search_tools")
    return names


def layout_block(text: str) -> list[str] | None:
    """Lines of the first fenced block whose first line is `backend/coffer/`."""
    in_block = False
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("```"):
            if in_block:
                return lines
            in_block = True
            continue
        if in_block:
            if not lines and line.strip() != "backend/coffer/":
                in_block = False
                continue
            lines.append(line)
    return None


def parse_tree(lines: list[str]) -> dict[str, set[str]]:
    """`{layer: {entry, ...}}` for depth-1 layers and their depth-2 entries."""
    tree: dict[str, set[str]] = {}
    layer: str | None = None
    for line in lines[1:]:
        m = re.match(r"((?:│   |    |├── |└── )+)(\S+)", line)
        if not m:
            continue
        depth = len(_TREE_CELL.findall(m.group(1)))
        name = m.group(2)
        if depth == 1:
            layer = name.rstrip("/")
            tree.setdefault(layer, set())
        elif depth == 2 and layer is not None:
            tree[layer].add(name)
    return tree


def check_doc(doc: Path, on_disk: dict[str, set[str]], tools: set[str]) -> list[str]:
    rel = doc.relative_to(REPO_ROOT)
    text = doc.read_text(encoding="utf-8")
    problems: list[str] = []

    block = layout_block(text)
    if block is None:
        return [f"{rel}: no fenced code-layout block starting with `backend/coffer/`"]
    tree = parse_tree(block)
    for layer in LAYERS:
        named = tree.get(layer)
        if named is None:
            problems.append(
                f"{rel}: layer `{layer}/` is missing from the code-layout tree"
            )
            continue
        for pkg in sorted(
            on_disk[layer] - {n.rstrip("/") for n in named if n.endswith("/")}
        ):
            problems.append(
                f"{rel}: `{layer}/{pkg}/` exists on disk but the code-layout tree does not name it"
            )
        for entry in sorted(named):
            if not (PACKAGE_ROOT / layer / entry.rstrip("/")).exists():
                problems.append(
                    f"{rel}: the code-layout tree names `{layer}/{entry}` but it is not on disk"
                )

    for name in sorted(tools):
        if f"{TOOL_PREFIX}{name}" not in text:
            problems.append(
                f"{rel}: builtin tool `{TOOL_PREFIX}{name}` is registered but never named"
            )
    return problems


def main() -> int:
    on_disk = packages_on_disk()
    tools = builtin_tool_names()
    problems: list[str] = []
    for doc in DOCS:
        if not doc.exists():
            problems.append(f"{doc.relative_to(REPO_ROOT)}: missing")
            continue
        problems.extend(check_doc(doc, on_disk, tools))
    if problems:
        print(
            "check_architecture_doc: FAIL — architecture doc drifted from the tree:",
            file=sys.stderr,
        )
        for line in problems:
            print(f"  - {line}", file=sys.stderr)
        return 1
    n_pkgs = sum(len(v) for v in on_disk.values())
    print(
        f"check_architecture_doc: OK — {n_pkgs} packages and {len(tools)} builtin tools named in the document"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
