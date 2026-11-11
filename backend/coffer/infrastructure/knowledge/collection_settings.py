"""What a collection says about itself, read off its own files on every call
(spec knowledge "Let each collection declare its own rules").

A collection's format is its own (ADR knowledge-collections-own-their-format):
Coffer knows no page type, no required key and no folder layout. All it reads
is what the collection declares in its ``README.md`` frontmatter, every key
optional:

* ``rules`` — the file whose rules agents follow when they write in it, a path
  relative to the collection (it may reach a shared rules file in another
  collection). Without one, the first of ``AGENTS.md``, ``CLAUDE.md`` and
  ``README.md`` at the collection's root, the same files a linked folder is
  read by.
* ``entry`` — the page an agent starts reading from, an ``index.md`` say. With
  one, the guide names it instead of listing every file.
* ``uploads`` — the folder an upload or a dropped file lands in, ``sources``
  by default. Coffer writes its own material there and nowhere else.

The same reader serves a linked folder, whose README may declare ``rules`` and
``entry`` too (``uploads`` means nothing there: Coffer never writes into one).
"""

from __future__ import annotations

import pathlib
import posixpath
import re
from dataclasses import dataclass
from typing import Any

from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

README_NAME = "README.md"

#: The files a collection's rules may live in, checked at its root in this
#: order when its README declares none.
RULES_FILES = ("AGENTS.md", "CLAUDE.md", README_NAME)

RULES_KEY = "rules"
ENTRY_KEY = "entry"
UPLOADS_KEY = "uploads"

#: Where Coffer writes uploads and dropped files when the README names no folder.
DEFAULT_UPLOADS = "sources"

#: How much of a file is read to find its title.
_HEAD_BYTES = 4096


@dataclass(frozen=True)
class Settings:
    """A collection's declarations, resolved against its files.

    ``rules`` and ``entry`` are collection-relative paths of files that exist
    (``rules`` may climb into another collection, ``../shared/rules.md``), empty
    when there is none; ``uploads`` is always a folder inside the collection.
    """

    rules: str = ""
    entry: str = ""
    uploads: str = DEFAULT_UPLOADS


def _readme_frontmatter(directory: pathlib.Path) -> dict[str, Any]:
    readme = directory / README_NAME
    if not readme.is_file():
        return {}
    try:
        text = readme.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return {}
    fm, _ = split_frontmatter(text.replace("\r\n", "\n"))
    return fm


def _declared(fm: dict[str, Any], key: str) -> str:
    value = fm.get(key)
    return value.strip() if isinstance(value, str) else ""


def _inside(base: pathlib.Path, relpath: str, *, bound: pathlib.Path) -> str:
    """``relpath`` as a normalised path relative to ``base`` when it names a
    file under ``bound`` that is not hidden; empty otherwise."""
    if not relpath or "\x00" in relpath or relpath.startswith("/"):
        return ""
    joined = posixpath.normpath(posixpath.join(base.as_posix(), relpath))
    candidate = pathlib.Path(joined)
    try:
        inner = candidate.relative_to(bound)
    except ValueError:
        return ""
    if any(part.startswith(".") for part in inner.parts) or not candidate.is_file():
        return ""
    return posixpath.relpath(joined, base.as_posix())


#: What a declared uploads folder's segment may not hold: the same characters
#: a knowledge path refuses (``paths.check_segment``).
_UNSAFE = re.compile(r"[\\\x00-\x1f\x7f]")


def _uploads(value: str) -> str:
    """The declared uploads folder when it is a plain folder inside the
    collection, else the default."""
    text = value.strip()
    if text.startswith("/"):
        return DEFAULT_UPLOADS
    parts = [p for p in text.strip("/").split("/") if p]
    if not parts or any(p.startswith(".") or _UNSAFE.search(p) for p in parts):
        return DEFAULT_UPLOADS
    if parts == [README_NAME]:
        return DEFAULT_UPLOADS
    return "/".join(parts)


def read(directory: pathlib.Path, *, bound: pathlib.Path | None = None) -> Settings:
    """The declarations of the collection at ``directory``.

    ``bound`` is how far a declared path may reach: the knowledge root for a
    collection Coffer keeps (so a shared rules file in another collection
    resolves), the folder itself for a linked one. A declared file that is
    missing, hidden or out of bounds is ignored, and the rules file falls back
    to the files a collection's rules are found in by default.
    """
    limit = bound if bound is not None else directory
    fm = _readme_frontmatter(directory)
    rules = _inside(directory, _declared(fm, RULES_KEY), bound=limit)
    if not rules:
        rules = next((name for name in RULES_FILES if (directory / name).is_file()), "")
    entry = _inside(directory, _declared(fm, ENTRY_KEY), bound=limit)
    uploads = _uploads(_declared(fm, UPLOADS_KEY))
    if (directory / uploads).exists() and not (directory / uploads).is_dir():
        uploads = DEFAULT_UPLOADS
    return Settings(rules=rules, entry=entry, uploads=uploads)


def description(directory: pathlib.Path) -> str:
    """A collection's one-line description: its README's first paragraph,
    before its first section (``##``); empty when it has none."""
    readme = directory / README_NAME
    if not readme.is_file():
        return ""
    _, body = split_frontmatter(readme.read_text(encoding="utf-8", errors="replace"))
    paragraph: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("##"):
            break
        if stripped.startswith("#"):
            continue
        if not stripped:
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    return " ".join(paragraph)


def title_of(fm: dict[str, Any], body: str, stem: str) -> str:
    """A file's title: its frontmatter ``title``, else its first ``#``
    heading, else its file name without ``.md``."""
    title = fm.get("title")
    if isinstance(title, str | int | float) and str(title).strip():
        return str(title).strip()
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or stem
    return stem


def head_title(path: pathlib.Path) -> tuple[str, str]:
    """``(title, description)`` of a Markdown file, read from its head only."""
    try:
        with path.open("rb") as handle:
            head = handle.read(_HEAD_BYTES).decode("utf-8", errors="replace")
    except OSError:
        return path.stem, ""
    fm, body = split_frontmatter(head.replace("\r\n", "\n"))
    described = fm.get("description")
    text = " ".join(str(described).split()) if isinstance(described, str | int | float) else ""
    return title_of(fm, body, path.stem), text


__all__ = [
    "DEFAULT_UPLOADS",
    "ENTRY_KEY",
    "README_NAME",
    "RULES_FILES",
    "RULES_KEY",
    "UPLOADS_KEY",
    "Settings",
    "description",
    "head_title",
    "read",
    "title_of",
]
