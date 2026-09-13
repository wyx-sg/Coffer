"""Unit tests for the pure retrieval ranking (domain/knowledge/retrieval.py)."""

from __future__ import annotations

from coffer.domain.knowledge.retrieval import (
    DEFAULT_MAX_CHARS,
    DEFAULT_MIN_SCORE,
    DEFAULT_TOP_K,
    IndexedSection,
    Section,
    cosine,
    rank,
    split_sections,
)

# ---------------------------------------------------------------------------
# split_sections
# ---------------------------------------------------------------------------


def test_no_headings_yields_one_section_with_empty_heading() -> None:
    body = "Just some prose.\nA second line."
    sections = split_sections(body)
    assert sections == (Section(heading="", text=body, start_line=1),)


def test_several_headings_split_into_separate_sections() -> None:
    body = "# Intro\nIntro body.\n\n## Details\nDetails body.\n\n## More\nMore body."
    sections = split_sections(body)
    assert [s.heading for s in sections] == ["Intro", "Details", "More"]
    assert sections[0].text == "# Intro\nIntro body."
    assert sections[1].text == "## Details\nDetails body."
    assert sections[2].text == "## More\nMore body."


def test_preamble_before_first_heading_is_its_own_section() -> None:
    body = "Lead-in text.\n\n# First Heading\nBody."
    sections = split_sections(body)
    assert sections[0].heading == ""
    assert sections[0].text == "Lead-in text."
    assert sections[1].heading == "First Heading"


def test_section_longer_than_max_chars_is_split_on_paragraph_boundaries() -> None:
    para_a = "A" * 40
    para_b = "B" * 40
    para_c = "C" * 40
    body = f"# Heading\n{para_a}\n\n{para_b}\n\n{para_c}"
    sections = split_sections(body, max_chars=60)
    assert len(sections) > 1
    for s in sections:
        assert len(s.text) <= 60
        assert s.heading == "Heading"
    # No paragraph's letters were split mid-word: each run of A/B/C appears
    # whole in exactly one piece.
    joined = [s.text for s in sections]
    assert any(para_a in t for t in joined)
    assert any(para_b in t for t in joined)
    assert any(para_c in t for t in joined)


def test_single_paragraph_bigger_than_max_chars_is_kept_whole_not_truncated() -> None:
    huge_word_run = "word " * 50  # one paragraph, no blank line inside it
    body = f"# Heading\n{huge_word_run.strip()}"
    sections = split_sections(body, max_chars=10)
    # Can't split without risking a mid-word cut, so it's emitted whole even
    # though it exceeds max_chars.
    assert len(sections) == 1
    assert huge_word_run.strip() in sections[0].text


def test_whitespace_only_section_is_skipped() -> None:
    body = "\n\n   \n\n# Real Heading\nReal body."
    sections = split_sections(body)
    assert len(sections) == 1
    assert sections[0].heading == "Real Heading"


def test_heading_with_no_body_is_kept_not_whitespace_only() -> None:
    body = "# First\n# Second\nSecond body."
    sections = split_sections(body)
    assert [s.heading for s in sections] == ["First", "Second"]
    assert sections[0].text == "# First"


def test_empty_body_yields_no_sections() -> None:
    assert split_sections("") == ()
    assert split_sections("   \n\n  \n") == ()


def test_cjk_content_is_split_and_headed_correctly() -> None:
    body = "# 账号服务\n这是账号服务的说明文档。\n\n## 网关\n网关负责路由请求。"
    sections = split_sections(body)
    assert sections[0].heading == "账号服务"
    assert "这是账号服务的说明文档。" in sections[0].text
    assert sections[1].heading == "网关"
    assert "网关负责路由请求。" in sections[1].text


def test_start_line_correctness_across_headings_and_preamble() -> None:
    body = "Lead line 1.\nLead line 2.\n\n# Heading A\nBody A.\n\n## Heading B\nBody B."
    sections = split_sections(body)
    # Line numbers are 1-based.
    assert sections[0].start_line == 1  # "Lead line 1."
    heading_a_line = body.splitlines().index("# Heading A") + 1
    heading_b_line = body.splitlines().index("## Heading B") + 1
    assert sections[1].start_line == heading_a_line
    assert sections[2].start_line == heading_b_line


def test_start_line_of_split_piece_advances_past_first_piece() -> None:
    para_a = "A" * 40
    para_b = "B" * 40
    body = f"# Heading\n{para_a}\n\n{para_b}"
    sections = split_sections(body, max_chars=50)
    assert len(sections) == 2
    assert sections[0].start_line == 1
    # The second piece starts at the blank-line-separated paragraph's own line.
    expected_second_line = body.splitlines().index(para_b) + 1
    assert sections[1].start_line == expected_second_line


def test_default_max_chars_constant_used_when_unspecified() -> None:
    assert DEFAULT_MAX_CHARS == 2000
    # Many short paragraphs (not one giant one) so the default cap actually
    # has room to pack-and-split rather than being forced to keep one
    # oversized paragraph whole.
    paragraphs = "\n\n".join(f"Paragraph {i} of prose." for i in range(400))
    body = f"# H\n{paragraphs}"
    for s in split_sections(body):
        assert len(s.text) <= DEFAULT_MAX_CHARS


# ---------------------------------------------------------------------------
# cosine
# ---------------------------------------------------------------------------


def test_cosine_identical_vectors_is_one() -> None:
    assert cosine((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)) == 1.0


def test_cosine_orthogonal_vectors_is_zero() -> None:
    assert cosine((1.0, 0.0), (0.0, 1.0)) == 0.0


def test_cosine_opposite_vectors_is_negative_one() -> None:
    assert cosine((1.0, 0.0), (-1.0, 0.0)) == -1.0


def test_cosine_zero_magnitude_vector_does_not_divide_by_zero() -> None:
    assert cosine((0.0, 0.0), (1.0, 2.0)) == 0.0
    assert cosine((1.0, 2.0), (0.0, 0.0)) == 0.0
    assert cosine((0.0, 0.0), (0.0, 0.0)) == 0.0


def test_cosine_mismatched_dimensions_returns_zero_not_raise() -> None:
    assert cosine((1.0, 2.0), (1.0, 2.0, 3.0)) == 0.0


def test_cosine_empty_vectors_returns_zero() -> None:
    assert cosine((), (1.0, 2.0)) == 0.0
    assert cosine((1.0, 2.0), ()) == 0.0
    assert cosine((), ()) == 0.0


# ---------------------------------------------------------------------------
# rank
# ---------------------------------------------------------------------------


def _section(
    path: str, vector: tuple[float, ...], heading: str = "", line: int = 1
) -> IndexedSection:
    return IndexedSection(path=path, heading=heading, start_line=line, vector=vector)


def test_rank_orders_by_score_descending() -> None:
    query = (1.0, 0.0)
    sections = [
        _section("low.md", (0.1, 0.995)),
        _section("high.md", (1.0, 0.0)),
        _section("mid.md", (0.8, 0.2)),
    ]
    hits = rank(query, sections, top_k=10, min_score=-1.0)
    assert [h.path for h in hits] == ["high.md", "mid.md", "low.md"]
    assert hits[0].score >= hits[1].score >= hits[2].score


def test_rank_one_hit_per_file_keeps_best_section() -> None:
    query = (1.0, 0.0)
    sections = [
        _section("doc.md", (0.1, 1.0), heading="weak", line=5),
        _section("doc.md", (1.0, 0.0), heading="strong", line=50),
        _section("doc.md", (0.5, 0.5), heading="mid", line=20),
    ]
    hits = rank(query, sections, top_k=10, min_score=-1.0)
    assert len(hits) == 1
    assert hits[0].path == "doc.md"
    assert hits[0].heading == "strong"
    assert hits[0].start_line == 50


def test_rank_long_document_cannot_crowd_out_other_files() -> None:
    query = (1.0, 0.0)
    # A single file contributes many strong-scoring sections; it must still
    # only occupy one slot in the ranked output.
    sections = [_section("big.md", (1.0, 0.0), line=i) for i in range(1, 20)]
    sections.append(_section("small.md", (0.9, 0.1)))
    hits = rank(query, sections, top_k=5, min_score=-1.0)
    paths = [h.path for h in hits]
    assert paths.count("big.md") == 1
    assert "small.md" in paths


def test_rank_respects_top_k() -> None:
    query = (1.0, 0.0)
    sections = [_section(f"f{i}.md", (1.0, 0.0)) for i in range(5)]
    hits = rank(query, sections, top_k=2, min_score=-1.0)
    assert len(hits) == 2


def test_rank_top_k_zero_or_negative_returns_empty() -> None:
    query = (1.0, 0.0)
    sections = [_section("a.md", (1.0, 0.0))]
    assert rank(query, sections, top_k=0, min_score=-1.0) == ()
    assert rank(query, sections, top_k=-1, min_score=-1.0) == ()


def test_rank_min_score_drops_weak_matches() -> None:
    query = (1.0, 0.0)
    sections = [
        _section("strong.md", (1.0, 0.0)),
        _section("weak.md", (0.01, 0.99999)),
    ]
    hits = rank(query, sections, top_k=10, min_score=0.5)
    assert [h.path for h in hits] == ["strong.md"]


def test_rank_empty_query_vector_returns_empty() -> None:
    sections = [_section("a.md", (1.0, 0.0))]
    assert rank((), sections, top_k=10, min_score=-1.0) == ()


def test_rank_zero_magnitude_section_vector_is_excluded_not_crashing() -> None:
    query = (1.0, 0.0)
    sections = [_section("zero.md", (0.0, 0.0)), _section("real.md", (1.0, 0.0))]
    # A zero-magnitude vector scores exactly 0.0 (cosine's defensive fallback,
    # never a crash); a positive min_score is what filters it out of a ranked
    # result, same as it would filter any other non-match.
    hits = rank(query, sections, top_k=10, min_score=0.01)
    assert [h.path for h in hits] == ["real.md"]


def test_rank_mismatched_dimension_section_is_excluded_not_crashing() -> None:
    query = (1.0, 0.0, 0.0)
    sections = [_section("odd.md", (1.0, 0.0)), _section("real.md", (1.0, 0.0, 0.0))]
    # A dimension-mismatched vector also scores 0.0 rather than raising; a
    # positive min_score filters it out just like any other non-match.
    hits = rank(query, sections, top_k=10, min_score=0.01)
    assert [h.path for h in hits] == ["real.md"]


def test_rank_ties_break_on_path_for_determinism() -> None:
    query = (1.0, 0.0)
    sections = [_section("b.md", (1.0, 0.0)), _section("a.md", (1.0, 0.0))]
    hits = rank(query, sections, top_k=10, min_score=-1.0)
    assert [h.path for h in hits] == ["a.md", "b.md"]


def test_rank_uses_default_constants_when_unspecified() -> None:
    assert DEFAULT_TOP_K == 8
    assert DEFAULT_MIN_SCORE == 0.2
    sections = [_section(f"f{i}.md", (1.0, 0.0)) for i in range(20)]
    hits = rank((1.0, 0.0), sections)
    assert len(hits) == DEFAULT_TOP_K
