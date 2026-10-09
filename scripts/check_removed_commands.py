#!/usr/bin/env python3
"""Fail when a doc, spec, shipped skill, web UI, desktop shell or e2e spec quotes a removed command.

Commands the command line has dropped over time (OpenSpec changes
trim-the-cli-to-what-needs-it and align-cli-with-ui-and-add-tool-environments)
are listed below with where the operation lives now, with no compatibility
aliases. Anything that still quotes an old spelling tells
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
#: The OpenSpec change trim-the-cli-to-what-needs-it cut the command line to
#: what the web UI could not do; align-cli-with-ui-and-add-tool-environments
#: then gave every web UI and desktop operation a command again (spec
#: resource-framework "Offer every management operation on the command line"),
#: so most of those spellings are live once more. What is left here is only
#: what is still gone, each with the command or the file that does the job now.
_MEMORY = "read and edit the memory notes as files"
REMOVED: tuple[tuple[str, str], ...] = (
    ("coffer tool", "coffer custom-tool"),
    ("coffer cli install", "the hand-off prompt on the CLIs page (coffer cli add registers one)"),
    (
        "coffer drift",
        "nothing: the reconciler repairs drift; what needs a person is coffer attention list",
    ),
    ("coffer migrate", "nothing: a fresh install starts at the current layout"),
    ("coffer open", "open the Coffer app"),
    ("coffer scan", "coffer agent list (detected agents) and coffer skill / mcp unmanaged items"),
    ("coffer adopt", "the adopt command of the Skills or MCP servers group"),
    ("coffer discard", "the discard command of the Skills or MCP servers group"),
    ("coffer memory edit", _MEMORY),
    ("coffer memory rm", "coffer memory delete"),
    ("coffer memory context", "coffer memory reading"),
    ("coffer memory delivery", "coffer agent connect"),
    ("coffer memory distil", "coffer memory sync"),
    ("coffer daemon service", "coffer daemon residency set"),
    ("coffer log prune", "coffer settings retention prune"),
    ("coffer mcp edit", "coffer mcp update"),
    ("coffer mcp rm", "coffer mcp delete"),
    ("coffer mcp scope", "coffer mcp reach"),
    ("coffer mcp handoff", "the MCP servers page's hand-off prompt"),
    ("coffer mcp cap", "coffer mcp exposure"),
    ("coffer secret get", "coffer secret reveal (the value shows only in the Coffer app)"),
    ("coffer secret rm", "coffer secret delete"),
    ("coffer secret approvals", "coffer approval list"),
    ("coffer secret reject", "coffer approval reject"),
    ("coffer vault show", "coffer vault history / coffer vault diff"),
    ("coffer path knowledge", "the knowledge folder named in the prompt"),
    ("coffer path memory", "the memory folder named in the prompt"),
    ("coffer path skill", "the skill master folder named in the prompt"),
    ("coffer path agent", "coffer agent config-files"),
    ("coffer path vault", "the vault folder named in the prompt"),
    ("coffer scope", "coffer resource reach"),
    ("coffer audit", "coffer log audit"),
    ("coffer retention", "coffer settings retention"),
    ("coffer engine", "coffer settings engine"),
    ("coffer daemon features", "coffer settings features"),
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
    ("openspec/specs/daemon/spec.md", "coffer daemon service", _ABSENT),
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
            "see the REMOVED table in scripts/check_removed_commands.py",
            file=sys.stderr,
        )
        return 1
    print(f"check_removed_commands: {len(paths)} files, no removed command quoted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
