"""Unit tests for the tool-choice parser (pure — no model server needed)."""

from __future__ import annotations

from evals.routing_eval import parse_tool_choice

VALID = [
    "search",
    "grep",
    "read",
    "list",
    "write",
    "delete",
    "list_skills",
    "load_skill",
]


def test_bare_name() -> None:
    assert parse_tool_choice("search", VALID) == "search"


def test_name_in_prose_and_backticks() -> None:
    assert parse_tool_choice("I would use `search` here.", VALID) == "search"


def test_name_with_label_and_newline() -> None:
    assert parse_tool_choice("Tool: write\n", VALID) == "write"


def test_case_insensitive() -> None:
    assert parse_tool_choice("LIST_SKILLS", VALID) == "list_skills"


def test_earliest_mention_wins() -> None:
    assert parse_tool_choice("first grep, maybe search", VALID) == "grep"


def test_longer_name_not_shadowed_by_prefix() -> None:
    # ``list`` is a strict prefix of ``list_skills`` since the knowledge tools
    # collapsed to bare verbs, so the longest-match tie-break is what keeps a
    # mention of ``list_skills`` from being read as ``list``.
    assert parse_tool_choice("use list_skills", VALID) == "list_skills"
    assert parse_tool_choice("use list", VALID) == "list"


def test_no_known_tool_returns_none() -> None:
    assert parse_tool_choice("I am not sure which tool to use.", VALID) is None
