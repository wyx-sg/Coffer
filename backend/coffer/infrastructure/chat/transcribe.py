"""Speech-to-text seam for inbound voice (spec 009 FR-022).

An agent that cannot hear audio (Claude Code, Codex) receives a voice message as
a **transcript** rather than an opaque file: the adapter transcribes the audio to
text before building the turn. The engine is injected behind :class:`Transcriber`
so turns are testable with a fake, and the real one is a lazily-imported optional
dependency — absent, transcription simply degrades to handing over the audio file
path (see ADR-038's per-agent materialisation).
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from collections.abc import Sequence
from typing import Protocol

from coffer.domain.chat.attachment import Attachment

_logger = logging.getLogger(__name__)

#: Default Apple-Silicon-native whisper model — small is ~real-time for a short
#: voice message and downloads once on first use.
_DEFAULT_MODEL = "mlx-community/whisper-small-mlx"


class Transcriber(Protocol):
    """Turn an audio file into text. Returns "" when it cannot (never raises to
    the caller — the adapter then falls back to handing over the file path)."""

    async def transcribe(self, path: str) -> str: ...


class MlxWhisperTranscriber:
    """`mlx-whisper` (Metal/ANE, Apple Silicon), imported lazily so the dependency
    stays optional. Runs the blocking transcribe off the event loop."""

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model = model

    async def transcribe(self, path: str) -> str:
        try:
            import mlx_whisper  # optional dependency (extra: voice)
        except ImportError:
            _logger.info("transcribe.mlx_whisper_absent — voice not transcribed")
            return ""
        try:
            result = await asyncio.to_thread(
                mlx_whisper.transcribe, path, path_or_hf_repo=self._model
            )
        except Exception:
            _logger.warning("transcribe.failed", extra={"model": self._model}, exc_info=True)
            return ""
        return str(result.get("text", "")).strip()


def default_transcriber() -> Transcriber | None:
    """The best transcriber available in this runtime (ADR-039):

    * the torch-free ``whisper.cpp`` engine — the frozen desktop app (bundled
      ``whisper-cli`` sibling), or a source run with ``whisper-cli`` on ``PATH``;
    * else source-run ``mlx-whisper`` (the ``[voice]`` extra), excluded from the
      frozen build because it drags torch;
    * else ``None`` — the adapter then hands over the audio file, untranscribed.
    """
    # Imported here (not at module scope) so the module stays importable without the
    # optional decode deps, and so PyInstaller keeps the whisper.cpp path traceable.
    from coffer.infrastructure.chat.stt_whispercpp import WhisperCppTranscriber

    if WhisperCppTranscriber.available():
        return WhisperCppTranscriber()
    if _mlx_whisper_available():
        return MlxWhisperTranscriber()
    return None


def _mlx_whisper_available() -> bool:
    """True when the source-run ``mlx-whisper`` fallback is importable (excluded from
    the frozen build, so this is always False there)."""
    return importlib.util.find_spec("mlx_whisper") is not None


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
    "MlxWhisperTranscriber",
    "Transcriber",
    "default_transcriber",
    "prompt_with_transcripts",
    "transcribe_audio_attachments",
]
