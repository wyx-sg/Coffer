"""Recovers the working directory a Codex v2 memory topic was learned in.

Codex's v2 memory (``~/.codex/memories_v2/``) files each piece of work under a
project scope it names in words ("Account Jira delivery"), and points at one
``rollout_summaries/<file>.md`` per session. That file opens with a short
header (``thread_id``, ``updated_at``, ``rollout_path``, ``cwd``), and the
``cwd`` there is the only place the session's directory is recorded.

Both the agent page's native-memory listing
(``infrastructure.agent.codex_memory_store``) and memory aggregation (the Codex
reader and the checkout map in ``infrastructure.memory``) read it through this
one function, which reads the header and stops: the session's account below it
is history, which nothing in Coffer reads. It lives in the kind-agnostic
``infrastructure.agent_files`` package for the same reason as
``claude_code_transcripts``. Read-only.
"""

from __future__ import annotations

import pathlib
import re

ROLLOUT_SUMMARIES = "rollout_summaries"
#: How many lines of a rollout summary's head hold its header.
HEADER_LINES = 8
_CWD_RE = re.compile(r"^cwd:[ \t]*(?P<cwd>\S.*?)\s*$")


def header_cwd(head: str) -> str:
    """The ``cwd:`` of a rollout summary's header, or ``""``; the header ends
    at the first blank line."""
    for line in head.splitlines()[:HEADER_LINES]:
        match = _CWD_RE.match(line)
        if match is not None:
            return match.group("cwd")
        if not line.strip():
            break
    return ""


def rollout_cwd(folder: pathlib.Path, file_name: str) -> str:
    """The ``cwd:`` in the header of ``folder/rollout_summaries/<file_name>``,
    or ``""``. A name that is not a plain file name gives ``""``."""
    if not file_name or "/" in file_name or "\\" in file_name or file_name.startswith("."):
        return ""
    try:
        with (folder / ROLLOUT_SUMMARIES / file_name).open(encoding="utf-8") as fh:
            head = "".join(fh.readline() for _ in range(HEADER_LINES))
    except (OSError, UnicodeDecodeError):
        return ""
    return header_cwd(head)


def all_rollout_cwds(folder: pathlib.Path) -> list[str]:
    """The ``cwd:`` of every rollout summary in ``folder``, in file-name order."""
    try:
        names = sorted(p.name for p in (folder / ROLLOUT_SUMMARIES).glob("*.md"))
    except OSError:
        return []
    return [cwd for cwd in (rollout_cwd(folder, n) for n in names) if cwd]


__all__ = ["HEADER_LINES", "ROLLOUT_SUMMARIES", "all_rollout_cwds", "header_cwd", "rollout_cwd"]
