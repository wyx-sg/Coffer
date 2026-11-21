#!/usr/bin/env python3
"""Keep agent-specific branches out of the web UI, outside its agent modules.

ADR what-coffer-does-for-an-agent-follows-from-its-facets: the daemon reports
what Coffer can do with each agent type as its ``features`` (and its other
per-type values, such as the skills folders it reads), and the web UI renders
from those, never from an agent's name. A picker or tab that lists agents by
name goes stale the day a type gains or loses a facet, which is how the
scheduled-task picker kept offering Codex on a Mac without it.

The backend half is ``check_agent_type_branches.py``. This script scans every
``.ts`` and ``.tsx`` file under ``frontend/src/`` (tests, fakes and the
generated wire types aside) and fails on an agent type's value written as a
string literal (``"codex"``) or as an object key (``codex: …``) outside the
allowed places:

* ``lib/agents/`` and ``components/agent/`` — the web UI's per-type values
  (product names, programs, icons, ordering), the counterpart of the
  descriptor table;
* the files in ``ALLOWED_FILES``, each holding a per-agent *value* the daemon
  does not serve, with the reason beside it. Add one only with that reason.

The values are read from ``backend/coffer/domain/agent/types.py``, so a new
type is checked the day it is added. Comments are stripped first. Stdlib-only.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "frontend" / "src"
TYPES_FILE = REPO_ROOT / "backend" / "coffer" / "domain" / "agent" / "types.py"

ALLOWED_DIRS = (
    SRC / "lib" / "agents",
    SRC / "components" / "agent",
    SRC / "lib" / "api" / "generated",
)

#: Files that hold a per-agent value the daemon does not serve, and why.
ALLOWED_FILES: dict[str, str] = {
    # The command a terminal runs to resume a session, per program.
    "lib/terminal/command.ts": "resume command syntax",
    # The hand-off starts an agent in a terminal by a command only these know.
    "lib/preferences.ts": "hand-off agents, whose terminal command is known",
    "components/settings/general/HandoffAgentPicker.tsx": "hand-off agents",
    "components/handoff/useAgentHandoff.tsx": "hand-off agents",
    "components/sessions/useOpenSession.tsx": "hand-off agents",
    # Program names in a pasted command line, not agent types.
    "lib/mcp/commandLine.ts": "program names",
    "lib/mcp/pasteCommand.ts": "program names",
    # The protocol each agent's provider projection speaks.
    "lib/api/providers.ts": "provider protocol per agent",
    # Plugin and session storage layout, per product.
    "components/agents/AgentPluginsTab.tsx": "plugin layout",
    "components/agents/useAgentPluginsBulk.tsx": "plugin layout",
    "components/agents/PluginUninstallDialog.tsx": "plugin uninstall command",
    "components/agents/sessions/AgentSessionsTab.tsx": "sessions folder name",
    "lib/hooks/useModelSwitchTest.ts": "model-switch test per protocol",
    "lib/providers/presets.ts": "vendor presets naming the agents they suit",
    # Where each product keeps its MCP file and which folders its listing shows.
    "components/agents/overview/paths.ts": "MCP file per product",
    "components/agents/list/useFolderListing.ts": "folder layout per product",
}

#: Values that are also ordinary words in the code (a pagination ``cursor``):
#: checked as string literals only, never as object keys.
AMBIGUOUS = frozenset({"cursor"})

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(?<![:\w])//[^\n]*")


def agent_type_values(types_file: Path = TYPES_FILE) -> tuple[str, ...]:
    text = types_file.read_text(encoding="utf-8")
    body = text.split("class AgentType", 1)[1].split("\n\n", 2)[1]
    return tuple(re.findall(r'^\s+[A-Z_]+ = "([a-z_]+)"', body, re.M))


def strip_comments(source: str) -> str:
    def blank(match: re.Match[str]) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return _LINE_COMMENT.sub(blank, _BLOCK_COMMENT.sub(blank, source))


def scan_source(source: str, values: tuple[str, ...]) -> list[tuple[int, str]]:
    """``(line, value)`` for every agent type value used as a literal or key."""
    names = "|".join(re.escape(v) for v in values)
    keys = "|".join(re.escape(v) for v in values if v not in AMBIGUOUS)
    pattern = re.compile(rf"""(?:["'`]({names})["'`])|(?:^[ \t]*({keys})[ \t]*:)""", re.M)
    text = strip_comments(source)
    hits = []
    for match in pattern.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        hits.append((line, match.group(1) or match.group(2)))
    return hits


def _scanned(path: Path) -> bool:
    if path.suffix not in {".ts", ".tsx"}:
        return False
    if any(path.is_relative_to(d) for d in ALLOWED_DIRS):
        return False
    name = path.name
    if ".test." in name or name.startswith("fake") or path.is_relative_to(SRC / "test"):
        return False
    return str(path.relative_to(SRC)) not in ALLOWED_FILES


def scan_tree(root: Path = SRC) -> list[tuple[Path, int, str]]:
    values = agent_type_values()
    found = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and _scanned(path):
            for line, value in scan_source(path.read_text(encoding="utf-8"), values):
                found.append((path, line, value))
    return found


def main() -> int:
    missing = [f for f in ALLOWED_FILES if not (SRC / f).is_file()]
    if missing:
        print(
            "check_frontend_agent_types: FAIL — allowed files that no longer exist:",
            file=sys.stderr,
        )
        for f in missing:
            print(f"  frontend/src/{f}", file=sys.stderr)
        return 1
    found = scan_tree()
    if not found:
        print("check_frontend_agent_types: OK — no agent type named outside the agent modules.")
        return 0
    print(
        "check_frontend_agent_types: FAIL — an agent type named outside the agent modules:",
        file=sys.stderr,
    )
    for path, line, value in found:
        print(f"  {path.relative_to(REPO_ROOT)}:{line}: `{value}`", file=sys.stderr)
    print(
        "\n  Render from the agent's `features` (or another value the daemon serves)\n"
        "  instead of its name, or move the per-type value into lib/agents/.\n"
        "  See ADR what-coffer-does-for-an-agent-follows-from-its-facets.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
