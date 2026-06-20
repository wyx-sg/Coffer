"""Unit tests for the boundary-aware markdown chunker. Pure — no I/O."""

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


def test_no_headings_single_short_chunk() -> None:
    chunks = chunk_markdown("just a paragraph", chunk_size=512, chunk_overlap=64)
    assert chunks == ["just a paragraph"]


def test_heading_awareness_chunks_stay_within_section() -> None:
    # Two sections, each large enough to split; no chunk straddles the boundary.
    sec_a = "# Alpha\n\n" + "\n\n".join(f"alpha paragraph {i} here" for i in range(40))
    sec_b = "# Beta\n\n" + "\n\n".join(f"beta paragraph {i} here" for i in range(40))
    chunks = chunk_markdown(sec_a + "\n\n" + sec_b, chunk_size=200, chunk_overlap=20)
    for c in chunks:
        # A chunk carrying alpha content never also carries beta content.
        assert not ("alpha" in c and "beta" in c)


def test_long_section_bounded_by_chunk_size() -> None:
    # A run of small prose blocks packs greedily into <= chunk_size chunks.
    body = "\n\n".join(f"sentence number {i} of the body." for i in range(60))
    chunks = chunk_markdown(body, chunk_size=200, chunk_overlap=40)
    assert len(chunks) >= 3
    assert all(len(c) <= 200 for c in chunks)


def test_greedy_block_packing_fills_chunks() -> None:
    # Three ~30-char blocks fit into one ~100-char chunk; greedy packing keeps
    # whole blocks together rather than emitting one chunk per block.
    blocks = ["block one content here", "block two content here", "block three text"]
    md = "\n\n".join(blocks)
    chunks = chunk_markdown(md, chunk_size=100, chunk_overlap=0)
    assert len(chunks) == 1
    assert "block one" in chunks[0]
    assert "block three" in chunks[0]


def test_packing_breaks_at_block_boundary_not_mid_block() -> None:
    # Two blocks that don't both fit: each chunk starts on a block boundary.
    a = "first block " * 8  # ~96 chars
    b = "second block " * 8
    md = a.strip() + "\n\n" + b.strip()
    chunks = chunk_markdown(md, chunk_size=120, chunk_overlap=0)
    assert len(chunks) == 2
    assert chunks[0].startswith("first block")
    assert chunks[1].startswith("second block")


def test_fenced_code_block_never_split() -> None:
    # A code fence that pushes a chunk over the limit must stay whole — no
    # orphaned opening/closing fence in any chunk.
    pre = "intro paragraph before the code"
    code = "```python\n" + "\n".join(f"line_{i} = {i}" for i in range(20)) + "\n```"
    md = pre + "\n\n" + code
    chunks = chunk_markdown(md, chunk_size=120, chunk_overlap=20)
    fence_chunk = next(c for c in chunks if "```python" in c)
    # The same chunk that opens the fence also closes it.
    assert fence_chunk.count("```") == 2
    assert "line_0 = 0" in fence_chunk
    assert "line_19 = 19" in fence_chunk
    # No other chunk carries a dangling fence.
    for c in chunks:
        assert c.count("```") % 2 == 0


def test_tilde_fence_never_split() -> None:
    code = "~~~\n" + "\n".join(f"data line {i}" for i in range(15)) + "\n~~~"
    md = "some prose here\n\n" + code
    chunks = chunk_markdown(md, chunk_size=80, chunk_overlap=10)
    fence_chunk = next(c for c in chunks if c.lstrip().startswith("~~~"))
    assert fence_chunk.count("~~~") == 2
    assert "data line 0" in fence_chunk
    assert "data line 14" in fence_chunk


def test_table_never_split() -> None:
    rows = "\n".join(f"| r{i}c1 | r{i}c2 |" for i in range(20))
    table = "| col a | col b |\n| --- | --- |\n" + rows
    md = "lead in paragraph\n\n" + table
    chunks = chunk_markdown(md, chunk_size=120, chunk_overlap=10)
    table_chunk = next(c for c in chunks if "col a" in c)
    # The header + delimiter + every body row land in the same chunk.
    assert "| --- | --- |" in table_chunk
    assert "r0c1" in table_chunk
    assert "r19c2" in table_chunk


def test_inline_pipe_in_prose_is_not_a_table() -> None:
    # A lone in-prose pipe (a shell `a | b`, a list item that contains one) must
    # NOT be mis-detected as a table and fragment the surrounding block.
    md = "- item alpha\n- item with a | pipe\n- item gamma"
    chunks = chunk_markdown(md, chunk_size=512, chunk_overlap=0)
    assert len(chunks) == 1
    # The list stays one tight block (no phantom-table split on the piped line).
    assert chunks[0].count("\n\n") == 0
    assert "item with a | pipe" in chunks[0]


def test_real_table_still_atomic_after_tightened_detection() -> None:
    # A genuine pipe-delimited table (leading/trailing pipes) is still atomic.
    table = "| a | b |\n| - | - |\n| 1 | 2 |\n| 3 | 4 |"
    chunks = chunk_markdown("intro\n\n" + table, chunk_size=200, chunk_overlap=0)
    table_chunk = next(c for c in chunks if "| a | b |" in c)
    assert "| - | - |" in table_chunk and "| 3 | 4 |" in table_chunk


def test_oversized_atomic_fence_stays_whole() -> None:
    # A single fence bigger than chunk_size is emitted whole (oversized) rather
    # than hard-split mid-structure.
    code = "```\n" + "\n".join(f"verylongcodeline_{i} = compute({i})" for i in range(40)) + "\n```"
    chunks = chunk_markdown(code, chunk_size=100, chunk_overlap=10)
    assert len(chunks) == 1
    assert len(chunks[0]) > 100  # oversized, intentionally
    assert chunks[0].count("```") == 2
    assert "verylongcodeline_39" in chunks[0]


def test_oversized_table_stays_whole() -> None:
    rows = "\n".join(f"| value_{i}_a | value_{i}_b | value_{i}_c |" for i in range(30))
    table = "| a | b | c |\n| - | - | - |\n" + rows
    chunks = chunk_markdown(table, chunk_size=100, chunk_overlap=10)
    assert len(chunks) == 1
    assert len(chunks[0]) > 100
    assert "value_0_a" in chunks[0]
    assert "value_29_c" in chunks[0]


def test_overlap_reincludes_trailing_context() -> None:
    # With overlap, the chunk that follows a flush re-includes a tail of the
    # previous chunk so adjacent chunks share context.
    a = "alpha sentence one. alpha sentence two. alpha sentence three."
    b = "beta block content here."
    md = a + "\n\n" + b
    no_overlap = chunk_markdown(md, chunk_size=70, chunk_overlap=0)
    with_overlap = chunk_markdown(md, chunk_size=70, chunk_overlap=30)
    assert len(no_overlap) == 2
    assert len(with_overlap) == 2
    # The overlapped second chunk re-includes a trailing sentence from the first.
    assert "alpha sentence three." in with_overlap[1]
    assert with_overlap[1].endswith(b)
    # Without overlap the second chunk is the bare beta block.
    assert no_overlap[1] == b


def test_oversized_prose_splits_at_sentence_boundary() -> None:
    # A single paragraph (no blank lines) larger than chunk_size splits at
    # sentence ends, not mid-word.
    para = " ".join(f"This is sentence {i} of a very long paragraph." for i in range(20))
    chunks = chunk_markdown(para, chunk_size=120, chunk_overlap=20)
    assert len(chunks) >= 2
    # Each non-final chunk ends at a sentence terminator (period), not mid-word.
    for c in chunks[:-1]:
        assert c.rstrip().endswith(".")


def test_cjk_sentence_boundary_split() -> None:
    # CJK full-stops are honored as sentence boundaries for oversized prose.
    para = "".join(f"这是第{i}个句子内容在这里。" for i in range(20))
    chunks = chunk_markdown(para, chunk_size=60, chunk_overlap=10)
    assert len(chunks) >= 2
    for c in chunks[:-1]:
        assert c.rstrip().endswith("。")
