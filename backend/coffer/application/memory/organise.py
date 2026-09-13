"""The organise pass: one structured completion over a partition's facts.

Memory is derived twice over — once from the agent's native store into a
``Fact``, and again here, from a partition's facts into a tidier partition of
the same facts — and the second derivation is allowed to be aggressive about
it in a way knowledge's tidy is not. Knowledge's ``tidy.py`` archives every
prior revision into ``.history/`` before it rewrites a file, because the
knowledge tree is the only copy of what is in it. This tree is not: every
fact here also still lives in the agent's own native memory, so a bad
organise pass costs nothing worse than a re-sync — the next aggregation
reads the sources again and this pass runs again on the result. That is why
there is no archive step below, and why merging or superseding a fact is
just another rewrite of a file this layer already owns.

**One completion, not a loop.** Knowledge's tidy hands a model a bounded
agentic tool loop because it rewrites arbitrary prose across arbitrarily many
files. This pass only ever answers one question — which facts in *this*
partition are the same fact, which one an earlier fact and a later one
disagree about, and which pair simply disagrees — so it hands the model one
compact, structured prompt per chunk and parses one JSON answer. There is
nothing for a tool to call.

**Never delete, never rewrite a body (FR-031).** A "duplicate" proposal does
not delete either file: it enriches the surviving fact with the other's
origins and marks the other fact ``superseded`` — the record other surfaces
already understand — so both files remain on disk and only the derived
metadata (status, ``superseded_by``, ``conflicts_with``, ``proposed``)
changes. A fact's ``title``/``description``/``body`` are never touched here.

**Everything the model proposes is a proposal (FR-033).** ``proposed=True``
is set on every fact this pass mutates, so a surface can always tell a
model's finding apart from a developer's own decision (``overrides.py``),
which always wins on the next reapplication regardless of what this pass
just wrote (FR-041).

**Malformed model output degrades to nothing, never to an exception.** A
model that answers in prose, returns invalid JSON, names a fact that does not
exist, or names the same fact twice in one pair contributes no proposals for
whatever it got wrong — logged, not raised. The mechanical digest still gets
written either way (FR-032), so an organise pass can never make delivery
worse than doing nothing would have.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from coffer.application.engine_ports import LlmCompletionPort, ModelSelectorPort
from coffer.application.memory.digest import render_digest
from coffer.domain.memory.fact import STATUS_ACTIVE, STATUS_SUPERSEDED, Fact
from coffer.infrastructure.memory import paths, store

logger = logging.getLogger(__name__)

#: How many active facts one completion call reasons over. The prompt carries
#: only a fact's key/title/description/type — never its body — so this is
#: cheap per fact, but the relationships the model is asked to find are
#: pairwise in its own reasoning, and a long, thin list of near-duplicate
#: titles is exactly the case where a model's attention degrades first. 40
#: keeps a chunk's prompt small and the judgement call tight. A partition
#: over the bound is split into contiguous chunks (sorted by key, so the
#: split is stable from one pass to the next) and each is judged on its own;
#: a relationship that spans two chunks is simply not proposed this pass.
#: That is an acceptable gap rather than a defect: nothing here is a one-shot
#: judgement (module docstring) — the next pass, or a partition that has
#: shrunk by then, gets another chance at it.
DEFAULT_MAX_FACTS_PER_CHUNK = 40

_TIMEOUT_SECONDS = 30.0

ORGANISE_SYSTEM = (
    "You review a batch of memory facts an AI coding agent recorded about one "
    "project, or about the developer. Each fact is given only by its key, "
    "title, description and type — never its full text.\n"
    "Find three kinds of relationship, each expressed by the facts' keys:\n"
    "1. duplicates — two facts that say the same thing in different words.\n"
    "2. supersedes — an older fact a newer one plainly contradicts or "
    "replaces.\n"
    "3. conflicts — two facts that disagree, where neither one looks like it "
    "replaces the other.\n"
    "Reply with EXACTLY ONE JSON object and nothing else — no prose, no "
    "markdown code fences, no explanation:\n"
    '{"duplicates": [["keyA", "keyB"]], '
    '"supersedes": [{"older": "keyA", "newer": "keyB"}], '
    '"conflicts": [["keyA", "keyB"]]}\n'
    "Only use keys you were given. Omit an array, or leave it empty, when "
    "you have nothing to propose for it."
)


@dataclass(frozen=True)
class OrganiseResult:
    """What one organise pass over one partition did."""

    partition: str
    #: Duplicate pairs merged into one surviving fact.
    merged: int
    #: Facts newly marked superseded by this pass.
    superseded: int
    #: Conflict pairs flagged (counted once per pair, not per fact).
    conflicts: int
    #: Whether an internal connection was configured and consulted at all —
    #: false only when no model exists to ask (FR-032's mechanical path).
    model_used: bool


def _facts_payload(facts: Sequence[Fact]) -> list[dict[str, str]]:
    return [
        {"key": f.key, "title": f.title, "description": f.description, "type": f.type}
        for f in facts
    ]


def _chunks(facts: Sequence[Fact], size: int) -> list[list[Fact]]:
    ordered = sorted(facts, key=lambda f: f.key)
    return [list(ordered[i : i + size]) for i in range(0, len(ordered), size)]


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.endswith("```"):
            stripped = stripped[: -len("```")]
    return stripped.strip()


def _parse_proposals(text: str) -> dict[str, Any]:
    """Parse one completion into a proposals dict, or ``{}`` for anything
    that is not a well-formed JSON object — prose, a JSON array, garbage.

    Never raises: a model that cannot follow the format contributes nothing,
    which is exactly as safe as a model that was never asked (module
    docstring's "degrades to nothing" rule).
    """
    try:
        parsed = json.loads(_strip_code_fence(text))
    except (json.JSONDecodeError, ValueError):
        logger.warning("memory.organise.malformed_json")
        return {}
    if not isinstance(parsed, dict):
        logger.warning("memory.organise.non_object_response")
        return {}
    return parsed


@dataclass
class _Counts:
    merged: int = 0
    superseded: int = 0
    conflicts: int = 0


def _apply_duplicate(by_key: dict[str, Fact], valid: set[str], pair: Any, counts: _Counts) -> None:
    if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
        logger.warning("memory.organise.dropped_duplicate; malformed pair=%r", pair)
        return
    key_a, key_b = pair
    if not (isinstance(key_a, str) and isinstance(key_b, str)) or key_a == key_b:
        logger.warning("memory.organise.dropped_duplicate; pair=%r", pair)
        return
    if key_a not in valid or key_b not in valid:
        logger.warning("memory.organise.dropped_duplicate; unknown key in pair=%r", pair)
        return
    # The smaller key wins: `Fact.key` is already each fact's own smallest
    # origin key, so the winner keeps the identity a developer's override may
    # already be attached to (Fact.key's own docstring; mirrors
    # `aggregate._merge_group`'s base-selection rule for the same reason).
    winner_key, loser_key = sorted((key_a, key_b))
    winner, loser = by_key[winner_key], by_key[loser_key]
    if loser.status == STATUS_SUPERSEDED:
        return  # already settled this pass or a prior one
    seen = {o.key for o in winner.origins}
    merged_origins = winner.origins + tuple(o for o in loser.origins if o.key not in seen)
    by_key[winner_key] = replace(winner, origins=merged_origins, proposed=True)
    by_key[loser_key] = replace(
        loser, status=STATUS_SUPERSEDED, superseded_by=winner.key, proposed=True
    )
    counts.merged += 1


def _apply_supersede(by_key: dict[str, Fact], valid: set[str], item: Any, counts: _Counts) -> None:
    if not isinstance(item, dict):
        logger.warning("memory.organise.dropped_supersede; malformed=%r", item)
        return
    older_key, newer_key = item.get("older"), item.get("newer")
    if not (isinstance(older_key, str) and isinstance(newer_key, str)) or older_key == newer_key:
        logger.warning("memory.organise.dropped_supersede; item=%r", item)
        return
    if older_key not in valid or newer_key not in valid:
        logger.warning("memory.organise.dropped_supersede; unknown key in item=%r", item)
        return
    older = by_key[older_key]
    newer = by_key[newer_key]
    if older.status == STATUS_SUPERSEDED:
        return
    by_key[older_key] = replace(
        older, status=STATUS_SUPERSEDED, superseded_by=newer.key, proposed=True
    )
    counts.superseded += 1


def _apply_conflict(by_key: dict[str, Fact], valid: set[str], pair: Any, counts: _Counts) -> None:
    if not (isinstance(pair, (list, tuple)) and len(pair) == 2):
        logger.warning("memory.organise.dropped_conflict; malformed pair=%r", pair)
        return
    key_a, key_b = pair
    if not (isinstance(key_a, str) and isinstance(key_b, str)) or key_a == key_b:
        logger.warning("memory.organise.dropped_conflict; pair=%r", pair)
        return
    if key_a not in valid or key_b not in valid:
        logger.warning("memory.organise.dropped_conflict; unknown key in pair=%r", pair)
        return
    a, b = by_key[key_a], by_key[key_b]
    if key_b not in a.conflicts_with:
        a = replace(a, conflicts_with=(*a.conflicts_with, key_b), proposed=True)
    if key_a not in b.conflicts_with:
        b = replace(b, conflicts_with=(*b.conflicts_with, key_a), proposed=True)
    by_key[key_a], by_key[key_b] = a, b
    counts.conflicts += 1


def _apply_chunk_proposals(
    by_key: dict[str, Fact], chunk: Sequence[Fact], proposals: dict[str, Any], counts: _Counts
) -> None:
    valid = {f.key for f in chunk}
    for pair in proposals.get("duplicates") or []:
        _apply_duplicate(by_key, valid, pair, counts)
    for item in proposals.get("supersedes") or []:
        _apply_supersede(by_key, valid, item, counts)
    for pair in proposals.get("conflicts") or []:
        _apply_conflict(by_key, valid, pair, counts)


async def _complete(
    chunk: Sequence[Fact],
    *,
    model: Any,
    completion: LlmCompletionPort,
    credential_resolver: Callable[[str], str],
) -> dict[str, Any]:
    try:
        text = await asyncio.wait_for(
            completion.complete(
                system=ORGANISE_SYSTEM,
                user=json.dumps(_facts_payload(chunk)),
                model=model,
                credential_resolver=credential_resolver,
            ),
            timeout=_TIMEOUT_SECONDS,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("memory.organise.completion_failed", exc_info=True)
        return {}
    return _parse_proposals(text)


def _write_summary(partition: str, text: str) -> None:
    path = paths.summary_path(partition)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


async def organise_partition(
    partition: str,
    *,
    models: ModelSelectorPort,
    completion: LlmCompletionPort,
    credential_resolver: Callable[[str], str],
    max_facts_per_chunk: int = DEFAULT_MAX_FACTS_PER_CHUNK,
) -> OrganiseResult:
    """Organise one partition: propose merges/supersessions/conflicts over
    its active facts, then (always) rewrite its digest.

    With no internal connection configured, ``model_used`` is false and no
    proposal is made at all — the digest is still regenerated mechanically
    (FR-032; ``digest.render_digest`` needs no model either). This mirrors
    ``run_tidy``'s ``no_model``/``ok`` split, except organise never has an
    "empty" no-op: an empty partition still gets a (trivial) digest, because
    FR-032 requires the digest step itself to never be a no-op.
    """
    all_facts = store.list_facts(partition)
    by_key: dict[str, Fact] = {f.key: f for f in all_facts}
    original = dict(by_key)

    model = await models.get_default()
    counts = _Counts()
    if model is not None:
        active = [f for f in all_facts if f.status == STATUS_ACTIVE]
        for chunk in _chunks(active, max_facts_per_chunk):
            # Facts already turned into a merge loser earlier in this same
            # pass must not be re-offered to the model under a status the
            # partition no longer has.
            live_chunk = [by_key[f.key] for f in chunk if by_key[f.key].status == STATUS_ACTIVE]
            if not live_chunk:
                continue
            proposals = await _complete(
                live_chunk,
                model=model,
                completion=completion,
                credential_resolver=credential_resolver,
            )
            _apply_chunk_proposals(by_key, live_chunk, proposals, counts)

    for key, fact in by_key.items():
        if fact != original[key]:
            store.write_fact(fact)

    _write_summary(partition, render_digest(list(by_key.values()), partition=partition))

    return OrganiseResult(
        partition=partition,
        merged=counts.merged,
        superseded=counts.superseded,
        conflicts=counts.conflicts,
        model_used=model is not None,
    )


__all__ = [
    "DEFAULT_MAX_FACTS_PER_CHUNK",
    "ORGANISE_SYSTEM",
    "OrganiseResult",
    "organise_partition",
]
