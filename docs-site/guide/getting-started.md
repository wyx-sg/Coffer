# Getting Started

> **This page covers the from-source / developer path.** For the prebuilt one-line install or
> the release archive, see [Download & install](/guide/install).

Install Coffer from source and connect your first MCP client. Once the daemon is running, every
MCP client on your machine can connect through the shim without any additional configuration.

## Install from source

```bash
git clone https://github.com/wyx-sg/Coffer.git
cd Coffer
uv sync --frozen --extra dev --project backend   # UV_PROJECT_ENVIRONMENT=$PWD/.venv
make verify          # sanity-check the install
```

This puts both the CLI (`coffer`) and the stdio shim (`coffer-mcp-shim`) on your `PATH`
as console-script entry points — no separate deploy step.

`--frozen` is what makes this reproducible: it installs exactly `backend/uv.lock`, which is
the dependency set CI gates against. `make install` uses `pip install -e ./backend[dev]`
instead, which re-resolves and can therefore give you versions CI has never seen. See
[Download & install](/guide/install#from-source-developers).

- **`coffer`** — the management CLI for registering and inspecting MCP servers.
- **`coffer-mcp-shim`** — the stdio bridge that MCP clients use to talk to the daemon.

`make verify` runs the full check suite (lint, type, unit, integration, contract, acceptance audit)
to confirm the install is healthy.

::: tip Daemon auto-starts — no manual start required
The daemon spawns automatically the first time you run any `coffer` management command or an MCP
client connects through the shim. `coffer daemon start` exists for explicit control but is **not**
a required setup step.
:::

## Look after the daemon

You rarely need to, but these are the commands for when you do:

```bash
coffer open                  # start a daemon if none is running, open the web UI in your browser
coffer open --no-browser     # print the URL instead (--json for {"url", "port"})
coffer daemon status         # status, version, port, pid (--json for scripts)
coffer daemon start | stop | restart
coffer daemon rotate-token   # mint a new API token; reload any open page to pick it up
```

The browser needs no login step: the daemon puts its live token into the page it serves. `curl http://127.0.0.1:8000/api/v1/daemon/status` is the one route that answers without a token, so scripts can use it as a readiness probe.

`stop` checks the recorded pid is still a Coffer daemon before signalling it; if a crashed daemon's pid has been reused by another process, it only cleans up the stale `~/.coffer/daemon.json`.

**Keep it running.** On macOS, `coffer daemon service install` makes the daemon a login service, so it is already up before the first agent call of the day and is restarted if it crashes (`uninstall` and `status` too). It stands down after twelve hours with nothing using it; change that with `coffer daemon idle set <hours>`, or `coffer daemon idle never`. See [Daemon & Processes](/architecture/processes#resident-but-not-forever).

**Change the port.** The daemon always binds `8000`, so bookmarks and browser-stored preferences survive restarts. If something else owns that port the daemon refuses to start and names the process holding it. To move:

```bash
coffer daemon port show      # the configured port, and the port a running daemon is on
coffer daemon port set 8123
coffer daemon restart
coffer daemon port clear     # back to 8000
```

`port` and `idle` write `~/.coffer/daemon-config.json` directly, so they work with no daemon running — the state a port conflict leaves you in.

**Read the log.** `tail -f ~/.coffer/logs/daemon.log` shows what the daemon, the processes it starts, and the desktop app wrote, in one timeline. The same file is the **Daemon** tab under [Activity](./activity). If a start fails with "daemon failed to start within 10s", the reason is in that file.

| Symptom | Fix |
| --- | --- |
| A warning that the daemon's version differs from the CLI's | You installed a new build while the old daemon kept running: `coffer daemon restart`. |
| The API answers but the web UI is blank | This install has no built UI. From a source checkout: `cd frontend && npm run build`, then restart the daemon. |
| Two daemons | A daemon that finds it has been replaced stands down by itself within about half a minute. If one lingers: `coffer daemon stop`, then `coffer daemon start`. |

[Register your first server →](/guide/register-server)
