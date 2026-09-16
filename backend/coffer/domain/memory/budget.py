"""A small, honest token estimator (spec memory FR-018).

Coffer has no tokenizer anywhere in this codebase, and composing the session
context is not a good enough reason to add one: FR-018 only needs the
composed payload to stay *roughly* inside its budget and to say how much it
left out, never to match one specific model's byte-exact accounting. Adding
a real BPE dependency (``tiktoken`` or similar) for that would be a real
dependency bought for a number that only has to be conservative, not exact.

What this heuristic does calibrate on, because it is the one property that
would otherwise make the estimate actively misleading rather than merely
approximate: **ASCII and CJK text do not cost the same per character** in
essentially every tokenizer this content will ever pass through. English-like
ASCII prose runs at roughly four characters per token; a CJK ideograph,
kana or hangul syllable is usually close to its own token. Pricing both at
one flat ratio would either wildly overcount a mostly-English digest or
wildly undercount a mostly-Chinese one. Both cases are real, not hypothetical:
what this measures is the user's own writing — their notes, their memory facts,
their agents' transcripts — and a vault whose owner works in Chinese produces
digests that are mostly CJK.

Being approximate is fine. Being silently unbounded — treating a
2,000-character Chinese digest as 500 tokens when it is closer to 2,000 — is
the failure this module exists to avoid (see ``application/memory/context.py``,
the one place that spends this estimate against a real budget).
"""

from __future__ import annotations

import math
import unicodedata

#: Characters per token for plain ASCII prose — the common rule of thumb for
#: English-like text (OpenAI's own docs cite ~4 chars/token for English).
_ASCII_CHARS_PER_TOKEN = 4.0

#: East-Asian-wide characters (CJK ideographs, kana, hangul syllables,
#: fullwidth punctuation) are each close to their own token in most
#: tokenizers — nothing like ASCII's 4:1 ratio.
_CJK_CHARS_PER_TOKEN = 1.0

#: Everything else (accented Latin, Cyrillic, Greek, symbols, emoji) is
#: priced between the two: worse than ASCII because it is rarer in a
#: tokenizer's vocabulary and so splits into more sub-word pieces, better
#: than CJK because it is not one-glyph-per-concept.
_OTHER_CHARS_PER_TOKEN = 2.0

#: Unicode's own "is this character East-Asian-wide" classes.
_EAST_ASIAN_WIDE = frozenset({"W", "F"})


def _is_cjk(char: str) -> bool:
    """Whether ``char`` is East-Asian-wide by Unicode's own classification —
    exactly the class of character that costs close to a whole token rather
    than a quarter of one."""
    return unicodedata.east_asian_width(char) in _EAST_ASIAN_WIDE


def estimate_tokens(text: str) -> int:
    """A rough, deterministic token count for ``text``.

    Not a tokenizer, and never calls out to one: three linear buckets —
    ASCII, CJK-width, and everything else — each priced at its own
    chars-per-token ratio (see the module docstring), summed and rounded up.
    Whitespace is not counted on its own (real tokenizers fold it into an
    adjacent word's token rather than pricing it separately), so padding a
    string with spaces does not inflate the estimate.

    Deterministic and pure: same input, same output, every time, no I/O.
    """
    if not text:
        return 0
    ascii_chars = 0
    cjk_chars = 0
    other_chars = 0
    for char in text:
        if char.isspace():
            continue
        codepoint = ord(char)
        if codepoint < 128:
            ascii_chars += 1
        elif _is_cjk(char):
            cjk_chars += 1
        else:
            other_chars += 1
    if not (ascii_chars or cjk_chars or other_chars):
        return 0
    exact = (
        ascii_chars / _ASCII_CHARS_PER_TOKEN
        + cjk_chars / _CJK_CHARS_PER_TOKEN
        + other_chars / _OTHER_CHARS_PER_TOKEN
    )
    return math.ceil(exact)


__all__ = ["estimate_tokens"]
