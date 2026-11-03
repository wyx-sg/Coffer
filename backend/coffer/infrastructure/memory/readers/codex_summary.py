"""Codex's `memory_summary.md`, v1's and v2's, read into raw entries, and the
text helpers both summaries and `MEMORY.md` share (see `readers.codex`, whose
docstring explains what each section becomes and why).

v2 (`memories_v2/memory_summary.md`) is Codex's whole consolidated memory: its
profile and preferences read like v1's, and it adds what v1 keeps in
`MEMORY.md`, as General Tips paragraphs and What's in Memory topics (spec
memory "Read Codex's v2 memory").
"""

from __future__ import annotations

import hashlib
import pathlib
import re

from coffer.domain.agent.codex_memory import parse_codex_v2_topics, section_bullets, section_text
from coffer.domain.memory.hub import TYPE_PROJECT, TYPE_USER
from coffer.domain.memory.reader import RawEntry
from coffer.infrastructure.agent_files.codex_rollout_summaries import rollout_cwd
from coffer.infrastructure.memory.codex_identity import PROFILE_ANCHOR, V2_TOPICS_HEADING
from coffer.infrastructure.memory.writers.codex import VIA_COFFER

SUMMARY_NAME = "memory_summary.md"
V2_FOLDER = "memories_v2"
_TIPS_HEADING = "General Tips"
_PROFILE_HEADING = "User Profile"
_PROFILE_PREFS_HEADING = "User preferences"


def v2_summary_beside(v1_summary: pathlib.Path) -> str | None:
    """The v2 summary next to a v1 one's folder, or ``None`` when there is none."""
    try:
        return (v1_summary.parent.parent / V2_FOLDER / SUMMARY_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def read_summary(text: str, v2_text: str | None = None) -> tuple[RawEntry, ...]:
    """A v1 summary. With a v2 summary beside it, the profile is v2's and only
    the preferences v2 does not state word for word are read here."""
    entries: list[RawEntry] = []
    profile = _without_coffer(section_text(text, _PROFILE_HEADING)).strip()
    stated = set(section_bullets(v2_text, _PROFILE_PREFS_HEADING)) if v2_text is not None else set()
    if v2_text is not None:
        profile = ""
    if profile:
        entries.append(
            RawEntry(
                title=_PROFILE_HEADING,
                description=profile,
                type=TYPE_USER,
                body=profile,
                anchor=PROFILE_ANCHOR,
                project_root="",
            )
        )
    for bullet in section_bullets(text, _PROFILE_PREFS_HEADING):
        if VIA_COFFER in bullet or bullet in stated:
            continue
        entries.append(
            RawEntry(
                title=bullet_title(bullet),
                description=bullet,
                type=TYPE_USER,
                body=bullet,
                anchor=anchor("profile", _PROFILE_PREFS_HEADING, bullet),
                project_root="",
            )
        )
    # No `search_terms` here on purpose: Codex states terms per *task group*,
    # and the profile is about the person, not about any group. Inventing terms
    # for it would be exactly the guess "Read Claude Code and Codex memory with
    # their search terms" exists to avoid.
    return tuple(entries)


def read_summary_v2(text: str, folder: pathlib.Path) -> tuple[RawEntry, ...]:
    """A v2 summary: the profile and preferences as v1's are read, then each
    General Tips paragraph and each What's in Memory topic."""
    entries = list(read_summary(text))
    for paragraph in _paragraphs(section_text(text, _TIPS_HEADING)):
        if VIA_COFFER in paragraph:
            continue
        entries.append(
            RawEntry(
                title=bullet_title(paragraph),
                description=paragraph,
                type=TYPE_PROJECT,
                body=paragraph,
                anchor=anchor("profile", _TIPS_HEADING, paragraph),
                project_root="",
            )
        )
    for topic in parse_codex_v2_topics(text):
        if VIA_COFFER in topic.body:
            continue
        entries.append(
            RawEntry(
                title=bullet_title(topic.text),
                description=topic.text,
                type=TYPE_PROJECT,
                body=topic.body,
                anchor=anchor(topic.scope or "memory", V2_TOPICS_HEADING, topic.body),
                project_root=_topic_cwd(folder, topic.rollout_file),
            )
        )
    return tuple(entries)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _topic_cwd(folder: pathlib.Path, rollout_file: str) -> str:
    """The working directory a v2 topic was learned in: the ``cwd:`` line of
    the header of the rollout summary it points at. Only the header is read,
    the summary's account is not ("Read no transcripts or rollouts")."""
    return rollout_cwd(folder, rollout_file)


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?\u3002\uff01\uff1f])\s+")


def _without_coffer(text: str) -> str:
    """``text`` without the sentences Codex derived from Coffer's copies.

    Codex tags what it derives from them `[via Coffer]` (see the extension's
    instructions). A tagged bullet is skipped whole; the profile is prose, so
    a tagged sentence in it is dropped and the rest kept, or Coffer would
    publish back, as Codex's, what it delivered."""
    lines = []
    for line in text.split("\n"):
        if VIA_COFFER not in line:
            lines.append(line)
            continue
        kept: list[str] = []
        for sentence in _SENTENCE_SPLIT_RE.split(line):
            if VIA_COFFER not in sentence:
                kept.append(sentence)
            elif not sentence.replace(VIA_COFFER, "").strip(" .;,") and kept:
                # "Sentence. [via Coffer]": the tag stands after what it marks.
                kept.pop()
        if kept:
            lines.append(" ".join(kept))
    return "\n".join(lines)


def bullet_title(bullet: str) -> str:
    """A short handle from a bullet's first clause.

    Codex's bullets are freeform prose with no author-given title (unlike Claude
    Code's frontmatter `name`). The first clause — up to the first `->`, `. ` or
    `; ` — reads as a reasonable stand-in; the full bullet stays intact as the
    description and the body, and the body is what lands verbatim under `.raw/`
    (see "Keep raw entries verbatim and hidden"), so nothing is lost by a handle
    that trims it. It is not trying to be a title a person will read: the note's
    title is Coffer's to write, later, in the distil pass (see "Distil each raw entry into a note
    mechanically").
    """
    clause = re.split(r"\s*->\s*|\.\s|;\s", bullet, maxsplit=1)[0].strip().rstrip(".")
    if not clause:
        clause = bullet.strip()
    if len(clause) > 100:
        clause = clause[:97].rstrip() + "..."
    return clause


def anchor(group: str, heading: str, bullet: str) -> str:
    """Stable identity for one bullet: group + section + content.

    See "Let only aggregation write raw entries" (reproducible from an unchanged
    source).

    Two different bullets in the same section hash differently; the same bullet
    re-read on a later sync hashes the same, which is the whole point — the
    anchor is half of a note's provenance (see "Distil each raw entry into a note mechanically")
    and the name a raw entry keeps under `.raw/`, so a note must still
    point at the entry it was built from after MEMORY.md is regenerated with
    this group's text unchanged.
    """
    digest = hashlib.sha256(bullet.encode("utf-8")).hexdigest()[:16]
    return f"{group}::{heading}::{digest}"
