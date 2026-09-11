"""The selection cards' pure rendering rules (FR-017/FR-018).

The model card is built from the agent's whole model catalogue — 29 entries for
``claude_code`` — but a card is a handful of quick-picks, not a catalogue:
SeaTalk refuses an over-long one outright (``code=102``) and the user is left
with nothing at all.
"""

from __future__ import annotations

from coffer.application.channel.selection_cards import (
    MAX_MODEL_PICKS,
    SelectionCard,
    model_card,
)


def _values(card: SelectionCard) -> list[str]:
    return [b.value for b in card.buttons]


class TestModelCardQuickPicks:
    def test_a_long_catalogue_is_capped(self):
        card = model_card(current=None, picks=[f"m{i}" for i in range(29)])

        assert len(card.buttons) == MAX_MODEL_PICKS
        assert _values(card) == [f"model:m{i}" for i in range(MAX_MODEL_PICKS)]

    def test_the_short_catalogue_is_shown_whole(self):
        card = model_card(current=None, picks=["sonnet", "opus"])

        assert _values(card) == ["model:sonnet", "model:opus"]

    def test_the_current_model_survives_the_cap(self):
        # Pinned via `/model <name>` to something far down the catalogue: it
        # must still get a button, or the refreshed card shows no tick at all.
        picks = [f"m{i}" for i in range(29)]

        card = model_card(current="m20", picks=picks)

        assert "model:m20" in _values(card)
        assert len(card.buttons) == MAX_MODEL_PICKS
        [ticked] = [b.value for b in card.buttons if b.label.endswith("✓")]
        assert ticked == "model:m20"

    def test_the_current_model_is_not_duplicated(self):
        card = model_card(current="sonnet", picks=["sonnet", "opus", "haiku"])

        assert _values(card) == ["model:sonnet", "model:opus", "model:haiku"]

    def test_the_body_still_points_at_the_rest_of_the_catalogue(self):
        # What makes a bounded card honest: every other model is one text
        # command away. (Angle brackets are safe on SeaTalk; live-probed.)
        card = model_card(current=None, picks=[f"m{i}" for i in range(29)])

        assert "/model <name>" in card.text

    def test_an_oversized_callback_is_still_dropped(self):
        card = model_card(current=None, picks=["ok", "x" * 100])

        assert _values(card) == ["model:ok"]
