# ADR-039: Frozen-app speech-to-text via a bundled whisper.cpp sidecar

> 中文版: [ADR-039-frozen-stt-whispercpp.zh.md](ADR-039-frozen-stt-whispercpp.zh.md)

**Status**: Accepted
**Date**: 2026-07-04
**Deciders**: Yuxing Wu
**Related**: spec `009-channels` (FR-022); builds on [ADR-038](ADR-038-channel-media.md) (channel media, the per-agent transcribe seam)

## Context

Spec 009 FR-022 turns an inbound voice message into a transcript for the text-only
agents (Claude Code, Codex) behind the `Transcriber` seam. The source-run engine is
`mlx-whisper` (the optional `[voice]` extra), lazily imported so the dependency stays
optional.

That lazy import defeats the frozen build. PyInstaller scans function bodies, so the
`import mlx_whisper` inside `transcribe.py` drags `torch` + `mlx` + `numba` +
`llvmlite` + `scipy` into **every** `coffer-*` binary (each `collect_submodules("coffer")`
pulls the whole package). The binaries balloon from ~94 MB to ~260 MB, and `torch`
is fragile under PyInstaller. The standing workaround uninstalls `mlx-whisper` before
bundling — so in the frozen desktop app the lazy import fails and voice silently
degrades to "hand the agent the audio file" instead of a transcript. **The shipped
app cannot transcribe voice.**

We want the frozen app to transcribe inbound voice **locally** (Coffer is local-first),
**torch-free**, with **Metal acceleration** on Apple Silicon, while keeping the
binaries lean.

## Decision

**Ship a torch-free `whisper.cpp` sidecar and keep the frozen build lean by
construction; `mlx-whisper` stays the source-run fallback.**

1. **Lean by construction.** Every `coffer-*.spec` that does `collect_submodules("coffer")`
   adds heavy-ML `excludes` (`torch`, `mlx`, `mlx_whisper`, `numba`, `llvmlite`,
   `scipy`, `sympy`, `networkx`, `mpmath`). The `[voice]` extra may now stay installed
   in the build venv and the binaries remain ~95 MB and torch-free.

2. **STT as a sidecar binary**, mirroring `coffer-callback` (ADR/​PR #240): `whisper.cpp`'s
   `whisper-cli` (Apple-Silicon Metal, no Python/torch) is built from a **pinned tag**
   (`v1.9.1`) in `build_binaries.sh`, packaged via Tauri `externalBin`, and deployed to
   `~/.coffer/bin` by `shim.rs` alongside the other sidecars. The daemon resolves it as
   a sibling of its own executable when frozen, or on `PATH` when run from source.

3. **`WhisperCppTranscriber` implements the seam.** It decodes the audio **in-process**
   with `soundfile` (libsndfile handles OGG/Opus — the Telegram voice format — plus
   wav/flac/mp3), resamples to 16 kHz mono with `soxr`, writes a temp WAV, and shells
   out to `whisper-cli`. `soundfile` + `soxr` are the small torch-free `[voice]` extra,
   kept in the frozen build (not excluded). Any missing piece (binary, model, decoder)
   returns `""` so the adapter falls back to handing over the file — the seam never raises.

4. **Model downloaded on first use.** The `ggml-base-q5_1` multilingual model (~57 MB)
   is fetched once to `~/.coffer/models/` (whisper.cpp's `models/` convention), not
   bundled, to keep the DMG lean. Offline on the first voice message degrades to file
   handoff until the model is cached.

5. **Best-available selection.** `default_transcriber()` picks the engine: `whisper.cpp`
   (frozen, or source with a `whisper-cli` on `PATH`) → `mlx-whisper` (source-run
   fallback) → `None`. The seam is unchanged, so the FR-022 acceptance test still drives
   a fake transcriber.

## Alternatives considered

- **`mlx-whisper` as its own frozen sidecar** — keeps the daemon lean but still ships a
  ~260 MB `torch` binary and torch's PyInstaller fragility; it only moves the weight.
  Rejected — it does not solve the stated problem.
- **`faster-whisper` (CTranslate2) frozen sidecar** — torch-free and PyInstaller-friendly,
  with in-process decode via PyAV, but **CPU-only on Apple Silicon** (no Metal/ANE) and a
  ~150 MB sidecar. Rejected — it forfeits the hardware acceleration `whisper.cpp` gets for
  free.
- **`sherpa-onnx` (ONNX Runtime + CoreML EP)** — can reach the ANE, but needs a
  Whisper→ONNX conversion, is less battle-tested for this case, and still needs a
  separate decoder. Deferred.
- **Bundle `ffmpeg` for decode** — universal (m4a/amr/…), but a second heavy binary.
  `soundfile`/libsndfile already decodes the OGG/Opus voice case (verified on
  macOS arm64) plus wav/flac/mp3 in-process. Chosen the lean in-process path; exotic
  formats degrade to file handoff.
- **Ship the model in the bundle** — offline-first but +57 MB DMG. Rejected for a lean
  DMG; download-on-first-use to `~/.coffer/models/` instead.

## Consequences

- The frozen desktop app transcribes inbound voice **locally, torch-free, Metal-accelerated**;
  all `coffer-*` binaries stay ~95 MB even with `[voice]` installed at build time.
- `make bundle-binaries` now needs **`cmake` + network + a one-time C++ build** of
  `whisper.cpp` (pinned, cached under `build/`). CI `desktop-build` and local desktop
  builds must have `cmake` (`brew install cmake`); the script errors clearly when it is
  absent.
- The `[voice]` extra is now the torch-free decode stack (`soundfile` + `soxr`),
  installed into the frozen build venv and bundled into the daemon (small).
  `mlx-whisper` moves to a separate `[voice-mlx]` extra (source-run fallback only) and
  is excluded from the frozen build.
- Audio formats libsndfile cannot decode (e.g. m4a/aac) fall back to file handoff — the
  same graceful path as "transcription unavailable".
- A small model accumulates under `~/.coffer/models/`; retention is a non-issue.
