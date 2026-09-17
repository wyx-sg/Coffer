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

`name` and `description` are the source's own title and description — no
derivation needed, unlike Codex's untitled bullets. `metadata.type` picks the
entry's type; `metadata.type: reference` is skipped rather than mapped, because
Claude Code's own `reference` memories are knowledge the user or the agent
wrote down about the world, not something the agent learned while working —
exactly the boundary spec memory's "Memory is not knowledge" section draws.
`MEMORY.md` in the same directory is Claude Code's own regenerated index and
is ignored for the same reason knowledge ignores `README.md`: Coffer
regenerates that role itself (FR-004).

What comes back is a `RawEntry`, and a raw entry is **the input layer, not
the product** (FR-008): it is written verbatim under the partition's `.raw/`,
and the distil pass is what turns entries into Coffer's own notes (FR-020).
So this reader is not trying to produce anything a person will read, even
though Claude Code hands it a perfectly good title — it carries the source's
words across intact and leaves the writing to the pass. The verbatim rule
that used to govern what Coffer *stored* now governs only this layer, which
is what keeps a note's claim checkable back against the agent's own file.

Claude Code states no search terms anywhere in this format — it relies on its
own always-loaded index instead — so `RawEntry.search_terms` stays empty
here. FR-004 asks a reader to carry terms **where the source states them**;
synthesising them from the body would be precisely the guess that requirement
exists to replace. Codex is the source that states them, and
`readers.codex` is where they are carried.

An entry's `project_root` is recovered the same way the agent page's
native-memory listing recovers it (`infrastructure.agent.native_memory_store`):
preferring a sibling session transcript's own recorded `cwd`
(`infrastructure.agent_files.claude_code_transcripts.cwd_from_transcripts`) —
authoritative, no decoding involved — and falling back to
`domain.agent.native_memory.resolve_project_slug`'s filesystem-aware slug
decode only when no transcript recorded one (e.g. every transcript for this
project has since been pruned). One parser, one slug-decoder, shared by both
callers.
"""

from __future__ import annotations

import hashlib
import pathlib
from typing import Any

import yaml

from coffer.domain.agent.native_memory import resolve_project_slug
from coffer.domain.memory.errors import UnreadableMemory
from coffer.domain.memory.note import TYPE_FEEDBACK, TYPE_PROJECT, TYPE_USER
from coffer.domain.memory.reader import RawEntry, SourceFile
from coffer.infrastructure.agent_files.claude_code_transcripts import cwd_from_transcripts

_INDEX_NAME = "MEMORY.md"
_FENCE = "---"

# Claude Code's own `metadata.type` values, mapped onto NOTE_TYPES. Anything
# else recognised as *not* `reference` (an empty type, or a future value this
# reader has not seen) falls to TYPE_PROJECT: note.py describes TYPE_PROJECT
# as "a decision, a trap, a piece of history" for one project, which is the
# closest general bucket for a note this reader cannot otherwise place —
# TYPE_USER/TYPE_FEEDBACK are narrower claims (about the person specifically)
# that an unrecognised type has not earned.
_TYPE_MAP = {
    "feedback": TYPE_FEEDBACK,
    "project": TYPE_PROJECT,
    "user": TYPE_USER,
}
_SKIP_TYPE = "reference"


class ClaudeCodeMemoryReader:
    """`MemoryReader` for Claude Code's per-entry Markdown files."""

    agent_type = "claude_code"

    def sources(self, config_dir: str) -> tuple[SourceFile, ...]:
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
                    # (FR-005's isolation applies here too).
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
        if raw_type == _SKIP_TYPE:
            return ()

        name = frontmatter.get("name")
        if not name or not isinstance(name, str):
            raise UnreadableMemory(source.path, "frontmatter is missing a string 'name'")
        description = frontmatter.get("description", "")
        if not isinstance(description, str):
            description = str(description)

        entry_type = _TYPE_MAP.get(raw_type, TYPE_PROJECT)
        project_dir = path.parent.parent
        project_root = cwd_from_transcripts(project_dir)
        if project_root is None:
            _, project_root = resolve_project_slug(project_dir.name, _list_dirs)
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
    identity, so FR-005 wants this loud rather than silently empty.
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
