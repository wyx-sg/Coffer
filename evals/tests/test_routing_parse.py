"""Unit tests for the tool-choice parser (pure — no model server needed)."""

from __future__ import annotations

from evals.routing_eval import parse_tool_choice

VALID = [
    "write",
    "recall",
    "diagnose",
    "search_tools",
    # Two synthetic names, present only so the prefix property below has an
    # example. The parser routes over whatever catalogue it is handed —
    # Coffer's own builtins today, an upstream server's tools tomorrow — so
    # that property must not depend on Coffer's roster happening to contain a
    # prefix pair. It did until 2026-09-17, when `list` and `list_skills` were
    # both deleted, and the test went with them.
    "fetch",
    "fetch_all",
]


def test_bare_name() -> None:
    assert parse_tool_choice("write", VALID) == "write"


def test_name_in_prose_and_backticks() -> None:
    assert parse_tool_choice("I would use `recall` here.", VALID) == "recall"


def test_name_with_label_and_newline() -> None:
    assert parse_tool_choice("Tool: write\n", VALID) == "write"


def test_case_insensitive() -> None:
    assert parse_tool_choice("SEARCH_TOOLS", VALID) == "search_tools"


def test_earliest_mention_wins() -> None:
    assert parse_tool_choice("first recall, maybe write", VALID) == "recall"


def test_longer_name_not_shadowed_by_prefix() -> None:
    # ``fetch`` is a strict prefix of ``fetch_all``, so the longest-match
    # tie-break is what keeps a mention of ``fetch_all`` from being read as
    # ``fetch``. Any aggregated catalogue can contain such a pair.
    assert parse_tool_choice("use fetch_all", VALID) == "fetch_all"
    assert parse_tool_choice("use fetch", VALID) == "fetch"


def test_no_known_tool_returns_none() -> None:
    assert parse_tool_choice("I am not sure which tool to use.", VALID) is None
