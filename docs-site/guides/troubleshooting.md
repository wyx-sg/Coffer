---
title: Troubleshooting
description: Symptoms, causes and fixes for common Coffer problems — the daemon, agent connections, missing tools, the web UI, upgrades, keychain prompts, sync and channels.
---

# Troubleshooting

This page lists problems you can meet running Coffer, organised by area, each as symptom, cause and fix. Every message quoted here is one Coffer actually prints. If your problem is not listed, start with [Collect information for a bug report](#collect-information-for-a-bug-report).

::: tip Ask your agent first
An agent connected to Coffer can call `coffer__diagnose`, which returns Coffer's recent audit log and daemon log on one timeline. Asking "check Coffer's logs for what just failed" is often the fastest first step. See [Activity and audit](/guides/activity#let-an-agent-diagnose-coffer-coffer-diagnose).
:::

## The daemon

### The daemon will not start: the port is taken

**Symptom.** `coffer daemon start` (or any command) prints:

```text
port 8000 is the port Coffer's daemon binds, but something else is already using it.
  held by: pid 5120  node server.js
```

**Cause.** Coffer binds one fixed port (8000 unless you changed it) and never moves to another.

**Fix.** Stop the process named, or move Coffer to another port and restart:

```sh
coffer daemon port set 8765
coffer daemon restart
```

If the holder is described as **another Coffer daemon**, it is most often your own daemon still starting: wait a few seconds and run `coffer daemon status`. See [Choose the port](/guides/daemon#choose-the-port).

### "daemon failed to start within 10s; check ~/.coffer/logs/daemon.log"

**Cause.** The daemon was spawned but did not publish itself in time. The reason is in the log, because a spawned daemon writes everything, including its refusal to start, to `daemon.log`.

**Fix.** Read the end of the log:

```sh
tail -n 50 ~/.coffer/logs/daemon.log
```

The most common entries are a taken port (above) and a database written by a newer build (below). The MCP shim reports the same situation as `coffer-mcp-shim: daemon did not come up within 10s; check ~/.coffer/logs/daemon.log`.

### The database schema is too new

**Symptom.** The daemon stops at startup and the log says:

```text
database schema revision '0105' is newer than this Coffer build understands — it was created by a newer or different version. Upgrade Coffer, or back up and remove ~/.coffer/coffer.db to start fresh.
```

The error code is `DB_SCHEMA_TOO_NEW`.

**Cause.** A newer build, or a development build with migrations this one does not ship, migrated the database. Typical after rolling back an upgrade or switching between source checkouts.

**Fix.** Run the newer build again. To stay on this build, stop the daemon and restore the copy taken before that migration, `~/.coffer/coffer.db.pre-<revision>` (see [Database migrations and automatic backups](/guides/daemon#database-migrations-and-automatic-backups)).

### A command warns that the daemon is a different version

**Symptom.**

```text
coffer: WARNING: attached to a Coffer daemon at version 0.1.1 (/Users/you/.coffer/bin/0.1.1/coffer-daemon) but this coffer is 0.2.0; run `coffer daemon restart` to serve the current build
```

`coffer daemon status` may also show `channel: unknown — the running daemon predates this CLI; restart it: coffer daemon restart`.

**Cause.** You installed a new version while the old daemon kept running. The daemon outlives the CLI and shim processes that attach to it, so the old build is still answering.

**Fix.** `coffer daemon restart`. In the desktop app, the **Daemon out of date** notice has a **Restart daemon** button.

### "daemon not reachable — it may have crashed"

**Cause.** The CLI found a daemon, then lost the connection mid-request.

**Fix.** Run `coffer daemon status`. If it prints `not running`, run `coffer daemon start`, then read `daemon.log` for what ended the previous one.

## Agents and tools

### An agent reports "All connection attempts failed" on a Coffer tool

**Cause.** The agent's `coffer-mcp-shim` could not reach the daemon. When the daemon restarts, the shim re-reads `~/.coffer/daemon.json`, reconnects to the new daemon and retries the call by itself. It reports this error only when no daemon comes up within a few seconds, for example after `coffer daemon stop`, or when the new daemon could not start.

**Fix.**

1. Run `coffer daemon status`. If it prints `not running`, run `coffer daemon start`, which starts one or shows why it cannot.
2. Call the tool again; the shim reconnects on the next call.
3. If the agent still fails, reconnect its MCP servers or restart the agent session, which launches a fresh shim.

The shim's own log is `~/.coffer/logs/shim-<pid>-<time>.log`.

### A tool the agent expects is not in its tool list

Work through these causes in order:

| Cause | How to tell | Fix |
| --- | --- | --- |
| The tool is not advertised, because the catalogue exceeds the listing budget (50 upstream tools by default). | The server is healthy and the tool is enabled. | The tool still works. Ask the agent to find it with `coffer__search_tools`, or set `COFFER_TOOL_TIERING=off` in the daemon's environment to list everything. |
| The server is disabled on this machine, or its reach does not include this agent. | The server's reach control, or `coffer scope show mcp_server <name>`. | Enable it, or add the agent: `coffer resource enable mcp_server <name>`, `coffer scope set mcp_server <name> --agents <agent>`. |
| The agent's session reports no identity, so it sees only unscoped servers. | The agent's MCP entry runs `coffer-mcp-shim` without `--agent-uid`. | Reinstall Coffer's MCP entry: `coffer agent mcp install <agent>`. |
| The individual tool is switched off. | The server's **Tools** tab, or `coffer mcp tool list <name>`. | Switch it on there, or with `coffer mcp tool enable`. |
| The server cannot start: its launcher is missing. | The server shows `npx is not installed on this machine` (or `uvx`, …). | Install that runtime, then **Refresh capabilities**. Coffer does not install runtimes. |
| The server is failing or slow to answer. | `coffer mcp test <name>`; the server's stderr in `~/.coffer/logs/upstream/<name>.log`. | Fix the server's configuration or credentials. A server that misses discovery is retried in the background and its tools reappear when it answers. |
| A Coffer tool belongs to a switched-off feature (`coffer__write` for `knowledge`, `coffer__recall` for `memory`). | `coffer daemon features list` | `coffer daemon features enable <key>` |

See [MCP servers](/guides/mcp-servers) and [Connect a client](/guides/connect-a-client).

### A tool call fails and the log only says "upstream tool returned an error result (isError)"

**Cause.** The upstream tool reported an error in its result. Coffer records that the call failed, but never stores the upstream's message, since it may echo the call's arguments.

**Fix.** The agent sees the tool's own error text in its result. For the server side, read `~/.coffer/logs/upstream/<server>.log`.

## The web UI

### "Daemon offline" or "Daemon not running"

**Cause.** The page cannot reach the daemon (**Daemon offline**), or the daemon answered but the page's token is not accepted (**Daemon not running**), which happens briefly while a daemon starts or after it restarted with a new token.

**Fix.** In a browser, run `coffer daemon start` in a terminal; the page checks again every 30 seconds and the notice clears itself. If it stays, reload the page: the daemon hands the page its current token on every load. In the desktop app, use **Restart daemon**.

### The UI lost its language, page size or sidebar state

**Cause.** The browser keeps those preferences per origin, and the origin includes the port. The daemon is now on a different port than before, so the browser treats it as a different site.

**Fix.** Keep one port: `coffer daemon port show` tells you the configured port; `coffer daemon port clear` returns to 8000.

### A page says a feature "is switched off"

**Cause.** Sync, Knowledge and Memory are [experimental features](/guides/experimental-features), off by default in release builds.

**Fix.** **Settings → General → Experimental features**, or `coffer daemon features enable <key>`. If the switch is disabled, the feature is pinned by `COFFER_FEATURES` in the daemon's environment.

## Credentials and macOS keychain prompts

### macOS asks for keychain access every time the daemon starts

**Cause.** One of two things:

- The credential master key is stored in the OS keychain (you opted in under **Settings → Security**). Reading it costs one prompt per daemon start.
- A resource cites a credential that is not in Coffer's encrypted store. At each start Coffer looks for that ref once in the OS keychain and moves it into the store if it finds it. A locked or denied read is retried at the next start, with another prompt.

**Fix.**

- Move the master key back to a file beside the database:
  ```sh
  coffer credentials storage --set file
  ```
  or switch off **Store master key in OS keychain** in **Settings → Security**.
- Find credentials that are cited but missing with `coffer credentials list`, then store each one with `coffer credentials set <ref>`.

See [Credentials](/guides/credentials).

## Vault sync

| Symptom | Cause | Fix |
| --- | --- | --- |
| `coffer sync status` exits 1 and shows `awaiting_confirmation` | The deletion guard held a round. | Read the list, then `coffer sync confirm`, `reject` or `rebuild`. Never confirm after a reinstall. |
| `conflict: <path>` | Two machines edited the same lines. | Resolve it in `~/.coffer/sync` with git, commit, then `coffer sync now`. |
| `awaiting_join` | This machine has not joined the remote. | `coffer sync adopt` |
| `credential locked: <ref>` | This machine lacks the master key. | `coffer sync key import <file>` |
| Push fails with an authentication error | Coffer does not use your global git config or the macOS keychain helper. | Store a token and pass `--credential-ref`, or use an SSH key that needs no passphrase prompt. |

The full list is in [Vault sync troubleshooting](/guides/vault-sync#troubleshooting).

## Channels

### The bot does not answer

Check the channel's runtime state first:

```sh
coffer channel status <name>
```

| What `status` shows | Cause | Fix |
| --- | --- | --- |
| No answer, or a daemon error | The daemon is not running. Channels run inside the daemon. | `coffer daemon start`. On macOS, `coffer daemon service install` keeps it running without a Coffer window. |
| `runs on: <id> (another machine)` | The channel is bound to another machine sharing this vault, which answers instead. | Nothing, or move it here: `coffer channel bind <name>` |
| `runs on: unbound (runs nowhere)` | The channel names no machine. | `coffer channel bind <name>` |
| `peer: not paired` | Nobody has paired with the bot, so every message is ignored. | `coffer channel pair <name>` and send the code to the bot from your own account. |
| `inbound: websocket (…)` with a `ws error:` line | A SeaTalk channel's connection failed. The error says why, for example another process holding the connection. | Fix the cause the error names. |
| `warning: …` | A platform-side setting defeats part of the configuration. | Follow the fix in the warning. |

Messages are accepted only from the paired owner. In a group, the bot acts only on a message from the owner that addresses it. See [Channels](/guides/channels).

## Where the logs are

| File | Written by |
| --- | --- |
| `~/.coffer/logs/daemon.log` (+ `.1`–`.3`) | The daemon and everything acting for it. Readable on **Activity → Daemon**. |
| `~/.coffer/logs/shim-<pid>-<time>.log` | Each `coffer-mcp-shim` process an agent launched. Kept seven days. |
| `~/.coffer/logs/upstream/<server>.log` | Each stdio MCP server's stderr. |

`COFFER_LOG_DIR` moves the directory. To match a failed REST call to its log lines, take the `X-Coffer-Trace` header from the response and search `daemon.log` for it; see [Correlate a failed request](/guides/activity#correlate-a-failed-request-with-the-log-x-coffer-trace).

## Collect information for a bug report

1. The version and channel: `coffer daemon status`, or **Settings → About → Copy diagnostics**.
2. How you installed it (desktop app, release archive, source) and your macOS version.
3. The error as printed, and the command or action that produced it. Re-run a failing CLI command with `coffer -v …` for the full traceback and HTTP context.
4. The relevant lines of `daemon.log`, filtered to the time of the failure, or the `X-Coffer-Trace` id of the failing request.

::: warning Check what you paste
Coffer never writes secret values to its logs, but upstream MCP servers write their own stderr into `upstream/*.log` and may include anything. Read log excerpts before you share them.
:::

File the report on [GitHub Issues](https://github.com/wyx-sg/Coffer/issues). For a security problem, follow the [security policy](/contributing/security) instead.

## Related

- [Running the daemon](/guides/daemon)
- [Activity and audit](/guides/activity)
- [FAQ](/guides/faq)
- [Error codes](/reference/error-codes)
