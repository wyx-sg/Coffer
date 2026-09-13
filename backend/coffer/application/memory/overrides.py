"""The developer's decisions about a fact — the one thing this layer does not
derive (spec memory FR-040, FR-070; ADR
``aggregate-agent-memory-never-write-it``).

Everything else under ``~/.coffer/memory/`` can be deleted and rebuilt from
the agents' own memory. A hide, a pin, a hand-picked supersession, or a
settled conflict cannot be recomputed — the model (or no model at all, per
FR-032) does not know the developer's mind — so those four decisions live
apart, keyed by ``Fact.key`` (stable across a rebuild), and are reapplied to
whatever aggregation produces next (FR-041). That reapplication, ``apply``
below, is pure: it knows nothing about SQL or files, only about ``Fact`` and
``Override`` values, so it is exercised directly in the unit tier with no
database at all.

The repository that persists them lives in
``infrastructure/persistence/models.py`` directly — the same
``sqlite_insert(...).on_conflict_do_update(...)`` idiom every other repo in
this codebase uses (see ``infrastructure/mcp/health_repo.py``) — rather than
defining a port here and an adapter in ``infrastructure/``. That is a
deliberate, narrow exception to "application does not import infrastructure"
(``backend/pyproject.toml``'s import-linter contract, extended alongside this
file): the table behind it is one key and four decision columns with no query
complexity a port would earn its keep abstracting away, the same reasoning
that already exempts the knowledge substrate from the same contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

from coffer.domain.memory.fact import STATUS_SUPERSEDED, Fact


@dataclass(frozen=True)
class Override:
    """One developer decision about one fact, keyed by its stable ``Fact.key``.

    Every field defaults to "no decision of this kind" so a caller can build
    an ``Override`` naming only the one thing it means to change.
    """

    fact_key: str
    hidden: bool = False
    pinned: bool = False
    #: Non-empty overrides whatever a model proposed as the fact that
    #: replaced this one, and always wins over it (FR-041).
    superseded_by: str = ""
    #: Non-empty settles a conflict this fact was flagged in. Names the fact
    #: key the developer settled the conflict in favour of — which side won
    #: does not change what ``apply`` does to the pair (see its docstring);
    #: it is kept here as the developer's own record of the decision made.
    conflict_choice: str = ""


@dataclass(frozen=True)
class AppliedFacts:
    """Facts re-stamped with the developer's decisions, plus what a bare
    ``Fact`` cannot say on its own: which keys are hidden or pinned, and which
    overrides matched no fact at all.

    ``Fact`` gains no ``hidden``/``pinned`` fields for this — every consumer
    that does not care about overrides would otherwise carry two booleans it
    never reads — so they travel alongside instead, as fact-key sets a caller
    checks membership against.
    """

    facts: tuple[Fact, ...]
    hidden: frozenset[str] = field(default_factory=frozenset)
    pinned: frozenset[str] = field(default_factory=frozenset)
    #: ``Override.fact_key`` values that matched no fact in this batch — the
    #: surface reports these as orphans rather than silently dropping them.
    orphaned: tuple[str, ...] = field(default_factory=tuple)

    def visible(self) -> tuple[Fact, ...]:
        """What delivery and recall may show — hidden facts excluded (FR-042)."""
        return tuple(f for f in self.facts if f.key not in self.hidden)


def apply(facts: Sequence[Fact], overrides: Mapping[str, Override]) -> AppliedFacts:
    """Re-stamp ``facts`` with the developer's decisions. Pure — no I/O.

    Overrides are processed in sorted key order so that two calls given the
    same inputs always produce the same result: a settled conflict touches
    two facts at once (the one the override is keyed to, and whichever one
    its ``conflicts_with`` names back), and which one is edited first must
    not depend on a dict's iteration order.

    - ``hidden`` / ``pinned`` are recorded in the result's own sets; ``Fact``
      itself is untouched (see ``AppliedFacts``).
    - A non-empty ``superseded_by`` replaces whatever the fact's own
      ``superseded_by`` held (model-proposed or not), sets ``status`` to
      superseded, and clears ``proposed`` — a developer's supersession is
      settled, never merely suggested (FR-033, FR-041).
    - A non-empty ``conflict_choice`` clears ``conflicts_with`` on the fact it
      is keyed to *and* on every fact that fact's own ``conflicts_with``
      named — a conflict is a relationship between two facts, so settling it
      must resolve both sides, not leave one still flagged against a fact
      that no longer disputes it. ``proposed`` clears on a fact only once its
      own ``conflicts_with`` is fully empty; a fact left disputing a third,
      untouched fact is still carrying a model's unresolved claim.
    - A key in ``overrides`` matching no fact in ``facts`` is skipped and
      reported in ``orphaned`` rather than applied or raising — the facts it
      once named may simply have aged out of this batch.
    """
    by_key: dict[str, Fact] = {f.key: f for f in facts}
    hidden: set[str] = set()
    pinned: set[str] = set()
    orphaned: list[str] = []

    for fact_key in sorted(overrides):
        override = overrides[fact_key]
        if fact_key not in by_key:
            orphaned.append(fact_key)
            continue
        if override.hidden:
            hidden.add(fact_key)
        if override.pinned:
            pinned.add(fact_key)
        if override.superseded_by:
            fact = by_key[fact_key]
            by_key[fact_key] = replace(
                fact,
                superseded_by=override.superseded_by,
                status=STATUS_SUPERSEDED,
                proposed=False,
            )
        if override.conflict_choice:
            _settle_conflict(by_key, fact_key)

    return AppliedFacts(
        facts=tuple(by_key[f.key] for f in facts),
        hidden=frozenset(hidden),
        pinned=frozenset(pinned),
        orphaned=tuple(orphaned),
    )


def _settle_conflict(by_key: dict[str, Fact], fact_key: str) -> None:
    """Clear ``conflicts_with`` on ``fact_key`` and every fact it named back."""
    fact = by_key[fact_key]
    disputed = fact.conflicts_with
    by_key[fact_key] = replace(fact, conflicts_with=(), proposed=False)
    for other_key in disputed:
        other = by_key.get(other_key)
        if other is None:
            continue
        remaining = tuple(k for k in other.conflicts_with if k != fact_key)
        by_key[other_key] = replace(
            other,
            conflicts_with=remaining,
            proposed=other.proposed if remaining else False,
        )
