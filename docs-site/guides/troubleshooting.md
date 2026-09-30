---
title: Troubleshooting
description: Symptoms, causes and fixes for common Coffer problems — the daemon, agent connections, missing tools, the web UI, upgrades, keychain prompts, sync and channels.
---

# Troubleshooting

This page lists problems you can meet running Coffer, organised by area, each as symptom, cause and fix. Every message quoted here is one Coffer actually prints. If your problem is not listed, start with [Collect information for a bug report](#collect-information-for-a-bug-report).

::: tip Ask your agent first
An agent with a shell can read Coffer's own records: `coffer log daemon --errors --since 1h` for the daemon log, `coffer log audit --since 1h` for the audit log, and `coffer path logs` for where `daemon.log` is, so it can grep the file directly. Asking "check Coffer's logs for what just failed" is often the fastest first step. See [Activity and audit](/guides/activity).
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
coffer config set daemon.port 8765
coffer daemon restart
```

If the holder is described as **another Coffer daemon**, it is most often your own daemon still starting: wait a few seconds and run `coffer daemon status`. See [Choose the port](/guides/daemon#choose-the-port).

### "daemon failed to start within 10s; check ~/.coffer/logs/daemon.log"

**Cause.** The daemon was spawned but did not publish itself in time. The reason is in the log, because a spawned daemon writes everything, including its refusal to start, to `daemon.log`.

**Fix.** Read the end of the log:

```sh
tail -n 50 ~/.coffer/logs/daemon.log
```

The most common entries are a taken port (above), a database written by a newer build, and a home that still needs the one-time upgrade (below). The MCP shim reports the same situation as `coffer-mcp-shim: daemon did not come up within 10s; check ~/.coffer/logs/daemon.log`.

### The database schema is too new

**Symptom.** The daemon stops at startup and the log says:

```text
database schema revision '0118' is newer than this Coffer build understands — it was created by a newer or different version. Upgrade Coffer, or back up and remove sqlite+aiosqlite:////Users/you/.coffer/runs.db to start fresh.
```

The error code is `DB_SCHEMA_TOO_NEW`.

**Cause.** A newer build, or a development build with migrations this one does not ship, migrated the history database, `runs.db`. Typical after rolling back an upgrade or switching between source checkouts.

**Fix.** Run the newer build again. To stay on this build, stop the daemon and restore the copy taken before that migration, `~/.coffer/runs.db.pre-<revision>` (see [Database migrations and automatic backups](/guides/daemon#database-migrations-and-automatic-backups)).

### The daemon asks for `coffer migrate`

**Symptom.** The daemon refuses to start and names `coffer migrate` (`VAULT_MIGRATION_REQUIRED`), or names `coffer migrate --resume` (`VAULT_MIGRATION_ON_HOLD`).

**Cause.** The home was written by a Coffer from before the vault layout and still keeps its state in `coffer.db`, or a rollback of the upgrade left its hold marker.

**Fix.** Stop the daemon, then `coffer migrate --rehearse` and `coffer migrate`; after a rollback, `coffer migrate --resume` first. See [Upgrading an existing Coffer](/guides/upgrading).

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
| The server is disabled on this machine, or its reach does not include this agent. | The server's reach control, or `coffer mcp scope <name>`. | Enable it, or add the agent: `coffer mcp enable <name>`, `coffer mcp scope <name> --agents <agent>`. |
| The agent's session reports no identity, so it sees only unscoped servers. | The agent's MCP entry runs `coffer-mcp-shim` without `--agent-uid`. | Connect the agent again: `coffer agent connect <agent>`. |
| The individual tool is switched off. | The server's **Tools** tab, or `coffer mcp cap list <name>`. | Switch it on there, or with `coffer mcp cap enable <name> tool:<tool>`. |
| The server cannot start: its launcher is missing. | The server shows `npx isn't found on this machine` (or `uvx`, …). | Install that runtime where the daemon's `PATH` reaches (an app started from the Dock or Finder does not read your shell's startup files), then **Test**. Coffer does not install runtimes; its callout's **Copy prompt** (or `coffer mcp handoff <name>`) hands the install to your agent with the command line and `PATH` it needs. |
| The server is failing or slow to answer. | `coffer mcp test <name>`; the server's stderr in `~/.coffer/logs/upstream/<name>.log`. | Fix the server's configuration or secrets. A server that misses discovery is retried in the background and its tools reappear when it answers. The failing callout's **Copy prompt** (or `coffer mcp test <name> --prompt`) hands the diagnosis to your agent, with the error and the stderr tail and without any secret value. |

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

**Fix.** Keep one port: `coffer config get daemon.port` tells you the configured port; `coffer config unset daemon.port` returns to 8000.

### A page says a feature "is switched off"

**Cause.** The page belongs to an [experimental feature](/guides/experimental-features) that is switched off on this machine. Experimental features are off by default in release builds. No feature is experimental right now, so a current build does not show this notice.

**Fix.** Press **Switch on** on the notice, switch it under **Settings → General**, or run `coffer config set feature.<key> on`. If the notice says `COFFER_FEATURES` holds it off, the feature is pinned in the daemon's environment; change it where the daemon is started.

## Secrets and macOS keychain prompts

### macOS asks for keychain access every time the daemon starts

**Cause.** One of two things:

- The secret master key is stored in the OS keychain (you opted in under **Settings → Security**). Reading it costs one prompt per daemon start.
- A resource cites a secret that is not in Coffer's encrypted store. At each start Coffer looks for that ref once in the OS keychain and moves it into the store if it finds it. A locked or denied read is retried at the next start, with another prompt.

**Fix.**

- Move the master key back to the file `~/.coffer/master.key`:
  ```sh
  coffer config set secrets.storage file
  ```
  or switch off **Store master key in OS keychain** in **Settings → Security**.
- Find secrets that are cited but missing with `coffer secret list`, then store each one with `coffer secret set <ref>`.

### A command exits 9: "waiting for approval in the Coffer app"

**Cause.** The change sends a secret somewhere it has not gone before — a second MCP server citing the same token, a changed command line or URL, a push token pointed at a new remote — or replaces a value something already uses, or switches `secrets.require_approval` off. The change is saved; the secret is held until you approve it. An MCP server in that state is not started, and its tools fail with `SECRET_BINDING_PENDING`.

**Fix.** Open the desktop app and answer the approval it shows (or look with `coffer secret approvals`). Approve only a target you recognise; refuse the rest with `coffer secret reject <id>`. Rerun the command with `--wait` to have it wait for your answer. See [Secrets → Approvals](/guides/secrets#approvals).

### There is no way to print a secret from the terminal

**Cause.** By design: no command, route or MCP tool returns a stored value, because an agent can run any command you can. `coffer secret get` only confirms a value is stored.

**Fix.** Reveal or copy it in the desktop app, which asks for Touch ID or your password. To give a value to a command, store it as a standalone secret and run the command with `coffer run --secret <name> -- <command>`. See [Secrets](/guides/secrets).

See [Secret store](/guides/secret-store).

## Vault sync

| Symptom | Cause | Fix |
| --- | --- | --- |
| `coffer sync status` exits 1 and shows `deletions held` | The deletion breaker held a round. | Read the list (`coffer sync hold`), then `coffer sync hold --confirm` or `--restore`. After a reinstall, restore. |
| `stopped on conflicts` | Two machines changed the same file in ways git cannot merge. | `coffer sync conflicts`, answer each file with `coffer sync resolve <path> --mine\|--theirs\|--edited`, then `coffer sync continue`, or use the conflict card on the **Sync** page. |
| `join required` | This machine has not joined the remote. | `coffer sync join` |
| `remote too old` | The remote was written by a Coffer from before the vault layout. | Rebuild it: see [Upgrading an existing Coffer](/guides/upgrading#rebuild-your-sync-remote). |
| Secrets cannot be decrypted | This machine lacks the master key. | `coffer sync key import <file>` |
| Push fails with an authentication error | Coffer does not use your global git config or the macOS keychain helper. | Store a token and pass `--secret-ref`, or use an SSH key that needs no passphrase prompt. |

The full list is in [Vault sync troubleshooting](/guides/vault-sync#troubleshooting).

## Channels

### The bot does not answer

Check the channel's runtime state first:

```sh
coffer channel show <name>
```

| What `show` prints | Cause | Fix |
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
