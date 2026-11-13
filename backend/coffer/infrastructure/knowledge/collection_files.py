"""The writes a collection's own files take besides its documents: its README
as a new collection starts it, its description, and every file of a deleted
collection put back.

A collection has no title (spec knowledge "Read a collection's description from
its README"): its heading is its folder name, and what it is about is the first
paragraph of its ``README.md``, before its first section. A new collection
starts from a template (spec knowledge "Start a collection from a template"):
a blank one is a README with a heading and that paragraph and nothing else, because
the format is the collection's own. Editing that description rewrites exactly that
paragraph and leaves the rest of the README — anything a person wrote under it —
as it was.

Restoring a deleted collection (spec knowledge "Undo a knowledge delete from its
toast") puts back, byte for byte, every file the delete
removed: its documents and its README.
Documents go through the same guard every document write does; the README is
the one non-document path a collection holds.
"""

from __future__ import annotations

from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.assets import write_bytes
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.fs import atomic_write, decode


def blank_readme(collection: str, description: str | None) -> str:
    """A blank collection's README: its heading and its description."""
    text = (description or "").strip()
    return f"# {collection}\n" + (f"\n{text}\n" if text else "")


def write_template(collection: str, files: dict[str, str]) -> None:
    """Write a template's files into a new collection: each a path relative to
    the collection and its text. Nothing is overwritten."""
    for relpath, text in files.items():
        target = paths.resolve(f"{collection}/{relpath}")
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, text)


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
        atomic_write(readme, blank_readme(collection, description))
        return
    raw = readme.read_text(encoding="utf-8", errors="replace")
    _, body = split_frontmatter(raw)
    # Whatever precedes the body — a frontmatter fence a person added — is kept.
    head = raw[: len(raw) - len(body)] if raw.endswith(body) else ""
    atomic_write(readme, head + _replace_first_paragraph(body, description))


def restore_file(relpath: str, raw: bytes) -> None:
    """Put back one file of a deleted collection exactly as it was: a document,
    the README, or a picture or other attachment. Anything that
    is not Markdown — a picture, a diagram's source, a raw export — goes back
    byte for byte, never through a text decode."""
    segments = paths.split(relpath)
    if len(segments) == 2 and segments[1] == paths.README_NAME:
        target = paths.readme_path(segments[0])
    else:
        paths.require_document(relpath)
        target = paths.resolve(relpath)
    if not target.name.endswith(".md"):
        write_bytes(paths.relative_of(target), raw)
        return
    atomic_write(target, decode(raw))


def current_bytes(relpath: str) -> bytes | None:
    """A document's bytes on disk now, ``None`` when it is not there."""
    target = paths.resolve(relpath)
    try:
        return target.read_bytes() if target.is_file() else None
    except OSError:
        return None


def remove_file(relpath: str) -> None:
    """Remove one document an undone change had added; nothing if it is gone."""
    target = paths.resolve(relpath)
    target.unlink(missing_ok=True)


__all__ = [
    "blank_readme",
    "current_bytes",
    "remove_file",
    "restore_file",
    "write_description",
    "write_template",
]
