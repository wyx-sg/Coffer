"""Prompt-time retrieval: a lexical ranker over a partition's notes (spec
memory "Retrieve the notes a prompt names").

ADR memory-reaches-a-session-at-prompt-time-and-before-a-known-trap chose
BM25 over embeddings: three points of recall on the eval set's held failures
did not pay for a 2.2 GB local model, and the product already dropped
embeddings for literal search. What is ranked is each note's title,
description, search terms and body; CJK text is tokenised as overlapping
bigrams, which is what lets a Chinese note be found by a Chinese prompt with no
segmenter.

Pure: the index is built from ``(key, text)`` pairs the caller read, and it is
derived state, held in memory and rebuilt when the notes change. Nothing here
chunks, embeds or writes anything.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

#: How many notes one prompt may bring in.
TOP_K = 3
#: The least BM25 score a note must reach to be delivered at all. Calibrated on
#: the 107-case eval set together with the tokeniser and stopwords below: at 4.0
#: a prompt that only shares common words with a note brings nothing.
RELEVANCE_FLOOR = 4.0
#: The ceiling on one prompt's delivery, in UTF-8 bytes of the whole text.
RETRIEVAL_CEILING_BYTES = 1500
#: A prompt with fewer words than this ("continue", "ok", "继续") retrieves
#: nothing.
MIN_PROMPT_WORDS = 3

#: Prompts that are a nudge rather than a request, whatever their length.
_TRIVIAL = frozenset(
    {
        "ok",
        "okay",
        "yes",
        "no",
        "go",
        "continue",
        "go on",
        "keep going",
        "next",
        "thanks",
        "thank you",
        "继续",
        "好",
        "好的",
        "可以",
        "是",
        "对",
        "嗯",
        "谢谢",
        "下一步",
    }
)

_WORD = re.compile(r"[a-z0-9_\-\.]+")
_CJK = re.compile(r"[一-鿿]")

#: Words too common in both prompts and notes to say anything about relevance.
STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "of",
        "in",
        "on",
        "for",
        "is",
        "it",
        "be",
        "with",
        "as",
        "at",
        "by",
        "this",
        "that",
        "from",
        "are",
        "was",
        "not",
        "use",
        "run",
        "do",
    }
)

_K1 = 1.2
_B = 0.75


def tokens(text: str) -> list[str]:
    """Lower-cased word tokens, plus CJK bigrams, minus stopwords and one-letter
    fragments."""
    lowered = text.lower()
    out = _WORD.findall(lowered)
    cjk = _CJK.findall(lowered)
    out += [cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)]
    cleaned = (t.strip(".-") for t in out)
    return [t for t in cleaned if len(t) > 1 and t not in STOPWORDS]


def _word_count(prompt: str) -> int:
    """Whitespace words, with each CJK character counted as one — a Chinese
    request has no spaces, and a three-character one is still a request."""
    count = 0
    for word in prompt.split():
        cjk = len(_CJK.findall(word))
        count += cjk + (1 if _CJK.sub("", word).strip() else 0) if cjk else 1
    return count


def is_substantive(prompt: str) -> bool:
    """Whether a prompt is worth ranking against: three words or more, and not a
    bare nudge like "继续" or "ok"."""
    stripped = " ".join(prompt.strip().lower().split()).strip(" .!?\u3002\uff01\uff1f")
    if not stripped or stripped in _TRIVIAL:
        return False
    return _word_count(stripped) >= MIN_PROMPT_WORDS


@dataclass(frozen=True)
class Ranked:
    """One note's score for one query."""

    key: str
    score: float


class Bm25Index:
    """An Okapi BM25 index over a fixed set of documents."""

    def __init__(self, docs: Iterable[tuple[str, str]]) -> None:
        self._keys: list[str] = []
        self._freqs: list[Counter[str]] = []
        self._lengths: list[int] = []
        df: Counter[str] = Counter()
        for key, text in docs:
            toks = tokens(text)
            freq = Counter(toks)
            self._keys.append(key)
            self._freqs.append(freq)
            self._lengths.append(len(toks))
            df.update(freq.keys())
        self._df = df
        n = len(self._keys)
        self._avg = (sum(self._lengths) / n) if n else 0.0

    def __len__(self) -> int:
        return len(self._keys)

    def _idf(self, term: str) -> float:
        n = len(self._keys)
        df = self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def rank(self, query: str) -> list[Ranked]:
        """Every document with a positive score, best first; ties by key."""
        terms = set(tokens(query))
        if not terms or not self._keys:
            return []
        out: list[Ranked] = []
        for key, freq, length in zip(self._keys, self._freqs, self._lengths, strict=True):
            score = 0.0
            norm = _K1 * (1 - _B + _B * length / self._avg) if self._avg else _K1
            for term in terms:
                f = freq.get(term, 0)
                if f:
                    score += self._idf(term) * f * (_K1 + 1) / (f + norm)
            if score > 0:
                out.append(Ranked(key, score))
        out.sort(key=lambda r: (-r.score, r.key))
        return out


def select(
    ranked: Sequence[Ranked],
    *,
    exclude: Iterable[str] = (),
    k: int = TOP_K,
    floor: float = RELEVANCE_FLOOR,
) -> list[Ranked]:
    """The top ``k`` above ``floor``, skipping what ``exclude`` names (the notes
    already delivered in this session)."""
    skip = set(exclude)
    picked: list[Ranked] = []
    for r in ranked:
        if r.score < floor:
            break
        if r.key in skip:
            continue
        picked.append(r)
        if len(picked) >= k:
            break
    return picked


__all__ = [
    "MIN_PROMPT_WORDS",
    "RELEVANCE_FLOOR",
    "RETRIEVAL_CEILING_BYTES",
    "STOPWORDS",
    "TOP_K",
    "Bm25Index",
    "Ranked",
    "is_substantive",
    "select",
    "tokens",
]
