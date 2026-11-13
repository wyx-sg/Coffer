"""Rendering Coffer's own skill — the one manual every agent on this machine gets.

It is one skill, not a set, and the reason is where the cost falls. A skill's
frontmatter description is resident in every session whether or not the skill is
ever opened (~160 tokens here); the body is paid for only when a model reaches
for it. A set of skills would spend the resident budget several times over to
describe things most sessions never touch.

So there is one description, carrying what a model can actually match on, and
one body carrying everything else: Coffer's one tool, the tiering contract that
means the tool list is not the whole catalogue, the read-it-yourself shape of
the knowledge layer, the ``coffer log`` readers of Coffer's own records, and
the full knowledge catalogue.

Pure: text in, text out. No filesystem beyond reading this package's own asset,
and no ports. The writing of it is ``application.skill.builtin_seed``, reached
through the composition root — this module knows nothing about skills as
resources, and the skill kind knows nothing about knowledge (import-linter's
cross-kind fences).

**The output must be a pure function of this build and the catalogue it is given** (spec
knowledge "Render the guide skill deterministically"): the same build over the same
collections renders the same bytes, every time.

The reason is not convergence. This artifact does not converge — neither the master
folder nor the row (spec vault-sync "Withhold derived output in both halves") —
precisely because it is rendered from files that converge *plus* this machine's own
registry, so two machines are expected to differ whenever their collections do. What
determinism buys is local: an unchanged catalogue re-rendering to the same bytes is what
lets the seed skip the write, so a boot or a sweep tick that changed nothing
registers nothing, audits nothing and re-delivers nothing, and the row's
``version_hash`` means "the content moved" rather than "time passed".

It is also why the knowledge root is rendered ``~``-relative under the home.
"""

from __future__ import annotations

import pathlib
import re
from collections.abc import Sequence
from importlib import resources

import yaml

from coffer.domain.knowledge.entry import CollectionEntry, FileEntry

#: The skill's name, its master folder name (under ``~/.coffer/derived/skills/``:
#: the folder is rendered from the build, so it is derived output, not vault
#: content), and the directory name every agent receives it as.
GUIDE_SKILL_NAME = "coffer-guide"

#: Skill frontmatter descriptions are capped by the importers that read them;
#: 1024 characters is the tightest ceiling in play, so it is the one rendered
#: against. Subjects are dropped from the tail rather than the description being
#: cut mid-sentence.
MAX_DESCRIPTION_CHARS = 1024

#: Replaced in the asset with the knowledge root as ``display_root`` gives it.
_ROOT_PLACEHOLDER = "<KNOWLEDGE_ROOT>"

#: A line ``<!-- when:<feature> -->`` opens a span of the asset that belongs to
#: one experimental feature, ``<!-- end:<feature> -->`` closes it; spans nest.
#: The marker lines are never rendered, and a span is dropped whole while its
#: feature is off (spec experimental-features "Withdraw what a switched-off
#: feature put in front of agents") — so the manual never documents a tool the
#: gateway would answer as unknown.
_SPAN_OPEN = re.compile(r"^<!-- when:([a-z_]+) -->$")
_SPAN_CLOSE = re.compile(r"^<!-- end:([a-z_]+) -->$")

_ASSET = "coffer-guide.md"

# Where a README description's first sentence ends, in English or Chinese.
_SENTENCE_END = re.compile(r"\.\s|。")

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


def _display(path: pathlib.Path, *, home: pathlib.Path | None) -> str:
    base = home or pathlib.Path.home()
    try:
        return f"~/{path.relative_to(base).as_posix()}"
    except ValueError:
        return str(path)


def display_root(root: pathlib.Path, *, home: pathlib.Path | None = None) -> str:
    """The knowledge root as the skill should name it.

    ``~/.coffer/vault/knowledge`` — the tilde form of any root under the home,
    and the absolute path otherwise. The tilde form keeps the rendered bytes
    free of this machine's home directory, and a path an agent reads should be
    one a person can retype; the artifact itself does not converge (see the
    module docstring), so this is not about two copies agreeing. A root
    outside the home (a home that is itself a symlink resolved elsewhere) is
    named absolutely, because an accurate path matters more than a stable one.
    """
    return _display(root, home=home)


def _subject(entry: CollectionEntry) -> str:
    """One collection reduced to the phrase a model might match on.

    The collection's own README first sentence — what the person wrote to say
    what this is for. A collection with no README contributes only its name,
    which is why an undescribed collection is an undiscoverable one.
    """
    description = " ".join(entry.description.split())
    if not description:
        return entry.name
    first = _SENTENCE_END.split(description, maxsplit=1)[0].rstrip(".")
    return f"{entry.name} ({first})"


def _lead(*, knowledge: bool) -> str:
    """The description's first sentence: what Coffer is and which tools it has."""
    head = _LEAD_WITH_KNOWLEDGE if knowledge else _LEAD_WITHOUT_KNOWLEDGE
    covers = f"Covers its own tool ({_SEARCH_TOOLS_GLOSS})"
    if knowledge:
        return (
            f"{head}. {covers}, how to write, tidy and check knowledge (整理知识), "
            "and THIS developer's own knowledge"
        )
    return f"{head}. {covers}"


def render_description(catalogue: Catalogue | None) -> str:
    """The frontmatter description: the one part always in a model's context.

    ``None`` is the knowledge feature switched off: no subjects, and a lead
    that does not promise any knowledge.
    """
    if catalogue is None:
        lead = _lead(knowledge=False)
        return f"{lead}. {_TAIL}"[:MAX_DESCRIPTION_CHARS]
    lead = _lead(knowledge=True)
    subjects = [_subject(entry) for entry, _ in catalogue if entry.note_count]
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


def _manual(root: str, *, knowledge: bool) -> str:
    """The static half with the switched-off features' spans taken out."""
    enabled = {"knowledge"} if knowledge else set()
    return _select_spans(_static_body(), enabled).replace(_ROOT_PLACEHOLDER, root)


#: The catalogue's budget in characters. Past it the catalogue drops every
#: description, and past it again lists only each collection's counts and the
#: directories to search (spec knowledge "Merge the manual and the catalogue in
#: the skill body"): the body is paid for whenever an agent opens the skill.
MAX_CATALOGUE_CHARS = 60_000

#: The three levels of detail, most first.
_FULL, _TITLES, _COUNTS = "full", "titles", "counts"


def _entry_line(file: FileEntry, *, describe: bool, base: str) -> str:
    relative = file.path.split("/", 1)[-1]
    shown = relative[len(base) + 1 :] if base and relative.startswith(base + "/") else relative
    line = f"- `{shown}` — **{file.title}**"
    description = " ".join(file.description.split()) if describe else ""
    return line + (f": {description}" if description else "")


def _by_folder(files: Sequence[FileEntry]) -> list[tuple[str, list[FileEntry]]]:
    """Files grouped by the folder they sit in, inside the collection; the
    root first."""
    groups: dict[str, list[FileEntry]] = {}
    for file in files:
        relative = file.path.split("/", 1)[-1]
        folder = relative.rsplit("/", 1)[0] if "/" in relative else ""
        groups.setdefault(folder, []).append(file)
    return sorted(groups.items(), key=lambda item: (item[0] != "", item[0]))


def _how_to_read(entry: CollectionEntry, where: str) -> str:
    """The one line that tells an agent which file holds the collection's
    rules and where to start reading it."""
    parts = [f"Files live under `{where}/`."]
    if entry.rules_file:
        parts.append(
            f"Its rules are in `{entry.rules_file}`: read them before you write here, "
            "and follow them over anything this file says about format."
        )
    else:
        parts.append("It names no rules file: write in it the way its existing files are written.")
    if entry.entry_file:
        parts.append(f"Start reading at `{entry.entry_file}`.")
    return " ".join(parts)


def _catalogue_lines(
    root: str, entry: CollectionEntry, files: Sequence[FileEntry], detail: str
) -> list[str]:
    """One collection: its description, its rules file and entry page, and —
    when it names no entry page — its files by folder (spec knowledge "Merge
    the manual and the catalogue in the skill body")."""
    if entry.linked:
        heading = f"### {entry.name} (linked folder)"
        where = _display(pathlib.Path(entry.folder_path), home=None)
        kept = (
            "A folder the developer keeps with their own tools; Coffer only shares it "
            "with you, so do not tidy it, upload into it or drop files for its inbox."
        )
    else:
        heading = f"### {entry.name}"
        where = f"{root}/{entry.name}"
        kept = ""
    lines = [heading]
    if entry.description:
        lines += ["", " ".join(entry.description.split())]
    lines += ["", " ".join(p for p in (_how_to_read(entry, where), kept) if p)]
    if not files:
        return [*lines, "", "_No Markdown files here yet._"]
    if entry.entry_file or detail == _COUNTS:
        return [*lines, "", f"{len(files)} Markdown files. Search the folder for the rest."]
    describe = detail == _FULL
    for folder, group in _by_folder(files):
        lines += ["", f"**{folder}/**" if folder else "**(root)**", ""]
        lines += [_entry_line(f, describe=describe, base=folder) for f in group]
    return lines


def _render_catalogue_at(root: str, catalogue: Catalogue, detail: str) -> str:
    lines = [
        "## What is in this developer's knowledge",
        "",
        "Each collection, where its rules are and where to start reading it. A "
        "collection that names no start page lists its files. Read any file at "
        f"`{root}/<collection>/<path>` with your own file tool; a linked folder lives "
        "where its own section says.",
        "",
    ]
    if detail == _TITLES:
        lines += ["_Shortened: descriptions are left out. Read a file for its own._", ""]
    elif detail == _COUNTS:
        lines += ["_Shortened: only counts are listed. Search each collection yourself._", ""]
    if not catalogue:
        lines.append("_No collections have been created yet._")
    for entry, files in catalogue:
        lines += _catalogue_lines(root, entry, files, detail)
        lines.append("")
    return "\n".join(lines).rstrip()


def render_catalogue(root: str, catalogue: Catalogue) -> str:
    """The generated half: every collection with its rules file and start
    page, shortened to fit :data:`MAX_CATALOGUE_CHARS`."""
    for detail in (_FULL, _TITLES):
        text = _render_catalogue_at(root, catalogue, detail)
        if len(text) <= MAX_CATALOGUE_CHARS:
            return text
    return _render_catalogue_at(root, catalogue, _COUNTS)


def render_body(root: str, catalogue: Catalogue | None) -> str:
    """The skill body: the manual, then the catalogue — or the manual alone,
    without its knowledge sections, while the knowledge feature is switched off
    (``None``)."""
    static = _manual(root, knowledge=catalogue is not None).rstrip()
    if catalogue is None:
        return f"{static}\n"
    return f"{static}\n\n{render_catalogue(root, catalogue)}\n"


def render_frontmatter(catalogue: Catalogue | None) -> str:
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
        {"name": GUIDE_SKILL_NAME, "description": render_description(catalogue)},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=10**9,
    )


def render(root: str, catalogue: Catalogue | None) -> str:
    """The complete `SKILL.md`, as every agent receives it.

    ``catalogue`` is ``None`` while the knowledge feature is switched off: the
    skill is then rendered without its knowledge catalogue or the sections
    that document writing and tidying knowledge (spec experimental-features
    "Withdraw what a switched-off feature put in front of agents")."""
    frontmatter = render_frontmatter(catalogue)
    body = render_body(root, catalogue)
    return f"---\n{frontmatter}---\n\n{body}"


__all__ = [
    "GUIDE_SKILL_NAME",
    "MAX_CATALOGUE_CHARS",
    "MAX_DESCRIPTION_CHARS",
    "display_root",
    "render",
    "render_body",
    "render_catalogue",
    "render_description",
    "render_frontmatter",
]
