"""Capability latching (FR-059) and rich-markdown normalisation (FR-061)."""

from __future__ import annotations

import pytest

from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel.telegram_features import Feature, FeatureSet, is_unsupported
from coffer.infrastructure.channel.telegram_rich import normalize_rich_markdown


def _refusal(description: str, status: int) -> ChannelSendFailed:
    return ChannelSendFailed("tg", description, api_rejected=True, status=status)


# -- is_unsupported -----------------------------------------------------------


def test_a_missing_method_is_unsupported() -> None:
    assert is_unsupported(_refusal("sendRichMessage: Not Found: method not found", 404)) is True


def test_an_unknown_parameter_is_unsupported() -> None:
    assert is_unsupported(_refusal("sendMessage: unknown parameter can_stop", 400)) is True


def test_a_malformed_message_is_not_unsupported() -> None:
    # The single most important distinction here: one bad table must not
    # disable rich messages for the whole process.
    assert is_unsupported(_refusal("sendRichMessage: can't parse entities", 400)) is False


def test_a_rate_limit_is_not_unsupported() -> None:
    assert is_unsupported(_refusal("Too Many Requests: retry after 30", 429)) is False


def test_a_transport_error_is_not_unsupported() -> None:
    # A connection that dropped says nothing about what the server can do.
    assert is_unsupported(ChannelSendFailed("tg", "ConnectTimeout")) is False


def test_an_unrelated_exception_is_not_unsupported() -> None:
    assert is_unsupported(RuntimeError("boom")) is False


# -- Feature ------------------------------------------------------------------


def test_a_feature_starts_available() -> None:
    assert Feature("rich").available is True


def test_an_unsupported_refusal_latches_the_feature_off() -> None:
    feature = Feature("rich")
    assert feature.note_failure("tg", _refusal("method not found", 404)) is True
    assert feature.available is False


def test_an_ordinary_refusal_leaves_the_feature_on() -> None:
    feature = Feature("rich")
    assert feature.note_failure("tg", _refusal("can't parse entities", 400)) is False
    assert feature.available is True


def test_the_latch_is_one_way() -> None:
    feature = Feature("rich")
    feature.note_failure("tg", _refusal("method not found", 404))
    feature.note_failure("tg", _refusal("can't parse entities", 400))
    assert feature.available is False


def test_each_feature_latches_independently() -> None:
    features = FeatureSet()
    features.rich_messages.note_failure("tg", _refusal("method not found", 404))
    assert features.rich_messages.available is False
    assert features.message_drafts.available is True
    assert features.ephemeral_messages.available is True


def test_two_adapters_do_not_share_a_latch() -> None:
    # Two channels may point at different Bot API servers.
    first, second = FeatureSet(), FeatureSet()
    first.rich_messages.note_failure("tg", _refusal("method not found", 404))
    assert second.rich_messages.available is True


# -- normalize_rich_markdown --------------------------------------------------


def test_ordinary_markdown_passes_through_untouched() -> None:
    body = "## Heading\n\n- one\n- two\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n> quote"
    assert normalize_rich_markdown(body) == body


def test_a_shell_variable_is_escaped_outside_code() -> None:
    # Unescaped, "$HOME ... $PATH" reads as a formula and swallows the line.
    assert normalize_rich_markdown("set $HOME then $PATH") == r"set \$HOME then \$PATH"


def test_a_dollar_inside_an_inline_code_span_is_left_alone() -> None:
    assert normalize_rich_markdown("run `echo $HOME`") == "run `echo $HOME`"


def test_a_dollar_inside_a_fence_is_left_alone() -> None:
    body = "before $X\n\n```sh\necho $HOME\n```\n\nafter $Y"
    assert normalize_rich_markdown(body) == "before \\$X\n\n```sh\necho $HOME\n```\n\nafter \\$Y"


@pytest.mark.parametrize("body", ["", "plain text", "no dollars here"])
def test_text_without_dollars_is_returned_as_is(body: str) -> None:
    assert normalize_rich_markdown(body) == body
