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
port 38470 is the port Coffer's daemon binds, but something else is already using it.
  held by: pid 5120  node server.js
```

**Cause.** Coffer binds one fixed port (38470 unless you changed it) and never moves to another.

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

The most common entries are a taken port (above) and a database written by a newer build (below). The MCP shim reports the same situation as `coffer-mcp-shim: daemon did not come up within 10s; check ~/.coffer/logs/daemon.log`.

### The database schema is too new

**Symptom.** The daemon stops at startup and the log says:

```text
database schema revision '0147' is newer than this Coffer build understands — it was created by a newer or different version. Upgrade Coffer, or back up and remove sqlite+aiosqlite:////Users/you/.coffer/runs.db to start fresh.
```

The error code is `DB_SCHEMA_TOO_NEW`.

**Cause.** A newer build, or a development build with migrations this one does not ship, migrated the history database, `runs.db`. Typical after rolling back an upgrade or switching between source checkouts.

**Fix.** Run the newer build again. To stay on this build, stop the daemon and restore the copy taken before that migration, `~/.coffer/runs.db.pre-<revision>` (see [Database migrations and automatic backups](/guides/daemon#database-migrations-and-automatic-backups)).

### A command warns that the daemon is a different version

**Symptom.**

```text
coffer: WARNING: attached to a Coffer daemon at version 0.1.1 (/Users/you/.coffer/bin/0.1.1/coffer-daemon) but this coffer is 0.2.0; run `coffer daemon restart` to serve the current build
```


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
| The server is disabled on this machine, or its reach does not include this agent. | The server's **Reach** control and enabled switch. | Enable it, or add the agent under **Available to**. |
| The agent's session reports no identity, so it sees only unscoped servers. | The agent's MCP entry runs `coffer-mcp-shim` without `--agent-uid`. | Press **Connect** again on the agent's page. |
| The individual tool is switched off. | The server's **Tools** tab. | Switch it on there. |
| The server cannot start: its launcher is missing. | The server shows `npx isn't found on this machine` (or `uvx`, …). | Install that runtime where the daemon's `PATH` reaches (an app started from the Dock or Finder does not read your shell's startup files), then **Test**. Coffer does not install runtimes; its callout's **Copy prompt** hands the install to your agent with the command line and `PATH` it needs. |
| The server is failing or slow to answer. | **Test** on the server's page (or `coffer mcp test <name>`); the server's stderr in `~/.coffer/logs/upstream/<name>.log`. | Fix the server's configuration or secrets. A server that misses discovery is retried in the background and its tools reappear when it answers. The failing callout's **Copy prompt** hands the diagnosis to your agent, with the error and the stderr tail and without any secret value. |

See [MCP servers](/guides/mcp-servers) and [Connect a client](/guides/connect-a-client).

### A tool call fails and the log only says "upstream tool returned an error result (isError)"

**Cause.** The upstream tool reported an error in its result. Coffer records that the call failed, but never stores the upstream's message, since it may echo the call's arguments.

**Fix.** The agent sees the tool's own error text in its result. For the server side, read `~/.coffer/logs/upstream/<server>.log`.

## The web UI

### "Daemon offline" or "Daemon not running"

**Cause.** The page cannot reach the daemon (**Daemon offline**), or the daemon answered but the page's token is not accepted (**Daemon not running**), which happens briefly while a daemon starts or after it restarted with a new token.

**Fix.** In a browser, run `coffer daemon start` in a terminal; the page checks again every 30 seconds and the notice clears itself. If it stays, reload the page: the daemon hands the page its current token on every load. In the desktop app, use **Restart daemon**.

### Coffer needs git

**Symptom.** The app or the web UI shows **Coffer needs git** in place of every page, and a `coffer` command prints the reason and a prompt for your agent, then exits 10:

```text
Coffer needs git, and git isn't installed on this machine. The vault keeps its history and syncs with git. Install git, then check again: press Check again in Coffer, or run the command again.
```

`coffer daemon status` reports `status:  setup` with the same words.

**Cause.** The vault is a git repository, and sync's merges need git 2.40 or later. With no git, or an older one, the daemon still starts, but waits in a setup state: it serves the page and its status and refuses everything that needs the vault (`GIT_NEEDED`, 503). It looks for git on its own `PATH` and on your login shell's, so a git your terminal finds is used even when the daemon was started from the Dock.

**Fix.** Install or update git. **Copy prompt** on the screen (or the prompt the command printed) hands the chore to your agent, which picks the way that fits your machine. Then press **Check again**: once git is there, Coffer restarts its daemon and opens normally. From a terminal, `coffer daemon restart` does the same.

### The UI lost its language or sidebar state

**Cause.** The browser keeps those preferences per origin, and the origin includes the port. The daemon is now on a different port than before, so the browser treats it as a different site.

**Fix.** Keep one port: `coffer config get daemon.port` tells you the configured port; `coffer config unset daemon.port` returns to 38470.

### A page or tool is missing because a feature is switched off

**Cause.** The page or tool belongs to an [experimental feature](/guides/experimental-features) that is switched off on this machine. Experimental features are off by default, and a switched-off feature looks absent: no sidebar entry, no palette result, and a link to its page shows the not-found page. The two experimental features are Knowledge and Memory; Sync and Model providers (with Usage) are always on and never hidden this way.

**Fix.** Switch it on under **Settings → Features**. **Decided by** shows what decided each feature; if it says `pin`, `COFFER_FEATURES` holds it in the daemon's environment, so change it where the daemon is started.

## Secrets and macOS keychain prompts

### macOS asks for keychain access every time the daemon starts

**Cause.** A resource cites a secret that is not in Coffer's encrypted store. At each start Coffer looks for that ref once in the OS keychain and moves it into the store if it finds it. A locked or denied read is retried at the next start, with another prompt.

**Fix.** Find secrets that are cited but missing with `coffer secret list`, then store each one on the **Secrets** page or with `coffer secret set <ref>`.

### A command exits 9: "waiting for approval"

**Cause.** The change sends a secret somewhere it has not gone before — a second MCP server citing the same token, a changed command line or URL, a push token pointed at a new remote — replaces a value something already uses, switches `secrets.require_approval` off, or asks `coffer run` to use a standalone secret you have not allowed it to (the secret's page shows **Allow `coffer run`…**; see [Secrets](/guides/secrets#allow-coffer-run-to-use-it)). The change is saved; the secret is held until you approve it. The command printed the approval ids and the command that approves them (`next: coffer approval approve <id>`). An MCP server in that state is not started, and its tools fail with `SECRET_BINDING_PENDING`; a custom tool's call answers the same tool error, naming the approval ids and the same command, for the environment that waits only.

**Fix.** Run the printed `coffer approval approve <id>` (or let your agent run it) and confirm the Touch ID or password prompt the desktop app shows, or open the desktop app and answer the approval there (on the **Secrets** page, **Review** opens the approvals dialog). Approve only a target you recognise; refuse the rest with **Reject** or `coffer approval reject <id>`. The change is already saved, so nothing needs to be rerun. If `coffer approval approve` exits `11`, the check was cancelled or timed out and the approval still waits; if it exits `12`, the desktop app is not running and could not be started — open it and run the command again. See [Secrets → Approvals](/guides/secrets#approvals).

### The app says "This is not Coffer's daemon — nothing was sent"

**Cause.** The desktop app asks the daemon it found to prove it holds the master key, and the answer did not verify. Usually a stale `~/.coffer/daemon.json` points at a process that is not your daemon; occasionally something is squatting the port on purpose. The app sent no token and no grant.

**Fix.** Quit the app, run `coffer daemon restart` (or stop what holds the port), and open the app again. If it keeps happening on a machine you trust, check `lsof -i :<port>` for the process on Coffer's port.

### Every approval came back after an update, or a secret asks again

**Cause.** The files under `~/.coffer/local/secret-boundary/` are sealed. A file that was edited by hand, copied from another Mac, or written by a version before sealing (in a signed build) fails the check and is read as empty; the daemon logs `secret_boundary.state_unsealed` once. The protection returns to on and the bindings must be approved again.

**Fix.** Approve them again in the desktop app. Nothing was lost but the approvals.

### A signed Coffer ignores my `HTTPS_PROXY` or certificate bundle

**Cause.** By design. A signed daemon and model proxy drop the proxy and certificate variables they inherit (`HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY`, `SSL_CERT_FILE`, `NODE_EXTRA_CA_CERTS` and the like), so another program cannot point them at its own proxy or authority.

**Fix.** Set the proxy in macOS System Settings › Network and install the certificate in the macOS keychain. Coffer reads both from there. Development builds still honour the environment.

### An HTTP server or custom tool answers 401 after you add a key

**Cause.** The header's auth scheme and the stored key disagree. Coffer sends `<scheme> <key>`. If the secret already holds `Bearer …` from an older setup and the row's scheme is also **Bearer**, the server sees `Bearer Bearer …`. If the row's scheme is **None** but the API wants `Authorization: Bearer <key>`, the word `Bearer` is missing. A header like `X-Api-Key` wants **None**.

**Fix.** Open the server's **Edit** dialog (or the custom-tool group's), find the header row and set its scheme to what the API documents. Store only the raw key as the secret: choose **Replace value** and paste the key without `Bearer`. Save, then press **Test**. See [MCP servers → Auth scheme](/guides/mcp-servers#register-an-http-server).

### There is no way to print a secret from the terminal

**Cause.** By design: no command, route or MCP tool returns a stored value, because an agent can run any command you can. `coffer secret list` only shows which values are stored.

**Fix.** Reveal or copy it in the desktop app, which asks for Touch ID or your password; `coffer secret reveal <ref>` opens that reveal from the terminal, and the value still shows only in the app. To give a value to a command, store it as a standalone secret, allow `coffer run` to use it on the secret's page (Touch ID or your password in the desktop app), then run the command with `coffer run --secret ENV=coffer://secret/<id> -- <command>`. See [Secrets](/guides/secrets#allow-coffer-run-to-use-it).

See [Secret store](/guides/secret-store).

## Vault sync

| Symptom | Cause | Fix |
| --- | --- | --- |
| The **Sync** page shows `deletions held` (**Review deletions**) | The deletion breaker held a round. | Read the list on **Review held deletions**, then press **Delete N files** or **Keep the files**. After a reinstall, keep the files. |
| `stopped on conflicts` | Two machines changed the same file in ways git cannot merge. | **Resolve conflicts** on the **Sync** page: answer each file, then **Continue round**. To have your agent merge them, press **Hand off to &lt;Agent&gt;**; when its merge shows as **Merged by an agent · check it**, read the copy with **Open in editor** and press **Mark resolved**. |
| `join required` | This machine has not joined the remote. | **Join and pull** on the **Sync** page |
| Secrets cannot be decrypted | This machine lacks the master key. | **Import a master key** on **Settings › Security** |
| Push fails with an authentication error | Coffer does not use your global git config or the macOS keychain helper. | Store a token and choose it under **Secret** on the **Remote** tab, or use an SSH key that needs no passphrase prompt. |
| `push failed`, `sign-in refused` or `remote unreachable` you cannot explain | The remote's side: a protected branch, a token without write scope, a network or VPN problem. | The prompt beside the message on the **Sync** page hands the diagnosis to your agent, without the token. Then **Retry**. |

The full list is in [Vault sync troubleshooting](/guides/vault-sync#troubleshooting).

## Channels

### The bot does not answer

Open the channel's page first: its status line says what is wrong.

| What the page says | Cause | Fix |
| --- | --- | --- |
| No answer, or a daemon error | The daemon is not running. Channels run inside the daemon. | `coffer daemon start`. On macOS, **Settings → Daemon → Start at login** keeps it running without a Coffer window. |
| Running on another machine | The channel is bound to another machine sharing this vault, which answers instead. | Nothing, or move it here with **Run it here…** on the channel's page. |
| **Runs nowhere** | The channel names no machine. | Choose a machine under **Runs on** on the channel's **Settings** tab. |
| **Not paired** | Nobody has paired with the bot, so every message is ignored. | **Generate pairing code** on the channel's **Overview**, and send the code to the bot from your own account. |
| A `ws error:` line under the inbound status | A SeaTalk channel's connection failed. The error says why, for example another process holding the connection. | Fix the cause the error names. |
| A warning | A platform-side setting defeats part of the configuration. | Follow the fix in the warning. |

Messages are accepted only from the paired owner. In a group, the bot acts only on a message from the owner that addresses it. See [Channels](/guides/channels).

## Where the logs are

| File | Written by |
| --- | --- |
| `~/.coffer/logs/daemon.log` (+ `.1`–`.3`) | The daemon and everything acting for it. Readable on **Activity → Daemon**. |
| `~/.coffer/logs/shim-<pid>-<time>.log` | Each `coffer-mcp-shim` process an agent launched. Kept seven days. |
| `~/.coffer/logs/upstream/<server>.log` | Each stdio MCP server's stderr. |

`COFFER_LOG_DIR` moves the directory. To match a failed REST call to its log lines, take the `X-Coffer-Trace` header from the response and search `daemon.log` for it; see [Correlate a failed request](/guides/activity#correlate-a-failed-request-with-the-log-x-coffer-trace).

## Collect information for a bug report

1. The version: `coffer daemon status`, or **Settings → About → Copy diagnostics**.
2. How you installed it (desktop app, release archive, source) and your macOS version.
3. The error as printed, and the command or action that produced it. Re-run a failing `coffer` command with `coffer -v …` for the full traceback and HTTP context.
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
