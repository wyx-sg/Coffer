"""Unit tests for the pure token estimator (domain/memory/budget.py)."""

from __future__ import annotations

from coffer.domain.memory.budget import estimate_tokens


def test_empty_string_is_zero_tokens() -> None:
    assert estimate_tokens("") == 0


def test_whitespace_only_is_zero_tokens() -> None:
    assert estimate_tokens("   \n\t  ") == 0


def test_ascii_prose_is_roughly_four_chars_per_token() -> None:
    text = "a" * 40  # 40 ascii chars
    assert estimate_tokens(text) == 10


def test_cjk_text_costs_far_more_per_character_than_ascii() -> None:
    """The whole reason this estimator exists: CJK must not be priced like
    ASCII, or a Chinese digest would look far cheaper than it really is."""
    ascii_text = "a" * 20
    cjk_text = "文" * 20
    assert estimate_tokens(cjk_text) > estimate_tokens(ascii_text)


def test_cjk_is_close_to_one_token_per_character() -> None:
    text = "文" * 12
    assert estimate_tokens(text) == 12


def test_mixed_ascii_and_cjk_sums_both_buckets() -> None:
    ascii_only = estimate_tokens("a" * 40)
    cjk_only = estimate_tokens("文" * 12)
    mixed = estimate_tokens("a" * 40 + "文" * 12)
    assert mixed == ascii_only + cjk_only


def test_result_is_a_non_negative_integer() -> None:
    for text in ("", "x", "文" * 3, "café", "🙂🙂🙂"):
        result = estimate_tokens(text)
        assert isinstance(result, int)
        assert result >= 0


def test_deterministic_for_the_same_input() -> None:
    text = "The developer prefers worktree-based development. 开发者偏好使用 worktree。"
    assert estimate_tokens(text) == estimate_tokens(text)


def test_longer_text_never_costs_fewer_tokens() -> None:
    short = "The developer's pip mirror is unreachable."
    longer = short + " Use public PyPI with Python 3.12 instead."
    assert estimate_tokens(longer) >= estimate_tokens(short)


def test_other_unicode_is_priced_between_ascii_and_cjk() -> None:
    """Accented Latin/Cyrillic/symbols land in the third bucket — cheaper per
    character than CJK, more expensive than plain ASCII."""
    ascii_cost = estimate_tokens("a" * 20)
    other_cost = estimate_tokens("é" * 20)
    cjk_cost = estimate_tokens("文" * 20)
    assert ascii_cost < other_cost < cjk_cost
