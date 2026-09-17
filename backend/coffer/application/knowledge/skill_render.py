"""Rendering the knowledge skill.

This is the whole of the layer's delivery half (spec knowledge FR-034 to FR-037),
and it is pure: text in, text out, no filesystem and no ports. The writing of
it is ``skill_delivery``. One rendering serves every agent — the catalogue it
carries is the whole enabled corpus, not a per-agent slice of it.

Two levels, and they are not interchangeable:

* **The frontmatter description is always in the model's context.** It is
  roughly 160 tokens Coffer spends on every session whether or not knowledge is
  ever touched, so it must carry things a model can *match*: the subjects the
  corpus covers, in the collections' own words. The version this replaces spent
  that budget describing the layer ("a fact about THIS user's working
  environment"), and across 448 sessions no model ever recognised it.
* **The body is read only when the model reaches for it**, so it can afford to
  be the whole catalogue — every topic document's path, title and description,
  measured at ~5.2K tokens for 58 documents. That is the point: once the model
  has opened this, it never has to guess what exists or what a file is called.

Nothing here tells the agent to call a Coffer tool for reading, because there
is none (FR-033). It gives absolute paths and gets out of the way.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.knowledge.entry import CollectionEntry, FileEntry

SKILL_NAME = "coffer-knowledge"

#: Skill frontmatter descriptions are capped by the importers that read them;
#: 1024 characters is the tightest ceiling in play, so it is the one rendered
#: against. Subjects are dropped from the tail rather than the description
#: being cut mid-sentence.
MAX_DESCRIPTION_CHARS = 1024

_LEAD = "Facts about THIS user's working environment that are not in the repository in front of you"

_TAIL = (
    "Read it before asking the user something they may already have written down, "
    "and use coffer__write when you learn something durable. NOT for facts you can "
    "read out of the current repository, and NOT a place for secrets."
)

Catalogue = Sequence[tuple[CollectionEntry, Sequence[FileEntry]]]


def _subject(entry: CollectionEntry) -> str:
    """One collection reduced to the phrase a model might match on.

    The collection's own README first sentence, which is the thing the person
    wrote to say what this is for (FR-011). A collection with no README
    contributes only its name, which is why an undescribed collection is an
    undiscoverable one.
    """
    description = " ".join(entry.description.split())
    if not description:
        return entry.name
    first = description.split(". ")[0].rstrip(".")
    return f"{entry.name} ({first})"


def render_description(catalogue: Catalogue) -> str:
    """The frontmatter description: what this corpus is actually about."""
    subjects = [
        _subject(entry) for entry, _ in catalogue if entry.topic_count or entry.source_count
    ]
    if not subjects:
        return f"{_LEAD}. Nothing has been filed yet. {_TAIL}"
    while subjects:
        joined = "; ".join(subjects)
        candidate = f"{_LEAD} — covering {joined}. {_TAIL}"
        if len(candidate) <= MAX_DESCRIPTION_CHARS:
            return candidate
        subjects.pop()
    return f"{_LEAD}. {_TAIL}"


def _catalogue_lines(root: str, entry: CollectionEntry, topics: Sequence[FileEntry]) -> list[str]:
    lines = [f"### {entry.name}"]
    if entry.description:
        lines += ["", " ".join(entry.description.split())]
    if not topics:
        lines += [
            "",
            "_Nothing curated here yet._ Material has been filed but Coffer has not "
            "folded it into documents; there is nothing to read in this collection "
            "right now.",
        ]
        return lines
    lines += ["", f"Files live under `{root}/{entry.name}/topics/`.", ""]
    for topic in topics:
        # The path an agent Reads is the absolute one; giving the relative form
        # as well would invite it to guess a base, which is the guessing this
        # whole design removes.
        relative = topic.path.split("/", 2)[-1]
        description = " ".join(topic.description.split())
        lines.append(
            f"- `{relative}` — **{topic.title}**" + (f": {description}" if description else "")
        )
    return lines


def render_body(root: str, catalogue: Catalogue) -> str:
    """The skill body: how to read the corpus, and everything in it."""
    total = sum(len(topics) for _, topics in catalogue)
    lines = [
        "# Coffer's knowledge",
        "",
        "A directory of Markdown documents about this user's working environment, "
        "shared by them and every agent they run. **Read it with your own file "
        "tools.** There is no Coffer tool for reading, listing or searching it: "
        "the full catalogue is below, so open the file you want directly.",
        "",
        f"Everything lives under `{root}/`.",
        "",
        "## How to use it",
        "",
        "1. Find the document you want in the catalogue below — every one of them "
        f"is listed ({total} in total), with what it answers.",
        f"2. Read it with your normal file-reading tool at `{root}/<collection>/topics/<path>`.",
        "3. Need something the titles do not cover? Grep the same directory for a "
        "literal string — an identifier, a service name, a CJK phrase. It matches "
        "bytes, so nothing is stemmed away.",
        "",
        "## Writing something down",
        "",
        "Use **`coffer__write`** when you learn something durable — a fact about a "
        "service, a convention the user follows, a decision and its reason, a trap "
        "and how to avoid it. What you write is filed as **source material** under "
        "`sources/`, and Coffer's own model then folds it into the documents below, "
        "merging it with what is already there. So write the fact plainly: you do "
        "not have to decide where it belongs, and you do not have to check whether "
        "it repeats something.",
        "",
        "Do not write into `topics/` yourself, and do not edit those files: they are "
        "generated, and the next pass will overwrite them. A correction goes in as a "
        "new source saying what is actually true.",
        "",
        "## What is in here",
        "",
    ]
    if not catalogue:
        lines.append("_No collections have been created yet._")
    for entry, topics in catalogue:
        lines += _catalogue_lines(root, entry, topics)
        lines.append("")
    lines += [
        "## What this is not",
        "",
        "Not a secret store — no keys, tokens or credentials. Not a scratch pad: "
        "what goes in is meant to be true in a month. And not the repository — if "
        "the answer is in the code in front of you, read the code.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def render(root: str, catalogue: Catalogue) -> str:
    """The complete `SKILL.md`, as every agent receives it."""
    description = render_description(catalogue)
    return (
        "---\n"
        f"name: {SKILL_NAME}\n"
        f"description: {description}\n"
        "---\n"
        "\n"
        f"{render_body(root, catalogue)}"
    )


__all__ = [
    "MAX_DESCRIPTION_CHARS",
    "SKILL_NAME",
    "render",
    "render_body",
    "render_description",
]
