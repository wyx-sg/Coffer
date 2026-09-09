"""Unit tests for the pure SeaTalk parsing helpers (FR-035 mention gating)."""

from coffer.infrastructure.channel.seatalk_parse import mentions_others


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
