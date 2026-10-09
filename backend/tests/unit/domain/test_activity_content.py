"""A call's recorded content is redacted, then cut (domain.activity_content)."""

from __future__ import annotations

import json

import pytest

from coffer.domain.activity_content import (
    MASK,
    PART_LIMIT,
    capture,
    capture_parts,
    is_secret_field,
)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="secret-named fields and credential headers are masked whole"
)
def test_secret_fields_and_credential_headers_are_masked_whole() -> None:
    part = capture(
        {
            "password": "hunter2-long",
            "max_tokens": 64,
            "token_count": "12",
            "api_token": "abc",
            "headers": {"Authorization": "Bearer abc123def456", "Accept": "text/plain"},
        }
    )
    data = json.loads(part.text)
    assert data["password"] == MASK
    assert data["max_tokens"] == 64
    assert data["token_count"] == "12"
    assert data["api_token"] == MASK
    assert data["headers"] == {"Authorization": MASK, "Accept": "text/plain"}


def test_secret_field_names_match_the_last_word_only() -> None:
    assert is_secret_field("client_secret")
    assert is_secret_field("next_page_token")
    assert not is_secret_field("max_tokens")
    assert not is_secret_field("secretary")


def test_injected_values_are_masked_wherever_they_appear() -> None:
    part = capture(
        {"text": "key is sk-live-12345 here", "nested": ["sk-live-12345"]}, ["sk-live-12345"]
    )
    assert "sk-live-12345" not in part.text
    assert json.loads(part.text) == {"text": f"key is {MASK} here", "nested": [MASK]}


def test_a_value_shorter_than_four_characters_is_not_masked() -> None:
    assert json.loads(capture({"n": "on"}, ["on"]).text) == {"n": "on"}


@pytest.mark.acceptance(spec="mcp-gateway", scenario="content past 16 KB is cut and says so")
def test_a_part_past_16_kb_is_cut_and_keeps_its_size() -> None:
    parts = capture_parts({"arguments": {"q": "x"}, "result": {"text": "y" * 40_000}})
    assert parts is not None
    result, arguments = parts["result"], parts["arguments"]
    assert result["truncated"] is True
    assert len(result["text"].encode()) <= PART_LIMIT
    assert 40_000 < result["bytes"] < 41_000
    assert arguments["truncated"] is False and json.loads(arguments["text"]) == {"q": "x"}


def test_a_cut_never_splits_a_character() -> None:
    part = capture("中" * 10_000)
    assert part.truncated and len(part.text.encode()) <= PART_LIMIT
    part.text.encode().decode()  # still valid UTF-8


def test_nothing_to_record_is_none() -> None:
    assert capture_parts({"arguments": None}) is None
