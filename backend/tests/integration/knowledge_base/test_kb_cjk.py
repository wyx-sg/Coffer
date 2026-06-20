"""CJK content retrieval over the real substrate.

FTS5's ``trigram`` tokenizer indexes 3-character sequences, so keyword search
matches CJK substrings — a contiguous Chinese run no longer hides its substrings
the way the old ``unicode61`` tokenizer did (which made keyword search useless
for Chinese; fixed in migration 0033). ``grep`` (ripgrep) remains the zero-index
substring mode; these tests pin that both work for CJK. A keyword query shorter
than 3 characters falls back to a substring (LIKE) scan.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def _ingest(kb, name: str, filename: str, data: bytes, **kw):
    return await kb.service.ingest_bytes(
        kb_name=name, filename=filename, raw_bytes=data, actor="user", **kw
    )


async def test_grep_finds_cjk_substrings(kb) -> None:
    await kb.create_kb("kb1")
    body = "# 部署文档\n\n我们的服务采用蓝绿发布策略,回滚通过流量切换完成。\n"
    await _ingest(kb, "kb1", "deploy.md", body.encode("utf-8"))

    result = await kb.service.grep(kb_name="kb1", pattern="蓝绿发布")
    assert len(result.hits) == 1
    assert "蓝绿发布" in result.hits[0].line

    result2 = await kb.service.grep(kb_name="kb1", pattern="流量切换")
    assert len(result2.hits) == 1


async def test_keyword_matches_isolated_cjk_phrase(kb) -> None:
    """An isolated CJK phrase (bounded by spaces/punctuation/latin) is a keyword
    match under the trigram tokenizer (as is a substring — see below)."""
    await kb.create_kb("kb1")
    body = "# 术语\n\n部署策略: 蓝绿发布 (blue-green)\n"
    await _ingest(kb, "kb1", "glossary.md", body.encode("utf-8"))

    hit = await kb.service.search(kb_name="kb1", query="蓝绿发布", top_k=5)
    assert len(hit.passages) == 1


async def test_cjk_fact_roundtrip_via_grep_recall(kb) -> None:
    """The end-to-end CJK answer: content ingests, persists in UTF-8 markdown,
    and grep retrieval returns it byte-exact."""
    await kb.create_kb("kb1")
    body = "# 配置\n\nAPI 网关的超时时间是 30 秒,重试 3 次。\n"
    doc = await _ingest(kb, "kb1", "config.md", body.encode("utf-8"))

    _, markdown = await kb.service.get_document_text(kb_name="kb1", document_id=doc.id)
    assert "超时时间是 30 秒" in markdown

    result = await kb.service.grep(kb_name="kb1", pattern="超时时间")
    assert len(result.hits) == 1


async def test_keyword_matches_cjk_substring_inside_a_run(kb) -> None:
    """Trigram tokenizer: a substring inside a contiguous CJK run IS now a
    keyword match. The old unicode61 tokenizer could not segment CJK, so this
    was a known limitation served only by grep — fixed in migration 0033 (this
    flips the former negative pin)."""
    await kb.create_kb("kb1")
    body = "# 策略\n\n我们的服务采用蓝绿发布策略完成上线。\n"
    await _ingest(kb, "kb1", "policy.md", body.encode("utf-8"))

    result = await kb.service.search(kb_name="kb1", query="蓝绿发布", top_k=5)
    assert len(result.passages) == 1
    assert "蓝绿发布" in result.passages[0].text
