# Feature Specification: Agent Registry

**Feature Branch**: `feature/004-agent-registry`
**Created**: 2026-05-22
**Status**: Accepted
**Input**: User description: "Manage which locally-installed AI agents Coffer knows about, so later features (skills, memory, knowledge bases) can deliver assets to them. Each agent is a Resource of kind `agent` in the kind-agnostic Resource framework introduced by spec 001-mcp-gateway. v1 supports two agent types: Claude Code and OpenAI Codex — each covering both its CLI and its desktop/IDE form, which share one on-disk config. Beyond registering agents, the user can view (read-only) each agent's known config files and open them in an external editor, and install Coffer's own MCP server into an agent with one click."

> **Note on agent types.** Supported products: **Claude Code** (`claude_code`, `~/.claude/`), **OpenAI Codex** (`codex`, `~/.codex/`), and — re-added by the multi-agent amendment below — **opencode** (`opencode`, `~/.config/opencode/`), **hermes** (`hermes`, `~/.hermes/`), **cursor** (`cursor`, `~/.cursor/`), and **OpenClaw** (`openclaw`, `~/.openclaw/`, [ADR-044](../../docs/decisions/ADR-044-openclaw-managed-agent.md)). Each spans its CLI _and_ its app/IDE form because they read one shared config directory. Per-type behaviour lives in the capability manifest (`AGENT_DESCRIPTORS`) — adding a product is one enum value + one descriptor record (config-file allowlist, MCP injection shape, etc.). The separate **Claude Desktop** chat app (its own `~/Library/Application Support/Claude/` config) is out of scope.

> **Multi-agent re-widening amendment ([ADR-040](../../docs/decisions/ADR-040-re-widen-agent-registry.md)).** An earlier simplification narrowed the registry to two products and deleted the `cursor` / `opencode` / `openclaw` / `hermes` enum values (data migration `0031`). This amendment reverses that for three additional **managed coding CLIs** — `opencode`, `hermes`, `cursor` — each delivered as one `AgentDescriptor` record plus, where its wire protocol is not already covered, one chat-provider adapter (spec 008). The manifest is the same seam it always was; re-widening is data, not new machinery, except where a product's native format differs from the JSON/TOML the two original agents use. Two constraints are documented as **capability gaps**, not bugs, and surface through the manifest so unsupported actions are hidden rather than failing: (a) `opencode` has no shell-command lifecycle hook — only in-process JS plugin callbacks — so its session-context injection differs from Claude Code/Codex; (b) `cursor` is locked to Cursor's own backend and exposes no custom LLM base URL, so provider/API-key projection (spec 011) is **N/A** for it. The fourth removed type, **openclaw**, was initially left out as "a peer gateway, not a leaf" ([ADR-040](../../docs/decisions/ADR-040-re-widen-agent-registry.md)); [ADR-042](../../docs/decisions/ADR-042-context-injection-mechanisms.md)'s re-check found three of that verdict's five capability cells wrong, and [ADR-044](../../docs/decisions/ADR-044-openclaw-managed-agent.md) reverses it — **openclaw IS the sixth managed agent**, every facet probe-verified against a real install (openclaw 2026.6.11). Per-agent facet support is tabulated in the **Agent capability matrix** under Requirements (FR-003).

> **Workspace amendment.** Stories 9–12 extend the registry into the agent's real on-disk workspace: the MCP servers actually configured in the agent's own files, the agent's installed plugins, and directory-type config entries. The guiding principle is **ingest → hub → deliver**: anything shareable found in an agent's workspace can be adopted into Coffer's hub (the MCP gateway, the master skill store of spec 005) and delivered back to any agent, instead of living as per-agent one-off config. All writes go through each agent's documented configuration paths only; internal state files are read, never written.

> **Note on the built-in agent ([ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md)).** This registry holds only **managed** agents — locally-installed external coding agents (Claude Code, Codex, …) that Coffer delivers assets to. The former `builtin` "Coffer Assistant" is **not** a registered agent here: [ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md) retires it as a chat persona and recasts its local model as an internal Coffer capability reached only through `coffer__*` MCP tools. (The separate chat agent-provider registry of spec 008 likewise drops the `builtin` provider and lists managed agents only.)

## User Scenarios & Testing

### User Story 1 — Discover installed agents and choose which to add (Priority: P1)

When a developer opens the Agents page (or runs `coffer agent detect`), Coffer scans well-known install paths for each supported agent type and presents the ones it finds that aren't registered yet as **candidates**. The developer reviews them and confirms which to add — Coffer never registers an agent silently.

**Why this priority**: Near-zero-config first impression without surprises. Detection finds agents so the user doesn't have to learn type identifiers and default paths, but the user stays in control of what enters their registry.

**Independent Test**: On a machine with `~/.claude/` and `~/.codex/` present, open the Agents page, run detection, observe both Claude Code and Codex offered as candidates; confirm them and observe both registered.

**Covering scenarios**:

- discover installed agents as candidates
- skip already-registered types on subsequent scan
- re-surface removed agents on subsequent scan

---

### User Story 2 — Manually register an agent with a custom path (Priority: P1)

Some users install agents in non-default locations or have multiple installs (work vs personal). They need to add an agent by type, optionally overriding the config directory. The name is optional — when omitted Coffer derives a stable per-type default. When choosing a custom path, the desktop app offers a folder picker (the OS-native dialog in the packaged app; a daemon-backed folder browser on the web) so the user picks a real directory instead of typing it.

**Why this priority**: Discovery covers the common case; manual register covers the long tail. Without it the registry is incomplete.

**Independent Test**: From the command line, register a `codex` agent named `codex-work` with `--config-dir /custom/path`; list agents; observe the manually-registered entry. From the desktop form, add an agent with no name and observe it registered under the per-type default name.

**Covering scenarios**:

- register an agent with a custom config dir
- register an agent without an explicit name
- reject registration when the config dir is missing or not writable
- reject duplicate agent names
- browse local folders to choose a config dir

---

### User Story 3 — Edit or remove an agent (Priority: P1)

The user's installed agents change over time. They need to update the config_dir path or description, or fully delete the agent. (Agents have no enable/disable concept — a registered agent is simply present.)

**Why this priority**: An immutable registry would be useless within a week.

**Independent Test**: Register an agent, update its config_dir, then remove it; verify each state is persisted and audited.

**Covering scenarios**:

- update config_dir for an existing agent
- remove an agent and observe audit entry

---

### User Story 4 — Manage agents through the desktop app (Priority: P2)

The user opens Coffer's desktop app, sees an "Agents" page listing every registered agent with type, name, and config_dir, and can add or edit from a form.

**Why this priority**: Non-CLI users need a visual surface to make sense of the registry.

**Independent Test**: Open desktop app → Agents → add Codex with default path → observe in list → click into it → change config_dir → save → list updates.

**Covering scenarios**:

- agents page lists all registered agents
- add an agent through the desktop form
- edit an agent through the desktop form
- remove an agent through the desktop confirmation

---

### User Story 5 — Same operations from the command line (Priority: P2)

The user scripts registry setup (dotfiles, CI machines). All operations available in the UI are available as `coffer agent ...` subcommands with `--json` output.

**Why this priority**: Coffer's audience is developers. CLI parity is table stakes.

**Independent Test**: A bash script registers two agents, lists them in JSON, edits one, removes one — all without touching the GUI.

**Covering scenarios**:

- command line covers every visual operation
- machine-readable JSON output

---

### User Story 6 — Audit registry changes (Priority: P3)

Every add / edit / remove / auto-detection is recorded with timestamp and actor, queryable from CLI and UI.

**Why this priority**: Builds trust and helps debug "wait, when did this change?" Not blocking core registry operation.

**Independent Test**: Make several changes; view audit log; observe one row per change with actor and event type.

**Covering scenarios**:

- audit agent lifecycle events

---

### User Story 7 — View an agent's config files and open them in an external editor (Priority: P2)

After an agent is registered, the user wants to see that agent's own configuration files (e.g. Claude Code's `settings.json`, Codex's `config.toml`) directly inside Coffer, without leaving the app to hunt for dotfiles. Coffer shows the agent type's curated set of known config files and lets the user open one to read its current content in a **read-only** viewer. For each file Coffer offers open-in-external-editor and reveal-in-file-manager affordances, so the user makes any edits in their own editor. Coffer does not edit config-file content in place; the programmatic write path (REST/CLI) keeps the validate + atomic-write + `.bak` safety net.

**Why this priority**: Locating agent config by hand means remembering where each file lives and what format it uses. Surfacing the curated set in one place — viewable at a glance, one click from the user's own editor — is the first feature that makes the registry useful beyond bookkeeping.

**Independent Test**: Register a `claude_code` agent; list its config files; open `settings.json` in the read-only viewer and observe the response surfaces the file's `path` and containing-folder `folder_path` (backing open/reveal); open a not-yet-created file (e.g. `CLAUDE.md`) and observe it reads as empty without being created.

**Covering scenarios**:

- list an agent's curated config files with existence + size metadata
- read the content of an existing config file
- read a not-yet-created config file as empty
- reject reading a key outside the agent type's allowlist

---

### User Story 8 — Install Coffer's MCP into an agent in one click (Priority: P2)

The user wants their agent (Claude Code, Codex) to actually use Coffer. From the agent's management view they click "Install Coffer MCP", and Coffer writes its own MCP-server entry into that agent's MCP config — a `coffer` stdio entry pointing at the `coffer-mcp-shim` binary. A status indicator shows whether Coffer is currently installed, and the user can uninstall to remove the entry.

**Why this priority**: Wiring an MCP server into a client by hand (editing `~/.claude.json` or `~/.codex/config.toml` correctly) is exactly the friction Coffer exists to remove. One click closes the loop between "Coffer knows your agent" and "your agent can use Coffer".

**Independent Test**: Register a `claude_code` agent with Coffer not yet installed; check status (not installed); install; observe a `coffer` entry written to `~/.claude.json` `mcpServers` with an absolute `command` path to the shim; check status (installed); install again (no duplicate); uninstall; observe the entry removed.

**Covering scenarios**:

- report Coffer-MCP install status for an agent
- install Coffer's MCP entry into a Claude Code agent (`~/.claude.json`)
- install Coffer's MCP entry into a Codex agent (`~/.codex/config.toml`)
- install is idempotent — re-installing does not duplicate the entry
- uninstall removes the Coffer entry
- install/uninstall write atomically with a `.bak` backup and emit an audit entry

---

### User Story 9 — See and manage the agent's real MCP servers (Priority: P2)

The agent's MCP servers tab today can only say whether Coffer's own shim is installed. The user wants to see what their agent **actually** has configured: every MCP server entry in the agent's own config files — for Claude Code from both `~/.claude.json` `mcpServers` and `settings.json` `mcpServers`, for Codex from `config.toml` `[mcp_servers.*]`. Each entry shows its transport (stdio command or HTTP URL), which file it came from, and (Codex only — the format defines a per-entry flag) its enabled state. The user can remove an entry or toggle a Codex entry's flag; Coffer's own `coffer` entry is rendered specially and managed by the existing install/uninstall actions.

**Why this priority**: The current tab shows the same Coffer-global list for every agent, which is misleading. Showing the agent's real configuration is the prerequisite for every other MCP-management action.

**Independent Test**: Register a `codex` agent whose `config.toml` carries several `[mcp_servers.*]` entries; open the MCP tab; observe exactly those entries with transports and enabled flags; remove one and observe it gone from the file (with a `.bak` kept); toggle another and observe its `enabled` flag flipped in place.

**Covering scenarios**:

- list an agent's real MCP entries
- remove a direct MCP entry
- toggle a Codex MCP entry's enabled flag
- reject toggling a Claude Code MCP entry
- degrade to read-only when MCP config is unparseable

---

### User Story 10 — Adopt a direct MCP server into Coffer (Priority: P2)

A direct MCP entry in one agent benefits that agent alone. The user clicks "Adopt into Coffer" on a direct entry: Coffer registers it as an `mcp_server` resource (so it is served to **every** agent through the gateway) and removes the now-redundant direct entry from the agent's config. If the entry's environment carries secret-looking values, Coffer routes them into the OS keychain and stores references only. If an equivalent resource already exists, Coffer offers to just remove the duplicate direct entry.

**Why this priority**: This is the ingest half of Coffer's hub-and-spoke model — the single action that turns scattered per-agent config into shared, gateway-served resources.

**Independent Test**: With a `codex` agent carrying a direct stdio entry, adopt it; observe a new `mcp_server` resource registered, the direct entry removed from `config.toml`, and the gateway serving the upstream's tools to all agents.

**Covering scenarios**:

- adopt a direct MCP entry into Coffer
- reject adoption on resource name conflict
- require keychain mapping for secret-like env values
- adoption failure leaves agent config untouched

---

### User Story 11 — Manage the agent's plugins (Priority: P2)

Agents with a file-backed plugin system expose it through the agent's Plugins tab: every installed plugin in a single table — the marketplace it came from is a column, not a per-marketplace section — with its enabled state and whether its on-disk cache is present. Each row expands to reveal the plugin's manifest detail (description, version, author, homepage) and the skills, commands, and MCP servers it bundles, read read-only from the plugin's install directory (recorded as `installPath` in the agent's plugin inventory). Because those components belong to the plugin, they surface here rather than on the agent's Skill / MCP pages, which only list the agent's own standalone resources. The plugin facet is generalised through the capability manifest — each agent record carries a `PluginCapability` (a plugin-model discriminator, the write-surface allowlist key, and `can_toggle`/`can_uninstall` flags), so the service dispatches on data rather than per-agent branches. Each capability maps to the agent's documented configuration surface; internal state files are read, never written. Installing new plugins and managing marketplaces stay with the agent's own tooling.

Per-agent plugin support:

| Agent       | Plugin model                                                                                                      | Write surface    | List  | Toggle | Uninstall                     |
| ----------- | ----------------------------------------------------------------------------------------------------------------- | ---------------- | ----- | ------ | ----------------------------- |
| Claude Code | `enabledPlugins` map in `settings.json` (internal `installed_plugins.json` / `known_marketplaces.json` read-only) | `settings.json`  | yes   | yes    | yes (via `claude plugin` CLI) |
| Codex       | `[plugins."<name>@<marketplace>"]` tables + cache dir                                                             | `config.toml`    | yes   | yes    | yes (entry + cache)           |

**Why this priority**: Plugins are real, persistent agent configuration that today is invisible to Coffer. Visibility plus the cheap, safe writes (toggle, uninstall where supported) cover the recurring needs; installation is left where it already works.

**Independent Test**: Register a `codex` agent with plugins configured; open the Plugins tab; observe the plugins grouped by marketplace with enabled state; disable one and observe `enabled = false` written to `config.toml`; uninstall one and observe its config entry and cache directory gone.

**Covering scenarios**:

- list an agent's plugins with enabled state
- surface a plugin's manifest detail (version/description/author) and the skills, commands, and MCP servers it bundles, read from its install directory
- toggle a plugin's enabled state
- uninstall a Codex plugin
- uninstall a Claude Code plugin via its CLI (Coffer never hand-writes Claude's internal files)
- reject Claude uninstall when its plugin CLI is unavailable
- flag a plugin whose cache is missing

---

### User Story 12 — Manage directory-type config entries (Priority: P2)

Some agent configuration is a directory of prose files, not a single file — Claude Code's `agents/` directory holds one Markdown file per personal subagent. The user expands such an entry in the config-files tab and sees its files, opening one in the read-only viewer (with open-in-external-editor / reveal for the child file and its folder). Creating, writing, and deleting individual files is available programmatically through the REST API / `coffer agent` CLI — with the same validation, atomic-write, and `.bak` safety net as single-file entries. The allowlist also gains Codex's `hooks.json`; the `memory` key is renamed `instructions` (CLAUDE.md / AGENTS.md are human-authored instructions, not agent-written memory).

**Why this priority**: Subagent definitions are exactly the kind of shareable prose the hub model wants visible first, adoptable later; today they are invisible.

**Covering scenarios**:

- list a directory config entry's files
- create a file inside a directory entry
- delete a file inside a directory entry
- reject directory file paths outside the entry
- reject stale config-file writes

---

### Edge Cases

- **Discovery on a second scan**: Already-registered types are not offered as candidates; discovery never duplicates existing entries.
- **User deletes an agent**: A removal is not permanent. The next scan re-surfaces that agent as a candidate (the deletion may have been accidental); Coffer keeps no suppression list. The user re-adds with one confirm.
- **Agent type not in the supported list**: Registration rejected with a clear message and the supported-type list (the manifest types — `claude_code`, `codex`, `opencode`, `hermes`, `cursor`, `openclaw`).
- **`config_dir` path doesn't exist or isn't writable**: Registration rejected; no partial state.
- **`config_dir` points to a privileged path** (`/etc`, `/usr`, etc.): Registration rejected.
- **Duplicate name within `agent` kind**: Rejected by the kind-agnostic Resource framework.
- **Config-file key not in the type's allowlist**: Read rejected with `not_found` (404); no filesystem access for an unknown key.
- **Config file does not exist yet**: Listed and readable as `exists=false` with empty content; the read never creates the file.
- **Coffer MCP install when already installed**: Idempotent — the `coffer` entry is updated in place, never duplicated; status remains `installed`.
- **Coffer MCP uninstall when not installed**: No-op success; status reports `not_installed`.
- **`coffer-mcp-shim` binary cannot be resolved**: Install rejected with a clear error naming the missing binary; nothing is written to the agent's config.
- **Folder browse outside the home directory**: The daemon-backed folder browser lists subdirectories of any readable directory the user navigates to; it never returns file contents. An unreadable or non-existent path returns an error, not a partial listing.
- **Agent config file fails to parse**: The affected facet (MCP entries, plugins) shows an explicit parse-error state and degrades to read-only; other facets and tabs are unaffected. Write operations against the broken file are rejected until it parses again.
- **Same MCP entry name in both Claude Code source files**: Both entries are listed, each labelled with its source file; remove/adopt requests carry the source so the right one is edited.
- **Coffer's own `coffer` MCP entry**: Never adoptable, never listed as a plain direct entry — it is the gateway's install state, managed by Story 8's install/uninstall.
- **Adoption requested for an entry equivalent to an existing resource**: Coffer reports the match (`matches_resource`) and offers removing the redundant direct entry instead of creating a duplicate resource.
- **Plugin configured but cache directory missing**: Listed with `cache_present=false` so the user sees the drift; Coffer does not attempt repair (reinstalling is the agent's own tooling).
- **The agent's own process rewrites a config file between Coffer's read and write**: The write is rejected as stale (fingerprint mismatch, 409); the user re-reads and retries. The `.bak` of every Coffer write keeps the prior content recoverable in the reverse race.
- **Instructions file contains the spec-007 memory-projection managed block**: The read-only viewer annotates that the block is owned by the memory feature; any editing happens in the user's external editor.
- **`~/.codex/auth.json` and other credential/state files**: Never enter any allowlist or listing; plugin and MCP parsing never reads them.

## Agent machine scope (Amendment 2026-07-10 — machine × agent scope, [ADR-045](../../docs/decisions/ADR-045-machine-agent-resource-scope.md))

An `agent` resource carries a framework-level `scope` restricted to the
MACHINE axis only (an `agent`'s scope entries accept only `"*"` as their
value, schema-enforced — an agent-name list is rejected, since an agent
resource IS the thing other kinds' agent axes reference, not itself a
target of one). `scope == None` (the default) means the agent is expected on
every machine; `scope == {"<ulid>": "*"}` (or `{"*": "*"}`) restricts it to
named machines.

- **Out-of-scope machines skip side-effects, not sync.** The agent's
  resource doc still syncs to and is visible on every machine (unchanged
  from spec 010's existing import pipeline). On a machine OUTSIDE the
  agent's scope, import upserts the registry row but performs none of the
  machine-local side-effects that would otherwise follow: no Coffer-MCP
  projection, no post-import reconcile hook run (spec 010's "Import
  reconciliation"), no shim install/refresh, no session-context hook
  install. The agent simply sits inert in the registry on that machine —
  visible in the Machines fleet view (spec 010) as "not present here," never
  as a quarantined or errored row.
- **Import gate demoted to an in-scope fallback.** Spec 010's import gate
  (the `config_dir`-existence check that quarantines an agent doc when its
  directory is missing locally) now runs ONLY for a machine that IS in the
  agent's scope (or when scope is `None`, the default "every machine"). A
  machine outside the agent's scope never reaches the gate at all — its
  missing `config_dir` is expected, not a quarantine condition. This closes
  the ADR-045 Context gap: an agent not installed on a machine no longer
  produces permanent quarantine noise once its scope excludes that machine;
  the gate remains the safety net for the case where scope says a machine
  SHOULD have the agent but its directory isn't there yet (not-yet-installed,
  not out-of-scope).

## Acceptance Scenarios

Per `agents/sdd.md` and `agents/testing.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="004-agent-registry", scenario="…")` (Python) or `acceptance("004-agent-registry", "…", …)` (TypeScript).

### Scenario: discover installed agents as candidates

- **Given** a Coffer install with `~/.codex/` present and no agent registered,
- **When** the user runs discovery,
- **Then** Coffer reports a `codex` candidate (type, display name, default config dir, suggested name) and registers nothing — discovery is read-only.

### Scenario: skip already-registered types on subsequent scan

- **Given** a `codex` agent is already registered,
- **When** the user runs discovery again,
- **Then** `codex` is not offered as a candidate.

### Scenario: re-surface removed agents on subsequent scan

- **Given** an agent has been removed by the user and its install marker is still present,
- **When** the user runs discovery again,
- **Then** that agent is offered as a candidate again (removal is not permanent; no suppression list).

### Scenario: register an agent with a custom config dir

- **Given** the daemon is running,
- **When** the user registers an agent of supported type with an explicit, writable `config_dir`,
- **Then** the agent is persisted with that path (and its `<config_dir>/skills` subdirectory auto-created) and appears in `coffer agent list`.

### Scenario: reject registration with an invalid config dir

- **Given** the daemon is running,
- **When** the user registers an agent whose `config_dir` does not exist, is not a directory, or is not writable,
- **Then** registration is rejected with a message naming the path, and nothing is persisted.

### Scenario: reject duplicate agent name

- **Given** an agent named `codex-work` exists,
- **When** the user attempts to register another agent with the same name,
- **Then** registration is rejected with a clear error.

### Scenario: reject a second agent for an already-registered config dir

- **Given** a `codex` agent is already registered (whose config dir is `~/.codex`),
- **When** the user attempts to register another `codex` agent (which resolves to the same config dir), even with a different name and config_dir,
- **Then** registration is rejected with a clear error and nothing is persisted — only one agent may exist per config directory.

### Scenario: register an agent without an explicit name

- **Given** the daemon is running,
- **When** the user registers an agent of supported type without supplying a name,
- **Then** the agent is registered under a stable per-type default name (underscores become hyphens, e.g. `claude_code` → `claude-code`).

### Scenario: browse local folders to choose a config dir

- **Given** the daemon is running,
- **When** the web folder browser requests the subdirectories of a readable directory,
- **Then** Coffer returns that directory's path, its parent, and its immediate subdirectories (no file contents); an unreadable or missing path returns an error.

### Scenario: open a managed file via the daemon (web open/reveal)

- **Given** the daemon is running and the read-only viewer is showing a managed file,
- **When** the web surface asks the daemon to open an existing absolute path (optionally with a preferred editor) or to reveal it in the file manager,
- **Then** the daemon launches the OS application / file manager for that path and returns success; a relative or non-existent path is rejected without spawning anything.

### Scenario: update an existing agent

- **Given** a registered agent,
- **When** the user updates its `config_dir` to a new writable path,
- **Then** the change persists, an audit entry is recorded, and subsequent operations see the new path.

### Scenario: remove an agent

- **Given** a registered agent (any binding cleanup is handled by the 005-skill-manager spec),
- **When** the user removes it,
- **Then** the agent is deleted, an audit entry is recorded, and `coffer agent list` no longer shows it.

### Scenario: desktop app agents page

- **Given** Coffer's desktop app is launched and one or more agents are registered,
- **When** the user opens the Agents page,
- **Then** every registered agent appears with type, name, and `config_dir`.

> Story 4 add/edit/remove flows from the desktop form are exercised at the e2e tier; see `e2e/web/specs/shell_agents.spec.ts` for the bundled acceptance coverage.

### Scenario: CLI surface mirrors REST operations

- **Given** the daemon is running and exposes the REST agent routes,
- **When** the user invokes `coffer agent add`, `list`, `edit`, `rm`, or `detect`,
- **Then** each subcommand calls the corresponding REST endpoint and produces equivalent state changes, and every read subcommand additionally accepts `--json` for machine-readable output.

### Scenario: reject registration into privileged system path

- **Given** the daemon is running,
- **When** the user attempts to register an agent whose `config_dir` resolves under a privileged location (`/etc`, `/usr`, `/bin`, `/sbin`, `/System`, `C:\Windows`, or `C:\Program Files`),
- **Then** registration is rejected with `unprocessable_entity` (422) and no resource row, audit event, or filesystem write occurs.

### Scenario: audit lifecycle events

- **Given** the user has registered, edited, or removed agents,
- **When** they view the audit log,
- **Then** every lifecycle change (create, update, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events, each carrying timestamp, actor, and the affected agent reference. (Agents have no enable/disable concept; discovery is read-only and registers nothing, so neither emits an audit event of its own.)

### Scenario: reject unsupported agent type

- **Given** the daemon is running,
- **When** the user attempts to register an agent of a type outside the supported set (e.g. `claude_desktop`, `gemini_cli`, or a garbage value),
- **Then** registration is rejected with `unprocessable_entity` (422) naming the supported types, and nothing is persisted.

### Scenario: an agent scoped to machine A causes no quarantine noise on machine B

- **Given** machine A registers an agent whose `scope` is set to machine A only, and machine B has no directory at that agent's `config_dir`,
- **When** B's sync run imports the agent resource,
- **Then** the agent row upserts on B without evaluating spec 010's import gate, B's sync status reports no quarantine for it, and B performs no projection / reconcile / shim install for that agent — while A continues operating it normally.

### Scenario: list an agent's config files

- **Given** a registered `claude_code` agent,
- **When** the user lists its config files,
- **Then** Coffer returns the curated set for the type — `settings.json`, `settings.local.json`, `~/.claude.json`, `CLAUDE.md` (key `instructions`), and the `agents/` directory entry — each with its resolved path, its containing-folder absolute path (`folder_path`), format, and an `exists` flag (with size + modified time when present).

### Scenario: read an existing config file

- **Given** a registered agent whose `settings.json` exists,
- **When** the user reads that config-file key,
- **Then** Coffer returns the file's current text content, its format (`json`), and `exists=true`.

### Scenario: read a not-yet-created config file

- **Given** a registered agent whose `CLAUDE.md` does not exist on disk,
- **When** the user reads that config-file key,
- **Then** Coffer returns empty content with `exists=false` and does not create the file.

### Scenario: reject config-file key outside the allowlist

- **Given** a registered agent,
- **When** the user references a config-file key not in that agent type's curated allowlist,
- **Then** Coffer responds `not_found` (404) and performs no filesystem read.

### Scenario: save a config file with valid content

- **Given** a registered `claude_code` agent whose `settings.json` exists,
- **When** the user writes new, well-formed content to that config-file key through the REST API or `coffer agent` CLI (the in-app UI is read-only),
- **Then** Coffer validates the content against the file's format, writes it atomically while keeping a `.bak` of the prior version, records an `agent_config_file_written` audit entry, and the new content reads back on the next read.

### Scenario: reject malformed config-file content

- **Given** a registered agent whose `settings.json` (a `json` file) exists,
- **When** the user writes malformed content (e.g. invalid JSON) to that key through the REST API or `coffer agent` CLI (the in-app UI is read-only),
- **Then** Coffer responds `unprocessable_entity` (422), leaves the on-disk file unchanged, writes no `.bak`, and records no write audit entry.

### Scenario: report Coffer-MCP install status

- **Given** a registered agent whose MCP config does not contain a `coffer` server entry,
- **When** the user checks Coffer-MCP install status,
- **Then** Coffer reports `installed=false`.

### Scenario: install Coffer's MCP into an agent

- **Given** a registered `claude_code` agent and a resolvable `coffer-mcp-shim` binary,
- **When** the user installs Coffer's MCP,
- **Then** a `coffer` entry is written into `~/.claude.json` `mcpServers` with `command` set to the absolute shim path, the prior file is backed up to `.bak`, an `agent_mcp_installed` audit entry is recorded, and install status reports `installed=true`.

### Scenario: install Coffer's MCP is idempotent

- **Given** an agent that already has Coffer's MCP installed,
- **When** the user installs again,
- **Then** the existing `coffer` entry is updated in place (never duplicated) and status still reports `installed=true`.

### Scenario: uninstall Coffer's MCP from an agent

- **Given** an agent that has Coffer's MCP installed,
- **When** the user uninstalls it,
- **Then** the `coffer` entry is removed from the agent's MCP config, the file is backed up to `.bak`, an `agent_mcp_uninstalled` audit entry is recorded, and status reports `installed=false`.

### Scenario: config-file and MCP operations mirror across surfaces

- **Given** the daemon exposes the config-file and MCP-install routes,
- **When** the user invokes the equivalent `coffer agent config …` / `coffer agent mcp …` CLI subcommands,
- **Then** each subcommand calls the corresponding REST endpoint and produces equivalent state, and read subcommands accept `--json`.

### Scenario: list an agent's real MCP entries

- **Given** a registered `codex` agent whose `config.toml` defines several `[mcp_servers.*]` entries including `coffer`,
- **When** the user lists the agent's MCP entries,
- **Then** Coffer returns every entry with its name, source file, transport (stdio command or HTTP URL), and `enabled` flag, marks the `coffer` entry `is_coffer=true`, and stores nothing — the listing is derived from the file at read time.

### Scenario: remove a direct MCP entry

- **Given** a registered agent with a direct (non-Coffer) MCP entry,
- **When** the user removes that entry (carrying the source file for a `claude_code` agent),
- **Then** the entry is deleted from exactly its source file via an atomic write with a `.bak` of the prior content, an `agent_mcp_entry_removed` audit entry is recorded, and the next listing no longer shows it.

### Scenario: toggle a Codex MCP entry's enabled flag

- **Given** a registered `codex` agent with an enabled direct MCP entry,
- **When** the user disables that entry,
- **Then** the entry's `enabled` field is rewritten in place in `config.toml` (atomic + `.bak`), and the listing reflects the new state.

### Scenario: reject toggling a Claude Code MCP entry

- **Given** a registered `claude_code` agent with a direct MCP entry,
- **When** the user attempts to toggle that entry's enabled state,
- **Then** the request is rejected with `unprocessable_entity` (422) and an explanatory error code — the Claude Code format has no per-entry enabled flag — and no file is touched.

### Scenario: degrade to read-only when MCP config is unparseable

- **Given** a registered agent whose MCP-bearing config file contains invalid JSON/TOML,
- **When** the user lists the agent's MCP entries,
- **Then** Coffer reports a parse-error state naming the file and the parser error instead of failing the request, and rejects entry-level writes against that file until it parses again.

### Scenario: adopt a direct MCP entry into Coffer

- **Given** a registered agent with a direct stdio MCP entry whose name collides with no existing resource,
- **When** the user adopts the entry,
- **Then** Coffer first registers an equivalent `mcp_server` resource (schema-validated, audited), verifies it reads back, then removes the direct entry from the agent's config (atomic + `.bak`), records an `agent_mcp_entry_adopted` audit entry, and the upstream is now served to all agents through the gateway.

### Scenario: reject adoption on resource name conflict

- **Given** an `mcp_server` resource already exists with the same name as a direct entry,
- **When** the user adopts that entry without renaming,
- **Then** the request is rejected with `conflict` (409) carrying a suggested alternative name, no resource is created, and the agent's config is untouched.

### Scenario: require keychain mapping for secret-like env values

- **Given** a direct MCP entry whose environment contains a value under a secret-like key (e.g. `API_TOKEN`),
- **When** the user adopts the entry without supplying a keychain mapping for that key,
- **Then** the request is rejected with a response listing the unresolved keys; when the mapping is supplied, the secret is stored in the OS keychain via the daemon and the created resource config carries a reference, never the value.

### Scenario: adoption failure leaves agent config untouched

- **Given** an adoption attempt that fails after resource registration (e.g. the config-file write is rejected as stale),
- **When** the operation aborts,
- **Then** the created resource is rolled back, the agent's config file is byte-identical to before the attempt, and the failure is reported with a specific error code.

### Scenario: list an agent's plugins with enabled state

- **Given** a registered `codex` agent whose `config.toml` defines `[marketplaces.*]` and `[plugins."<name>@<marketplace>"]` entries with cache directories present,
- **When** the user lists the agent's plugins,
- **Then** Coffer returns every plugin with its `<name>@<marketplace>` id, enabled state, marketplace grouping, and `cache_present=true`, deriving everything from the documented files at read time.

### Scenario: toggle a plugin's enabled state

- **Given** a registered agent with an enabled plugin,
- **When** the user disables it,
- **Then** only the documented location is written — the Codex entry's `enabled` field, or the Claude Code `enabledPlugins` map in `settings.json` — internal plugin state files are byte-identical before and after, and an `agent_plugin_toggled` audit entry is recorded.

### Scenario: uninstall a Codex plugin

- **Given** a registered `codex` agent with an installed plugin,
- **When** the user uninstalls it,
- **Then** the `[plugins."…"]` entry is removed from `config.toml` (atomic + `.bak`), the plugin's cache directory under `~/.codex/plugins/cache/` is deleted, and an `agent_plugin_uninstalled` audit entry is recorded.

### Scenario: uninstall a Claude Code plugin via its CLI

- **Given** a registered `claude_code` agent with an installed plugin and the `claude` CLI on PATH,
- **When** the user uninstalls it,
- **Then** Coffer runs `claude plugin uninstall <id>` (it never hand-writes Claude's internal `installed_plugins.json` / `settings.json`), the request succeeds, and an `agent_plugin_uninstalled` audit entry is recorded.

### Scenario: reject Claude uninstall when its CLI is unavailable

- **Given** a registered `claude_code` agent whose `claude` CLI is not on PATH,
- **When** the user attempts to uninstall a plugin,
- **Then** the request is rejected with `unprocessable_entity` (422) and error code `PLUGIN_UNINSTALL_UNSUPPORTED`, and nothing is written — the listing also hides the in-app uninstall affordance in this case.

### Scenario: flag a plugin whose cache is missing

- **Given** a `codex` agent whose `config.toml` references a plugin with no cache directory on disk,
- **When** the user lists the agent's plugins,
- **Then** that plugin is listed with `cache_present=false` and no repair is attempted.

### Scenario: list a directory config entry's files

- **Given** a registered `claude_code` agent whose `agents/` directory contains Markdown subagent files (possibly nested),
- **When** the user lists that config entry,
- **Then** Coffer returns the entry with `kind=directory` and its files (entry-relative path, size, modified time); a missing directory lists as `exists=false` with no files and is not created by the read.

### Scenario: create a file inside a directory entry

- **Given** a registered `claude_code` agent with an `agents/` directory entry,
- **When** the user writes content to a new `.md` file path inside the entry through the REST API or `coffer agent` CLI (the in-app UI is read-only),
- **Then** the file is created via the atomic-write machinery, an `agent_config_file_written` audit entry is recorded, and the next listing includes it.

### Scenario: delete a file inside a directory entry

- **Given** a directory entry containing a file,
- **When** the user deletes that file through the REST API or `coffer agent` CLI (the in-app UI is read-only),
- **Then** the file is removed with its prior content preserved as `.bak`, an `agent_config_file_deleted` audit entry is recorded, and the next listing no longer shows it.

### Scenario: reject directory file paths outside the entry

- **Given** a registered agent with a directory config entry,
- **When** the user addresses a child path containing `..`, an absolute path, or a non-`.md` extension,
- **Then** the request is rejected before any filesystem access with `not_found` (404) for containment violations or `unprocessable_entity` (422) for a disallowed extension.

### Scenario: reject stale config-file writes

- **Given** a config file (or directory child) read by the user, then modified on disk by another process,
- **When** the user writes back content carrying the fingerprint from the earlier read,
- **Then** the write is rejected with `conflict` (409) and the on-disk file is unchanged; re-reading yields a fresh fingerprint that allows the write.

### Scenario: the native memory scan lists an agent's own per-project stores

- **Given** a registered `claude_code` agent whose `<config_dir>/projects/<slug>/memory` directory holds `.md` fact files (plus a `MEMORY.md` index),
- **When** the user scans the agent's native memory,
- **Then** Coffer returns one store per project with a `project` label and `path` that are the REAL project directory (recovered from the project's session-transcript `cwd`, not the lossy slug), the real `memory_dir`, and an `item_count` of `.md` files excluding `MEMORY.md` (or `1` for a store whose only content is an inline `MEMORY.md`) — read-only, deriving everything from disk and emitting no audit event. An agent type with no native memory layout, or one with no `projects/` directory, returns an empty list.

### Scenario: the native memory scan lists Codex's global memory by project

- **Given** a registered `codex` agent whose `<config_dir>/memories/MEMORY.md` holds `# Task Group` blocks, each with an `applies_to: cwd=…` line routing it to one or more project working directories,
- **When** the user scans the agent's native memory,
- **Then** Coffer parses the single global document into one store row per distinct routed cwd — `project`/`path` the cwd, `item_count` the number of Task Groups routed there, and `memory_dir` the one shared global store — read-only and emitting no audit event; with no `memories/MEMORY.md` the list is empty.

### Scenario: importing a native memory store adopts it into Coffer

- **Given** a registered `claude_code` agent and a native memory store whose project resolves to a real git project (by the decoded slug, or by the `cwd` recorded in a sibling transcript `.jsonl` when the lossy slug does not decode),
- **When** the user imports that store by its `memory_dir`,
- **Then** Coffer reads each fact file (skipping `MEMORY.md`), writes each as a project-scoped Coffer memory fact into the project store's `knowledge/inbox/` lane (a trusted import may write up to the 32768-character domain ceiling), reports `imported`/`skipped` counts with the resolved `store` and `project_path`, and schedules the spec-007 organizer as a BACKGROUND task (`organized=true`) so the dozens of internal-LLM calls never block the request. The memory writes audit through spec 007's existing memory events; the import itself adds no new 004 audit event.

### Scenario: importing a store outside a git project maps to no Coffer store

- **Given** a registered `claude_code` agent and a native memory store whose path cannot be mapped to a Coffer project (not a git project, or an unresolvable lossy slug with no transcript `cwd`),
- **When** the user imports that store,
- **Then** Coffer corrupts no inbox and reports a zero-import result — `imported=0`, `store=null`, `project_path=null`, `organized=false` — rather than an error.

### Scenario: install Coffer's session hook into Cursor

- **Given** a registered `cursor` agent, whose manifest declares `SHELL_COMMAND` injection in the `cursor` hook flavor,
- **When** the user installs Coffer's lifecycle hook,
- **Then** `~/.cursor/hooks.json` gains a flat `sessionStart` command entry — `coffer-hook --agent <name> --dialect cursor --event sessionStart` — under a top-level `version`, with any existing entries for other events untouched.

### Scenario: install Coffer's session-context block into Hermes

- **Given** a registered `hermes` agent, whose manifest declares `INSTRUCTIONS_BLOCK` injection into the allowlisted `soul` file, and a `~/.hermes/SOUL.md` holding the user's own persona,
- **When** the user installs Coffer's session-context injection,
- **Then** `SOUL.md` gains Coffer's marker-fenced block carrying the FR-044 session-context payload (rendered at install time, global scope), the user's own content is preserved byte-identical outside the block, a `.bak` sibling is kept, the install audits `agent_hook_installed`, and `status` reports `installed=true, supported=true` with no `command` (a block carries the payload itself).

### Scenario: uninstalling the Hermes context block is a true inverse

- **Given** a registered `hermes` agent with Coffer's context block installed into a `SOUL.md` that also holds user content,
- **When** the user uninstalls the injection,
- **Then** only Coffer's block (and the separating blank line install added) is removed — the document returns to its pre-install content (trailing-newline normalization aside: install rstrips the tail before appending) — the uninstall audits `agent_hook_uninstalled`, and uninstalling again is a no-op success that writes and audits nothing.

### Scenario: a Coffer-driven turn refreshes the Hermes context block

- **Given** a registered `hermes` agent with the context block installed, and rules/memory that changed since install,
- **When** Coffer drives a hermes chat turn (the provider builds the turn's adapter),
- **Then** the block is re-rendered in place with the fresh FR-044 payload before the agent starts — exactly one block remains, no audit event is emitted for the routine refresh, an agent without an installed block is skipped (nothing is created), and a refresh failure never blocks the turn.

### Scenario: install Coffer's session-context plugin into opencode

- **Given** a registered `opencode` agent, whose manifest declares `PLUGIN_DROP` injection into the allowlisted `plugin` directory,
- **When** the user installs Coffer's session-context injection,
- **Then** `~/.config/opencode/plugin/coffer-session-context.js` is written — a self-contained module that spawns `coffer-hook --agent <name> --dialect raw --event sessionStart` (argv, no shell; hook path and agent name embedded as JSON string literals) and pushes its stdout onto the system prompt via `experimental.chat.system.transform` — the install audits `agent_hook_installed` with the file path and command, `status` reports `installed=true, supported=true` with the command, and reinstalling overwrites Coffer's own file in place (exactly one file).

### Scenario: uninstalling the opencode plugin removes only Coffer's file

- **Given** a registered `opencode` agent with Coffer's plugin installed alongside a user-authored plugin file in the same directory,
- **When** the user uninstalls the injection,
- **Then** only `coffer-session-context.js` is removed (a `.bak` is kept), the user's own plugin files are untouched, the uninstall audits `agent_hook_uninstalled`, and uninstalling again is a no-op success that audits nothing.

### Scenario: install Coffer's MCP into OpenClaw's nested servers map

- **Given** a registered `openclaw` agent whose `openclaw.json` already carries a user MCP server under the nested `mcp.servers` map,
- **When** the user installs Coffer's MCP,
- **Then** a `coffer` command-map entry lands INSIDE `mcp.servers` (the manifest's dotted container key descends one object per dot), the user's server and every unrelated top-level key are preserved, a `.bak` is kept, and status/uninstall read and edit through the same nested path.

### Scenario: install Coffer's session-context plugin package into OpenClaw

- **Given** a registered `openclaw` agent, whose manifest declares `PLUGIN_DROP` injection in the `openclaw` plugin flavor (package dir + fail-closed enable flag),
- **When** the user installs Coffer's session-context injection,
- **Then** `~/.openclaw/extensions/coffer-session-context/` is written with its three files — `package.json` (whose `openclaw.extensions` names the entry), `openclaw.plugin.json` (the `{id, configSchema}` manifest), and `index.js` (`definePluginEntry` + a `before_prompt_build` handler returning `{appendSystemContext}`, spawning `coffer-hook --agent <name> --dialect raw --event sessionStart` as argv) — AND `plugins.entries.coffer-session-context.enabled: true` is set in `openclaw.json` with the user's other config preserved, the install audits `agent_hook_installed` with the package path and command, and reinstalling overwrites Coffer's own package in place.

### Scenario: uninstalling the OpenClaw plugin package removes the extension and its enable flag

- **Given** a registered `openclaw` agent with Coffer's extension installed alongside a user-authored extension and a user's own `plugins.entries` entry,
- **When** the user uninstalls the injection,
- **Then** the whole `extensions/coffer-session-context/` package is removed (no `.bak` — the content is Coffer-rendered and regenerates byte-identically; a leftover backup package would still be scanned by openclaw), Coffer's `plugins.entries` key is removed while the user's extension and entries survive, the uninstall audits `agent_hook_uninstalled`, and uninstalling again is a no-op success that neither writes nor audits.

## Requirements

### Functional Requirements

**Resource model**

- **FR-001**: System MUST register each known local agent as a Resource of kind `agent`, identified by `agent:<name>` per spec 001-mcp-gateway's `<kind>:<name>` convention.
- **FR-002**: System MUST validate agent configuration against a kind-specific schema with fields `type` (enum) and `config_dir` (path, optional absolute-path override; when omitted it defaults to the type's standard location — `~/.claude` for `claude_code`, `~/.codex` for `codex`). Skills are delivered to `<config_dir>/skills`.
- **FR-003**: System MUST support the agent types `claude_code`, `codex`, `opencode`, `hermes`, `cursor`, and `openclaw`; registering any type outside the manifest (e.g. the `claude_desktop` chat app, a Gemini CLI) is rejected with `unprocessable_entity` (422). Per-type behaviour is defined by the capability manifest (`AGENT_DESCRIPTORS`), so adding a type is adding one enum value + one descriptor record (plus, where the product's wire protocol is new, one chat-provider adapter). Each supported type covers both the CLI and the app/IDE form of that product, which share one config directory. A product whose capability for a given facet does not exist upstream declares that facet absent in its descriptor, and the surface MUST hide the corresponding action rather than fail it (per-facet support is the capability matrix below).

**Agent capability matrix (FR-003a).** Per-agent facet support. "✓" = full parity with the two original agents; "N/A" = the capability does not exist upstream — **every N/A MUST cite the upstream doc, flag, or issue that makes it so** ([ADR-042](../../docs/decisions/ADR-042-context-injection-mechanisms.md): three of ADR-040's four uncited N/A cells turned out to be wrong). A "slice" note names a mechanism Coffer has not yet implemented — that is Coffer's gap, not the product's.

The matrix is machine-readable: `AgentOut.capabilities` reports the per-type facet booleans the UI consumes (`plugins`, `transcripts`, `connections`), each derived from the facet's own source of truth (the manifest's `plugins` record, the transcript-layout map, the provider projection targets — never a hardcoded type list). A surface whose facet flag is false renders one uniform, neutral "not supported" state in place of its normal content (no empty table, no raw error), and cross-resource pickers (the connection form's compatible-agents checkboxes) omit incapable agents entirely — the per-agent reason lives on the agent's own detail page, not on other resources' forms (amends ADR-042's presentation rule, 2026-07-10).

The **session context injection** column names the `InjectionMode` the agent's manifest declares. Three mechanisms exist upstream and all three deliver the same payload (`GET /agents/{name}/session-context`): `SHELL_COMMAND` (the agent execs `coffer-hook`), `PLUGIN_DROP` (Coffer drops a JS/TS plugin that spawns it), `INSTRUCTIONS_BLOCK` (Coffer renders it into a marker block in the instructions file).

| Agent | config dir | chat provider (spec 008) | Coffer-MCP inject (FR-019) | session context injection (FR-043/044) | provider projection (spec 011) | native-memory disable (FR-046) | delivery |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `claude_code` | `~/.claude/` | Claude Agent SDK | ✓ `mcpServers` JSON | ✓ `SHELL_COMMAND` — `settings.json` (Start+End) | ✓ `apiKeyHelper` | ✓ `autoMemoryEnabled` | shipped |
| `codex` | `~/.codex/` | `codex app-server` | ✓ `[mcp_servers]` TOML | ✓ `SHELL_COMMAND` — `hooks.json` (Start only) | ✓ `[model_providers]` env_key | ✓ `features.memories` | shipped |
| `opencode` | `~/.config/opencode/` | `opencode run --format json` (JSONL) | ✓ `mcp` typed-local JSON | ✓ `PLUGIN_DROP` — a dropped plugin in the auto-loaded `plugin/` dir (FR-048) spawning `coffer-hook --dialect raw`; injection point `experimental.chat.system.transform` pushes onto the system prompt (probe-verified on 1.14.48; no shell hook exists upstream) | ✓ `provider` block, `apiKey:"{env:COFFER_PROVIDER_KEY}"` | **N/A** — no cross-session native memory feature exists to disable | shipped |
| `hermes` | `~/.hermes/` | `hermes acp` (ACP JSON-RPC over stdio) | ✓ `mcp_servers` YAML | ✓ `INSTRUCTIONS_BLOCK` — a marker block in `SOUL.md`, the only instruction file hermes reads from its home dir (`prompt_builder.load_soul_md`; `AGENTS.md` is cwd-only — both probe-verified on v0.18.0) (FR-047: rendered at install, refreshed before each Coffer-driven turn), because `on_session_start` / `pre_llm_call` are documented but **never invoked** upstream ([hermes-agent#2817](https://github.com/NousResearch/hermes-agent/issues/2817), closed as not planned); only tool hooks fire | ✓ `providers.coffer` + `key_env: COFFER_PROVIDER_KEY` | ✓ `memory.memory_enabled:false` | shipped |
| `cursor` | `~/.cursor/` | `cursor-agent -p --output-format stream-json` (NDJSON) | ✓ `mcpServers` in `mcp.json` | ✓ `SHELL_COMMAND` — `hooks.json` `sessionStart` (own flavor: flat entries, camelCase keys, top-level `version`), output field `additional_context` | **N/A** — `cursor-agent --help` (v2026.02.27) exposes no base-URL flag and `cli-config.json` no endpoint key; custom base URL is IDE-only. Uses its own `cursor-agent login` auth | **N/A** — Memories is an IDE-only Settings→Rules toggle, no CLI flag or config key | shipped |
| `openclaw` | `~/.openclaw/` | `openclaw agent --agent main --session-key <key> -m … --json --local` — ONE JSON blob on stdout, **non-streaming** (Coffer's only such adapter; probe-verified, 2026.6.11). No cwd flag: turns run in openclaw's own workspace, never the conversation's directory ([ADR-044](../../docs/decisions/ADR-044-openclaw-managed-agent.md)) | ✓ nested `mcp.servers` command-map in `openclaw.json` (probe: `openclaw mcp status` lists a hand-written `{command}` entry) | ✓ `PLUGIN_DROP`, `openclaw` flavor — a package dir in `extensions/` + fail-closed `plugins.entries.<id>.enabled: true` (probe: `openclaw config validate` accepts the pair); hook `before_prompt_build` returns `{appendSystemContext}`. `--local` preloads plugins per run → Coffer-driven turns see it immediately; the long-running gateway needs a restart (channel-use caveat) | ✓ `models.providers.coffer` + `apiKey: "${COFFER_PROVIDER_KEY}"` — a missing env var is a startup WARNING only, exit 0 (probe 2026-07-10, overriding the docs' "throws at load"); `models[].{id,name}` both required, `models: []` valid; `agents.defaults.model.primary` set, user `fallbacks` preserved (all probed via `openclaw config validate`) | ✓ `plugins.slots.memory: "none"` (probe: validates; restore removes the key) | this slice |

**Cursor's `sessionStart` headless firing is empirically confirmed** (2026-07-10, authenticated live probe): with Coffer's exact `hooks.json` shape installed, `cursor-agent -p` fired the hook command (marker file written) and the `additional_context` envelope reached the model. This closes the one docs-only claim in ADR-042's Consequences.

`openclaw` — the fourth removed type — was initially excluded as "a peer gateway, not a leaf" ([ADR-040](../../docs/decisions/ADR-040-re-widen-agent-registry.md)); [ADR-044](../../docs/decisions/ADR-044-openclaw-managed-agent.md) reverses that with every matrix cell above verified against a real install. It remains true that openclaw is *also* a gateway (it orchestrates coding CLIs and hosts channels); Coffer manages the leaf-agent surface of it and does not touch its gateway role.

**Discovery (detection = discovery + confirm)**

- **FR-004**: System MUST provide a read-only discovery operation that scans well-known install markers for each supported agent type and reports installed types that are not already registered as **candidates** (each carrying `type`, `display_name`, `config_dir`, `default_skill_dir`, and `suggested_name`). Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add. The daemon MUST NOT auto-register agents on startup.
- **FR-005**: A removed agent MUST re-appear as a discovery candidate on subsequent scans while its install marker is present — a removal is not permanent (it may be accidental). System MUST NOT keep a "suppressed types" list.

**Lifecycle**

- **FR-006**: Users MUST be able to register, list, view, update (config_dir, description), and remove agents. Agents have **no enable/disable concept** — a registered agent is simply present; there is no enabled/disabled state on the agent surface. The agent name is optional at registration — when omitted, System MUST derive a stable per-type default (underscores become hyphens, e.g. `claude_code` → `claude-code`).
- **FR-007**: At registration System MUST auto-create the `<config_dir>/skills` subdirectory, then validate that the resolved `config_dir` exists, is a directory, is writable, and is not a privileged system path before accepting the value. Skills are delivered to `<config_dir>/skills`.
- **FR-008**: System MUST reject registration that would create a duplicate `agent:<name>`, and MUST reject registering more than one agent for the same config directory. `config_dir` is derived from the agent type, so each supported type — and thus each on-disk config directory — may be registered at most once; a second attempt is rejected with `conflict` (409) and nothing is persisted.
- **FR-008a** (Amendment 2026-07-10 — machine × agent scope, [ADR-045](../../docs/decisions/ADR-045-machine-agent-resource-scope.md)): An agent resource's `scope` MUST accept only the machine axis — each entry's value MUST be `"*"`; a scope entry naming specific agents MUST be rejected at validation (422). On a machine outside an agent's scope, System MUST NOT run that agent's post-import reconcile hook, Coffer-MCP projection, or shim/session-context install, and spec 010's import gate MUST NOT be evaluated for that agent on that machine — the doc still upserts into the registry. On a machine WITHIN an agent's scope (including the default `scope=None`), the import gate remains the fallback safety net for a missing `config_dir`.

**Config files**

- **FR-013**: Each supported agent type MUST define a curated allowlist of config files (in its capability-manifest record), each entry carrying a stable `key`, a display name, a resolved absolute path, and a `format` (`json`, `toml`, `yaml`, `markdown`, or `text`). Claude Code → `settings.json`, `settings.local.json`, `~/.claude.json`, `CLAUDE.md` (key `instructions`), and the `agents/` directory entry (FR-034); Codex → `config.toml`, `AGENTS.md` (key `instructions`), and `hooks.json`; Cursor → `cli-config.json` (key `config`), `mcp.json` (key `mcp`), `hooks.json` (key `hooks`), and `AGENTS.md` (key `instructions`); opencode → `opencode.json` (key `opencode`), `AGENTS.md` (key `instructions`), and the `plugin/` directory entry (key `plugin` — opencode auto-loads plugin modules from it; holds Coffer's dropped session-context plugin, FR-048; the directory viewer lists `.md` children only, so the `.js` plugin is managed exclusively through the FR-048 install/uninstall operations); Hermes → `config.yaml` (key `config`) and `SOUL.md` (key `soul`) — SOUL.md is the ONLY instruction file hermes reads from its home dir (its `AGENTS.md` resolution is session-cwd-only, so a `~/.hermes/AGENTS.md` is dead weight and is not allowlisted; both probe-verified on hermes v0.18.0); OpenClaw → `openclaw.json` (key `config` — holds the nested `mcp.servers` block, the `models.providers` projection block, and the `plugins.entries`/`plugins.slots` flags), the workspace instruction files `AGENTS.md` (key `instructions`), `SOUL.md` (key `soul`), `IDENTITY.md` (key `identity`), `USER.md` (key `user`), `TOOLS.md` (key `tools`), and `MEMORY.md` (key `memory` — openclaw's agent-curated memory index, surfaced read-only) — their paths assume the default workspace `~/.openclaw/workspace` (`agents.defaults.workspace` is configurable; a relocated workspace simply lists as absent) — plus the `extensions/` directory entry (key `extensions` — local extension packages; holds Coffer's dropped session-context package, FR-048; the directory viewer lists `.md` children only, so the package's JS/JSON files are managed exclusively through the FR-048 install/uninstall operations). The former `memory` key of Claude Code/Codex is renamed `instructions` — those files are human-authored instructions, distinct from agent-written memory (spec 007's domain).
- **FR-014**: Users MUST be able to list an agent's config files with, for each, its key, display name, path, the containing-folder absolute path (`folder_path`), format, and existence (plus size and modified time when the file exists). The `path`/`folder_path` pair feeds the read-only UI's open-in-external-editor / reveal-in-file-manager affordances (FR-038).
- **FR-015**: Users MUST be able to read the content of any allowlisted config file. A file that does not exist reads as empty content with `exists=false` and is not created by the read.
- **FR-016**: The system MUST expose a programmatic write (save) for the content of any allowlisted config file through the REST API and the `coffer agent` CLI; the in-app UI is read-only and does not write config-file content. The content MUST be validated against the file's `format` before any write; malformed `json`/`toml` MUST be rejected (`unprocessable_entity`, 422) and the on-disk file left unchanged. `markdown`/`text` files accept any content.
- **FR-017**: Writes MUST be atomic (temp file + rename) and MUST keep a `.bak` copy of the prior content so a bad edit is recoverable; each successful write MUST record an `agent_config_file_written` audit entry. The Coffer-MCP install/uninstall operations (FR-022) reuse the same atomic-write + `.bak` machinery.
- **FR-018**: Config-file read and write MUST be addressable only by allowlisted `key` (never by caller-supplied path); an unknown key returns `not_found` (404) and performs no filesystem access.

**Coffer MCP install**

- **FR-019**: Users MUST be able to install Coffer's own MCP server into an agent in one action. The install writes a `coffer` stdio MCP-server entry into the agent's MCP config, using the shape declared by that agent's manifest `McpInjectionSpec` — `mcpServers.coffer` in `~/.claude.json` (`claude_code`); `[mcp_servers.coffer]` in `~/.codex/config.toml` (`codex`). `command` is the absolute path of the `coffer-mcp-shim` binary (resolved on `PATH`, then the running interpreter's scripts directory — so a venv-installed shim is found even when the daemon's `PATH` lacks the venv — then the bundled binary; a `COFFER_MCP_SHIM_PATH` environment override takes precedence over all). The install additionally writes `--agent <name>` (the agent's registry name) as an argument of the shim invocation — in the entry shape's argument slot (`args` for command-map entries, appended to the `command` array for typed-array entries) — so the gateway can attribute the session to this agent for agent-axis scope enforcement (Amendment 2026-07-10, [ADR-045](../../docs/decisions/ADR-045-machine-agent-resource-scope.md); same pattern as FR-043's hook install). If the shim cannot be resolved, install is rejected and nothing is written.
- **FR-020**: Install MUST be idempotent — re-installing updates the existing `coffer` entry in place and never creates a duplicate. System MUST expose a status operation reporting whether Coffer's MCP is currently installed for the agent.
- **FR-021**: Users MUST be able to uninstall Coffer's MCP, removing the `coffer` entry from the agent's MCP config. Uninstalling when not installed is a no-op success.
- **FR-022**: Install and uninstall MUST reuse the atomic-write + `.bak` machinery from FR-017 and record an audit entry (`agent_mcp_installed` / `agent_mcp_uninstalled`).

**Agent MCP entries (workspace amendment)**

- **FR-025**: System MUST parse and list the MCP server entries configured in the agent's own files — for `claude_code` from both `~/.claude.json` `mcpServers` and `settings.json` `mcpServers` (each entry labelled with its source file); for `codex` from `config.toml` `[mcp_servers.*]`. Each entry carries name, source, transport (stdio command or HTTP URL), the `enabled` flag where the format defines one (Codex), `is_coffer` for Coffer's own gateway entry, and `matches_resource` naming an equivalent registered `mcp_server` resource when one exists. Entries are derived at read time, never stored.
- **FR-026**: Users MUST be able to remove a direct MCP entry. Removal edits only the entry's source file (disambiguated by the caller for `claude_code` when both files carry the name), reuses the FR-017 atomic-write + `.bak` machinery, and records an `agent_mcp_entry_removed` audit entry. The `coffer` entry is not removable through this operation — it is managed by FR-019/FR-021.
- **FR-027**: Users MUST be able to toggle a Codex entry's `enabled` flag in place. For `claude_code`, whose format has no per-entry flag, the toggle is rejected with `unprocessable_entity` (422) and an explanatory error code.
- **FR-028**: Users MUST be able to adopt a direct MCP entry into Coffer. Adoption (a) registers the entry as an `mcp_server` resource through the standard resource flow (schema validation + audit), (b) verifies the resource reads back, then (c) removes the source entry per FR-026 — strictly in that order. Any failure stops the operation, rolls back a created resource, and leaves the agent's config byte-identical; audited as `agent_mcp_entry_adopted` on success. A name collision with an existing resource is rejected with `conflict` (409) carrying a suggested alternative; an entry equivalent to an existing resource is reported via `matches_resource` so the user can remove the duplicate instead. The `coffer` entry is never adoptable.
- **FR-029**: Adoption MUST NOT persist secret values into resource config. When an entry's environment carries values under secret-like keys (`TOKEN`, `KEY`, `SECRET`, `PASSWORD` patterns), the adopt request MUST supply a keychain mapping for each flagged key or be rejected with the unresolved keys listed. Mapped values are stored in the OS keychain through the daemon (per the credentials invariant); the resource config carries references only.
- **FR-030**: When an agent config file cannot be parsed, the affected facet MUST degrade to an explicit parse-error state (file path + parser error) without failing the surrounding view, and entry-level writes against that file MUST be rejected until it parses again.

**Plugins (workspace amendment)**

- **FR-031**: System MUST list an agent's installed plugins with enabled state, grouped by marketplace. For `codex` the listing derives from `config.toml` (`[plugins."<name>@<marketplace>"]`, `[marketplaces.*]`) plus presence of the documented cache directory `~/.codex/plugins/cache/<marketplace>/<plugin>/`; for `claude_code` the inventory derives read-only from `~/.claude/plugins/installed_plugins.json` and `known_marketplaces.json`, with enabled state from `settings.json` `enabledPlugins`. A plugin configured without its cache is flagged `cache_present=false`; no repair is attempted.
- **FR-032**: Users MUST be able to enable/disable a plugin. Writes touch only the documented locations — the Codex entry's `enabled` field; the Claude Code `enabledPlugins` map in `settings.json` — and MUST never write the agents' internal state files. Audited as `agent_plugin_toggled`.
- **FR-033**: Users MUST be able to uninstall a plugin, by a per-agent strategy. For `codex` the `[plugins."…"]` entry is removed from `config.toml` and the plugin's cache directory is deleted. For `claude_code` Coffer delegates to `claude plugin uninstall <id>` — it never hand-writes Claude's internal `installed_plugins.json`; the CLI owns that state. When the `claude` CLI is not on PATH the operation is rejected with `unprocessable_entity` (422) / `PLUGIN_UNINSTALL_UNSUPPORTED` and the in-app uninstall affordance is hidden (the listing reports `can_uninstall=false`); a CLI error surfaces as `PLUGIN_UNINSTALL_FAILED` (422). Both successful paths are audited as `agent_plugin_uninstalled`. Plugin installation and marketplace management are not provided by Coffer; both remain with the agent's own tooling.

**Directory config entries (workspace amendment)**

- **FR-034**: A config-file allowlist entry MAY be a **directory entry** (`kind=directory`): it resolves to a directory and lists its files (entry-relative path, size, modified time) instead of carrying content. The directory entry for Claude Code is `agents/` (one Markdown file per personal subagent, nested paths allowed). A missing directory lists as `exists=false` with no files; the read never creates it.
- **FR-035**: Users MUST be able to read individual files inside a directory entry; this read is available to the UI's read-only viewer. Write (create-on-write) and delete of individual files are programmatic, available through the REST API and the `coffer agent` CLI. Child paths are validated server-side before any filesystem access: they MUST resolve inside the entry's directory (no `..`, no absolute paths, no symlink escape) and carry the `.md` extension. Writes reuse FR-017's machinery; deletion preserves the prior content as `.bak`. Audited as `agent_config_file_written` / `agent_config_file_deleted`.
- **FR-036**: Config-file reads (single files and directory children) MUST return a content fingerprint; writes MUST carry it back and are rejected with `conflict` (409) when the on-disk content changed since the read, leaving the file untouched.
- **FR-037**: When an instructions file contains a managed block defined by another feature — the spec-007 memory-projection block — the read-only viewer MUST annotate that the block is owned by that feature. Each block uses its own distinct markers and is rewritten independently; the marker format is owned by the defining feature.

**Native memory (workspace amendment)**

These two requirements extend the registry to the coding agent's OWN native per-project memory — distinct from the `instructions` config files of FR-013 (CLAUDE.md / AGENTS.md are human-authored instructions; this is the agent's self-written memory store). The transform (organizing imported facts into Coffer topic documents) is owned by spec 007's organizer; this spec only reads the agent's store and hands its facts to that organizer.

- **FR-040**: System MUST expose a read-only **native-memory scan** that lists an agent type's own native memory stores. Two layouts are supported. For `claude_code` the stores are per-project at `<config_dir>/projects/<slug>/memory/`: one row per project that has a `memory/` dir, with an `item_count` of `.md` fact files excluding `MEMORY.md` — or `1` when there are no fact files but `MEMORY.md` holds inline content (an older / hand-written hub doc), since that inline doc is itself the importable entry. The `project` label and `path` are the REAL project directory, recovered from the project's session transcript `cwd` (the slug encoding is lossy — `/`, `.`, `_` all collapse to `-` — so the path cannot be reliably reconstructed from the slug; a lossy slug decode is only a last-resort fallback). For `codex` the store is a single GLOBAL task-grouped document at `<config_dir>/memories/MEMORY.md`, where each `# Task Group` block carries an `applies_to: cwd=…` line routing it to one or more project working directories; the scan parses it into one row per distinct routed cwd, with `item_count` the number of Task Groups routed there and `path` the cwd (`memory_dir` is the one shared global store for every row). An agent type with no native memory layout, an absent `projects/` dir, or an absent `memories/MEMORY.md`, all return an empty list. The scan is read-only, derives everything from disk at read time (nothing stored), and — consistent with FR-011's "workspace listings are read-only; none emits an audit event" — emits NO audit event. It never writes the agent's store.
- **FR-041**: Users MUST be able to **import (adopt)** one native memory store into Coffer. For `claude_code`, given a store's `memory_dir`, System reads its fact files (skipping `MEMORY.md`, or parsing an inline `MEMORY.md` when there are no fact files), resolves the REAL project path — the decoded slug when it exists on disk, else the `cwd` recorded in a sibling transcript `.jsonl` (the slug decode is lossy). For `codex`, whose global store is shared by every row, the request also carries the chosen row's `project_path`, and System imports only the Task-Group blocks routed to that cwd. Either way it writes each entry as a project-scoped Coffer memory fact into the project store's `knowledge/inbox/` lane (like a batch of `remember`s; a trusted import MAY write a note up to the 32768-character domain ceiling). It then triggers spec 007's organizer as a BACKGROUND task, because a bulk import is dozens of sequential internal-LLM calls and MUST NOT block the request. The result reports `imported`, `skipped`, `store` (null when the project cannot be mapped to a Coffer store), `project_path`, and `organized`. A store outside any git project (no mappable Coffer project) yields `imported=0`, `store=null`, `project_path=null`, `organized=false` — it corrupts no inbox and is not an error. The import's memory writes audit through spec 007's existing memory events; the import adds no NEW 004 audit event.

- **FR-043**: Users MUST be able to **install Coffer's lifecycle hooks** into an agent in one action, and to uninstall them and query their status. The install writes a `coffer-hook` command entry into the agent's hooks file declared by that agent's manifest `ContextInjectionSpec` — `settings.json` for `claude_code`, `hooks.json` for `codex` and `cursor` — with the command being the absolute path of the `coffer-hook` binary (resolved like the shim: `COFFER_HOOK_PATH` override → `PATH` → the interpreter's scripts dir → bundled) plus `--agent <name>` args, since the external hook payload does not carry Coffer's agent identity. The on-disk entry shape and the event-key spelling follow the spec's `HookFlavor`: `claude` (matcher groups, PascalCase keys) for `claude_code`/`codex`, `cursor` (flat command entries, camelCase keys, top-level `version` set on create and never rewritten). A non-`claude` flavor additionally bakes `--dialect <flavor> --event <key>` into the command, because Cursor keys `hooks.json` by event but does not contractually name the event on stdin. `claude_code` installs SessionStart **and** SessionEnd; `codex` and `cursor` install SessionStart **only** (neither has a usable session-end event). Install MUST be idempotent (it replaces Coffer's own entry in place, recognised by the `coffer-hook` basename, and never touches user-authored hooks); uninstall removes only Coffer's entries; Cursor's top-level `version` survives beside any other content, but a `version` Coffer itself wrote into a file that had none MUST be removed when nothing else remains, so uninstall is a true inverse of install. Recognition of Coffer's own entry MUST tolerate an unparseable user-authored command (an unbalanced quote is not Coffer's — it shell-quotes everything it writes) rather than failing the request. If the binary cannot be resolved, or the agent type declares no context injection, install is rejected (`HOOK_INSTALL_UNSUPPORTED`, 422) and nothing is written; `status` reports `installed=false` for such an agent rather than erroring. All three `InjectionMode`s are implemented and flow through the same install/uninstall/status operations: `INSTRUCTIONS_BLOCK` takes the FR-047 path, `PLUGIN_DROP` the FR-048 path. Both events audit (`agent_hook_installed` / `agent_hook_uninstalled`).
- **FR-044**: On SessionStart, the installed hook MUST be able to fetch a **rules bundle** to inject as additional context: System resolves the session's recall scopes from its `cwd` (project, if a git project, then global), concatenates each store's rules (project first, then global), and ALWAYS appends two seeded built-in rules — a *resume* rule (steering the agent to call `coffer__resume()` when the user asks to continue prior work) and a *soft-steer* rule (preferring `coffer__remember` / `coffer__recall` over the agent's native memory). The bundle is runtime-only (nothing is written to the agent's files) and bounded to ≤10000 characters; when no user rules exist anywhere it still returns the seeded rules. Exposed as `GET /agents/{name}/session-context?cwd=` — **the single payload source shared by all three `InjectionMode` mechanisms**. `coffer-hook` wraps it in the envelope its `--dialect` selects (`hookSpecificOutput.additionalContext` for `claude`; a top-level `additional_context` for `cursor`), and MUST tolerate an absent or unparseable stdin payload — falling back to `--event` for the event and the hook process's own working directory (inherited from the agent) for the scope — so an agent whose payload schema is not contractual still receives the injection. When `--event` names a SessionStart the payload MUST NOT be read at all: `stdin` has no timeout, and an agent that leaves it open would otherwise stall on the hook. When the working directory cannot be determined, `cwd` MUST be **omitted** rather than sent empty — the daemon resolves an empty `cwd` against its own long-lived working directory, whereas an absent one means global scope.
- **FR-045** (Slice 6): On SessionEnd (Claude Code only — Codex has no session-end event and degrades to the FR-046 catch-up sweep), the installed hook MUST be able to trigger a **single-session distill** into the journal lane, reusing the FR-046 idempotency ledger so a session is never double-distilled by the sweep. The operation is idempotent and always succeeds (2xx): a no-internal-engine, unknown-session, already-distilled, or not-a-git-project session is a tolerated no-op. Exposed as `POST /agents/{name}/sessions/{session_id}/end`.
- **FR-046** (Slice 6): Users MUST be able to opt into **disabling an agent's native write-side memory** via `disable_native_memory` (default false) on the agent. Toggling it drives the persisted field AND the on-disk transform in lockstep — Claude Code sets `autoMemoryEnabled=false` in `settings.json`; Codex sets `features.memories=false` + `memories.generate_memories=false` in `config.toml`; Hermes sets `memory.memory_enabled=false` + `memory.user_profile_enabled=false` in `config.yaml`; OpenClaw sets `plugins.slots.memory: "none"` in `openclaw.json` (emptying the memory plugin slot — probe-validated, [ADR-044](../../docs/decisions/ADR-044-openclaw-managed-agent.md)) — so Coffer becomes the single shared memory store. Toggling it back to false restores the agent's native memory (removing the keys Coffer added). **OpenClaw caveat**: the slot key carries a user-chosen VALUE (a memory plugin id), unlike the other agents' boolean toggles — restore removes the key, which lands on openclaw's DEFAULT memory plugin (`memory-core`); a user who had selected a non-default plugin (e.g. `memory-lancedb`) re-selects it by hand. Coffer does not snapshot the prior selection. It does not stop the agent reading its instruction files (CLAUDE.md / AGENTS.md). Both transitions audit (`agent_native_memory_disabled` / `agent_native_memory_restored`).
- **FR-047**: For an agent whose manifest declares `INSTRUCTIONS_BLOCK` injection (`hermes` — no working upstream hook, [ADR-042](../../docs/decisions/ADR-042-context-injection-mechanisms.md)), the FR-043 install/uninstall/status operations MUST act on a **marker-fenced block** in the instructions file the manifest's `config_key` names, instead of a hooks entry. That file MUST be one the agent actually injects globally at session start — for hermes the `soul` key (`~/.hermes/SOUL.md`, identity slot #1 on every platform including ACP); its `AGENTS.md` is resolved against the session cwd only and is NOT a valid target (probe-verified, v0.18.0). Install renders the FR-044 payload (fetched at **global scope** — the block is not per-project) between `<!-- coffer:session-context:start -->` / `<!-- coffer:session-context:end -->` fences, replacing Coffer's existing block in place or appending after the user's content; user content outside the fences is never touched, and writes go through the atomic store (`.bak`). Uninstall removes only the balanced block and inverts install up to trailing-newline normalization; fence pairing MUST bind each end fence to the closest preceding start fence (a span can then never swallow user text between an orphaned fence and the real block), an unbalanced fence (user damage) is treated as *not Coffer's* — so install appends a fresh balanced block and uninstall touches nothing — and fence markers occurring inside the payload MUST be neutralized before rendering so the payload cannot break out of the block. `status` reports block presence with `command=null`. Because the block is **static between writes**, System MUST re-render it (best-effort, never blocking or failing the turn, no audit event) before each Coffer-driven chat turn for that agent type; agents without an installed block are skipped. The install/uninstall actions audit the same `agent_hook_installed` / `agent_hook_uninstalled` events as FR-043.
- **FR-048**: For an agent whose manifest declares `PLUGIN_DROP` injection (`opencode`, `openclaw` — no shell hook; the in-process JS plugin API is the injection point, [ADR-042](../../docs/decisions/ADR-042-context-injection-mechanisms.md)), the FR-043 install/uninstall/status operations MUST act on **Coffer's own plugin** inside the agent's plugin directory (the manifest's `config_key` names the allowlisted DIRECTORY entry), in the on-disk shape the manifest's **`PluginFlavor`** declares. For the `opencode` flavor that is one flat file (`coffer-session-context.js` in the auto-loaded `plugin/` dir) whose module pushes the bundle onto the system prompt via `experimental.chat.system.transform`. For the `openclaw` flavor ([ADR-044](../../docs/decisions/ADR-044-openclaw-managed-agent.md)) it is a **package directory** `extensions/coffer-session-context/` — `package.json` (its `openclaw.extensions` names the entry), `openclaw.plugin.json` (`{id, configSchema}`), and `index.js` (`definePluginEntry` whose `before_prompt_build` handler returns `{appendSystemContext}`) — PLUS, because non-bundled openclaw plugins are **fail-closed**, the `plugins.entries.coffer-session-context.enabled: true` flag in the config file the manifest's `plugin_enable_config_key` names; `--local` embedded runs preload the plugin registry per run so Coffer-driven turns see the extension immediately, while the long-running gateway picks it up only after a restart (documented caveat for channel-driven openclaw use). Both flavors spawn the same `coffer-hook` binary with `--dialect raw --event sessionStart` (argv spawn, no shell — the hook path and agent name are embedded as JSON string literals, so any path is safe), cached per session and failure-silent (a broken daemon never breaks the agent; a bounded timeout guards the spawn). Unlike FR-047 this mode is **dynamic** — the plugin fetches the bundle live, so no pre-turn refresh machinery exists for it. Install MUST be idempotent (Coffer's named file/package is overwritten in place) and MUST NOT touch any other file in the plugin directory; uninstall removes only Coffer's file (keeping a `.bak`) or package-plus-enable-flag (no `.bak` for the package — its content is Coffer-rendered and regenerates byte-identically, and a leftover backup package would still be scanned by openclaw) and is a no-op success when absent; `status` reports presence of the plugin with the spawn command. The `raw` dialect prints the bundle text with no envelope and never reads stdin. Audits as FR-043.

**Surfaces**

- **FR-009**: Every management operation — register/list/view/update/remove, config-file list/read/write (including directory children), Coffer-MCP install/uninstall/status, MCP entry list/remove/toggle/adopt, plugin list/toggle/uninstall, native-memory scan/import (FR-040/FR-041) — MUST be available through (a) the REST API and (b) the `coffer agent ...` CLI. The native-memory commands are `coffer agent native-memory <name>` (read, `--json`) and `coffer agent import-native-memory <name> <memory_dir>` (adopt; `--project-path` selects the cwd for Codex's shared global store). The desktop Agents page MUST expose all of these EXCEPT config-file content writes (single files and directory children): in the UI, config files and directory children are **read-only** with open-in-external-editor / reveal-in-file-manager affordances (FR-038), while the REST API and CLI keep the programmatic write/create/delete path. The agent Memory tab shows the Coffer-managed memory link plus this native table **read-only** (open / reveal per FR-038), with an import button that adopts a store (FR-041).
- **FR-010**: The CLI MUST support `--json` for machine-readable output on every read operation.
- **FR-038**: For each config file (and each directory-entry child) the UI MUST offer **open-in-external-editor** and **reveal-in-file-manager** actions on the file, using the `path` from FR-014/FR-015. Open and reveal perform the real OS action on **both** surfaces: the packaged desktop app (Tauri) uses the OS opener directly; the web uses the daemon filesystem-action endpoints (FR-039), since the loopback daemon is always on the user's own machine (ADR-033). There is no copy-path fallback. The editor used for open-in-external-editor references the user's "preferred external editor" preference defined by spec 002-ui-shell (not re-specified here).

**Observability**

- **FR-011**: System MUST record an audit entry for every lifecycle event: agent created, updated, removed; config file written/deleted (`agent_config_file_written` / `agent_config_file_deleted`); Coffer MCP installed/uninstalled; MCP entry removed/adopted (`agent_mcp_entry_removed` / `agent_mcp_entry_adopted`); plugin toggled/uninstalled (`agent_plugin_toggled` / `agent_plugin_uninstalled`). (Agents have no enable/disable concept; discovery and all workspace listings — including the native-memory scan, FR-040 — are read-only and emit no audit event. The native-memory import, FR-041, adds no NEW 004 audit event: each imported fact audits through spec 007's existing memory write events.)
- **FR-012**: System MUST expose a read-only discovery operation listing installed-but-unregistered agents as candidates, available from the REST API (`GET /api/v1/agents/candidates`), the `coffer agent detect` CLI, and the desktop Agents page.

**Config-directory picker**

- **FR-023**: When choosing a custom `config_dir`, the desktop app MUST offer a folder picker rather than requiring the user to type a path. In the packaged desktop app it MUST use the OS-native directory dialog; on the web it MUST use the daemon native directory dialog (FR-042), falling back to the daemon-backed folder browser (FR-024) only when the host has no native dialog tool. Both yield an absolute path that is then validated per FR-007 before registration.
- **FR-024**: System MUST expose a read-only filesystem-browse operation (`GET /api/v1/fs/browse`) that, given a directory path (defaulting to the user's home), returns that path, its parent, and its immediate subdirectories. It MUST NOT return file contents and MUST be guarded by the same loopback + token auth as all other daemon routes.
- **FR-042**: System MUST expose native OS picker dialogs through the loopback daemon (ADR-036) so the web surface opens the host's real dialog instead of requiring a typed path: `POST /api/v1/fs/pick-folder` (choose a directory), `POST /api/v1/fs/pick-file` (choose an existing file to open), and `POST /api/v1/fs/save-file` (choose a destination, with an optional `suggested_name`). Each opens the host's native dialog (macOS `osascript`; Linux `zenity`/`kdialog`), invoked with a fixed argument vector (no shell interpolation), and returns `{ available, path }`: `available=false` when the host has no native dialog tool, `available=true` with `path=null` on cancel, otherwise the chosen absolute path. When `available=false` the caller degrades — folder picking to the in-app browser (FR-024), file picking and saving to a typed path. All three create nothing and are guarded by the same loopback + token auth as every daemon route.

**Filesystem open/reveal**

- **FR-039**: System MUST expose filesystem-action operations that let the web surface perform real open/reveal (FR-038) through the loopback daemon, which is always co-located with the web client on the user's machine (ADR-033): `POST /api/v1/fs/open` (open an existing absolute path in an application — a `with` editor preference, or the OS default) and `POST /api/v1/fs/reveal` (select / reveal an existing absolute path in the OS file manager). Both MUST validate the path is absolute and exists before acting, MUST invoke the OS launcher with a fixed argument vector (no shell interpolation), MUST create nothing, and MUST be guarded by the same loopback + token auth as all other daemon routes. A non-absolute or non-existent path is rejected (`FS_PATH_NOT_OPENABLE`, 400). Where a platform has no portable "select the file" primitive (Linux), reveal degrades to opening the containing folder. System MUST also expose `GET /api/v1/fs/editors`, which enumerates common GUI editors detected as installed on the host (macOS app-bundle names for `open -a`; Linux/Windows commands on PATH) so the spec 002-ui-shell preferred-editor setting can offer a picker rather than a blind text field. It returns each editor's display label and the launcher `value` accepted by `/fs/open`'s `with`, reads nothing but app presence, and is guarded by the same loopback + token auth.

### Key Entities

- **Agent**: A Resource of kind `agent`. Represents one locally-installed AI agent. Config: `type` (supported enum), `config_dir` (optional absolute-path override; defaults to the type's standard location). Skills are delivered to `<config_dir>/skills`. Identified by `agent:<name>`. Carries a framework-level `scope` restricted to the machine axis (`"*"`-only entry values) restricting which machines the agent is expected to exist on (Amendment 2026-07-10 — machine × agent scope, ADR-045; see "Agent machine scope").
- **Agent Type**: An enum value identifying a known agent product (`claude_code`, `codex`, `opencode`, `hermes`, `cursor`, `openclaw`). Each value maps to a record in the **capability manifest** (`AGENT_DESCRIPTORS`) carrying its default `config_dir`, display name, install-marker (for discovery), curated **config-file allowlist**, **MCP injection shape**, and the optional context-injection / provider-projection / native-memory facets — a facet a product lacks upstream is left unset (the capability matrix under FR-003a), and surfaces hide the corresponding action. Where a facet is absent because *Coffer* has not implemented the product's mechanism (rather than the product lacking one), surfaces MUST say so rather than presenting it as an upstream limitation.
- **Context Injection Spec**: The manifest facet describing how Coffer's session context (rules + memory) reaches one agent's model. Carries an `InjectionMode` (`SHELL_COMMAND` / `PLUGIN_DROP` / `INSTRUCTIONS_BLOCK`), the allowlisted config `key` + `format` it writes, the lifecycle `events` it installs (empty for `INSTRUCTIONS_BLOCK` — a block is not event-driven), a `HookFlavor` selecting both the on-disk entry shape and the stdout envelope `coffer-hook` prints (meaningful for `SHELL_COMMAND` only), and — for `PLUGIN_DROP` only — a `PluginFlavor` selecting the plugin's on-disk shape (`opencode`: one flat auto-loaded file; `openclaw`: a package directory plus the fail-closed enable flag in the file `plugin_enable_config_key` names). All three modes are implemented: `SHELL_COMMAND` (FR-043), `INSTRUCTIONS_BLOCK` (FR-047), `PLUGIN_DROP` (FR-048). See [ADR-042](../../docs/decisions/ADR-042-context-injection-mechanisms.md).
- **Agent Candidate**: A discovered installed-but-unregistered agent — `type`, `display_name`, `config_dir` (the type's default config directory), `default_skill_dir`, and `suggested_name`. Derived at scan time, never stored; the user confirms a candidate to register it.
- **Config File**: A curated, allowlisted file belonging to an agent type, identified by a stable `key`. Carries a display name, a resolved absolute path, its containing-folder absolute path (`folder_path`), a `format` (`json` / `toml` / `markdown` / `text`), and (when present) size and modified time. Surfaced read-only in the UI (view its content, open it / its folder in an external editor); read and programmatically written by key (REST/CLI), never by arbitrary path. Not persisted in SQLite — the file on disk is the source of truth.
- **Coffer MCP Install Status**: Derived (not stored) state for an agent: whether a `coffer` MCP-server entry is present in that agent's MCP config file.
- **Agent MCP Entry**: A derived (never stored) view of one MCP server configured in the agent's own files — name, source file, transport, `enabled` (Codex), `is_coffer`, `matches_resource`. The file is the source of truth; Coffer reads, edits, removes, or adopts entries but keeps no copy.
- **Agent Plugin**: A derived (never stored) view of one installed plugin — id (`<name>@<marketplace>`), marketplace, enabled state, `cache_present`. Enabled state lives in each agent's documented config surface; the inventory files of Claude Code are read-only inputs.
- **Directory Config Entry**: An allowlisted config entry that resolves to a directory of files rather than a single file. Children are addressed by validated entry-relative paths; the directory on disk is the source of truth.
- **Native Memory Store**: A derived (never stored) view of one of the coding agent's OWN native memory stores — for `claude_code` a per-project directory (`<config_dir>/projects/<slug>/memory`), for `codex` one routed-cwd slice of the single global task-grouped `<config_dir>/memories/MEMORY.md`. Carries a `project` label and `path` (the REAL project cwd), the real `memory_dir`, and an `item_count` (Claude Code fact files / an inline `MEMORY.md` / Codex Task Groups routed to the cwd). Read-only; the agent's store is never written. Adopting one (FR-041) imports its entries into the matching Coffer project memory's `knowledge/inbox/` lane and hands them to spec 007's organizer.

## Success Criteria

### Measurable Outcomes

- **SC-001**: On a machine with at least two supported agent install paths present, running discovery surfaces exactly those agents as candidates, and the user adds them with a single confirm each — no typing of type identifiers or paths.
- **SC-002**: From a fresh install, a user can register an additional agent with a custom `config_dir` and see it in `coffer agent list --json` within 60 seconds, without consulting documentation more than once.
- **SC-003**: Every Acceptance Scenario in this spec is covered by at least one test marked `acceptance(spec="004-agent-registry", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-004**: The full `make verify` suite passes locally and in CI; `make verify-all` (adding e2e) passes on macOS and Linux.
- **SC-005**: No `config_dir` value ever permits writing outside the directory itself (path-traversal check); validated by a dedicated security test.
- **SC-006**: A user can open an agent's `settings.json` (Claude Code) or `config.toml` (Codex) read-only in Coffer and, from the desktop app, open it in their external editor; the programmatic save (REST/CLI) still validates the content (a malformed save is rejected with the file left unchanged) and keeps a `.bak` of the prior version on a successful save.
- **SC-007**: A user can install Coffer's MCP into a freshly-registered agent in one click and, after restarting that agent, the agent lists Coffer's aggregated tools; re-installing never duplicates the entry, and uninstall removes it.
- **SC-008**: The MCP tab lists exactly the entries present in the agent's real config files, and adopting a direct entry completes the full round trip — resource registered, gateway serving it, direct entry gone — in one user action plus at most one confirmation.
- **SC-009**: Plugin toggles change only the documented config surface: a test asserts the agents' internal state files are byte-identical before and after every toggle.
- **SC-010**: No directory-entry operation can read or write a path outside its entry's directory; validated by dedicated security tests covering `..` traversal, absolute paths, symlink escape, and disallowed extensions.

## Assumptions

- The user runs Coffer on their own machine; there is no multi-tenant or remote-access requirement.
- Multiple agent types are wired in the capability manifest (`AGENT_DESCRIPTORS`) — `claude_code`, `codex`, `opencode`, `hermes`, `cursor`, and `openclaw` — each one `AgentType` enum value plus one record (install marker, config-file allowlist, MCP injection shape, and any optional facets it supports). Adding a further product is the same one-record change, plus a chat-provider adapter when its wire protocol is new and, where a facet does not exist upstream, leaving that facet unset (the capability matrix, FR-003a). The re-widening from the earlier two-type state is [ADR-040](../../docs/decisions/ADR-040-re-widen-agent-registry.md).
- Each supported agent's CLI and app/IDE form read one shared config directory (`~/.claude/` and `~/.codex/`), so Coffer manages one config set per agent.
- Config files are surfaced as raw text the user can view read-only; editing happens in the user's external editor (opened from the viewer), while the programmatic write path (REST/CLI) keeps the validate + atomic-write + `.bak` safety net. The read-only viewer plus open-in-external-editor is the escape hatch for the long tail; recurring structured needs graduate into facets (MCP entries, plugins) per the workspace amendment. The credential/state file `~/.codex/auth.json` is intentionally excluded from the allowlist.
- The agents' internal state files (`~/.claude.json` beyond its `mcpServers` map, `~/.claude/plugins/*.json`, Codex's `[marketplaces.*]` / `[hooks.state.*]` / `[projects.*]` tables) are read as inputs where needed and never written by the workspace facets; the documented configuration surfaces verified against each vendor's docs are the only write targets. In practice (verified on a real machine) user-scope Claude Code MCP servers live in `~/.claude.json` `mcpServers` and may also appear in `settings.json` `mcpServers` — both are parsed.
- Workspace facets follow the ingest → hub → deliver principle: shareable content found in an agent's workspace is adoptable into Coffer's hub (MCP gateway here; the master skill store via spec 005's companion amendment) rather than managed as per-agent one-offs. Cross-machine sharing of the hub itself is a future spec (and constitutional amendment); these facets are designed so their state serializes to declarative manifests when that lands.
- Agents store their skill libraries on the local filesystem under `<config_dir>/skills`. Web-only agents (e.g., claude.ai) are out of scope for v1 and require a future spec to add API-based sync.
- The kind-agnostic Resource framework, audit log, and `<kind>:<name>` identity scheme defined by spec 001-mcp-gateway are in place.
- The application shell from spec 002-ui-shell — sidebar IA, layout, routing skeleton, and design system — is in place. The desktop Agents page renders within that shell at `/agents` as a **dedicated top-level nav entry** (a sibling of the Resources and System groups, **not** nested under Resources — agents are consumers of vault assets, not assets themselves). Agent resources do not appear in the kind-agnostic resources/MCP browser, which lists only kinds that register a resource-card UI.
- Skill bindings (i.e., the relationship between an agent and a particular skill) are introduced and managed by spec 005-skill-manager; spec 004 does not define skill operations beyond exposing an `on_delete` hook for cascade cleanup.
