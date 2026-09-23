"""The context ceiling and how it is priced (spec workflow "Keep a task's opening
context within budget")."""

from __future__ import annotations

from coffer.application.workflow.context_budget import (
    BRIEF_SHARE,
    INDEX_SHARE,
    NODE_CONTEXT_TOKEN_BUDGET,
    estimate_tokens,
    share_of,
)


def test_the_shares_divide_the_budget_exactly_once() -> None:
    # Floats, so compared at a tolerance rather than exactly: two shares that
    # sum to 0.9999999999 would still be two shares that divide the budget.
    assert abs(BRIEF_SHARE + INDEX_SHARE - 1.0) < 1e-9
    assert share_of(INDEX_SHARE) == int(NODE_CONTEXT_TOKEN_BUDGET * INDEX_SHARE)


def test_the_brief_takes_the_bulk_because_it_is_the_only_part_that_is_content() -> None:
    # The index is a list of names; the skill's instructions are a document. A
    # split that squeezed the document to make room for the names would be
    # squeezing the one part that says how the work is done.
    assert BRIEF_SHARE > INDEX_SHARE


def test_cjk_is_not_priced_as_ascii() -> None:
    # A budget that treated 2,000 Chinese characters as 500 tokens would be
    # silently unbounded for a vault whose owner writes in Chinese.
    assert estimate_tokens("账号服务的分库分表" * 100) > estimate_tokens("account service" * 100)


def test_whitespace_padding_does_not_inflate_the_estimate() -> None:
    assert estimate_tokens("hello world") == estimate_tokens("hello       world")
