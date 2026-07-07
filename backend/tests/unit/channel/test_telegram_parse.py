"""Unit tests for the pure Telegram inbound parsing helpers (Task 8): group
detection, @mention/reply addressing, and forwarded/quoted-reply framing."""

from coffer.infrastructure.channel.telegram_parse import (
    addressed_and_text,
    is_group,
    prepend_context,
)

BOT_ID = 999
BOT_USERNAME = "mybot"


def _message(**overrides):
    base = {
        "chat": {"id": 555, "type": "group"},
        "from": {"id": 4242, "first_name": "Yu", "username": "yu"},
    }
    base.update(overrides)
    return base


# -- is_group ------------------------------------------------------------


def test_is_group_true_for_group_and_supergroup():
    assert is_group(_message(chat={"id": 1, "type": "group"})) is True
    assert is_group(_message(chat={"id": 1, "type": "supergroup"})) is True


def test_is_group_false_for_private_chat():
    assert is_group(_message(chat={"id": 1, "type": "private"})) is False


# -- addressed_and_text: @mention entity ----------------------------------


def test_mention_entity_strips_bot_username_and_addresses():
    text = "@mybot run"
    message = _message(
        entities=[{"type": "mention", "offset": 0, "length": len("@mybot")}],
    )
    addressed, stripped = addressed_and_text(
        message, text, bot_id=BOT_ID, bot_username=BOT_USERNAME
    )
    assert addressed is True
    assert stripped == "run"


def test_mention_entity_is_case_insensitive():
    text = "@MyBot run"
    message = _message(
        entities=[{"type": "mention", "offset": 0, "length": len("@MyBot")}],
    )
    addressed, stripped = addressed_and_text(
        message, text, bot_id=BOT_ID, bot_username=BOT_USERNAME
    )
    assert addressed is True
    assert stripped == "run"


def test_multiple_mentions_only_bot_mention_is_stripped():
    text = "@someoneelse hey @mybot run"
    message = _message(
        entities=[
            {"type": "mention", "offset": 0, "length": len("@someoneelse")},
            {"type": "mention", "offset": 17, "length": len("@mybot")},
        ],
    )
    addressed, stripped = addressed_and_text(
        message, text, bot_id=BOT_ID, bot_username=BOT_USERNAME
    )
    assert addressed is True
    assert stripped == "@someoneelse hey run"


def test_mention_of_someone_else_does_not_address_bot():
    text = "@someoneelse run"
    message = _message(
        entities=[{"type": "mention", "offset": 0, "length": len("@someoneelse")}],
    )
    addressed, stripped = addressed_and_text(
        message, text, bot_id=BOT_ID, bot_username=BOT_USERNAME
    )
    assert addressed is False
    assert stripped == text


# -- addressed_and_text: text_mention entity (no @username needed) --------


def test_text_mention_entity_by_bot_id_addresses():
    text = "hey Bot run"
    message = _message(
        entities=[{"type": "text_mention", "offset": 4, "length": 3, "user": {"id": BOT_ID}}],
    )
    addressed, stripped = addressed_and_text(
        message, text, bot_id=BOT_ID, bot_username=BOT_USERNAME
    )
    assert addressed is True
    assert stripped == "hey run"


def test_text_mention_of_different_user_does_not_address():
    text = "hey Bot run"
    message = _message(
        entities=[{"type": "text_mention", "offset": 4, "length": 3, "user": {"id": 1}}],
    )
    addressed, stripped = addressed_and_text(
        message, text, bot_id=BOT_ID, bot_username=BOT_USERNAME
    )
    assert addressed is False
    assert stripped == text


# -- addressed_and_text: reply-to-bot --------------------------------------


def test_reply_to_bot_by_id_addresses_without_stripping_text():
    text = "yes please"
    message = _message(
        reply_to_message={"from": {"id": BOT_ID, "is_bot": True, "username": BOT_USERNAME}},
    )
    addressed, out = addressed_and_text(message, text, bot_id=BOT_ID, bot_username=BOT_USERNAME)
    assert addressed is True
    assert out == text


def test_reply_to_bot_by_username_addresses():
    text = "yes please"
    message = _message(
        reply_to_message={"from": {"id": 12345, "is_bot": True, "username": BOT_USERNAME}},
    )
    addressed, out = addressed_and_text(message, text, bot_id=BOT_ID, bot_username=BOT_USERNAME)
    assert addressed is True
    assert out == text


def test_reply_to_non_bot_does_not_address():
    text = "yes please"
    message = _message(
        reply_to_message={"from": {"id": 1, "is_bot": False, "username": "someoneelse"}},
    )
    addressed, out = addressed_and_text(message, text, bot_id=BOT_ID, bot_username=BOT_USERNAME)
    assert addressed is False
    assert out == text


def test_no_entities_or_reply_is_not_addressed():
    text = "just chatting"
    message = _message()
    addressed, out = addressed_and_text(message, text, bot_id=BOT_ID, bot_username=BOT_USERNAME)
    assert addressed is False
    assert out == text


def test_addressed_and_text_handles_none_bot_identity():
    # start() failed to resolve getMe: bot_id/bot_username both None — never
    # crash, just never match.
    text = "@mybot run"
    message = _message(entities=[{"type": "mention", "offset": 0, "length": 6}])
    addressed, out = addressed_and_text(message, text, bot_id=None, bot_username=None)
    assert addressed is False
    assert out == text


# -- prepend_context: forward -----------------------------------------------


def test_prepend_context_flattens_forward_origin_user():
    message = _message(
        forward_origin={"type": "user", "sender_user": {"first_name": "Alice"}},
    )
    out = prepend_context(message, "hello there")
    assert out.splitlines()[0] == "[Forwarded chat record]"
    assert "Alice: hello there" in out


def test_prepend_context_flattens_legacy_forward_from():
    message = _message(forward_from={"first_name": "Bob"})
    out = prepend_context(message, "old style forward")
    assert out.splitlines()[0] == "[Forwarded chat record]"
    assert "Bob: old style forward" in out


def test_prepend_context_no_forward_or_reply_is_unchanged():
    message = _message()
    assert prepend_context(message, "plain text") == "plain text"


# -- prepend_context: quoted reply -------------------------------------------


def test_prepend_context_quotes_reply_text():
    message = _message(
        reply_to_message={"from": {"first_name": "Sam"}, "text": "original message"},
    )
    out = prepend_context(message, "my reply")
    assert out.splitlines()[0] == "> Sam: original message"
    assert out.splitlines()[-1] == "my reply"


def test_prepend_context_combines_forward_and_reply():
    message = _message(
        forward_from={"first_name": "Bob"},
        reply_to_message={"from": {"first_name": "Sam"}, "text": "original message"},
    )
    out = prepend_context(message, "hi")
    lines = out.splitlines()
    assert lines[0] == "> Sam: original message"
    assert lines[1] == "[Forwarded chat record]"
    assert "Bob: hi" in out
