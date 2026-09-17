"""Stage one of the distil pass: where each new entry belongs (spec memory FR-023).

This module asks one question and never writes anything. Given a batch of raw
entries that have not been distilled yet, the **index** of the notes the
partition already holds, and the titles it has already retired, it returns one
action per entry: merge into a named note, open a new one, retire a note this
entry contradicts, or keep nothing.

**Why the index and not the bodies.** FR-023 makes the pass incremental in one
specific sense — *no single request carries the partition's bodies*. A
partition of a hundred notes that gained three entries must cost one request
over a hundred index lines, not a request over a hundred note bodies. So the
notes arrive here as :class:`IndexEntry` — slug, title, description — and the
bodies are the writing stage's business, one note per request. Handing a body
to this stage would be the easy mistake and it is the one the whole two-stage
shape exists to make impossible: this module cannot read a body, because it is
never given one.

**Judgement is about meaning, and that is the point of the stage existing.**
The design this replaces matched entries against each other literally, and on
the maintainer's live vault 378 entries from two agents produced **zero**
cross-agent matches, because two agents never phrase anything the same way.
Each entry therefore carries the agent it came from, so "Claude Code says the
worktree has no `.venv`" and "Codex says builds fail in a linked checkout" can
be recognised as one subject by a reader that understands both sentences.

**The retired titles are input, not decoration (FR-025).** The material a
retired note was built from still sits in the agent's own memory, so the next
aggregation reads it again and — without this list — the next pass re-opens
the note the last one removed. Every prompt says, in as many words, not to
re-open a subject named in it.

**Malformed output degrades to nothing (FR-027).** A model that answers in
prose, returns a JSON array, names an entry that is not in the batch, names a
slug the partition does not have, or invents a fifth action contributes
nothing for whatever it got wrong — logged, never raised. An entry with no
usable action is simply not distilled this pass; it is still in ``.raw/`` and
the next pass sees it again. That is the same "degrade to nothing" discipline
the organise pass held, and it is why a pass can never leave a partition worse
than not running would have.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from coffer.application.engine_ports import LlmCompletionPort
from coffer.domain.memory.note import NOTE_TYPES
from coffer.infrastructure.memory.raw_store import StoredRawEntry

logger = logging.getLogger(__name__)

#: The four actions FR-023 confines the routing stage's output to. Anything
#: else the model names is dropped with a warning.
ACTION_MERGE = "merge"
ACTION_OPEN = "open"
ACTION_RETIRE = "retire"
ACTION_DROP = "drop"
ROUTE_ACTIONS = frozenset({ACTION_MERGE, ACTION_OPEN, ACTION_RETIRE, ACTION_DROP})

#: How many new entries one routing request reasons over. Smaller than the
#: organise pass's 40 because an entry carries its text and a fact carried only
#: a title — but still a batch, because the judgement is comparative: an entry
#: alone cannot be told apart from an entry the batch already covers. Entries
#: are chunked in ``entry_id`` order so the split is identical from one pass to
#: the next; a relationship spanning two chunks is simply not proposed this
#: pass, which the next pass gets another chance at.
DEFAULT_MAX_ENTRIES_PER_CHUNK = 20

#: Routing only decides *where* an entry goes, so it gets the opening of an
#: entry's text rather than all of it. The writing stage gets the whole thing.
#: Both supported sources are short — Codex writes prose bullets and Claude
#: Code writes one topic per file — so this bites rarely and, when it does,
#: costs a routing decision some tail context rather than costing a note any.
MAX_ROUTING_TEXT_CHARS = 2000

_TIMEOUT_SECONDS = 60.0

ROUTING_SYSTEM = (
    "You maintain one partition of a developer's shared AI memory. The "
    "developer runs several coding agents; each keeps its own memory, and none "
    "of them can see any of the others'. You are given entries read out of "
    "those memories, the INDEX of the notes already written here — each note's "
    "slug, title and one-line description, never its text — and the subjects "
    "already retired.\n"
    "Decide exactly one action per entry:\n"
    '- "merge": this subject is already covered. Name the existing note\'s '
    "slug — or, when the subject is covered by ANOTHER ENTRY in this same "
    "batch that you are opening a note for, name that entry's id instead, and "
    "the two share one note. Judge by MEANING, never by wording: two agents "
    "state the same lesson in no shared phrasing, and recognising that is the "
    "whole job.\n"
    '- "open": no existing note covers it. Give a short title for a new note '
    'and its type — "project" (about this repository), "user" (about the '
    'person), "feedback" (a standing instruction the developer gave).\n'
    '- "retire": the entry contradicts an existing note — what that note '
    "recorded is no longer true. Name its slug and say why. That note is "
    "removed and this entry becomes the note replacing it.\n"
    '- "drop": keep nothing. The entry is transient, incidental, or says '
    "nothing worth carrying into another session. This is an ordinary "
    "outcome, not a failure.\n"
    "Never open a note for a subject in the retired list — drop the entry "
    "instead. The material still sits in the agent's own memory and will be "
    "offered to you again otherwise.\n"
    "Reply with EXACTLY ONE JSON object and nothing else — no prose, no "
    "markdown code fences:\n"
    '{"actions": ['
    '{"entry": "<id>", "action": "merge", "slug": "<existing slug>"}, '
    '{"entry": "<id>", "action": "open", "title": "<short title>", '
    '"type": "project"}, '
    '{"entry": "<id>", "action": "retire", "slug": "<existing slug>", '
    '"reason": "<why it is no longer true>"}, '
    '{"entry": "<id>", "action": "drop", "reason": "<why nothing is kept>"}'
    "]}\n"
    "Use only the entry ids and note slugs you were given. Give one action per "
    "entry, and omit an entry you cannot place rather than inventing a slug. "
    "A merge naming another entry must name one you are opening a note for, "
    "and an entry may not merge into itself."
)


@dataclass(frozen=True)
class IndexEntry:
    """One existing note as the routing stage is allowed to see it.

    Slug, title, description — the index line's own material (FR-017), and
    deliberately not the body. See the module docstring.
    """

    slug: str
    title: str
    description: str


@dataclass(frozen=True)
class RouteAction:
    """One decision about one entry, already validated against the batch."""

    entry_id: str
    #: One of :data:`ROUTE_ACTIONS`.
    action: str
    #: The existing note named by a ``merge`` or a ``retire``.
    slug: str = ""
    #: Another entry in the same batch whose note this one joins. A first pass
    #: over a fresh partition has no index at all, so two agents' accounts of
    #: one lesson can only become one note by naming each other — which is
    #: precisely the cross-agent merge this layer exists for (FR-018).
    into_entry: str = ""
    #: The title proposed by an ``open`` (and by a ``retire``'s replacement).
    title: str = ""
    #: The type proposed by an ``open``, when it is one of ``NOTE_TYPES``.
    type: str = ""
    #: Why, for a ``retire`` or a ``drop``. Written into ``RETIRED.md``.
    reason: str = ""


def chunks(
    entries: Sequence[StoredRawEntry], size: int = DEFAULT_MAX_ENTRIES_PER_CHUNK
) -> list[list[StoredRawEntry]]:
    """Split ``entries`` into stable batches, in ``entry_id`` order."""
    ordered = sorted(entries, key=lambda e: e.entry_id)
    step = max(1, size)
    return [list(ordered[i : i + step]) for i in range(0, len(ordered), step)]


def strip_code_fence(text: str) -> str:
    """Drop a ```` ``` ```` wrapper a model added around its JSON."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[: -len("```")]
    return stripped.strip()


def parse_json_object(text: str, *, log_key: str) -> dict[str, Any]:
    """One completion as a JSON object, or ``{}`` for anything that is not one.

    Never raises: a model that cannot follow the format contributes nothing,
    which is exactly as safe as a model that was never asked (FR-027).
    """
    try:
        parsed = json.loads(strip_code_fence(text))
    except (json.JSONDecodeError, ValueError):
        logger.warning("%s.malformed_json", log_key)
        return {}
    if not isinstance(parsed, dict):
        logger.warning("%s.non_object_response", log_key)
        return {}
    return parsed


def _entry_payload(entry: StoredRawEntry) -> dict[str, Any]:
    raw = entry.entry
    text = (
        raw.body if len(raw.body) <= MAX_ROUTING_TEXT_CHARS else raw.body[:MAX_ROUTING_TEXT_CHARS]
    )
    return {
        "id": entry.entry_id,
        # Named on purpose: the cross-agent merge is the one thing this layer
        # exists for, and knowing two entries came from two agents is what
        # makes "same subject, no shared words" a question worth asking.
        "agent": entry.agent,
        "title": raw.title,
        "description": raw.description,
        "type": raw.type,
        "search_terms": list(raw.search_terms),
        "text": text,
    }


def routing_payload(
    entries: Sequence[StoredRawEntry],
    *,
    index: Sequence[IndexEntry],
    retired_titles: Sequence[str],
    partition: str,
) -> str:
    """The user half of one routing request, as JSON."""
    return json.dumps(
        {
            "partition": partition,
            "notes": [
                {"slug": e.slug, "title": e.title, "description": e.description} for e in index
            ],
            "retired_subjects": list(retired_titles),
            "entries": [_entry_payload(e) for e in entries],
        },
        ensure_ascii=False,
    )


def _parse_action(item: Any, *, entry_ids: set[str], slugs: set[str]) -> RouteAction | None:
    if not isinstance(item, dict):
        logger.warning("memory.distil.dropped_action; malformed=%r", item)
        return None
    entry_id = item.get("entry")
    action = item.get("action")
    if not isinstance(entry_id, str) or entry_id not in entry_ids:
        logger.warning("memory.distil.dropped_action; unknown entry=%r", entry_id)
        return None
    if not isinstance(action, str) or action not in ROUTE_ACTIONS:
        logger.warning("memory.distil.dropped_action; unknown action=%r", action)
        return None
    slug = item.get("slug") if isinstance(item.get("slug"), str) else ""
    title = item.get("title") if isinstance(item.get("title"), str) else ""
    type_ = item.get("type") if item.get("type") in NOTE_TYPES else ""
    reason = item.get("reason") if isinstance(item.get("reason"), str) else ""
    into_entry = ""
    if action == ACTION_MERGE and slug not in slugs:
        # A merge may instead name a sibling entry in this batch; anything else
        # is a slug the model invented, and applying it would write a note file
        # under a name nothing else knows.
        if slug in entry_ids and slug != entry_id:
            into_entry, slug = slug, ""
        else:
            logger.warning("memory.distil.dropped_action; unknown merge target=%r", slug)
            return None
    if action == ACTION_RETIRE and slug not in slugs:
        logger.warning("memory.distil.dropped_action; unknown slug=%r action=%s", slug, action)
        return None
    return RouteAction(
        entry_id=entry_id,
        action=action,
        slug=slug or "",
        into_entry=into_entry,
        title=(title or "").strip(),
        type=type_ or "",
        reason=(reason or "").strip(),
    )


def parse_actions(text: str, *, entry_ids: set[str], slugs: set[str]) -> tuple[RouteAction, ...]:
    """Parse one routing answer, keeping only actions that name real things.

    The first action for an entry wins; a second one for the same entry is
    dropped, because FR-023 gives an entry exactly one action and a model that
    names two has not decided.
    """
    parsed = parse_json_object(text, log_key="memory.distil.routing")
    raw_actions = parsed.get("actions")
    if not isinstance(raw_actions, list):
        if parsed:
            logger.warning("memory.distil.routing.no_actions_array")
        return ()
    seen: set[str] = set()
    kept: list[RouteAction] = []
    for item in raw_actions:
        action = _parse_action(item, entry_ids=entry_ids, slugs=slugs)
        if action is None:
            continue
        if action.entry_id in seen:
            logger.warning("memory.distil.dropped_action; duplicate entry=%s", action.entry_id)
            continue
        seen.add(action.entry_id)
        kept.append(action)
    return tuple(kept)


async def route_chunk(
    entries: Sequence[StoredRawEntry],
    *,
    index: Sequence[IndexEntry],
    retired_titles: Sequence[str],
    partition: str,
    model: Any,
    completion: LlmCompletionPort,
    credential_resolver: Callable[[str], str],
) -> tuple[RouteAction, ...]:
    """Route one batch of entries. Returns ``()`` for any failure at all."""
    try:
        text = await asyncio.wait_for(
            completion.complete(
                system=ROUTING_SYSTEM,
                user=routing_payload(
                    entries, index=index, retired_titles=retired_titles, partition=partition
                ),
                model=model,
                credential_resolver=credential_resolver,
            ),
            timeout=_TIMEOUT_SECONDS,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("memory.distil.routing.completion_failed", exc_info=True)
        return ()
    return parse_actions(
        text,
        entry_ids={e.entry_id for e in entries},
        slugs={e.slug for e in index},
    )


__all__ = [
    "ACTION_DROP",
    "ACTION_MERGE",
    "ACTION_OPEN",
    "ACTION_RETIRE",
    "DEFAULT_MAX_ENTRIES_PER_CHUNK",
    "MAX_ROUTING_TEXT_CHARS",
    "ROUTE_ACTIONS",
    "ROUTING_SYSTEM",
    "IndexEntry",
    "RouteAction",
    "chunks",
    "parse_actions",
    "parse_json_object",
    "route_chunk",
    "routing_payload",
    "strip_code_fence",
]
