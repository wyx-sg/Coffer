"""Unit tests for the organizer prompt's structured-output parser."""

from __future__ import annotations

import json

from coffer.application.memory.organizer_prompt import parse_organized_topic


def _raw(**kw: str) -> str:
    return json.dumps(kw)


def test_parse_lowercases_slug() -> None:
    """Slugs are filenames — a case variant must normalize so the LLM returning
    ``Deploy-Conventions`` for an on-disk ``deploy-conventions.md`` can't split one
    topic into two docs on a case-insensitive filesystem."""
    out = parse_organized_topic(
        _raw(
            topic_slug="Deploy-Conventions",
            topic_title="Deploy",
            topic_description="how we ship",
            markdown="# Deploy\n\nbody",
        )
    )
    assert out is not None
    assert out.topic_slug == "deploy-conventions"


def test_parse_strips_code_fence() -> None:
    out = parse_organized_topic(
        "```json\n"
        + _raw(topic_slug="t", topic_title="T", topic_description="d", markdown="x")
        + "\n```"
    )
    assert out is not None and out.topic_slug == "t"


def test_parse_rejects_malformed_unsafe_and_empty() -> None:
    # Non-JSON → None (item skipped, never written).
    assert parse_organized_topic("not json at all {oops") is None
    # A non-object → None.
    assert parse_organized_topic("[1, 2, 3]") is None
    # An unsafe slug (path traversal) → None.
    assert (
        parse_organized_topic(
            _raw(topic_slug="../etc", topic_title="T", topic_description="d", markdown="x")
        )
        is None
    )
    # An empty required field → None.
    assert (
        parse_organized_topic(
            _raw(topic_slug="ok", topic_title="", topic_description="d", markdown="x")
        )
        is None
    )


def test_parse_is_rule_true_with_empty_slug_and_title() -> None:
    """When is_rule=true, slug/title/description may be empty; only markdown required."""
    raw = json.dumps(
        {
            "is_rule": True,
            "topic_slug": "",
            "topic_title": "",
            "topic_description": "",
            "markdown": "Always run make verify before pushing.",
        }
    )
    out = parse_organized_topic(raw)
    assert out is not None
    assert out.is_rule is True
    assert out.markdown == "Always run make verify before pushing."


def test_parse_is_rule_false_still_requires_slug() -> None:
    """When is_rule=false, strict slug validation is enforced."""
    raw = json.dumps(
        {
            "is_rule": False,
            "topic_slug": "",
            "topic_title": "T",
            "topic_description": "d",
            "markdown": "body",
        }
    )
    assert parse_organized_topic(raw) is None


def test_parse_is_rule_missing_defaults_false() -> None:
    """is_rule defaults to False when absent; slug validation still enforced."""
    out = parse_organized_topic(
        _raw(topic_slug="slug-ok", topic_title="T", topic_description="d", markdown="body")
    )
    assert out is not None
    assert out.is_rule is False


def test_parse_is_rule_true_requires_markdown() -> None:
    """Even for a rule, markdown (the rule text) must be non-empty."""
    raw = json.dumps(
        {
            "is_rule": True,
            "topic_slug": "",
            "topic_title": "",
            "topic_description": "",
            "markdown": "",
        }
    )
    assert parse_organized_topic(raw) is None
