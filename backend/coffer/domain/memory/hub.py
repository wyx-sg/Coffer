"""The memory hub's vocabulary (spec memory "Keep memory in one place in the
vault"; ADR keep-memory-in-one-place-agents-write-themselves).

Memory is files. ``vault/memory/projects/<project>/`` holds one Markdown file
per **topic**: memories that belong together and are used together, one per
line, under a frontmatter of ``title``, ``type`` and ``updated``. Agents read
and write these files with their own file tools by the rules the coffer-guide
skill states; Coffer writes none of them except when the person edits one on
the Memory page. Everything here is a plain value or a pure function.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from coffer.domain.memory.errors import UnsafeMemoryPath
from coffer.domain.memory.repository import normalise_remote

#: The folder holding one subfolder per project.
PROJECTS = "projects"

#: What a topic is about: the person, how to work with them, a project's state.
TYPE_USER = "user"
TYPE_FEEDBACK = "feedback"
TYPE_PROJECT = "project"
TYPES = (TYPE_USER, TYPE_FEEDBACK, TYPE_PROJECT)

#: The longest line a topic keeps: a memory is a sentence or two.
MAX_LINE = 400

_UNSAFE_FOLDER_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_DOTS_ONLY = re.compile(r"^\.+$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class Topic:
    """One memory file as the page and the session-start hook read it."""

    #: The project folder under ``projects/``.
    project: str
    #: The file name, ``.md`` included.
    name: str
    title: str
    type: str
    #: ``YYYY-MM-DD``, or ``""`` when the file names none.
    updated: str
    body: str
    #: What breaks the format, in plain words; empty when the file follows it.
    problems: tuple[str, ...] = ()

    @property
    def path(self) -> str:
        """The hub-relative path of this file."""
        return f"{PROJECTS}/{self.project}/{self.name}"


def read_topic(project: str, name: str, frontmatter: dict[str, object], body: str) -> Topic:
    """A topic from its parsed file, with what breaks the format named.

    Lenient: a file that breaks the format is still read and shown — the
    page flags it and a tidy fixes it — so nothing an agent wrote is lost
    because one field is missing.
    """
    title = str(frontmatter.get("title") or "").strip()
    kind = str(frontmatter.get("type") or "").strip()
    updated = _date(frontmatter.get("updated"))
    text = body.strip("\n")
    problems: list[str] = []
    if not title:
        problems.append("no title")
    if kind not in TYPES:
        problems.append("type is not user, feedback or project")
    if not updated:
        problems.append("no updated date")
    if not text.strip():
        problems.append("no memories")
    elif any(len(line) > MAX_LINE for line in text.splitlines()):
        problems.append(f"a line longer than {MAX_LINE} characters")
    return Topic(
        project=project,
        name=name,
        title=title or name.removesuffix(".md"),
        type=kind if kind in TYPES else "",
        updated=updated,
        body=text,
        problems=tuple(problems),
    )


def _date(value: object) -> str:
    text = str(value or "").strip()
    match = _DATE.match(text)
    return match.group(0) if match else ""


def hub_project_key(*, remote_url: str, root_name: str) -> str:
    """The key a repository's memories are filed under.

    The normalised ``origin`` URL when there is one, so two clones on two
    machines agree; the repository directory's own name otherwise, because a
    path is not portable. ``""`` when neither is usable.
    """
    remote = normalise_remote(remote_url)
    if remote:
        return remote
    return (root_name or "").strip().strip("/").rsplit("/", 1)[-1]


def project_folder(key: str) -> str:
    """The folder of the project ``key``: every character outside
    ``[A-Za-z0-9._-]`` becomes ``-`` (``github.com/acme/payments`` →
    ``github.com-acme-payments``)."""
    folder = _UNSAFE_FOLDER_CHARS.sub("-", key).strip("-")
    return check_segment(folder)


def check_segment(segment: str) -> str:
    """Refuse a path segment that is empty, all dots, hidden or unsafe."""
    if not segment:
        raise UnsafeMemoryPath(segment, "empty path segment")
    if _DOTS_ONLY.fullmatch(segment):
        raise UnsafeMemoryPath(segment, "traversal segment")
    if segment.startswith("."):
        raise UnsafeMemoryPath(segment, "hidden entries are not addressable")
    if "/" in segment or "\\" in segment or "\0" in segment:
        raise UnsafeMemoryPath(segment, "path separator")
    return segment


def check_file_name(name: str) -> str:
    """A memory file's name: a safe segment ending in ``.md``."""
    check_segment(name)
    if not name.endswith(".md"):
        raise UnsafeMemoryPath(name, "not a Markdown file")
    return name


__all__ = [
    "MAX_LINE",
    "PROJECTS",
    "TYPES",
    "TYPE_FEEDBACK",
    "TYPE_PROJECT",
    "TYPE_USER",
    "Topic",
    "check_file_name",
    "check_segment",
    "hub_project_key",
    "project_folder",
    "read_topic",
]
