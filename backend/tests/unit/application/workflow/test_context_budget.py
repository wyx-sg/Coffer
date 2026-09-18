"""The context ceiling and what gives when it is reached (FR-047, FR-048)."""

from __future__ import annotations

import pytest

from coffer.application.workflow.context_budget import (
    BRIEF_SHARE,
    CATALOGUE_SHARE,
    NODE_CONTEXT_TOKEN_BUDGET,
    SUMMARY_TOKEN_ALLOWANCE,
    TRANSCRIPTS_SHARE,
    TranscriptFitter,
    estimate_tokens,
    share_of,
)
from coffer.application.workflow.transcripts import TaskTranscript, TranscriptMessage

from .fakes import FakeSummariser

#: Comfortably over the transcripts' share once rendered.
HUGE = "x" * 200_000


def task(node_key: str, text: str, *, attempt: int = 1, name: str | None = None) -> TaskTranscript:
    return TaskTranscript(
        node_key=node_key,
        attempt=attempt,
        name=name,
        messages=(TranscriptMessage(role="developer", text=text),),
    )


def test_the_shares_divide_the_budget_exactly_once() -> None:
    assert BRIEF_SHARE + TRANSCRIPTS_SHARE + CATALOGUE_SHARE == 1.0
    assert share_of(TRANSCRIPTS_SHARE) == int(NODE_CONTEXT_TOKEN_BUDGET * TRANSCRIPTS_SHARE)


def test_cjk_is_not_priced_as_ascii() -> None:
    # A budget that treated 2,000 Chinese characters as 500 tokens would be
    # silently unbounded for a vault whose owner writes in Chinese.
    assert estimate_tokens("账号服务的分库分表" * 100) > estimate_tokens("account service" * 100)


def test_whitespace_padding_does_not_inflate_the_estimate() -> None:
    assert estimate_tokens("hello world") == estimate_tokens("hello       world")


async def test_everything_that_fits_is_kept_verbatim_and_nothing_is_announced() -> None:
    fitter = TranscriptFitter(summariser=FakeSummariser())
    fitted = await fitter.fit([task("draft_td", "Short."), task("write_code", "Also short.")])

    assert fitted.summarised == ()
    assert fitted.omitted == ()
    assert fitted.notice == ""
    assert len(fitted.blocks) == 2


@pytest.mark.acceptance(
    spec="workflow", scenario="earlier tasks are summarised when they exceed the budget"
)
async def test_the_oldest_are_summarised_not_the_newest() -> None:
    summariser = FakeSummariser("A tidy summary.")
    fitter = TranscriptFitter(summariser=summariser)

    fitted = await fitter.fit(
        [
            task("draft_td", HUGE, name="Draft the TD"),
            task("write_code", "The newest thing anyone said."),
        ]
    )

    assert fitted.summarised == ("`draft_td` attempt 1 — Draft the TD",)
    assert fitted.omitted == ()
    # Run order survives the cut: the summary of the old task comes first.
    assert "A tidy summary." in fitted.blocks[0]
    assert "The newest thing anyone said." in fitted.blocks[1]
    assert summariser.asked, "the overflowing transcript is what gets summarised"


async def test_with_no_internal_connection_the_overflow_is_named_not_dropped() -> None:
    fitter = TranscriptFitter(summariser=FakeSummariser(None))

    fitted = await fitter.fit(
        [task("draft_td", HUGE, name="Draft the TD"), task("write_code", "Kept.")]
    )

    assert fitted.summarised == ()
    assert fitted.omitted == ("`draft_td` attempt 1 — Draft the TD",)
    assert "no internal model connection is configured" in fitted.notice
    assert "`draft_td` attempt 1 — Draft the TD" in fitted.notice


async def test_a_summariser_that_raises_degrades_the_same_way_as_one_that_is_absent() -> None:
    class Exploding:
        async def summarise(self, text: str, *, hint: str) -> str | None:
            raise RuntimeError("the internal connection is down")

    fitter = TranscriptFitter(summariser=Exploding())

    fitted = await fitter.fit([task("draft_td", HUGE), task("write_code", "Kept.")])

    assert fitted.omitted == ("`draft_td` attempt 1 — draft_td",)


async def test_a_summary_that_ignores_the_length_instruction_is_clipped_and_says_so() -> None:
    fitter = TranscriptFitter(summariser=FakeSummariser("y" * 40_000))

    fitted = await fitter.fit([task("draft_td", HUGE), task("write_code", "Kept.")])

    assert "summary clipped" in fitted.blocks[0]
    assert estimate_tokens(fitted.blocks[0]) <= SUMMARY_TOKEN_ALLOWANCE + 50


@pytest.mark.acceptance(
    spec="workflow", scenario="earlier tasks are summarised when they exceed the budget"
)
async def test_the_whole_section_lands_inside_its_share() -> None:
    fitter = TranscriptFitter(summariser=FakeSummariser("Short."))

    fitted = await fitter.fit([task(f"node_{index}", HUGE) for index in range(6)])

    whole = "\n\n".join((*fitted.blocks, fitted.notice))
    assert estimate_tokens(whole) <= share_of(TRANSCRIPTS_SHARE)


async def test_an_empty_transcript_needs_no_model_to_be_summarised() -> None:
    summariser = FakeSummariser(None)
    fitter = TranscriptFitter(summariser=summariser, allowance=1)

    fitted = await fitter.fit([TaskTranscript(node_key="draft_td", attempt=1)])

    assert fitted.omitted == ()
    assert summariser.asked == []
