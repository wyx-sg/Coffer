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
