# Quickstart — Coffer Daemon

The daemon is the process every other Coffer surface talks to. Most of the time
you never start it: the CLI, the MCP shim and the desktop shell each spawn one
when they need one. This is what to do on the occasions you do have to look at
it directly.

## Prerequisites

- Coffer installed, either from source (`pip install ./backend`, Python 3.12+)
  or from the release archive (`coffer-cli-<triple>.tar.gz`, no Python needed).

## Open the UI

```bash
coffer open
```

Starts a daemon if none is running, then opens
`http://127.0.0.1:<port>/` in your browser. You are already signed in — the
daemon injects its live token into the page it serves, so there is nothing to
paste and nothing is stored in the browser. `--no-browser` prints the URL
instead; `--json` prints `{ "url": …, "port": … }`.

## See whether a daemon is running

```bash
coffer daemon status
```

```
status:  ready
version: 0.2.0
port:    8000
pid:     41233
```

`--json` adds the same fields in one object for a script. If nothing is
running, the command starts one — that is detect-or-spawn, and it is how every
other Coffer command behaves too.

The same answer over HTTP, with no token, is:

```bash
curl -s http://127.0.0.1:8000/api/v1/daemon/status
```

This is the only unauthenticated route. It is the readiness probe, so it
answers while the daemon is still starting.

## Start, stop, restart

```bash
coffer daemon start      # spawns a detached daemon; refuses if one is live
coffer daemon stop       # SIGTERM, then waits for the discovery file to go
coffer daemon restart    # stop then start — how a changed port takes effect
```

`stop` checks that the recorded pid is still a Coffer daemon before signalling
anything. If a crashed daemon's pid has been recycled onto something else, it
cleans up the stale `~/.coffer/daemon.json` and tells you so, rather than
killing a stranger.

## Move the port

The daemon binds `8000` and stays there, so a bookmark keeps working and the
browser keeps everything it stored against that origin. If something else on
your machine owns 8000:

```bash
coffer daemon port show
```

```
configured: default (8000)
daemon:     running on 8000
```

```bash
coffer daemon port set 8123
coffer daemon restart
```

`coffer daemon port clear` goes back to the default. The setting lives in
`~/.coffer/daemon-config.json`, which the daemon reads **before** it binds — so
this command works with no daemon running, which is exactly the state you are
in when a port conflict has stopped it from starting. There is no REST endpoint
and no settings panel for it, on purpose.

## When a start fails

A daemon that cannot bind its port refuses to start rather than drifting to
another one, and says what is holding it:

```
port 8000 is the port Coffer's daemon binds, but something else is already using it.
  held by: pid 992  /usr/local/bin/something
  fix one of:
    stop that process, then    coffer daemon start
    use a different port       coffer daemon port set <port>
```

When the holder turns out to be another Coffer daemon the message says so, and
leads with "it is probably your own, still starting up" rather than with
"kill it" — dropping a healthy daemon takes every attached MCP client with it.

Everything else the daemon says on its way up is in the log:

```bash
tail -f ~/.coffer/logs/daemon.log
```

That one file carries the daemon, the children it spawns, and every surface
writing on their behalf — several different formats in one timeline. The web
Activity page reads the same file through
`GET /api/v1/daemon/logs`, normalised into columns.

## Rotate the API token

```bash
coffer daemon rotate-token
```

Mints a new token, rewrites `~/.coffer/daemon.json`, and audits the change.
Anything holding the old token — an open browser tab, a long-running script —
starts getting `401` immediately; reload the page and it picks up the new one
from the document the daemon serves.

## Install without a Python

```bash
curl -LO https://github.com/<owner>/coffer/releases/download/<tag>/coffer-cli-aarch64-apple-darwin.tar.gz
curl -LO https://github.com/<owner>/coffer/releases/download/<tag>/SHA256SUMS
shasum -a 256 -c SHA256SUMS --ignore-missing
tar xzf coffer-cli-aarch64-apple-darwin.tar.gz
./coffer daemon start
./coffer open
```

The archive holds four binaries — `coffer`, `coffer-daemon`,
`coffer-mcp-shim`, `coffer-callback` — and they must stay together: the frozen
daemon resolution looks for `coffer-daemon` next to `coffer`. On the first
start the daemon copies all four into `~/.coffer/bin/<version>/` and points
`~/.coffer/bin/<name>` at them, so adding `~/.coffer/bin` to your `PATH` is
enough from then on.

macOS arm64 is the only platform built. The binaries are unsigned, so the first
run needs the quarantine attribute cleared:

```bash
xattr -d com.apple.quarantine coffer coffer-daemon coffer-mcp-shim coffer-callback
```

If you would rather double-click an application than use a terminal, that is
the other tier — see spec desktop-app.

## Files the daemon owns

| Path | What it is |
| --- | --- |
| `~/.coffer/daemon.json` | Where the daemon is and how to talk to it. Contains the token: mode `0600`, deleted when the daemon exits. |
| `~/.coffer/daemon-config.json` | Your settings, read before the daemon binds. Survives shutdown. |
| `~/.coffer/daemon.lock` | Advisory lock that keeps two daemons from starting at once. Leave it alone. |
| `~/.coffer/logs/` | `daemon.log` and its rotations, plus per-shim and per-upstream logs. |
| `~/.coffer/bin/` | Deployed frozen builds, one directory per version, public names as symlinks. |
| `~/.coffer/coffer.db.pre-<revision>` | The copy taken before a schema upgrade. The three newest are kept. |

## Troubleshooting

**"attached to a Coffer daemon at version X but this CLI is Y".** You installed
a new build while the old daemon was still running; the daemon outlives the
commands that attach to it. `coffer daemon restart`.

**Two daemons.** There should never be two, and a daemon that sees it has been
superseded stands down on its own within half a minute. If one lingers,
`coffer daemon stop` then `coffer daemon start`.

**"daemon failed to start within 10s".** Read `~/.coffer/logs/daemon.log` — the
detached daemon writes its own refusal there, which is why the message points
at it.

**The UI is blank but the API answers.** No web UI was built into this install.
From a source checkout, `cd frontend && npm run build`, then restart the daemon.
