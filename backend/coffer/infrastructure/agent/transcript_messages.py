"""Turning a transcript's records into the turns one session's page renders.

The counterpart to :mod:`transcript_parsers`: same files, same record
recognisers (:mod:`transcript_records`), but the text kept instead of counted.
That inversion is the whole module, and it is why it is small — the formats are
already understood one layer down, so all that is left here is the one thing a
body needs and a summary does not: making the text safe to leave the machine.

Safe means two cuts, both applied where the value is constructed rather than
anywhere downstream. Secrets are scrubbed, because a prompt is exactly the kind
of text someone pastes an API key into and this is the first surface that shows
prompts at all. And a turn longer than ``MAX_MESSAGE_CHARS`` is cut to its
start and says so, because one pasted log can be a large fraction of a
multi-megabyte file and a page must not become that file.

Read-only, like everything else over an agent's own transcripts: nothing here
writes.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from coffer.domain.agent.transcripts import (
    MAX_MESSAGE_CHARS,
    TranscriptMessage,
    scrub_secrets,
)
from coffer.infrastructure.agent.transcript_records import (
    claude_turn,
    codex_turn,
    iter_json_records,
    parse_iso,
)


def _message(role: str, text: str, timestamp_raw: object) -> TranscriptMessage:
    """Build one turn, scrubbed and capped before the value exists.

    The scrub runs on the WHOLE turn and the cut runs after it, in that order.
    Reversed, a secret straddling the cap would be split in half — and half a
    key, past a redactor that no longer recognises the shape, is exactly the
    leak the scrubbing exists to prevent.
    """
    scrubbed = scrub_secrets(text)
    truncated = len(scrubbed) > MAX_MESSAGE_CHARS
    return TranscriptMessage(
        role=role,
        text=scrubbed[:MAX_MESSAGE_CHARS] if truncated else scrubbed,
        timestamp=parse_iso(timestamp_raw) if isinstance(timestamp_raw, str) else None,
        truncated=truncated,
    )


def iter_claude_code_messages(
    lines: Iterable[str], *, source_path: str
) -> Iterator[TranscriptMessage]:
    """Yield each conversational turn of a Claude Code transcript, in file order.

    A generator rather than a list: the caller wants a window, and a window
    taken from a generator stops reading the file once it is full.
    """
    for record in iter_json_records(lines, source_path=source_path, label="claude_code messages"):
        turn = claude_turn(record)
        if turn is None:
            continue
        role, text = turn
        yield _message(role, text, record.get("timestamp"))


def iter_codex_messages(lines: Iterable[str], *, source_path: str) -> Iterator[TranscriptMessage]:
    """Yield each conversational turn of a Codex rollout, in file order."""
    for record in iter_json_records(lines, source_path=source_path, label="codex messages"):
        turn = codex_turn(record)
        if turn is None:
            continue
        role, text = turn
        yield _message(role, text, record.get("timestamp"))


__all__ = ["iter_claude_code_messages", "iter_codex_messages"]
