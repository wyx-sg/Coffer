#!/usr/bin/env python3
"""A cited requirement must exist, and retired id forms must not come back.

Requirements are identified by title (see `.agents/openspec.md`), so a comment
or a document points at one by naming its capability and quoting its title:

    spec vault-sync "Hold a returning machine's empty vault instead of ..."
    spec channels/telegram, "Download every Telegram media type ..."
    [knowledge](../openspec/specs/knowledge/spec.md) "Use the file path ..."

A title is only a name, so nothing but this script notices when one is renamed
or retired and the citation keeps quoting the old words. Two rules:

  1. Every citation resolves. Its capability is a directory under
     `openspec/specs/` (a child such as `channels/seatalk` included) and its
     title is a `### Requirement:` heading in that directory's `spec.md`. A
     citation may wrap across comment or docstring lines; the continuation's
     leader (`#`, `#:`, `//`, `///`, `*`, `>`) is not part of the title.
     A title that only exists in an in-flight change — an `ADDED` requirement
     or the new name of a `RENAMED` one under `openspec/changes/<name>/specs/`
     — is accepted and listed, so a change can cite what it is adding before
     it is archived. Files inside a change folder may also cite the titles
     that change modifies, renames away or removes.
  2. No retired id form comes back: an amendment letter after a capability
     (`spec <capability> <letter><digits>`), a numbered error code
     (`CODE-<digits>`, `CODE-REG`) and an uppercase spec id
     (`SPEC-<digits>`). Each was a second name for something that already had
     one, and each drifted the way numbers do. Change folders are exempt, as
     they are from `check_doc_numbering.py`: a change may describe what it
     replaced.

Scope: every tracked file except archived changes, migration scripts (history
that is never edited), vendored `node_modules/` and the generated API client.

Stdlib only. Exits non-zero on any failure.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

EXCLUDED_PREFIXES = (
    "openspec/changes/archive/",
    "backend/coffer/infrastructure/persistence/migrations/versions/",
    "frontend/src/lib/api/generated/",
)
#: This file names the retired forms on purpose, in the docstring above.
SELF = "scripts/check_spec_citations.py"
CHANGES_PREFIX = "openspec/changes/"

REQUIREMENT = re.compile(r"^###\s+Requirement:\s*(.+?)\s*$", re.MULTILINE)
DELTA_SECTION = re.compile(r"^##\s+(ADDED|MODIFIED|REMOVED|RENAMED)\s+Requirements\b")
RENAMED_LINE = re.compile(r"^\s*-\s*(FROM|TO):\s*`?\s*###\s+Requirement:\s*(.+?)\s*`?\s*$")

#: What may sit between the tokens of a citation that wraps: optional spaces,
#: then at most one line break followed by a comment leader.
_BREAK = r"[ \t]*\n[ \t]*(?:#:?|//[/!]?|\*|>)?[ \t]*"
_SEP = r"[ \t]*(?:" + _BREAK + r")?"
#: A quoted title, in any of the quotes the tree uses. A single-quoted title
#: starts with a capital and stops at its first apostrophe, and a quote with a
#: letter on its outer side is an apostrophe, so `agent's` neither opens nor
#: closes one.
_TITLE = (
    r"(?:\\?\"(?P<dq>[^\"\\]{1,300})\\?\""
    r"|“(?P<cq>[^”]{1,300})”"
    r"|(?<![A-Za-z])'(?P<sq>[A-Z][^'\n]{0,200})'(?![A-Za-z]))"
)
#: `spec <cap>[/<child>]['s][,] "<Title>"`, a line break allowed after `spec`.
PLAIN_CITATION = re.compile(
    r"\b[Ss]pecs?(?:[ \t]+|" + _BREAK + r")"
    r"(?P<cap>[a-z][a-z0-9-]*(?:/[a-z][a-z0-9-]*)?)(?![\w/-])(?:'s)?,?" + _SEP + _TITLE
)
#: `[<text>](<path>/openspec/specs/<cap>/spec.md) "<Title>"`.
LINK_CITATION = re.compile(
    r"\[[^\]\n]*\]\((?:[^)\s]*/)?openspec/specs/(?P<cap>[a-z0-9/-]+?)/spec\.md"
    r"(?:#[^)\s]*)?\)(?:'s)?,?" + _SEP + _TITLE
)
#: Words that read as `spec <word> "..."` in prose without naming a capability.
NOT_A_CAPABILITY = frozenset(
    {"scenario", "scenarios", "requirement", "requirements", "title", "says", "text"}
)
#: A comment leader at the start of a continuation line, dropped from a title.
_CONTINUATION = re.compile(_BREAK)

RETIRED_IDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b[Ss]pecs?[ \t]+[a-z][a-z-]*(?:/[a-z-]+)?,?[ \t]+[A-Z]\d+[a-z]?\b"),
        "amendment letters are retired — cite the requirement's title instead",
    ),
    (
        re.compile(r"\bCODE-(?:\d{3}|REG)\b"),
        "numbered error codes are retired — name the error by its code string",
    ),
    (
        re.compile(r"\bSPEC-\d+"),
        "specs are named, not numbered — name the capability instead",
    ),
)


@dataclass(frozen=True)
class Citation:
    line: int
    capability: str
    title: str


@dataclass
class Titles:
    """Requirement titles by capability: the specs, plus in-flight changes."""

    live: dict[str, set[str]]
    #: capability -> title -> change name, for ADDED and RENAMED-to titles.
    pending: dict[str, dict[str, str]]
    #: capability -> title -> change name, for REMOVED and RENAMED-from titles:
    #: still valid, but a citation of one breaks when that change is archived.
    retiring: dict[str, dict[str, str]]
    #: change name -> capability -> every title the change's deltas mention.
    by_change: dict[str, dict[str, set[str]]]


def load_titles(root: Path) -> Titles:
    live: dict[str, set[str]] = {}
    specs = root / "openspec" / "specs"
    for spec in sorted(specs.rglob("spec.md")):
        cap = spec.parent.relative_to(specs).as_posix()
        live[cap] = set(REQUIREMENT.findall(spec.read_text(encoding="utf-8")))
    pending: dict[str, dict[str, str]] = {}
    retiring: dict[str, dict[str, str]] = {}
    by_change: dict[str, dict[str, set[str]]] = {}
    changes = root / "openspec" / "changes"
    if changes.is_dir():
        for change in sorted(p for p in changes.iterdir() if p.is_dir()):
            if change.name == "archive":
                continue
            delta_root = change / "specs"
            for spec in sorted(delta_root.rglob("spec.md")):
                cap = spec.parent.relative_to(delta_root).as_posix()
                added, retired, mentioned = _delta_titles(spec.read_text(encoding="utf-8"))
                for title in added:
                    pending.setdefault(cap, {})[title] = change.name
                for title in retired:
                    retiring.setdefault(cap, {})[title] = change.name
                by_change.setdefault(change.name, {}).setdefault(cap, set()).update(mentioned)
    return Titles(live, pending, retiring, by_change)


def _delta_titles(text: str) -> tuple[set[str], set[str], set[str]]:
    """(titles a delta adds or renames to, titles it removes or renames away,
    every title it mentions)."""
    added: set[str] = set()
    retired: set[str] = set()
    mentioned: set[str] = set()
    section = ""
    for line in text.splitlines():
        if match := DELTA_SECTION.match(line):
            section = match.group(1)
            continue
        if match := REQUIREMENT.match(line):
            mentioned.add(match.group(1))
            if section == "ADDED":
                added.add(match.group(1))
            elif section == "REMOVED":
                retired.add(match.group(1))
        elif section == "RENAMED" and (match := RENAMED_LINE.match(line)):
            mentioned.add(match.group(2))
            (added if match.group(1) == "TO" else retired).add(match.group(2))
    return added, retired, mentioned


def _title(match: re.Match[str]) -> str:
    raw = match.group("dq") or match.group("cq") or match.group("sq") or ""
    return _CONTINUATION.sub(" ", raw).strip()


def find_citations(text: str) -> list[Citation]:
    found: list[Citation] = []
    for pattern in (PLAIN_CITATION, LINK_CITATION):
        for match in pattern.finditer(text):
            cap = match.group("cap")
            if pattern is PLAIN_CITATION and cap in NOT_A_CAPABILITY:
                continue
            raw = match.group("dq") or match.group("cq") or match.group("sq") or ""
            # A "title" spanning several lines is two quotes that happen to
            # pair up, not one wrapped title.
            if raw.count("\n") > 3:
                continue
            # Every title is a phrase. A quoted single token after a
            # `# spec <cap>` label is the next line's key — an error code in
            # a status map — not a title.
            if not re.search(r"\s", raw.strip()):
                continue
            line = text.count("\n", 0, match.start()) + 1
            found.append(Citation(line, cap, _title(match)))
    return sorted(found, key=lambda c: c.line)


def _change_of(rel: str) -> str | None:
    if not rel.startswith(CHANGES_PREFIX):
        return None
    return rel[len(CHANGES_PREFIX) :].split("/", 1)[0]


def check_file(rel: str, text: str, titles: Titles) -> tuple[list[str], list[str]]:
    """(errors, notes) for one file."""
    errors: list[str] = []
    notes: list[str] = []
    change = _change_of(rel)
    for cite in find_citations(text):
        where = f"{rel}:{cite.line}"
        known = titles.live.get(cite.capability)
        own = (titles.by_change.get(change, {}) if change else {}).get(cite.capability)
        if known is None and own is None and cite.capability not in titles.pending:
            errors.append(f"{where}: no capability {cite.capability!r} under openspec/specs/")
            continue
        if cite.title in (own or set()):
            continue
        if cite.title in (known or set()):
            leaving = titles.retiring.get(cite.capability, {}).get(cite.title)
            if leaving and change is None:
                notes.append(
                    f"{where}: spec {cite.capability} {cite.title!r} is removed or "
                    f"renamed by openspec/changes/{leaving}/ — update this citation "
                    f"before that change is archived"
                )
            continue
        if in_flight := titles.pending.get(cite.capability, {}).get(cite.title):
            notes.append(
                f"{where}: spec {cite.capability} {cite.title!r} exists only in "
                f"openspec/changes/{in_flight}/ (not yet archived)"
            )
            continue
        errors.append(f"{where}: spec {cite.capability} has no requirement titled {cite.title!r}")
    if change is None:
        for lineno, line in enumerate(text.splitlines(), 1):
            for pattern, why in RETIRED_IDS:
                if match := pattern.search(line):
                    errors.append(f"{rel}:{lineno}: {match.group(0)!r}: {why}")
    return errors, notes


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [
        f
        for f in out
        if f != SELF and not f.startswith(EXCLUDED_PREFIXES) and "node_modules/" not in f
    ]


def check_tree(root: Path, files: list[str]) -> tuple[list[str], list[str], int]:
    """(errors, notes, number of citations checked) over `files`."""
    titles = load_titles(root)
    errors: list[str] = []
    notes: list[str] = []
    count = 0
    for rel in files:
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        count += len(find_citations(text))
        file_errors, file_notes = check_file(rel, text, titles)
        errors += file_errors
        notes += file_notes
    return errors, notes, count


def main() -> int:
    errors, notes, count = check_tree(REPO_ROOT, tracked_files(REPO_ROOT))
    for note in notes:
        print(f"note: {note}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"\ncheck_spec_citations: {len(errors)} problem(s)", file=sys.stderr)
        return 1
    print(f"check_spec_citations: {count} requirement citations resolve, no retired id form")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
