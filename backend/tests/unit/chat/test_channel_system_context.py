"""Unit tests for ``channel_system_context`` — the note that tells a
channel-driven agent it is on a phone chat.

"Keep replies short" once read as licence to drop evidence: asked over SeaTalk
to investigate a failed login, the agent answered with a prose summary and the
user had to ask a second time for the log lines behind it. Brevity and evidence
must both be in the note.
"""

from __future__ import annotations

import pytest

from coffer.infrastructure.chat.adapter_support import channel_system_context


@pytest.mark.acceptance(
    spec="channels",
    scenario="the channel-driven agent is told it is on a chat channel",
)
def test_asks_for_short_replies_that_keep_the_evidence() -> None:
    text = channel_system_context("SeaTalk")

    assert "the SeaTalk chat channel" in text
    assert "Keep replies short" in text
    assert "Short never means dropping evidence" in text
    assert "log lines" in text
    assert "verbatim" in text


def test_an_unresolvable_channel_name_keeps_the_guidance() -> None:
    text = channel_system_context(None)

    assert "over a chat channel" in text
    assert "Short never means dropping evidence" in text
