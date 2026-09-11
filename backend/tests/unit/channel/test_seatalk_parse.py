"""Unit tests for the pure SeaTalk parsing helpers: FR-035 mention gating and
the interactive-card element limits SeaTalk documents."""

from coffer.domain.channel.envelopes import ChoiceButton
from coffer.infrastructure.channel.seatalk_parse import (
    CARD_DESCRIPTION_MAX_CHARS,
    CARD_TITLE_MAX_CHARS,
    interactive_card,
    mentions_others,
)


def test_mentions_others_false_for_bot_only_single_mention():
    # new_mentioned_message_received_from_group_chat only fires when the bot is
    # mentioned, so a single username is the bot alone.
    assert mentions_others([{"username": "coffer-bot"}]) is False


def test_mentions_others_true_for_two_distinct_usernames():
    assert mentions_others([{"username": "coffer-bot"}, {"username": "alice"}]) is True


def test_mentions_others_dedups_repeated_bot_mentions():
    # The same user @mentioned twice is still one distinct username, not "others".
    assert mentions_others([{"username": "coffer-bot"}, {"username": "coffer-bot"}]) is False


def test_mentions_others_handles_empty_or_none_list():
    assert mentions_others(None) is False
    assert mentions_others([]) is False


def test_mentions_others_ignores_entries_without_a_username():
    assert mentions_others([{"username": "coffer-bot"}, {"seatalk_id": "x"}, {}]) is False


# -- interactive_card element limits ------------------------------------------


def _elements(card):
    return card["interactive_message"]["elements"]


def _of_type(card, element_type):
    return [e for e in _elements(card) if e["element_type"] == element_type]


def test_interactive_card_omits_the_title_element_when_the_title_is_empty():
    # A blank title element would still occupy one of the 3 allowed title slots
    # and render as an empty line above the body.
    card = interactive_card("body", [])
    assert _of_type(card, "title") == []
    assert card["tag"] == "interactive_message"


def test_interactive_card_truncates_the_title_at_120_characters():
    # SeaTalk refuses the whole card when title.text exceeds 120 characters, so
    # a long title must cost the title's tail, never the card.
    [title] = _of_type(interactive_card("body", [], title="T" * 500), "title")
    assert len(title["title"]["text"]) == CARD_TITLE_MAX_CHARS == 120
    assert title["title"]["text"].endswith("…")


def test_interactive_card_keeps_a_title_that_already_fits_verbatim():
    [title] = _of_type(interactive_card("body", [], title="Model"), "title")
    assert title["title"]["text"] == "Model"


def test_interactive_card_truncates_the_description_at_1000_characters():
    [desc] = _of_type(interactive_card("B" * 4000, []), "description")
    assert len(desc["description"]["text"]) == CARD_DESCRIPTION_MAX_CHARS == 1000
    assert desc["description"]["text"].endswith("…")
    assert desc["description"]["format"] == 1  # markdown body survives the clamp


def test_interactive_card_groups_two_buttons_into_one_row():
    # Two buttons fit one button_group; no bare "button" element is ever emitted.
    card = interactive_card(
        "body", [ChoiceButton(label="A", value="a"), ChoiceButton(label="B", value="b")]
    )
    [group] = _of_type(card, "button_group")
    assert _of_type(card, "button") == []
    assert group["button_group"] == [
        {"button_type": "callback", "text": "A", "value": "a"},
        {"button_type": "callback", "text": "B", "value": "b"},
    ]


def test_interactive_card_splits_six_buttons_into_two_rows_of_three():
    # The documented ceiling is 5 bare buttons but 3 button_group elements of 3:
    # grouping is what makes six choices legal at all.
    buttons = [ChoiceButton(label=f"L{i}", value=f"v{i}") for i in range(6)]
    groups = _of_type(interactive_card("body", buttons), "button_group")
    assert [[b["value"] for b in g["button_group"]] for g in groups] == [
        ["v0", "v1", "v2"],
        ["v3", "v4", "v5"],
    ]


def test_interactive_card_leaves_a_short_last_row_short():
    # 4 buttons are 3 + 1, not padded out — a row holds 1 to 3 buttons.
    buttons = [ChoiceButton(label=f"L{i}", value=f"v{i}") for i in range(4)]
    groups = _of_type(interactive_card("body", buttons), "button_group")
    assert [len(g["button_group"]) for g in groups] == [3, 1]


def test_interactive_card_emits_no_button_element_without_buttons():
    # A plain card is title + description only; an empty button_group would be
    # below the documented minimum of one button per group.
    card = interactive_card("body", [], title="Agent")
    assert [e["element_type"] for e in _elements(card)] == ["title", "description"]


def test_interactive_card_carries_no_language_wrapper():
    # Multi-language card content is a Send Service Notice API feature; a bot
    # card wrapped in "default"/language codes is refused.
    card = interactive_card("body", [ChoiceButton(label="A", value="a")], title="T")
    assert set(card["interactive_message"]) == {"elements"}
