"""Unit tests for the memory per-passage chunker ``_chunk_fact``.

These tests verify that ``_chunk_fact`` in ``sync.py`` splits a multi-section
topic document per heading section (so recall surfaces the relevant passage)
while preserving the old one-chunk parity for short, heading-less facts.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def _chunk_fact():
    from coffer.application.memory.sync import _chunk_fact as fn

    return fn


def test_multi_section_doc_yields_at_least_two_chunks(_chunk_fact) -> None:
    """A body with two ## sections → ≥ 2 chunks, each section isolated."""
    body = (
        "## Alpha section\n\n"
        "Use the alphawidget for the alpha flow.\n\n"
        "## Beta section\n\n"
        "Run the betagizmo for the beta flow."
    )
    chunks = _chunk_fact(body)

    assert len(chunks) >= 2, f"Expected ≥ 2 chunks, got {len(chunks)}: {chunks}"

    alpha_chunks = [c for c in chunks if "alphawidget" in c]
    beta_chunks = [c for c in chunks if "betagizmo" in c]

    assert alpha_chunks, "Expected a chunk containing 'alphawidget'"
    assert beta_chunks, "Expected a chunk containing 'betagizmo'"

    # No chunk may span both sections.
    for chunk in chunks:
        assert not ("alphawidget" in chunk and "betagizmo" in chunk), (
            f"A chunk spans both sections: {chunk!r}"
        )


def test_short_headingless_body_returns_single_chunk(_chunk_fact) -> None:
    """A short, heading-less body → exactly one chunk (parity with _one_chunk)."""
    body = "just a short fact"
    chunks = _chunk_fact(body)
    assert chunks == ["just a short fact"], f"Expected one-chunk result, got {chunks!r}"


def test_empty_string_returns_empty(_chunk_fact) -> None:
    chunks = _chunk_fact("")
    assert chunks == []


def test_whitespace_only_returns_empty(_chunk_fact) -> None:
    chunks = _chunk_fact("   \n  ")
    assert chunks == []
