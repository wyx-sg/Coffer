"""Reads Codex's distilled memory: `MEMORY.md` task groups and a profile.

Two files matter, both under `<config_dir>/memories/`:

- `MEMORY.md` — repeated `# Task Group: <name>` sections, each carrying an
  `applies_to: cwd=<path>; ...` line and, among its subsections, exactly
  three bullet lists this reader treats as facts: `## User preferences`,
  `## Reusable knowledge`, `## Failures and how to do differently`. The
  group's own `## Task N: ...` subsections (rollout file references, search
  keywords) describe *how the group was produced*, not something learned, so
  they are read for context only and never become a fact.
- `memory_summary.md` — a `## User Profile` prose block and its own
  `## User preferences` bullet list, both about the person rather than any
  project. Its other sections (`## General Tips`, `## What's in Memory`)
  restate what `MEMORY.md` already holds — the same kind of index Claude
  Code's own `MEMORY.md` is, and skipped for the same reason (FR-004).

Neither file gives a bullet a title the way Claude Code's frontmatter does,
so this reader derives one from the bullet's first clause and keeps the
bullet's full text as both the description and the body (FR-021) — see
`_bullet_title`. An anchor is built from the group, the section heading and
a content hash of the bullet (`_anchor`): the same triple two runs apart
names the same fact, and two different bullets that happen to start with the
same clause still get distinct anchors.

`raw_memories.md` and `rollout_summaries/` are never read: they are the raw
transcripts Codex already distilled into the two files above, and FR-003
forbids this layer from reading transcripts a second time.

The Task Group/cwd file *format* — splitting `MEMORY.md` into groups and
extracting each group's routed cwd(s), including the prose Codex writes a
multi-project `applies_to` line in — is `domain.agent.codex_memory`'s job,
shared with the agent page's native-memory listing
(`infrastructure.agent.codex_memory_store`) so the two never drift apart on
what counts as a path in that line. This reader only owns which sections
count as facts, how a bullet gets a title, and how its anchor is built —
the aggregation-specific policy on top of that shared parse.
"""

from __future__ import annotations

import hashlib
import pathlib
import re

from coffer.domain.agent.codex_memory import parse_codex_memory, section_bullets, section_text
from coffer.domain.memory.errors import UnreadableMemory
from coffer.domain.memory.fact import TYPE_PROJECT, TYPE_USER
from coffer.domain.memory.reader import RawFact, SourceFile

_MEMORY_NAME = "MEMORY.md"
_SUMMARY_NAME = "memory_summary.md"

# The three per-group bullet lists this reader turns into facts, and the type
# each maps to. "User preferences" is the person's own standing preference —
# TYPE_USER. "Reusable knowledge" and "Failures and how to do differently"
# are both about the *project* the group's `cwd` names — a technique that
# works in this codebase, or a trap already hit in it — which is TYPE_PROJECT
# per fact.py's own description ("a decision, a trap, a piece of its
# history"). TYPE_FEEDBACK is reserved for a standing instruction the
# developer gave about how to work (Claude Code's `feedback` type); a group's
# "Failures" bullets are Codex's own retrospective on a past attempt, not an
# instruction from the user, so they land as TYPE_PROJECT rather than
# TYPE_FEEDBACK.
_GROUP_SECTIONS = {
    "User preferences": TYPE_USER,
    "Reusable knowledge": TYPE_PROJECT,
    "Failures and how to do differently": TYPE_PROJECT,
}

_PROFILE_HEADING = "User Profile"
_PROFILE_PREFS_HEADING = "User preferences"


class CodexMemoryReader:
    """`MemoryReader` for Codex's `MEMORY.md` and `memory_summary.md`."""

    agent_type = "codex"

    def sources(self, config_dir: str) -> tuple[SourceFile, ...]:
        memories_dir = pathlib.Path(config_dir) / "memories"
        out: list[SourceFile] = []
        for name in (_MEMORY_NAME, _SUMMARY_NAME):
            file = memories_dir / name
            try:
                digest = hashlib.sha256(file.read_bytes()).hexdigest()
            except OSError:
                # Missing or unreadable — skip it, the other file (and the
                # other agent) still gets aggregated (FR-005's isolation).
                continue
            out.append(SourceFile(path=str(file), digest=digest))
        return tuple(out)

    def read(self, source: SourceFile) -> tuple[RawFact, ...]:
        path = pathlib.Path(source.path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise UnreadableMemory(source.path, str(exc)) from exc

        if path.name == _SUMMARY_NAME:
            return _read_summary(text)
        if path.name == _MEMORY_NAME:
            return _read_groups(text)
        raise UnreadableMemory(source.path, f"unrecognised Codex memory file {path.name!r}")


def _read_groups(text: str) -> tuple[RawFact, ...]:
    facts: list[RawFact] = []
    for entry in parse_codex_memory(text):
        # A group can route to more than one cwd (`applies_to: cwd=A and B`);
        # attributing every fact to all of them would give the same anchor
        # two homes and blur which partition an override belongs to (FR-022),
        # so — same as the un-ambiguous, overwhelmingly common single-cwd
        # case — the first recorded cwd is the one project a group's facts
        # are filed under. A group with none files under "" (global).
        project_root = entry.cwds[0] if entry.cwds else ""
        for heading, fact_type in _GROUP_SECTIONS.items():
            for bullet in section_bullets(entry.body, heading):
                facts.append(
                    RawFact(
                        title=_bullet_title(bullet),
                        description=bullet,
                        type=fact_type,
                        body=bullet,
                        anchor=_anchor(entry.title, heading, bullet),
                        project_root=project_root,
                    )
                )
    return tuple(facts)


def _read_summary(text: str) -> tuple[RawFact, ...]:
    facts: list[RawFact] = []
    profile = section_text(text, _PROFILE_HEADING).strip()
    if profile:
        facts.append(
            RawFact(
                title=_PROFILE_HEADING,
                description=profile,
                type=TYPE_USER,
                body=profile,
                anchor="profile::user-profile",
                project_root="",
            )
        )
    for bullet in section_bullets(text, _PROFILE_PREFS_HEADING):
        facts.append(
            RawFact(
                title=_bullet_title(bullet),
                description=bullet,
                type=TYPE_USER,
                body=bullet,
                anchor=_anchor("profile", _PROFILE_PREFS_HEADING, bullet),
                project_root="",
            )
        )
    return tuple(facts)


def _bullet_title(bullet: str) -> str:
    """A short title from a bullet's first clause.

    Codex's bullets are freeform prose with no author-given title (unlike
    Claude Code's frontmatter `name`). The first clause — up to the first
    `->`, `. ` or `; ` — reads as a reasonable stand-in; the full bullet
    stays intact as the description and body (FR-021), so nothing is lost by
    a title that trims it.
    """
    clause = re.split(r"\s*->\s*|\.\s|;\s", bullet, maxsplit=1)[0].strip().rstrip(".")
    if not clause:
        clause = bullet.strip()
    if len(clause) > 100:
        clause = clause[:97].rstrip() + "..."
    return clause


def _anchor(group: str, heading: str, bullet: str) -> str:
    """Stable identity for one bullet (FR-022): group + section + content.

    Two different bullets in the same section hash differently; the same
    bullet re-read on a later sync hashes the same, which is the whole point
    — an override the developer records against this anchor must still find
    the fact after MEMORY.md is regenerated with this group's text unchanged.
    """
    digest = hashlib.sha256(bullet.encode("utf-8")).hexdigest()[:16]
    return f"{group}::{heading}::{digest}"
