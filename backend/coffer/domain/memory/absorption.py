"""Whether an agent's change to its own memory only restates what Coffer
delivered to it (spec memory "Never republish Coffer's own copies").

When an agent's curation folds a copy into one of its own memories (Auto
Dream merges a ``coffer_`` file and deletes it; Codex rewrites a bullet), that
memory is the agent's and syncs like any other. Its rewording of what it
absorbed must not circulate forever, so every sentence Coffer delivers to an
agent is fingerprinted, and a change whose added sentences are all among
those fingerprints is recorded without being published.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

#: A sentence ends at ``.``, ``!`` or ``?`` (and their full-width forms) or a line break.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|(?<=[\u3002\uff01\uff1f])\s*|\n+")
_NOT_WORD = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE = re.compile(r"\s+")
_LIST_MARK = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
#: A fragment this short says too little to count as a sentence (a CJK
#: character counts twice: it says about as much as a short word).
MIN_SENTENCE = 12
_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def sentences(text: str) -> list[str]:
    """``text`` split into normalised sentences: lower-cased, punctuation
    dropped, whitespace collapsed; list markers and short fragments skipped."""
    out: list[str] = []
    for raw in _SENTENCE_END.split(text):
        line = _LIST_MARK.sub("", raw)
        norm = _SPACE.sub(" ", _NOT_WORD.sub(" ", line.lower())).strip()
        if len(norm) + len(_CJK.findall(norm)) >= MIN_SENTENCE:
            out.append(norm)
    return out


def fingerprint(sentence: str) -> str:
    return hashlib.sha1(sentence.encode("utf-8"), usedforsecurity=False).hexdigest()


def fingerprints(text: str) -> set[str]:
    """Every sentence fingerprint of ``text``."""
    return {fingerprint(s) for s in sentences(text)}


def added(old: str, new: str) -> set[str]:
    """The fingerprints ``new`` holds that ``old`` did not."""
    return fingerprints(new) - fingerprints(old)


def only_delivered(old: str, new: str, delivered: Iterable[str]) -> bool:
    """Whether every sentence ``new`` adds over ``old`` is one Coffer
    delivered. A change that adds nothing (a removal, a reorder) is not
    "only delivered": it is the agent's own and publishes as usual."""
    new_ones = added(old, new)
    if not new_ones:
        return False
    return new_ones <= set(delivered)


__all__ = ["MIN_SENTENCE", "added", "fingerprint", "fingerprints", "only_delivered", "sentences"]
