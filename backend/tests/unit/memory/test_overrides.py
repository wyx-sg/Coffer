"""``apply`` is the heart of FR-041 and is pure — no filesystem, no database —
so every case lives here in the unit tier: hide, pin, supersede, settle a
conflict, and the orphan an override leaves behind when its fact is gone.
"""

from __future__ import annotations

from coffer.application.memory.overrides import AppliedFacts, Override, apply
from coffer.domain.memory.fact import STATUS_ACTIVE, STATUS_SUPERSEDED, TYPE_PROJECT, Fact, Origin


def _fact(key_seed: str, **overrides: object) -> Fact:
    """A fact whose ``.key`` is deterministic from ``key_seed``, via one origin
    whose ``native_path`` is the seed — ``Fact.key`` hashes the origin triple,
    so two facts built from different seeds get different keys."""
    defaults: dict[str, object] = {
        "slug": key_seed,
        "title": key_seed,
        "description": "",
        "type": TYPE_PROJECT,
        "body": "body",
        "partition": "coffer",
        "origins": (Origin(agent="claude_code", native_path=f"/mem/{key_seed}.md"),),
    }
    defaults.update(overrides)
    return Fact(**defaults)  # type: ignore[arg-type]


def test_apply_with_no_overrides_is_a_no_op() -> None:
    fact = _fact("a")
    result = apply([fact], {})
    assert result.facts == (fact,)
    assert result.hidden == frozenset()
    assert result.pinned == frozenset()
    assert result.orphaned == ()


def test_hidden_fact_is_recorded_hidden_but_the_fact_itself_is_unchanged() -> None:
    fact = _fact("a")
    result = apply([fact], {fact.key: Override(fact_key=fact.key, hidden=True)})
    assert result.hidden == frozenset({fact.key})
    assert result.facts == (fact,)  # Fact itself carries no hidden field


def test_visible_excludes_hidden_facts() -> None:
    shown = _fact("a")
    hidden = _fact("b")
    result = apply(
        [shown, hidden],
        {hidden.key: Override(fact_key=hidden.key, hidden=True)},
    )
    assert result.visible() == (shown,)


def test_pinned_fact_is_recorded_pinned() -> None:
    fact = _fact("a")
    result = apply([fact], {fact.key: Override(fact_key=fact.key, pinned=True)})
    assert result.pinned == frozenset({fact.key})


def test_superseded_by_override_wins_over_no_prior_supersession() -> None:
    fact = _fact("a", status=STATUS_ACTIVE, superseded_by="", proposed=False)
    result = apply(
        [fact],
        {fact.key: Override(fact_key=fact.key, superseded_by="winner-key")},
    )
    (restamped,) = result.facts
    assert restamped.superseded_by == "winner-key"
    assert restamped.status == STATUS_SUPERSEDED
    assert restamped.proposed is False


def test_superseded_by_override_replaces_a_model_proposed_one() -> None:
    fact = _fact("a", status=STATUS_SUPERSEDED, superseded_by="model-guess", proposed=True)
    result = apply(
        [fact],
        {fact.key: Override(fact_key=fact.key, superseded_by="developer-choice")},
    )
    (restamped,) = result.facts
    assert restamped.superseded_by == "developer-choice"
    assert restamped.proposed is False


def test_settled_conflict_clears_conflicts_with_on_both_sides() -> None:
    a_key = _fact("a").key
    b_key = _fact("b").key
    a = _fact("a", conflicts_with=(b_key,), proposed=True)
    b = _fact("b", conflicts_with=(a_key,), proposed=True)
    result = apply(
        [a, b],
        {a.key: Override(fact_key=a.key, conflict_choice=a.key)},
    )
    by_key = {f.key: f for f in result.facts}
    assert by_key[a.key].conflicts_with == ()
    assert by_key[a.key].proposed is False
    assert by_key[b.key].conflicts_with == ()
    assert by_key[b.key].proposed is False


def test_settled_conflict_leaves_an_unrelated_conflict_on_the_other_side_alone() -> None:
    a_key = _fact("a").key
    b_key = _fact("b").key
    a = _fact("a", conflicts_with=(b_key,), proposed=True)
    # "b" conflicts with both "a" and a third fact "c" that is not in this
    # apply() call at all (aged out of the batch, or in another partition).
    b = _fact("b", conflicts_with=(a_key, "c-key-not-in-batch"), proposed=True)
    result = apply(
        [a, b],
        {a.key: Override(fact_key=a.key, conflict_choice=a.key)},
    )
    by_key = {f.key: f for f in result.facts}
    assert by_key[a.key].conflicts_with == ()
    assert by_key[b.key].conflicts_with == ("c-key-not-in-batch",)
    # b still disputes a fact this call never touched, so its unresolved
    # model claim on THAT relationship stands.
    assert by_key[b.key].proposed is True


def test_an_override_matching_no_fact_is_not_applied_and_is_reported_as_orphaned() -> None:
    fact = _fact("a")
    result = apply(
        [fact],
        {"no-such-key": Override(fact_key="no-such-key", hidden=True)},
    )
    assert result.facts == (fact,)
    assert result.hidden == frozenset()
    assert result.orphaned == ("no-such-key",)


def test_multiple_overrides_are_all_applied() -> None:
    a = _fact("a")
    b = _fact("b")
    c = _fact("c")
    result = apply(
        [a, b, c],
        {
            a.key: Override(fact_key=a.key, hidden=True),
            b.key: Override(fact_key=b.key, pinned=True),
            "orphan": Override(fact_key="orphan", pinned=True),
        },
    )
    assert result.hidden == frozenset({a.key})
    assert result.pinned == frozenset({b.key})
    assert result.orphaned == ("orphan",)
    assert {f.key for f in result.facts} == {a.key, b.key, c.key}


def test_result_type_is_appliedfacts() -> None:
    result = apply([], {})
    assert isinstance(result, AppliedFacts)
    assert result.facts == ()
    assert result.visible() == ()
