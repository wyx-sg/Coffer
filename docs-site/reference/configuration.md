---
title: Configuration
description: Every environment variable, daemon-config.json key, experimental-feature switch and runtime setting Coffer reads, with its default and where it is read.
---

# Configuration

This page lists every knob that changes how Coffer behaves: environment variables, the keys of `~/.coffer/daemon-config.json`, the experimental-feature switches, and the runtime settings you change from **Settings**. It is for operators and contributors who need the exact name, default and effect of a setting.

Coffer keeps configuration in five places, and each one exists for a reason:

| Where | Holds | Why there |
| --- | --- | --- |
| Environment variables | Operator escape hatches, test and dev overrides | Read by one process at start-up; nothing persists them |
| `~/.coffer/daemon-config.json` | Daemon and model-proxy ports, machine name and id, experimental features | Needed before anything else is opened, and machine-local |
| The vault (`~/.coffer/vault/state/settings/internal-engine.json`) | The speech-to-text model, the model-call time limit, the aggregate and distil switches and intervals | Settings every machine shares; they travel with [vault sync](/guides/vault-sync) |
| Local state (`~/.coffer/local/`) | Retention policies, the sync remote, reach | True of this machine only; never synced |
| Browser `localStorage` | Web UI preferences | Per browser, never sent to the daemon |

::: warning Environment variables and a detached daemon
The daemon is usually spawned detached — by the CLI, by an agent's MCP shim, by the desktop app or by the login service — and inherits the environment of whichever process started it, not your shell profile. An environment variable only reaches the daemon if you set it in the environment of the process that starts it, for example `COFFER_FEATURES=run=off,models=off coffer daemon restart`. Settings you want to keep belong in `daemon-config.json` or in **Settings**.
:::

## Environment variables

### Daemon and network

| Name | Default | Effect |
| --- | --- | --- |
| `COFFER_FEATURES` | unset | Pins experimental features for this daemon process, overriding the machine setting and the default (off). Syntax below. Read once at start. |
| `COFFER_ALLOWED_HOSTS` | unset | Comma-separated extra `Host` header names the daemon answers besides `127.0.0.1`, `localhost` and `::1`; `*` disables the check. Requests naming any other host, or a loopback name on another port, get `403 HOST_NOT_ALLOWED`. Never relaxes the `Origin` check. A tagged release build ignores it. |
| `COFFER_CORS_ORIGINS` | unset | Comma-separated list of exact origins that replaces the cross-origin allow-list entirely, for both CORS and the `Origin` check. Without it the daemon allows only the desktop app's origins (`tauri://localhost`, `http://tauri.localhost`). The daemon's own origins are always allowed; any other origin gets `403 ORIGIN_NOT_ALLOWED`. A tagged release build ignores it. |
| `COFFER_DEV_CORS` | unset | `1` adds the Vite dev server origins `http://localhost:5173` and `http://127.0.0.1:5173` to the default allow-list, for both CORS and the `Origin` check. Ignored when `COFFER_CORS_ORIGINS` is set. A tagged release build ignores it. `make dev` sets it. |
| `COFFER_WEBUI_DIR` | built-in | Directory holding a built web UI (`index.html`). Without it the daemon serves the UI bundled into the frozen binary, or `frontend/dist` in a source checkout. |
| `COFFER_PRICE_REFRESH` | unset | `off` pins the daily model price-list refresh off, whatever `price_refresh` says; prices come from the list shipped in the build. The test suite and the e2e daemon set it. |
| `COFFER_MODEL_PROXY` | unset | `off` keeps the daemon from starting or supervising the [local model proxy](/architecture/model-proxy); any other value, or none, leaves it on. The test suite sets it. |

### MCP gateway

| Name | Default | Effect |
| --- | --- | --- |
| `COFFER_TOOL_TIERING` | `auto` | `off` lists every upstream tool to clients. Any other value keeps budget-driven tiering on. |
| `COFFER_TOOL_TIERING_BUDGET` | `50` | How many upstream tools are listed directly before the rest are reachable only through `coffer__search_tools`. Non-positive or malformed values fall back to the default. |
| `COFFER_TOOL_TIERING_WINDOW_DAYS` | `90` | The trailing window of invocation history used to rank tools for the budget. |
| `COFFER_MCP_MAX_CONCURRENT_SPAWNS` | `4` | How many upstream MCP servers one session cold-starts at the same time. |
| `COFFER_MCP_SESSION_IDLE_S` | `1800` | Seconds a `/mcp` session may sit idle before the reaper closes it and its upstream processes. |
| `COFFER_MCP_SESSION_REAPER_INTERVAL_S` | `60` | Seconds between reaper sweeps. |
| `COFFER_MCP_SHIM_PATH` | unset | Absolute path to a `coffer-mcp-shim` binary to write into an agent's MCP entry, tried before `PATH` and the bundled copy. Ignored if the file does not exist. |

### Chat and channels

| Name | Default | Effect |
| --- | --- | --- |
| `COFFER_TURN_IDLE_TIMEOUT_SECONDS` | `300` | Seconds a chat or channel turn may go without an event before the watchdog cancels it. `0`, a negative value or a non-number turns the watchdog off. |
| `COFFER_SEATALK_SDK_DIR` | `~/.coffer/vendor` | Directory the SeaTalk WebSocket SDK package (`seatalk_oapi_sdk`) is imported from. |
| `COFFER_SEATALK_STREAM_INTERVAL` | `0.1` | Minimum seconds between streamed updates of a SeaTalk reply. |

### Storage locations

The vault, local state, content and derived state have no per-tree override: every one of them is resolved from `$HOME` when it is needed. The variables below move only the history database, the model proxy's spool and the logs. They exist mainly so tests and development setups never touch a real home; to run a daemon against a different home, set `HOME`.

| Name | Default | Effect |
| --- | --- | --- |
| `COFFER_DB_URL` | `sqlite+aiosqlite:///~/.coffer/runs.db` | SQLAlchemy URL of the history database. The master key file (`master.key`) stays in `~/.coffer` whatever this says. |
| `COFFER_PROXY_SPOOL_DIR` | `~/.coffer/proxy-usage` | Directory the model proxy writes its usage spool files to and the daemon ingests them from. Both processes must see the same value. |
| `COFFER_LOG_DIR` | `~/.coffer/logs` | Directory for `daemon.log`, `proxy.log`, upstream server logs, MCP shim logs and the login service's output. |
| `HOME` | the user's home | Every `~/.coffer` path is resolved against `$HOME` at the moment it is needed, so an alternate `HOME` gives a fully separate vault. |

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

| Name | Default | Effect |
| --- | --- | --- |
| `COFFER_PORT_RANGE_START`, `COFFER_PORT_RANGE_END` | unset | Bind the first free port in this range instead of the single configured port. Outranks `daemon-config.json`. If only one end is set, the other falls back to `38470` or `8009`. |
| `COFFER_EVAL_CAPTURE` | unset | Records each `coffer__search_tools` query and its results as JSON lines for the eval harness. `1`, `true` or `yes` writes to `~/.coffer/eval-capture.jsonl`; any other non-falsy value is taken as the output path. |
| `COFFER_RUN_BENCHMARKS` | unset | `1` runs the perf-budget tests too slow for `make verify`, such as the reconcile pass cost (`make verify-benchmark`). |

### Variables Coffer sets for processes it starts

Coffer never reads these from its own environment; it sets them for child processes. You see them in an agent's config or in a process listing.

| Name | Set for | Purpose |
| --- | --- | --- |
| `CLAUDE_CONFIG_DIR` | Claude Code turns | Points Claude Code at a registered agent's config directory when it is not `~/.claude`. |
| `CODEX_HOME` | Codex turns | Points Codex at a registered agent's config directory when it is not `~/.codex`. |
| `COFFER_GIT_TOKEN`, `COFFER_GIT_USERNAME` | `git` during vault sync | The sync remote's token and the username derived from the remote's host, read by a credential helper at run time so the token never appears in `argv` or on disk. |
| `PATH`, `HOME` | the login service | Captured from your login shell when you install the service, so the daemon can find `npx`, `uvx` and other upstream launchers. |

The desktop app reads `HOME` (or `USERPROFILE`), `SHELL` and `PATH` to locate `~/.coffer` and to probe your login shell's `PATH`; it defines no variables of its own.

## daemon-config.json

`~/.coffer/daemon-config.json` holds the settings the daemon needs before it opens the database, plus the settings that must stay on one machine. It is written with mode `0600`. The daemon merges into it and preserves keys it does not recognise, so a file written by a newer Coffer survives an older one. A file that cannot be parsed is ignored with a warning in `daemon.log`, and the defaults apply.

```json
{
  "port": 8123,
  "proxy_port": 38471,
  "machine_name": "studio",
  "machine_id": "3f0c9a…",
  "features": {},
  "price_refresh": true
}
```

| Key | Type | Default | Effect | Changed with |
| --- | --- | --- | --- | --- |
| `port` | integer 1024–65535, or `null` | `38470` | The one port the daemon binds. The daemon refuses to start rather than move to another port. Takes effect at the next start. | **Settings › Daemon → Port**, or `coffer config set daemon.port <port>` and `coffer config unset daemon.port` when the daemon cannot start |
| `proxy_port` | integer 1024–65535, or `null` | `38471` | The port the [local model proxy](/architecture/model-proxy) binds on `127.0.0.1`, and the one projected into agents' configs. An invalid value is ignored with a warning and the default applies. Takes effect when the proxy next starts. | edit the file |
| `machine_name` | string | host name without `.local` | This machine's display label in vault sync. Free to change; nothing references it. | **Sync** page |
| `machine_id` | string | derived from the host | Cache of the host-derived machine id that names this machine in a synced vault. Deleting it recomputes the same value. | written by the daemon |
| `features` | object of booleans | `{}` | This machine's experimental-feature switches. Takes effect at once. A key the registry does not declare is ignored. | **Settings → Features** |
| `price_refresh` | boolean | `true` | Whether the daemon refreshes the model price list from genai-prices once a day. Off, it prices from the list shipped in the build. Read at each refresh. | **Settings › General → Refresh model prices** |

The daemon's runtime state — its pid, port and API token — lives in a different file, `~/.coffer/daemon.json`, which is created on start and removed on exit. See [Files and directories](/reference/filesystem#daemon-files).

## Experimental features

An experimental feature is a capability that is off until you switch it on, per machine; while it is off it looks absent — its pages, commands and routes are closed — and nothing it holds is deleted. Each registry entry names its key, the routes it owns and the resource kinds it owns.

The registry holds four features, in this order:

| Key | Closes | REST prefixes |
| --- | --- | --- |
| `knowledge` | Knowledge | `/api/v1/knowledge` |
| `memory` | Memory | `/api/v1/memory` |
| `sync` | Vault sync | `/api/v1/sync` |
| `models` | Model providers (with its Usage tab) and the local model proxy | `/api/v1/providers`, `/api/v1/models`, `/api/v1/proxy`, `/api/v1/usage` |

Everything else is always on, including conversations and channels. Any other key is not a feature: `PUT /api/v1/daemon/features/<key>` answers `FEATURE_UNKNOWN`. A stored setting for a key the registry does not name is ignored.

While a feature is off, its routes answer `404` with code `FEATURE_DISABLED`; switch it on in **Settings → Features**. The registry lives in [`domain/features.py`](https://github.com/wyx-sg/Coffer/blob/main/backend/coffer/domain/features.py).

### How a feature's state is decided

Highest precedence first:

1. **Pin** — an entry in `COFFER_FEATURES` for the daemon process. A pinned feature cannot be changed from the UI (`409 FEATURE_PINNED`).
2. **Setting** — this machine's value in `daemon-config.json` under `features`.
3. **Default** — off, for every feature in every build.

**Settings → Features** lists the four features in every build and the source of each state is reported as `pin`, `setting` or `default`. A pinned feature's switch is disabled.

### COFFER_FEATURES syntax

A comma-separated list of `key=value` entries. `on`, `true` and `1` switch a feature on; `off`, `false` and `0` switch it off. Whitespace around entries is ignored and values are case-insensitive. An unknown key or a malformed entry is logged and skipped; it never stops the daemon.

```sh
COFFER_FEATURES="knowledge=on,models=off" coffer daemon restart
```

See [Experimental features](/guides/experimental-features) for the task-oriented guide.

## Runtime settings

These live in the vault or in `~/.coffer/local/` (or, where noted, elsewhere) and are changed from **Settings** in the web UI or desktop app. Settings marked *synced* travel to other machines through [vault sync](/guides/vault-sync).

### Settings → General

| Setting | Default | Effect | Stored in |
| --- | --- | --- | --- |
| **Rows per page** | `20` (choices 10, 20, 50, 100) | The initial page size of every table. | browser `localStorage` (`coffer.pageSize`) |
| **Open files with** | System default | The app or command Coffer opens managed files with. | browser `localStorage` (`coffer.preferredEditor`) |
| **Experimental features** (Settings → Features) | off | See [Experimental features](#experimental-features). | `daemon-config.json` |

**Start at login** is under **Settings → Daemon**, not General. It is off by default and, when on, installs a launchd agent (`~/Library/LaunchAgents/dev.coffer.daemon.plist`) that starts the daemon at login and restarts it after a crash. macOS only. It is stored in the plist file.

### Settings › General → Speech to text

The settings for Coffer's own work are one vault document, `state/settings/internal-engine.json`, and all of them are *synced*. You can also edit the file by hand; an absent file means every default. Speech to text is the one place Coffer itself calls a model; it never runs a model over your knowledge or memory.

| Setting | Default | Effect |
| --- | --- | --- |
| **Transcription provider** / **Transcription model** | off | The connection and model voice messages are transcribed with before an agent sees them. While either is unset, Coffer transcribes nothing. |
| **Check skills for updates** (Settings → General) | every 6 hours | How often this machine checks Git-imported skills for newer commits in the background: every 6 hours, every day, every week or only when you ask. **Machine-local** (kept in `daemon-config.json`), not synced, and takes effect at once; a skill's own **Check for updates** works in every setting. |
| **Refresh model prices** | on | Once a day, fetch the latest model price list from genai-prices; off, price from the list shipped in the build. This one is **machine-local** (`price_refresh` in `daemon-config.json`), not synced. |

The two memory passes are not in Settings. Each is switched and retimed in the **Automatic** popover on the **Memory** page; the popover's interval list (**Every**) runs from 15 minutes to 1 day, and a shorter interval can be set through the settings API down to a floor of 60 seconds. `coffer daemon status` shows the passes in flight.

| Pass | Where | Default | Effect |
| --- | --- | --- | --- |
| aggregate | **Memory** header → **Automatic**, switched with distil as **Read memory automatically** | on, every 1 h | Reads the agents' own memory files into the derived memory tree. |
| distil | the same switch; its interval has no control in the popover | on, every 6 h | On its own interval, not after each aggregation: turns each partition's new raw entries into notes as they stand, renders its `MEMORY.md`, and removes notes an agent has marked `retired:`. It calls no model. |

The knowledge sweep has no setting. While the **Knowledge** [experimental feature](#experimental-features) is on, it runs every minute: it re-renders the `coffer-guide` skill, promotes files dropped in a collection's `.inbox/`, and commits edits made on disk.

### Sync remote

The sync remote is one machine-local file, `~/.coffer/local/sync/remote.json`, set on the **Sync** page (the **Remote** tab, and the set-up form before the first join). See [Vault sync](/guides/vault-sync).

| Setting | Default | Effect |
| --- | --- | --- |
| **Run a round** | every hour | How often a round runs automatically (a list from every minute to every few days). Stored as seconds; at least `60`: a smaller value is refused over the API. |
| **Secret** | none | The secret holding the push token. |
| **Include encrypted secrets** | off | Commit and push `vault/secret/` (ciphertext only, never the key). |
| **Only when I press Sync now** (a choice under **Run a round**) | off | Pauses the timer; the remote and its history are kept, and **Sync now** still runs a round. |

### Settings → Data

Retention policies decide how long rows are kept. The retention worker prunes once at start-up and then every 6 hours. Policies are local to this machine, kept in `~/.coffer/local/retention.json`.

The window is set in **Settings → Data → History**, which shows four policies, and **Attachments** under **Local content**. The other one, `sync_runs`, keeps its default and is reachable only over REST (`/api/v1/retention/policies`).

| Policy | Key | Default | Effect |
| --- | --- | --- | --- |
| **Changes** | `audit_log` | 365 days | Deletes audit entries older than the window. |
| **MCP calls** | `mcp_invocations` | 30 days | Deletes gateway invocation log rows. |
| **Skill working files** | `skill_data` | 30 days | Deletes files anywhere under `~/.coffer/skill-data` whose last-modified time is older than the window, then the folders left empty (never `skill-data` itself). |
| **Config backups** | `config_backups` | 30 days | Deletes files under `~/.coffer/config-backups` whose last-modified time is older than the window, except the newest backup of each config file, which is always kept so the last write can be undone; folders left empty are removed. |
| **Attachments** | `attachments` | 30 days | Deletes files in `~/.coffer/content/channel-media` whose last-modified time is older than the window. Shown under **Local content**. |
| REST only | `sync_runs` | 90 days | Deletes the history of sync rounds. |

Conversations have no retention policy: Coffer keeps no conversation text, and the agent's own sessions follow the agent's own clean-up (see [Conversations](/guides/chat#chat-and-the-agent-s-own-sessions)). A `conversations` or `conversations_archive` entry left in `retention.json` by an older version is dropped when the daemon starts. A policy can be set to **Keep forever** (the value `forever`). The same run also deletes aged shim and upstream logs older than 7 days.

### Settings → Security

| Setting | Default | Effect |
| --- | --- | --- |
| **Store master key in OS keychain** | off (file) | Moves the secret master key between `~/.coffer/master.key` and the OS keychain (service `coffer`, entry `master-key`). The key itself never changes, so stored secrets stay readable. The move is audited. Development builds only: a signed release keeps the key in its Keychain access group and refuses to move it. |
| Approval for new secret destinations (`secrets.require_approval`) | on in a signed release, off in a development build | When on, a secret waits for approval in the desktop app before it goes to a new destination or target. When off, a new destination is approved without asking. Switching it on applies at once; switching it off waits for an approval in the desktop app. See [Secrets](/guides/secrets#switching-the-protection-off). |

## Related

- [Files and directories](/reference/filesystem)
- [Running the daemon](/guides/daemon)
- [Experimental features](/guides/experimental-features)
- [Secret store](/guides/secret-store)
- [CLI reference](/reference/cli)
- [Distribution and releases](/architecture/distribution)
