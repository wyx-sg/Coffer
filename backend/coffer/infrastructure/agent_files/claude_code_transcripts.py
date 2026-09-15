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


def cwd_from_transcripts(project_dir: pathlib.Path) -> str | None:
    """First ``"cwd"`` string found in the first readable sibling ``*.jsonl``.

    Returns ``None`` when ``project_dir`` is not a directory, holds no
    ``*.jsonl`` transcript, or that transcript's lines never mention a
    string ``"cwd"`` field — never raises, since a missing or malformed
    transcript is not a reason to fail the caller's own lookup.
    """
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


__all__ = ["cwd_from_transcripts"]
