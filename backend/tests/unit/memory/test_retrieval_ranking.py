"""The lexical ranker behind prompt-time retrieval (spec memory "Retrieve the
notes a prompt names"): what counts as a word, which prompts are worth
ranking, how BM25 orders a corpus, and how ``select`` applies the floor, the
top-k and the session's already-delivered notes."""

from __future__ import annotations

import pytest

from coffer.domain.memory import retrieval as r
from coffer.domain.memory.retrieval import Bm25Index, Ranked, is_substantive, select, tokens
from tests.unit.memory._delivery_corpus import filler_notes


def _doc(n) -> str:  # type: ignore[no-untyped-def]
    return " ".join((n.title, n.description, n.body))


# --- tokens ------------------------------------------------------------------


def test_tokens_lowercase_and_drop_stopwords_and_one_letter_fragments() -> None:
    assert tokens("Run THE make verify a b") == ["make", "verify"]


def test_tokens_keep_dotted_and_hyphenated_words_whole() -> None:
    assert tokens("uv.lock make-verify") == ["uv.lock", "make-verify"]


def test_tokens_turn_cjk_text_into_overlapping_bigrams() -> None:
    assert tokens("运行测试") == ["运行", "行测", "测试"]
    # One CJK character alone has no bigram.
    assert tokens("好") == []


def test_tokens_of_mixed_text_carry_both_halves() -> None:
    out = tokens("make verify 失败了")
    assert out[:2] == ["make", "verify"]
    assert {"失败", "败了"} <= set(out)


# --- is_substantive -------------------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    ["继续", "ok", "OK.", "  continue  ", "thanks!", "fix bug", "keep going", "", "   "],
)
def test_nudges_and_short_prompts_are_not_substantive(prompt: str) -> None:
    assert is_substantive(prompt) is False


@pytest.mark.parametrize(
    "prompt",
    ["fix the bug", "why does make verify fail", "运行测试", "帮我看看这个错误"],
)
def test_three_words_or_a_chinese_request_of_three_characters_is_substantive(
    prompt: str,
) -> None:
    assert is_substantive(prompt) is True


def test_the_minimum_is_three_words() -> None:
    assert r.MIN_PROMPT_WORDS == 3
    assert not is_substantive("two words")
    assert is_substantive("now three words")


# --- Bm25Index ------------------------------------------------------------------


def test_the_note_sharing_the_rare_terms_ranks_first() -> None:
    docs = [(n.slug, _doc(n)) for n in filler_notes("p")]
    docs.append(("node", "make verify fails with undici AbortSignal under Node 22"))
    docs.append(("vitest", "frontend vitest runs under node 20 in CI"))
    ranked = Bm25Index(docs).rank("why does make verify fail with undici under node")
    assert [x.key for x in ranked][:2] == ["node", "vitest"]
    assert ranked[0].score > ranked[1].score > 0
    # A document sharing no term is not ranked at all.
    assert all(x.key in ("node", "vitest") for x in ranked)


def test_rank_prefers_the_higher_term_frequency_among_equals() -> None:
    docs = [(n.slug, _doc(n)) for n in filler_notes("p")]
    docs += [("once", "gradle build cache"), ("twice", "gradle gradle build cache")]
    ranked = Bm25Index(docs).rank("gradle")
    assert [x.key for x in ranked] == ["twice", "once"]


def test_ties_are_broken_by_key() -> None:
    docs = [(n.slug, _doc(n)) for n in filler_notes("p")]
    docs += [("b-note", "terraform plan drift"), ("a-note", "terraform plan drift")]
    ranked = Bm25Index(docs).rank("terraform drift")
    assert [x.key for x in ranked] == ["a-note", "b-note"]


def test_an_empty_index_or_a_stopword_query_ranks_nothing() -> None:
    assert Bm25Index([]).rank("make verify") == []
    assert len(Bm25Index([])) == 0
    assert Bm25Index([("x", "make verify")]).rank("the and of") == []


def test_a_cjk_note_is_found_by_a_cjk_prompt() -> None:
    docs = [(n.slug, _doc(n)) for n in filler_notes("p")]
    docs.append(("zh", "数据库迁移要先备份"))
    ranked = Bm25Index(docs).rank("迁移之前怎么备份数据库")
    assert ranked and ranked[0].key == "zh"
    assert ranked[0].score >= r.RELEVANCE_FLOOR


def test_one_shared_common_word_stays_under_the_floor() -> None:
    """A prompt that only shares an everyday word with a note brings nothing,
    while the note it names clears the floor in the same corpus."""
    docs = [(n.slug, _doc(n)) for n in filler_notes("p")]
    docs.append(("node", "make verify fails with undici AbortSignal under Node 22"))
    docs.append(("other", "the kettle handling needs a lantern"))
    index = Bm25Index(docs)
    named = index.rank("why does make verify fail with undici AbortSignal under node")
    assert named[0].key == "node" and named[0].score >= r.RELEVANCE_FLOOR
    assert select(index.rank("please explain why this fails")) == []


# --- select ----------------------------------------------------------------------


def _ranked(*scores: float) -> list[Ranked]:
    return [Ranked(f"n{i}", s) for i, s in enumerate(scores)]


def test_select_keeps_the_top_k_above_the_floor() -> None:
    picked = select(_ranked(20, 15, 10, 9, 8))
    assert [p.key for p in picked] == ["n0", "n1", "n2"]
    assert r.TOP_K == 3


def test_select_stops_at_the_floor() -> None:
    picked = select(_ranked(9.0, r.RELEVANCE_FLOOR, r.RELEVANCE_FLOOR - 0.01, 3.0))
    assert [p.key for p in picked] == ["n0", "n1"]


def test_select_skips_what_the_session_was_given_and_fills_from_below() -> None:
    picked = select(_ranked(20, 15, 10, 9, 1), exclude={"n0", "n2"})
    assert [p.key for p in picked] == ["n1", "n3"]


def test_select_honours_k_and_floor_overrides() -> None:
    assert [p.key for p in select(_ranked(5, 4, 3), k=1)] == ["n0"]
    assert [p.key for p in select(_ranked(5, 4, 3), floor=2.5)] == ["n0", "n1", "n2"]
    assert select(_ranked(3.9, 2.0)) == []


def test_the_ceiling_constant_is_the_spec_s() -> None:
    assert r.RETRIEVAL_CEILING_BYTES == 1500
    assert r.RELEVANCE_FLOOR == 4.0
