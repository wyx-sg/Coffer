#!/usr/bin/env python3
"""Keep every ``~/.coffer`` path inside ``infrastructure/vault/home.py``.

That module is the one place that knows the root and each entry directly
under it (the five class directories, ``daemon.json``, ``logs/``, ``bin/`` …),
and it honours the one override, ``HOME``. A second construction elsewhere is
how a path drifts: it reads ``Path.home()`` where the rest reads ``HOME``, or
it keeps a directory the layout has since moved. This script parses every
module under ``backend/coffer/`` and ``backend/tests/support/`` and fails on
any of these outside the allow-list:

* the string ``".coffer"`` (or ``".coffer/…"``) — ``home / ".coffer"``,
  ``os.path.join(home, ".coffer")``;
* ``Path`` / ``expanduser`` / ``os.path.join`` given a string that starts
  with ``~/.coffer`` — ``Path("~/.coffer/logs").expanduser()``;
* an f-string that puts ``/.coffer`` right after an interpolated value —
  ``f"{Path.home()}/.coffer/runs.db"``;
* ``Path.home()`` joined straight to an entry of the layout —
  ``Path.home() / "vault"``.

Prose is not scanned: a docstring, a comment or a message that *names*
``~/.coffer/bin`` to a person is not a path Coffer builds.

Allowed:

* ``backend/coffer/infrastructure/vault/home.py`` — the paths module;
* ``backend/coffer/infrastructure/persistence/migrations/`` — a migration
  freezes the layout it was written against;
* ``backend/tests/support/real_home_guard.py`` — the real-home guard names
  the tree it protects;
* ``backend/tests/support/homes.py`` — the tests' isolated homes.

Stdlib-only.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
SCANNED = (BACKEND / "coffer", BACKEND / "tests" / "support")
PATHS_MODULE = BACKEND / "coffer" / "infrastructure" / "vault" / "home.py"
ALLOWED: tuple[Path, ...] = (
    PATHS_MODULE,
    BACKEND / "coffer" / "infrastructure" / "persistence" / "migrations",
    BACKEND / "tests" / "support" / "real_home_guard.py",
    BACKEND / "tests" / "support" / "homes.py",
)

#: Entries directly under ``~/.coffer``; ``Path.home() / <one of these>`` is a
#: Coffer path that forgot its root.
LAYOUT_ENTRIES = frozenset(
    {
        "vault",
        "local",
        "content",
        "derived",
        "runs.db",
        "logs",
        "bin",
        "daemon.json",
        "daemon-config.json",
        "daemon.lock",
        "master.key",
        "upstream-pids",
        "vendor",
        "eval-capture.jsonl",
        "proxy.json",
        "proxy-usage",
    }
)


#: Calls that turn a string into a path: ``Path("~/.coffer")``,
#: ``os.path.expanduser("~/.coffer")``, ``os.path.join("~/.coffer", …)``.
PATH_CALLS = frozenset({"Path", "PurePath", "PosixPath", "expanduser", "join"})


def _callee(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _is_allowed(path: Path) -> bool:
    return any(path == a or a in path.parents for a in ALLOWED)


def _is_root_name(value: str) -> bool:
    return value == ".coffer" or value.startswith(".coffer/")


def _is_home_call(node: ast.AST) -> bool:
    """``Path.home()`` / ``pathlib.Path.home()``."""
    return (
        isinstance(node, ast.Call)
        and not node.args
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "home"
        and (
            (isinstance(node.func.value, ast.Name) and node.func.value.id == "Path")
            or (isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "Path")
        )
    )


def scan_source(source: str, filename: str = "<string>") -> list[tuple[int, str]]:
    """Every ad-hoc Coffer path in ``source`` as ``(line, description)``."""
    tree = ast.parse(source, filename=filename)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _is_root_name(node.value):
                hits.append((node.lineno, f'"{node.value}"'))
        elif isinstance(node, ast.Call) and _callee(node) in PATH_CALLS:
            for arg in node.args:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and arg.value.startswith("~/.coffer")
                ):
                    hits.append((arg.lineno, f'{_callee(node)}("{arg.value}")'))
        elif isinstance(node, ast.JoinedStr):
            for before, part in zip(node.values, node.values[1:], strict=False):
                if (
                    isinstance(before, ast.FormattedValue)
                    and isinstance(part, ast.Constant)
                    and isinstance(part.value, str)
                    and part.value.startswith("/.coffer")
                ):
                    hits.append((node.lineno, "an f-string joining /.coffer"))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            right = node.right
            if (
                _is_home_call(node.left)
                and isinstance(right, ast.Constant)
                and right.value in LAYOUT_ENTRIES
            ):
                hits.append((node.lineno, f'Path.home() / "{right.value}"'))
    return sorted(set(hits))


def scan_tree(roots: tuple[Path, ...] = SCANNED) -> list[tuple[Path, int, str]]:
    """Every ad-hoc Coffer path under ``roots`` outside the allow-list."""
    found: list[tuple[Path, int, str]] = []
    for root in roots:
        for py in sorted(root.rglob("*.py")):
            if _is_allowed(py):
                continue
            try:
                hits = scan_source(py.read_text(encoding="utf-8"), str(py))
            except (SyntaxError, UnicodeDecodeError) as e:
                print(f"check_coffer_paths: cannot parse {py}: {e}", file=sys.stderr)
                continue
            found.extend((py, line, what) for line, what in hits)
    return found


def main() -> int:
    found = scan_tree()
    module = PATHS_MODULE.relative_to(REPO_ROOT)
    if not found:
        print(f"check_coffer_paths: OK — every ~/.coffer path comes from {module}.")
        return 0
    print(
        f"check_coffer_paths: FAIL — ~/.coffer paths built outside {module}:",
        file=sys.stderr,
    )
    for path, line, what in found:
        print(f"  {path.relative_to(REPO_ROOT)}:{line}: {what}", file=sys.stderr)
    print(
        f"Ask {module} for the path (add a function there for a new entry).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
