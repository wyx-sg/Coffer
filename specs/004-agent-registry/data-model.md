# Data Model — 004 Agent Registry

Entities, fields, relationships, and storage notes for the agent registry.
Builds on the kind-agnostic Resource framework from spec 001 — agents are rows
in the generic `resources` table, so spec 004 adds no table of its own.

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
| `claude_code` | Claude Code  | `~/.claude`          | `~/.claude.json` · `mcpServers` · map      |
| `codex`       | OpenAI Codex | `~/.codex`           | `config.toml` · `mcp_servers` · map        |
| `cursor`      | Cursor       | `~/.cursor`          | `mcp.json` · `mcpServers` · map            |
| `opencode`    | OpenCode     | `~/.config/opencode` | `opencode.json` · `mcp` · typed-array      |
| `openclaw`    | OpenClaw     | `~/.openclaw`        | `openclaw.json` · `mcp` · map              |
| `hermes`      | Hermes       | `~/.hermes`          | `config.yaml` (YAML) · `mcp_servers` · map |

Skills are delivered to `<config_dir>/skills` (per-agent skill targets are
refined by the skill-delivery work; OpenClaw's real target is
`workspace/skills`). `claude_desktop` (the separate Claude chat app) remains out
of scope.

`AgentDescriptor` carries: `display_name`, `config_subpath`, `config_files`
(allowlist builder), `mcp` (`McpInjectionSpec | None`), `mcp_source_keys`,
`skill_subpath`, and `plugins` (`PluginCapability | None`). Each enum value still
exposes:

- `display_name: str`
- `default_name() -> str` (stable per-type default resource name — underscores become hyphens, e.g. `claude_code` → `claude-code`; used when the user registers without an explicit name)
- `default_config_dir() -> Path` (the type's standard config directory, computed per host platform — `~/.claude` / `~/.codex`; used when the user registers without an explicit `config_dir`)
- `detect_marker() -> Path` (the path checked during discovery; usually the `default_config_dir` itself)

The config-file allowlist and the skills-delivery target (`<config_dir>/skills`) both resolve against the agent's resolved `config_dir`.

### `AgentConfig` (`domain/agent/config.py`)

Pydantic v2 `BaseModel`. The kind-specific config schema registered with `ResourceService`.

| Field               | Type           | Notes                                                                                                                               |
| ------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `type`              | `AgentType`    | required; enum value                                                                                                                |
| `config_dir`        | `Path \| None` | optional absolute-path override; defaults to `type.default_config_dir()` at read time                                               |
| `follow_all_skills` | `bool`         | follow-master-library policy flag (spec 005 FR-025); defaults to `True`, preserving the pre-amendment trust-mode auto-bind behavior |
| `skill_exclusions`  | `list[str]`    | skill names excluded from delivery while following; default `[]`                                                                    |

Skills are delivered to `<config_dir>/skills`; the config-file allowlist resolves against `config_dir`. Only one agent may exist per resolved `config_dir`. The two policy fields are _stored_ here (this spec's schema) but their delivery semantics are owned by spec 005 (`SkillService` follow reconciliation); they surface on `AgentOut` and are updatable via `PATCH /agents/{name}`.

Validators:

- `config_dir` (when set) must be an absolute path; at registration the `<config_dir>/skills` subdirectory is auto-created, then the resolved `config_dir` must be an existing, writable directory.
- `config_dir` must not point inside `/etc`, `/usr`, `/bin`, `/sbin`, `/System` (POSIX) or `C:\Windows`, `C:\Program Files` (Windows).
- `model_config = ConfigDict(extra="forbid")` so unknown fields are rejected.
- A `model_validator(mode="before")` drops a legacy `auto_detected` key from dict input (and maps a legacy `skill_dir` onto `config_dir`) so older rows that persisted now-removed fields still load under `extra="forbid"`.

### `ConfigFileFormat` + config-file allowlist (`domain/agent/config_files.py`)

Pure domain module (no I/O beyond `os.environ`-based path construction, same
pattern as `types.py`). Defines the curated set of config files each agent
type exposes. The files are surfaced **read-only in the UI** — the viewer
renders content and offers open-in-external-editor / reveal / copy-path (the
HTTP `ConfigFileInfo` / `ConfigFileContent` views carry both the file `path`
and its containing-folder `folder_path` for these affordances, FR-038);
programmatic read and write still go through the REST API / CLI.

`ConfigFileFormat` — `StrEnum` of `json`, `toml`, `yaml`, `markdown`, `text`.
Drives save-time validation: `json` parses with `json.loads`, `toml` with
`tomllib.loads`, `yaml` with `yaml.safe_load`; `markdown` and `text` are always
valid.

`ConfigFileKind` — `StrEnum` of `file`, `directory`. A `directory` entry
(FR-034) resolves to a directory of files rather than a single file; its
`format` describes the CHILD files.

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
which is spec 007's domain):

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
| `cursor`      | `mcp`            | `~/.cursor/mcp.json`               | `json`     | `file`      |
| `cursor`      | `rules`          | `~/.cursor/.cursorrules`           | `markdown` | `file`      |
| `cursor`      | `instructions`   | `~/.cursor/AGENTS.md`              | `markdown` | `file`      |
| `opencode`    | `config`         | `~/.config/opencode/opencode.json` | `json`     | `file`      |
| `opencode`    | `instructions`   | `~/.config/opencode/AGENTS.md`     | `markdown` | `file`      |
| `opencode`    | `subagents`      | `~/.config/opencode/agents/`       | `markdown` | `directory` |
| `openclaw`    | `config`         | `~/.openclaw/openclaw.json`        | `json`     | `file`      |
| `hermes`      | `config`         | `~/.hermes/config.yaml`            | `yaml`     | `file`      |
| `hermes`      | `instructions`   | `~/.hermes/SOUL.md`                | `markdown` | `file`      |
| `hermes`      | `identity_user`  | `~/.hermes/USER.md`                | `markdown` | `file`      |
| `hermes`      | `cron`           | `~/.hermes/cron/`                  | `markdown` | `directory` |

(The allowlist for the agents added on top of Claude Code / Codex covers each
agent's config, instructions/identity, and managed directory surfaces and grows
as their other facets land. Cursor carries the global `~/.cursor/.cursorrules`
plus `AGENTS.md`; its per-project `.cursor/rules/*.mdc` are project-scoped, not
config-dir files, so they stay out of the allowlist. OpenCode adds an RW
`agents/` directory. Hermes carries both identity files
(`SOUL.md` + `USER.md`) and the RW `cron/` directory. OpenClaw stays
config-only — its instructions/identity file is not reliably documented, so no
instructions entry is added until confirmed. `global` always anchors to `$HOME`
— Claude Code keeps `~/.claude.json` at the home root even when the config dir
itself is overridden.)

`~/.codex/auth.json` is deliberately excluded (credential/state, not a
hand-edited config). `~/.claude.json` is included (per product decision) and
protected by the `.bak` backup on every write.

`validate_content(fmt: ConfigFileFormat, text: str) -> None` raises
`ConfigFileFormatInvalid` for malformed structured content.

`spec_for(agent_type, key) -> ConfigFileSpec` raises `ConfigFileNotAllowed`
when `key` is not in the type's allowlist (drives the 404 + no-FS-access rule).

### Directory Config Entry (FR-034/FR-035)

An allowlisted entry with `kind=directory` lists its child files instead of
carrying content; the directory on disk is the source of truth (derived, never
stored). Directory entries: Claude Code `subagents` (`~/.claude/agents/`, one
Markdown file per personal subagent, nested paths allowed), OpenCode `subagents`
(`~/.config/opencode/agents/`), and Hermes `cron` (`~/.hermes/cron/`).

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

- **format** — `json` / `toml` / `yaml` — selects the parser/serializer (each
  preserving the user's comments/order: `json` stdlib, `toml` `tomlkit`, `yaml`
  `ruamel.yaml` round-trip).
- **shape** — `container_key` (the top-level table: `mcpServers` / `mcp_servers`
  / `mcp`) + `entry_style` (`McpEntryStyle`): `COMMAND_MAP` (`{"command": shim}`
  — Claude/Codex/Cursor/Hermes) or `TYPED_COMMAND_ARRAY`
  (`{"type": "local", "command": [shim]}` — OpenCode).

`mcp_install.py` builds / detects / removes the `coffer` entry as pure text
transforms (no filesystem):

- `COFFER_SERVER_KEY = "coffer"`.
- `apply_install(fmt, text, shim_path, *, container_key=None, entry_style=COMMAND_MAP) -> str`
  — inserts/updates the `coffer` entry. `container_key` defaults per format
  (`default_container_key`), reproducing Claude/Codex behaviour; new agents pass
  their own. Idempotent.
- `apply_uninstall(fmt, text, *, container_key=None) -> str` — removes the
  `coffer` entry (no-op if absent).
- `is_installed` / `installed_command` (`*, container_key=None`) — presence /
  shim path (the latter handles both command-map and command-array shapes).

The MCP config file for each type is itself an allowlisted config file
(`global` for Claude Code, `config` for Codex). The Coffer-MCP
install/uninstall operations write to it via the atomic-write/backup path
described under `AgentMcpService`; it can also be edited like any other
allowlisted config file through `AgentConfigFileService.write_file`. Both paths
share the same atomic-write + `.bak` machinery.

## SQLite schema additions

**None.** The `agent` kind needs no table of its own — agents are rows in the
generic `resources` table (kind-agnostic Resource framework from spec 001), and
discovery is read-only with no suppression list to persist. The head migration
revision therefore stays at **0004**; spec 004 adds no Alembic migration.

**Config files and Coffer-MCP install state are NOT persisted in SQLite** — the
agent's on-disk config files are the source of truth. Install status is derived
by reading the relevant config file on demand.

### Reuse of existing tables

- `resources`: new rows with `kind='agent'`. No schema change.
- `audit_log`: new event types written (see below). No schema change.

## Audit event types added

Add to `AuditEventType` (`domain/audit.py`):

| Value                       | When emitted                                                                                        |
| --------------------------- | --------------------------------------------------------------------------------------------------- |
| `agent_config_file_written` | A config file was saved through Coffer (atomic write + `.bak`); details carry the config-file `key` |
| `agent_mcp_installed`       | Coffer's MCP server entry was written into an agent's MCP config                                    |
| `agent_mcp_uninstalled`     | Coffer's MCP server entry was removed from an agent's MCP config                                    |

The workspace amendment adds:

| Value                       | When emitted                                                                    |
| --------------------------- | ------------------------------------------------------------------------------- |
| `agent_config_file_deleted` | A directory-entry child file was deleted (prior content preserved as `.bak`)    |
| `agent_mcp_entry_removed`   | A direct MCP entry was removed from the agent's config file (FR-026)            |
| `agent_mcp_entry_adopted`   | A direct MCP entry was adopted into a registered `mcp_server` resource (FR-028) |
| `agent_plugin_toggled`      | A plugin's enabled state was changed on its documented config surface (FR-032)  |
| `agent_plugin_uninstalled`  | A Codex plugin entry + cache directory were removed (FR-033)                    |

The lifecycle steps required by FR-011 — registration, update, and removal — are emitted as the existing kind-agnostic `resource_created`, `resource_updated`, and `resource_deleted` events (each carrying the affected `agent:<name>` reference). No `agent_*` duplicates are added for these; surfaces filter by `kind='agent'` plus the kind-agnostic event type. A successful config-file save emits `agent_config_file_written` (ref `agent:<name>`, details `{key}`). Agents have no enable/disable concept, and discovery is read-only and registers nothing, so neither emits an audit event of its own.

## Application service contracts (`backend/coffer/application/agent/`)

### `AgentService`

| Method                                                                            | Purpose                                                                                                                                                                                                                                      |
| --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `register(type, name=None, config_dir=None, description=None, actor) -> Resource` | Auto-create `<config_dir>/skills`, validate the resolved `config_dir`, then delegate to `ResourceService.register(kind='agent', ...)`. `name` is optional — when omitted, derive `type.default_name()` (e.g. `claude_code` → `claude-code`). |
| `update_config_dir(ref, new_path, actor) -> Resource`                             | Delegate to `ResourceService.update_config`.                                                                                                                                                                                                 |
| `list() -> list[Resource]`                                                        | Delegate to `ResourceService.list(kind='agent')`.                                                                                                                                                                                            |
| `remove(ref, actor) -> None`                                                      | Delete via `ResourceService.delete`. Removal is not permanent — there is no suppression list, so the agent re-appears as a discovery candidate on the next scan.                                                                             |

### `AutoDetectService`

| Method                               | Purpose                                                                                                                                                                                                                                                                                                                         |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `discover() -> list[AgentCandidate]` | Read-only scan: check each `AgentType`'s install marker; for any type whose marker is present but which is not already registered in `resources`, emit an `AgentCandidate`. Registers nothing and writes nothing. NOT called on daemon startup; invoked on demand by `GET /api/v1/agents/candidates` and `coffer agent detect`. |

`AgentCandidate` is a derived value object (not a SQLite entity, never stored):
an installed-but-unregistered agent the user can confirm to register. Fields:
`type` (`AgentType`), `display_name`, `config_dir` (the type's default config
directory, as a string), `default_skill_dir` (the type's default skill
directory, as a string), and `suggested_name` (the type's `default_name()`).
A removed agent re-appears as a candidate on the next scan — there is no
suppression list.

### `BrowseService` (`application/fs/browse_service.py`)

Backs the web folder picker for choosing a custom `config_dir` (FR-023/FR-024).
Read-only: given a directory path (defaulting to the user's home), it lists the
directory's immediate subdirectories — never file contents.

| Method                                | Purpose                                                                                                                                                                                                     |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `browse(path=None) -> FsBrowseResult` | Resolve `path` (default home); return its resolved path, its parent (or `None` at the filesystem root), and its immediate subdirectories. Unreadable or non-existent path → error, never a partial listing. |

The desktop app uses the OS-native directory dialog; the web uses this
daemon-backed browser via `GET /api/v1/fs/browse`, surfaced in the
`FolderPicker.tsx` frontend component.

### `AgentConfigFileService` (`application/agent/config_file_service.py`)

Resolves an agent → its `AgentType`, then operates on that type's config-file
allowlist via a `ConfigFileStorePort`.

| Method                                                                                            | Purpose                                                                                                                                                                                                                                                                                                                                                                                                    |
| ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_files(name) -> list[ConfigFileInfo]`                                                        | For each `ConfigFileSpec` of the agent's type, return key, display name, path, containing-folder `folder_path` (backs the read-only UI's open/reveal/copy-path, FR-038), format, `kind`, `exists`, and (when present) size + mtime. Directory entries additionally carry `files` (recursive `.md` listing as `DirEntryInfo` rows).                                                                         |
| `read_file(name, key) -> ConfigFileContent`                                                       | Resolve `spec_for(type, key)`; return content + `path` + `folder_path` + format + `exists` + `fingerprint` + `memory_block` (the `path`/`folder_path` pair backs open-in-external-editor / reveal / copy-path, FR-038). Missing file → empty content, `exists=False`, `fingerprint=""`, no file created.                                                                                                   |
| `write_file(name, key, content, *, expected_fingerprint=None, actor) -> ConfigFileInfo`           | Resolve `spec_for(type, key)`; `validate_content(format, content)` (malformed json/toml → `ConfigFileFormatInvalid` → 422, file unchanged); when `expected_fingerprint` is supplied, reject with `ConfigFileStale` (→ 409) if the on-disk content changed since the read (FR-036); `store.write_text_atomic` (atomic + `.bak`); record `agent_config_file_written`; return the refreshed `ConfigFileInfo`. |
| `read_child(name, key, relpath) -> ConfigFileContent`                                             | `validate_child_relpath`, then read one child of a directory entry; same shape as `read_file`.                                                                                                                                                                                                                                                                                                             |
| `write_child(name, key, relpath, content, *, expected_fingerprint=None, actor) -> ConfigFileInfo` | Create-on-write save of one child file; same validation / staleness / atomic-write / audit machinery as `write_file` (FR-035).                                                                                                                                                                                                                                                                             |
| `delete_child(name, key, relpath, *, actor) -> None`                                              | Delete one child file, preserving the prior content as `.bak`; records `agent_config_file_deleted`.                                                                                                                                                                                                                                                                                                        |

`ConfigFileContent.fingerprint` is a content fingerprint used for
optimistic-concurrency writes (FR-036) — reads return it, writes carry it
back. `ConfigFileContent.memory_block` is true when the text contains the
managed memory-projection block marker owned by spec 007 (FR-037); the editor
only surfaces a notice, never parses the block.

### `AgentMcpService` (`application/agent/mcp_service.py`)

Installs/uninstalls Coffer's MCP entry by editing the agent's MCP config file
through the same store. Reuses `domain/agent/mcp_install.py`.

| Method                   | Purpose                                                                                                                                                                                                                                         |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `status(name) -> bool`   | Read the agent's MCP config file; return `is_installed`.                                                                                                                                                                                        |
| `install(name, actor)`   | Resolve the shim path (`COFFER_MCP_SHIM_PATH` → `shutil.which("coffer-mcp-shim")` → interpreter scripts dir → bundled fallback; raise `ShimNotFound` if none). `apply_install`; atomic write + `.bak`; audit `agent_mcp_installed`. Idempotent. |
| `uninstall(name, actor)` | `apply_uninstall`; atomic write + `.bak`; audit `agent_mcp_uninstalled`. No-op when absent.                                                                                                                                                     |

## Workspace amendment — derived entities (never stored)

The workspace facets (FR-025..FR-033) operate on the agent's own config files;
the files on disk stay the source of truth and Coffer keeps no copy. Both
entities below are read-time projections.

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
| `is_coffer`        | `bool`           | Coffer's own gateway entry — protected from remove/toggle/adopt                                                                                                  |
| `matches_resource` | `str \| None`    | equivalent registered `mcp_server` resource, filled by the application layer                                                                                     |

Companion helpers: `parse_entries`, `remove_entry`, `set_entry_enabled` (TOML
only), `secret_env_keys` (TOKEN/SECRET/PASSWORD/API_KEY/CREDENTIAL/AUTHORIZATION
patterns), and `to_transport_config` (entry → `mcp_server` transport config
with secret keys moved to `credential_refs` for adoption). Malformed files
raise `AgentConfigParseError`, which the listing degrades to a `parse_errors`
item instead of failing the view (FR-030).

### `PluginCapability` / `PluginModel` (`domain/agent/descriptor.py`)

The plugin facet of the capability manifest. `PluginModel` is the strategy
discriminator — `CLAUDE`, `CODEX`, `CURSOR_RO`, `OPENCODE`, `OPENCLAW` — each
mapping to a parse/toggle/uninstall strategy in `plugin_state.py` /
`plugin_state_extra.py`. `PluginCapability` (frozen) carries enough for the
service to dispatch without an `AgentType` switch:

| Field           | Type          | Notes                                                                |
| --------------- | ------------- | -------------------------------------------------------------------- |
| `model`         | `PluginModel` | parse/toggle/uninstall strategy                                      |
| `config_key`    | `str \| None` | allowlist key of the write surface (`None` = list-only, e.g. Cursor) |
| `can_toggle`    | `bool`        | whether `set_enabled` is supported                                   |
| `can_uninstall` | `bool`        | whether `uninstall` is supported                                     |

`AgentDescriptor.plugins` is `PluginCapability | None`; `None` means the agent
has no plugin concept (Hermes — MCP is the plugin mechanism), so the listing is
empty and toggle/uninstall raise the matching "unsupported" error. The per-agent
mapping: Claude Code `CLAUDE`/`settings`/toggle-only; Codex `CODEX`/`config`/full;
Cursor `CURSOR_RO`/`None`/read-only; OpenCode `OPENCODE`/`config`/full; OpenClaw
`OPENCLAW`/`config`/full; Hermes `None`.

### Agent Plugin (`domain/agent/plugin_state.py`, `domain/agent/plugin_state_extra.py` — `PluginInfo` / `MarketplaceInfo`)

One installed plugin, id `<name>@<marketplace>` (or the bare extension/plugin
name for agents without a marketplace concept). Codex state lives in
`config.toml` (`[plugins."…"]` + `[marketplaces.*]`, both readable and the
plugins table writable). Claude Code splits state across the internal
inventory files `installed_plugins.json` / `known_marketplaces.json`
(read-only inputs — Coffer never writes them) and the documented write surface
`settings.json` `enabledPlugins`. The newer agents add pure-text transforms in
`plugin_state_extra.py`: Cursor reads the `extensions/extensions.json` array
(read-only); OpenCode toggles membership in the `plugin` array of
`opencode.json`; OpenClaw reads/writes the `plugins{}` block of `openclaw.json`
(tolerant of its partly documented `entries`/`enabled`/`allow`/`deny` shape).
Agents without a marketplace concept return an empty `marketplaces` list.

| Field         | Type   | Notes                                                               |
| ------------- | ------ | ------------------------------------------------------------------- |
| `id`          | `str`  | `<name>@<marketplace>` (split on the last `@`)                      |
| `name`        | `str`  |                                                                     |
| `marketplace` | `str`  |                                                                     |
| `enabled`     | `bool` | defaults to `True` when the config carries no explicit flag         |
| `installed`   | `bool` | present in the install inventory; settings-only orphans get `False` |

`MarketplaceInfo` carries `name`, `source_type`, `source` (read-only). The
HTTP view (`PluginView`) replaces `installed` with `cache_present` — whether
the plugin's cache directory exists on disk (no repair is attempted, FR-031).

### `AgentMcpEntryService` (`application/agent/mcp_entry_service.py`)

| Method                                                                | Purpose                                                                                                                                                                                                                                                                     |
| --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_entries(name)`                                                  | Parse all MCP-bearing files of the agent's type; mark `is_coffer` and `matches_resource`; collect per-file `parse_errors`.                                                                                                                                                  |
| `set_enabled(name, entry, enabled, actor)`                            | Toggle the `enabled` flag in place (codex `config.toml` only — claude_code → `McpEntryToggleUnsupported` → 422). `coffer` entry → `McpEntryProtected`.                                                                                                                      |
| `remove_entry(name, entry, source=None, actor)`                       | Remove the entry from its source file (atomic + `.bak`); `source` disambiguates when claude_code carries the name in both files (else `McpEntrySourceAmbiguous`); audits `agent_mcp_entry_removed`.                                                                         |
| `adopt(name, entry, source=None, new_name=None, secrets=None, actor)` | FR-028 promotion: secret-looking keys MUST map to keychain refs (`AdoptSecretUnresolved` lists unresolved keys); register the `mcp_server` resource → verify it reads back → remove the source entry, with rollback on any later failure; audits `agent_mcp_entry_adopted`. |

### `AgentPluginService` (`application/agent/plugin_service.py`)

| Method                                         | Purpose                                                                                                                                                                                                                                  |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `list_plugins(name)`                           | Dispatch on `descriptor.plugins.model`; parse plugin + marketplace state from the documented file(s); compute `cache_present`; collect `parse_errors`. No capability → empty listing.                                                    |
| `set_enabled(name, plugin_id, enabled, actor)` | Dispatch on the `PluginModel`; write only the capability's `config_key` surface; `can_toggle=false` (Cursor) or no capability (Hermes) → `PluginToggleUnsupported` → 422; audits `agent_plugin_toggled`.                                 |
| `uninstall(name, plugin_id, actor)`            | Dispatch on the `PluginModel`; remove the entry (Codex also deletes the cache directory); `can_uninstall=false` (Claude Code, Cursor) or no capability (Hermes) → `PluginUninstallUnsupported` → 422; audits `agent_plugin_uninstalled`. |

### `ConfigFileStorePort` (Protocol, defined in application)

Application-layer interface; concrete impl lives in
`infrastructure/agent/config_file_store.py` (Contract 4 — application must not
import infrastructure directly).

- `read_text(path) -> str | None` — `None` when the file does not exist.
- `stat(path) -> FileStat | None` — size + mtime, or `None` when absent.
- `write_text_atomic(path, text) -> None` — temp file + `os.replace`; if the
  target exists, copy it to `<path>.bak` first; create parent dirs as needed.
- `list_dir(root) -> list[DirEntryInfo] | None` — recursive listing of regular
  `.md` files under `root` (symlinked files skipped, sorted by relpath);
  `None` when `root` is not a directory.
- `delete_with_backup(path) -> bool` — copy content to `<path>.bak`, then
  remove the file.
- `fingerprint(text) -> str` — content fingerprint backing the FR-036
  staleness check.

## Kind wiring (`backend/coffer/application/agent/kind.py`)

`make_agent_kind(...)` returns a `Kind` with:

- `name='agent'`
- `display_name='Agent'`
- `config_schema=AgentConfig`
- `on_delete=...` — cascade hook invoked by `ResourceService.delete` to call the **skill-side** binding cleanup (skill module provides the callback; agent kind does not import the skill module directly — wiring is via a setter on the kind module at composition root).

## Composition root wiring

In `surfaces/http/app.py`, `_wire_agent_kind(app, resource_svc, audit, sm)`:

1. Build `AgentService` + `AutoDetectService` + `BrowseService`.
2. Build `AgentConfigFileService` + `AgentMcpService` over a `ConfigFileStore`.
3. Construct the `Kind` via `make_agent_kind(on_delete_hook)`.
4. Register into `app.state.kinds['agent']`.
5. Mount `agent_routes` (registry + candidates), `agent_config_routes`
   (config files + MCP install), and `fs_routes` (read-only folder browse).

Discovery is read-only and is **not** run on startup — no agent is ever
auto-registered. The user runs discovery on demand and confirms which
candidates to add.

The `on_delete_hook` is bound to a callable supplied by the skill module (the 005-skill-manager spec), so that removing an agent triggers `SkillService.cleanup_bindings_for_agent(...)` synchronously before the resource row is deleted — once the 005-skill-manager spec wires the callback. Spec 004 only exposes the hook seam.

## Constraints summary

- All HTTP routes bind `127.0.0.1`, share `X-Coffer-Token` auth (per spec 001).
- No new credential-store entries — `agent` config has no credentials. Config-file
  reads do not parse or extract secrets; `~/.codex/auth.json` is excluded from
  the allowlist.
- Config files are editable through Coffer. All writes to an agent's own config
  files (under `~/.claude/`, `~/.codex/`, and `~/.claude.json`) — whether a user
  save or a Coffer-MCP install/uninstall — are addressable **only** by
  allowlisted `key`, never by a caller-supplied path, and each is protected by an
  atomic write and a `.bak` backup. User saves additionally validate content
  against the file's format before touching disk. No path outside the resolved
  allowlist entries is ever read or written.
