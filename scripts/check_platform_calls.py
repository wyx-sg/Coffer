#!/usr/bin/env python3
"""Keep operating-system checks inside ``backend/coffer/infrastructure/platform/``.

Coffer's foundation must not hard-code macOS. The rule that makes that true is
that exactly one package asks which OS it runs on; everything else asks that
package (the application through ``PlatformPort``). import-linter cannot hold
this line — ``sys`` and ``platform`` are importable everywhere, and the check
is an attribute read, not an import — so this script parses every module under
``backend/coffer/`` and fails on any of these outside the allowed package:

* a read of ``sys.platform`` (``if sys.platform == "win32"``, ``startswith``);
* a call to ``platform.system()`` / ``release()`` / ``mac_ver()`` /
  ``win32_ver()`` / ``libc_ver()`` / ``freedesktop_os_release()`` /
  ``uname()`` / ``version()`` / ``platform()``;
* a read of ``os.name`` or a call to ``os.uname()``;
* ``from sys import platform``, ``from os import name``, or ``from platform
  import <any of the calls above>`` — the same reads under another name.

Tests are not scanned: pinning ``sys.platform`` is how a test simulates a host.
Stdlib-only.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / "backend" / "coffer"
#: The one package allowed to ask which OS this is.
ALLOWED = PACKAGE_DIR / "infrastructure" / "platform"

#: ``platform.<fn>()`` calls that identify the host OS.
PLATFORM_CALLS = frozenset(
    {
        "system",
        "release",
        "version",
        "mac_ver",
        "win32_ver",
        "win32_edition",
        "libc_ver",
        "freedesktop_os_release",
        "uname",
        "platform",
    }
)
#: ``<module>.<attr>`` reads that identify the host OS.
ATTRIBUTE_READS = {("sys", "platform"), ("os", "name")}
#: ``<module>.<fn>()`` calls outside ``platform`` that identify the host OS.
OTHER_CALLS = {("os", "uname"), ("sys", "getwindowsversion")}


def _is_allowed(path: Path) -> bool:
    return path == ALLOWED or ALLOWED in path.parents


def _module_aliases(tree: ast.AST) -> dict[str, str]:
    """Local names bound to ``sys`` / ``os`` / ``platform`` (``import os as _os``)."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in {"sys", "os", "platform"}:
                    aliases[alias.asname or alias.name] = alias.name
    return aliases


def scan_source(source: str, filename: str = "<string>") -> list[tuple[int, str]]:
    """Every OS check in ``source`` as ``(line, description)``."""
    tree = ast.parse(source, filename=filename)
    aliases = _module_aliases(tree)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {"sys", "os", "platform"}:
            for alias in node.names:
                name = alias.name
                if (
                    (node.module == "sys" and name in {"platform", "getwindowsversion"})
                    or (node.module == "os" and name in {"name", "uname"})
                    or (node.module == "platform" and (name in PLATFORM_CALLS or name == "*"))
                ):
                    hits.append((node.lineno, f"from {node.module} import {name}"))
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            module = aliases.get(node.value.id)
            if module is None:
                continue
            pair = (module, node.attr)
            if pair in ATTRIBUTE_READS or pair in OTHER_CALLS:
                hits.append((node.lineno, f"{module}.{node.attr}"))
            elif module == "platform" and node.attr in PLATFORM_CALLS:
                hits.append((node.lineno, f"platform.{node.attr}()"))
    return sorted(set(hits))


def scan_tree(root: Path) -> list[tuple[Path, int, str]]:
    """Every OS check under ``root`` outside the allowed package."""
    found: list[tuple[Path, int, str]] = []
    for py in sorted(root.rglob("*.py")):
        if _is_allowed(py):
            continue
        try:
            source = py.read_text(encoding="utf-8")
            hits = scan_source(source, str(py))
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"check_platform_calls: cannot parse {py}: {e}", file=sys.stderr)
            continue
        found.extend((py, line, what) for line, what in hits)
    return found


def main() -> int:
    found = scan_tree(PACKAGE_DIR)
    if not found:
        print(f"check_platform_calls: OK — no OS checks outside {ALLOWED.relative_to(REPO_ROOT)}/.")
        return 0
    print("check_platform_calls: FAIL — OS checks outside the platform package:", file=sys.stderr)
    for path, line, what in found:
        print(f"  {path.relative_to(REPO_ROOT)}:{line}: `{what}`", file=sys.stderr)
    print(
        "\n  Ask coffer.infrastructure.platform instead: from application/ through\n"
        "  PlatformPort (application/platform_port.py), from infrastructure/ by importing\n"
        "  the platform module directly. See docs-site/architecture/platform.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
