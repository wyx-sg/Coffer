# Download & Install

This page is the authoritative install guide for Coffer — it is what the installer scripts and
release notes link to. Choose the path that fits your use case:

| Path                                             | Best for                                                        |
| ------------------------------------------------ | --------------------------------------------------------------- |
| [One-line CLI install](#one-line-cli-install)    | The fastest setup on a workstation, a server or a headless box  |
| [Desktop app](#desktop-app)                      | A Dock icon and a tray item instead of a terminal command       |
| [Manual archive download](#manual-archive-download) | Air-gapped machines, pinned versions, or checking signatures yourself |
| [From source](#from-source-developers)           | Contributors and developers working on Coffer itself            |

::: tip Two artifacts, one Coffer
A release publishes the CLI archive `coffer-cli-<triple>.tar.gz` and the desktop app
`Coffer-unsigned-<triple>.dmg`. They carry the **same four binaries** and drive the same
daemon and the same web UI, so the choice is only how you reach it: `coffer open` in a
browser, or a Dock icon. Installing the app installs the CLI too — on first launch it
deploys those binaries into `~/.coffer/bin/`.
:::

::: tip Daemon auto-starts — you never run it manually
Once Coffer is installed, just point your MCP client at `coffer-mcp-shim` and connect. The
daemon starts itself the first time it is needed. This is the core design of
[Detect-or-Spawn](/architecture/processes#detect-or-spawn-adr-daemon-detect-or-spawn). You will never see a
"daemon not running" error from a fresh install.
:::

---

## One-line CLI install

The quickest path to a working Coffer. A single command downloads the release archive and
unpacks its binaries into `~/.coffer/bin`:

- **`coffer`** — management CLI (`coffer mcp add`, `coffer mcp list`, `coffer open`, …)
- **`coffer-daemon`** — the long-lived background process that aggregates upstream MCP servers
  and serves the web UI
- **`coffer-mcp-shim`** — the stdio bridge that MCP clients (Claude Code, Codex, …) talk to

plus the runtime helper binary the daemon spawns for itself (`coffer-callback`, for SeaTalk
channels).

### macOS (Apple Silicon)

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

Coffer ships macOS (Apple Silicon) builds only. On Linux or Intel macOS the
installer stops with a friendly message pointing at the
[from-source install](#from-source-developers).

The script adds `~/.coffer/bin` to your `PATH` automatically (shell profile). Open a new
terminal — all three binaries are available.

### Environment overrides

| Variable                | Effect                                                   |
| ----------------------- | -------------------------------------------------------- |
| `COFFER_INSTALL_DIR`    | Override install directory (default: `~/.coffer/bin`)    |
| `COFFER_VERSION`        | Pin a release, e.g. `v0.1.0` (default: latest)           |
| `COFFER_NO_MODIFY_PATH` | Set to `1` to skip modifying shell profile / environment |

### Verify the download

Every release publishes **one aggregated `SHA256SUMS`** covering every artifact in that
release. The installer verifies the download automatically. To check manually, in the directory
holding the archive and `SHA256SUMS` (`--ignore-missing` skips the artifacts you did not download):

```sh
shasum -a 256 -c SHA256SUMS --ignore-missing
```

### Post-install: connect an MCP client

After the one-line install, the daemon has not started yet — it will auto-spawn on first use:

```sh
# Register Coffer with Claude Code (spawns the daemon on first tool call)
claude mcp add coffer coffer-mcp-shim
```

For other clients, set `command: coffer-mcp-shim` in their config and restart. The daemon
starts automatically the first time the shim receives a connection.

You can also trigger auto-spawn from the management CLI:

```sh
coffer mcp add filesystem --stdio "npx -y @modelcontextprotocol/server-filesystem /tmp"
coffer mcp list
```

Either command auto-starts the daemon if it is not already running.

### Open the web UI

```sh
coffer open
```

This starts a daemon if none is running and opens your browser at the daemon's own address.
You are already signed in: the daemon puts its live API token into the page it serves, so there
is nothing to paste and nothing stored in the browser. See the [Web UI guide](/guide/web-ui).

### Next steps

- [Getting Started](/guide/getting-started) — register your first MCP server and verify the setup
- [Connect a client →](/guide/connect-client) — full client configuration reference

---

## Desktop app

`Coffer-unsigned-<triple>.dmg` on the
[GitHub Releases page](https://github.com/wyx-sg/Coffer/releases/latest) is the same web UI
in a native window: a Dock icon, an entry in Cmd-Tab and Spotlight, and a resident tray item
with **Open Coffer**, a sync status entry, **Restart daemon** and **Quit Coffer**. Closing the
window leaves the app in the tray rather than quitting it, and quitting leaves the daemon
running, because your agents are still using it.

Drag `Coffer.app` into `/Applications` and open it. You do not start a daemon first — the
app resolves one for itself, in a fixed order: an already-running daemon named by
`~/.coffer/daemon.json` is taken over rather than duplicated; otherwise it spawns the
`coffer-daemon` it carries inside its own bundle, or the one in `~/.coffer/bin/`, or one on
your `PATH`. The window appears once a daemon answers, or once the attempt has failed — in
which case it opens on a banner that says why.

The `.dmg` is **self-contained**: it embeds `coffer`, `coffer-daemon`, `coffer-mcp-shim` and
`coffer-callback`, and deploys them into `~/.coffer/bin/` on first launch. Installing the
app therefore installs the CLI as well — add `~/.coffer/bin` to your `PATH` and
`coffer …` and `coffer-mcp-shim` are available in a terminal too.

The app is unsigned and un-notarised, so macOS quarantines it after the drag:

```sh
xattr -dr com.apple.quarantine /Applications/Coffer.app
```

When the UI cannot reach the daemon, the offline banner in the app carries a **Restart**
button (a browser tab cannot offer one: a daemon that is down cannot serve the page). It and
the tray's **Restart daemon** ask a running daemon to shut down and wait for its port to free
before starting a new one, so a daemon that is listening but stuck is really replaced. A second
restart within five seconds of a successful one is refused with the time left; after a failed
start you can retry at once.

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| "Coffer is damaged and can't be opened" | Quarantine attribute on a browser download | `xattr -dr com.apple.quarantine /Applications/Coffer.app` |
| The window opens on the offline banner | No daemon could be found or started | Press **Restart**; the reason is in `~/.coffer/logs/daemon.log`. |
| An MCP server fails with "command not found" only when the daemon was started by the app | An app launched from Finder has a minimal `PATH` | The app reads your login shell's `PATH` (`$SHELL -lc`), so export it from `~/.zprofile`, not only `~/.zshrc`. |
| A warning about mismatched versions | A daemon from a previous install is still running | **Restart daemon** from the tray. |

The app writes its own records — which daemon it found, a restart that failed — into
`~/.coffer/logs/daemon.log` under the logger `coffer.desktop`; there is no separate desktop
log. See [Distribution](/architecture/distribution) for what the shell owns and what it
deliberately leaves to the daemon.

---

## Manual archive download

Go to the [GitHub Releases page](https://github.com/wyx-sg/Coffer/releases/latest) and pick
the artifact for your platform:

| Platform                       | File                            | What it is                                  |
| ------------------------------ | ------------------------------- | ------------------------------------------- |
| macOS Apple silicon (M-series) | `coffer-cli-<triple>.tar.gz`    | The four binaries, for the terminal         |
| macOS Apple silicon (M-series) | `Coffer-unsigned-<triple>.dmg`  | The [desktop app](#desktop-app), carrying the same four |

Coffer ships macOS (Apple Silicon) builds only. On Linux or Intel macOS, use the
[from-source install](#from-source-developers).

Verify the download against the release's aggregated `SHA256SUMS` — it covers every artifact
in the release, the `.dmg` included — then extract it:

```sh
shasum -a 256 -c SHA256SUMS --ignore-missing
tar -xzf coffer-cli-<triple>.tar.gz -C ~/.coffer/bin
```

Keep the four binaries in one directory: a frozen `coffer` looks for `coffer-daemon` beside
itself. Add `~/.coffer/bin` to your `PATH` so MCP clients can find `coffer-mcp-shim`.

### macOS Gatekeeper (unsigned — signing pending)

The binaries are unsigned, so macOS quarantines them on first run. Code signing and
notarisation need a paid Apple Developer ID, which has not been provisioned yet. Clear the
quarantine attribute on everything you extracted — recursively, so the helper binaries are
covered too:

```sh
xattr -dr com.apple.quarantine ~/.coffer/bin
```

For the desktop app it is the bundle you dragged across:

```sh
xattr -dr com.apple.quarantine /Applications/Coffer.app
```

A binary installed by the [one-line installer](#one-line-cli-install) is never quarantined,
so that path skips this step entirely.

### After install

The first time the daemon starts from a frozen build, it deploys its sibling binaries into
`~/.coffer/bin/` (idempotently — unchanged binaries are left alone), so MCP clients can find
the shim and the shim can auto-spawn the daemon. Then:

```sh
claude mcp add coffer coffer-mcp-shim
coffer open
```

---

## From source (developers)

For contributors and developers working on Coffer itself. Gives you the `coffer` CLI and shim
as Python console-script entry points (no PyInstaller, no binary download).

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
uv sync --frozen --extra dev --project backend   # UV_PROJECT_ENVIRONMENT=$PWD/.venv
make verify          # lint + types + unit + integration + contract + acceptance
```

::: warning Use the lockfile, not a fresh resolve
`make install` still runs `pip install -e ./backend[dev]`, which works — but it
**re-resolves** every dependency to whatever is newest and satisfies the range, so the
versions you get are not the versions CI gates against. CI runs
`uv sync --frozen --extra dev --project backend` against the committed `backend/uv.lock`.
If a test passes locally and fails in CI (or the reverse) for no reason visible in the
diff, rebuild the environment with `uv sync --frozen` before looking any further — an
unlocked environment is the usual cause.
:::

::: tip Auto-spawn applies here too
Either install puts `coffer`, `coffer-daemon`, and `coffer-mcp-shim` on your `PATH` as
console scripts. The daemon auto-starts the first time you run a management command or an
MCP client connects — `coffer daemon start` exists for explicit control but is **not** a
required setup step. A source install skips binary deployment entirely: it is not a frozen
build, and the console scripts are already there.
:::

### Prerequisites

- **Python ≥ 3.12** for the from-source install (the release binaries bundle their own).
- **[uv](https://docs.astral.sh/uv/)** — how CI builds the environment, and the only way to
  get exactly the locked dependency set.
- **[ripgrep](https://github.com/BurntSushi/ripgrep)** (`rg`) — recommended, on every install
  path. Coffer's knowledge search (`coffer__grep`, `coffer__search`) runs `rg` when it is on
  your `PATH`; without it Coffer falls back to a slower built-in search that returns the same
  results, and notes the fallback once in the daemon log.

See [Getting Started](/guide/getting-started) for the full from-source walkthrough.
