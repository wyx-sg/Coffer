"""Render / detect / remove Coffer's session-context block in an instructions file.

Pure domain text transforms — no filesystem access — mirroring
``hook_install.py``. This is the ``INSTRUCTIONS_BLOCK`` injection mode
(ADR-042): for an agent with no working hook at all (Hermes — its
``on_session_start`` / ``pre_llm_call`` hooks are documented but never invoked
upstream, NousResearch/hermes-agent#2817), Coffer renders the same FR-044
session-context payload into a marker-fenced block in the agent's instructions
file (hermes: ``~/.hermes/SOUL.md`` — the only instruction file hermes reads
from its home dir; its ``AGENTS.md`` resolution is cwd-only), replacing it in
place on every refresh.

Coffer recognises *its own* block by the marker pair below, in order. Content
outside the markers is never touched. A lone, unbalanced marker (user damage to
one fence) is treated as "no Coffer block": install appends a fresh balanced
block rather than guessing where the damaged one ends — the safe failure is a
stray comment line, never eaten user content.
"""

from __future__ import annotations

BLOCK_START = "<!-- coffer:session-context:start -->"
BLOCK_END = "<!-- coffer:session-context:end -->"

#: First line inside the block, warning off hand edits (they are overwritten on
#: the next refresh).
_BLOCK_NOTE = "<!-- Managed by Coffer; refreshed automatically. Do not edit. -->"


def _find_block(content: str) -> tuple[int, int] | None:
    """The ``(start, end)`` span of Coffer's block including both marker lines,
    or ``None`` when no balanced block exists."""
    start = content.find(BLOCK_START)
    if start == -1:
        return None
    end = content.find(BLOCK_END, start + len(BLOCK_START))
    if end == -1:
        return None
    return start, end + len(BLOCK_END)


def _render(payload: str) -> str:
    return f"{BLOCK_START}\n{_BLOCK_NOTE}\n\n{payload.strip()}\n{BLOCK_END}"


def apply_block(content: str, *, payload: str) -> str:
    """Return new instructions text carrying Coffer's block with ``payload``.

    Idempotent: an existing balanced block is replaced in place (its position
    among the user's own sections is preserved); otherwise the block is appended
    after the existing content, separated by one blank line.
    """
    block = _render(payload)
    span = _find_block(content)
    if span is not None:
        start, end = span
        return content[:start] + block + content[end:]
    if not content.strip():
        return block + "\n"
    return content.rstrip("\n") + "\n\n" + block + "\n"


def remove_block(content: str) -> str:
    """Return new instructions text with ONLY Coffer's block removed.

    A true inverse of :func:`apply_block`: the separating blank line the append
    added is dropped with the block, and a file whose only content was the block
    becomes empty. User content is byte-identical either side of the block.
    """
    span = _find_block(content)
    if span is None:
        return content
    start, end = span
    before, after = content[:start], content[end:]
    # Drop the blank separator apply_block added and the block's own trailing
    # newline; keep exactly the user's original boundary.
    before = before.rstrip("\n")
    after = after.lstrip("\n")
    if not before:
        return after
    if not after:
        return before + "\n"
    return before + "\n\n" + after


def has_block(content: str) -> bool:
    """Whether Coffer's balanced session-context block is present."""
    return _find_block(content) is not None
