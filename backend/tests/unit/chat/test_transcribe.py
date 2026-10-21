"""Voice transcription seam (spec channels "Transcribe inbound voice only when
the user opted in").

A text-only agent (Claude Code, Codex) receives a voice attachment as a
transcript rather than an opaque audio file. The engine is behind the
``Transcriber`` seam, so these tests use a fake — no model download.
"""

from __future__ import annotations

import pytest

from coffer.domain.chat.attachment import Attachment
from coffer.infrastructure.chat.transcribe import (
    prompt_with_transcripts,
    transcribe_audio_attachments,
)


class _FakeTranscriber:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[str] = []

    async def transcribe(self, path: str) -> str:
        self.calls.append(path)
        return self.text


@pytest.mark.acceptance(
    spec="channels",
    scenario="an inbound voice message is transcribed for a text-only agent",
)
@pytest.mark.acceptance(
    spec="chat",
    scenario="an inbound voice message is transcribed for a text-only agent",
)
async def test_audio_is_transcribed_and_other_files_are_kept() -> None:
    transcriber = _FakeTranscriber("change the time to 11:18")
    attachments = [
        Attachment(path="/tmp/voice.ogg", mime="audio/ogg", filename="voice.ogg"),
        Attachment(path="/tmp/photo.png", mime="image/png", filename="photo.png"),
    ]

    kept, transcripts = await transcribe_audio_attachments(attachments, transcriber)

    # The audio became a transcript and is dropped from the attachments…
    assert transcripts == [(attachments[0], "change the time to 11:18")]
    assert transcriber.calls == ["/tmp/voice.ogg"]
    # …while the image is kept to be materialised as an image block.
    assert [a.filename for a in kept] == ["photo.png"]


async def test_no_transcriber_keeps_audio_as_a_file() -> None:
    attachments = [Attachment(path="/tmp/voice.ogg", mime="audio/ogg", filename="voice.ogg")]

    kept, transcripts = await transcribe_audio_attachments(attachments, None)

    # Without a transcriber the audio is handed over as a file (path), unchanged.
    assert transcripts == []
    assert [a.filename for a in kept] == ["voice.ogg"]


async def test_empty_transcript_falls_back_to_the_audio_file() -> None:
    transcriber = _FakeTranscriber("   ")  # transcription yielded nothing usable
    attachments = [Attachment(path="/tmp/voice.ogg", mime="audio/ogg", filename="voice.ogg")]

    kept, transcripts = await transcribe_audio_attachments(attachments, transcriber)

    assert transcripts == []
    assert [a.filename for a in kept] == ["voice.ogg"]


def test_prompt_with_transcripts_folds_voice_into_the_text() -> None:
    voice = Attachment(
        path="/m/v.ogg", mime="audio/ogg", filename="voice.ogg", number=3, source="a thread message"
    )
    assert prompt_with_transcripts("hello", []) == "hello"
    folded = prompt_with_transcripts("what did they say?", [(voice, "change the time")])
    assert folded == (
        "what did they say?\n\n"
        "[Voice message transcript #3 from a thread message: voice.ogg]\n"
        "change the time\n"
        "[End of voice message transcript]"
    )
    # With no caption, the transcript is the whole prompt.
    assert prompt_with_transcripts("", [(voice, "hi")]).startswith("[Voice message transcript")
