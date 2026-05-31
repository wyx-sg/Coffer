# Download & Install

This page is the authoritative install guide for Coffer — it is what the installer scripts and
release notes link to. Choose the path that fits your use case:

| Path                                          | Best for                                                           |
| --------------------------------------------- | ------------------------------------------------------------------ |
| [One-line CLI install](#one-line-cli-install) | Servers, headless boxes, terminal users who want the fastest setup |
| [Desktop app](#desktop-app)                   | Daily-driver use on a workstation; includes a GUI and Web UI       |
| [From source](#from-source-developers)        | Contributors and developers working on Coffer itself               |

::: tip Daemon auto-starts — you never run it manually
Once Coffer is installed, just point your MCP client at `coffer-mcp-shim` and connect. The
daemon starts itself the first time it is needed. This is the core design of
[ADR-006 (detect-or-spawn)](/architecture/distribution#adr-006). You will never see a
"daemon not running" error from a fresh install.
:::

---

## One-line CLI install

The quickest path to a working Coffer. A single command downloads and unpacks three binaries
into `~/.coffer/bin`:

- **`coffer`** — management CLI (`coffer mcp add`, `coffer mcp list`, …)
- **`coffer-daemon`** — the long-lived background process that aggregates upstream MCP servers
- **`coffer-mcp-shim`** — the stdio bridge that MCP clients (Claude Code, Cursor, …) talk to

### macOS / Linux

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh | sh
```

The script adds `~/.coffer/bin` to your `PATH` automatically (shell profile). Open a new
terminal — all three binaries are available.

### Environment overrides

| Variable                | Effect                                                   |
| ----------------------- | -------------------------------------------------------- |
| `COFFER_INSTALL_DIR`    | Override install directory (default: `~/.coffer/bin`)    |
| `COFFER_VERSION`        | Pin a release, e.g. `v0.1.0` (default: latest)           |
| `COFFER_NO_MODIFY_PATH` | Set to `1` to skip modifying shell profile / environment |

### Verify the download

Every release publishes a `SHA256SUMS` file. The installer verifies the download automatically.
To check manually:

```sh
# macOS
shasum -a 256 -c SHA256SUMS

# Linux
sha256sum -c SHA256SUMS
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

### Next steps

- [Getting Started](/guide/getting-started) — register your first MCP server and verify the setup
- [Connect a client →](/guide/connect-client) — full client configuration reference

---

## Desktop app

The Desktop app bundles everything — daemon, shim, Web UI — in a single installer. No Python
required. Recommended for workstation use.

### Download

Go to the [GitHub Releases page](https://github.com/wyx-sg/Coffer/releases/latest) and pick
the file for your platform:

| Platform                          | File                              |
| --------------------------------- | --------------------------------- |
| macOS Apple silicon (M-series)    | `Coffer_<version>_aarch64.dmg`    |
| Linux x64 (AppImage, recommended) | `Coffer_<version>_amd64.AppImage` |
| Linux x64 (deb)                   | `coffer_<version>_amd64.deb`      |

Each file has a `.sha256` sibling. Verify before running:

```sh
# macOS / Linux
shasum -a 256 -c SHA256SUMS   # or sha256sum -c SHA256SUMS on Linux
```

### Install

- **macOS**: Open the DMG, drag **Coffer.app** to `/Applications`.
- **Linux (AppImage)**: `chmod +x Coffer_<version>_amd64.AppImage`, then run it.
- **Linux (deb)**: `sudo apt install ./coffer_<version>_amd64.deb`.

### macOS Gatekeeper (unsigned — notarisation pending)

The DMG ships unsigned, so on first open macOS may say Coffer is "damaged" (it isn't — it's
just unsigned). For the "damaged" message, right-click → Open does **not** help; clear the
quarantine flag instead:

```sh
xattr -dr com.apple.quarantine /Applications/Coffer.app
```

If it still won't open, re-apply an ad-hoc signature:

```sh
codesign --force --deep --sign - /Applications/Coffer.app
```

Or right-click the app and pick **Open** for a one-time bypass.

### After install

On first launch, the Desktop app:

1. Starts the daemon on a free port (default 8000) and writes `~/.coffer/daemon.json`.
2. Deploys `coffer-mcp-shim` to `~/.coffer/bin/` so MCP clients can find it.
3. Opens the Web UI in the main window.

Connect your MCP client:

```sh
claude mcp add coffer coffer-mcp-shim
```

See [Desktop app →](/guide/desktop) for the full Desktop guide (tray menu, launch at login, etc.).

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
