"""Recovers a Claude Code project's real working directory from its own
session transcripts.

Claude Code's per-project slug encodes the project's absolute path lossily
(``coffer.domain.agent.native_memory.resolve_project_slug`` decodes it
best-effort from the filesystem). When a project has since been renamed,
moved, or deleted, neither that walk nor the naive dash-split fallback can
recover the truth any more — but Claude Code's own session transcripts
(``<slug>/*.jsonl``, sitting right next to the ``memory/`` directory the slug
names) record the literal ``cwd`` each session ran with, and that recorded
value is authoritative: no decoding, no ambiguity, no probing the disk for a
plausible match.

Both the agent page's native-memory listing
(``infrastructure.agent.native_memory_store``) and memory aggregation's
Claude Code reader (``infrastructure.memory.readers.claude_code``) read a
project's transcripts through this one function, so the format is parsed in
exactly one place — which is why it lives in the kind-agnostic
``infrastructure.agent_files`` package rather than under either caller's
kind. Read-only: nothing here writes anything.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Callable


def cwd_from_transcripts(
    project_dir: pathlib.Path, encode_slug: Callable[[str], str]
) -> str | None:
    """The recorded ``"cwd"`` that IS this project, from its sibling ``*.jsonl``.

    A transcript's first ``cwd`` is not the project's: a desktop session
    starts in a scratch workspace and only then moves into the project, and
    its transcript is filed under the project it ended up in. So a ``cwd``
    counts only when Claude Code's own encoding of it (``encode_slug``,
    passed in by the caller, which owns the slug format) is exactly
    ``project_dir``'s name — the slug says which path it is, the transcript
    says how that path is really spelled. Every transcript is tried, line by
    line, until one matches.

    Returns ``None`` when ``project_dir`` is not a directory or no transcript
    records a matching ``cwd`` — never raises, since a missing or malformed
    transcript is not a reason to fail the caller's own lookup.
    """
    if not project_dir.is_dir():
        return None
    slug = project_dir.name
    for jsonl in sorted(project_dir.glob("*.jsonl")):
        try:
            with jsonl.open(encoding="utf-8", errors="replace") as lines:
                for line in lines:
                    if '"cwd"' not in line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    cwd = record.get("cwd") if isinstance(record, dict) else None
                    if isinstance(cwd, str) and encode_slug(cwd) == slug:
                        return cwd
        except OSError:
            continue
    return None


__all__ = ["cwd_from_transcripts"]
