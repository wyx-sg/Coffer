---
title: Files and directories
description: Every file and directory Coffer keeps under ~/.coffer and writes into an agent's config directory, with its owner, whether it syncs, and whether it is safe to delete.
---

# Files and directories

This page maps everything Coffer keeps on disk: the `~/.coffer` tree, the one file outside it, and the entries Coffer writes into each registered agent's own config directory. Use it to back up a vault, to clean up safely, or to understand what a file you found is for.

Every path below is resolved against `$HOME`. The storage-location environment variables in [Configuration](/reference/configuration#storage-locations) move individual trees elsewhere.

## The ~/.coffer tree

```text
~/.coffer/
├── coffer.db                     # the database (SQLite, WAL mode)
├── coffer.db-wal, coffer.db-shm  # SQLite write-ahead log and shared memory
├── coffer.db.pre-<revision>      # copy taken before a schema migration (newest 3 kept)
├── master.key                    # credential master key (when stored as a file)
├── machine-id                    # fallback machine id (only if the host gives none)
├── daemon.json                   # running daemon: pid, port, API token
├── daemon.lock                   # spawn lock
├── daemon-config.json            # port, machine name, experimental features
├── bin/
│   ├── coffer -> <version>/coffer
│   ├── coffer-daemon -> <version>/coffer-daemon
│   ├── coffer-mcp-shim -> <version>/coffer-mcp-shim
│   └── <version>/                # one directory per deployed build (newest 2 kept)
├── logs/
│   ├── daemon.log, daemon.log.1…3
│   ├── shim-<pid>-<epoch>.log
│   └── upstream/<server>.log, <server>.log.1
├── knowledge/<collection>/       # knowledge documents (+ README.md, hidden .inbox/)
├── memory/<partition>/           # derived memory (MEMORY.md, notes/, RETIRED.md, .raw/)
├── skills/<name>/                # skill master store (SKILL.md, .coffer.meta.json, …)
├── sync/                         # vault sync working tree (a git repository)
├── cache/agent/                  # derived agent state
├── state/                        # one-off markers
├── upstream-pids/                # pid files of spawned upstream MCP servers
├── channel-media/                # attachments received over channels
├── workspace/                    # default working directory for chats
├── vendor/                       # operator-supplied SeaTalk SDK
└── eval-capture.jsonl            # only with COFFER_EVAL_CAPTURE set
```

### Database and keys

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `coffer.db` | Every resource (MCP servers, agents, providers, channels, …), credentials as Fernet ciphertext, conversations, audit log, MCP invocation log, settings. | daemon | Resources and shared settings travel as YAML documents in the sync tree; the file itself never does | **No.** This is the vault. Stop the daemon before copying it. |
| `coffer.db-wal`, `coffer.db-shm` | SQLite write-ahead log and shared-memory index. The WAL can hold committed data not yet folded into `coffer.db`. | daemon | No | **No**, and never copy `coffer.db` without them while the daemon runs. |
| `coffer.db.pre-<revision>` (+ `-wal`, `-shm`) | A copy of the database taken just before a migration changes the schema. Only the newest three are kept. | daemon | No | Yes, once the upgraded daemon works. To roll back a failed upgrade, stop the daemon and rename the copy to `coffer.db`. |
| `master.key` | The Fernet key that decrypts stored credentials, mode `0600`. Absent when the key lives in the OS keychain (service `coffer`, entry `master-key`). Always beside the database file. | daemon | **Never.** Move it between machines with `coffer sync key`. | **No.** Without it every stored secret is unreadable. |
| `machine-id` | A random id, mode `0600`, used only when the host exposes no hardware id (macOS `IOPlatformUUID`, Linux machine-id). Never rewritten. | daemon | No | No: a new id splits this machine's identity in a synced vault. |

See [Persistence](/architecture/persistence) and [Credentials](/guides/credentials).

### Daemon files {#daemon-files}

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `daemon.json` | Runtime state of the running daemon: `version`, `pid`, `port`, `token`, `started_at`, `binary_path`. Mode `0600`. Every client (CLI, shim, desktop app, web UI dev server) reads the port and API token from it. Removed when the daemon exits. | daemon | No | Only while no daemon runs. A stale file is detected and ignored. |
| `daemon.lock` | `flock` target that serialises detect-or-spawn, so two clients never start two daemons. Left on disk between runs by design. | daemon, CLI, shim | No | Yes, while no daemon is starting. |
| `daemon-config.json` | Settings read before the database opens: `port`, `machine_name`, `machine_id` (cache), `features`, `memory_delivery_withdrawn`. Mode `0600`. See [Configuration](/reference/configuration#daemon-config-json). | daemon, CLI | No (machine-local on purpose) | Yes: the daemon falls back to port 8000, the host name and the channel defaults. |
| `upstream-pids/<server-uid>-<pid>.json` | One file per upstream MCP server process the daemon spawned, so the next daemon can reap orphans after a crash. | daemon | No | Yes, while the daemon is stopped. |
| `state/removed-agent-notice.done` | Marks that the one-time notice about config directories of agent types Coffer no longer supports was logged. | daemon | No | Yes; the notice is logged once more. |

See [Daemon and processes](/architecture/daemon) and [Running the daemon](/guides/daemon).

### Binaries

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `bin/<version>/` | One directory per deployed frozen build, holding `coffer`, `coffer-daemon` and `coffer-mcp-shim`, each with a `.<name>.version` sentinel written after the copy completes. The current and the previous version are kept. | installer, daemon (frozen builds) | No | Old version directories, yes. Not the one the symlinks point at. |
| `bin/coffer`, `bin/coffer-daemon`, `bin/coffer-mcp-shim` | Relative symlinks into the current version directory, flipped atomically on upgrade. Agents' MCP entries, the login service and your `PATH` use these stable names. | installer, daemon | No | No: agents' MCP entries point at `bin/coffer-mcp-shim`. |

To undo an upgrade by hand, point the symlinks back at the previous version directory. A frozen daemon deploys its sibling binaries here on start; a source install uses the console scripts `pip` put on `PATH` instead. See [Distribution and releases](/architecture/distribution).

### Logs

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `logs/daemon.log`, `daemon.log.1`…`.3` | The daemon's log, one JSON object per line, rotated at 10 MB with three backups. The desktop app and the login service write their own records into the same file. Shown on the **Activity** page and read by `coffer__diagnose`. | daemon, desktop app | No | Rotated files, yes. Leave the live file while the daemon runs. |
| `logs/shim-<pid>-<epoch>.log` | One file per MCP shim process, created only when the shim has something to log. Pruned after 7 days. | shim | No | Yes. |
| `logs/upstream/<server>.log`, `.log.1` | Standard error of each stdio upstream MCP server. Rolled aside at 2 MB; the `.1` copy is pruned after 7 days. | daemon | No | Yes. |

`COFFER_LOG_DIR` moves the daemon and upstream logs; shim logs always go to `~/.coffer/logs`. See [Observability](/architecture/observability).

### Knowledge, memory and skills

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `knowledge/<collection>/` | A collection: Markdown documents in any nesting, plus a `README.md` describing the collection. You and Coffer's curation pass both edit these files. | you, daemon | Yes, when [vault sync](/guides/vault-sync) is on | **No.** This is written knowledge. |
| `knowledge/<collection>/.inbox/` | New material waiting to be merged into the documents: extracted upload text, an agent's `coffer__write`. Each item is removed once curation folds it in. | daemon | Yes | No: unmerged material is lost. |
| `knowledge.pre-<revision>.bak/` | A copy of the knowledge tree taken before a migration that restructured it. | daemon | No | Yes, once you have checked the migrated tree. |
| `memory/<partition>/` | Derived memory for `global` or one repository: `MEMORY.md` (index), `notes/` (Coffer's notes), `RETIRED.md` (what was retired and why). | daemon (distil pass) | **No** (derived and local) | Yes: aggregation and distil rebuild it. Retirement decisions in `RETIRED.md` are lost. |
| `memory/<partition>/.raw/` | What aggregation read out of the agents' own memory, verbatim. | daemon (aggregate pass) | No | Yes: the next aggregation rereads the agents. |
| `skills/<name>/` | The master copy of a managed skill: `SKILL.md`, its other files, and `.coffer.meta.json` (Coffer's metadata). Agents receive a symlink to this folder. | daemon | Yes, except `skills/coffer-guide/`, which each machine renders for itself | **No.** Deleting a folder breaks the symlinks delivered to agents. |

See [Knowledge](/guides/knowledge), [Memory](/guides/memory) and [Skills](/guides/skills).

### Sync

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `sync/` | The git working tree that converges with your sync remote. The location is part of the remote's configuration; `~/.coffer/sync` is the default. It may not sit inside, at or above the knowledge, skills or memory roots. | daemon | It *is* what syncs | Not while a remote is configured: it holds the merge base. |
| `sync/manifest.json` | Layout version of the tree, read before anything is applied. | daemon | Yes | — |
| `sync/resources/<kind>/<uid>.yaml` | One document per synced resource. | daemon | Yes | — |
| `sync/state/<area>/…yaml` | Shared state owned by one module, for example the internal engine settings. | daemon | Yes | — |
| `sync/credentials/<ref>.enc` | Credential ciphertext, only when you opt in. Never the key. | daemon | Yes | — |
| `sync/machines/<machine-id>.yaml` | One descriptor per machine sharing the vault. | daemon | Yes | — |
| `sync/knowledge/`, `sync/skills/` | Mirrors of the live trees. | daemon | Yes | — |

Each applied round is preceded by a git tag under `coffer/pre-apply/` in this repository, which `coffer sync rollback` returns to. See [Vault sync](/architecture/vault-sync).

### Caches, media and working directories

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `cache/agent/.transcript_summaries.json` | What the transcript reader already parsed, so the conversation history list loads without rereading every transcript. | daemon | No | Yes; it is rebuilt, slowly, on the next read. |
| `channel-media/` | Attachments (images, files, voice, documents) received over Telegram and SeaTalk, saved so the agent can open them. Files older than 30 days are pruned. | daemon | No | Yes. |
| `workspace/` | The default working directory for a chat when you pick none. | daemon | No | Only if no chat uses it. |
| `vendor/` | Where you place the SeaTalk WebSocket SDK (`seatalk_oapi_sdk`). Coffer only reads it. | you | No | Yes, if you do not use SeaTalk. |
| `eval-capture.jsonl` | Captured `coffer__search_tools` calls, only when `COFFER_EVAL_CAPTURE` is set. | daemon | No | Yes. |

## Outside ~/.coffer

| Path | Purpose | Owner | Safe to delete |
| --- | --- | --- | --- |
| `~/Library/LaunchAgents/dev.coffer.daemon.plist` | The login service that starts the daemon at login and restarts it after a crash (macOS). Runs `~/.coffer/bin/coffer-daemon` and logs to `~/.coffer/logs/daemon.log`. | daemon (**Settings → General → Start at login**, `coffer daemon service install`) | Use `coffer daemon service uninstall` instead. |
| `${TMPDIR:-/tmp}/.coffer-memory-fired-<pid>` | Once-per-session guard of the Codex memory delivery hook. | the hook | Yes. |
| Your shell profile | `install.sh` appends `~/.coffer/bin` to `PATH` unless `COFFER_NO_MODIFY_PATH=1`. | installer | Remove the line by hand. |

## Inside an agent's config directory

Coffer writes into a registered agent's own config directory only for things you asked for: installing its MCP entry, delivering a skill, switching a model provider, installing memory delivery, or editing a config file from the agent's page. Every write is atomic, and the previous version of an edited file is kept as `<file>.bak`, `<file>.bak.1` and `<file>.bak.2`.

The config directory is `~/.claude` for Claude Code and `~/.codex` for Codex by default. An agent registered with another directory gets `CLAUDE_CONFIG_DIR` or `CODEX_HOME` set on every process Coffer starts for it.

### Claude Code

| File | What Coffer writes | When |
| --- | --- | --- |
| `~/.claude.json` (inside the config dir for a non-default one) | `mcpServers.coffer`: `{"command": "~/.coffer/bin/coffer-mcp-shim", "args": ["--agent-uid", "<uid>"]}` with the absolute shim path. | Installing Coffer's MCP entry. See [Connect a client](/guides/connect-a-client). |
| `settings.json` | `apiKeyHelper` set to `coffer provider key --connection-uid <uid>` and `env.ANTHROPIC_BASE_URL`, `env.ANTHROPIC_MODEL`, `env.ANTHROPIC_SMALL_FAST_MODEL`. The API key itself is never written. | Switching the agent to a model provider. See [Model providers](/guides/providers). |
| `settings.json` | A `hooks.SessionStart` entry, matcher `startup\|resume\|clear\|compact`, whose command begins `: coffer-memory;` and runs `coffer memory context --agent-uid <uid> --cwd "$PWD"`. | Installing memory delivery. See [Memory](/guides/memory). |
| `skills/<name>` | A symlink to `~/.coffer/skills/<name>` (a copy where symlinks are unavailable). | Delivering a skill to the agent. See [Skills](/guides/skills). |

### Codex

| File | What Coffer writes | When |
| --- | --- | --- |
| `config.toml` | `[mcp_servers.coffer]` with `command` set to the shim and `args = ["--agent-uid", "<uid>"]`. | Installing Coffer's MCP entry. |
| `config.toml` | `model_provider = "coffer"`, a `[model_providers.coffer]` table whose `env_key` is `COFFER_PROVIDER_KEY`, and `model_catalog_json` pointing at the catalogue below. | Switching the agent to a model provider. |
| `coffer-model-catalog.json` | The provider's curated model list, so Codex's own model picker shows it. Removed when the provider is switched off. | Switching the agent to a model provider. |
| `hooks.json` | A `hooks.UserPromptSubmit` entry whose command begins `: coffer-memory;`, guarded to fire once per session, with a 10-second timeout. | Installing memory delivery. |
| `skills/<name>` | A symlink to `~/.coffer/skills/<name>`. | Delivering a skill to the agent. |

Coffer recognises its own entries by the `coffer` server key, the `: coffer-memory` marker and the `coffer provider key` helper prefix, and removes only those. Every other entry — your own MCP servers, other tools' hooks, your `env` — is left as it was. Coffer reads the agents' native memory files but never writes them.

::: tip Cleaning up an agent
Before removing Coffer, uninstall the MCP entry, memory delivery and provider projection from each agent's page (or the matching `coffer agent` and `coffer provider` commands), then delete `~/.coffer`. Deleting `~/.coffer` first leaves the agents pointing at a shim that no longer exists.
:::

## Related

- [Configuration](/reference/configuration)
- [Persistence](/architecture/persistence)
- [Security model](/architecture/security)
- [Vault sync](/guides/vault-sync)
- [Troubleshooting](/guides/troubleshooting)
