# Feature Specification: Agent Registry

**Feature Branch**: `feature/004-agent-registry`
**Created**: 2026-05-22
**Status**: Draft
**Input**: User description: "Manage which locally-installed AI agents Coffer knows about, so later features (skills, memory, knowledge bases) can deliver assets to them. Each agent is a Resource of kind `agent` in the kind-agnostic Resource framework introduced by spec 001-mcp-gateway. v1 supports four agent types: Claude Code, Claude Desktop, Cursor, OpenAI Codex CLI."

## User Scenarios & Testing

### User Story 1 — Auto-detect installed agents on first run (Priority: P1)

When a developer first launches Coffer, the daemon scans well-known install paths for each supported agent type and registers what it finds. The developer sees their existing agents already listed without manually typing paths.

**Why this priority**: Zero-config first impression. Without auto-detect, the user has to learn agent type identifiers and default paths before doing anything useful.

**Independent Test**: On a machine with `~/.claude/` and `~/.cursor/` present, launch the daemon, list agents, observe both Claude Code and Cursor registered with `auto_detected=true`.

**Covering scenarios**:

- detect Claude Code from `~/.claude/`
- detect Claude Desktop from platform-specific path
- detect Cursor and Codex CLI
- skip already-registered types
- suppress agents the user previously removed

---

### User Story 2 — Manually register an agent with a custom path (Priority: P1)

Some users install agents in non-default locations or have multiple installs (work vs personal). They need to add an agent by type with an overridden skill directory.

**Why this priority**: Auto-detect covers the common case; manual register covers the long tail. Without it the registry is incomplete.

**Independent Test**: From the command line, register a `cursor` agent named `cursor-work` with `--skill-dir /custom/path`; list agents; observe both auto-detected and manually-registered entries.

**Covering scenarios**:

- register an agent with a custom skill_dir
- reject registration when skill_dir is missing or not writable
- reject duplicate agent names

---

### User Story 3 — Edit, disable, or remove an agent (Priority: P1)

The user's installed agents change over time. They need to update the skill_dir path, toggle the agent off without removing, or fully delete it.

**Why this priority**: An immutable registry would be useless within a week.

**Independent Test**: Register an agent, update its skill_dir, disable it, re-enable it, then remove it; verify each state is persisted and audited.

**Covering scenarios**:

- update skill_dir for an existing agent
- enable/disable an agent
- remove an agent and observe audit entry

---

### User Story 4 — Manage agents through the desktop app (Priority: P2)

The user opens Coffer's desktop app, sees an "Agents" page listing every registered agent with type, name, skill_dir, and detection method, and can add or edit from a form.

**Why this priority**: Non-CLI users need a visual surface to make sense of the registry.

**Independent Test**: Open desktop app → Agents → add Cursor with default path → observe in list → click into it → change skill_dir → save → list updates.

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

### Edge Cases

- **Auto-detect on second launch**: Already-registered types are skipped; the scan does not duplicate existing entries.
- **User deletes an auto-detected agent**: That agent type is not re-registered automatically on next scan (suppressed). The user can re-add manually at any time.
- **Agent type not in the supported list**: Registration rejected with a clear message and the supported-type list.
- **`skill_dir` path doesn't exist or isn't writable**: Registration rejected; no partial state.
- **`skill_dir` points to a privileged path** (`/etc`, `/usr`, etc.): Registration rejected.
- **Duplicate name within `agent` kind**: Rejected by the kind-agnostic Resource framework.

(Concurrent detect requests are covered by an explicit acceptance scenario above; see "concurrent detect requests are serialized".)

## Acceptance Scenarios

Per `agents/sdd.md` and `agents/testing.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="004-agent-registry", scenario="…")` (Python) or `acceptance("004-agent-registry", "…", …)` (TypeScript).

### Scenario: detect installed agents on first launch

- **Given** a fresh Coffer install with `~/.claude/` and `~/.cursor/` present,
- **When** the daemon starts for the first time,
- **Then** Coffer registers one `claude_code` agent and one `cursor` agent, both flagged `auto_detected=true`, with default `skill_dir` values.

### Scenario: skip already-registered types on subsequent launch

- **Given** a `claude_code` agent is already registered,
- **When** the daemon restarts and re-scans,
- **Then** no second `claude_code` agent is registered.

### Scenario: respect user removal across launches

- **Given** an auto-detected agent has been removed by the user,
- **When** the daemon restarts and re-scans,
- **Then** that agent type is not re-registered automatically.

### Scenario: register an agent with custom skill_dir

- **Given** the daemon is running,
- **When** the user registers an agent of supported type with an explicit, writable `skill_dir`,
- **Then** the agent is persisted with that path and appears in `coffer agent list`.

### Scenario: reject registration with invalid skill_dir

- **Given** the daemon is running,
- **When** the user registers an agent whose `skill_dir` does not exist, is not a directory, or is not writable,
- **Then** registration is rejected with a message naming the path, and nothing is persisted.

### Scenario: reject duplicate agent name

- **Given** an agent named `cursor-work` exists,
- **When** the user attempts to register another agent with the same name,
- **Then** registration is rejected with a clear error.

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
- **Then** every registered agent appears with type, name, `skill_dir`, and detection method.

> Story 4 add/edit/remove flows from the desktop form are exercised at the e2e tier; see `e2e/web/specs/shell_agents.spec.ts` for the bundled acceptance coverage.

### Scenario: CLI surface mirrors REST operations

- **Given** the daemon is running and exposes the REST agent routes,
- **When** the user invokes `coffer agent add`, `list`, `edit`, `rm`, or `detect`,
- **Then** each subcommand calls the corresponding REST endpoint and produces equivalent state changes, and every read subcommand additionally accepts `--json` for machine-readable output.

### Scenario: reject registration into privileged system path

- **Given** the daemon is running,
- **When** the user attempts to register an agent whose `skill_dir` resolves under a privileged location (`/etc`, `/usr`, `/bin`, `/sbin`, `/System`, `C:\Windows`, or `C:\Program Files`),
- **Then** registration is rejected with `unprocessable_entity` (422) and no resource row, audit event, or filesystem write occurs.

### Scenario: concurrent detect requests are serialized

- **Given** the daemon is running and exposes `POST /api/v1/agents/detect`,
- **When** two detect requests arrive concurrently on a host with the same supported install markers present,
- **Then** auto-detection is serialized so each supported type is registered at most once across both responses (no duplicate `agent:<name>` rows).

### Scenario: audit lifecycle events

- **Given** the user has registered, edited, or removed agents,
- **When** they view the audit log,
- **Then** auto-detected additions appear as `agent_auto_registered`, user removals of auto-detected agents also emit `agent_type_suppressed`, and every other lifecycle change (manual create, update, enable, disable, remove) appears via the kind-agnostic `resource_created` / `resource_updated` / `resource_enabled` / `resource_disabled` / `resource_removed` events, each carrying timestamp, actor, and the affected agent reference.

## Requirements

### Functional Requirements

**Resource model**

- **FR-001**: System MUST register each known local agent as a Resource of kind `agent`, identified by `agent:<name>` per spec 001-mcp-gateway's `<kind>:<name>` convention.
- **FR-002**: System MUST validate agent configuration against a kind-specific schema with fields `type` (enum), `skill_dir` (path, optional override), and `auto_detected` (bool).
- **FR-003**: System MUST support the agent types `claude_code`, `claude_desktop`, `cursor`, and `codex_cli` in v1; registering any other type is rejected with `unprocessable_entity` (422).

**Auto-detection**

- **FR-004**: On daemon startup, System MUST scan well-known install markers for each supported agent type and register a Resource for any type not already present and not on the user-suppression list.
- **FR-005**: System MUST persist a "suppressed types" list of agent types previously removed by the user, and skip auto-registration for those types on subsequent scans until the user re-registers manually.

**Lifecycle**

- **FR-006**: Users MUST be able to register, list, view, update (skill_dir, description), enable/disable, and remove agents.
- **FR-007**: System MUST validate that any provided `skill_dir` exists, is a directory, is writable, and is not a privileged system path before accepting the value.
- **FR-008**: System MUST reject registration that would create a duplicate `agent:<name>`.

**Surfaces**

- **FR-009**: Every management operation MUST be available through (a) the REST API, (b) the `coffer agent ...` CLI, and (c) the desktop Agents page.
- **FR-010**: The CLI MUST support `--json` for machine-readable output on every read operation.

**Observability**

- **FR-011**: System MUST record an audit entry for every lifecycle event: agent created (auto or manual), updated, enabled, disabled, removed.
- **FR-012**: System MUST expose a `detect` operation to re-run auto-detection on demand from the REST API (`POST /api/v1/agents/detect`), the `coffer agent detect` CLI, and the desktop Agents page.

### Key Entities

- **Agent**: A Resource of kind `agent`. Represents one locally-installed AI agent. Config: `type` (supported enum), `skill_dir` (path or default-by-type), `auto_detected` (provenance). Identified by `agent:<name>`.
- **Agent Type**: An enum value identifying a known agent product. Each type has a default `skill_dir` (used when the user does not override), a display name, and an install-marker scanner used for auto-detection.
- **Suppressed Type Record**: A small system-state row indicating the user explicitly removed an auto-detected agent of a given type; used to suppress re-auto-registration.

## Success Criteria

### Measurable Outcomes

- **SC-001**: On a machine with at least two supported agent install paths present, launching the daemon for the first time auto-registers exactly those agents, with no manual steps.
- **SC-002**: From a fresh install, a user can register an additional agent with a custom `skill_dir` and see it in `coffer agent list --json` within 60 seconds, without consulting documentation more than once.
- **SC-003**: Every Acceptance Scenario in this spec is covered by at least one test marked `acceptance(spec="004-agent-registry", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-004**: The full `make verify` suite passes locally and in CI; `make verify-all` (adding e2e) passes on macOS and Linux.
- **SC-005**: No `skill_dir` value ever permits writing outside the directory itself (path-traversal check); validated by a dedicated security test.

## Assumptions

- The user runs Coffer on their own machine; there is no multi-tenant or remote-access requirement.
- v1's four supported agent types cover the user's installed agents; adding a new type is a future-spec change that adds another enum value and install-marker scanner.
- Agents store their skill libraries on the local filesystem in a discoverable directory. Web-only agents (e.g., claude.ai) are out of scope for v1 and require a future spec to add API-based sync.
- The kind-agnostic Resource framework, audit log, and `<kind>:<name>` identity scheme defined by spec 001-mcp-gateway are in place.
- The application shell from spec 002-ui-shell — sidebar IA, layout, routing skeleton, and design system — is in place; the desktop Agents page is a feature surface that renders within that shell and fills the `/agents` nav slot 002-ui-shell reserved as a placeholder.
- Skill bindings (i.e., the relationship between an agent and a particular skill) are introduced and managed by spec 005-skill-manager; spec 004 does not define skill operations beyond exposing an `on_delete` hook for cascade cleanup.
