"""Unit tests for the tool-choice parser (pure — no model server needed)."""

from __future__ import annotations

from evals.routing_eval import parse_tool_choice

VALID = [
    "search_knowledge",
    "grep_knowledge",
    "recall",
    "remember",
    "list_skills",
    "load_skill",
    "list_knowledge_bases",
    "read_document",
]


def test_bare_name() -> None:
    assert parse_tool_choice("search_knowledge", VALID) == "search_knowledge"


def test_name_in_prose_and_backticks() -> None:
    assert parse_tool_choice("I would use `recall` here.", VALID) == "recall"


def test_name_with_label_and_newline() -> None:
    assert parse_tool_choice("Tool: remember\n", VALID) == "remember"


def test_case_insensitive() -> None:
    assert parse_tool_choice("LIST_SKILLS", VALID) == "list_skills"


def test_earliest_mention_wins() -> None:
    assert (
        parse_tool_choice("first search_knowledge, maybe recall", VALID)
        == "search_knowledge"
    )


def test_longer_name_not_shadowed_by_prefix() -> None:
    # only list_knowledge_bases is present; the shorter list_* names must not match
    assert (
        parse_tool_choice("use list_knowledge_bases", VALID) == "list_knowledge_bases"
    )


def test_no_known_tool_returns_none() -> None:
    assert parse_tool_choice("I am not sure which tool to use.", VALID) is None
