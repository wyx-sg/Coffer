"""Speech-to-text seam for inbound voice (spec channels FR-022).

An agent that cannot hear audio (Claude Code, Codex) receives a voice message as
a **transcript** rather than an opaque file: the adapter transcribes the audio to
text before building the turn. The engine is injected behind :class:`Transcriber`
so turns are testable with a fake and so this module stays free of any opinion
about where transcription happens.

The shipped engine is remote — see
:mod:`coffer.infrastructure.llm.transcription` — and is absent unless the user
has designated an internal connection. Absent, transcription degrades to handing
over the audio file path (channel media's per-agent materialisation), which is the
default and means nothing leaves the machine.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from coffer.domain.chat.attachment import Attachment


class Transcriber(Protocol):
    """Turn an audio file into text. Returns "" when it cannot (never raises to
    the caller — the adapter then falls back to handing over the file path)."""

    async def transcribe(self, path: str) -> str: ...


async def transcribe_audio_attachments(
    attachments: Sequence[Attachment], transcriber: Transcriber | None
) -> tuple[list[Attachment], list[str]]:
    """Split ``attachments`` into (the non-audio ones to keep, transcripts of the
    audio ones). With no transcriber — or when transcription yields nothing —
    audio is kept as an attachment so the agent still receives the file path."""
    if transcriber is None:
        return list(attachments), []
    kept: list[Attachment] = []
    transcripts: list[str] = []
    for att in attachments:
        if att.mime.startswith("audio/"):
            text = (await transcriber.transcribe(att.path)).strip()
            if text:
                transcripts.append(text)
                continue
        kept.append(att)
    return kept, transcripts


def prompt_with_transcripts(prompt: str, transcripts: Sequence[str]) -> str:
    """Fold voice transcripts into the turn's text prompt (labelled so the agent
    knows they came from speech)."""
    if not transcripts:
        return prompt
    voice = "\n\n".join(f"[Voice message transcript]\n{t}" for t in transcripts)
    return f"{prompt}\n\n{voice}".strip() if prompt else voice


__all__ = [
    "Transcriber",
    "prompt_with_transcripts",
    "transcribe_audio_attachments",
]
