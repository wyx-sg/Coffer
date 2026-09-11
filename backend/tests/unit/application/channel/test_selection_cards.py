"""The selection cards' pure rendering rules (FR-017/FR-018).

The model card is built from the agent's whole model catalogue — 29 entries for
``claude_code`` — but a card is a window onto that list, not the list: SeaTalk
refuses an over-long card outright (``code=102``) and the user is left with
nothing at all. So a long list is paged, and a short one is not paged at all.
"""

from __future__ import annotations

from coffer.application.channel.selection_cards import (
    CALLBACK_MAX_BYTES,
    MAX_CARD_BUTTONS,
    PAGE_SIZE,
    SelectionCard,
    agent_card,
    is_page_turn,
    model_card,
    parse_page_turn,
)


def _values(card: SelectionCard) -> list[str]:
    return [b.value for b in card.buttons]


def _choices(card: SelectionCard) -> list[str]:
    return [b.value for b in card.buttons if not is_page_turn(b.value)]


def _nav(card: SelectionCard) -> list[str]:
    return [b.value for b in card.buttons if is_page_turn(b.value)]


class TestShortListsAreNotPaged:
    def test_the_agent_card_carries_no_navigation_chrome(self):
        # /agent has two choices and must look exactly as it always has.
        card = agent_card(current="builtin", choices=[("builtin", "Builtin"), ("codex", "Codex")])

        assert _values(card) == ["agent:builtin", "agent:codex"]
        assert card.pages == 1
        assert "Page" not in card.text

    def test_a_catalogue_that_fits_is_shown_whole(self):
        card = model_card(current=None, picks=[f"m{i}" for i in range(MAX_CARD_BUTTONS)])

        assert _nav(card) == []
        assert len(card.buttons) == MAX_CARD_BUTTONS
        assert card.pages == 1

    def test_one_past_the_fit_starts_paging(self):
        card = model_card(current=None, picks=[f"m{i}" for i in range(MAX_CARD_BUTTONS + 1)])

        assert card.pages == 2
        assert _choices(card) == [f"model:m{i}" for i in range(PAGE_SIZE)]

    def test_the_short_catalogue_is_shown_whole(self):
        card = model_card(current=None, picks=["sonnet", "opus"])

        assert _values(card) == ["model:sonnet", "model:opus"]

    def test_the_current_model_is_not_duplicated(self):
        card = model_card(current="sonnet", picks=["sonnet", "opus", "haiku"])

        assert _values(card) == ["model:sonnet", "model:opus", "model:haiku"]

    def test_an_oversized_callback_is_still_dropped(self):
        card = model_card(current=None, picks=["ok", "x" * 100])

        assert _values(card) == ["model:ok"]


class TestPaging:
    def test_the_whole_catalogue_is_reachable_by_paging(self):
        picks = [f"m{i}" for i in range(29)]
        seen: list[str] = []
        page = 0
        while True:
            card = model_card(current=None, picks=picks, page=page)
            assert len(card.buttons) <= MAX_CARD_BUTTONS
            seen += _choices(card)
            if f"page:model:{page + 1}" not in _nav(card):
                break
            page += 1

        assert seen == [f"model:m{i}" for i in range(29)]

    def test_the_first_page_offers_next_but_no_prev(self):
        card = model_card(current=None, picks=[f"m{i}" for i in range(29)], page=0)

        assert _nav(card) == ["page:model:1"]

    def test_the_last_page_is_not_followed_by_an_empty_one(self):
        picks = [f"m{i}" for i in range(29)]
        last = model_card(current=None, picks=picks, page=0).pages - 1

        card = model_card(current=None, picks=picks, page=last)

        assert _nav(card) == [f"page:model:{last - 1}"]
        assert _choices(card)  # the last page is never empty either

    def test_a_page_past_the_end_is_clamped(self):
        # A stale Next tapped after the catalogue shrank must not show a void.
        picks = [f"m{i}" for i in range(29)]

        card = model_card(current=None, picks=picks, page=99)

        assert card.page == card.pages - 1
        assert _choices(card)

    def test_the_body_still_points_at_the_rest_of_the_catalogue(self):
        # (Angle brackets are safe on SeaTalk; live-probed.)
        card = model_card(current=None, picks=[f"m{i}" for i in range(29)])

        assert "/model <name>" in card.text

    def test_the_agent_card_pages_by_the_same_rule(self):
        # Pagination is not a model special case: the rule lives in one place.
        choices = [(f"a{i}", f"Agent {i}") for i in range(20)]

        card = agent_card(current="a0", choices=choices, page=1)

        assert _choices(card) == [f"agent:a{i}" for i in range(PAGE_SIZE, 2 * PAGE_SIZE)]
        assert _nav(card) == ["page:agent:0", "page:agent:2"]


class TestTheTickStaysHonest:
    def test_the_card_opens_on_the_page_holding_the_current_choice(self):
        picks = [f"m{i}" for i in range(29)]

        card = model_card(current="m20", picks=picks)

        assert card.page == 20 // PAGE_SIZE
        [ticked] = [b.value for b in card.buttons if b.label.endswith("✓")]
        assert ticked == "model:m20"

    def test_a_page_without_the_current_choice_carries_no_tick(self):
        card = model_card(current="m20", picks=[f"m{i}" for i in range(29)], page=0)

        assert [b for b in card.buttons if b.label.endswith("✓")] == []

    def test_an_off_page_current_choice_is_still_named_in_the_body(self):
        # The one thing a card must never do is look like nothing is selected.
        card = model_card(current="m20", picks=[f"m{i}" for i in range(29)], page=0)

        assert "Current model: m20" in card.text
        assert f"page {20 // PAGE_SIZE + 1}" in card.text

    def test_an_unpinned_model_says_so_on_every_page(self):
        card = model_card(current=None, picks=[f"m{i}" for i in range(29)], page=3)

        assert "Current model: (CLI default)" in card.text
        assert "✓" not in card.text

    def test_a_current_model_outside_the_catalogue_is_still_named(self):
        # `/model something-exotic` pins a name the catalogue never listed.
        card = model_card(current="exotic", picks=[f"m{i}" for i in range(29)])

        assert "Current model: exotic" in card.text
        assert [b for b in card.buttons if b.label.endswith("✓")] == []


class TestNavigationPayloads:
    def test_a_navigation_payload_fits_the_callback_budget(self):
        picks = [f"model-with-a-fairly-long-name-{i}" for i in range(200)]
        card = model_card(current=None, picks=picks, page=17)

        for button in card.buttons:
            if is_page_turn(button.value):
                assert len(button.value.encode("utf-8")) <= CALLBACK_MAX_BYTES
                assert len(button.value) < 20  # fixed-size, with room to spare

    def test_navigation_is_parsed_apart_from_a_choice(self):
        assert parse_page_turn("page:model:3") == ("model", 3)
        assert parse_page_turn("page:agent:0") == ("agent", 0)

    def test_a_choice_never_parses_as_navigation(self):
        # Including a model whose own id starts with the navigation word.
        for value in ("model:page", "model:page:3", "agent:builtin", "model:opus", ""):
            assert parse_page_turn(value) is None
            assert not is_page_turn(value)

    def test_a_malformed_navigation_payload_is_dropped_not_guessed(self):
        for value in ("page:", "page:model", "page:model:x", "page:ghost:1", "page:model:-1"):
            assert parse_page_turn(value) is None


def test_a_model_set_by_name_that_is_not_in_the_catalogue_gets_no_false_locator() -> None:
    """A model can be in effect without being on any page — an alias, or one
    newer than the installed catalogue. The footer must not then point at a
    page that has no tick on it either."""
    card = model_card(current="sonnet", picks=[f"m{i}" for i in range(20)])
    assert card.pages > 1
    assert "Current model: sonnet" in card.text
    assert "is on page" not in card.text
