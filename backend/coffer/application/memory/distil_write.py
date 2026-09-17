"""Stage two of the distil pass: Coffer's own words for one note (FR-020).

One request per note the routing stage actually touched, carrying **that one
note's** current text and the entries routed to it. A partition of a hundred
notes that gained three entries costs at most three of these — which is the
whole reason routing was a separate stage, and the reason nothing here ever
sees a note it was not asked to rewrite.

**What comes back is a note, not a copy.** This is the reversal FR-020
records: the design this replaces stored the sources' own words, and Codex's
untitled prose bullets therefore arrived as 284 entries whose title,
description and body were the same sentence three times over — against the 16
entries Codex's own index had already distilled the same material into. So the
model is asked to *write*, accumulating what the note already said together
with what the new entries add, and the verbatim material survives one layer
down in ``.raw/``, which the note's provenance points at.

**``description`` is the product.** It is not a summary of the note, it is the
index entry, and the index is the whole of what a session is given (FR-017,
FR-029). A line that says "notes on the venv situation" costs a file read; a
line that says "worktrees have no ``.venv`` — symlink the main one first"
usually ends the errand. The prompt says so in as many words, because this is
the single sentence the layer's delivery value rests on.

**A failure here writes nothing (FR-027).** No completion, a non-JSON answer,
an answer missing a field: this returns ``None``, the caller skips that note,
and the entries routed to it stay undistilled in ``.raw/`` for the next pass.
A half-written note would be worse than no note, because the index line is
what a session reads instead of the body.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from coffer.application.engine_ports import LlmCompletionPort
from coffer.application.memory.distil_routing import parse_json_object
from coffer.domain.memory.note import Note
from coffer.infrastructure.memory.raw_store import StoredRawEntry

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 60.0

WRITE_SYSTEM = (
    "You write one note in a developer's shared AI memory. A note covers ONE "
    "subject, accumulates over time, and is YOUR OWN prose — never a quote of "
    "the material you are given.\n"
    "You are given the note as it currently stands (empty when it is new) and "
    "new entries about the same subject, read out of the developer's coding "
    "agents' own memories. Rewrite the note so that it says everything still "
    "true from both. Keep what the current note already says unless an entry "
    "contradicts it, in which case the entry is newer and wins. Do not pad, do "
    "not hedge, and do not repeat the same point in title, description and "
    "body.\n"
    "The description is the most important line you write. It is the INDEX "
    "entry, and the index — one line per note — is the whole of what a session "
    "is given before it reads anything. Write ONE line that carries the "
    "conclusion itself, so that reading it is usually the end of the errand: "
    '"worktrees have no .venv, symlink the main one first", not "notes about '
    'the virtualenv situation".\n'
    "Reply with EXACTLY ONE JSON object and nothing else — no prose, no "
    "markdown code fences:\n"
    '{"title": "<short subject>", "description": "<one line, the conclusion>", '
    '"body": "<the note, in Markdown, your own words>"}'
)


@dataclass(frozen=True)
class WrittenNote:
    """What the writing stage returns: the three fields it is allowed to set.

    Everything else about a note — its slug, type, origins, search terms and
    timestamps — is Coffer's bookkeeping, derived from the entries and from the
    note that was already there. A model that could set them could rename a
    file, re-file a note into ``global``, or drop a provenance entry, none of
    which is a judgement about meaning.
    """

    title: str
    description: str
    body: str


def _current_payload(existing: Note | None) -> dict[str, str]:
    if existing is None:
        return {"title": "", "description": "", "body": ""}
    return {
        "title": existing.title,
        "description": existing.description,
        "body": existing.body,
    }


def write_payload(
    entries: Sequence[StoredRawEntry], *, existing: Note | None, partition: str
) -> str:
    """The user half of one writing request, as JSON.

    Entries carry their **whole** text here — unlike routing, which caps it
    (``distil_routing.MAX_ROUTING_TEXT_CHARS``). Routing only had to decide
    where an entry belonged; this is where the content actually lands, and
    truncating it would silently drop the detail the pass exists to carry.
    """

    return json.dumps(
        {
            "partition": partition,
            "current_note": _current_payload(existing),
            "new_entries": [
                {
                    "agent": e.agent,
                    "title": e.entry.title,
                    "description": e.entry.description,
                    "text": e.entry.body,
                }
                for e in entries
            ],
        },
        ensure_ascii=False,
    )


def parse_written(text: str) -> WrittenNote | None:
    """One writing answer, or ``None`` when it is not usable.

    A blank body is refused as hard as invalid JSON: a note whose file holds
    only frontmatter is an index line pointing at nothing, and the index line
    is what a session reads instead of the file.
    """
    parsed = parse_json_object(text, log_key="memory.distil.write")
    if not parsed:
        return None
    title = parsed.get("title")
    description = parsed.get("description")
    body = parsed.get("body")
    if not isinstance(body, str) or not body.strip():
        logger.warning("memory.distil.write.empty_body")
        return None
    if not isinstance(title, str) or not title.strip():
        logger.warning("memory.distil.write.missing_title")
        return None
    one_line = " ".join(description.split()) if isinstance(description, str) else ""
    return WrittenNote(
        title=title.strip(),
        # One line, always: ``description`` is rendered into an index line
        # (FR-017), and a newline in it would break the one-note-per-line shape
        # both ``MEMORY.md`` and the delivered payload depend on.
        description=one_line,
        body=body.strip() + "\n",
    )


async def rewrite_note(
    entries: Sequence[StoredRawEntry],
    *,
    existing: Note | None,
    partition: str,
    model: Any,
    completion: LlmCompletionPort,
    credential_resolver: Callable[[str], str],
) -> WrittenNote | None:
    """Rewrite one note from its current text plus the entries routed to it."""
    try:
        text = await asyncio.wait_for(
            completion.complete(
                system=WRITE_SYSTEM,
                user=write_payload(entries, existing=existing, partition=partition),
                model=model,
                credential_resolver=credential_resolver,
            ),
            timeout=_TIMEOUT_SECONDS,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("memory.distil.write.completion_failed", exc_info=True)
        return None
    return parse_written(text)


__all__ = [
    "WRITE_SYSTEM",
    "WrittenNote",
    "parse_written",
    "rewrite_note",
    "write_payload",
]
