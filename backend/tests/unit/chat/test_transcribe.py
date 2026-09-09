"""Voice transcription seam (spec 009 FR-022).

A text-only agent (Claude Code, Codex) receives a voice attachment as a
transcript rather than an opaque audio file. The engine is behind the
``Transcriber`` seam, so these tests use a fake — no model download.
"""

from __future__ import annotations

import pytest

from coffer.domain.chat.attachment import Attachment
from coffer.infrastructure.chat import transcribe as transcribe_mod
from coffer.infrastructure.chat.stt_whispercpp import WhisperCppTranscriber
from coffer.infrastructure.chat.transcribe import (
    MlxWhisperTranscriber,
    default_transcriber,
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
    spec="009-channels",
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
    assert transcripts == ["change the time to 11:18"]
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


def test_default_transcriber_prefers_whispercpp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(WhisperCppTranscriber, "available", staticmethod(lambda: True))
    assert isinstance(default_transcriber(), WhisperCppTranscriber)


def test_default_transcriber_falls_back_to_mlx(monkeypatch: pytest.MonkeyPatch) -> None:
    # whisper.cpp unavailable (e.g. no whisper-cli) but mlx-whisper importable.
    monkeypatch.setattr(WhisperCppTranscriber, "available", staticmethod(lambda: False))
    monkeypatch.setattr(transcribe_mod, "_mlx_whisper_available", lambda: True)
    assert isinstance(default_transcriber(), MlxWhisperTranscriber)


def test_default_transcriber_none_when_no_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(WhisperCppTranscriber, "available", staticmethod(lambda: False))
    monkeypatch.setattr(transcribe_mod, "_mlx_whisper_available", lambda: False)
    assert default_transcriber() is None


def test_prompt_with_transcripts_folds_voice_into_the_text() -> None:
    assert prompt_with_transcripts("hello", []) == "hello"
    folded = prompt_with_transcripts("what did they say?", ["change the time"])
    assert folded.startswith("what did they say?")
    assert "[Voice message transcript]" in folded
    # With no caption, the transcript is the whole prompt.
    assert prompt_with_transcripts("", ["hi"]).startswith("[Voice message transcript]")
