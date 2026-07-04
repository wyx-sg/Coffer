"""Torch-free whisper.cpp STT engine (spec 009 FR-022 / ADR-039).

The engine shells out to a bundled ``whisper-cli`` and decodes audio in-process.
These tests stay hermetic: the binary resolution, availability, and degrade-to-""
paths are exercised with fakes/monkeypatches, the ``_run_cli`` path with a fake CLI
script, and the real decode path only when ``soundfile``/``soxr`` are installed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from coffer.infrastructure.chat import stt_whispercpp as stt
from coffer.infrastructure.chat.stt_whispercpp import WhisperCppTranscriber


def test_resolve_whisper_cli_finds_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stt.shutil, "which", lambda name: "/opt/bin/whisper-cli")
    assert stt.resolve_whisper_cli() == "/opt/bin/whisper-cli"


def test_resolve_whisper_cli_none_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stt.shutil, "which", lambda name: None)
    assert stt.resolve_whisper_cli() is None


def test_available_false_without_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stt, "resolve_whisper_cli", lambda: None)
    monkeypatch.setattr(stt, "_decoder_available", lambda: True)
    assert WhisperCppTranscriber.available() is False


def test_available_false_without_decoder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stt, "resolve_whisper_cli", lambda: "/opt/bin/whisper-cli")
    monkeypatch.setattr(stt, "_decoder_available", lambda: False)
    assert WhisperCppTranscriber.available() is False


def test_available_true_with_cli_and_decoder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stt, "resolve_whisper_cli", lambda: "/opt/bin/whisper-cli")
    monkeypatch.setattr(stt, "_decoder_available", lambda: True)
    assert WhisperCppTranscriber.available() is True


async def test_transcribe_empty_without_cli() -> None:
    assert await WhisperCppTranscriber(cli=None).transcribe("/x.ogg") == ""


async def test_transcribe_empty_when_model_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_model() -> Path | None:
        return None

    monkeypatch.setattr(stt, "_ensure_model", _no_model)
    t = WhisperCppTranscriber(cli="/fake/whisper-cli")
    assert await t.transcribe("/x.ogg") == ""


def _stage_fake_cli(tmp_path: Path, script: str) -> tuple[Path, Path, Path]:
    """Write an executable fake ``whisper-cli`` plus a dummy model + wav, and return
    (cli, model, wav). The dummy wav lets us monkeypatch ``_decode_to_wav`` so the
    subprocess path is exercised without ``soundfile`` or a real model."""
    cli = tmp_path / "whisper-cli"
    cli.write_text(script)
    cli.chmod(0o755)
    model = tmp_path / "model.bin"
    model.write_bytes(b"x")
    wav = tmp_path / "in.wav"
    wav.write_bytes(b"RIFF")
    return cli, model, wav


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX fake-cli shell script")
async def test_run_cli_reads_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A fake `whisper-cli` that mirrors the real one's `-of <base>` contract:
    # it writes `<base>.txt` and exits 0 — no model download, no decoder needed.
    cli, model, wav = _stage_fake_cli(
        tmp_path,
        "#!/bin/sh\n"
        "while [ $# -gt 0 ]; do\n"
        '  if [ "$1" = "-of" ]; then shift; printf "hello from fake" > "$1.txt"; fi\n'
        "  shift\n"
        "done\n",
    )

    async def _model() -> Path:
        return model

    monkeypatch.setattr(stt, "_ensure_model", _model)
    monkeypatch.setattr(stt, "_decode_to_wav", lambda path: str(wav))

    text = await WhisperCppTranscriber(cli=str(cli)).transcribe("/voice.ogg")
    assert text == "hello from fake"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX fake-cli shell script")
async def test_run_cli_empty_on_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli, model, wav = _stage_fake_cli(tmp_path, "#!/bin/sh\nexit 3\n")

    async def _model() -> Path:
        return model

    monkeypatch.setattr(stt, "_ensure_model", _model)
    monkeypatch.setattr(stt, "_decode_to_wav", lambda path: str(wav))

    assert await WhisperCppTranscriber(cli=str(cli)).transcribe("/voice.ogg") == ""


def test_decode_to_wav_produces_16k_mono(tmp_path: Path) -> None:
    sf = pytest.importorskip("soundfile")
    pytest.importorskip("soxr")
    import numpy as np

    sr = 48000
    n = int(sr * 0.3)
    sig = (0.1 * np.sin(2 * np.pi * 440 * np.arange(n) / sr)).astype("float32")
    ogg = tmp_path / "voice.ogg"
    sf.write(str(ogg), sig, sr, format="OGG", subtype="OPUS")

    wav = stt._decode_to_wav(str(ogg))
    try:
        data, out_sr = sf.read(wav, always_2d=False)
        assert out_sr == stt._SAMPLE_RATE == 16000
        assert data.ndim == 1  # downmixed to mono
    finally:
        os.unlink(wav)
