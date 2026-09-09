"""Unit tests for ``model_system_context`` — the per-turn note that tells the
agent which model Coffer put it on.

The agent cannot see Coffer's choice; asked over a real channel it named a model
it was not running. The note must be unambiguous in both directions: an explicit
override, and no override at all (where guessing a version is the failure mode).
"""

from __future__ import annotations

from coffer.infrastructure.chat.adapter_support import model_system_context

_AVAILABLE = ["fable", "opus", "sonnet"]


def test_names_the_model_coffer_selected() -> None:
    text = model_system_context("opus", _AVAILABLE)

    assert "`opus`" in text
    assert "trust this note" in text.lower()


def test_no_override_says_the_cli_default_and_forbids_guessing() -> None:
    text = model_system_context(None, _AVAILABLE)

    assert "no model override" in text
    assert "default" in text
    assert "not name a specific model" in text


def test_lists_the_available_ids_and_how_to_switch() -> None:
    text = model_system_context("sonnet", _AVAILABLE)

    for model_id in _AVAILABLE:
        assert model_id in text
    assert "/model <id>" in text
    assert "model picker" in text


def test_empty_catalogue_still_produces_a_usable_note() -> None:
    text = model_system_context("sonnet", [])

    assert "`sonnet`" in text
    assert "none listed" in text


def test_stays_short_enough_to_ride_on_every_turn() -> None:
    # It is appended to every prompt; a few sentences, not a document.
    assert len(model_system_context(None, _AVAILABLE)) < 700
