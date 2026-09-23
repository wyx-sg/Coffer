# Quickstart — Coffer Desktop App

The double-click way into Coffer. Nothing needs to be installed first — no
Python, no `coffer` CLI, no source checkout.

## Install

1. Download `Coffer_<version>_aarch64.dmg` from the release. It is macOS
   arm64 only.
2. Open it and drag **Coffer** to Applications.
3. Clear the quarantine attribute. The binaries inside are unsigned, so macOS
   refuses a browser-downloaded app on double-click with "Coffer is damaged":

   ```bash
   xattr -dr com.apple.quarantine /Applications/Coffer.app
   ```

   (The same step applies to the terminal install; the release notes carry it
   for both.)
4. Double-click Coffer.

## First launch

The window appears immediately, before anything has been contacted. Behind it
the app looks for a daemon in a fixed order:

1. a daemon already running and answering, named by `~/.coffer/daemon.json`
2. the binary bundled inside the app
3. `~/.coffer/bin/`
4. `PATH`

If one is already running — say you started it from a terminal — the app takes
it over rather than starting a second. Otherwise it starts one from the bundle.
Either way the UI fills in on its own once the daemon answers.

**The CLI comes with it.** On its first frozen start the daemon lays its own
sibling binaries down under `~/.coffer/bin/`, so after one launch `coffer`,
`coffer-daemon` and `coffer-mcp-shim` are on disk. Put `~/.coffer/bin` on your
`PATH` if you want them:

```bash
echo 'export PATH="$HOME/.coffer/bin:$PATH"' >> ~/.zprofile
```

## The tray

Coffer stays in the menu bar while it runs. From there:

- **Open** — bring the window back.
- **Restart daemon** — stop the running daemon and start a fresh one.
- **Quit** — exit the app. The daemon keeps running, because agents are still
  talking to it.

**Closing the window does not quit.** It hides to the tray; re-activating from
the Dock brings it back.

## When the UI says it cannot reach the daemon

The offline banner carries a **Restart** button in the desktop app that it
cannot carry in a browser — a daemon that is down cannot serve the page the
button would live on. Pressing it, or using the tray's restart:

- asks a responsive daemon to shut down and waits for its port to free, so a
  wedged-but-listening daemon is really replaced rather than left alone;
- refuses a second restart within five seconds of a successful one, saying how
  long is left;
- lets you retry immediately if the spawn itself failed.

If the app cannot find a daemon at all it says so in the window rather than
sitting blank.

## Two hosts, one Coffer

The app and the browser show the same UI from the same build. Which you use is
a matter of how you got there:

| | Desktop app | Browser (`coffer open`) |
| --- | --- | --- |
| Reaching it | Dock, Spotlight, Cmd-Tab | a loopback URL you have to know |
| Authentication | IPC handshake from the app | the daemon injects the token into the page it serves |
| Restart control when the daemon is down | yes | no — the page would have to be served by the daemon that is down |
| Install | one `.dmg` | the terminal archive, or `pip install ./backend` |

Neither is a substitute for the other, and both ship on every release tag.

## Troubleshooting

| Symptom | Most likely cause | Fix |
| --- | --- | --- |
| "Coffer is damaged and can't be opened" | Quarantine attribute on a browser download | `xattr -dr com.apple.quarantine /Applications/Coffer.app` |
| Window opens but never fills in | No daemon could be found or started | The banner says which; the tray's Restart is the first thing to try. |
| An MCP server fails with "command not found" only under the app | A GUI launch inherits a minimal `$PATH` | The app probes your login shell for the real one — check that `~/.zprofile` (not `~/.zshrc`) exports it. |
| A warning about mismatched versions | An older daemon from a previous install is still listening | Restart the daemon from the tray. |
| The UI looks older than the daemon | A stale `.app` carrying a stale UI build | Install the current `.dmg`. |

Everything the shell itself reports — which binary it resolved, a restart that
failed — is in `~/.coffer/logs/daemon.log` alongside the daemon's own lines,
tagged `coffer.desktop`. There is no separate desktop log.
