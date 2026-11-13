"""Reads Claude Code's per-project memory: one Markdown file per entry.

Each entry lives at `<config_dir>/projects/<slug>/memory/<name>.md`, frontmatter
first:

    ---
    name: feedback-worktree-development
    description: Always develop in a git worktree...
    metadata:
      node_type: memory
      type: feedback
      originSessionId: ...
    ---

    <body>

`name` and `description` are the source's own title and description;
`metadata.type` picks the entry's type (an unknown or empty type is read as
`project`). `MEMORY.md` in the same directory is Claude Code's own index, and
holds Coffer's block, so it is never read as a memory (spec memory "Never
republish Coffer's own copies").

An entry's `project_root` is recovered the way the agent page's native-memory
listing recovers it (`infrastructure.agent.native_memory_store`): a sibling
session transcript's own recorded `cwd`
(`infrastructure.agent_files.claude_code_transcripts.cwd_from_transcripts`)
first, and `domain.agent.native_memory.resolve_project_slug`'s slug decode
only when no transcript recorded one.
"""

from __future__ import annotations

import hashlib
import pathlib
from typing import Any

import yaml

from coffer.domain.agent.native_memory import encode_slug, resolve_project_slug
from coffer.domain.memory.errors import UnreadableMemory
from coffer.domain.memory.hub import TYPE_FEEDBACK, TYPE_PROJECT, TYPE_USER
from coffer.domain.memory.reader import RawEntry, SourceFile
from coffer.infrastructure.agent_files.claude_code_transcripts import cwd_from_transcripts

_INDEX_NAME = "MEMORY.md"
_FENCE = "---"

# Claude Code's own `metadata.type` values. An empty type, or a value this
# reader has not seen, falls to TYPE_PROJECT: the user and feedback types are
# narrower claims about the person that an unrecognised type has not earned.
_TYPE_MAP = {
    "feedback": TYPE_FEEDBACK,
    "project": TYPE_PROJECT,
    "user": TYPE_USER,
}
_REFERENCE = "reference"


class ClaudeCodeMemoryReader:
    """`MemoryReader` for Claude Code's per-entry Markdown files."""

    agent_type = "claude_code"

    def __init__(self) -> None:
        # A project's real directory, per project directory, for one pass: every
        # fact file of a project asks the same question, and answering it scans
        # that project's session transcripts. Cleared when a pass lists its sources.
        self._roots: dict[pathlib.Path, str | None] = {}

    def sources(self, config_dir: str) -> tuple[SourceFile, ...]:
        self._roots.clear()
        projects_dir = pathlib.Path(config_dir) / "projects"
        if not projects_dir.is_dir():
            return ()
        out: list[SourceFile] = []
        for project_dir in sorted(_iterdir(projects_dir)):
            memory_dir = project_dir / "memory"
            if not memory_dir.is_dir():
                continue
            for file in sorted(memory_dir.glob("*.md")):
                if file.name == _INDEX_NAME:
                    continue
                try:
                    digest = _digest(file)
                except OSError:
                    # One unreadable file (permissions, a race with deletion)
                    # must not stop the rest of this agent's files listing
                    # ("Fail a broken reader loudly and in isolation" applies
                    # here too).
                    continue
                out.append(SourceFile(path=str(file), digest=digest))
        return tuple(out)

    def read(self, source: SourceFile) -> tuple[RawEntry, ...]:
        path = pathlib.Path(source.path)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise UnreadableMemory(source.path, str(exc)) from exc

        frontmatter, body = _split_frontmatter(text, source.path)
        # ``metadata:`` with nothing under it loads as ``None``, not ``{}``.
        metadata = frontmatter.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise UnreadableMemory(source.path, "frontmatter 'metadata' is not a mapping")
        raw_type = str(metadata.get("type", "") or "").strip().lower()
        name = frontmatter.get("name")
        if not name or not isinstance(name, str):
            raise UnreadableMemory(source.path, "frontmatter is missing a string 'name'")
        description = frontmatter.get("description", "")
        if not isinstance(description, str):
            description = str(description)

        entry_type = _REFERENCE if raw_type == _REFERENCE else _TYPE_MAP.get(raw_type, TYPE_PROJECT)
        project_dir = path.parent.parent
        project_root = self._project_root(project_dir)
        return (
            RawEntry(
                title=name,
                description=description,
                type=entry_type,
                body=body.strip("\n"),
                anchor=name,
                project_root=project_root or "",
            ),
        )

    def _project_root(self, project_dir: pathlib.Path) -> str | None:
        """The directory a project slug names: the ``cwd`` its own session
        transcripts recorded when one matches, else the slug decoded against the
        filesystem. Asked once per project per pass."""
        if project_dir in self._roots:
            return self._roots[project_dir]
        root = cwd_from_transcripts(project_dir, encode_slug)
        if root is None:
            _, root = resolve_project_slug(project_dir.name, _list_dirs)
        self._roots[project_dir] = root
        return root


def _digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iterdir(path: pathlib.Path) -> list[pathlib.Path]:
    try:
        return [p for p in path.iterdir() if p.is_dir()]
    except OSError:
        return []


def _list_dirs(path: str) -> list[str]:
    """The FS adapter `resolve_project_slug` walks against."""
    try:
        return [entry.name for entry in pathlib.Path(path).iterdir() if entry.is_dir()]
    except OSError:
        return []


def _split_frontmatter(text: str, path: str) -> tuple[dict[str, Any], str]:
    """Split the leading `---`-fenced YAML block from the body, or raise.

    Unlike `infrastructure.knowledge.frontmatter.split_frontmatter` — which
    tolerates a malformed fence by degrading to `({}, text)` — a memory file
    with no readable frontmatter has lost its type, its title and half its
    identity, so "Fail a broken reader loudly and in isolation" wants this loud
    rather than silently empty.
    """
    if not text.startswith(_FENCE):
        raise UnreadableMemory(path, "no YAML frontmatter fence")
    lines = text.split("\n")
    close_at = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FENCE:
            close_at = i
            break
    if close_at is None:
        raise UnreadableMemory(path, "unterminated YAML frontmatter fence")
    raw_yaml = "\n".join(lines[1:close_at])
    body = "\n".join(lines[close_at + 1 :])
    try:
        loaded = yaml.safe_load(raw_yaml) if raw_yaml.strip() else {}
    except yaml.YAMLError as exc:
        raise UnreadableMemory(path, f"malformed YAML frontmatter: {exc}") from exc
    if not isinstance(loaded, dict):
        raise UnreadableMemory(path, "frontmatter is not a YAML mapping")
    return loaded, body
