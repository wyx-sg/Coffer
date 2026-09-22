"""How much a node's opening message may cost, and what gives when it costs
more (FR-047, FR-048).

A delivery runs for weeks and a node's opening message carries everything the
run has said. Left alone that message grows until the node **cannot start at
all** — not a degraded experience, a broken one — so the message has a stated
ceiling, each part has a stated share of it, and the part that overruns is
summarised rather than truncated.

Two rules hold everywhere below:

* **Oldest first.** What a task said an hour ago is more likely to have been
  superseded than what the task before this one said, so the oldest transcripts
  are the ones replaced by a summary (FR-048).
* **Never silently.** A summary says it is one, and a transcript that could not
  even be summarised is still *named* in the message. A node that is told "the
  design task's transcript is not here" can go and ask; a node that is told
  nothing answers from a hole it cannot see (FR-047).
"""

from __future__ import annotations

import logging
import math
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from coffer.application.workflow.ports import SummariserPort
from coffer.application.workflow.transcripts import (
    TaskTranscript,
    render_transcript,
    transcript_title,
)

__all__ = [
    "BRIEF_SHARE",
    "CATALOGUE_SHARE",
    "NODE_CONTEXT_TOKEN_BUDGET",
    "TRANSCRIPTS_SHARE",
    "FittedTranscripts",
    "TranscriptFitter",
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

#: The shares of that budget, which sum to 1.0.
#:
#: The brief and the bound skill are what the node is actually being asked to
#: do; they are authored by the developer and bounded by hand, so a quarter is
#: generous and they are never squeezed. The earlier tasks take the largest
#: share because they are the only part that grows without limit — a run of
#: forty tasks has forty transcripts and one catalogue. The catalogue and the
#: mounted inputs take the smallest share because every line of them is a
#: *name*: a path, a collection, a URL, never a file's contents (FR-032).
BRIEF_SHARE = 0.25
TRANSCRIPTS_SHARE = 0.55
CATALOGUE_SHARE = 0.20

#: East-Asian-wide characters cost close to a whole token each, where ASCII
#: prose runs at roughly four characters per token. Pricing both at one ratio
#: would undercount a vault whose owner writes in Chinese by a factor of four,
#: which is exactly the case this ceiling exists to catch.
_ASCII_CHARS_PER_TOKEN = 4.0
_CJK_CHARS_PER_TOKEN = 1.0
_OTHER_CHARS_PER_TOKEN = 2.0
_EAST_ASIAN_WIDE = frozenset({"W", "F"})

#: What one summarised transcript is allowed to cost. A summary that is itself
#: a page long defeats the point, and it also has to be *cheaper than the
#: alternative* — five summaries at this size still fit where one raw
#: transcript did not.
SUMMARY_TOKEN_ALLOWANCE = 400

_SUMMARY_HINT = (
    "Summarise this task's conversation for the next task of the same workflow "
    "run. Keep decisions, corrections the developer made, and anything still "
    "outstanding; drop pleasantries and tool chatter. Write at most one short "
    "paragraph."
)


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


@dataclass(frozen=True)
class FittedTranscripts:
    """The earlier tasks, cut to their share, and the honest account of it."""

    #: Rendered blocks, oldest first — a full transcript or a summary of one.
    blocks: tuple[str, ...]
    #: Tasks replaced by a summary, by title.
    summarised: tuple[str, ...] = ()
    #: Tasks that could not even be summarised, by title (FR-047's "never
    #: silently": these are named in the message rather than dropped).
    omitted: tuple[str, ...] = ()

    @property
    def notice(self) -> str:
        """What the section says about itself. Empty when nothing was cut."""
        lines: list[str] = []
        if self.summarised:
            lines.append(
                "The oldest task(s) below are **summaries, not transcripts** — they exceeded "
                "this section's share of the context budget:"
            )
            lines.extend(f"- {title}" for title in self.summarised)
        if self.omitted:
            lines.append(
                "These task(s) are **not here at all**. They exceeded the budget and no "
                "internal model connection is configured to summarise them, so they are named "
                "rather than guessed at — open the task's own conversation if you need it:"
            )
            lines.extend(f"- {title}" for title in self.omitted)
        return "\n".join(lines)


class TranscriptFitter:
    """Fits the run's earlier tasks into ``TRANSCRIPTS_SHARE`` of the budget.

    Newest-first accumulation, because the newest transcript is the one whose
    every word still stands. Once the allowance is spent, everything older is
    summarised — and when there is no summariser, named.
    """

    def __init__(
        self,
        *,
        summariser: SummariserPort,
        allowance: int = share_of(TRANSCRIPTS_SHARE),
    ) -> None:
        self._summariser = summariser
        self._allowance = allowance

    async def fit(self, transcripts: Sequence[TaskTranscript]) -> FittedTranscripts:
        verbatim, overflow = self._split(transcripts)
        blocks: list[str] = []
        summarised: list[str] = []
        omitted: list[str] = []
        # The overflow is the OLDEST end of the run, so its blocks come first:
        # the section reads in run order whichever way each one was rendered.
        for transcript in overflow:
            title = transcript_title(transcript)
            summary = await self._summarise(transcript)
            if summary is None:
                omitted.append(title)
                continue
            summarised.append(title)
            blocks.append(f"### {title} (summary)\n\n{summary.strip()}")
        blocks.extend(render_transcript(item) for item in verbatim)
        return FittedTranscripts(
            blocks=tuple(blocks),
            summarised=tuple(summarised),
            omitted=tuple(omitted),
        )

    def _split(
        self, transcripts: Sequence[TaskTranscript]
    ) -> tuple[list[TaskTranscript], list[TaskTranscript]]:
        """``(kept verbatim, must be summarised)``, both oldest first.

        A transcript is kept only when the whole of it fits in what is left,
        and once one does not fit, nothing older is kept either — a run that
        alternated between fitting and not would read as history with holes in
        it rather than as a recent window.
        """
        remaining = self._allowance
        verbatim: list[TaskTranscript] = []
        for transcript in reversed(transcripts):
            cost = estimate_tokens(render_transcript(transcript))
            if cost > remaining:
                break
            remaining -= cost
            verbatim.append(transcript)
        verbatim.reverse()
        overflow = list(transcripts[: len(transcripts) - len(verbatim)])
        return verbatim, overflow

    async def _summarise(self, transcript: TaskTranscript) -> str | None:
        """One task's transcript as a paragraph, or ``None`` to say so instead."""
        if not transcript.messages:
            return "This task's conversation was empty."
        try:
            summary = await self._summariser.summarise(
                render_transcript(transcript), hint=_SUMMARY_HINT
            )
        except Exception:  # pragma: no cover - the port is allowed to fail loudly
            _logger.warning(
                "workflow.context.summarise_failed",
                extra={"node_key": transcript.node_key},
                exc_info=True,
            )
            return None
        if summary is None or not summary.strip():
            return None
        return _cap(summary, SUMMARY_TOKEN_ALLOWANCE)


def _cap(text: str, allowance: int) -> str:
    """Hold a model that ignored "one short paragraph" to the allowance anyway.

    This is the one place truncation is right: the alternative to a clipped
    summary is a summary that reintroduces the overrun it was called to fix,
    and the clip says so.
    """
    if estimate_tokens(text) <= allowance:
        return text
    cut = text[: allowance * int(_ASCII_CHARS_PER_TOKEN)].rstrip()
    return f"{cut}… _(summary clipped at {allowance} tokens)_"
