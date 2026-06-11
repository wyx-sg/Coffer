# Quickstart — Coffer Desktop

A 5-minute path from a fresh download to a Coffer desktop app sitting in
your tray, with `coffer-mcp-shim` already on `PATH` and the daemon running
in the background. This is the **end-user** companion to
[`specs/001-mcp-gateway/quickstart.md`](../001-mcp-gateway/quickstart.md)
(CLI / shim) and [`specs/002-ui-shell/quickstart.md`](../002-ui-shell/quickstart.md)
(dev-checkout walkthrough); it covers the bundled installer path.

## Pick your download tier

Coffer ships **macOS (Apple Silicon) only** today. The Releases page offers
two tiers, both built from the same `coffer` + `coffer-daemon` +
`coffer-mcp-shim` binaries:

- **CLI-only** — a `coffer-cli-<triple>.tar.gz` archive (macOS arm64) with
  all three binaries. Best for headless servers and no-GUI installs. See
  [CLI-only install](#cli-only-install) below.
- **CLI+desktop** — the unsigned macOS arm64 `.dmg` with the desktop shell +
  web UI. Best for daily-driver desktop use. This is the path documented in
  steps 1–7 below.

## Prerequisites

- A Mac running macOS 12+ on Apple Silicon (M-series). No Python required.
- An MCP client (Claude Code, Claude Desktop, Cursor, or any other client
  that supports stdio MCP servers).

## 1. Download the installer

Go to the [GitHub Releases page](https://github.com/coffer/coffer/releases)
and download the macOS bundle:

| Platform                        | File                                       |
| ------------------------------- | ------------------------------------------ |
| macOS, Apple silicon (M-series) | `Coffer_<version>_aarch64-unsigned.dmg`    |

The release ships one aggregated `SHA256SUMS` file (not a per-file `.sha256`
sibling). Verify (optional but recommended):

```bash
# from the directory holding the download + the SHA256SUMS file
shasum -a 256 -c SHA256SUMS --ignore-missing
```

> **macOS Gatekeeper**: until Coffer has an Apple Developer ID, the DMG
> ships unsigned (note the `-unsigned` in the filename). On first open,
> macOS will refuse to launch it. Either right-click the app and pick
> **Open** (one-time bypass), or run
> `xattr -dr com.apple.quarantine /Applications/Coffer.app`. See
> [macos-notarization.md](../../docs/distribution/macos-notarization.md).

## 2. Install

- **macOS**: open the DMG, drag **Coffer.app** to `/Applications`.

## 3. First launch

Open **Coffer** from your Applications folder. On first launch:

- The main window opens to the Agents view (the index redirects to
  `/agents`; same web UI documented in
  [002-ui-shell quickstart](../002-ui-shell/quickstart.md) step 2).
- The desktop shell silently deploys `coffer-mcp-shim` to a stable PATH
  location: `~/.coffer/bin/coffer-mcp-shim`.
- The daemon comes up on a free port (defaults to 8000, falls back to
  8001–8009 if taken) and writes `~/.coffer/daemon.json`.
- A tray icon appears in your menu bar.

If the shim's target directory is not on `PATH`, Coffer shows a one-time
prompt on the **Settings → App** tab with the exact line to add to your
shell rc file (`~/.zshrc`, `~/.bashrc`, etc.).

## 4. Add an MCP server

Open **MCP servers** in the sidebar (`/mcp-servers`) and click
**Add MCP server**. Paste the standard `mcpServers` JSON from any vendor's
README, confirm the secrets-review step, and submit. The server lands on the
MCP servers list and reaches "healthy" within ~10 seconds.

## 5. Point your MCP client at Coffer

In your MCP client's config, add Coffer's shim as a server. Paste these
snippets verbatim — they self-discover the daemon, no per-machine
parameterisation:

**Claude Code / Claude Desktop / Cursor** (`.mcp.json` or vendor-specific
config):

```json
{
  "mcpServers": {
    "coffer": {
      "command": "coffer-mcp-shim"
    }
  }
}
```

Restart your MCP client. It should now see every enabled capability from
every registered Coffer server.

## 6. Tray usage

Left-click the tray icon (macOS shows the menu on left-click). The menu
offers:

| Item               | What it does                                                                                         |
| ------------------ | ----------------------------------------------------------------------------------------------------- |
| **Open**           | Restore the main Coffer window (the same one closing-the-X just hid).                                 |
| **Restart daemon** | Bounce the daemon (rate-limited; same command as the in-app banner's Restart button).                 |
| **Quit**           | Exit the desktop app and remove the tray icon. The daemon keeps running, so MCP clients still work.   |

**Quit** stops only the desktop (GUI) app — the daemon is a detached process
and survives Quit, so registered MCP clients continue to work through the
shim. To stop the daemon itself, use the CLI (`coffer daemon stop`).

The daemon can also be restarted from inside the app: when the daemon is
unreachable, the **Daemon not running** banner offers a **Restart** button
backed by the same rate-limited command as the tray item.

Closing the main window with the OS close button just **hides** the window
to the tray; the daemon stays alive and your MCP clients keep working.

## 7. Optional: launch Coffer at login

Open **Settings → App**, flip the **Launch at login** toggle. Coffer
re-registers itself with macOS's autostart mechanism (a LaunchAgent under
`~/Library/LaunchAgents/`).

Log out and back in (or reboot) to confirm — the tray icon appears without
you opening anything.

## CLI-only install

For a headless box or any machine where you don't want the desktop app,
grab the CLI-only archive instead of the installer.

1. From the [GitHub Releases page](https://github.com/coffer/coffer/releases),
   download the macOS arm64 archive (`<triple>` is `aarch64-apple-darwin`):
   `coffer-cli-<triple>.tar.gz`.

   Verify the checksum against the aggregated `SHA256SUMS` (optional but
   recommended):

   ```bash
   shasum -a 256 -c SHA256SUMS --ignore-missing
   ```

2. Extract it — it contains `coffer`, `coffer-daemon`, and `coffer-mcp-shim`
   (keep all three co-located so `coffer` can detect-or-spawn the daemon):

   ```bash
   tar -xzf coffer-cli-<triple>.tar.gz
   ```

3. Start the daemon. It picks a free port (default 8000, falling back to
   8001–8009) and writes `~/.coffer/daemon.json`:

   ```bash
   ./coffer-daemon
   ```

4. Put `coffer-mcp-shim` on your `PATH` so MCP clients can resolve the
   `command: coffer-mcp-shim` config: move it to `~/.coffer/bin/` and add
   that directory to `PATH` in your shell rc (`~/.zshrc`, `~/.bashrc`, etc.).

5. Point your MCP client at the shim — the same snippet as the desktop
   path ([step 5](#5-point-your-mcp-client-at-coffer)):

   ```json
   {
     "mcpServers": {
       "coffer": {
         "command": "coffer-mcp-shim"
       }
     }
   }
   ```

The shim self-discovers the running daemon through `~/.coffer/daemon.json`,
so no per-machine parameterisation is needed.

## Troubleshooting

- **Tray icon never shows up** — the desktop shell falls back to an
  embedded PNG when the platform tray icon fails to load (see spec's Edge
  Cases). Desktop-side diagnostics are not file-backed yet (the desktop
  crate wires no log sink), so launch Coffer from a terminal to see its
  stderr; for daemon problems check `~/.coffer/logs/daemon.log`.
- **`coffer-mcp-shim: command not found`** — your shell's `PATH` does not
  include the shim directory. Re-launch Coffer once, follow the prompt on
  Settings → App, then open a new terminal.
- **Daemon does not start** — open `~/.coffer/logs/daemon.log` and search
  for `ERROR`. The most common cause is another process already bound to
  every port in 8000–8009; quit that process or wait for it to free up.
- **Updates** — check the
  [GitHub Releases page](https://github.com/coffer/coffer/releases) for
  new versions; install the new bundle over the existing app (your data
  in `~/.coffer/` is preserved).
