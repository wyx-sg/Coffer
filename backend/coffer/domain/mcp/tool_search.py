"""Pure keyword ranking over MCP tool descriptors for ``coffer__search_tools``.

No I/O, no infra import, kind-agnostic (importlinter Contracts 2b/5/6). Given a
query and a catalogue of ``(name, description[, parameters])`` tools, returns
the indices of the best matches ranked by a BM25-lite score: tool-name tokens
weigh most, description tokens next and the input schema's parameter text
(names, descriptions, enum values) least. Chinese, Japanese and Korean text is
cut into overlapping two-character terms, since it has no spaces to split on.
Deterministic — equal scores keep catalogue order — so the retrieval eval can
score it offline.
"""

from __future__ import annotations

import functools
import math
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

#: CJK ideographs (with extension A and compatibility forms), Japanese kana and
#: Korean Hangul syllables: scripts written without spaces between words.
_CJK = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff"
_TOKEN_RE = re.compile(rf"[a-z0-9]+|[{_CJK}]+")
_CJK_RUN_RE = re.compile(rf"[{_CJK}]")
_NAME_WEIGHT = 3.0
_DESC_WEIGHT = 1.0
_PARAM_WEIGHT = 0.5
_K1 = 1.5
_B = 0.75


def _tokenize(text: str) -> list[str]:
    """Latin runs split on case and punctuation; a CJK run becomes its
    overlapping character pairs (a lone character stays itself), the way
    Lucene's CJK analyzer cuts text it has no dictionary for."""
    normal = unicodedata.normalize("NFKC", text)
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", normal)
    tokens: list[str] = []
    for run in _TOKEN_RE.findall(spaced.lower()):
        if len(run) > 1 and _CJK_RUN_RE.match(run):
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        else:
            tokens.append(run)
    return tokens


def schema_text(schema: Mapping[str, Any] | None) -> str:
    """The searchable text of an input schema: each property's name, its
    description and its string enum values, nested objects and array items
    included. Order follows the schema, so the text is deterministic."""
    parts: list[str] = []

    def walk(node: Any, depth: int) -> None:
        if not isinstance(node, Mapping) or depth > 4:
            return
        properties = node.get("properties")
        if isinstance(properties, Mapping):
            for name, prop in properties.items():
                parts.append(str(name))
                if isinstance(prop, Mapping):
                    if isinstance(prop.get("description"), str):
                        parts.append(prop["description"])
                    enum = prop.get("enum")
                    if isinstance(enum, list):
                        parts.extend(v for v in enum if isinstance(v, str))
                walk(prop, depth + 1)
        walk(node.get("items"), depth + 1)

    walk(schema, 0)
    return "\n".join(parts)


@dataclass(frozen=True)
class ScoredTool:
    index: int
    score: float


@dataclass(frozen=True)
class _Index:
    """The query-independent half of the score, computed once per catalogue."""

    doc_tfs: tuple[dict[str, float], ...]
    doc_lens: tuple[float, ...]
    avg_len: float


@functools.lru_cache(maxsize=8)
def _index(catalogue: tuple[tuple[str, ...], ...]) -> _Index:
    """Tokenize and weigh every tool once. Keyed on the catalogue itself, so a
    changed tool list (a server added, a description edited) is a new index
    and an unchanged one costs a hash of the tuple rather than a re-tokenize
    of every description on every search."""
    doc_tfs: list[dict[str, float]] = []
    doc_lens: list[float] = []
    for name, description, parameters in catalogue:
        tf: dict[str, float] = {}
        length = 0.0
        for text, weight in ((name, _NAME_WEIGHT), (description, _DESC_WEIGHT)):
            for tok in _tokenize(text):
                tf[tok] = tf.get(tok, 0.0) + weight
                length += weight
        # Parameter text scores but does not lengthen the document: a schema
        # with many parameters is a well-described tool, not a verbose one,
        # and counting it would push the tool's name and description down.
        for tok in _tokenize(parameters):
            tf[tok] = tf.get(tok, 0.0) + _PARAM_WEIGHT
        doc_tfs.append(tf)
        doc_lens.append(length)
    n = len(catalogue)
    return _Index(tuple(doc_tfs), tuple(doc_lens), (sum(doc_lens) / n) if n else 0.0)


def _fields(tool: tuple[str, ...]) -> tuple[str, str, str]:
    name, description, *rest = tool
    return str(name), str(description), str(rest[0]) if rest else ""


def rank_tools(
    query: str,
    catalogue: Sequence[tuple[str, str] | tuple[str, str, str]],
    top_k: int,
    *,
    prefer: Sequence[bool] | None = None,
) -> list[ScoredTool]:
    """Rank ``catalogue`` against ``query``; return up to ``top_k`` best-first.

    Zero-score tools are dropped. Deterministic: ties keep catalogue order,
    except that a tool flagged in ``prefer`` (one only search can reach) goes
    ahead of an equally scored one the agent already sees listed.
    """
    if top_k <= 0 or not catalogue:
        return []
    query_terms = set(_tokenize(query))
    if not query_terms:
        return []

    index = _index(tuple(_fields(tool) for tool in catalogue))
    doc_tfs, doc_lens, avg_len = index.doc_tfs, index.doc_lens, index.avg_len
    n = len(catalogue)

    idf: dict[str, float] = {}
    for term in query_terms:
        df = sum(1 for tf in doc_tfs if term in tf)
        idf[term] = math.log(1 + (n - df + 0.5) / (df + 0.5))

    scored: list[ScoredTool] = []
    for i, tf in enumerate(doc_tfs):
        score = 0.0
        for term in query_terms:
            f = tf.get(term, 0.0)
            if f == 0.0:
                continue
            norm = (doc_lens[i] / avg_len) if avg_len else 0.0
            denom = f + _K1 * (1 - _B + _B * norm)
            score += idf[term] * (f * (_K1 + 1)) / denom
        if score > 0.0:
            scored.append(ScoredTool(index=i, score=score))

    scored.sort(key=lambda s: (-s.score, not (prefer and prefer[s.index]), s.index))
    return scored[:top_k]


__all__ = ["ScoredTool", "rank_tools", "schema_text"]
