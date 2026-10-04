"""fan_out: one hint sink feeding several, each isolated from the others."""

from __future__ import annotations

from coffer.application.reconcile.hints import fan_out
from coffer.domain.reconcile import Changed


def test_every_sink_gets_every_hint_in_order_even_after_one_raises() -> None:
    first: list[Changed] = []
    last: list[Changed] = []

    def _boom(_: Changed) -> None:
        raise RuntimeError("sink gone")

    sink = fan_out(first.append, _boom, last.append)
    hints = [Changed("skill", "u1"), Changed("skill", "u1", "delete")]
    for hint in hints:
        sink(hint)
    assert first == hints
    assert last == hints


def test_a_hint_is_an_upsert_unless_it_says_delete() -> None:
    assert Changed("skill", "u1").op == "upsert"
