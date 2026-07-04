"""Torch-free local speech-to-text for the frozen desktop app (spec 009 FR-022).

``mlx-whisper`` drags torch/mlx into a PyInstaller build, so the frozen app ships this
engine instead: a bundled ``whisper-cli`` sidecar (Apple-Silicon Metal, no Python/torch)
plus a small ggml model downloaded on first use. Audio is decoded **in-process** with
``soundfile`` (libsndfile reads the OGG/Opus Telegram voice format, plus wav/flac/mp3)
and resampled to 16 kHz mono with ``soxr`` before ``whisper-cli`` runs. Any missing
piece — binary, model, or decoder — returns ``""`` so the :class:`Transcriber` seam
degrades to handing over the audio file (see ADR-039, building on ADR-038).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

_logger = logging.getLogger(__name__)

#: Multilingual quantized base model — ~57 MB, near-real-time for a short voice
#: message on Metal, downloaded once to ``~/.coffer/models/``.
_MODEL_FILE = "ggml-base-q5_1.bin"
_MODEL_URL = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{_MODEL_FILE}"
_SAMPLE_RATE = 16000

_download_lock = asyncio.Lock()


def _models_dir() -> Path:
    """``~/.coffer/models`` — ``HOME`` honored (not ``Path.home()``) so tests redirect it."""
    home = Path(os.environ.get("HOME") or "~").expanduser()
    return home / ".coffer" / "models"


def resolve_whisper_cli() -> str | None:
    """Locate the ``whisper-cli`` binary: a sibling of the frozen executable (bundled
    or deployed to ``~/.coffer/bin``), else on ``PATH`` for source runs (e.g. a dev's
    ``brew install whisper-cpp``)."""
    if getattr(sys, "frozen", False):  # pragma: no cover - packaged builds only
        sibling = Path(sys.executable).with_name("whisper-cli")
        return str(sibling) if sibling.exists() else None
    return shutil.which("whisper-cli")


def _decoder_available() -> bool:
    """``soundfile`` + ``soxr`` importable (the in-process decode/resample path)."""
    try:
        import soundfile  # noqa: F401
        import soxr  # noqa: F401
    except ImportError:
        return False
    return True


def _decode_to_wav(path: str) -> str:
    """Decode a libsndfile-readable audio file (OGG/Opus, wav, flac, mp3) to a temp
    16 kHz mono 16-bit WAV and return its path. Raises on an unreadable format — the
    caller catches and degrades to file handoff."""
    import soundfile as sf
    import soxr

    data, sr = sf.read(path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)  # downmix any channel count to mono
    if sr != _SAMPLE_RATE:
        mono = soxr.resample(mono, sr, _SAMPLE_RATE)
    fd, out = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(out, mono, _SAMPLE_RATE, subtype="PCM_16")
    return out


async def _ensure_model() -> Path | None:
    """Return the local model path, downloading it once on first use to
    ``~/.coffer/models/``. Returns ``None`` when it is absent and cannot be fetched
    (offline) — the caller then degrades to file handoff."""
    path = _models_dir() / _MODEL_FILE
    if path.exists():
        return path
    async with _download_lock:
        if path.exists():  # another turn won the race while we waited on the lock
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".partial")
        try:
            import httpx

            timeout = httpx.Timeout(30.0, read=300.0)
            async with (
                httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client,
                client.stream("GET", _MODEL_URL) as resp,
            ):
                resp.raise_for_status()
                with tmp.open("wb") as f:
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)
            tmp.replace(path)  # atomic — a partial download is never seen as complete
            _logger.info("stt.model_downloaded", extra={"model": _MODEL_FILE})
            return path
        except Exception:
            _logger.warning("stt.model_download_failed", exc_info=True)
            with contextlib.suppress(FileNotFoundError):
                tmp.unlink()
            return None


class WhisperCppTranscriber:
    """Local STT via a bundled ``whisper-cli`` (Metal). Never raises to the caller —
    a missing binary/model/decoder or any failure yields ``""`` so the adapter hands
    over the audio file instead."""

    def __init__(self, cli: str | None = None) -> None:
        self._cli = cli or resolve_whisper_cli()

    @staticmethod
    def available() -> bool:
        """True when this engine can run here: the ``whisper-cli`` binary and the
        in-process decoder are both present. The model downloads lazily, so it is
        deliberately not part of availability."""
        return resolve_whisper_cli() is not None and _decoder_available()

    async def transcribe(self, path: str) -> str:
        if self._cli is None:
            return ""
        model = await _ensure_model()
        if model is None:
            return ""
        try:
            wav = await asyncio.to_thread(_decode_to_wav, path)
        except Exception:
            _logger.warning("stt.decode_failed", exc_info=True)
            return ""
        try:
            return await self._run_cli(model, wav)
        finally:
            with contextlib.suppress(OSError):
                Path(wav).unlink()

    async def _run_cli(self, model: Path, wav: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            out_base = str(Path(tmp) / "out")
            assert self._cli is not None
            proc = await asyncio.create_subprocess_exec(
                self._cli,
                "-m",
                str(model),
                "-f",
                wav,
                "-l",
                "auto",
                "-nt",
                "-otxt",
                "-of",
                out_base,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                await asyncio.wait_for(proc.communicate(), timeout=120.0)
            except TimeoutError:
                proc.kill()
                with contextlib.suppress(Exception):
                    await proc.wait()  # reap the killed child
                _logger.warning("stt.cli_timeout")
                return ""
            if proc.returncode != 0:
                _logger.warning("stt.cli_failed", extra={"code": proc.returncode})
                return ""
            txt = Path(out_base + ".txt")
            return txt.read_text(encoding="utf-8").strip() if txt.exists() else ""


__all__ = ["WhisperCppTranscriber", "resolve_whisper_cli"]
