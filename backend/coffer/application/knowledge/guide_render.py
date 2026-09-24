"""Rendering Coffer's own skill — the one manual every agent on this machine gets.

It is one skill, not a set, and the reason is where the cost falls. A skill's
frontmatter description is resident in every session whether or not the skill is
ever opened (~160 tokens here); the body is paid for only when a model reaches
for it. A set of skills would spend the resident budget several times over to
describe things most sessions never touch.

So there is one description, carrying what a model can actually match on, and
one body carrying everything else: Coffer's tools, the tiering contract that
means the tool list is not the whole catalogue, the read-it-yourself shape of
the knowledge layer, the fact that Coffer never writes an agent's memory, and
the full knowledge catalogue.

Pure: text in, text out. No filesystem beyond reading this package's own asset,
and no ports. The writing of it is ``application.skill.builtin_seed``, reached
through the composition root — this module knows nothing about skills as
resources, and the skill kind knows nothing about knowledge (import-linter's
cross-kind fences).

**The output must be a pure function of this build and the catalogue it is given** (spec
knowledge "Render the guide skill deterministically"): the same build over the same
enabled collections renders the same bytes, every time.

The reason is not convergence. This artifact does not converge — neither the master
folder nor the row (spec vault-sync "Withhold derived output in both halves") —
precisely because it is rendered from files that converge *plus* this machine's own
reach, so two machines are expected to differ whenever their enabled sets do. What
determinism buys is local: an unchanged catalogue re-rendering to the same bytes is what
lets the seed skip the write, so a boot or a curation tick that changed nothing
registers nothing, audits nothing and re-delivers nothing, and the row's
``version_hash`` means "the content moved" rather than "time passed".

That is still why the knowledge root is rendered in its ``~``-relative form
whenever it sits in the default place — though the reason there has always been
partly that a path an agent reads should be one a person can retype.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Sequence
from importlib import resources

import yaml

from coffer.domain.knowledge.entry import CollectionEntry, FileEntry

#: The skill's name, its master folder name under ``~/.coffer/skills/``, and the
#: directory name every agent receives it as.
GUIDE_SKILL_NAME = "coffer-guide"

#: Skill frontmatter descriptions are capped by the importers that read them;
#: 1024 characters is the tightest ceiling in play, so it is the one rendered
#: against. Subjects are dropped from the tail rather than the description being
#: cut mid-sentence.
MAX_DESCRIPTION_CHARS = 1024

#: Replaced in the asset with the knowledge root as ``display_root`` gives it.
_ROOT_PLACEHOLDER = "<KNOWLEDGE_ROOT>"

#: Replaced in the asset with how many ``coffer__`` tools the manual describes.
_TOOL_COUNT_PLACEHOLDER = "<TOOL_COUNT>"

#: A line ``<!-- when:<feature> -->`` opens a span of the asset that belongs to
#: one experimental feature, ``<!-- end:<feature> -->`` closes it; spans nest.
#: The marker lines are never rendered, and a span is dropped whole while its
#: feature is off (spec experimental-features "Withdraw what a switched-off
#: feature put in front of agents") — so the manual never documents a tool the
#: gateway would answer as unknown.
_SPAN_OPEN = re.compile(r"^<!-- when:([a-z_]+) -->$")
_SPAN_CLOSE = re.compile(r"^<!-- end:([a-z_]+) -->$")

_ASSET = "coffer-guide.md"

_COUNT_WORDS = {2: "Two", 3: "Three", 4: "Four"}

_LEAD_WITH_KNOWLEDGE = (
    "Coffer, this machine's local vault — how to use it, and what it already holds"
)

#: The lead while the knowledge feature is switched off: the manual still
#: describes Coffer's tools, and names no knowledge.
_LEAD_WITHOUT_KNOWLEDGE = "Coffer, this machine's local vault — how to use it"

_SEARCH_TOOLS_GLOSS = (
    "coffer__search_tools, which finds upstream tools your tool list does not show"
)

_TAIL = (
    "Read it before asking the developer something they may already have written "
    "down, before concluding a capability is unavailable, and before assuming a "
    "tool call is waiting on their approval."
)

Catalogue = Sequence[tuple[CollectionEntry, Sequence[FileEntry]]]


def display_root(root: pathlib.Path, *, home: pathlib.Path | None = None) -> str:
    """The knowledge root as the skill should name it.

    ``~/.coffer/knowledge`` when the root sits in its default place, and the
    absolute path otherwise. The tilde form is not cosmetic: it is what keeps
    this file identical on two machines whose home directories differ, which is
    what keeps the converging copies from overwriting each other. When the root
    has been moved (``COFFER_KNOWLEDGE_ROOT``), ``~`` would be a lie, and an
    accurate path matters more than a stable one.
    """
    base = (home or pathlib.Path.home()) / ".coffer" / "knowledge"
    return "~/.coffer/knowledge" if root == base else str(root)


def _subject(entry: CollectionEntry) -> str:
    """One collection reduced to the phrase a model might match on.

    The collection's own README first sentence — what the person wrote to say
    what this is for. A collection with no README contributes only its name,
    which is why an undescribed collection is an undiscoverable one.
    """
    description = " ".join(entry.description.split())
    if not description:
        return entry.name
    first = description.split(". ")[0].rstrip(".")
    return f"{entry.name} ({first})"


def _lead(*, knowledge: bool, memory: bool) -> str:
    """The description's first sentence: what Coffer is and which tools it has."""
    tools = [_SEARCH_TOOLS_GLOSS]
    if knowledge:
        tools.append("coffer__write")
    if memory:
        tools.append("coffer__recall")
    tools.append("coffer__diagnose")
    head = _LEAD_WITH_KNOWLEDGE if knowledge else _LEAD_WITHOUT_KNOWLEDGE
    covers = f"Covers its own tools ({'; '.join(tools)})"
    if knowledge:
        return f"{head}. {covers}, and THIS developer's own knowledge"
    return f"{head}. {covers}"


def render_description(catalogue: Catalogue | None, *, memory: bool = True) -> str:
    """The frontmatter description: the one part always in a model's context.

    ``None`` is the knowledge feature switched off: no subjects, and a lead
    that does not promise any knowledge. ``memory`` is the memory feature:
    while it is off the lead does not name ``coffer__recall``.
    """
    if catalogue is None:
        lead = _lead(knowledge=False, memory=memory)
        return f"{lead}. {_TAIL}"[:MAX_DESCRIPTION_CHARS]
    lead = _lead(knowledge=True, memory=memory)
    subjects = [
        _subject(entry) for entry, _ in catalogue if entry.document_count or entry.pending_count
    ]
    while subjects:
        joined = "; ".join(subjects)
        candidate = f"{lead}, covering {joined}. {_TAIL}"
        if len(candidate) <= MAX_DESCRIPTION_CHARS:
            return candidate
        subjects.pop()
    return f"{lead}, which is empty so far. {_TAIL}"[:MAX_DESCRIPTION_CHARS]


def _static_body() -> str:
    """The hand-written half, shipped with the package."""
    return resources.files(__package__).joinpath("skill_assets", _ASSET).read_text(encoding="utf-8")


def _select_spans(text: str, enabled: set[str]) -> str:
    """Drop every span of a feature not in ``enabled``, and every marker line."""
    out: list[str] = []
    stack: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        opened = _SPAN_OPEN.match(stripped)
        if opened:
            stack.append(opened.group(1))
            continue
        closed = _SPAN_CLOSE.match(stripped)
        if closed:
            if not stack or stack[-1] != closed.group(1):
                raise ValueError(f"unbalanced feature span in {_ASSET}: {stripped}")
            stack.pop()
            continue
        if all(feature in enabled for feature in stack):
            out.append(line)
    if stack:
        raise ValueError(f"unclosed feature span in {_ASSET}: {stack[-1]}")
    return "".join(out)


def _manual(root: str, *, knowledge: bool, memory: bool) -> str:
    """The static half with the switched-off features' spans taken out."""
    enabled = {key for key, on in (("knowledge", knowledge), ("memory", memory)) if on}
    count = 2 + len(enabled)  # search_tools and diagnose are always there
    return (
        _select_spans(_static_body(), enabled)
        .replace(_ROOT_PLACEHOLDER, root)
        .replace(_TOOL_COUNT_PLACEHOLDER, _COUNT_WORDS[count])
    )


def _catalogue_lines(
    root: str, entry: CollectionEntry, documents: Sequence[FileEntry]
) -> list[str]:
    lines = [f"### {entry.name}"]
    if entry.description:
        lines += ["", " ".join(entry.description.split())]
    if not documents:
        lines += [
            "",
            "_No documents here yet._ Material has been submitted but Coffer has not "
            "folded it into documents; there is nothing to read in this collection "
            "right now.",
        ]
        return lines
    lines += ["", f"Files live under `{root}/{entry.name}/`.", ""]
    for document in documents:
        relative = document.path.split("/", 1)[-1]
        description = " ".join(document.description.split())
        lines.append(
            f"- `{relative}` — **{document.title}**" + (f": {description}" if description else "")
        )
    return lines


def render_catalogue(root: str, catalogue: Catalogue) -> str:
    """The generated half: every collection, every document."""
    total = sum(len(documents) for _, documents in catalogue)
    lines = [
        "## What is in this developer's knowledge",
        "",
        f"Every document, {total} in all. Read one at "
        f"`{root}/<collection>/<path>` with your own file tool.",
        "",
    ]
    if not catalogue:
        lines.append("_No collections have been created yet._")
    for entry, documents in catalogue:
        lines += _catalogue_lines(root, entry, documents)
        lines.append("")
    return "\n".join(lines).rstrip()


def render_body(root: str, catalogue: Catalogue | None, *, memory: bool = True) -> str:
    """The skill body: the manual, then the catalogue — or the manual alone,
    without its knowledge sections, while the knowledge feature is switched off
    (``None``). ``memory`` off takes the memory sections out likewise."""
    static = _manual(root, knowledge=catalogue is not None, memory=memory).rstrip()
    if catalogue is None:
        return f"{static}\n"
    return f"{static}\n\n{render_catalogue(root, catalogue)}\n"


def render_frontmatter(catalogue: Catalogue | None, *, memory: bool = True) -> str:
    """The `---`-delimited YAML block, with the description safely quoted.

    Emitted through a YAML dumper rather than an f-string, because the
    description is not ours: it is built from the collections' own READMEs,
    and a person writes `Shopee-internal knowledge: the account system` without
    a thought. Interpolated raw, that `: ` is a mapping indicator and the whole
    block stops parsing — the skill then fails validation and is never written
    at all, which is a silent, total failure of this layer. A ` #` is worse
    still, because it parses: everything after it is a comment, so the
    description is truncated and nothing anywhere reports a problem.

    ``width`` is set past any real description so the dumper never folds a long
    line. A folded scalar would still parse, but it would make the bytes depend
    on where the line breaks fall, and these bytes have to be reproducible.
    """
    return yaml.safe_dump(
        {"name": GUIDE_SKILL_NAME, "description": render_description(catalogue, memory=memory)},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=10**9,
    )


def render(root: str, catalogue: Catalogue | None, *, memory: bool = True) -> str:
    """The complete `SKILL.md`, as every agent receives it.

    ``catalogue`` is ``None`` while the knowledge feature is switched off: the
    skill is then rendered without its knowledge catalogue or the sections
    that document ``coffer__write`` and the knowledge root. ``memory`` is the
    memory feature: while it is off the sections documenting
    ``coffer__recall`` are left out."""
    frontmatter = render_frontmatter(catalogue, memory=memory)
    return f"---\n{frontmatter}---\n\n{render_body(root, catalogue, memory=memory)}"


__all__ = [
    "GUIDE_SKILL_NAME",
    "MAX_DESCRIPTION_CHARS",
    "display_root",
    "render",
    "render_body",
    "render_catalogue",
    "render_description",
    "render_frontmatter",
]
