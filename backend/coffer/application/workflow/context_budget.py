"""How much a task's opening message may cost, and what gives (spec
workflow "Keep a task's opening context within budget").

The ceiling here is a **backstop, not the mechanism**. What keeps a task's
opening message small is that almost none of it is content: the deliverables,
the artifacts, the mounted inputs and the earlier tasks are all *named*, with
the path or address that opens them, so the message grows by a line per task
rather than by everything the run has said. The one part carried in full is the
bound skill's instructions, which is what the task is being asked to do and is
bounded by the person who wrote it.

Two rules hold everywhere below:

* **Oldest first.** The run's recent history is what the next task continues
  from, so it is the oldest rows that go when something has to.
* **Never silently.** Anything cut says it was cut and says where the whole of
  it can be read. A task told "the fifteen oldest tasks are not listed here"
  can go and look; a task told nothing works from a hole it cannot see.
"""

from __future__ import annotations

import logging
import math
import unicodedata

__all__ = [
    "BRIEF_SHARE",
    "INDEX_SHARE",
    "NODE_CONTEXT_TOKEN_BUDGET",
    "estimate_tokens",
    "share_of",
]

_logger = logging.getLogger(__name__)

#: The whole opening message's ceiling, in tokens.
#:
#: 60,000 because the smallest context window among the agents Coffer drives is
#: around 200,000 tokens, and the opening message is the node's *brief*, not its
#: work: a node that spends a third of its window before reading a single file
#: has nowhere left to run a repository's tests and quote the output. Under a
#: third of the smallest window leaves two thirds for the work itself, which is
#: the ratio the rest of this module's shares are cut from.
NODE_CONTEXT_TOKEN_BUDGET = 60_000

#: The two shares of that budget, which sum to 1.0.
#:
#: The brief and its bound skill take the bulk because they are the only part
#: carried as CONTENT rather than as names — a skill's instructions are a
#: document, and squeezing them would be squeezing the one thing that says how
#: the work is done. The index of earlier tasks takes a tenth because every
#: line of it is a *name*: a path, a task key, never a file's contents (spec
#: workflow "Open every task with the same four parts"). Neither is expected
#: to be reached; they exist so that an enormous skill or a run hundreds of
#: tasks long degrades by SAYING what it left out rather than by failing to
#: open at all ("Keep a task's opening context within budget").
#:
#: Both are enforced. A share that is declared and never applied is a ceiling
#: in the documentation and nowhere else — which is what ``BRIEF_SHARE`` was
#: until the skill's instructions became the only unbounded part of the
#: message.
BRIEF_SHARE = 0.9
INDEX_SHARE = 0.1

#: East-Asian-wide characters cost close to a whole token each, where ASCII
#: prose runs at roughly four characters per token. Pricing both at one ratio
#: would undercount a vault whose owner writes in Chinese by a factor of four,
#: which is exactly the case this ceiling exists to catch.
_ASCII_CHARS_PER_TOKEN = 4.0
_CJK_CHARS_PER_TOKEN = 1.0
_OTHER_CHARS_PER_TOKEN = 2.0
_EAST_ASIAN_WIDE = frozenset({"W", "F"})


def estimate_tokens(text: str) -> int:
    """A rough, deterministic token count — never a tokenizer, never I/O.

    The ceiling only has to be conservative, not byte-exact against one
    model's accounting, and adding a real BPE dependency for a number that is
    compared against 60,000 would be a dependency bought for nothing.
    """
    if not text:
        return 0
    ascii_chars = cjk_chars = other_chars = 0
    for char in text:
        if char.isspace():
            continue
        if ord(char) < 128:
            ascii_chars += 1
        elif unicodedata.east_asian_width(char) in _EAST_ASIAN_WIDE:
            cjk_chars += 1
        else:
            other_chars += 1
    exact = (
        ascii_chars / _ASCII_CHARS_PER_TOKEN
        + cjk_chars / _CJK_CHARS_PER_TOKEN
        + other_chars / _OTHER_CHARS_PER_TOKEN
    )
    return math.ceil(exact)


def share_of(fraction: float, budget: int = NODE_CONTEXT_TOKEN_BUDGET) -> int:
    """One part's allowance, in tokens."""
    return int(budget * fraction)
