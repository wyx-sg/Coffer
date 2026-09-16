"""Reads Codex's distilled memory: `MEMORY.md` task groups and a profile.

Two files matter, both under `<config_dir>/memories/`:

- `MEMORY.md` — repeated `# Task Group: <name>` sections, each carrying an
  `applies_to: cwd=<path>; ...` line and, among its subsections, exactly
  three bullet lists this reader turns into entries: `## User preferences`,
  `## Reusable knowledge`, `## Failures and how to do differently`. The
  group's own `## Task N: ...` subsections (rollout file references, search
  keywords) describe *how the group was produced*, not something learned, so
  they are read for context only and never become an entry.
- `memory_summary.md` — a `## User Profile` prose block and its own
  `## User preferences` bullet list, both about the person rather than any
  project, plus `## What's in Memory`, which is read for one thing only: the
  **search terms** Codex states per task group (see below). `## General
  Tips` restates what `MEMORY.md` already holds — the same kind of index
  Claude Code's own `MEMORY.md` is, and skipped for the same reason (FR-004).

What a reader produces is a `RawEntry`, and a raw entry is **the input layer,
not the product** (FR-008). It is written verbatim under the partition's
`.raw/`, and the distil pass is what turns entries into Coffer's own notes
(FR-020). That is why nothing here tries to write something a person will
read: a title derived from a bullet's first clause would be a poor note
title, and is a perfectly good handle for a pass that is going to rewrite the
material anyway. The verbatim rule that used to govern what Coffer *stored*
now governs only this layer, which is exactly where it earns its keep — a
note's claim stays checkable against the agent's own words.

## The search terms, and why they are matched rather than read off

FR-004 requires that where a source states its own search terms, the reader
carries them: Codex has already answered "what would you look this up by"
better than any later guess, and discarding that answer is what left the
previous design's retrieval to guesswork. Codex states them in
`memory_summary.md`, one bullet per task group; the material they belong to
is in `MEMORY.md`. So `_read_groups` reads the sibling summary alongside the
groups (`_sibling_summary`) and joins the two on the group's title.

**That join is fuzzy, and deliberately conservative.** Codex does not repeat
a group's title verbatim in its summary — it re-words it. On the maintainer's
live files, 16 summary topics against 29 task groups produced **zero** exact
title matches: `account SPACE Config Center cache-pipeline regional
configuration` is summarised as `SPACE Config Center cache-pipeline regional
configuration`, and `account core SPB-66270 UserID Buffer producer control
and balanced scheduler design` as `SPB-66270 UserID Buffer Producer Error
Handling and scheduler_balanced`. Reading the terms off an exact match would
therefore have carried none of them.

So the match is on token coverage (`_match_terms_to_groups`) with one rule
standing over it: **a wrong attribution is worse than none.** Terms are
attached only when exactly one group clears the coverage bar and exactly one
summary topic claims that group. On the live files that carries terms for 12
of 16 topics, every one of them correct by inspection; the four it declines
are genuinely ambiguous — two summary topics that roll several task groups
into one line, and two that score identically against two groups apiece
(`SPB-65312 privacy compatibility` fits both of the two SPB-65312 groups).
Those four groups get no terms, which is the intended outcome, not a gap to
be closed by lowering the bar.

`## What's in Memory` also carries a `desc:` and a `learnings:` line per
topic, and `learnings:` in particular is Codex's sharpest prose — a distilled
conclusion where the group's own bullets are working notes. Neither becomes
an entry, for two reasons. FR-004 names which sections become entries and
those are not among them; and `.raw/` is the layer that must stay *faithful*
(FR-008) while Coffer's own distillation happens later and in one place
(FR-023). Feeding the pass Codex's pre-compressed summary instead of the
material it was compressed from would distil a distillation — the same
mistake, one level up, that this layer's rewrite was built to stop making.
The terms are different: they are metadata about where material is findable,
not a second telling of it, and nothing else in either file records them.

`raw_memories.md` and `rollout_summaries/` are never read: they are the raw
transcripts Codex already distilled into the two files above, and FR-003
forbids this layer from reading transcripts a second time.

Codex's file *format* — splitting `MEMORY.md` into groups and extracting each
group's routed cwd(s), and parsing the summary's topic bullets into titles
and terms — is `domain.agent.codex_memory`'s job, shared with the agent
page's native-memory listing (`infrastructure.agent.codex_memory_store`) so
the two never drift apart on what counts as a path in an `applies_to` line.
This reader owns the aggregation-specific policy on top: which sections
become entries, how a bullet gets a title, how its anchor is built, and which
summary topic is judged to describe which group.
"""

from __future__ import annotations

import hashlib
import pathlib
import re
from collections.abc import Iterable

from coffer.domain.agent.codex_memory import (
    parse_codex_memory,
    parse_codex_summary_topics,
    section_bullets,
    section_text,
)
from coffer.domain.memory.errors import UnreadableMemory
from coffer.domain.memory.note import TYPE_PROJECT, TYPE_USER
from coffer.domain.memory.reader import RawEntry, SourceFile

_MEMORY_NAME = "MEMORY.md"
_SUMMARY_NAME = "memory_summary.md"

# The three per-group bullet lists this reader turns into entries, and the
# type each maps to. "User preferences" is the person's own standing
# preference — TYPE_USER. "Reusable knowledge" and "Failures and how to do
# differently" are both about the *project* the group's `cwd` names — a
# technique that works in this codebase, or a trap already hit in it — which
# is TYPE_PROJECT per note.py's own description ("a decision, a trap, a piece
# of its history"). TYPE_FEEDBACK is reserved for a standing instruction the
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

# Title-matching policy for joining a summary topic to a task group.
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")
# Words that carry no distinguishing weight in a title and would otherwise
# lift a near-miss over the bar.
_TITLE_STOPWORDS = frozenset({"a", "an", "and", "for", "in", "of", "on", "or", "the", "to", "with"})
# A topic title with fewer distinguishing tokens than this is not matched at
# all: two or three shared generic words are not evidence, and a short title
# can score a perfect coverage against a group it has nothing to do with.
_MIN_TITLE_TOKENS = 3
# The share of a topic title's tokens a group's title must account for. 0.6
# separates every correct pairing on the maintainer's files (lowest correct
# score: 0.75) from every incorrect one (highest: 0.40) with room on both
# sides, and the uniqueness rule below is what actually guards the result.
_MIN_TITLE_COVERAGE = 0.6


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

    def read(self, source: SourceFile) -> tuple[RawEntry, ...]:
        path = pathlib.Path(source.path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise UnreadableMemory(source.path, str(exc)) from exc

        if path.name == _SUMMARY_NAME:
            return _read_summary(text)
        if path.name == _MEMORY_NAME:
            return _read_groups(text, _sibling_summary(path))
        raise UnreadableMemory(source.path, f"unrecognised Codex memory file {path.name!r}")


def _sibling_summary(memory_path: pathlib.Path) -> str:
    """The summary text beside a `MEMORY.md`, or "" when there is none.

    The search terms belong to `MEMORY.md`'s groups but are written in the
    file next door, so reading the groups means opening both (the acceptance
    scenario says as much: "when the Codex reader reads both files"). The
    path is derived from the source's own parent, never from anything inside
    a file, so FR-044's traversal guard has nothing to catch here.

    A missing or unreadable sibling degrades to no terms rather than raising:
    the group material itself parsed fine, and FR-005's loud failure is for a
    source Coffer cannot read at all, not for an absent optional one. The
    cost of the degradation is that a pass in which only the summary changed
    leaves `MEMORY.md` hash-unchanged and therefore unre-read (FR-006), so
    newly stated terms arrive with the group's next edit. Codex regenerates
    both files in one pass, so in practice they move together.
    """
    try:
        return (memory_path.parent / _SUMMARY_NAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _read_groups(text: str, summary_text: str) -> tuple[RawEntry, ...]:
    groups = parse_codex_memory(text)
    terms_by_title = _match_terms_to_groups(summary_text, (g.title for g in groups))
    entries: list[RawEntry] = []
    for entry in groups:
        # A group can route to more than one cwd (`applies_to: cwd=A and B`);
        # attributing every entry to all of them would give the same anchor
        # two homes and blur which partition a note built from it belongs to
        # (FR-018), so — same as the un-ambiguous, overwhelmingly common
        # single-cwd case — the first recorded cwd is the one project a
        # group's entries are filed under. A group with none files under ""
        # (global).
        project_root = entry.cwds[0] if entry.cwds else ""
        search_terms = terms_by_title.get(entry.title, ())
        for heading, entry_type in _GROUP_SECTIONS.items():
            for bullet in section_bullets(entry.body, heading):
                entries.append(
                    RawEntry(
                        title=_bullet_title(bullet),
                        description=bullet,
                        type=entry_type,
                        body=bullet,
                        anchor=_anchor(entry.title, heading, bullet),
                        project_root=project_root,
                        search_terms=search_terms,
                    )
                )
    return tuple(entries)


def _read_summary(text: str) -> tuple[RawEntry, ...]:
    entries: list[RawEntry] = []
    profile = section_text(text, _PROFILE_HEADING).strip()
    if profile:
        entries.append(
            RawEntry(
                title=_PROFILE_HEADING,
                description=profile,
                type=TYPE_USER,
                body=profile,
                anchor="profile::user-profile",
                project_root="",
            )
        )
    for bullet in section_bullets(text, _PROFILE_PREFS_HEADING):
        entries.append(
            RawEntry(
                title=_bullet_title(bullet),
                description=bullet,
                type=TYPE_USER,
                body=bullet,
                anchor=_anchor("profile", _PROFILE_PREFS_HEADING, bullet),
                project_root="",
            )
        )
    # No `search_terms` here on purpose: Codex states terms per *task group*,
    # and the profile is about the person, not about any group. Inventing
    # terms for it would be exactly the guess FR-004 exists to avoid.
    return tuple(entries)


def _match_terms_to_groups(
    summary_text: str, group_titles: Iterable[str]
) -> dict[str, tuple[str, ...]]:
    """Which task group each summary topic's search terms belong to.

    Keyed by group title, so `_read_groups` can look one up directly. A group
    absent from the result is one no topic could be attributed to without
    guessing — see this module's docstring for why that is common and why it
    is preferred to the alternative.

    Two independent uniqueness rules, both of which must hold:

    - **One group clears the bar for a topic.** Two groups scoring above
      `_MIN_TITLE_COVERAGE` means the topic does not identify either of them;
      a higher score is not a tie-break, because Codex genuinely writes one
      summary line covering two related groups and the higher score would
      then be attaching a group's terms to the wrong half.
    - **One topic claims a group.** Two topics landing on one group is the
      same ambiguity read from the other end, and neither claim survives it.
    """
    titles = tuple(dict.fromkeys(group_titles))
    scored = [(title, _title_tokens(title)) for title in titles]
    claims: dict[str, list[tuple[str, ...]]] = {}
    for topic in parse_codex_summary_topics(summary_text):
        if not topic.search_terms:
            continue
        topic_tokens = _title_tokens(topic.title)
        if len(topic_tokens) < _MIN_TITLE_TOKENS:
            continue
        above = [
            title
            for title, tokens in scored
            if len(topic_tokens & tokens) / len(topic_tokens) >= _MIN_TITLE_COVERAGE
        ]
        if len(above) != 1:
            continue
        claims.setdefault(above[0], []).append(topic.search_terms)
    return {title: terms[0] for title, terms in claims.items() if len(terms) == 1}


def _title_tokens(title: str) -> frozenset[str]:
    """A title reduced to the words that distinguish it.

    Lowercased, split on everything that is not a letter or a digit — which
    also dissolves the backticks Codex quotes identifiers in and the
    punctuation the two files disagree about (`account.gateway` against
    `account-gateway`, `scheduler_balanced` against `balanced scheduler`) —
    and stripped of stopwords.
    """
    return frozenset(
        token
        for token in _TOKEN_SPLIT_RE.split(title.lower())
        if token and token not in _TITLE_STOPWORDS
    )


def _bullet_title(bullet: str) -> str:
    """A short handle from a bullet's first clause.

    Codex's bullets are freeform prose with no author-given title (unlike
    Claude Code's frontmatter `name`). The first clause — up to the first
    `->`, `. ` or `; ` — reads as a reasonable stand-in; the full bullet
    stays intact as the description and the body, and the body is what lands
    verbatim under `.raw/` (FR-008), so nothing is lost by a handle that
    trims it. It is not trying to be a title a person will read: the note's
    title is Coffer's to write, later, in the distil pass (FR-020).
    """
    clause = re.split(r"\s*->\s*|\.\s|;\s", bullet, maxsplit=1)[0].strip().rstrip(".")
    if not clause:
        clause = bullet.strip()
    if len(clause) > 100:
        clause = clause[:97].rstrip() + "..."
    return clause


def _anchor(group: str, heading: str, bullet: str) -> str:
    """Stable identity for one bullet (FR-009): group + section + content.

    Two different bullets in the same section hash differently; the same
    bullet re-read on a later sync hashes the same, which is the whole point
    — the anchor is half of a note's provenance (FR-018) and the name a raw
    entry keeps under `.raw/`, so a note must still point at the entry it was
    built from after MEMORY.md is regenerated with this group's text
    unchanged.
    """
    digest = hashlib.sha256(bullet.encode("utf-8")).hexdigest()[:16]
    return f"{group}::{heading}::{digest}"
