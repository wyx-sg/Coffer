"""``card_as_text`` — a refused card written out as a list someone can act on."""

from __future__ import annotations

from coffer.application.channel.card_delivery import card_as_text
from coffer.application.channel.selection_cards import model_card


def test_a_named_choice_also_shows_the_id_the_command_takes():
    # "/model Fable 1M" would send "Fable" to the CLI; the id is what to type.
    labels = {"fable": "Fable 5.1", "claude-fable-5-1[1m]": "Fable 1M", "opus": "opus"}
    text = card_as_text(model_card(current="fable", picks=list(labels), labels=labels))

    assert "• Fable 5.1 ✓ — fable" in text
    assert "• Fable 1M — claude-fable-5-1[1m]" in text
    assert "• opus\n" in text + "\n"  # a label that IS the id is not repeated
