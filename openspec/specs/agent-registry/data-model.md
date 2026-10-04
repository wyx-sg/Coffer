# Data Model — Agent Registry

Entities, fields, relationships, and storage notes for the agent registry.
Builds on the kind-agnostic Resource framework from spec resource-framework — an agent is a
resource file, so spec agent-registry adds no table of its own. The `agent`
kind's storage class is `local` (`Kind.storage`): an agent names a config
directory on this disk, so its file is `~/.coffer/local/resources/agent/<name>.json`,
never committed and never synced.

## Domain entities (`backend/coffer/domain/agent/`)

### `AgentType` + the capability manifest (`domain/agent/types.py`, `domain/agent/descriptor.py`)

`AgentType` is a string-valued enum (`StrEnum`) — the stable identity (persisted
value + API contract + registration whitelist). Each value covers both the CLI
and the app/IDE form of that product, which share one config directory.

All _per-type behaviour_ lives in the **capability manifest**
(`domain/agent/descriptor.py`): `AGENT_DESCRIPTORS: dict[AgentType,
AgentDescriptor]`, one record per agent. `types.py` methods, `config_files_for`,
the MCP services, and auto-detect read this table (the enum's methods delegate
via a lazy import to keep the graph acyclic). **Adding an agent = adding one
enum value + one descriptor record** (plus a novel MCP entry renderer or memory
adapter only when the agent introduces a genuinely new shape).

| Value         | Display name | Default `config_dir` | MCP file / container / shape               |
| ------------- | ------------ | -------------------- | ------------------------------------------ |
| `claude_code` | Claude Code  | `~/.claude`          | `.claude.json` · `mcpServers` · map        |
| `codex`       | OpenAI Codex | `~/.codex`           | `config.toml` · `mcp_servers` · map        |

Skills are delivered to `<config_dir>/skills`. `claude_desktop` (the separate Claude chat app) remains out
of scope.

`AgentDescriptor` carries the per-type values: `type`, `display_name`,
`config_subpath`, `config_files` (allowlist builder), `mcp`
(`McpInjectionSpec | None`), `mcp_source_keys`, `skill_subpath`, `home_env_var`,
`plugins` (`PluginCapability | None`), `hook_source_keys` (the allowlist keys of
the files that carry hooks: `settings` and `settings_local` for Claude Code,
`hooks` for Codex) and `program` (the executable detection looks for: `claude`,
`codex`), plus `default_config_dir()`. It also names four optional mechanism
facets — `projection`, `driver`, `memory_reader`, `dependency_probe` — which are
`None` in the pure table and bound to their implementations at the composition
root into an `AgentCatalog` (`domain/agent/facets.py`; ADR
agent-mechanisms-are-optional-facets-on-the-descriptor). The projection facet
is a registry of `ProjectionEntry(asset, landing, config_key | subpath)` rows —
assets `mcp_server`, `skill`, `provider`, `delivery_hook`; landings `user`,
`project`, `shared` — and every entry of the two shipped agents lands at `user`.
There is no per-type `enabled` flag: discovery looks at every `AgentType`, and
withdrawing a type means removing it from the enum and the manifest. Each enum
value still exposes:

- `display_name: str`
- `default_name() -> str` (the name of the type's one agent — underscores become hyphens, e.g. `claude_code` → `claude-code`; there is no other name an agent may carry)
- `config_dir() -> Path` (the type's standard config directory, computed per host platform — `~/.claude` / `~/.codex`; used when the user registers without an explicit `config_dir`)
- `default_skill_dir() -> Path` (`<config_dir()>/skills`, the default skills-delivery directory a discovery candidate reports)

### Detection (`domain/agent/detection.py`)

`DetectionState` is `installed_active` | `installed_never_run` | `config_only` |
`missing`, from `classify(ProgramInfo, config_dir_exists)`; `ProgramInfo` is
`{path | None, version | None}`, what the dependency probe found. Neither is
stored: candidates and the agent read model compute them per request.

### Hooks (`domain/agent/hooks.py`)

`HookRow {event, matcher, command, type, timeout, group_index, hook_index}` — the last two are where the hook sits in its file, `hooks.<event>[group_index].hooks[hook_index]` — parsed from the
`{"hooks": {event: [{matcher, hooks: [{type, command, timeout}]}]}}` shape both
agents use; `HookSource` is `user` | `plugin`; `HookHealth` is `current` |
`stale` | `missing`. Read only; nothing stored.

The config-file allowlist and the skills-delivery target (`<config_dir>/skills`) both resolve against the agent's resolved `config_dir`.

### `AgentConfig` (`domain/agent/config.py`)

Pydantic v2 `BaseModel`. The kind-specific config schema registered with `ResourceService`.

| Field               | Type           | Notes                                                                                                                               |
| ------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `type`              | `AgentType`    | required; enum value                                                                                                                |
| `config_dir`        | `str \| None`  | optional absolute-path override, stored as a string (`~` expanded before the absolute-path check); `resolved_config_dir()` returns the `Path`, defaulting to `type.config_dir()` |
| `model`             | `str \| None`  | the model this agent runs on; `None` = the agent's own default (see "Carry the model binding on the agent record")                                                              |
| `tier_models`       | `dict \| None` | Claude Code only: `opus` / `sonnet` / `haiku` / `fable` → model id; an explicit null unbinds it                            |
| `connection_uid`    | `str \| None`  | the uid of the provider connection this agent runs on; `None` = the agent's own built-in login. Machine-local like the record (agents are filed under `local/`), so it never syncs. Written only by the provider switch operations, never by `PATCH /api/v1/agents/{uid}`; `AgentOut` reports it (see "Carry the connection an agent runs on on the agent record") |

Those are the whole schema — the model is `extra="forbid"` and declares nothing
else (no `wire_api`: Codex's `responses` is a fixed value the projection writes). The two model fields are the agent's own binding (see "Carry the model
binding on the agent record"): they live here because the model is chosen at the
point of use. Projecting them into an agent's native config is [spec
provider-switching](../provider-switching/spec.md)'s.

Skills are delivered to `<config_dir>/skills`; the config-file allowlist resolves against `config_dir`. Only one agent may exist per resolved `config_dir`.

The `agent` kind has no on/off switch: it declares `toggleable=False`, so the generic enable/disable routes refuse it (`RESOURCE_NOT_TOGGLEABLE`) and an `enabled: false` left in `local/reach.json` by an earlier build reads as enabled. The agent record carries no skill-delivery policy of its own: which skills reach it is decided entirely by each skill's `enabled` flag and its agent scope (spec skill-manager, [ADR per-agent-resource-scope](../../../docs/decisions/per-agent-resource-scope.md)).

Validators:

- `config_dir` (when set) must be an absolute path; at registration the `<config_dir>/skills` subdirectory is auto-created, then the resolved `config_dir` must be an existing, writable directory.
- `config_dir` must not point inside a privileged location (checked by `assert_skill_dir_usable` in `application/agent/service.py`): `/etc`, `/bin`, `/sbin`, `/usr`, `/var`, `/sys`, `/proc`, `/root`, `/boot`, `/dev`, `/System`, `/Library/Application Support/Apple` (POSIX; matched at a path-component boundary on both the expanded and the resolved path, with macOS's `/private` prefix stripped, and `/var/folders/` carved out as usable) or `C:\Windows`, `C:\Program Files`, `C:\Program Files (x86)` (Windows).
- `model_config = ConfigDict(extra="forbid")` so unknown fields are rejected. The one exception is the retired `effort` key: a `mode="before"` validator drops it, so a vault file written before reasoning effort was removed still loads and loses the key on its next write.

### `ConfigFileFormat` + config-file allowlist (`domain/agent/config_files.py`)

Pure domain module (no I/O beyond `os.environ`-based path construction, same
pattern as `types.py`). Defines the curated set of config files each agent type
exposes. The UI viewer renders a file's content and lets the user **edit it in
place behind an explicit Edit**, with the unsaved draft guarded three ways
(switching file, switching tab, leaving the page); it also offers
open-in-external-editor / reveal for the edits that want a real editor (the HTTP
`ConfigFileInfo` / `ConfigFileContent` views carry both the file `path` and its
containing-folder `folder_path` for those affordances — see "Open config files
in an external editor or reveal them"). The REST API and CLI expose the same
write.

`ConfigFileFormat` — `StrEnum` of `json`, `toml`, `markdown`.
Drives save-time validation: `json` parses with `json.loads`, `toml` with
`tomllib.loads`; `markdown` is always valid.

`ConfigFileKind` — `StrEnum` of `file`, `directory`. A `directory` entry (see
"List directory config entries") resolves to a directory of files rather than a
single file; its `format` describes the CHILD files.

`ConfigFileSpec` — frozen dataclass describing one allowlisted file:

| Field          | Type               | Notes                                                                    |
| -------------- | ------------------ | ------------------------------------------------------------------------ |
| `key`          | `str`              | stable identifier addressed by API/CLI (e.g. `settings`, `instructions`) |
| `display_name` | `str`              | human label (e.g. "User settings")                                       |
| `path`         | `Path`             | resolved absolute path (computed per host)                               |
| `format`       | `ConfigFileFormat` | governs validation (child-file validation for directory entries)         |
| `kind`         | `ConfigFileKind`   | `file` (default) or `directory`                                          |

`config_files_for(agent_type, config_dir=None) -> tuple[ConfigFileSpec, ...]`
returns the curated allowlist, resolved against the agent's effective config
dir. Current set (the former `memory` key is renamed `instructions` — these
files are human-authored instructions, distinct from agent-written memory,
which is spec knowledge's domain):

| Agent         | `key`            | Path                               | Format     | Kind        |
| ------------- | ---------------- | ---------------------------------- | ---------- | ----------- |
| `claude_code` | `settings`       | `~/.claude/settings.json`          | `json`     | `file`      |
| `claude_code` | `settings_local` | `~/.claude/settings.local.json`    | `json`     | `file`      |
| `claude_code` | `global`         | `~/.claude.json`                   | `json`     | `file`      |
| `claude_code` | `instructions`   | `~/.claude/CLAUDE.md`              | `markdown` | `file`      |
| `claude_code` | `subagents`      | `~/.claude/agents/`                | `markdown` | `directory` |
| `codex`       | `config`         | `~/.codex/config.toml`             | `toml`     | `file`      |
| `codex`       | `instructions`   | `~/.codex/AGENTS.md`               | `markdown` | `file`      |
| `codex`       | `hooks`          | `~/.codex/hooks.json`              | `json`     | `file`      |

(Paths are shown for the default config dir. `global` is `~/.claude.json` for the default `~/.claude` and `<config_dir>/.claude.json` for any other `config_dir` — Claude Code run with `CLAUDE_CONFIG_DIR` keeps the file inside that directory and never reads the home one; spec agent-registry/claude-code "Allowlist exactly the files Claude Code reads".)

`~/.codex/auth.json` is deliberately excluded (secret/state, not a
hand-edited config). `~/.claude.json` is included (per product decision) and
protected by a timestamped backup under `~/.coffer/config-backups/` on every write.

`validate_content(fmt: ConfigFileFormat, text: str) -> None` raises
`ConfigFileFormatInvalid` for malformed structured content.

`spec_for(agent_type, key) -> ConfigFileSpec` raises `ConfigFileNotAllowed`
when `key` is not in the type's allowlist (drives the 404 + no-FS-access rule).

### Directory Config Entry

An allowlisted entry with `kind=directory` lists its child files instead of
carrying content; the directory on disk is the source of truth (derived, never
stored). The directory entry is Claude Code `subagents` (`~/.claude/agents/`, one
Markdown file per personal subagent, nested paths allowed).

`DirEntryInfo` — frozen dataclass for one child file:

| Field         | Type       | Notes                                        |
| ------------- | ---------- | -------------------------------------------- |
| `relpath`     | `str`      | POSIX path relative to the entry's directory |
| `size`        | `int`      | byte size                                    |
| `modified_at` | `datetime` | last-modified time                           |

`validate_child_relpath(root, relpath) -> Path` is the child-path security
boundary (pure path math; symlink escape is re-checked at I/O time by the
store): it rejects traversal (`..`), absolute paths, backslashes, hidden
segments, and any extension other than lowercase `.md` — before any
filesystem access.

### MCP injection — orthogonal axes (`domain/agent/mcp_injection.py`, `mcp_install.py`)

MCP configuration varies across agents along **two independent axes**, captured
by `McpInjectionSpec` (held per agent in the manifest):

- **format** — `json` / `toml` — selects the parser/serializer (`json` stdlib, `toml` `tomlkit`).
- **shape** — `container_key` (the top-level table: `mcpServers` / `mcp_servers`) + `entry_style` (`McpEntryStyle`): `COMMAND_MAP` (`{"command": shim, "args": ["--agent-uid", uid]}` — Claude Code/Codex; `args` is omitted when no agent uid is given).

`mcp_install.py` builds / detects / removes the `coffer` entry as pure text
transforms (no filesystem):

- `COFFER_SERVER_KEY = "coffer"`.
- `apply_install(fmt, text, shim_path, *, container_key=None, entry_style=COMMAND_MAP, agent_uid=None) -> str`
  — inserts/updates the `coffer` entry. `container_key` defaults per format
  (`default_container_key`); `agent_uid` is written as `--agent-uid <uid>` in the
  entry's `args` so the gateway can attribute the session. Idempotent.
- `apply_uninstall(fmt, text, *, container_key=None) -> str` — removes the
  `coffer` entry (no-op if absent).
- `is_installed` / `installed_command` (`*, container_key=None`) — presence /
  shim path (the latter handles both command-map and command-array shapes).

The MCP config file for each type is itself an allowlisted config file
(`global` for Claude Code, `config` for Codex). The Coffer
connection's `mcp` part writes to it via the atomic-write/backup path
described under `AgentMcpService`; it can also be edited like any other
allowlisted config file through `AgentConfigFileService.write_file`. Both paths
share the same atomic-write + backup machinery.

## Storage

**No table of its own.** An agent is one resource file,
`~/.coffer/local/resources/agent/<name>.json` (spec resource-framework), with
its reach in `local/reach.json`. Both are machine-local: another machine's
agents are its own, discovered there. Discovery is read-only, with no
suppression list to persist.

**Config files and Coffer connection state are NOT persisted by Coffer** — the
agent's on-disk config files are the source of truth. Connection status is
derived by reading the relevant config files on demand.

**The plugin inventory travels in the machine descriptor.** This machine's
descriptor (`vault/machines/<machine id>.json`, spec vault-sync)
lists every agent with the plugins `AgentPluginService.list_plugins` reported
before the last round that moved anything
(`{type, name, plugins: [{id, name, marketplace, enabled, version}]}`,
`application/sync/inventory.py`). An inventory, not a replicator: nothing on
any machine writes an agent's plugin configuration from it.

### Also written

- resource files with `kind: agent`, under `local/`.
- `audit_log` in `runs.db`: new event types (see below). No schema change.

## Audit event types added

Add to `AuditEventType` (`domain/audit.py`):

| Value                       | When emitted                                                                                        |
| --------------------------- | --------------------------------------------------------------------------------------------------- |
| `agent_config_file_written` | A config file was saved through Coffer (atomic write + backup); details carry the config-file `key` |
| `agent_mcp_installed`       | Coffer's MCP server entry was written into an agent's MCP config                                    |
| `agent_mcp_uninstalled`     | Coffer's MCP server entry was removed from an agent's MCP config                                    |

The workspace amendment adds:

| Value                       | When emitted                                                                    |
| --------------------------- | ------------------------------------------------------------------------------- |
| `agent_config_file_deleted`  | A directory-entry child file was deleted (prior content preserved as a backup under `~/.coffer/config-backups/`) |
| `agent_mcp_entry_removed`    | A direct MCP entry was removed from the agent's own config                      |
| `agent_mcp_entry_adopted`    | A direct MCP entry was adopted into a registered `mcp_server` resource          |
| `agent_plugin_toggled`       | A plugin was enabled or disabled on its documented surface                      |
| `agent_plugin_uninstalled`   | A plugin was uninstalled, by config edit or by the agent's own CLI               |

The lifecycle steps required by "Audit every agent lifecycle event" — registration, update, and removal — are emitted as the existing kind-agnostic `resource_created`, `resource_updated`, and `resource_deleted` events (each carrying the affected agent's `uid`). No `agent_*` duplicates are added for these; surfaces filter by `kind='agent'` plus the kind-agnostic event type. A successful config-file save emits `agent_config_file_written` (the agent's `uid`, details `{key}`). Disabling or re-enabling an agent through the kind-agnostic `POST /api/v1/resources/{uid}/disable|enable` is recorded as the kind-agnostic `resource_disabled` / `resource_enabled`; discovery is read-only and registers nothing, so it emits no audit event.

## Application service contracts (`backend/coffer/application/agent/`)

### `AgentService`

Every method is keyword-only and addresses an agent by its immutable `uid`
([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)).

| Method | Purpose |
| ------ | ------- |
| `register(*, agent_type, config_dir=None, create_config_dir=False, actor) -> Resource` | Build and validate `AgentConfig`; reject a second agent of the type with `AgentTypeRegistered` (→ 409 `AGENT_TYPE_REGISTERED`) and a second agent on the same resolved config dir with `AgentConfigDirRegistered` (→ 409 `AGENT_CONFIG_DIR_REGISTERED`); when `create_config_dir` (the route's finding that the type is `installed_never_run` and the directory is its standard one) create the missing directory after the privileged-path check; auto-create `<config_dir>/skills` and validate it (`assert_skill_dir_usable`); then delegate to `ResourceService.register(kind='agent', name=agent_type.default_name(), ...)`. |
| `find_by_type(agent_type) -> Resource \| None` | The type's one agent, found by its name. |
| `resolve(ref) -> Resource` | The agent `ref` names: its type (`claude-code` or `claude_code`) or its uid; `ResourceNotFound` otherwise. The routers' `resolve_agent_path` dependency does the same for the `{uid}` path segment. |
| `list() -> list[Resource]` | Delegate to `ResourceService.list(kind='agent')`. |
| `get(uid) -> Resource` | Delegate to `ResourceService.get`. |
| `update_config_dir(*, uid, new_config_dir, actor) -> Resource` | Re-validate the merged config; only when the effective dir changes, check it is free, auto-create and check its `skills/`. Then `ResourceService.update_config` and, on a dir change, the config-dir-changed hook that re-delivers skills to the new location. |
| `set_model_binding(*, uid, model=None, tier_models=None, clear_tiers=False, actor) -> Resource` | The sole writer of the model binding ("Carry the model binding on the agent record"): `None` leaves a field unchanged, `clear_tiers` unbinds; the merged config is re-validated. |
| `remove(*, uid, actor) -> None` | Delete via `ResourceService.delete`. Removal is not permanent — there is no suppression list, so the agent re-appears as a discovery candidate on the next scan. |

### `AutoDetectService`

| Method | Purpose |
| --- | --- |
| `types() -> list[AgentTypeDetection]` | Read-only, one row per type in the bound catalogue: ask its dependency probe for the program and version, and look at its standard config directory plus the directory its environment variable (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`) names in the daemon's environment. A registered type reports its agent's directory; any other reports the standard one unless only the environment's exists, with the other existing directory as `other_config_dir`. Registers nothing and writes nothing. Served by `GET /api/v1/agents/types`. |
| `discover() -> list[AgentTypeDetection]` | The rows of `types()` with no agent registered and either signal present — at most one candidate per type. NOT called on daemon startup; invoked on demand by `GET /api/v1/agents/candidates`. |
| `detect(agent_type, config_dir) -> AgentDetection` | The detection state and version of one agent at one directory — what the agent read model carries. |

`AgentTypeDetection` is a derived value object (not a stored entity, never
stored): what this machine holds of one supported type. Fields: `type`
(`AgentType`), `display_name`, `config_dir` (as a string), `standard_config_dir`,
`default_skill_dir` (`<config_dir>/skills`), `state` (`DetectionState`),
`version`, `uid` (the registered agent's, or `None`) and `other_config_dir`;
properties `name` (the type's `default_name()`), `addable` (not registered and
the program installed — `installed_never_run` included, `config_only` not) and
`is_candidate` (not registered and not `missing`).

### `AgentHooksService`

| Method | Purpose |
| --- | --- |
| `list_hooks(uid) -> AgentHooks` | Every hook in the agent's hook-carrying files and its enabled plugins' `hooks/hooks.json`, Coffer's own marked, plus Coffer's hook health (`current` / `stale` / `missing`, by the delivery hook's marker-and-command comparison) and its last `memory_delivery_fired`. Writes nothing. |
A removed agent re-appears as a candidate on the next scan — there is no
suppression list.

### The folder picker's backend (spec daemon)

The picker of "Offer a folder picker for a custom config directory" is a
CONSUMER of the daemon's filesystem routes, not an owner of them. `POST
/api/v1/fs/pick-folder` opens the host's native directory dialog and `GET
/api/v1/fs/browse` is the in-app fallback when the host has no such tool; both,
with `POST /api/v1/fs/open`, `POST /api/v1/fs/reveal` and the installed-editor
enumeration behind the open-in-editor preference, are specified and implemented
by spec daemon. This spec models only what it does with the absolute path they
return: validate it per "Validate the config directory at registration" and
store it as `config_dir`. The `FolderPicker.tsx` frontend component is the
surface that calls them.

### `AgentConfigFileService` (`application/agent/config_file_service.py`)

Resolves an agent → its `AgentType`, then operates on that type's config-file
allowlist via a `ConfigFileStorePort`.

| Method                                                                                            | Purpose                                                                                                                                                                                                                                                                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_files(uid) -> list[ConfigFileInfo]`                                                        | For each `ConfigFileSpec` of the agent's type, return key, display name, path, containing-folder `folder_path` (backs the read-only UI's open/reveal), format, `kind`, `exists`, and (when present) size + mtime. Directory entries additionally carry `files` (recursive `.md` listing as `DirEntryInfo` rows).                                                                         |
| `read_file(uid, key) -> ConfigFileContent`                                                       | Resolve `spec_for(type, key)`; return content + `path` + `folder_path` + format + `exists` + `fingerprint` (the `path`/`folder_path` pair backs open-in-external-editor / reveal). Missing file → empty content, `exists=False`, `fingerprint=""`, no file created.                                                                                                   |
| `write_file(uid, key, content, *, expected_fingerprint=None, actor) -> ConfigFileInfo`           | Resolve `spec_for(type, key)`; `validate_content(format, content)` (malformed json/toml → `ConfigFileFormatInvalid` → 422, file unchanged); when `expected_fingerprint` is supplied, reject with `ConfigFileStale` (→ 409) if the on-disk content changed since the read ("Reject stale config-file writes by fingerprint"); `store.write_text_atomic` (atomic + backup); record `agent_config_file_written`; return the refreshed `ConfigFileInfo`. |
| `read_child(uid, key, relpath) -> ConfigFileContent`                                             | `validate_child_relpath`, then read one child of a directory entry; same shape as `read_file`.                                                                                                                                                                                                                                                                                                             |
| `write_child(uid, key, relpath, content, *, expected_fingerprint=None, actor) -> ConfigFileInfo` | Create-on-write save of one child file; same validation / staleness / atomic-write / audit machinery as `write_file`.                                                                                                                                                                                                                                                                             |
| `delete_child(uid, key, relpath, *, actor) -> None`                                              | Delete one child file, preserving the prior content as a backup under `~/.coffer/config-backups/`; records `agent_config_file_deleted`.                                                                                                                                                                                                                                                                                                        |

`ConfigFileContent.fingerprint` is a content fingerprint used for
optimistic-concurrency writes (see "Reject stale config-file writes by
fingerprint") — reads return it, writes carry it back.

### `AgentMcpService` (`application/agent/mcp_service.py`)

Installs/uninstalls Coffer's MCP entry by editing the agent's MCP config file
through the same store. Reuses `domain/agent/mcp_install.py`.

| Method                   | Purpose                                                                                                                                                                                                                                         |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `status(uid) -> McpInstallStatus`   | Read the agent's MCP config file; return `McpInstallStatus(installed, command)` from `is_installed` / `installed_command`.                                                                                                                       |
| `install(uid, *, actor) -> McpInstallStatus`   | Resolve the shim path (`COFFER_MCP_SHIM_PATH` → `shutil.which("coffer-mcp-shim")` → interpreter scripts dir → bundled fallback; raise `ShimNotFound` if none). `apply_install` with the agent's uid; atomic write + backup; audit `agent_mcp_installed`. Idempotent. |
| `uninstall(uid, *, actor) -> McpInstallStatus` | `apply_uninstall`; atomic write + backup; audit `agent_mcp_uninstalled`. No-op when absent (no write, no audit).                                                                                                                    |

`McpInstallStatus` is `(installed: bool, command: str | None)`. A type whose
descriptor declares no `McpInjectionSpec` raises `McpInstallUnsupported`
(→ 422). The service is not exposed on its own route: it is the `mcp` part of
the agent's Coffer connection, below.

### `AgentConnectionService` (`application/agent/connection_service.py`)

Connects an agent to Coffer, or disconnects it, by installing or removing each
**part** Coffer writes into the agent's own configuration ("Connect an agent to
Coffer in one action", "Report an agent's Coffer connection part by part",
"Disconnect an agent from Coffer"). A part is a `ConnectionPart` — a key,
`supports(agent_type)`, and `status` / `install` / `remove` by
agent uid — and owns its own atomic write, backup and audit event; the service
writes nothing itself and records no audit event of its own.

| Part          | Owner                                         | Applies when                          | Audit events                                            |
| ------------- | --------------------------------------------- | ------------------------------------- | ------------------------------------------------------- |
| `mcp`         | `AgentMcpService` (via `McpConnectionPart`)   | always (every type declares one)      | `agent_mcp_installed` / `agent_mcp_uninstalled`         |
| `memory_hook` | memory's `DeliveryService`, adapted in `surfaces/http/agent_connection_wiring.py` | the type has a hook adapter | `memory_delivery_installed` / `memory_delivery_removed` |

| Method                                   | Purpose |
| ---------------------------------------- | ------- |
| `status(uid) -> ConnectionStatus`        | Each applicable part's `PartStatus(key, installed, detail)`, and a `state`: `connected` (all installed), `partial`, or `disconnected` (none). Read on demand, never stored. |
| `connect(uid, *, actor)`                 | (Re)install every applicable part, the `mcp` part first so a missing shim refuses before anything is written. |
| `disconnect(uid, *, actor)`              | Remove every part the type supports. |
| `connected_agents() -> list[str]`        | The uids of agents carrying the `mcp` entry — the ones the hook's reconcile pass treats as connected. |

The memory kind's part is adapted at the composition root because the agent
kind may not import the memory kind; the HTTP shape is `CofferConnectionOut`
(`state`, `parts[]` of `CofferConnectionPartOut(key, installed, detail)`).

## Workspace amendment — derived entities (never stored)

The workspace facets (MCP entries and plugins) operate on the agent's own config
files; the files on disk stay the source of truth and Coffer keeps no copy. Both
entities below are read-time projections, and the only write any of them
performs is the source-entry removal that adoption ("Adopt a direct MCP entry
into Coffer") owns.

### Agent MCP Entry (`domain/agent/mcp_entries.py` — `McpEntry`)

One MCP server entry as configured in the agent's own file. Parsed from
claude_code's `~/.claude.json` + `settings.json` `mcpServers` maps and codex's
`config.toml` `[mcp_servers.*]` tables (pure text transforms; `tomlkit`
preserves the user's TOML layout).

| Field              | Type             | Notes                                                                                                                                                            |
| ------------------ | ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `name`             | `str`            | entry key in the config file                                                                                                                                     |
| `source`           | `str`            | allowlist key of the file it came from (`global`/`settings`/`config`)                                                                                            |
| `transport`        | `str`            | `stdio` or `http` (derived: `url` present → `http`)                                                                                                              |
| `command` / `args` | `str?` / `tuple` | stdio launch spec                                                                                                                                                |
| `env` / `headers`  | `dict[str,str]`  | `repr=False` — values may carry secrets; over HTTP only KEY NAMES leave the daemon (`env_keys`, `header_keys`, plus `secret_keys` flagging secret-looking names) |
| `url`              | `str \| None`    | http transport target                                                                                                                                            |
| `enabled`          | `bool \| None`   | per-entry flag where the format defines one (codex); `None` for claude_code                                                                                      |
| `is_coffer`        | `bool`           | Coffer's own gateway entry — never adoptable                                                                                                                     |
| `matches_resource` | `str \| None`    | equivalent registered `mcp_server` resource, filled by the application layer                                                                                     |

Companion helpers: `parse_entries`, `remove_entry` (retained solely for the
removal step of an adoption), `secret_env_keys`
(TOKEN/SECRET/PASSWORD/PASSWD/API_KEY/APIKEY/CREDENTIAL/AUTHORIZATION patterns,
applied to the entry's env and HTTP headers alike on adoption), and
`to_transport_config` (entry → `mcp_server` transport config with secret keys
moved to `secret_refs` for adoption). Malformed files raise
`AgentConfigParseError`, which the listing degrades to a `parse_errors` item
instead of failing the view (see "Degrade a facet to a parse-error state when
its config file is unparseable").

### `PluginCapability` / `PluginModel` (`domain/agent/plugin_capability.py`)

The plugin facet of the capability manifest. `PluginModel` is the strategy
discriminator — `CLAUDE`, `CODEX` — each mapping to a parse strategy in
`plugin_state.py`. `PluginCapability` (frozen) carries enough for the
service to dispatch without an `AgentType` switch:

| Field                | Type                | Notes                                                                                          |
| -------------------- | ------------------- | ---------------------------------------------------------------------------------------------- |
| `model`              | `PluginModel`       | parse strategy                                                                                 |
| `config_key`         | `str \| None`       | allowlist key of the file the enabled state is read from and the writes go to (`None` = list-only) |
| `can_toggle`         | `bool`              | whether the plugin enable/disable toggle is offered (default `True`)                           |
| `can_uninstall`      | `bool`              | whether in-app plugin uninstall is offered (default `False`)                                   |
| `uninstall_strategy` | `UninstallStrategy` | `CONFIG_EDIT` (edit the documented surface) or `CLI` (delegate to the agent's own command)      |

`AgentDescriptor.plugins` is `PluginCapability | None`. The per-agent mapping:
Claude Code `CLAUDE`/`settings`, toggle + uninstall via `CLI` (`claude plugin
uninstall`, gated at runtime on `claude` being on `PATH`, so the listing can
report `can_uninstall=false`); Codex `CODEX`/`config`, toggle + uninstall by
`CONFIG_EDIT`.

### Agent Plugin (`domain/agent/plugin_state.py` — `PluginInfo` / `MarketplaceInfo`)

One installed plugin, id `<name>@<marketplace>`. The *internal inventory* files
are read-only — Coffer parses them and never writes them; the toggle and
uninstall writes touch only the documented surfaces (`settings.json`
`enabledPlugins`, `config.toml` `[plugins."…"]`) or delegate to the agent's own
CLI. Codex state lives in `config.toml` (`[plugins."…"]` + `[marketplaces.*]`).
Claude Code splits state across the internal inventory files
`installed_plugins.json` / `known_marketplaces.json` and the documented surface
`settings.json` `enabledPlugins`.

| Field         | Type   | Notes                                                               |
| ------------- | ------ | ------------------------------------------------------------------- |
| `id`          | `str`  | `<name>@<marketplace>` (split on the last `@`)                      |
| `name`        | `str`  |                                                                     |
| `marketplace` | `str`  |                                                                     |
| `enabled`     | `bool` | defaults to `True` when the config carries no explicit flag         |
| `installed`   | `bool` | present in the install inventory; settings-only orphans get `False` |
| `version`     | `str \| None` | resolved install version, when the inventory records one (Claude Code) |
| `install_path` | `str \| None` | install directory, when the inventory records one; the detail reader enumerates bundled skills/commands/MCP servers from it |

`MarketplaceInfo` carries `name`, `source_type`, `source` (read-only). The HTTP
view (`PluginView`) replaces `installed` with `cache_present` — whether the
plugin's cache directory exists on disk (no repair is attempted, per "List an
agent's installed plugins without writing anything").

### `AgentMcpEntryService` (`application/agent/mcp_entry_service.py`)

| Method                                                                | Purpose                                                                                                                                                                                                                                                                     |
| --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_entries(uid)`                                                  | Parse all MCP-bearing files of the agent's type; mark `is_coffer` and `matches_resource`; collect per-file `parse_errors`.                                                                                                                                                  |
| `remove_entry(uid, entry, source=None, actor)`                       | Removal: edit only the entry's source file (`source` disambiguates when claude_code carries the name in both, else `McpEntrySourceAmbiguous`), atomic write + backup, drop any secret refs it owned, audit `agent_mcp_entry_removed`. Coffer's own entry is refused. |
| `adopt(uid, entry, source=None, new_name=None, secrets=None, actor)` | Adoption: secret-looking keys MUST map to secret refs (`AdoptSecretUnresolved` lists unresolved keys); register the `mcp_server` resource → verify it reads back → remove the source entry (atomic + backup; `source` disambiguates when claude_code carries the name in both files, else `McpEntrySourceAmbiguous`), with rollback on any later failure; audits `agent_mcp_entry_adopted`. |

There is no `set_enabled`: a per-entry enable toggle was removed (see the note
in spec "List the MCP entries in the agent's own config files") because
claude_code's format has no such flag and codex's duplicates a switch its own UI
owns. Removal and adoption stay, because each is a write Coffer alone has a
reason to make. Both are exposed as `DELETE
/api/v1/agents/{uid}/mcp-entries/{entry}` and (adoption) `POST
/api/v1/agents/{uid}/mcp-entries/{entry}/adopt`, and from the agent's page.

### `AgentPluginService` (`application/agent/plugin_service.py`)

| Method                                         | Purpose                                                                                                                                                                                                                                  |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_plugins(uid)`                            | Dispatch on `descriptor.plugins.model`; parse plugin + marketplace state from the documented file(s); compute `cache_present`; read best-effort manifest detail from the plugin's install path; collect `parse_errors`. No capability → empty listing. |
| `set_enabled(uid, plugin_id, enabled, actor)`   | Toggle: write the enabled flag to the capability's `config_key` file (atomic + backup); `PluginToggleUnsupported` (422) when the capability declares `can_toggle=False`; audit `agent_plugin_toggled`. |
| `uninstall(uid, plugin_id, actor)`              | Uninstall: by `uninstall_strategy` — `CONFIG_EDIT` removes the `config.toml` entry and its cache dir; `CLI` runs the agent's own uninstall command through a `PluginCliRunner` and never hand-writes the internal inventory. `PluginUninstallUnsupported` (422) when unavailable; audit `agent_plugin_uninstalled`. |

The listing writes nothing; the two writes above are the whole of what this
service changes, and each goes through a documented surface. `PluginCliRunner`
and `PluginDetailReader` are application-layer ports (`plugin_views.py`)
satisfied at the composition root. The surfaces are
`PATCH`/`DELETE /api/v1/agents/{uid}/plugins/{plugin_id}` and the
agent's Plugins tab.

### `AgentModel` + `AgentModelCatalogueService` (`domain/agent/model_catalogue.py`, `application/agent/model_catalogue.py`)

Derived, never stored. One `AgentModel` is one entry of what an installed agent
can be put on (see "Serve each agent type's model catalogue from its one agent"): `id` (passed to
the agent verbatim), `label` and `description`.

| Method               | Purpose                                                                                                                                                                      |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `catalogue(agent_key)` | Ask each of that type's sources in picker order and concatenate what they answer. A source that raises, finds nothing, or no longer matches its anchor contributes nothing and the others still answer. Never raises. |
| `offered(agent_key)` | What a picker offers: the curated ids of the connection the agent runs on when it curates any, else `catalogue(agent_key)` — spec provider-switching "Serve one model list to every surface". |
| `suggest(agent_key)` | The plain ids of `offered()` — the list a channel's `/model` card presents. |

`GET /api/v1/agent-providers/{agent_key}/models` serves `offered()`; the route,
not the service, answers 404 for an unregistered `agent_key`.

The sources themselves live in `infrastructure/agent/` — one reader per source,
each named by the type's child spec (`claude_binary_models.py`
for agent-registry/claude-code, `codex_rpc_models.py` for
agent-registry/codex), behind `model_discovery.py`. Nothing here is written to
a database, to the vault, or to the agent: the catalogue is re-derived on every
request, which is the whole point of "Keep one source of truth for an agent's
models". What a PICKER is offered — the narrowing the agent's connection applies —
is spec provider-switching's read over this same service, not a second list.

### `ConfigFileStorePort` (Protocol, defined in application)

Application-layer interface; concrete impl lives in
`infrastructure/agent/config_file_store.py` (Contract 4 — application must not
import infrastructure directly).

- `read_text(path) -> str | None` — `None` when the file does not exist.
- `stat(path) -> FileStat | None` — size + mtime, or `None` when absent.
- `write_text_atomic(path, text) -> None` — temp file + `os.replace`; if the
  target exists, copy it first to a new timestamped file in its own folder under
  `~/.coffer/config-backups/<name>-<hash>/` (`<name>.coffer-backup-<UTC time>`, one per write,
  nothing next to the file; the `config_backups` retention policy keeps each
  file's newest); create parent dirs as needed.
- `latest_backup(path) -> Path | None` — the newest backup of `path`, what an
  undo restores.
- `list_dir(root) -> list[DirEntryInfo] | None` — recursive listing of regular
  `.md` files under `root` (symlinked files skipped, sorted by relpath);
  `None` when `root` is not a directory.
- `delete_with_backup(path) -> bool` — copy content to a timestamped backup (as a
  write does), then remove the file; `False` when
  already absent.
- `remove_tree(path) -> bool` — remove a directory tree with no backup, used
  only for content Coffer rendered itself and can regenerate; `False` when
  already absent.
- `fingerprint(text: str | None) -> str` — sha256 hex digest backing the
  "Reject stale config-file writes by fingerprint" check; `""` for a missing
  file (`None`).
- `resolved_within(path, root) -> bool` — whether `path` resolves, following
  symlinks, inside `root`.

## Kind wiring (`backend/coffer/application/agent/kind.py`)

`make_agent_kind(...)` returns a `Kind` with:

- `name='agent'`
- `display_name='Agent'`
- `config_schema=AgentConfig`
- `on_delete=...` — cascade hook invoked by `ResourceService.delete` to call the **skill-side** binding cleanup (skill module provides the callback; agent kind does not import the skill module directly — the callback is passed to `make_agent_kind` at the composition root).
- `toggleable=False` — an agent has no on/off switch; the generic enable/disable routes refuse it.
- `generic_create_allowed=False` — the kind-agnostic `POST /api/v1/resources` refuses to create an agent; agents are registered only through `AgentService`, which validates the config directory.
- `name_from_config=agent_name_for`, `name_fixed=True`, `titled=False` — the name is the type's (`claude-code`, `codex`), fixed, and there is no title (spec agent-registry "Keep one agent per type, named by it").

## Composition root wiring

The agent kind is wired by `surfaces/http/agent_skill_wiring.py`
(`wire_agent_and_skill_kinds`), called from `surfaces/http/kind_wiring.py`;
the routers are mounted in `surfaces/http/routing.py`. Together they:

1. Build `AgentService` + `AutoDetectService`.
2. Build `AgentConfigFileService` + `AgentMcpService` + `AgentMcpEntryService` +
   `AgentPluginService` + the native-memory and transcript readers over a
   `ConfigFileStore`.
3. Construct the `Kind` via `make_agent_kind(...)` with its `on_delete` hook.
4. Register it in the per-kind registry the kind-agnostic resource routes read.
5. Mount `agent_routes` (registry + candidates), `agent_config_routes` (config
   files), `agent_connection_routes` (the Coffer connection, whose service
   `agent_connection_wiring` builds once the memory kind is wired too),
   `agent_workspace_routes` (MCP entries + plugins),
   `agent_native_memory_routes`, `agent_transcript_routes`,
   and `agent_unmanaged_skill_routes`. The `/fs/*` routes the picker and the
   open/reveal affordances call are mounted by spec daemon, not here.

Discovery is read-only and is **not** run on startup — no agent is ever
auto-registered. The user runs discovery on demand and confirms which
candidates to add.

The `on_delete` hook is bound to a callable supplied by the skill module (spec skill-manager), so that removing an agent triggers the skill-side binding cleanup before the resource file is deleted. Spec agent-registry owns the seam; spec skill-manager owns what it calls.

## Constraints summary

- All HTTP routes bind `127.0.0.1`, share `X-Coffer-Token` auth (per spec mcp-gateway).
- No new secret-store entries — `agent` config has no secrets. Config-file
  reads do not parse or extract secrets; each type's credential file is excluded
  from its allowlist (see agent-registry/codex "Never expose Codex's credential file").
- Config files are editable through Coffer. All writes to an agent's own config
  files — whichever files the type's child spec allowlists — whether a user
  save or a Coffer connect/disconnect — are addressable **only** by
  allowlisted `key`, never by a caller-supplied path, and each is protected by an
  atomic write and a backup copy in Coffer's folder. User saves additionally validate content
  against the file's format before touching disk. No path outside the resolved
  allowlist entries is ever read or written.
