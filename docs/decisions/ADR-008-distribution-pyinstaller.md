# ADR-008: Distribution — PyInstaller-Bundled Daemon, Shim, and CLI

**Status**: Accepted
**Date**: 2026-05-20 (revised 2026-09-09; see Revision history)
**Deciders**: Yuxing Wu
**Related**: `.specify/memory/constitution.md` (Languages), spec `001-mcp-gateway` (FR-022, SC-009), [ADR-006](ADR-006-daemon-detect-or-spawn.md)

## Context

Coffer has three runnable entry points: the long-lived `coffer-daemon`,
the per-MCP-session `coffer-mcp-shim`, and the `coffer` management CLI.
The target user population includes users without a system Python
install. Spec `001-mcp-gateway` commits to this:

- **SC-009** — A user on a clean machine (no Python) reaches `status: ready`
  from a single distributable with no manual steps beyond clicking through
  the installer.

**FR-022** fixes the shape of that distributable: one release archive
per tag, `coffer-cli-<triple>.tar.gz`, carrying every runnable binary.

That rules out any approach that requires users to install Python,
maintain a virtualenv, or recover from wheel-build errors. We need to
decide how Python code is delivered to end users.

## Decision

**PyInstaller-built daemon, shim, and management CLI, shipped as a single
download tier from one CI release job.**

Concrete choices:

- `backend/coffer-daemon.spec` builds `dist/coffer-daemon` (single-file
  executable). `backend/coffer-mcp-shim.spec` builds `dist/coffer-mcp-shim`.
  The `coffer` management CLI is built the same way.
- `make bundle-binaries` (driven by `scripts/build_binaries.sh`) runs
  PyInstaller on the current host; the release CI job invokes the same
  script on a macOS arm64 runner.
- Each spec pins the `hiddenimports` empirically required at runtime —
  FastAPI, SQLAlchemy 2 / aiosqlite, Pydantic 2, `mcp`, `keyring`, and
  (daemon only) Alembic. The list is recorded in
  `specs/001-mcp-gateway/research.md`.
- Alembic migrations ship as data files inside the daemon binary so
  first-launch can run `upgrade head` against a fresh DB.
- sqlite-vec's loadable native extension (`vec0.dylib`/`.so`/`.dll`) ships
  as a data file too (`collect_data_files("sqlite_vec")`) — it is package
  data, not a Python submodule, so `collect_submodules` alone misses it.
  Without it a frozen build loses the vec0 extension and vector retrieval
  silently degrades to keyword-only (`VecIndex.available()` swallows the
  load failure). The KB/memory/chat deps added by specs 006/007/008
  (`sqlite_vec`, `markitdown`, `openai`, `langgraph`, `langchain`) are
  imported lazily, so they are pinned in `hiddenimports` for the same
  reason. The bundle smoke test (`scripts/smoke_test_bundle.sh`) probes
  `coffer-daemon --check-vec` so a build that lost the extension fails
  instead of shipping quietly.
- The shim binary deliberately excludes server-side heavy dependencies
  (FastAPI, uvicorn, SQLAlchemy, Alembic, structlog) to keep its size
  manageable — the shim talks to the daemon over loopback HTTP and only
  needs `httpx`.
- The daemon also serves the built web UI as static files at its own
  loopback origin (spec 001 FR-024), so the web assets ride along inside
  the daemon binary rather than in a separate shell. There is no separate
  GUI artifact to build, sign, or install.
- **The daemon deploys its sibling binaries on a frozen start**
  (spec 001 FR-026). When `coffer-daemon` detects it is running from a
  frozen build, it idempotently copies its siblings — `coffer-mcp-shim`,
  `coffer-callback`, and `whisper-cli` — into `~/.coffer/bin/`, using an
  atomic temp-copy-then-rename and a 3-signal staleness check (byte size,
  mtime, version sentinel). This makes MCP clients able to resolve the
  `command: coffer-mcp-shim` config, and it keeps a `coffer-daemon`
  sibling next to the shim so the frozen shim's detect-or-spawn
  ([ADR-006](ADR-006-daemon-detect-or-spawn.md)) finds a daemon to start
  after a reboot. The daemon is the natural owner because it is the
  process that spawns `coffer-callback` and `whisper-cli` at runtime.
  `~/.coffer/bin/` co-locates with the daemon's `~/.coffer/daemon.json`
  from [ADR-006](ADR-006-daemon-detect-or-spawn.md), which simplifies the
  user mental model ("everything Coffer lives under `~/.coffer/`"). A
  source install needs none of this — `pip install` already puts the
  console scripts on `PATH` (spec 001 FR-018).
- macOS Apple codesigning and notarisation are deferred (they require a
  paid Apple Developer ID). Gatekeeper quarantine therefore still applies
  to the downloaded CLI archive; the current user-visible workaround is
  `xattr -d com.apple.quarantine` on the extracted binaries. Codesigning
  and notarising the CLI binaries is the open follow-up.

## Consequences

**Positive**

- Satisfies SC-009 and FR-022 from day one: `make bundle-binaries`
  produces single-file executables that run on a clean machine with
  no Python.
- Same binaries work for command-line invocation, MCP-client spawn, and
  direct download. No multiple distribution paths to maintain.
- Cross-platform consistency: the same PyInstaller specs work on macOS,
  Windows, and Linux unchanged (only `--target-arch` differs per host),
  so re-widening the release matrix is a CI change, not a redesign.
- The shim binary stays small because it excludes server-side
  dependencies — important for MCP clients that re-spawn the shim
  every session.
- Updating is cheap: replace the binaries, restart the daemon, hard-refresh
  the browser. There is no separate GUI artifact that can drift from the
  source it was built from.
- Forward-compatible with optional "system service install" (an
  [ADR-006](ADR-006-daemon-detect-or-spawn.md) follow-up): launchd, systemd, and Windows service
  configs all point at the same binary paths.

**Negative**

- Bundle size ≈ 80–120 MB per platform (Python interpreter + httpx +
  SQLAlchemy + aiosqlite + keyring + Pydantic + structlog + Typer + …).
  Larger than a comparable native binary but acceptable for a
  developer-targeted tool.
- PyInstaller cold-start is ~500–800 ms (vs ~100 ms for system Python).
  The daemon starts once per OS-login and lives long; the shim starts
  once per MCP-client startup. Both fit within human-perceivable
  tolerance.
- CI maintenance overhead: every dependency upgrade must be validated on
  a real frozen build, not only against the source tree. Mitigated by the
  post-build smoke test.
- macOS Gatekeeper friction until codesigning and notarisation are added.
  The current user-visible workaround is `xattr -d com.apple.quarantine`
  on the extracted binaries.
- PyInstaller has known sharp edges around hidden imports (especially
  for Pydantic v2 and SQLAlchemy 2). Mitigation: explicit `hiddenimports`
  lists in the PyInstaller specs, validated by a CI smoke test
  ([`scripts/smoke_test_bundle.sh`](../../scripts/smoke_test_bundle.sh) — boots the bundled daemon to
  `status: ready` and exchanges a JSON-RPC `initialize` with the bundled
  shim).

**Operational follow-ups**

- Per `v*` tag the CI release job produces exactly one archive —
  `coffer-cli-<triple>.tar.gz` for macOS arm64, containing `coffer`,
  `coffer-daemon`, `coffer-mcp-shim` and the runtime helper binaries
  (`coffer-callback`, `whisper-cli`) — plus one aggregated `SHA256SUMS`
  file covering every published artifact (spec 001 FR-022 / FR-023).
- Before every release, the bundle runs a post-build smoke test
  ([`scripts/smoke_test_bundle.sh`](../../scripts/smoke_test_bundle.sh))
  — must boot the bundled daemon to `status: ready` and let the bundled
  shim exchange a JSON-RPC `initialize` over loopback.
- The shim binary path is exposed to the user via `coffer daemon status`
  (and in the daemon-served web UI) so it can be pasted into MCP-client
  config.

## Alternatives Considered

**Require system Python 3.12+ with a venv (`pip install coffer`).**
Rejected.

- Directly violates SC-009. Most macOS users with a designer /
  non-developer background, and most Windows users, do not have a working
  Python install at the required version.
- Even on Linux, distro-shipped Python is typically one major version
  behind ours; users hit wheel-build errors for `aiosqlite` or
  `pydantic-core`.
- The contributor-facing path (`pip install -e ./backend`) stays
  in the docs — but it is not the end-user distribution channel.

**Nuitka or PyOxidizer instead of PyInstaller.** Rejected for v0.

- PyInstaller has the broadest support for our dependency set (FastAPI,
  SQLAlchemy async, `mcp`, `keyring` backends) and the largest community
  cookbook for hidden imports. Nuitka's AOT compilation is appealing
  but lengthens the build cycle and pulls platform-specific compilers
  into CI.
- Switching packager later is a bounded reversible change: nothing in
  the daemon's runtime contract is PyInstaller-specific.

**Multiple download tiers (a GUI installer alongside the CLI archive).**
Rejected.

- A second tier means a second artifact to build, verify, and keep in
  step with the first. The single `coffer-cli-<triple>.tar.gz` tier is
  what ships: it runs headless on a server and, because the daemon serves
  the web UI itself, it is also the complete graphical install.
- For developers working from a checkout, `pip install -e ./backend`
  remains the documented path; they entirely bypass PyInstaller.

## Revision history

- **2026-05-20** — Initial decision (spec 001 era): PyInstaller binaries,
  universal macOS binary planned, shim path under
  `~/Library/Application Support/Coffer/bin/` on macOS.
- **2026-05-28** (PR #28) — Revised for implementation reality:
  (a) two separate per-arch macOS artifacts instead of a universal binary
  (the release pipeline does not run `lipo`); (b) shim path on macOS / Linux
  moved to `~/.coffer/bin/` to co-locate with `~/.coffer/daemon.json`
  from ADR-006; (c) explicit per-release artifact count with a SHA-256
  checksum each; (d) cross-links to [`scripts/build_binaries.sh`](../../scripts/build_binaries.sh)
  and [`scripts/smoke_test_bundle.sh`](../../scripts/smoke_test_bundle.sh)
  restored.
- **2026-05-30** — CLI tier expanded: the release now ships **three**
  PyInstaller binaries — `coffer` (management CLI) added alongside
  `coffer-daemon` + `coffer-mcp-shim`. The `coffer` management CLI, previously
  only available via `pip install -e ./backend`, is now a first-class part of
  the CLI tier. The archive (`coffer-cli-<triple>.tar.gz`) is installed via a
  one-line script (`install.sh`, served from
  `https://wyx-sg.github.io/Coffer/`) into `~/.coffer/bin`; the script also
  adds `~/.coffer/bin` to `PATH` automatically. Env overrides available:
  `COFFER_INSTALL_DIR`, `COFFER_VERSION`, `COFFER_NO_MODIFY_PATH`.
- **2026-06-05** — Shipping scope narrowed to **macOS (Apple Silicon) only**.
  The Linux and Windows release matrix legs were never validated end-to-end,
  so they are dropped from `release.yml` rather than shipped untested. The
  PyInstaller mechanism here is unchanged and platform-agnostic; the other
  targets can be re-enabled once each is actually tested.
- **2026-06-12** — Binary deploy now covers **both** the shim and the
  daemon in the user bin dir: `coffer-daemon` is copied to `~/.coffer/bin/`
  alongside `coffer-mcp-shim` (same idempotent atomic-replace +
  version-sentinel logic), so the frozen shim's ADR-006 sibling probe finds
  a daemon to auto-spawn after a reboot.
- **2026-09-09** — **The desktop shell was removed and this ADR became a
  pure PyInstaller distribution decision.** The judgement was about the
  operating cost of every update, not lines of code: each desktop update
  required a rebuild plus a reinstall, and the built artifact kept
  diverging from source. Two incidents are on record — a build made before
  fetching produced an app running stale code, and a separately-pinned
  build directory meant UI bug reports had to be re-verified against `main`
  before they could be trusted. The web form has neither failure mode:
  restart the daemon, hard-refresh the browser, and you are on the current
  code. (Supporting datum: 7 of the 15 commits under `desktop/` were fixes,
  the highest ratio in the project — though all during the build-out, and
  the tree had been unchanged for two months. So this removed a recurring
  operating tax, not an actively bleeding wound.) Concretely:
  (a) the Tauri-sidecar half of the decision is gone — `bundle.externalBin`,
  sidecar triple-suffix naming, `desktop/tauri.conf.json`, and the
  DMG / MSI / AppImage / deb bundles no longer exist;
  (b) the release collapsed to a **single tier** — one
  `coffer-cli-<triple>.tar.gz` per `v*` tag plus one aggregated
  `SHA256SUMS` covering every artifact (spec 001 FR-022 / FR-023), with the
  `.dmg` and `Coffer-unsigned-<triple>.app.zip` retired;
  (c) binary deployment into `~/.coffer/bin/` **moved into the daemon's
  frozen-start path** (spec 001 FR-026), keeping the same atomic
  temp-copy-then-rename and the same 3-signal staleness check, and now also
  covering `coffer-callback` and `whisper-cli`;
  (d) the macOS notarisation runbook (`docs/distribution/macos-notarization.md`)
  was deleted — every step in it was `cargo tauri build` / `.dmg` signing
  and stapling for a pipeline that no longer exists; Gatekeeper quarantine
  on the CLI archive and the `xattr -d com.apple.quarantine` workaround are
  now noted inline above.
  Spec 003 (MCP Gateway Desktop) is retired; its two surviving
  release-pipeline requirements folded into spec 001.
