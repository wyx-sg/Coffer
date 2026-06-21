"""Read + resolve helpers for ADOPTING an agent's native per-project memory.

The read-side counterpart to ``native_memory_store.py`` (which only lists). These
pure functions parse a Claude Code ``<config_dir>/projects/<slug>/memory/`` dir
into ``ParsedNativeFact`` rows and recover the REAL project path for that store.

No memory-kind imports live here (the import boundary fences ``infrastructure.agent``
off ``infrastructure.memory``): the only shared dependency is the frontmatter
splitter under ``infrastructure.knowledge``, which is kind-agnostic substrate.
"""

from __future__ import annotations

import json
import pathlib

from coffer.domain.agent.native_memory import ParsedNativeFact, decode_project_slug
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter

_INDEX_FILE = "MEMORY.md"


def read_memory_facts(memory_dir: pathlib.Path) -> list[ParsedNativeFact]:
    """Parse every ``*.md`` in ``memory_dir`` except the ``MEMORY.md`` index.

    Defensive: a single unparseable file never raises — the frontmatter splitter
    degrades a malformed block to ``({}, body)`` and the missing keys fall back
    (``name`` → filename stem, ``description`` → ``""``, ``type``/``originSessionId``
    → ``None``). A missing dir yields ``[]``.
    """
    if not memory_dir.is_dir():
        return []
    out: list[ParsedNativeFact] = []
    for md in sorted(memory_dir.glob("*.md")):
        if not md.is_file() or md.name == _INDEX_FILE:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = split_frontmatter(text)
        out.append(
            ParsedNativeFact(
                name=_as_str(meta.get("name")) or md.stem,
                description=_as_str(meta.get("description")) or "",
                body=body,
                type=_as_str(meta.get("type")) or None,
                origin_session_id=_as_str(meta.get("originSessionId")) or None,
            )
        )
    return out


def resolve_project_path(memory_dir: pathlib.Path) -> str | None:
    """Recover the REAL absolute project path that ``memory_dir`` belongs to.

    Two-step resolution:
      1. Decode the parent dir name (the slug). If the decoded path is an
         existing directory, use it.
      2. Else scan the first readable sibling ``*.jsonl`` transcript (one JSON
         object per line; bad lines skipped) for a record carrying a string
         ``"cwd"`` and use that.
    Returns ``None`` when neither resolves.
    """
    project_dir = memory_dir.parent
    _, decoded = decode_project_slug(project_dir.name)
    if decoded is not None and pathlib.Path(decoded).is_dir():
        return decoded
    return _cwd_from_transcripts(project_dir)


def _cwd_from_transcripts(project_dir: pathlib.Path) -> str | None:
    """First ``"cwd"`` string found in the first readable sibling ``*.jsonl``."""
    if not project_dir.is_dir():
        return None
    for jsonl in sorted(project_dir.glob("*.jsonl")):
        try:
            text = jsonl.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                cwd = record.get("cwd")
                if isinstance(cwd, str):
                    return cwd
        # First readable transcript only (per the contract): stop after it.
        return None
    return None


def _as_str(value: object) -> str | None:
    """Coerce a frontmatter scalar to ``str`` (YAML may load ints/None)."""
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


__all__ = ["ParsedNativeFact", "read_memory_facts", "resolve_project_path"]
