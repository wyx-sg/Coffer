#!/usr/bin/env python3
"""Fail when a doc, a spec, a shipped skill, the web UI or an e2e spec quotes a removed command.

The OpenSpec change reshape-cli-and-mcp-surface rebuilt the `coffer` command
line around one grammar and removed two built-in MCP tools, with no
compatibility aliases (its design.md "Command mapping" lists every old
spelling and its replacement). Anything that still quotes an old spelling tells
a reader or an agent to run a command that no longer exists, and the failure
only shows when someone follows it. The readers that matter are the docs site,
the repository's own guides (README, AGENTS, CONTRIBUTING, ``.agents/``), the
specs, the skills Coffer ships (an agent runs what they say verbatim), the web
UI's source and the e2e suite, so those are the trees scanned here.

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
    ("AGENTS.md", (".md",)),
    ("CONTRIBUTING.md", (".md",)),
    (".agents", (".md",)),
    ("openspec/specs", (".md", ".yaml")),
    ("frontend/src", (".ts", ".tsx", ".json")),
)
_SKIP_DIRS = {"node_modules", ".vitepress/cache", "dist", "__pycache__"}
_SKIP_FILES = {"package-lock.json"}

#: (removed phrase, what replaces it). A phrase is words separated by spaces;
#: it matches with any run of whitespace between the words and must not be
#: followed by a word character or a dash.
REMOVED: tuple[tuple[str, str], ...] = (
    ("coffer resource", "coffer <kind> list|show|edit|rm|enable|disable"),
    ("coffer scope", "coffer <kind> scope <name> --agents|--all|--none"),
    ("coffer audit", "coffer log audit"),
    ("coffer retention", "coffer config list|set retention.<table>, coffer log prune"),
    ("coffer engine", "coffer config engine.* / transcribe.*, coffer daemon status"),
    ("coffer daemon port", "coffer config get|set|unset daemon.port"),
    ("coffer daemon features", "coffer config list feature. / set feature.<key> on|off"),
    ("coffer provider internal-default", "coffer config set engine.provider <name>"),
    ("coffer provider transcribe-default", "coffer config set transcribe.provider <name>"),
    ("coffer provider use-builtin", "coffer provider builtin"),
    ("coffer provider key", "coffer proxy token --agent-uid <uid> (a local proxy token, never a provider key)"),
    ("coffer mcp remove", "coffer mcp rm"),
    ("coffer mcp refresh", "coffer mcp test"),
    ("coffer mcp invocations", "coffer log mcp [--server <name>]"),
    ("coffer mcp tool", "coffer mcp cap list|enable|disable <server> tool:<name>"),
    ("coffer mcp resource", "coffer mcp cap list|enable|disable <server> resource:<uri>"),
    ("coffer mcp prompt", "coffer mcp cap list|enable|disable <server> prompt:<name>"),
    ("coffer credentials delete", "coffer credentials rm"),
    ("coffer credentials storage", "coffer config get|set credentials.storage"),
    ("coffer agent detect", "coffer scan"),
    ("coffer agent native-memory", "coffer path agent <name> memory"),
    ("coffer agent native-memory-files", "coffer path agent <name> memory"),
    ("coffer agent transcripts", "coffer agent transcript <name> [<id>]"),
    ("coffer agent config ls", "coffer path agent <name> config"),
    ("coffer agent config cat", "coffer path agent <name> config"),
    ("coffer agent config files", "coffer path agent <name> config"),
    ("coffer agent config write", "coffer agent config edit <name> <key> --from-file"),
    ("coffer agent mcp", "coffer agent connect|disconnect, coffer scan, coffer adopt|discard mcp"),
    ("coffer agent plugin uninstall", "coffer agent plugin rm"),
    ("coffer channel register", "coffer channel add"),
    ("coffer channel status", "coffer channel show"),
    ("coffer channel set", "coffer channel edit"),
    ("coffer skill import", "coffer skill add <folder>"),
    ("coffer skill files", "coffer path skill <name>"),
    ("coffer skill cat", "coffer path skill <name>, then read the file"),
    ("coffer skill write", "coffer path skill <name>, then edit the file"),
    ("coffer skill unmanaged", "coffer scan"),
    ("coffer skill adopt", "coffer adopt skill <path>"),
    ("coffer skill rm-unmanaged", "coffer discard skill <path>"),
    ("coffer knowledge collections", "coffer knowledge list"),
    ("coffer knowledge create", "coffer knowledge add"),
    ("coffer knowledge ls", "coffer path knowledge [<collection>]"),
    ("coffer knowledge read", "coffer path knowledge [<collection>], then read the file"),
    ("coffer knowledge delete", "delete the file under coffer path knowledge"),
    ("coffer memory partitions", "coffer memory list"),
    ("coffer memory notes", "coffer path memory [<partition>]"),
    ("coffer memory note", "coffer path memory [<partition>]"),
    ("coffer memory retired", "coffer path memory [<partition>]"),
    ("coffer memory ls", "coffer path memory [<partition>]"),
    ("coffer memory read", "coffer path memory [<partition>], then read the file"),
    ("coffer memory delivery-install", "coffer agent connect <agent>"),
    ("coffer memory delivery-remove", "coffer agent disconnect <agent>"),
    # The delivery hook is a part of the agent's Coffer connection (spec
    # agent-registry "Connect an agent to Coffer in one action").
    ("coffer memory delivery", "coffer agent connect|disconnect <agent>, coffer agent show <agent>"),
    # Trimmed by the OpenSpec change trim-redundant-cli-commands: each repeated
    # another command or guarded nothing.
    ("coffer adopt agent", "coffer agent add <type>"),
    ("coffer discard agent", "coffer agent add <type> to register it; Coffer never removes a detected agent"),
    ("coffer agent connection", "coffer agent show <name> (field coffer_connection)"),
    ("coffer knowledge save", "edit the file under coffer path knowledge <collection>"),
    ("coffer memory distil", "coffer memory sync"),
    ("coffer sync rollback", "coffer sync restore"),
    ("coffer sync remote show", "coffer sync status"),
    ("coffer sync machine remove", "coffer sync machine rm"),
    # Removed by the OpenSpec change add-secret-boundary: no command hands out
    # the master key (spec credentials "Return no plaintext on any route,
    # command or tool").
    ("coffer sync key export", "export a key backup in the Coffer desktop app"),
    # Removed by the OpenSpec change one-agent-per-type-and-no-titles: a skill
    # has a fixed name and no title, and its description is SKILL.md's.
    ("coffer skill edit", "edit SKILL.md under coffer path skill <name>"),
    ("coffer__recall", "grep the memory root (coffer path memory)"),
    ("coffer__diagnose", "coffer log audit|mcp|daemon, coffer path logs"),
)

#: (command phrase, removed option, what replaces it). Matches the phrase with
#: the option later on the same line.
REMOVED_OPTIONS: tuple[tuple[str, str, str], ...] = (
    # One agent per type (change one-agent-per-type-and-no-titles): the type
    # is the name.
    ("coffer agent add", "--name", "coffer agent add <type> [--config-dir <dir>]"),
    # No command prints a stored secret (spec credentials "Return no plaintext
    # on any route, command or tool").
    ("coffer credentials get", "--show", "coffer credentials get <ref> (metadata only)"),
)

#: (file, phrase, why this line may name it). The phrase is the removed phrase
#: as it appears in REMOVED, or "<command> <option>" for REMOVED_OPTIONS.
_ABSENT = "a requirement or scenario asserting the removed spelling does not exist"
ALLOWED: tuple[tuple[str, str, str], ...] = (
    ("openspec/specs/credentials/spec.md", "coffer credentials get --show", _ABSENT),
    ("openspec/specs/credentials/spec.md", "coffer sync key export", _ABSENT),
    ("openspec/specs/internal-engine/spec.md", "coffer engine", _ABSENT),
    ("openspec/specs/resource-framework/spec.md", "coffer discard agent", _ABSENT),
    ("openspec/specs/knowledge/spec.md", "coffer__recall", _ABSENT),
    ("openspec/specs/knowledge/spec.md", "coffer__diagnose", _ABSENT),
    ("openspec/specs/mcp-gateway/spec.md", "coffer__recall", _ABSENT),
    ("openspec/specs/mcp-gateway/spec.md", "coffer__diagnose", _ABSENT),
    ("openspec/specs/memory/spec.md", "coffer__recall", _ABSENT),
    ("docs-site/architecture/security.md", "coffer credentials get --show", _ABSENT),
    # The vault-sync data model is being rewritten on its own branch; delete
    # this entry when that lands (the gate fails once it matches nothing).
    ("openspec/specs/vault-sync/data-model.md", "coffer sync key export", "pending vault-sync rewrite"),
)


def _pattern(phrase: str) -> re.Pattern[str]:
    words = [re.escape(w) for w in phrase.split()]
    return re.compile(r"(?<![\w-])" + r"\s+".join(words) + r"(?![\w-])")


def _option_pattern(phrase: str, option: str) -> re.Pattern[str]:
    return re.compile(_pattern(phrase).pattern + r".*?(?<![\w-])" + re.escape(option) + r"(?![\w-])")


PATTERNS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    *((_pattern(phrase), phrase, instead) for phrase, instead in REMOVED),
    *(
        (_option_pattern(phrase, option), f"{phrase} {option}", instead)
        for phrase, option, instead in REMOVED_OPTIONS
    ),
)


def _skipped(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    if path.name in _SKIP_FILES:
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


def scan(
    paths: list[Path], allowed: tuple[tuple[str, str, str], ...] = ALLOWED
) -> list[str]:
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
            "see openspec design 'Command mapping' (reshape-cli-and-mcp-surface)",
            file=sys.stderr,
        )
        return 1
    print(f"check_removed_commands: {len(paths)} files, no removed command quoted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
