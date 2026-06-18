"""Unit tests for the pure managed-block text helpers (spec 004 item 1)."""

from __future__ import annotations

from coffer.domain.agent.managed_block import (
    extract_block,
    has_block,
    strip_block,
    upsert_block,
)

S = "<!-- x:start -->"
E = "<!-- x:end -->"


def test_upsert_appends_block_to_existing_content() -> None:
    out = upsert_block("# notes\n", "BODY", start_marker=S, end_marker=E)
    assert out == f"# notes\n\n{S}\nBODY\n{E}\n"
    # Content before the block is preserved verbatim.
    assert out.startswith("# notes\n")


def test_upsert_into_empty_text_has_no_leading_blank() -> None:
    assert upsert_block("", "BODY", start_marker=S, end_marker=E) == f"{S}\nBODY\n{E}\n"


def test_upsert_replaces_existing_block_in_place_and_keeps_surroundings() -> None:
    seeded = f"head\n\n{S}\nOLD\n{E}\n\ntail\n"
    out = upsert_block(seeded, "NEW", start_marker=S, end_marker=E)
    assert f"{S}\nNEW\n{E}" in out
    assert "OLD" not in out
    assert out.startswith("head\n")
    assert out.rstrip().endswith("tail")
    # Idempotent: re-upserting the same body is a fixed point.
    assert upsert_block(out, "NEW", start_marker=S, end_marker=E) == out


def test_upsert_rstrips_body() -> None:
    out = upsert_block("", "BODY\n\n", start_marker=S, end_marker=E)
    assert out == f"{S}\nBODY\n{E}\n"


def test_extract_returns_body_or_none() -> None:
    seeded = f"head\n{S}\nthe body\n{E}\ntail\n"
    assert extract_block(seeded, start_marker=S, end_marker=E) == "the body"
    assert extract_block("no markers here", start_marker=S, end_marker=E) is None


def test_extract_round_trips_with_upsert() -> None:
    out = upsert_block("x\n", "line1\nline2", start_marker=S, end_marker=E)
    assert extract_block(out, start_marker=S, end_marker=E) == "line1\nline2"


def test_strip_removes_only_the_block() -> None:
    seeded = f"head\n\n{S}\nBODY\n{E}\n\ntail\n"
    out = strip_block(seeded, start_marker=S, end_marker=E)
    assert S not in out and "BODY" not in out
    assert "head" in out and "tail" in out


def test_strip_absent_block_is_noop() -> None:
    assert strip_block("untouched\n", start_marker=S, end_marker=E) == "untouched\n"


def test_has_block() -> None:
    assert has_block(f"a\n{S}\nb\n{E}\n", start_marker=S) is True
    assert has_block("a\nb\n", start_marker=S) is False


def test_two_distinct_blocks_coexist() -> None:
    s2, e2 = "<!-- y:start -->", "<!-- y:end -->"
    text = upsert_block("", "X-BODY", start_marker=S, end_marker=E)
    text = upsert_block(text, "Y-BODY", start_marker=s2, end_marker=e2)
    # Both blocks present; stripping one leaves the other intact.
    assert extract_block(text, start_marker=S, end_marker=E) == "X-BODY"
    assert extract_block(text, start_marker=s2, end_marker=e2) == "Y-BODY"
    after = strip_block(text, start_marker=S, end_marker=E)
    assert extract_block(after, start_marker=s2, end_marker=e2) == "Y-BODY"
    assert S not in after
