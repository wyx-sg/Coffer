#!/usr/bin/env python3
"""Keep agent-specific branches inside the agent descriptor and its facets.

ADR agent-mechanisms-are-optional-facets-on-the-descriptor: per-agent values
live in the descriptor table, per-agent mechanisms in the facet
implementations bound to it at the composition root, and nothing else asks
"which agent is this?". import-linter cannot hold that line — ``AgentType`` is
importable everywhere, and the tell is naming a member, not importing the
enum — so this script parses every module under ``backend/coffer/`` and fails
on any of these outside the allowed places:

* a member of ``AgentType`` named directly (``AgentType.CODEX``), whether in a
  comparison, a branch, a dict key or a default — under any local alias;
* a comparison or ``match`` case against an agent type's literal value
  (``agent_key == "claude_code"``), the same branch spelled as a string.

Constructing a member from a value (``AgentType(value)``) and iterating the
enum are fine: neither says which agent is which.

The allowed places are ``domain/agent/`` (the descriptor table), the agent
kind's own infrastructure (``infrastructure/agent/``), the facet
implementations other kinds own (listed in ``FACET_IMPLEMENTATIONS``), and the
migrations, which are history. Tests are not scanned. Stdlib-only.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / "backend" / "coffer"
TYPES_FILE = PACKAGE_DIR / "domain" / "agent" / "types.py"

#: Directories whose modules may name an agent.
ALLOWED_DIRS = (
    PACKAGE_DIR / "domain" / "agent",
    PACKAGE_DIR / "infrastructure" / "agent",
    PACKAGE_DIR / "infrastructure" / "persistence" / "migrations",
)
#: Facet implementations owned by other kinds: each serves exactly one agent
#: and says so. A new one is added here in the change that adds it.
FACET_IMPLEMENTATIONS = (
    PACKAGE_DIR / "domain" / "provider" / "agent_projection.py",
    PACKAGE_DIR / "infrastructure" / "memory" / "delivery",
    PACKAGE_DIR / "infrastructure" / "memory" / "readers",
    PACKAGE_DIR / "infrastructure" / "chat" / "claude_sdk_provider.py",
    PACKAGE_DIR / "infrastructure" / "chat" / "codex_provider.py",
    PACKAGE_DIR / "infrastructure" / "chat" / "drivers.py",
)


def agent_type_values(types_file: Path = TYPES_FILE) -> dict[str, str]:
    """``{member: value}`` of ``class AgentType`` read from its source."""
    tree = ast.parse(types_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AgentType":
            members: dict[str, str] = {}
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    members[stmt.targets[0].id] = stmt.value.value
            return members
    raise SystemExit(f"check_agent_type_branches: no AgentType enum in {types_file}")


def _is_allowed(path: Path) -> bool:
    for root in (*ALLOWED_DIRS, *FACET_IMPLEMENTATIONS):
        if path == root or root in path.parents:
            return True
    return False


def _aliases(tree: ast.AST) -> set[str]:
    """Local names bound to the ``AgentType`` enum."""
    names = {"AgentType"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "AgentType":
                    names.add(alias.asname or alias.name)
    return names


def _literal(node: ast.AST, values: set[str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in values:
        return node.value
    return None


def scan_source(
    source: str, members: dict[str, str], filename: str = "<string>"
) -> list[tuple[int, str]]:
    """Every agent branch in ``source`` as ``(line, description)``."""
    tree = ast.parse(source, filename=filename)
    aliases = _aliases(tree)
    values = set(members.values())
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
            and node.attr in members
        ):
            hits.append((node.lineno, f"{node.value.id}.{node.attr}"))
        elif isinstance(node, ast.Compare):
            for operand in (node.left, *node.comparators):
                value = _literal(operand, values)
                if value is not None:
                    hits.append((node.lineno, f"comparison with {value!r}"))
        elif isinstance(node, ast.MatchValue):
            value = _literal(node.value, values)
            if value is not None:
                hits.append((node.lineno, f"match case {value!r}"))
    return sorted(set(hits))


def scan_tree(root: Path, members: dict[str, str]) -> list[tuple[Path, int, str]]:
    found: list[tuple[Path, int, str]] = []
    for py in sorted(root.rglob("*.py")):
        if _is_allowed(py):
            continue
        try:
            hits = scan_source(py.read_text(encoding="utf-8"), members, str(py))
        except (SyntaxError, UnicodeDecodeError) as e:
            print(f"check_agent_type_branches: cannot parse {py}: {e}", file=sys.stderr)
            continue
        found.extend((py, line, what) for line, what in hits)
    return found


def main() -> int:
    members = agent_type_values()
    found = scan_tree(PACKAGE_DIR, members)
    if not found:
        print(
            "check_agent_type_branches: OK — no agent branches outside the descriptor and facets."
        )
        return 0
    print(
        "check_agent_type_branches: FAIL — code outside the descriptor and its facets "
        "names an agent:",
        file=sys.stderr,
    )
    for path, line, what in found:
        print(f"  {path.relative_to(REPO_ROOT)}:{line}: `{what}`", file=sys.stderr)
    print(
        "\n  Put the per-agent value on the descriptor (domain/agent/descriptor.py) or the\n"
        "  mechanism in a facet implementation bound at the composition root, and ask the\n"
        "  agent catalogue for it. See docs-site/architecture/agent-facets.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
