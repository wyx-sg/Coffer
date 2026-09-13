"""The pure heart of aggregation: merging and naming, with no I/O.

``MemoryService`` (``service.py``) does the orchestration — listing agent
Resources, calling readers, reading and writing the store. Everything in
*this* module is a plain function over ``Fact``/``RawFact`` values, which is
what lets the tricky part — deciding which facts are certainly the same fact,
and what file name each one gets — be exercised in the unit tier with no
filesystem and no database at all.

Two decisions live here and are documented where they are made, not just in
this docstring:

- :func:`merge_duplicates` implements FR-022's "only on an exact signal" rule.
  Two facts merge into one (union of origins) only when they are identical in
  a way that cannot be a coincidence: the same normalised body text, or the
  same ``(type, partition, normalised title)``. Nothing softer — a fuzzy
  match belongs to the organise pass's model (spec memory FR-030), which can
  weigh a judgement call; a deterministic guess here would silently drop a
  fact no one asked it to drop.
- :func:`assign_slugs` gives every fact a stable, readable file name, on the
  same discipline ``infrastructure/knowledge/naming.py`` uses (a slug from the
  title, a short numeric suffix only on a real collision). It is a small
  local copy rather than an import: this package may not reach into
  ``infrastructure.knowledge`` (Contract 5d — the knowledge kind is fenced off
  from every other kind), and the whole function is ~10 lines of pure string
  handling, cheaper to duplicate than to route around.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from coffer.domain.memory.fact import Fact, Origin
from coffer.domain.memory.reader import RawFact
from coffer.domain.resource import Resource

# ----- results (returned to callers of MemoryService.aggregate) -----------


@dataclass(frozen=True)
class SourceFailure:
    """One reader's ``UnreadableMemory`` for one source, isolated (FR-005)."""

    agent: str
    path: str
    reason: str


@dataclass(frozen=True)
class AggregationResult:
    partitions: tuple[str, ...]
    facts_written: int
    sources_read: int
    sources_skipped: int
    failures: tuple[SourceFailure, ...]


# ----- the agent-kind seam --------------------------------------------------


@dataclass(frozen=True)
class AgentSource:
    """A registered, enabled agent Resource, reduced to what aggregation
    needs: its own resource name (an ``Origin.agent``), which reader applies
    to it, and the directory to hand that reader.

    Built by a resolver the composition root injects (mirroring
    ``SkillService``'s ``AgentSkillDirResolver``) so this package never
    imports ``coffer.domain.agent`` directly — memory is its own kind, and a
    direct import would be exactly the cross-kind coupling Contracts
    5/5b/5c/5d already fence the other kinds off from.
    """

    agent: str
    agent_type: str
    config_dir: str


#: Given an ``agent``-kind Resource, return what aggregation needs from it.
AgentSourceResolver = Callable[[Resource], AgentSource]


# ----- turning one RawFact into a candidate Fact ---------------------------


def build_fact(
    raw: RawFact,
    *,
    partition: str,
    agent: str,
    native_path: str,
    captured_at: str,
) -> Fact:
    """One freshly-parsed ``RawFact``, wrapped as a ``Fact`` with a single
    origin. ``slug`` is left blank — :func:`assign_slugs` fills it in once
    every fact bound for a partition is known, so a collision can be resolved
    against the whole set rather than one at a time.
    """
    origin = Origin(
        agent=agent,
        native_path=native_path,
        anchor=raw.anchor,
        captured_at=captured_at,
        source_written_at=raw.source_written_at,
    )
    return Fact(
        slug="",
        title=raw.title,
        description=raw.description,
        type=raw.type,
        body=raw.body,
        partition=partition,
        origins=(origin,),
    )


# ----- FR-022: merge only what is certain -----------------------------------


def _normalize(text: str) -> str:
    return " ".join(text.strip().lower().split())


def merge_duplicates(facts: Sequence[Fact]) -> tuple[Fact, ...]:
    """Merge facts that are certainly the same thing; leave everything else
    apart. See the module docstring for the exact-signal rule (FR-022).

    Uses union-find over the two signals so the merge is transitive: if A and
    B share a body and B and C share a title, all three land in one fact
    rather than two — the alternative (a fresh dict per signal, last write
    wins) can silently split a group depending on iteration order, which is
    the opposite of the determinism this whole module exists for.
    """
    n = len(facts)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    body_index: dict[tuple[str, str], int] = {}
    title_index: dict[tuple[str, str, str], int] = {}
    for i, fact in enumerate(facts):
        body_key = (fact.partition, _normalize(fact.body))
        title_key = (fact.type, fact.partition, _normalize(fact.title))
        if body_key in body_index:
            union(i, body_index[body_key])
        else:
            body_index[body_key] = i
        if title_key in title_index:
            union(i, title_index[title_key])
        else:
            title_index[title_key] = i

    groups: dict[int, list[Fact]] = defaultdict(list)
    order: list[int] = []
    for i, fact in enumerate(facts):
        root = find(i)
        if root not in groups:
            order.append(root)
        groups[root].append(fact)

    return tuple(_merge_group(groups[root]) for root in order)


def _merge_group(group: list[Fact]) -> Fact:
    if len(group) == 1:
        return group[0]
    # Deterministic choice of which fact's own title/description/body/slug
    # the merged fact carries forward: the fact whose smallest origin key
    # sorts first. Origin keys are content hashes (fact.py), so this has no
    # relation to recency — it only needs to be the same choice every time
    # the same origins are merged, which it is.
    ordered = sorted(group, key=lambda f: min((o.key for o in f.origins), default=""))
    base = ordered[0]
    origins: list[Origin] = []
    seen: set[str] = set()
    for fact in ordered:
        for origin in fact.origins:
            if origin.key not in seen:
                seen.add(origin.key)
                origins.append(origin)
    return replace(base, origins=tuple(origins))


# ----- file names ------------------------------------------------------------

_SEPARATORS = re.compile(r"[\s_/\\]+")
_DROP = re.compile(r"[^A-Za-z0-9\-一-鿿ぁ-ヿ]")
_DASHES = re.compile(r"-{2,}")
_MAX_SLUG_CHARS = 80


def _slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title or "").strip().lower()
    stem = _DASHES.sub("-", _DROP.sub("", _SEPARATORS.sub("-", normalized))).strip("-")
    return (stem or "fact")[:_MAX_SLUG_CHARS].strip("-") or "fact"


def assign_slugs(facts: Sequence[Fact]) -> tuple[Fact, ...]:
    """Give every fact in one partition a file slug, preferring the slug it
    already has (read back from the store) so a fact's file name does not
    churn from one pass to the next just because it was re-merged.

    Only a fact with no slug yet — freshly merged from RawFacts this pass —
    gets a fresh one, derived from its title; a collision against anything
    already claimed (an existing slug, or another fresh one) gets a short
    numeric suffix, exactly the discipline ``infrastructure/knowledge/naming.py``
    uses for the same problem in the knowledge layer.
    """
    used: set[str] = set()
    kept: list[Fact] = list(facts)
    needs_slug: list[int] = []
    for i, fact in enumerate(facts):
        if fact.slug and fact.slug not in used:
            used.add(fact.slug)
        else:
            needs_slug.append(i)

    # Assign fresh slugs in a stable order (by identity, not list position) so
    # two facts sharing a title get the same suffix pairing every pass.
    pending = sorted(needs_slug, key=lambda i: facts[i].key)
    for i in pending:
        fact = facts[i]
        base = _slugify(fact.title)
        slug = base
        n = 2
        while slug in used:
            slug = f"{base}-{n}"
            n += 1
        used.add(slug)
        kept[i] = replace(fact, slug=slug)

    return tuple(kept)
