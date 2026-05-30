# Feature Specification: Agent Registry

**Feature Branch**: `feature/004-agent-registry`
**Created**: 2026-05-22
**Status**: Draft
**Input**: User description: "Manage which locally-installed AI agents Coffer knows about, so later features (skills, memory, knowledge bases) can deliver assets to them. Each agent is a Resource of kind `agent` in the kind-agnostic Resource framework introduced by spec 001-mcp-gateway. v1 supports two agent types: Claude Code and OpenAI Codex — each covering both its CLI and its desktop/IDE form, which share one on-disk config. Beyond registering agents, the user can view and edit each agent's known config files and install Coffer's own MCP server into an agent with one click."

> **Note on agent types.** v1 covers exactly two products: **Claude Code** (`claude_code`) and **OpenAI Codex** (`codex`). Each spans its CLI _and_ its app/IDE form because they read one shared config directory — Claude Code uses `~/.claude/`, Codex uses `~/.codex/`. The separate **Claude Desktop** chat app (its own `~/Library/Application Support/Claude/` config) and **Cursor** are out of scope for v1; either would be added later as its own agent type with its own config allowlist.

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

Some users install agents in non-default locations or have multiple installs (work vs personal). They need to add an agent by type, optionally overriding the skill directory. The name is optional — when omitted Coffer derives a stable per-type default. When choosing a custom path, the desktop app offers a folder picker (the OS-native dialog in the packaged app; a daemon-backed folder browser on the web) so the user picks a real directory instead of typing it.

**Why this priority**: Discovery covers the common case; manual register covers the long tail. Without it the registry is incomplete.

**Independent Test**: From the command line, register a `codex` agent named `codex-work` with `--skill-dir /custom/path`; list agents; observe the manually-registered entry. From the desktop form, add an agent with no name and observe it registered under the per-type default name.

**Covering scenarios**:

- register an agent with a custom skill_dir
- register an agent without an explicit name
- reject registration when skill_dir is missing or not writable
- reject duplicate agent names
- browse local folders to choose a skill directory

---

### User Story 3 — Edit or remove an agent (Priority: P1)

The user's installed agents change over time. They need to update the skill_dir path or description, or fully delete the agent. (Agents have no enable/disable concept — a registered agent is simply present.)

**Why this priority**: An immutable registry would be useless within a week.

**Independent Test**: Register an agent, update its skill_dir, then remove it; verify each state is persisted and audited.

**Covering scenarios**:

- update skill_dir for an existing agent
- remove an agent and observe audit entry

---

### User Story 4 — Manage agents through the desktop app (Priority: P2)

The user opens Coffer's desktop app, sees an "Agents" page listing every registered agent with type, name, and skill_dir, and can add or edit from a form.

**Why this priority**: Non-CLI users need a visual surface to make sense of the registry.

**Independent Test**: Open desktop app → Agents → add Codex with default path → observe in list → click into it → change skill_dir → save → list updates.

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

### User Story 7 — View and edit an agent's config files (Priority: P2)

After an agent is registered, the user wants to see and adjust that agent's own configuration files (e.g. Claude Code's `settings.json`, Codex's `config.toml`) directly inside Coffer, without leaving the app to hunt for dotfiles. Coffer shows the agent type's curated set of known config files, lets the user open one to read its current content, edit it in place, and save it back. On save, Coffer validates the content against the file's format (malformed JSON/TOML is rejected and the file is left unchanged), writes it atomically, and keeps a `.bak` of the prior version so a bad edit is always recoverable. A dependency-free in-editor find / replace tool is offered as a convenience while editing.

**Why this priority**: Locating agent config by hand means remembering where each file lives and what format it uses. Surfacing the curated set in one place — viewable and editable at a glance, with a safety net for bad edits — is the first feature that makes the registry useful beyond bookkeeping.

**Independent Test**: Register a `claude_code` agent; list its config files; open `settings.json`; edit and save it; observe the new content reads back and a `.bak` was kept; open a not-yet-created file (e.g. `CLAUDE.md`) and observe it reads as empty without being created.

**Covering scenarios**:

- list an agent's curated config files with existence + size metadata
- read the content of an existing config file
- read a not-yet-created config file as empty
- reject reading a key outside the agent type's allowlist
- save a config file with valid content
- reject malformed config-file content

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

### Edge Cases

- **Discovery on a second scan**: Already-registered types are not offered as candidates; discovery never duplicates existing entries.
- **User deletes an agent**: A removal is not permanent. The next scan re-surfaces that agent as a candidate (the deletion may have been accidental); Coffer keeps no suppression list. The user re-adds with one confirm.
- **Agent type not in the supported list**: Registration rejected with a clear message and the supported-type list (`claude_code`, `codex`).
- **`skill_dir` path doesn't exist or isn't writable**: Registration rejected; no partial state.
- **`skill_dir` points to a privileged path** (`/etc`, `/usr`, etc.): Registration rejected.
- **Duplicate name within `agent` kind**: Rejected by the kind-agnostic Resource framework.
- **Config-file key not in the type's allowlist**: Read rejected with `not_found` (404); no filesystem access for an unknown key.
- **Config file does not exist yet**: Listed and readable as `exists=false` with empty content; the read never creates the file.
- **Coffer MCP install when already installed**: Idempotent — the `coffer` entry is updated in place, never duplicated; status remains `installed`.
- **Coffer MCP uninstall when not installed**: No-op success; status reports `not_installed`.
- **`coffer-mcp-shim` binary cannot be resolved**: Install rejected with a clear error naming the missing binary; nothing is written to the agent's config.
- **Folder browse outside the home directory**: The daemon-backed folder browser lists subdirectories of any readable directory the user navigates to; it never returns file contents. An unreadable or non-existent path returns an error, not a partial listing.

## Acceptance Scenarios

Per `agents/sdd.md` and `agents/testing.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="004-agent-registry", scenario="…")` (Python) or `acceptance("004-agent-registry", "…", …)` (TypeScript).

### Scenario: discover installed agents as candidates

- **Given** a Coffer install with `~/.codex/` present and no agent registered,
- **When** the user runs discovery,
- **Then** Coffer reports a `codex` candidate (type, display name, config dir, default `skill_dir`, suggested name) and registers nothing — discovery is read-only.

### Scenario: skip already-registered types on subsequent scan

- **Given** a `codex` agent is already registered,
- **When** the user runs discovery again,
- **Then** `codex` is not offered as a candidate.

### Scenario: re-surface removed agents on subsequent scan

- **Given** an agent has been removed by the user and its install marker is still present,
- **When** the user runs discovery again,
- **Then** that agent is offered as a candidate again (removal is not permanent; no suppression list).

### Scenario: register an agent with custom skill_dir

- **Given** the daemon is running,
- **When** the user registers an agent of supported type with an explicit, writable `skill_dir`,
- **Then** the agent is persisted with that path and appears in `coffer agent list`.

### Scenario: reject registration with invalid skill_dir

- **Given** the daemon is running,
- **When** the user registers an agent whose `skill_dir` does not exist, is not a directory, or is not writable,
- **Then** registration is rejected with a message naming the path, and nothing is persisted.

### Scenario: reject duplicate agent name

- **Given** an agent named `codex-work` exists,
- **When** the user attempts to register another agent with the same name,
- **Then** registration is rejected with a clear error.

### Scenario: reject a second agent for an already-registered config dir

- **Given** a `codex` agent is already registered (whose config dir is `~/.codex`),
- **When** the user attempts to register another `codex` agent (which resolves to the same config dir), even with a different name and skill_dir,
- **Then** registration is rejected with a clear error and nothing is persisted — only one agent may exist per config directory.

### Scenario: register an agent without an explicit name

- **Given** the daemon is running,
- **When** the user registers an agent of supported type without supplying a name,
- **Then** the agent is registered under a stable per-type default name (underscores become hyphens, e.g. `claude_code` → `claude-code`).

### Scenario: browse local folders to choose a skill directory

- **Given** the daemon is running,
- **When** the web folder browser requests the subdirectories of a readable directory,
- **Then** Coffer returns that directory's path, its parent, and its immediate subdirectories (no file contents); an unreadable or missing path returns an error.

### Scenario: update an existing agent

- **Given** a registered agent,
- **When** the user updates its `skill_dir` to a new writable path,
- **Then** the change persists, an audit entry is recorded, and subsequent operations see the new path.

### Scenario: remove an agent

- **Given** a registered agent (any binding cleanup is handled by spec 005),
- **When** the user removes it,
- **Then** the agent is deleted, an audit entry is recorded, and `coffer agent list` no longer shows it.

### Scenario: desktop app agents page

- **Given** Coffer's desktop app is launched and one or more agents are registered,
- **When** the user opens the Agents page,
- **Then** every registered agent appears with type, name, and `skill_dir`.

> Story 4 add/edit/remove flows from the desktop form are exercised at the e2e tier; see `e2e/web/specs/shell_agents.spec.ts` for the bundled acceptance coverage.

### Scenario: CLI surface mirrors REST operations

- **Given** the daemon is running and exposes the REST agent routes,
- **When** the user invokes `coffer agent add`, `list`, `edit`, `rm`, or `detect`,
- **Then** each subcommand calls the corresponding REST endpoint and produces equivalent state changes, and every read subcommand additionally accepts `--json` for machine-readable output.

### Scenario: reject registration into privileged system path

- **Given** the daemon is running,
- **When** the user attempts to register an agent whose `skill_dir` resolves under a privileged location (`/etc`, `/usr`, `/bin`, `/sbin`, `/System`, `C:\Windows`, or `C:\Program Files`),
- **Then** registration is rejected with `unprocessable_entity` (422) and no resource row, audit event, or filesystem write occurs.

### Scenario: audit lifecycle events

- **Given** the user has registered, edited, or removed agents,
- **When** they view the audit log,
- **Then** every lifecycle change (create, update, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_deleted` events, each carrying timestamp, actor, and the affected agent reference. (Agents have no enable/disable concept; discovery is read-only and registers nothing, so neither emits an audit event of its own.)

### Scenario: reject unsupported agent type

- **Given** the daemon is running,
- **When** the user attempts to register an agent of a type other than `claude_code` or `codex` (e.g. `cursor`, `claude_desktop`),
- **Then** registration is rejected with `unprocessable_entity` (422) naming the two supported types, and nothing is persisted.

### Scenario: list an agent's config files

- **Given** a registered `claude_code` agent,
- **When** the user lists its config files,
- **Then** Coffer returns the curated set for the type — `settings.json`, `settings.local.json`, `~/.claude.json`, `CLAUDE.md` — each with its resolved path, format, and an `exists` flag (with size + modified time when present).

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
- **When** the user writes new, well-formed content to that config-file key,
- **Then** Coffer validates the content against the file's format, writes it atomically while keeping a `.bak` of the prior version, records an `agent_config_file_written` audit entry, and the new content reads back on the next read.

### Scenario: reject malformed config-file content

- **Given** a registered agent whose `settings.json` (a `json` file) exists,
- **When** the user writes malformed content (e.g. invalid JSON) to that key,
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

## Requirements

### Functional Requirements

**Resource model**

- **FR-001**: System MUST register each known local agent as a Resource of kind `agent`, identified by `agent:<name>` per spec 001-mcp-gateway's `<kind>:<name>` convention.
- **FR-002**: System MUST validate agent configuration against a kind-specific schema with fields `type` (enum) and `skill_dir` (path, optional override).
- **FR-003**: System MUST support the agent types `claude_code` and `codex` in v1; registering any other type (including `claude_desktop`, `cursor`) is rejected with `unprocessable_entity` (422). Each supported type covers both the CLI and the app/IDE form of that product, which share one config directory.

**Discovery (detection = discovery + confirm)**

- **FR-004**: System MUST provide a read-only discovery operation that scans well-known install markers for each supported agent type and reports installed types that are not already registered as **candidates** (each carrying type, display name, config dir, default `skill_dir`, and a suggested name). Discovery MUST NOT register anything automatically — the user reviews candidates and confirms which to add. The daemon MUST NOT auto-register agents on startup.
- **FR-005**: A removed agent MUST re-appear as a discovery candidate on subsequent scans while its install marker is present — a removal is not permanent (it may be accidental). System MUST NOT keep a "suppressed types" list.

**Lifecycle**

- **FR-006**: Users MUST be able to register, list, view, update (skill_dir, description), and remove agents. Agents have **no enable/disable concept** — a registered agent is simply present; there is no enabled/disabled state on the agent surface. The agent name is optional at registration — when omitted, System MUST derive a stable per-type default (underscores become hyphens, e.g. `claude_code` → `claude-code`).
- **FR-007**: System MUST validate that any provided `skill_dir` exists, is a directory, is writable, and is not a privileged system path before accepting the value.
- **FR-008**: System MUST reject registration that would create a duplicate `agent:<name>`, and MUST reject registering more than one agent for the same config directory. `config_dir` is derived from the agent type, so each supported type — and thus each on-disk config directory — may be registered at most once; a second attempt is rejected with `conflict` (409) and nothing is persisted.

**Config files**

- **FR-013**: Each supported agent type MUST define a curated allowlist of config files, each entry carrying a stable `key`, a display name, a resolved absolute path, and a `format` (`json`, `toml`, `markdown`, or `text`). For v1: Claude Code → `settings.json`, `settings.local.json`, `~/.claude.json`, `CLAUDE.md`; Codex → `config.toml`, `AGENTS.md`.
- **FR-014**: Users MUST be able to list an agent's config files with, for each, its key, display name, path, format, and existence (plus size and modified time when the file exists).
- **FR-015**: Users MUST be able to read the content of any allowlisted config file. A file that does not exist reads as empty content with `exists=false` and is not created by the read.
- **FR-016**: Users MUST be able to write (save) the content of any allowlisted config file. The content MUST be validated against the file's `format` before any write; malformed `json`/`toml` MUST be rejected (`unprocessable_entity`, 422) and the on-disk file left unchanged. `markdown`/`text` files accept any content.
- **FR-017**: Writes MUST be atomic (temp file + rename) and MUST keep a `.bak` copy of the prior content so a bad edit is recoverable; each successful write MUST record an `agent_config_file_written` audit entry. The Coffer-MCP install/uninstall operations (FR-022) reuse the same atomic-write + `.bak` machinery.
- **FR-018**: Config-file read and write MUST be addressable only by allowlisted `key` (never by caller-supplied path); an unknown key returns `not_found` (404) and performs no filesystem access.

**Coffer MCP install**

- **FR-019**: Users MUST be able to install Coffer's own MCP server into an agent in one action. The install writes a `coffer` MCP-server entry into the agent's MCP config — `mcpServers.coffer` in `~/.claude.json` for `claude_code`, `[mcp_servers.coffer]` in `~/.codex/config.toml` for `codex` — using the stdio shim with `command` set to the absolute path of the `coffer-mcp-shim` binary (resolved on `PATH`, then the running interpreter's scripts directory — so a venv-installed shim is found even when the daemon's `PATH` lacks the venv — then the bundled binary; a `COFFER_MCP_SHIM_PATH` environment override takes precedence over all). If the shim cannot be resolved, install is rejected and nothing is written.
- **FR-020**: Install MUST be idempotent — re-installing updates the existing `coffer` entry in place and never creates a duplicate. System MUST expose a status operation reporting whether Coffer's MCP is currently installed for the agent.
- **FR-021**: Users MUST be able to uninstall Coffer's MCP, removing the `coffer` entry from the agent's MCP config. Uninstalling when not installed is a no-op success.
- **FR-022**: Install and uninstall MUST reuse the atomic-write + `.bak` machinery from FR-017 and record an audit entry (`agent_mcp_installed` / `agent_mcp_uninstalled`).

**Surfaces**

- **FR-009**: Every management operation — register/list/view/update/remove, config-file list/read/write, and Coffer-MCP install/uninstall/status — MUST be available through (a) the REST API, (b) the `coffer agent ...` CLI, and (c) the desktop Agents page.
- **FR-010**: The CLI MUST support `--json` for machine-readable output on every read operation.

**Observability**

- **FR-011**: System MUST record an audit entry for every lifecycle event: agent created, updated, removed; config file written (`agent_config_file_written`); Coffer MCP installed/uninstalled. (Agents have no enable/disable concept; discovery is read-only — neither emits an audit event.)
- **FR-012**: System MUST expose a read-only discovery operation listing installed-but-unregistered agents as candidates, available from the REST API (`GET /api/v1/agents/candidates`), the `coffer agent detect` CLI, and the desktop Agents page.

**Skill-directory picker**

- **FR-023**: When choosing a custom `skill_dir`, the desktop app MUST offer a folder picker rather than requiring the user to type a path. In the packaged desktop app it MUST use the OS-native directory dialog; on the web it MUST use the daemon-backed folder browser (FR-024). Both yield an absolute path that is then validated per FR-007 before registration.
- **FR-024**: System MUST expose a read-only filesystem-browse operation (`GET /api/v1/fs/browse`) that, given a directory path (defaulting to the user's home), returns that path, its parent, and its immediate subdirectories. It MUST NOT return file contents and MUST be guarded by the same loopback + token auth as all other daemon routes.

### Key Entities

- **Agent**: A Resource of kind `agent`. Represents one locally-installed AI agent. Config: `type` (supported enum), `skill_dir` (path or default-by-type). Identified by `agent:<name>`.
- **Agent Type**: An enum value identifying a known agent product (`claude_code`, `codex`). Each type has a default `skill_dir`, a display name, an install-marker scanner used for discovery, and a curated **config-file allowlist**.
- **Agent Candidate**: A discovered installed-but-unregistered agent — type, display name, config dir, default `skill_dir`, and suggested name. Derived at scan time, never stored; the user confirms a candidate to register it.
- **Config File**: A curated, allowlisted file belonging to an agent type, identified by a stable `key`. Carries a display name, a resolved absolute path, a `format` (`json` / `toml` / `markdown` / `text`), and (when present) size and modified time. Read/written by key, never by arbitrary path. Not persisted in SQLite — the file on disk is the source of truth.
- **Coffer MCP Install Status**: Derived (not stored) state for an agent: whether a `coffer` MCP-server entry is present in that agent's MCP config file.

## Success Criteria

### Measurable Outcomes

- **SC-001**: On a machine with at least two supported agent install paths present, running discovery surfaces exactly those agents as candidates, and the user adds them with a single confirm each — no typing of type identifiers or paths.
- **SC-002**: From a fresh install, a user can register an additional agent with a custom `skill_dir` and see it in `coffer agent list --json` within 60 seconds, without consulting documentation more than once.
- **SC-003**: Every Acceptance Scenario in this spec is covered by at least one test marked `acceptance(spec="004-agent-registry", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-004**: The full `make verify` suite passes locally and in CI; `make verify-all` (adding e2e) passes on macOS and Linux.
- **SC-005**: No `skill_dir` value ever permits writing outside the directory itself (path-traversal check); validated by a dedicated security test.
- **SC-006**: A user can open, edit, and save an agent's `settings.json` (Claude Code) or `config.toml` (Codex) from both the desktop app and the CLI; a malformed save is rejected with the file left unchanged, and a `.bak` of the prior version is kept on a successful save.
- **SC-007**: A user can install Coffer's MCP into a freshly-registered agent in one click and, after restarting that agent, the agent lists Coffer's aggregated tools; re-installing never duplicates the entry, and uninstall removes it.

## Assumptions

- The user runs Coffer on their own machine; there is no multi-tenant or remote-access requirement.
- v1's two supported agent types (`claude_code`, `codex`) cover the user's installed agents; adding a new type (e.g. the Claude Desktop chat app, Cursor, Gemini CLI) is a future-spec change that adds another enum value, install-marker scanner, and config-file allowlist.
- Each supported agent's CLI and app/IDE form read one shared config directory (`~/.claude/` for Claude Code, `~/.codex/` for Codex), so Coffer manages one config set per agent.
- Config files are surfaced as raw text the user can edit and save (with a `.bak` safety net); an in-editor find / replace is a UI convenience. Structured per-field editing and managing the MCP-server list inside `~/.claude.json` beyond the one-click Coffer entry are out of scope for v1. The credential/state file `~/.codex/auth.json` is intentionally excluded from the allowlist.
- Agents store their skill libraries on the local filesystem in a discoverable directory. Web-only agents (e.g., claude.ai) are out of scope for v1 and require a future spec to add API-based sync.
- The kind-agnostic Resource framework, audit log, and `<kind>:<name>` identity scheme defined by spec 001-mcp-gateway are in place.
- The application shell from spec 002-ui-shell — sidebar IA, layout, routing skeleton, and design system — is in place. The desktop Agents page renders within that shell at `/agents` as a **dedicated top-level nav entry** (a sibling of the Resources and System groups, **not** nested under Resources — agents are consumers of vault assets, not assets themselves). Agent resources do not appear in the kind-agnostic resources/MCP browser, which lists only kinds that register a resource-card UI.
- Skill bindings (i.e., the relationship between an agent and a particular skill) are introduced and managed by spec 005-skill-manager; spec 004 does not define skill operations beyond exposing an `on_delete` hook for cascade cleanup.
