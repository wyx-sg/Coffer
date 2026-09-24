# Distribution

::: tip Core anchor
Coffer ships **one set of binaries in two wrappers**, published per `v*` tag alongside a single aggregated `SHA256SUMS`: a `coffer-cli-<triple>.tar.gz` archive of PyInstaller binaries, and a `Coffer-unsigned-<triple>.dmg` desktop app that embeds the very same four binaries. Neither requires a Python installation on the user's machine. The management UI is one web UI that the **daemon itself serves**; the desktop app renders that same UI in a native window rather than shipping a second frontend.
:::

## The problem this solves

Coffer's daemon and shim are Python applications. The target user population includes developers who do not have Python 3.12 installed at all, and end-users on macOS who have only the system Python (typically one or two versions behind). Asking these users to `pip install coffer` and manage a virtual environment would immediately disqualify Coffer as a daily-driver tool.

The requirement, stated precisely in the spec: a user on a clean machine with no Python can reach `status: ready` from a single downloadable artifact with no manual steps beyond extracting it.

## The desktop shell, and what it owns

Coffer ships a Tauri 2 desktop application (`desktop/`) that renders the web UI in a native window. It was retired on 2026-09-09 and **restored on 2026-09-12**, and both halves of that history matter.

The retirement's reasoning was about **the operating cost of every update**, and it was sound: every change had to travel through a rebuild _and_ a reinstall before it could be seen, and the built artifact kept drifting from source. Two incidents are on the record — a build produced before fetching shipped an app quietly running stale code, and an app built from a separately pinned directory made UI bug reports untrustworthy until re-verified against `main`.

What the retirement did not weigh is that the shell was also the only thing that made Coffer **reachable**. Three months of daemon-served web UI surfaced the cost: a `127.0.0.1` tab is one of dozens, with no Dock icon and nothing resident to click; reaching the UI at all meant knowing that a daemon has to be running, on which port, and that `coffer open` answers both.

So the shell came back owning **only** what a browser cannot do for itself, which is a much smaller shell than the one that was removed — the intervening three months had moved most of its old work somewhere better (binary deployment into the daemon's frozen-start path, native folder-picking and file-revealing onto daemon HTTP routes). What is left, one module per concern under `desktop/src/`:

| Concern                  | Module                                | What it does                                                                                                   |
| ------------------------ | ------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| A window that exists     | `lib.rs`                              | A 1200×800 Tauri window with a Dock icon and an entry in Cmd-Tab.                                              |
| Something resident       | `tray.rs`                             | A tray icon with **Open Coffer**, a **Sync** entry (badged when the vault needs attention), **Restart daemon** and **Quit**; closing the window hides to the tray. |
| Detect-or-spawn          | `resolve.rs`, `discovery.rs`, `spawn.rs`, `env_path.rs` | The five-step chain below, and the `$PATH` a spawned daemon inherits.                        |
| Restart policy + handshake | `daemon.rs`                         | The three IPC commands the webview calls, rate-limited, plus the credential handshake a locally-hosted page cannot get any other way. |
| Finding the binaries     | `sidecar.rs`                          | Locating a binary Tauri staged inside the app bundle.                                                          |

**The five-step resolution chain** (order is correctness, not preference):

1. An already-running daemon named by `~/.coffer/daemon.json` — **taken over, never re-spawned**.
2. A `coffer-daemon` inside the app bundle (`externalBin`).
3. `~/.coffer/bin/coffer-daemon`, where the daemon's own frozen-start path deploys it.
4. `coffer-daemon` on `$PATH`.
5. Otherwise, a message telling the user to install the Coffer CLI.

The liveness probe has to come first. Steps 2–4 all answer *which binary would we spawn*; step 1 answers a different question — *whether to spawn at all*. Asked the other way round, a bundled build opens a second daemon beside the one the user already started from the CLI, and under the fixed-port default (see [Daemon & processes](/architecture/processes)) that second daemon cannot bind and refuses to start. The symptom would be an error on an app that should simply have attached to what was already there.

**The shell hosts the UI; it does not reimplement it.** `tauri.conf.json` keeps `frontendDist: ../frontend/dist`, so the window loads the built SPA as a **local asset** rather than `http://127.0.0.1:<port>/`. That is what makes it a native app instead of a bookmarked browser window: the UI is rendered before the daemon answers, so a daemon that is slow, absent or wedged produces a real page with an actionable banner rather than a connection error. It also makes the port invisible to the UI — only API calls carry it, read from the same `~/.coffer/daemon.json` every other client reads.

Because the page is a local asset, nobody injected a token into it, so the browser's mechanism cannot apply. The shell supplies the same two globals through an IPC command instead:

```
browser  → daemon injects window.__COFFER_TOKEN__ into index.html
Tauri    → shell invokes get_daemon_info → setDaemonConnection(…)
```

Both hosts converge on the same globals, which is why this is a second *supplier* and not a second *path*. The handshake runs alongside the first render and never before it — it may have to spawn a daemon and poll, and blocking would put an empty window in front of the user for exactly as long as that takes.

What the shell deliberately does **not** own: deploying helper binaries, and native file actions (folder picking, opening a file in an editor, revealing it in Finder). Both are the daemon's, reached over loopback HTTP, which a webview does exactly as a browser tab does. The frontend has no `isTauri()` fan-out for them, and only two affordances are host-gated — a **restart control on the offline banner** (impossible in a browser, where a down daemon cannot serve the page the button would live on) and a **daemon version-skew check** (the app pairs with a daemon; a browser has no such pairing).

## Developer install path

Developers who work from a source checkout bypass PyInstaller entirely. `make install` does this:

```bash
pip install -e ./backend[dev]
```

CI does **not**. It resolves against the committed lockfile instead:

```bash
uv sync --frozen --extra dev --project backend   # UV_PROJECT_ENVIRONMENT=$PWD/.venv
```

The difference is worth knowing before you debug a failure that only happens on your machine: `pip install -e` re-resolves every dependency to whatever is newest and satisfies the range, so a local environment is *not* the set of versions CI gates against. `--frozen` installs exactly `backend/uv.lock`. When a test passes locally and fails in CI (or the reverse) for no reason you can see in the diff, rebuild the environment with `uv sync --frozen` before looking any further.

Either way, two console-script entry points land on the developer's `PATH`:

- **`coffer`** — the management CLI (Typer application in `surfaces/cli/`)
- **`coffer-mcp-shim`** — the per-MCP-session stdio shim (`surfaces/shim/`)

The daemon runs directly as a Python process: `coffer daemon start` invokes the FastAPI/uvicorn startup path inside the installed package. No binary packaging, no build step. Changes to the Python source are visible immediately, and a source install needs no binary deployment at all — `pip install` has already put the console scripts on `PATH`.

This developer path is well-documented and remains the primary contribution path. It is **not** the end-user distribution channel — the PyInstaller binaries serve that role.

## PyInstaller: standalone binaries

For end-user distribution, `make bundle-binaries` (driven by `scripts/build_binaries.sh`) runs PyInstaller on the current host against these spec files:

| Spec file                      | Output binary          | Includes                                                                                                                                                                                                                  |
| ------------------------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/coffer-daemon.spec`   | `dist/coffer-daemon`   | FastAPI, SQLAlchemy 2 / aiosqlite, Pydantic 2, `mcp`, `keyring`, Alembic, structlog, Typer, uvicorn, `tomlkit` / `yaml` (agent config editing), `markitdown`, `openai` (provider calls + remote transcription), and the internal-engine stack (`langchain*` / `langgraph`) |
| `backend/coffer-mcp-shim.spec` | `dist/coffer-mcp-shim` | `httpx` only (shim is a thin loopback forwarder)                                                                                                                                                                          |
| `backend/coffer.spec`          | `dist/coffer`          | the management CLI (Typer app)                                                                                                                                                                                            |

PyInstaller bundles the Python interpreter, all dependencies, and the application code into a single-file executable. The user runs `coffer-daemon` directly; no `python` command, no `venv`, no `pip`. The shim binary is deliberately lean — it excludes all server-side dependencies because the shim only needs `httpx` to forward requests to the daemon over loopback HTTP. MCP clients that re-spawn the shim every session benefit from the shorter cold-start time a smaller binary provides.

Alongside these, the release archive carries the **runtime helper binaries** the daemon spawns as child processes: `coffer-callback` (the SeaTalk callback listener, `surfaces/callback/`, spawned while a SeaTalk channel on webhook delivery is enabled). In a source/dev run the daemon spawns the callback listener as `python -m coffer.surfaces.callback`; in a frozen build `listener_spawn.py` looks for a `coffer-callback` sibling next to the daemon binary. This sibling relationship is exactly why the daemon — not an installer — owns deploying these binaries (see [Binary deployment at frozen start](#binary-deployment-at-frozen-start)).

Alembic migration files ship as data files inside the daemon binary via PyInstaller's `datas` mechanism. On first launch, the daemon runs `alembic upgrade head` against a fresh database before accepting connections — the end-user gets correct schema creation with no separate step.

The daemon binary also bundles the heavier knowledge and engine dependencies: `markitdown` for document conversion, `openai` for the OpenAI-compatible provider calls and remote speech-to-text, and the `langchain*` / `langgraph` stack that Coffer's **internal engine** runs the knowledge curation and memory distil passes on. (None of these drives a chat persona — Coffer has none; chat drives the user's own Claude Code and Codex agents.) All of them are imported lazily inside functions, so PyInstaller's static analysis cannot trace them — `coffer-daemon.spec` declares them explicitly as hidden imports so the frozen daemon can convert documents, transcribe audio and run its unattended passes.

The built web UI also ships as data files inside the daemon binary, which is what lets the frozen daemon serve the UI from its own origin.

::: warning Bundle verification — the web UI is a data file
`coffer-daemon.spec` folds `frontend/dist` in as `webui/` **only if `index.html` is already there when PyInstaller runs**. Build the binaries without building the frontend first and the result is a daemon that serves an API and no interface — a build that fails nothing, reports `status: ready`, and answers `--version` perfectly well. The release smoke test therefore asks the running daemon for its root and requires a hashed `assets/index-*.js` reference back, which proves the data files reached the archive, `webui.resolve_webui_dir()` found them inside the bundle, and the route serves them.
:::

::: tip Why PyInstaller, not alternatives
Two alternatives were explicitly considered and rejected for v0:

- **Nuitka / PyOxidizer**: AOT compilation produces smaller and faster binaries, but lengthens the build cycle significantly and requires platform-specific compilers in CI. Switching packager later is a bounded, reversible change — nothing in the daemon's runtime contract is PyInstaller-specific.
- **Requiring system Python**: directly violates the requirement that a user with no Python can install Coffer. Even on Linux, the distro-shipped Python is typically one version behind; users encounter wheel-build errors for `aiosqlite` or `pydantic-core`.
  :::

## One set of binaries, two wrappers

Every release publishes one binary set in two wrappers, and the wrappers carry *the same four files* — the `.dmg` is a copy of `dist/`, not a second PyInstaller run, because freezing these takes the better part of an hour and it is already done.

`coffer-cli-<triple>.tar.gz` contains:

- `coffer` (the management CLI)
- `coffer-daemon` (standalone executable, with the built web UI inside it)
- `coffer-mcp-shim` (standalone executable)
- the runtime helper binary the daemon spawns — `coffer-callback`

`Coffer-unsigned-<triple>.dmg` contains `Coffer.app`, whose `externalBin` entries stage those same four binaries inside the bundle. On first launch the app starts its bundled daemon, whose frozen-start path deploys them into `~/.coffer/bin/`, so **installing the app installs the CLI**.

The archive is what a headless server, a CI environment or a terminal-first workstation wants: extract, run `coffer-daemon` (or `coffer daemon start`), and open the UI with `coffer open` — on a headless box you simply never open it. The `.dmg` is what a workstation wants when the terminal is not the way in.

Instead of a per-file `.sha256` sidecar file, the release publishes **one aggregated `SHA256SUMS`** covering every artifact in the release, the `.dmg` included, so a single `shasum -c SHA256SUMS` verifies the whole download set.

## The daemon serves the web UI

The daemon serves the built web UI itself, as static files, at its own loopback origin. The UI and the REST API are therefore **same-origin**: the page is fetched from `http://127.0.0.1:<port>/` and calls `http://127.0.0.1:<port>/api/v1/`. This is the browser host. The desktop shell is the other host — it loads the same `frontend/dist` as a local asset — and the frontend has no build-time branching for "am I inside a desktop shell": one build, two suppliers of the connection globals.

Because the daemon serves the document, the response body is a channel to the browser, and that is where the credential travels: the daemon injects its live API token into the `index.html` it serves, as a `window.__COFFER_TOKEN__` global in the head. Every route that resolves to that document gets it — the bare `/` and every client-side route served through the SPA fallback — and the document is served `Cache-Control: no-store` with no ETag or Last-Modified, because a cached copy would hand a restarted daemon's browser the previous daemon's dead token. Hashed files under `/assets` keep normal caching.

`coffer open` therefore carries no credential at all. What it still does is read the daemon's real port from `~/.coffer/daemon.json` (mode `0600`) and open the browser at that origin, spawning a daemon first if none is running. The port is `8000` unless the user pinned another one, and reading it from the discovery file rather than assuming the default is what keeps `coffer open` correct either way.

The token never appears in a URL, and the page persists nothing. Putting it in a URL would write it into browser history, which contradicts Coffer's loopback-plus-token posture; persisting it would outlive the daemon that minted it, which was the previous design's failure. What makes serving it in the body safe is the `Host` check — see [Security](/architecture/security).

Because the UI is same-origin with the API, CORS is **same-origin by default**. The Vite dev-server origins remain available behind the existing `COFFER_DEV_CORS` opt-in for frontend development. See [Security](/architecture/security) for the full posture.

## Binary deployment at frozen start

Deploying `coffer-mcp-shim` onto the user's `PATH` was the desktop shell's job in its first incarnation. It is the daemon's now, and stayed the daemon's when the shell returned — the shell is explicitly forbidden from doing it, because two processes writing `~/.coffer/bin/` race. The daemon does it at startup, and only when it detects that it is running as a frozen build. Four binaries are deployed: `coffer`, `coffer-daemon`, `coffer-mcp-shim`, `coffer-callback`. `coffer` is on that list precisely so a user who installed only the `.dmg` has the management CLI on disk after the first launch.

**Each build lands in its own directory, and the public names are symlinks into it:**

```
~/.coffer/bin/coffer-daemon  ->  0.2.0/coffer-daemon
~/.coffer/bin/0.2.0/coffer-daemon   (+ a .coffer-daemon.version sentinel)
~/.coffer/bin/0.1.1/coffer-daemon   (the previous build, kept)
```

The paths callers use (`~/.coffer/bin/<name>`) never change. What the layout buys is that a deploy **never overwrites a binary the user may be running or may need to go back to**: the new build is copied beside the old one and the symlink is flipped atomically, so a bad build is undone by pointing the link at the previous directory. The two newest version directories survive; older ones are pruned once a newer deploy lands, and a directory any live symlink still resolves into is never removed.

Staleness is **two signals — byte size and the version sentinel**, which is written *after* the copy completes, so a sentinel present means a complete copy. mtime is deliberately not one of them: a build's mtime says when it was extracted, not what it contains, and comparing it re-copied every binary on every start after a reinstall of the same release.

One more thing rides this path: before `alembic upgrade head` changes an on-disk `coffer.db`, the daemon copies it (with any `-wal` / `-shm` companions) to `coffer.db.pre-<revision>`, keeping the three newest. An already-current schema and an in-memory database are not copied.

The daemon is the natural owner of this step because it is the process that actually spawns `coffer-callback` at runtime and needs it at a known sibling path. A source install skips deployment entirely — it is not a frozen build, and `pip install` has already put the console scripts on `PATH`.

The desktop app's bundled daemon deploys the same four binaries on first launch, for the same reason in reverse: a user who only ever double-clicks `Coffer.app` still needs `coffer-mcp-shim` on disk at a path an MCP client can be pointed at.

## Release pipeline

The CI release workflow (`.github/workflows/release.yml`) runs on every `v*` tag and produces, per built target — currently macOS arm64 — the CLI archive, the `Coffer-unsigned-<triple>.dmg`, and the aggregated `SHA256SUMS` over both. The `.dmg` step stages `dist/` into `desktop/binaries/<name>-<triple>` (where `externalBin` looks for it), runs the npm-published Tauri CLI, and then *fails the release* if no `.dmg` turned up under `desktop/target/<triple>/release/bundle/dmg` — a missing bundle is signal, not noise.

macOS x64 (Intel) and Windows are not built: GitHub's Intel macOS runner pool is being deprecated and reliably starves the `macos-13` job (it sits "waiting for a runner" indefinitely), and PyInstaller cannot cross-compile x86_64 binaries from the arm64 runner.

Before PyInstaller runs, the workflow stamps the build's release channel with `scripts/stamp_channel.py stable`, rewriting the one line of `coffer/build_channel.py` that says `dev` in the repository. Only a tagged release is therefore `stable`, with its [experimental features](/guide/experimental-features) off by default; every other build — a source install, `make desktop` — is `dev`.

Before upload, the archive runs a post-build smoke test (`scripts/smoke_test_bundle.sh`): the script boots the bundled `coffer-daemon` to `status: ready` and has the bundled `coffer-mcp-shim` exchange a JSON-RPC `initialize` message with it over loopback. A non-zero exit from the smoke test fails the release. The script uses a backgrounded watchdog rather than GNU `timeout`, so it runs cleanly on macOS.

## macOS Gatekeeper

macOS Gatekeeper quarantines downloaded, unsigned executables on first run. Code-signing and notarisation — Apple's process for attesting that a binary is free of known malware — are currently a non-goal for Coffer: they require a paid Apple Developer ID, which has not been provisioned.

Until one is, users clear the quarantine attribute recursively on whatever they installed — the directory they extracted the archive into, or the app bundle they dragged across:

```bash
xattr -dr com.apple.quarantine <extracted-directory>
xattr -dr com.apple.quarantine /Applications/Coffer.app
```

The `.dmg` filename says `unsigned` for the same reason: a downloader should know before Gatekeeper tells them. A binary installed by the one-line installer is never quarantined, so that path skips this step.
