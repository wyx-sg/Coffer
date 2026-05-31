# Desktop App

The Coffer Desktop app is the recommended installation path for daily-driver use. It
packages everything you need — the daemon, the shim, and the Web UI — in a single
installer with no Python required.

## What the Desktop app is

The Desktop app is a **Tauri 2** shell (Rust + WebView) that bundles the Coffer daemon
and MCP shim as PyInstaller-built sidecar binaries. Because the binaries are
self-contained, end users need no Python install. The Web UI from
[spec 002](/reference/specs/002-ui-shell/spec) renders inside the Tauri window.

See [Architecture → Distribution](/architecture/distribution) for the two-tier release
design (CLI-only archive vs. CLI+desktop bundle) and the ADR behind it.

## How it runs

On every launch the Desktop app:

1. **Detects or spawns the daemon** — it reads `~/.coffer/daemon.json` to find a running
   daemon. If none is reachable, it spawns `coffer-daemon` as a detached background process
   that survives the Desktop window closing.
2. **Deploys the shim** — idempotently copies the bundled `coffer-mcp-shim` to a stable
   user-writable PATH location:
   - macOS / Linux: `~/.coffer/bin/coffer-mcp-shim`
3. **Shows a system-tray icon** — always present while the app is running.

Closing the main window **hides** it to the tray; the daemon stays alive and your MCP
clients keep working. To actually quit, use **Quit** from the tray menu.

### Tray menu

| Item               | What it does                                                          |
| ------------------ | --------------------------------------------------------------------- |
| **Open**           | Restore the main window (the same one the close button hid).          |
| **Restart daemon** | Stop the local daemon process and start a fresh one on the same port. |
| **Quit**           | Stop the Desktop process and the daemon, removing the tray icon.      |

### Launch at login (optional)

Open **Settings → App** and flip the **Launch at login** toggle. Coffer registers itself
with your OS autostart mechanism:

- macOS: a LaunchAgent under `~/Library/LaunchAgents/`.
- Linux: a `.desktop` file under `~/.config/autostart/`.

## Installation

### Download

Go to the [GitHub Releases page](https://github.com/wyx-sg/Coffer/releases) and download
the file for your platform:

| Platform                          | File                              |
| --------------------------------- | --------------------------------- |
| macOS, Apple silicon (M-series)   | `Coffer_<version>_aarch64.dmg`    |
| Linux x64 (AppImage, recommended) | `Coffer_<version>_amd64.AppImage` |
| Linux x64 (deb)                   | `coffer_<version>_amd64.deb`      |

Each download has a `.sha256` sibling for verification.

### Install

- **macOS**: open the DMG and drag **Coffer.app** to `/Applications`.
- **Linux (AppImage)**: `chmod +x Coffer_<version>_amd64.AppImage`, then run it.
- **Linux (deb)**: `sudo apt install ./coffer_<version>_amd64.deb`.

### macOS Gatekeeper

Until Coffer has an Apple Developer ID, the DMG ships unsigned, so on first open macOS may say
Coffer is "damaged". (For the "damaged" message, right-click → Open does **not** help.) Clear
the quarantine flag:

```bash
xattr -dr com.apple.quarantine /Applications/Coffer.app
```

If it still won't open, re-apply an ad-hoc signature:

```bash
codesign --force --deep --sign - /Applications/Coffer.app
```

Notarisation is a current non-goal; the runbook for enabling it once a Developer ID is
available lives in `docs/distribution/macos-notarization.md`.

### First launch

On first launch:

- The main window opens to the Resources welcome view (the Web UI documented in the
  [Web UI guide](/guide/web-ui)).
- The daemon starts on a free port (default 8000, falling back to 8001–8009) and writes
  `~/.coffer/daemon.json`.
- The shim is deployed to its PATH location (see above).
- The tray icon appears.

If the shim's target directory is not yet on `PATH`, Coffer shows a one-time prompt on
**Settings → App** with the exact line to add to your shell rc file.

## CLI-only alternative

For headless servers or machines where you do not want the Desktop app, download the
**CLI-only** archive (`coffer-cli-<triple>.tar.gz`) from the same Releases page. It
contains just `coffer-daemon` and `coffer-mcp-shim` — extract, run the daemon, put the
shim on `PATH`,
and point your MCP clients at it.

## Next steps

- [Connect a client →](/guide/connect-client)
- [Architecture → Distribution](/architecture/distribution)
