"""The memory hub's vocabulary: one entry per memory an agent wrote itself
(spec memory "Keep every agent's memories in a hub in the vault").

The hub is a transport, not a curated store: every memory a registered agent
on any of the person's machines wrote for itself is one Markdown file under
``vault/memory/``, filed under ``global`` or under a project named by a key
that does not depend on the machine ("Identify a project by a key that does
not depend on the machine"). Each machine writes the hub into the agents
installed on it; the agents curate what they receive with their own built-in
curation.

Everything here is a plain value or a pure function. Rendering an entry as a
file and reading one back is :mod:`coffer.infrastructure.memory.hub_store`'s.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace

from coffer.domain.memory.errors import UnsafeMemoryPath
from coffer.domain.memory.repository import normalise_remote

#: The folder of memories about the person, written into every machine.
GLOBAL = "global"
#: The folder holding one subfolder per project.
PROJECTS = "projects"

#: The memory types a hub entry carries. Claude Code's four; Codex's
#: sections map onto ``user`` and ``project``.
TYPE_USER = "user"
TYPE_FEEDBACK = "feedback"
TYPE_PROJECT = "project"
TYPE_REFERENCE = "reference"
HUB_TYPES = frozenset({TYPE_USER, TYPE_FEEDBACK, TYPE_PROJECT, TYPE_REFERENCE})

#: The agent types the hub knows a reader and a writer for.
CLAUDE_CODE = "claude_code"
CODEX = "codex"
AGENT_LABELS = {CLAUDE_CODE: "Claude Code", CODEX: "Codex"}

_UNSAFE_FOLDER_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_SLUG_CHARS = re.compile(r"[^a-z0-9]+")
_DOTS_ONLY = re.compile(r"^\.+$")
_ID = re.compile(r"^[0-9a-f]{16}$")
#: A title slug's longest form; a file name stays readable in a listing.
SLUG_MAX = 48


@dataclass(frozen=True)
class Origin:
    """Where a hub entry came from: the only machine and agent that may change
    or delete it ("Publish only what the origin agent wrote, and only from its
    machine")."""

    machine: str
    agent: str
    #: The source's own identity on that machine: a Claude Code topic file's
    #: path under its config directory, or a Codex file plus bullet anchor.
    source: str


@dataclass(frozen=True)
class HubEntry:
    """One memory, as the hub holds it.

    ``body`` is stored portable ("Store paths in a memory portably"): the
    repository root it was learned in is ``<repo>`` and the home directory
    ``~``.
    """

    id: str
    origin: Origin
    #: The project key (``github.com/acme/payments``), or ``""`` for global.
    project: str
    type: str
    title: str
    description: str
    body: str
    created_at: str
    updated_at: str
    search_terms: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_global(self) -> bool:
        return not self.project

    @property
    def folder(self) -> str:
        """The hub-relative folder this entry is filed under."""
        return GLOBAL if self.is_global else f"{PROJECTS}/{project_folder(self.project)}"

    @property
    def path(self) -> str:
        """The hub-relative path of this entry's file."""
        return f"{self.folder}/{check_id(self.id)}.md"

    def same_content(self, other: HubEntry) -> bool:
        """Whether ``other`` says the same thing, ignoring the timestamps."""
        return replace(self, created_at="", updated_at="") == replace(
            other, created_at="", updated_at=""
        )


def entry_id(machine: str, agent_type: str, source_identity: str) -> str:
    """The stable id of the memory ``source_identity`` names.

    A re-read of an unchanged source maps to the same id, so an edit is an
    update, not a new entry; the machine and agent are part of it so two
    machines never mint one id.
    """
    raw = "\0".join((machine, agent_type, source_identity)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def check_id(value: str) -> str:
    """``value`` when it is a hub entry id, else ``UnsafeMemoryPath``: an id
    read back from a hub file becomes a file name."""
    if not _ID.fullmatch(value or ""):
        raise UnsafeMemoryPath(value, "not a memory id")
    return value


def hub_project_key(*, remote_url: str, root_name: str) -> str:
    """The key a repository's memories are filed under in the hub.

    The normalised ``origin`` URL when there is one, so two clones on two
    machines agree; the repository directory's own name otherwise, because a
    path is not portable. ``""`` when neither is usable.
    """
    remote = normalise_remote(remote_url)
    if remote:
        return remote
    return (root_name or "").strip().strip("/").rsplit("/", 1)[-1]


def project_folder(key: str) -> str:
    """The hub folder of the project ``key``: every character outside
    ``[A-Za-z0-9._-]`` becomes ``-`` (``github.com/acme/payments`` →
    ``github.com-acme-payments``). The key itself is in each entry, so the
    folder name never has to be decoded."""
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


def title_slug(title: str) -> str:
    """A short file-name slug from a title (``coffer_<slug>.md``)."""
    slug = _SLUG_CHARS.sub("-", title.lower()).strip("-")[:SLUG_MAX].strip("-")
    return slug or "memory"


def one_line(text: str, limit: int = 200) -> str:
    """``text`` on one line, cut to ``limit`` characters."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


__all__ = [
    "AGENT_LABELS",
    "CLAUDE_CODE",
    "CODEX",
    "GLOBAL",
    "HUB_TYPES",
    "PROJECTS",
    "TYPE_FEEDBACK",
    "TYPE_PROJECT",
    "TYPE_REFERENCE",
    "TYPE_USER",
    "HubEntry",
    "Origin",
    "check_id",
    "check_segment",
    "entry_id",
    "hub_project_key",
    "one_line",
    "project_folder",
    "title_slug",
]
