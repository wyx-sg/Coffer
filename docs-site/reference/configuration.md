---
title: Configuration
description: Every environment variable, daemon-config.json key, experimental-feature switch and runtime setting Coffer reads, with its default and where it is read.
---

# Configuration

This page lists every knob that changes how Coffer behaves: environment variables, the keys of `~/.coffer/daemon-config.json`, the experimental-feature switches, and the runtime settings you change from **Settings** or the CLI. It is for operators and contributors who need the exact name, default and effect of a setting.

Coffer keeps configuration in four places, and each one exists for a reason:

| Where | Holds | Why there |
| --- | --- | --- |
| Environment variables | Operator escape hatches, test and dev overrides | Read by one process at start-up; nothing persists them |
| `~/.coffer/daemon-config.json` | Port, machine name and id, experimental features | Needed before the database is opened, and machine-local |
| The database (`~/.coffer/coffer.db`) | Coffer's model, upkeep passes, retention policies | Ordinary settings; some travel with [vault sync](/guides/vault-sync) |
| Browser `localStorage` | Web UI preferences | Per browser, never sent to the daemon |

::: warning Environment variables and a detached daemon
The daemon is usually spawned detached — by the CLI, by an agent's MCP shim, by the desktop app or by the login service — and inherits the environment of whichever process started it, not your shell profile. An environment variable only reaches the daemon if you set it in the environment of the process that starts it, for example `COFFER_FEATURES=memory=off coffer daemon restart`. Settings you want to keep belong in `daemon-config.json` or in **Settings**.
:::

## Environment variables

Links point at the file that reads each variable on GitHub.

### Daemon and network

| Name | Default | Effect | Where read |
| --- | --- | --- | --- |
| `COFFER_FEATURES` | unset | Pins experimental features for this daemon process, overriding the machine setting and the channel default. Syntax below. Read once at start. | [`infrastructure/daemon/config.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/daemon/config.py) |
| `COFFER_ALLOWED_HOSTS` | unset | Comma-separated extra `Host` header names the daemon answers besides `127.0.0.1`, `localhost` and `::1`; `*` disables the check. Requests naming any other host get `421 HOST_NOT_LOOPBACK`. | [`surfaces/http/host_guard.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/host_guard.py) |
| `COFFER_CORS_ORIGINS` | unset | Comma-separated list that replaces the CORS allow-list entirely. Without it the daemon allows only the desktop app's origins (`tauri://localhost`, `http://tauri.localhost`). | [`surfaces/http/cors.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/cors.py) |
| `COFFER_DEV_CORS` | unset | `1` adds the Vite dev server origins `http://localhost:5173` and `http://127.0.0.1:5173` to the default allow-list. Ignored when `COFFER_CORS_ORIGINS` is set. `make dev` sets it. | [`surfaces/http/cors.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/cors.py) |
| `COFFER_WEBUI_DIR` | built-in | Directory holding a built web UI (`index.html`). Without it the daemon serves the UI bundled into the frozen binary, or `frontend/dist` in a source checkout. | [`surfaces/http/webui.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/webui.py) |

### MCP gateway

| Name | Default | Effect | Where read |
| --- | --- | --- | --- |
| `COFFER_TOOL_TIERING` | `auto` | `off` lists every upstream tool to clients. Any other value keeps budget-driven tiering on. | [`application/mcp/tiering_config.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/mcp/tiering_config.py) |
| `COFFER_TOOL_TIERING_BUDGET` | `50` | How many upstream tools are listed directly before the rest are reachable only through `coffer__search_tools`. Non-positive or malformed values fall back to the default. | [`application/mcp/tiering_config.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/mcp/tiering_config.py) |
| `COFFER_TOOL_TIERING_WINDOW_DAYS` | `90` | The trailing window of invocation history used to rank tools for the budget. | [`application/mcp/tiering_config.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/mcp/tiering_config.py) |
| `COFFER_MCP_MAX_CONCURRENT_SPAWNS` | `4` | How many upstream MCP servers one session cold-starts at the same time. | [`application/mcp/supervisor.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/mcp/supervisor.py) |
| `COFFER_MCP_SESSION_IDLE_S` | `1800` | Seconds a `/mcp` session may sit idle before the reaper closes it and its upstream processes. | [`surfaces/http/app_mcp_composition.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/app_mcp_composition.py) |
| `COFFER_MCP_SESSION_REAPER_INTERVAL_S` | `60` | Seconds between reaper sweeps. | [`surfaces/http/app_mcp_composition.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/app_mcp_composition.py) |
| `COFFER_MCP_SHIM_PATH` | unset | Absolute path to a `coffer-mcp-shim` binary to write into an agent's MCP entry, tried before `PATH` and the bundled copy. Ignored if the file does not exist. | [`application/agent/mcp_service.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/agent/mcp_service.py) |

### Chat and channels

| Name | Default | Effect | Where read |
| --- | --- | --- | --- |
| `COFFER_TURN_IDLE_TIMEOUT_SECONDS` | `300` | Seconds a chat or channel turn may go without an event before the watchdog cancels it. `0`, a negative value or a non-number turns the watchdog off. | [`surfaces/http/chat_wiring.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/chat_wiring.py) |
| `COFFER_SEATALK_SDK_DIR` | `~/.coffer/vendor` | Directory the SeaTalk WebSocket SDK package (`seatalk_oapi_sdk`) is imported from. | [`infrastructure/channel/seatalk_sdk.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/channel/seatalk_sdk.py) |
| `COFFER_SEATALK_STREAM_INTERVAL` | `0.1` | Minimum seconds between streamed updates of a SeaTalk reply. | [`infrastructure/channel/live_text.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/channel/live_text.py) |

### Storage locations

These move a tree away from `~/.coffer`. They exist mainly so tests never touch a real vault; set them for a daemon only if you mean to run it against a different vault.

| Name | Default | Effect | Where read |
| --- | --- | --- | --- |
| `COFFER_DB_URL` | `sqlite+aiosqlite:///~/.coffer/coffer.db` | SQLAlchemy URL of the database. The credential master key file (`master.key`) lives beside the database file. | [`surfaces/http/app.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/surfaces/http/app.py) |
| `COFFER_KNOWLEDGE_ROOT` | `~/.coffer/knowledge` | Root of the knowledge collections. | [`infrastructure/knowledge/paths.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/knowledge/paths.py) |
| `COFFER_MEMORY_ROOT` | `~/.coffer/memory` | Root of the derived memory tree. | [`infrastructure/memory/paths.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/memory/paths.py) |
| `COFFER_SKILLS_ROOT` | `~/.coffer/skills` | Root of the skill master store, and the tree vault sync mirrors. | [`infrastructure/skill/master_store.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/skill/master_store.py), [`infrastructure/sync/paths.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/sync/paths.py) |
| `COFFER_AGENT_STATE_ROOT` | `~/.coffer/cache/agent` | Where the agent layer keeps derived state such as the transcript summary cache. | [`infrastructure/agent/paths.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/agent/paths.py) |
| `COFFER_LOG_DIR` | `~/.coffer/logs` | Directory for `daemon.log`, upstream server logs, MCP shim logs and the login service's output. | [`infrastructure/logging/files.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/logging/files.py) |
| `HOME` | the user's home | Every `~/.coffer` path is resolved against `$HOME`, so an alternate `HOME` gives a fully separate vault. | many modules |

### Installer

Read by `install.sh` ([`docs-site/public/install.sh`](https://github.com/wyx-sg/Coffer/blob/main/docs-site/public/install.sh)).

| Name | Default | Effect |
| --- | --- | --- |
| `COFFER_INSTALL_DIR` | `~/.coffer/bin` | Where the binaries are installed. |
| `COFFER_VERSION` | latest release | Release tag to install, for example `v0.1.0` (a leading `v` is optional). |
| `COFFER_NO_MODIFY_PATH` | `0` | `1` skips adding the install directory to your shell profile. |
| `ZDOTDIR`, `XDG_CONFIG_HOME` | shell defaults | Used to find the zsh and fish profile to edit. |

```sh
curl -fsSL --proto '=https' --tlsv1.2 https://wyx-sg.github.io/Coffer/install.sh \
  | COFFER_VERSION=v0.1.0 COFFER_NO_MODIFY_PATH=1 sh
```

### Development and tests

These are for contributors. Do not set them on a daemon you use day to day.

| Name | Default | Effect | Where read |
| --- | --- | --- | --- |
| `COFFER_PORT_RANGE_START`, `COFFER_PORT_RANGE_END` | unset | Bind the first free port in this range instead of the single configured port. Outranks `daemon-config.json`. If only one end is set, the other falls back to `8000` or `8009`. | [`infrastructure/daemon/bootstrap.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/daemon/bootstrap.py) |
| `COFFER_EVAL_CAPTURE` | unset | Records each `coffer__search_tools` query and its results as JSON lines for the eval harness. `1`, `true` or `yes` writes to `~/.coffer/eval-capture.jsonl`; any other non-falsy value is taken as the output path. | [`application/eval_capture.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/application/eval_capture.py), [`infrastructure/logging/eval_capture.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/infrastructure/logging/eval_capture.py) |
| `COFFER_RUN_BENCHMARKS` | unset | `1` runs the gateway-overhead benchmark (`make verify-benchmark`). | [`backend/tests/integration/perf/test_gateway_overhead.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/tests/integration/perf/test_gateway_overhead.py) |

### Variables Coffer sets for processes it starts

Coffer never reads these from its own environment; it sets them for child processes. You see them in an agent's config or in a process listing.

| Name | Set for | Purpose |
| --- | --- | --- |
| `CLAUDE_CONFIG_DIR` | Claude Code turns | Points Claude Code at a registered agent's config directory when it is not `~/.claude`. |
| `CODEX_HOME` | Codex turns | Points Codex at a registered agent's config directory when it is not `~/.codex`. |
| `COFFER_PROVIDER_KEY` | Codex turns | The API key of the model provider Coffer projected into Codex's `config.toml` (`model_providers.coffer.env_key`). The key is never written to disk. |
| `COFFER_GIT_TOKEN` | `git` during vault sync | The sync remote's token, read by a credential helper at run time so it never appears in `argv` or on disk. |
| `PATH`, `HOME` | the login service | Captured from your login shell when you install the service, so the daemon can find `npx`, `uvx` and other upstream launchers. |

The desktop app reads `HOME` (or `USERPROFILE`), `SHELL` and `PATH` to locate `~/.coffer` and to probe your login shell's `PATH`; it defines no variables of its own.

## daemon-config.json

`~/.coffer/daemon-config.json` holds the settings the daemon needs before it opens the database, plus the settings that must stay on one machine. It is written with mode `0600`. The daemon merges into it and preserves keys it does not recognise, so a file written by a newer Coffer survives an older one. A file that cannot be parsed is ignored with a warning in `daemon.log`, and the defaults apply.

```json
{
  "port": 8123,
  "machine_name": "studio",
  "machine_id": "3f0c9a…",
  "features": { "vault_sync": true, "memory": false },
  "memory_delivery_withdrawn": ["01J9ZX…"]
}
```

| Key | Type | Default | Effect | Changed with |
| --- | --- | --- | --- | --- |
| `port` | integer 1024–65535, or `null` | `8000` | The one port the daemon binds. The daemon refuses to start rather than move to another port. Takes effect at the next start. | `coffer daemon port set <port>`, `coffer daemon port clear` |
| `machine_name` | string | host name without `.local` | This machine's display label in vault sync. Free to change; nothing references it. | **Sync** page, `coffer sync machine rename` |
| `machine_id` | string | derived from the host | Cache of the host-derived machine id that names this machine in a synced vault. Deleting it recomputes the same value. | written by the daemon |
| `features` | object of booleans | `{}` | This machine's experimental-feature switches. Takes effect at once. | **Settings → General → Experimental features**, `coffer daemon features enable/disable` |
| `memory_delivery_withdrawn` | array of agent uids | absent | The agents whose memory delivery hook Coffer removed when `memory` was switched off, so switching it back on restores exactly those. | written by the daemon |

The daemon's runtime state — its pid, port and API token — lives in a different file, `~/.coffer/daemon.json`, which is created on start and removed on exit. See [Files and directories](/reference/filesystem#daemon-files).

## Experimental features

Three capabilities are experimental. Each can be switched off per machine; switching one off hides its pages, commands and routes and deletes nothing it holds.

| Key | Name in the UI | Routes it owns | Resource kinds it owns |
| --- | --- | --- | --- |
| `vault_sync` | Sync | `/api/v1/sync` | — |
| `knowledge` | Knowledge | `/api/v1/knowledge` | `knowledge` |
| `memory` | Memory | `/api/v1/memory` | `memory` |

While a feature is off, its routes answer `404` with code `FEATURE_DISABLED`, and the CLI prints the command that switches it back on. The registry lives in [`domain/features.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/domain/features.py).

### How a feature's state is decided

Highest precedence first:

1. **Pin** — an entry in `COFFER_FEATURES` for the daemon process. A pinned feature cannot be changed from the UI or CLI (`409 FEATURE_PINNED`).
2. **Setting** — this machine's value in `daemon-config.json` under `features`.
3. **Channel default** — on for a `dev` build, off for a `stable` build. Release builds are stamped `stable`; every other build (source runs, local frozen builds) is `dev`.

**Settings → General → Experimental features** shows which of the three decided each switch.

### COFFER_FEATURES syntax

A comma-separated list of `key=value` entries. `on`, `true` and `1` switch a feature on; `off`, `false` and `0` switch it off. Whitespace around entries is ignored and values are case-insensitive. An unknown key or a malformed entry is logged and skipped; it never stops the daemon.

```sh
COFFER_FEATURES="vault_sync=on,memory=off" coffer daemon restart
```

### Commands

```sh
coffer daemon features list             # every feature, its state, and what decided it
coffer daemon features enable memory    # switch on, at once
coffer daemon features disable knowledge
```

See [Experimental features](/guides/experimental-features) for the task-oriented guide.

## Runtime settings

These live in the database (or, where noted, elsewhere on disk) and are changed from **Settings** in the web UI or desktop app, or from the CLI. Settings marked *synced* travel to other machines through [vault sync](/guides/vault-sync).

### Settings → General

| Setting | Default | Effect | CLI | Stored in |
| --- | --- | --- | --- | --- |
| **Default rows per page** | `20` (choices 10, 20, 50, 100) | The initial page size of every table. | — | browser `localStorage` (`coffer.pageSize`) |
| **Preferred editor** | System default | The app or command Coffer opens managed files with. | — | browser `localStorage` (`coffer.preferredEditor`) |
| **Start at login** | off | Installs a launchd agent (`~/Library/LaunchAgents/dev.coffer.daemon.plist`) that starts the daemon at login and restarts it after a crash. macOS only. | `coffer daemon service install`, `uninstall`, `status` | the plist file |
| **Experimental features** | channel default | See [Experimental features](#experimental-features). | `coffer daemon features` | `daemon-config.json` |

### Settings → Coffer's model

The internal engine settings are one record, and all of them are *synced*.

| Setting | Default | Effect | CLI |
| --- | --- | --- | --- |
| **Model provider** / **Model** | none | The connection and model Coffer's own passes (memory distil, knowledge curation, descriptions) run on. With no model, those passes do not call a model. | `coffer engine model show`, `set`, `clear` |
| **Time limit per call** | `60` s | How long one call to Coffer's own model may take. | `coffer engine timeout show`, `set`, `default` |
| **Transcription provider** / **Transcription model** | off | The connection and model voice messages are transcribed with before an agent sees them. While either is unset, Coffer transcribes nothing. | `coffer engine transcribe-model show`, `set`, `clear` |
| **Automatic upkeep** — aggregate | on, every 1 h | Reads the agents' own memory files into the derived memory tree. | `coffer engine upkeep set aggregate --on/--off --interval <s>` |
| **Automatic upkeep** — distil | on, every 6 h | On its own interval, not after each aggregation: turns each partition's new raw entries into notes with Coffer's model and rewrites its `MEMORY.md`. A partition with nothing new costs no call. | `coffer engine upkeep set distil …` |
| **Automatic upkeep** — curate | on, every 60 s | Folds new material from each knowledge collection's inbox into its documents. | `coffer engine upkeep set curate …` |
| Curation owner (**Runs on:**) | every machine | The one machine allowed to run curation in a synced vault. | `coffer engine curate-owner show`, `set`, `clear` |

Upkeep intervals have a floor of 60 seconds; `--default-interval` returns a pass to its default. `coffer engine upkeep list` shows the current values and `coffer engine upkeep runs` shows passes in flight.

### Sync remote

The sync remote is one record in the database, set on the **Sync** page (**Setup**) or with `coffer sync remote set`. See [Vault sync](/guides/vault-sync).

| Setting | Default | Effect | CLI |
| --- | --- | --- | --- |
| **Interval (seconds)** | `3600` | Seconds between automatic rounds. At least `60`: a smaller value is refused, and one stored before the floor existed loads as `60`. | `coffer sync remote set --interval <s>` |
| **Converge automatically** | on | Off pauses the remote: every round reports `disabled`, and the remote and its history are kept. | `coffer sync remote pause`, `resume` |

### Settings → Data

Retention policies decide how long rows are kept. The retention worker prunes once at start-up and then every 6 hours. Policies are local to this machine.

| Policy | Key | Default | Effect |
| --- | --- | --- | --- |
| **Audit log** | `audit_log` | 365 days | Deletes audit entries older than the window. |
| **MCP invocations** | `mcp_invocations` | 30 days | Deletes gateway invocation log rows. |
| **Sync rounds** | `sync_runs` | 90 days | Deletes the history of sync rounds. |
| **Auto-archive idle chats** | `conversations_archive` | 7 days | Archives conversations with no new message for this long. |
| **Delete archived chats** | `conversations` | 30 days | Deletes archived conversations, with their messages, this long after archival. |

The key is what `coffer retention set` takes; both chat policies act on the `conversations` table. A policy can be set to **Keep forever**. The same run also deletes files in `~/.coffer/channel-media` older than 30 days and aged shim and upstream logs older than 7 days.

```sh
coffer retention list
coffer retention set audit_log --days 90
coffer retention set mcp_invocations --forever
coffer retention prune-now
```

### Settings → Security

| Setting | Default | Effect | CLI |
| --- | --- | --- | --- |
| **Store master key in OS keychain** | off (file) | Moves the credential master key between `~/.coffer/master.key` and the OS keychain (service `coffer`, entry `master-key`). The key itself never changes, so stored secrets stay readable. The move is audited. | `coffer credentials storage` |

## Related

- [Files and directories](/reference/filesystem)
- [Running the daemon](/guides/daemon)
- [Experimental features](/guides/experimental-features)
- [Credentials](/guides/credentials)
- [CLI reference](/reference/cli)
- [Distribution and releases](/architecture/distribution)
