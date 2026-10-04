---
title: Files and directories
description: Every file and directory Coffer keeps under ~/.coffer and writes into an agent's config directory, with its owner, whether it syncs, and whether it is safe to delete.
---

# Files and directories

This page maps everything Coffer keeps on disk: the `~/.coffer` tree, the one file outside it, and the entries Coffer writes into each registered agent's own config directory. Use it to back up a vault, to clean up safely, or to understand what a file you found is for.

Every path below is resolved against `$HOME`. There is no per-tree override, and the only locations environment variables move are the logs, the model proxy's usage spool and the history database (see [Configuration](/reference/configuration#storage-locations)).

## The ~/.coffer tree

State is kept in five [storage classes](/architecture/persistence), one directory or file each, plus the files the daemon and the installer need:

```text
~/.coffer/
├── vault/                        # the vault: a git repository — configuration and content
├── local/                        # this machine only: never synced, can be set again
├── content/                      # media and the chat workspace: your only copy, not synced
├── runs.db                       # history (SQLite, WAL mode)
├── runs.db-wal, runs.db-shm      # SQLite write-ahead log and shared memory
├── runs.db.pre-<revision>        # copy taken before a schema migration (newest 3 kept)
├── config-backups/               # copies of agent config files made before Coffer rewrites them: never synced, pruned by retention (each file's newest is kept)
├── skill-data/                   # logs, journals and temp files skill scripts write, one folder per skill: never synced, pruned by retention
├── derived/                      # rebuilt from the rest: always safe to delete
├── master.key                    # secret master key (when stored as a file)
├── machine-id                    # fallback machine id (only if the host gives none)
├── daemon.json                   # running daemon: pid, port, API token
├── daemon.lock                   # spawn lock
├── daemon-config.json            # ports, machine name, experimental features
├── proxy.json                    # running model proxy: pid, port, control token
├── proxy-usage/                  # model proxy usage spool, ingested by the daemon
├── bin/                          # deployed builds and the stable symlinks
├── logs/                         # daemon, proxy, shim and upstream logs
├── upstream-pids/                # pid files of spawned upstream MCP servers
├── vendor/                       # operator-supplied SeaTalk SDK
└── eval-capture.jsonl            # only with COFFER_EVAL_CAPTURE set
```

### The vault

`~/.coffer/vault/` is a git repository from the first time Coffer runs, whether or not you sync. Every accepted change is a commit naming its writer. See [Editing the vault by hand](/guides/vault-files).

```text
~/.coffer/vault/
├── manifest.json                       # {"schema_version": 3}
├── resources/<kind>/<name>.json        # mcp_server, skill, channel, provider, knowledge
├── state/mcp-preferences/<server>.json
├── state/channel-peers/<channel>.json
├── state/settings/internal-engine.json
├── knowledge/<collection>/             # documents, README.md, hidden .inbox/
├── skills/<name>/                      # skill master folders
├── secret/<ref>.enc
├── machines/<machine id>.json
└── .git/
```

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `vault/` as a whole | Your configuration and authored content, and its full history in `.git/`. | you, daemon, sync | Yes, when [vault sync](/guides/vault-sync) is on | **No.** It is the only copy. Stop the daemon before copying it. |
| `manifest.json` | The vault's layout number, `schema_version`, read before a sync round merges anything. | daemon | Yes | No |
| `resources/<kind>/<name>.json` | One JSON file per resource: `uid`, `kind`, `format_version`, `name`, an optional `title`, `description`, `config`. Identity is the `uid` inside, not the path. | you, daemon | Yes | No: the resource is gone on every machine that syncs. |
| `state/mcp-preferences/<server>.json` | The tools, prompts and resources you switched off on one MCP server, with that server's uid. | you, daemon | Yes | Yes: everything on that server is switched back on. |
| `state/channel-peers/<channel>.json` | The identities paired with one channel, including the owner. | daemon | Yes | The pairings are lost. |
| `state/settings/internal-engine.json` | Coffer's model, the curation owner machine, the per-call timeout, the transcription model and each upkeep pass's switch and interval. Absent means defaults. | you, daemon | Yes | Yes: the settings return to their defaults. |
| `knowledge/<collection>/` | A collection: Markdown documents in any nesting, plus a `README.md` describing it. You, your agents and Coffer's curation pass all edit these files. | you, daemon | Yes | **No.** This is written knowledge. |
| `knowledge/<collection>/.inbox/` | Items waiting to be curated into the documents: extracted upload text, a Markdown file an agent wrote there, a document added on the Knowledge page. | daemon | Yes | No: items not yet curated are lost. |
| `skills/<name>/` | The master copy of a managed skill: `SKILL.md`, its other files, and `.coffer.meta.json` (Coffer's metadata). Agents receive a symlink to this folder. | you, daemon | Yes | **No.** Deleting a folder breaks the links delivered to agents. |
| `secret/<ref>.enc` | One secret's Fernet ciphertext, mode `0600`. Never the key. Excluded from the repository unless the sync remote carries secrets. | daemon | Only with `--with-secret` | **No.** The secret is gone. |
| `machines/<machine id>.json` | One descriptor per machine that syncs: name, OS, hostname, Coffer version, last round, last converged commit, key fingerprint, agents and their plugins. | sync (each machine writes only its own) | Yes | Retire another machine with **Retire** in the **Sync** page's machine list. |
| `.git/` | The history of every file above. Snapshots before sync rounds are tags under `refs/tags/coffer/pre-apply/`. `.git/info/exclude` lists what the repository ignores. | daemon | The commits are what syncs | **No.** Every version and every rollback is lost. |

### Local

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `local/resources/agent/<name>.json` | This machine's agents, one resource file each. | daemon | Never | The agent is unregistered here. |
| `local/reach.json` | Every resource's reach on this machine: enabled, and for which agents. | daemon | Never | Every resource returns to its kind's default reach. |
| `local/engine.json` | When this machine last changed Coffer's engine settings. | daemon | Never | Yes. |
| `local/retention.json` | Each prunable table's retention and when it was last pruned. | daemon | Never | Yes: the defaults apply. |
| `local/curation.json` | The content each knowledge document had when curation last settled it, so a person's later edit is noticed. | daemon | Never | Curation re-reads every document once. |
| `local/skill-source-status.json` | What this machine last found at each Git-imported skill's source. | daemon | Never | Yes: the next check fills it in. |
| `local/secret/` | Machine-local ciphertext, such as the model proxy's tokens. | daemon | Never | The proxy tokens are minted again; agents on a provider re-read theirs. |
| `local/secret-boundary/` | `bindings.json`, `approvals.json`, `settings.json`, `times.json`: which destination each secret is approved for, pending approvals, the boundary's switches, when each secret was first stored here. | daemon | Never | Every secret waits for approval again. |
| `local/sync/remote.json` | The one sync remote: URL, branch, push secret ref, whether secrets travel, interval, paused. | daemon | Never | This machine forgets the remote. |
| `local/sync/round.json` | A stopped round, a hold, or a join's pending choices, with your answers so far. | daemon | Never | The question is asked again on the next round. |

A local file that does not parse is moved aside as `<name>.unreadable-<n>` and read as empty.

### Content

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `content/channel-media/` | Attachments received over Telegram and SeaTalk, saved so the agent can open them. Files older than the attachments retention window (30 days by default) are pruned. | daemon | No | Yes. |
| `content/chat-media/` | Files attached on the Conversations page: each upload's bytes (`<id><ext>`) beside a small `<id>.json` record of its name, type and size. Files older than the attachments retention window (30 days by default) are pruned. | daemon | No | Yes. A conversation keeps showing the file's chip, but a later turn can no longer open it. |
| `content/workspace/` | The default working directory for a chat when you pick none. | daemon | No | Only if no chat uses it. |

### History and keys

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `runs.db` | History: audit log, MCP invocation log, conversations and messages, channel threads and outbox, sync rounds and usage. `COFFER_DB_URL` names another database. | daemon | Never | You lose history, not configuration. Stop the daemon first. |
| `runs.db-wal`, `runs.db-shm` | SQLite write-ahead log and shared-memory index. The WAL can hold committed data not yet folded into `runs.db`. | daemon | No | **No**, and never copy `runs.db` without them while the daemon runs. |
| `runs.db.pre-<revision>` (+ `-wal`, `-shm`) | A copy taken just before a migration changes the schema. Only the newest three are kept. | daemon | No | Yes, once the upgraded daemon works. |
| `master.key` | The Fernet key that decrypts stored secrets, mode `0600`. Absent when the key lives in the OS keychain (service `coffer`, entry `master-key`). | daemon | **Never.** Back it up in the desktop app and install it on another machine from **Settings › Security › Import a master key**. | **No.** Without it every stored secret is unreadable. |
| `machine-id` | A random id, mode `0600`, used only when the host exposes no hardware id (macOS `IOPlatformUUID`, Linux machine-id). Never rewritten. | daemon | No | No: a new id splits this machine's identity in a synced vault. |

### Derived

Everything under `derived/` is rebuilt from the rest, so deleting it (with the daemon stopped) is always safe. **Settings → Data** clears the caches for you.

| Path | Purpose | Rebuilt by |
| --- | --- | --- |
| `derived/derived.db` | MCP server health, which skill copies were delivered into which agent, when each upstream capability was first and last seen. Recreated when its schema version differs. | Health checks, skill delivery, the gateway |
| `derived/memory/<partition>/` | Derived memory for `global` or one repository: `MEMORY.md` (index), `notes/`, `RETIRED.md` (what was retired and why), hidden `.raw/` (what aggregation read, verbatim). `.source_state.json` at the root records what the last aggregation read. | Aggregation and distil (retirement decisions in `RETIRED.md` and your edits to notes are lost) |
| `derived/cache/agent/.transcript_summaries.json` | What the transcript reader already parsed. | The next read, slowly |
| `derived/resources/` | Derived resource files: memory partitions, and `skill/coffer-guide.json`. | The daemon at start |
| `derived/skills/coffer-guide/` | Coffer's own guide skill, rendered from this build. | The daemon at start |
| `derived/sync-conflicts/` | Marked-up copies of a stopped round's conflicting files, for a hand merge. | Opening the file in an editor again |

### Daemon files {#daemon-files}

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `daemon.json` | Runtime state of the running daemon: `version`, `pid`, `port`, `token`, `started_at`, `binary_path`. Mode `0600`. Every client (CLI, shim, desktop app, web UI dev server) reads the port and API token from it. Removed when the daemon exits. | daemon | No | Only while no daemon runs. A stale file is detected and ignored. |
| `daemon.lock` | `flock` target that serialises detect-or-spawn, so two clients never start two daemons. Left on disk between runs by design. | daemon, CLI, shim | No | Yes, while no daemon is starting. |
| `daemon-config.json` | Settings read before the database opens: `port`, `proxy_port`, `machine_name`, `machine_id` (cache), `features`. Mode `0600`. See [Configuration](/reference/configuration#daemon-config-json). | daemon, CLI | No (machine-local on purpose) | Yes: the daemon falls back to port 38470, the host name and the defaults (every experimental feature off). |
| `proxy.json` | Runtime state of the running [model proxy](/architecture/model-proxy): `port`, `pid`, `started_at`, `version` and `control_token`, the token the daemon uses to push the proxy its state and tell it to drain. Mode `0600`. Written by the proxy once its socket is bound, and removed on exit only while it still names that proxy's pid. The proxy outlives daemon restarts, and a new daemon finds it through this file. | model proxy | No | Only while no proxy runs. |
| `proxy-usage/<pid>-<start>-<seq>.jsonl` (`.jsonl.part` while open) | The model proxy's usage records, one JSON object per line, metadata only. The proxy never opens the database; the daemon ingests each finished file. `COFFER_PROXY_SPOOL_DIR` moves the directory. | model proxy, daemon | No | Finished files not yet ingested are lost from the usage report. |
| `upstream-pids/<server-uid>-<pid>.json` | One file per upstream MCP server process the daemon spawned, so the next daemon can reap orphans after a crash. | daemon | No | Yes, while the daemon is stopped. |

See [Daemon and processes](/architecture/daemon) and [Running the daemon](/guides/daemon).

### Binaries

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `bin/<version>/` | One directory per deployed frozen build, holding `coffer`, `coffer-daemon` and `coffer-mcp-shim`, each with a `.<name>.version` sentinel written after the copy completes. The current and the previous version are kept. | installer, daemon (frozen builds) | No | Old version directories, yes. Not the one the symlinks point at. |
| `bin/coffer`, `bin/coffer-daemon`, `bin/coffer-mcp-shim` | Relative symlinks into the current version directory, flipped atomically on upgrade. Agents' MCP entries, the login service and your `PATH` use these stable names. | installer, daemon | No | No: agents' MCP entries point at `bin/coffer-mcp-shim`. |

To undo an upgrade by hand, point the symlinks back at the previous version directory. A frozen daemon deploys its sibling binaries here on start; a source install uses the console scripts `pip` put on `PATH` instead. See [Distribution and releases](/architecture/distribution).

### Skill working files

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `skill-data/<skill-name>/` | Where a skill's scripts keep the logs, operation journals and temporary files they generate. It sits outside the vault, so none of it syncs, and `coffer path skill-data` prints the directory. Files whose last-modified time is older than the **Skill working files** retention window (30 days by default) are deleted, folders left empty with them. | skills' scripts; daemon prunes | No | Yes. Anything a skill needs for good does not belong here. |

### Config backups

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `config-backups/<file>-<hash>/<name>.coffer-backup-<UTC time>` | The previous content of an agent's config file (`~/.codex/config.toml`, `~/.claude/settings.json`, `~/.claude.json`, a memory or subagent file), copied here before Coffer rewrites or deletes it. One folder per file, named for the file and a short hash of its full path; each backup is named by the UTC time it was taken. It sits outside the vault, so none of it syncs. Backups older than the **Config backups** retention window (30 days by default) are deleted, except that **the newest backup of each file is always kept**, so the last write can always be undone. | daemon (the config writer); daemon prunes | No | Yes, but you lose the undo. |

### Logs

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `logs/daemon.log`, `daemon.log.1`…`.3` | The daemon's log, one JSON object per line, rotated at 10 MB with three backups. The desktop app and the login service write their own records into the same file. Shown on the **Activity** page, read by `coffer log daemon`, and located by `coffer path logs`. | daemon, desktop app | No | Rotated files, yes. Leave the live file while the daemon runs. |
| `logs/proxy.log` | Standard error of the model proxy: metadata-only lines, never a body, prompt or secret. | daemon (supervisor), model proxy | No | Yes. |
| `logs/shim-<pid>-<epoch>.log` | One file per MCP shim process, created only when the shim has something to log. Pruned after 7 days. | shim | No | Yes. |
| `logs/upstream/<server>.log`, `.log.1` | Standard error of each stdio upstream MCP server. Rolled aside at 2 MB; the `.1` copy is pruned after 7 days. | daemon | No | Yes. |

`COFFER_LOG_DIR` moves the daemon, proxy, upstream and shim logs together. See [Observability](/architecture/observability).

### Other files

| Path | Purpose | Owner | Syncs | Safe to delete |
| --- | --- | --- | --- | --- |
| `vendor/` | Where you place the SeaTalk WebSocket SDK (`seatalk_oapi_sdk`). Coffer only reads it. | you | No | Yes, if you do not use SeaTalk. |
| `eval-capture.jsonl` | Captured `coffer__search_tools` calls, only when `COFFER_EVAL_CAPTURE` is set. | daemon | No | Yes. |

## Outside ~/.coffer

| Path | Purpose | Owner | Safe to delete |
| --- | --- | --- | --- |
| `~/Library/LaunchAgents/dev.coffer.daemon.plist` | The login service that starts the daemon at login and restarts it after a crash (macOS). Runs `~/.coffer/bin/coffer-daemon` and logs to `~/.coffer/logs/daemon.log`. | daemon (**Settings → Daemon → Start at login**) | Turn off **Start at login** instead. |
| Your shell profile | `install.sh` appends `~/.coffer/bin` to `PATH` unless `COFFER_NO_MODIFY_PATH=1`. | installer | Remove the line by hand. |

## Inside an agent's config directory

Coffer writes into a registered agent's own config directory only for things you asked for: connecting it to Coffer, delivering a skill, switching a model provider, or editing a config file from the agent's page. Every write is atomic, and the previous version of an edited file is first copied to `~/.coffer/config-backups`, never next to the file (see [Config backups](#config-backups)).

The config directory is `~/.claude` for Claude Code and `~/.codex` for Codex by default. An agent registered with another directory gets `CLAUDE_CONFIG_DIR` or `CODEX_HOME` set on every process Coffer starts for it.

### Claude Code

| File | What Coffer writes | When |
| --- | --- | --- |
| `~/.claude.json` (inside the config dir for a non-default one) | `mcpServers.coffer`: `{"command": "~/.coffer/bin/coffer-mcp-shim", "args": ["--agent-uid", "<uid>"]}` with the absolute shim path. | Connecting the agent to Coffer. See [Agents](/guides/agents#connect-an-agent-to-coffer). |
| `settings.json` | `apiKeyHelper` set to `<absolute path to coffer> proxy token --agent-uid <agent uid>` (for example `/Users/you/.coffer/bin/coffer …`; the bare `coffer` only when no CLI can be found), which prints the agent's local proxy token; `env.ANTHROPIC_BASE_URL` set to the model proxy's `http://127.0.0.1:<proxy port>/anthropic`; `127.0.0.1,localhost` appended to `env.NO_PROXY`; and the model keys (`model`, `env.ANTHROPIC_DEFAULT_<TIER>_MODEL`, `modelPicker`). No provider key is ever written. | Switching the agent to a model provider. See [Model providers](/guides/providers). |
| `settings.json` | Two hook entries whose command begins `: coffer-memory;` and runs the `coffer` CLI by full path as `coffer memory hook --agent-uid <uid> --cwd "$PWD"`: `hooks.SessionStart` (matcher `startup\|resume\|clear\|compact`, 10-second timeout) and `hooks.UserPromptSubmit` (5-second timeout). | Connecting the agent to Coffer. See [Memory](/guides/memory#install-the-hook). |
| `skills/<name>` | A symlink to `~/.coffer/vault/skills/<name>` (a copy where symlinks are unavailable). | Delivering a skill to the agent. See [Skills](/guides/skills). |

### Codex

| File | What Coffer writes | When |
| --- | --- | --- |
| `config.toml` | `[mcp_servers.coffer]` with `command` set to the shim and `args = ["--agent-uid", "<uid>"]`. | Connecting the agent to Coffer. |
| `config.toml` | `model_provider = "coffer"`, a `[model_providers.coffer]` table with `base_url` set to the model proxy's `http://127.0.0.1:<proxy port>/openai/v1`, `supports_websockets = false`, `requires_openai_auth = false` and an `auth` command (`coffer` by absolute path, `args = ["proxy", "token", "--agent-uid", "<agent uid>"]`), and `model_catalog_json` pointing at the catalogue below. No provider key is ever written. | Switching the agent to a model provider. |
| `coffer-model-catalog.json` | The provider's curated model list, so Codex's own model picker shows it. Removed when the provider is switched off. | Switching the agent to a model provider. |
| `hooks.json` | The same two hook entries as for Claude Code, on the same events with the same matcher and timeouts, all running `coffer memory hook`. Coffer reads, and never writes, Codex's approval of each entry in `config.toml`'s `[hooks.state]`. | Connecting the agent to Coffer. |
| `skills/<name>` | A symlink to `~/.coffer/vault/skills/<name>`. | Delivering a skill to the agent. |

Coffer recognises its own entries by the `coffer` server key, the `: coffer-memory` marker and an `apiKeyHelper` that runs the `coffer` CLI (bare or by any path) with `proxy token`, and removes only those. Every other entry — your own MCP servers, other tools' hooks, your `env` — is left as it was. Coffer reads the agents' native memory files but never writes them.

::: tip Cleaning up an agent
Before removing Coffer, disconnect each agent from Coffer and remove the provider projection from each agent's page, then delete `~/.coffer`. Deleting `~/.coffer` first leaves the agents pointing at a shim that no longer exists.
:::

## Related

- [Configuration](/reference/configuration)
- [Persistence](/architecture/persistence)
- [Security model](/architecture/security)
- [Vault sync](/guides/vault-sync)
- [Editing the vault by hand](/guides/vault-files)
- [Troubleshooting](/guides/troubleshooting)
