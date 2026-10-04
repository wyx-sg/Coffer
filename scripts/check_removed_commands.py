#!/usr/bin/env python3
"""Fail when a doc, spec, shipped skill, web UI, desktop shell or e2e spec quotes a removed command.

The OpenSpec change trim-the-cli-to-what-needs-it cut the `coffer` command line
to what the web UI cannot do (its design.md §1 lists what stays), with no
compatibility aliases; each removed spelling is listed below with where the
operation lives now. Anything that still quotes an old spelling tells
a reader or an agent to run a command that no longer exists, and the failure
only shows when someone follows it. The readers that matter are the docs site,
the repository's own guides (README in both languages, AGENTS, CONTRIBUTING,
``.agents/``, ``docs/``), the specs, the skills Coffer ships (an agent runs what
they say verbatim), the web UI's and the desktop shell's source and the e2e
suite, so those are the trees scanned here. The ADRs under ``docs/decisions/``
are not: an ADR is the record of a decision as it was taken, and quoting the
command that decision introduced or removed is its job.

Each entry is a whole command phrase matched on word boundaries, so a phrase
that is a prefix of a live command is not caught by accident (`coffer mcp
test` stays legal while `coffer mcp refresh` fails). The
REST routes behind many removed commands still exist, so route paths are not
matched — only `coffer ...` command phrases and the two tool names.

A removed OPTION is matched as the command phrase followed, later on the same
line, by the option (``REMOVED_OPTIONS``).

Some lines name a removed spelling on purpose — a spec scenario asserting that
the old command is gone, a note that recognises what earlier builds wrote.
Each such line is listed in ``ALLOWED`` by file and phrase, with the reason,
so the exception is reviewed like any other change; an ``ALLOWED`` entry that
no longer matches anything fails the gate too, so the list cannot rot.

Stdlib only. Exits non-zero with one line per hit: path, line and the phrase,
and the replacement to use.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Trees scanned, and the file suffixes read in each.
#: A tree may also be a single file.
SCANNED: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("docs-site", (".md", ".mts", ".ts", ".vue", ".py", ".sh", ".json", ".yaml", ".yml")),
    ("backend/coffer", (".md",)),  # shipped skill bodies (`**/skill_assets/*.md`)
    ("e2e", (".ts", ".sh", ".json")),
    ("README.md", (".md",)),
    ("README.zh-CN.md", (".md",)),
    ("docs", (".md",)),
    ("desktop", (".rs", ".json", ".toml")),
    ("AGENTS.md", (".md",)),
    ("CONTRIBUTING.md", (".md",)),
    (".agents", (".md",)),
    ("openspec/specs", (".md", ".yaml")),
    ("frontend/src", (".ts", ".tsx", ".json")),
)
_SKIP_DIRS = {
    "node_modules",
    ".vitepress/cache",
    "dist",
    "__pycache__",
    "desktop/gen",  # generated Tauri schemas
    "desktop/target",
    "desktop/binaries",
}
#: Subtrees of a scanned tree left out on purpose: the ADRs are history.
_SKIP_TREES = ("docs/decisions/",)
_SKIP_FILES = {"package-lock.json"}

#: (removed phrase, what replaces it). A phrase is words separated by spaces;
#: it matches with any run of whitespace between the words and must not be
#: followed by a word character or a dash.
#:
#: The command line keeps only what needs it (OpenSpec change
#: trim-the-cli-to-what-needs-it, design §1): `memory hook`, `proxy token`,
#: `daemon start|stop|restart|status`, `migrate`, `path logs`, `config
#: list|get|set|unset`, `run`, `secret list|set`, `log audit|mcp|daemon`, `mcp
#: test` and `vault problems`. Everything else is removed, with no aliases;
#: each spelling names the web UI page that does the job now.
_AGENTS = "the Agents page"
_CHANNELS = "the Channels page"
_SKILLS = "the Skills page"
_KNOWLEDGE = "edit the files in the knowledge folder directly (or the Knowledge page)"
_MEMORY = "read the memory notes as files (or the Memory page)"
_MCP = "the MCP servers page"
_MODELS = "the Models page"
_SYNC = "the Sync page"
_SECRETS = "the Secrets page"
_SETTINGS = "Settings"
REMOVED: tuple[tuple[str, str], ...] = (
    # Whole groups.
    ("coffer agent", _AGENTS),
    ("coffer channel", _CHANNELS),
    ("coffer skill", _SKILLS),
    ("coffer knowledge", _KNOWLEDGE),
    ("coffer provider", _MODELS),
    ("coffer tool", "the Custom tools page"),
    ("coffer cli", "the Commands page"),
    ("coffer usage", "the Usage tab"),
    ("coffer sync", _SYNC),
    (
        "coffer drift",
        "nothing: the reconciler repairs drift; what needs a person is on the attention list",
    ),
    ("coffer attention", "the attention list on the Overview page"),
    ("coffer open", "open the Coffer app"),
    (
        "coffer scan",
        "the Agents page (detected agents) and the Skills / MCP servers pages (unmanaged items)",
    ),
    ("coffer adopt", "the Skills / MCP servers pages"),
    ("coffer discard", "the Skills / MCP servers pages"),
    # Subcommands of groups that keep a few.
    ("coffer memory list", _MEMORY),
    ("coffer memory show", _MEMORY),
    ("coffer memory edit", _MEMORY),
    ("coffer memory rm", _MEMORY),
    ("coffer memory sync", "Update memory on the Memory page"),
    ("coffer memory delivered", "the Memory page"),
    ("coffer memory context", "the Memory page"),
    ("coffer memory delivery", "the Agents page (Connect)"),
    ("coffer memory distil", "Update memory on the Memory page"),
    ("coffer memory partitions", _MEMORY),
    ("coffer memory notes", _MEMORY),
    ("coffer proxy rotate", "the Agents page"),
    ("coffer proxy status", _MODELS),
    ("coffer daemon service", f"{_SETTINGS} > General (start at login)"),
    ("coffer daemon rotate-token", f"{_SETTINGS}"),
    ("coffer log prune", f"{_SETTINGS} (log retention)"),
    ("coffer mcp add", _MCP),
    ("coffer mcp edit", _MCP),
    ("coffer mcp rm", _MCP),
    ("coffer mcp list", _MCP),
    ("coffer mcp show", _MCP),
    ("coffer mcp enable", _MCP),
    ("coffer mcp disable", _MCP),
    ("coffer mcp scope", _MCP),
    ("coffer mcp handoff", _MCP),
    ("coffer mcp cap", _MCP),
    ("coffer secret get", _SECRETS),
    ("coffer secret rm", _SECRETS),
    ("coffer secret approvals", "approve in the Coffer app"),
    ("coffer secret reject", "reject in the Coffer app"),
    ("coffer secret scan", _SECRETS),
    ("coffer secret import", _SECRETS),
    ("coffer vault history", "the file history in the web UI"),
    ("coffer vault diff", "the file history in the web UI"),
    ("coffer vault show", "the file history in the web UI"),
    ("coffer vault restore", "the file history in the web UI"),
    ("coffer path knowledge", "the knowledge folder named in the prompt"),
    ("coffer path memory", "the memory folder named in the prompt"),
    ("coffer path skill", "the skill master folder named in the prompt"),
    ("coffer path agent", "the Agents page"),
    ("coffer path vault", "the vault folder named in the prompt"),
    # Earlier removals, still gone.
    ("coffer resource", _MCP),
    ("coffer scope", "the Reach control on the resource's page"),
    ("coffer audit", "coffer log audit"),
    ("coffer retention", f"{_SETTINGS} (log retention)"),
    ("coffer engine", f"{_SETTINGS} > Coffer's model"),
    ("coffer daemon port", "coffer config get|set|unset daemon.port"),
    ("coffer daemon features", f"{_SETTINGS} > General (Experimental features)"),
    ("coffer credentials", "coffer secret list|set"),
    ("coffer__recall", "grep the memory root"),
    ("coffer__diagnose", "coffer log audit|mcp|daemon, coffer path logs"),
    # Removed by the OpenSpec change make-knowledge-and-memory-files-only: an
    # agent adds knowledge with its own file tools.
    ("coffer__write", "write a file into <collection>/.inbox/"),
)

#: (command phrase, removed option, what replaces it). Matches the phrase with
#: the option later on the same line. None are left: every command that had a
#: removed option is itself removed above.
REMOVED_OPTIONS: tuple[tuple[str, str, str], ...] = ()

#: (file, phrase, why this line may name it). The phrase is the removed phrase
#: as it appears in REMOVED, or "<command> <option>" for REMOVED_OPTIONS.
_ABSENT = "a requirement or scenario asserting the removed spelling does not exist"
ALLOWED: tuple[tuple[str, str, str], ...] = (
    ("openspec/specs/knowledge/spec.md", "coffer__recall", _ABSENT),
    ("openspec/specs/knowledge/spec.md", "coffer__write", _ABSENT),
    ("openspec/specs/knowledge/spec.md", "coffer__diagnose", _ABSENT),
    ("openspec/specs/mcp-gateway/spec.md", "coffer__recall", _ABSENT),
    ("openspec/specs/mcp-gateway/spec.md", "coffer__diagnose", _ABSENT),
    ("openspec/specs/memory/spec.md", "coffer__recall", _ABSENT),
)


def _pattern(phrase: str) -> re.Pattern[str]:
    words = [re.escape(w) for w in phrase.split()]
    return re.compile(r"(?<![\w-])" + r"\s+".join(words) + r"(?![\w-])")


def _option_pattern(phrase: str, option: str) -> re.Pattern[str]:
    return re.compile(
        _pattern(phrase).pattern + r".*?(?<![\w-])" + re.escape(option) + r"(?![\w-])"
    )


PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    *((_pattern(phrase), phrase, instead) for phrase, instead in REMOVED),
    *(
        (_option_pattern(phrase, option), f"{phrase} {option}", instead)
        for phrase, option, instead in REMOVED_OPTIONS
    ),
)


def _skipped(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    if path.name in _SKIP_FILES or rel.startswith(_SKIP_TREES):
        return True
    return any(f"/{d}/" in f"/{rel}/" for d in _SKIP_DIRS)


def _files() -> list[Path]:
    out: list[Path] = []
    for tree, suffixes in SCANNED:
        root = REPO_ROOT / tree
        if root.is_file():
            out.append(root)
            continue
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in suffixes or _skipped(path):
                continue
            if tree == "backend/coffer" and "skill_assets" not in path.parts:
                continue
            out.append(path)
    return out


def scan(paths: list[Path], allowed: tuple[tuple[str, str, str], ...] = ALLOWED) -> list[str]:
    hits: list[str] = []
    allow = {(rel, phrase) for rel, phrase, _why in allowed}
    used: set[tuple[str, str]] = set()
    for path in paths:
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, phrase, instead in PATTERNS:
                if not pattern.search(line):
                    continue
                if (rel, phrase) in allow:
                    used.add((rel, phrase))
                    continue
                hits.append(f"{rel}:{lineno}: removed `{phrase}` — use {instead}")
    for rel, phrase in sorted(allow - used):
        hits.append(f"{rel}: ALLOWED entry for `{phrase}` matches nothing — delete it")
    return hits


def main() -> int:
    paths = _files()
    hits = scan(paths)
    for hit in hits:
        print(f"check_removed_commands: {hit}", file=sys.stderr)
    if hits:
        print(
            f"check_removed_commands: {len(hits)} quote(s) of removed commands; "
            "see openspec change trim-the-cli-to-what-needs-it design §1",
            file=sys.stderr,
        )
        return 1
    print(f"check_removed_commands: {len(paths)} files, no removed command quoted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
