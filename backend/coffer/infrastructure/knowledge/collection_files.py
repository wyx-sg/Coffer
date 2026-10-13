"""The writes a collection's own files take besides its documents: its README
as a new collection starts it, its description, and every file of a deleted
collection put back.

A collection has no title (spec knowledge "Read a collection's description from
its README"): its heading is its folder name, and what it is about is the first
paragraph of its ``README.md``, before its first section. A new collection's
README also carries the default page types and rules, written out so the
person sees what they can change (spec knowledge "Start a collection's README
with its rules written out"). Editing that description rewrites exactly that
paragraph and leaves the rest of the README — anything a person wrote under it —
as it was.

Restoring a deleted collection (spec knowledge "Undo a knowledge delete from its
toast") puts back, byte for byte, every file the delete
removed: its pages and sources, its README, root files such as ``index.md`` or
``log.md``, folders a person made, ``assets/`` and any other file, Markdown or
not, and any inbox items. Every path goes through the same traversal guard as
any knowledge write; an inbox item, the one hidden path a collection holds, is
resolved through the module that owns its shape. Bytes are written as they
were, never decoded, so a picture, a CRLF file and the relative links between
files all come back unchanged.
"""

from __future__ import annotations

from coffer.domain.knowledge.errors import UnsafeKnowledgePath
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.assets import write_bytes
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.fs import atomic_write
from coffer.infrastructure.knowledge.wiki import DEFAULT_VERIFY_DAYS
from coffer.infrastructure.vault.atomic import atomic_write as atomic_write_bytes

#: The rules a new collection's README starts with, below its description.
#: The page types are the guide's defaults; the person changes them here.
DEFAULT_RULES = """\
## Page types

Every page under `pages/` has one `type` from this list. Change, add or remove
types here; agents follow this list over their defaults.

- `overview`: where to start. What this collection covers and which pages to read first.
- `concept`: what something is and why it works the way it does.
- `entity`: one service, system or team. What it owns and how to reach it.
- `how-to`: the steps for one task.
- `decision`: a choice that was made, the options and the reason.

## Rules

- One subject per page. Link related pages with `[[slug]]`.
- Every page lists the sources it draws on in `sources`, and the day it was last
  checked against them or the code in `verified`.
- `verify_after_days` at the top of this file is how many days a check holds
  before Coffer asks for another. `0` turns it off.
"""


def default_readme(collection: str, description: str | None) -> str:
    """A new collection's README: its heading, its description and the
    default rules, with the default recheck interval in its frontmatter."""
    head = f"---\nverify_after_days: {DEFAULT_VERIFY_DAYS}\n---\n\n# {collection}\n\n"
    text = (description or "").strip()
    return head + (f"{text}\n\n" if text else "") + DEFAULT_RULES


def _is_section(stripped: str) -> bool:
    """A second-level or deeper heading: where the README's rules begin."""
    return stripped.startswith("##")


def _replace_first_paragraph(body: str, description: str) -> str:
    """``body`` with its first non-heading paragraph before any section replaced
    by ``description`` (or inserted after the leading headings when it has none)."""
    lines = body.splitlines()
    start = end = None
    section = len(lines)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is None:
            if _is_section(stripped):
                section = i
                break
            if stripped and not stripped.startswith("#"):
                start = i
            continue
        if not stripped:
            end = i
            break
    new = description.strip().splitlines()
    if start is None:
        head = list(lines[:section])
        while head and not head[-1].strip():
            head.pop()
        rest = lines[section:]
        out = [*head, "", *new] if head else list(new)
        if rest:
            out += ["", *rest]
    else:
        out = [*lines[:start], *new, *lines[end if end is not None else len(lines) :]]
    return "\n".join(out).rstrip("\n") + "\n"


def write_description(collection: str, description: str) -> None:
    """Make ``description`` the opening paragraph of ``collection``'s README,
    creating the README (headed by the folder name) when there is none."""
    readme = paths.readme_path(collection)
    if not readme.is_file():
        atomic_write(readme, default_readme(collection, description))
        return
    raw = readme.read_text(encoding="utf-8", errors="replace")
    _, body = split_frontmatter(raw)
    # Whatever precedes the body — a frontmatter fence a person added — is kept.
    head = raw[: len(raw) - len(body)] if raw.endswith(body) else ""
    atomic_write(readme, head + _replace_first_paragraph(body, description))


def restore_file(relpath: str, raw: bytes) -> None:
    """Put back one file of a deleted collection exactly as it was, byte for
    byte: any file under the collection, or an inbox item."""
    in_inbox = paths.inbox_parts(relpath)
    if in_inbox is None:
        if len(paths.split(relpath)) < 2:
            raise UnsafeKnowledgePath(relpath, "a file lives inside a collection")
        write_bytes(relpath, raw)
        return
    collection, item = in_inbox
    if item is None:
        raise UnsafeKnowledgePath(relpath, "the inbox itself is not a file")
    target = paths.inbox_dir(collection) / item
    paths.assert_inside_root(target, relpath)
    atomic_write_bytes(target, raw)


def current_bytes(relpath: str) -> bytes | None:
    """A file's bytes on disk now, ``None`` when it is not there."""
    target = paths.resolve(relpath)
    try:
        return target.read_bytes() if target.is_file() else None
    except OSError:
        return None


def remove_file(relpath: str) -> None:
    """Remove one document an undone change had added; nothing if it is gone."""
    target = paths.resolve(relpath)
    target.unlink(missing_ok=True)


__all__ = ["current_bytes", "remove_file", "restore_file", "write_description"]
