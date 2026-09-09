# Download & Install

This page is the authoritative install guide for Coffer — it is what the installer scripts and
release notes link to. Choose the path that fits your use case:

| Path                                             | Best for                                                        |
| ------------------------------------------------ | --------------------------------------------------------------- |
| [One-line CLI install](#one-line-cli-install)    | The fastest setup on a workstation, a server or a headless box  |
| [Manual archive download](#manual-archive-download) | Air-gapped machines, pinned versions, or checking signatures yourself |
| [From source](#from-source-developers)           | Contributors and developers working on Coffer itself            |

::: tip There is one download, and it includes the UI
Coffer ships a **single release artifact**: `coffer-cli-<triple>.tar.gz`. There is no separate
desktop application — the daemon serves the web UI itself, and you open it with `coffer open`.
:::

::: tip Daemon auto-starts — you never run it manually
Once Coffer is installed, just point your MCP client at `coffer-mcp-shim` and connect. The
daemon starts itself the first time it is needed. This is the core design of
[ADR-006 (detect-or-spawn)](/architecture/processes#detect-or-spawn-adr-006). You will never see a
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

plus the runtime helper binaries the daemon spawns for itself (`coffer-callback` for SeaTalk
channels, `whisper-cli` for local speech-to-text).

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
release. The installer verifies the download automatically. To check manually:

```sh
shasum -a 256 -c SHA256SUMS
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

This starts your browser at the daemon's own address and hands the page a token via a
single-use, short-lived code. See the [Web UI guide](/guide/web-ui).

### Next steps

- [Getting Started](/guide/getting-started) — register your first MCP server and verify the setup
- [Connect a client →](/guide/connect-client) — full client configuration reference

---

## Manual archive download

Go to the [GitHub Releases page](https://github.com/wyx-sg/Coffer/releases/latest) and pick
the archive for your platform:

| Platform                       | File                                |
| ------------------------------ | ----------------------------------- |
| macOS Apple silicon (M-series) | `coffer-cli-<triple>.tar.gz`        |

Coffer ships macOS (Apple Silicon) builds only. On Linux or Intel macOS, use the
[from-source install](#from-source-developers).

Verify the download against the release's aggregated `SHA256SUMS`, then extract it:

```sh
shasum -a 256 -c SHA256SUMS
tar -xzf coffer-cli-<triple>.tar.gz -C ~/.coffer/bin
```

Add `~/.coffer/bin` to your `PATH` so MCP clients can find `coffer-mcp-shim`.

### macOS Gatekeeper (unsigned — signing pending)

The binaries are unsigned, so macOS quarantines them on first run. Code signing and
notarisation need a paid Apple Developer ID, which has not been provisioned yet. Clear the
quarantine attribute on the extracted binaries:

```sh
xattr -d com.apple.quarantine ~/.coffer/bin/coffer ~/.coffer/bin/coffer-daemon ~/.coffer/bin/coffer-mcp-shim
```

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
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
make verify          # lint + types + unit + integration + contract + acceptance
```

::: tip Auto-spawn applies here too
`pip install` puts `coffer`, `coffer-daemon`, and `coffer-mcp-shim` on your `PATH`. The
daemon auto-starts the first time you run a management command or an MCP client connects —
`coffer daemon start` exists for explicit control but is **not** a required setup step.
:::

See [Getting Started](/guide/getting-started) for the full from-source walkthrough.
