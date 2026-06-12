"""Unit tests for the markdown-aware chunker. Pure — no I/O."""

from coffer.infrastructure.knowledge.chunking import chunk_markdown


def test_empty_yields_no_chunks() -> None:
    assert chunk_markdown("", chunk_size=512, chunk_overlap=64) == []
    assert chunk_markdown("   \n\n ", chunk_size=512, chunk_overlap=64) == []


def test_splits_on_headings() -> None:
    md = "# Intro\nalpha\n\n# Body\nbeta\n\n## Sub\ngamma"
    chunks = chunk_markdown(md, chunk_size=512, chunk_overlap=0)
    assert len(chunks) == 3
    assert chunks[0].startswith("# Intro")
    assert chunks[1].startswith("# Body")
    assert chunks[2].startswith("## Sub")


def test_preamble_before_first_heading_kept() -> None:
    md = "leading text\n\n# Heading\nbody"
    chunks = chunk_markdown(md, chunk_size=512, chunk_overlap=0)
    assert chunks[0] == "leading text"
    assert chunks[1].startswith("# Heading")


def test_long_section_bounded_by_chunk_size_with_overlap() -> None:
    body = "x" * 1000
    chunks = chunk_markdown(body, chunk_size=400, chunk_overlap=50)
    assert len(chunks) >= 3
    assert all(len(c) <= 400 for c in chunks)
    # Overlap: consecutive windows step by chunk_size - overlap = 350.
    assert chunks[1].startswith("x")


def test_no_headings_single_short_chunk() -> None:
    chunks = chunk_markdown("just a paragraph", chunk_size=512, chunk_overlap=64)
    assert chunks == ["just a paragraph"]
