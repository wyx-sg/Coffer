# Feature Specification: Skill Manager

**Feature Branch**: `feature/skill-manager`
**Created**: 2026-05-22
**Status**: Draft
**Input**: User description: "Coffer manages portable AI skills using the open AgentSkills standard (agentskills.io). One canonical store lives at `~/.coffer/skills/`; per-agent visibility is a directory symlink/junction into the `skills/` subfolder of each agent's config directory. Users can import skills from local paths or fetch them from public Git repositories, then enable or disable each skill per registered agent. v1 supports Claude Code and Codex CLI as sync targets (each registered as a Resource of kind `agent` per spec 004-agent-registry)."

## User Scenarios & Testing

### User Story 1 — Import an existing skill folder (Priority: P1)

A developer already has skills in `~/.claude/skills/` (or elsewhere on disk). They import them into Coffer to make them portable across agents and centrally managed.

**Why this priority**: Migrating existing assets is most users' day-zero need. Without import, Coffer has no skills to manage.

**Independent Test**: From the command line, import an existing skill folder; verify the canonical copy exists at `~/.coffer/skills/<name>/`; verify the skill appears in `coffer skill list`.

**Covering scenarios**:

- import a valid skill folder
- reject import when SKILL.md is missing or has invalid frontmatter
- reject import on duplicate skill name
- reject import containing path-escape symlinks

---

### User Story 2 — Fetch a skill from a Git URL (Priority: P1)

A developer finds a skill in a public GitHub repository and pulls it into Coffer.

**Why this priority**: The AgentSkills ecosystem is collaborative; fetching from URLs is the primary distribution channel. Without it, users are locked to their own authored skills.

**Independent Test**: From the command line, fetch a known public skill repo with a subpath; verify the canonical copy is created with `source.type=git`; verify the URL, ref, and subpath are persisted.

**Covering scenarios**:

- fetch a public Git skill repo by URL + ref + subpath
- reject SSRF attempts (loopback / private IPs)
- reject private repos in v1
- reject fetched payloads that fail SKILL.md validation

---

### User Story 3 — Enable a skill for a specific agent (Priority: P1)

The developer wants this skill available in Claude Code but not in Codex. They enable per agent, and Coffer creates a directory symlink into the `skills/` subfolder of that agent's config directory.

**Why this priority**: This is the core "unify management" value. Without per-agent enable, Coffer has no advantage over copying files manually.

**Independent Test**: Register a Claude Code agent (per spec 004); import a skill; enable for that agent; verify a directory symlink appears at `<config_dir>/skills/<skill-name>` pointing to `~/.coffer/skills/<skill-name>/`.

**Covering scenarios**:

- enable a skill for a registered agent
- disable a skill for an agent (link removed, master untouched)
- enable for multiple agents (multiple links to one master)
- refuse to overwrite an existing non-Coffer file at the target without `--force`

---

### User Story 4 — Update a skill from its source (Priority: P2)

A developer wants the latest version of a Git-sourced skill.

**Why this priority**: Without updates, fetched skills go stale and users distrust the system.

**Independent Test**: Fetch a Git skill; bump the upstream content; run `coffer skill update`; verify the master content changes and every enabled agent sees the new version on next read.

**Covering scenarios**:

- update a Git-sourced skill to newer upstream content
- detect and warn on SKILL.md frontmatter name change between versions
- no-op update when content is unchanged

---

### User Story 5 — Detect and report drift (Priority: P2)

Files in agents' `config_dir/skills` folders can be tampered with (deleted, replaced, edited). The developer needs to see what's out of sync and decide what to do.

**Why this priority**: Trust in the sync engine depends on transparency about disagreement.

**Independent Test**: Manually delete a symlink in an agent's `config_dir/skills` folder; run `coffer skill verify`; observe the drift report identifies the missing link with a suggested remedy.

**Covering scenarios**:

- detect missing link at target
- detect tampered link (regular file or symlink to a different target)
- detect missing master folder
- detect orphan master (folder on disk but no DB record)
- no automatic remediation without explicit user action

---

### User Story 6 — Manage skills through the desktop app (Priority: P2)

The user opens Coffer, sees the Skills page rendered as a data table (search, filter, pagination, row multi-select for bulk actions), can import via file picker or paste a Git URL, and browse the list. The Skills page manages the skill resource itself, not its per-agent bindings: clicking a skill opens a detail view with an Overview metadata tab and a read-only Files tab (file tree + file viewer). Per-agent enable/disable lives on the agent detail page — the agent's "Skills" tab lists the skills bound to that agent with per-binding toggles.

**Why this priority**: Non-CLI users need a visual surface for daily management.

**Independent Test**: Open desktop app → Skills → import a folder via picker → see it listed in the table → open the agent detail page → its Skills tab → toggle the skill enabled for that agent → confirm the symlink exists on disk.

**Covering scenarios**:

- import a skill via desktop file picker
- fetch a skill via desktop URL form
- toggle per-agent enable via desktop toggle
- surface drift count via a UI notification

---

### User Story 7 — Same operations from the command line (Priority: P2)

The developer scripts skill setup across machines via `coffer skill ...` subcommands with `--json` output.

**Independent Test**: A bash script imports a skill, fetches another, enables both for two agents, lists state, verifies drift, all without GUI.

**Covering scenarios**:

- command line covers every visual operation
- machine-readable JSON output

---

### User Story 8 — Remove a skill cleanly (Priority: P3)

When the developer removes a skill, every per-agent symlink is removed and the canonical folder is deleted.

**Why this priority**: A delete that leaves stale symlinks behind would silently confuse agents.

**Independent Test**: Enable a skill for two agents; remove the skill; verify both target symlinks are gone and the master folder is deleted.

**Covering scenarios**:

- remove a skill that has active per-agent bindings
- audit the removal with a snapshot

---

### User Story 9 — Audit skill lifecycle (Priority: P3)

Every import, fetch, enable, disable, update, and remove is auditable.

**Independent Test**: Perform a representative sequence; view audit log; one row per change with actor, target, and event type.

**Covering scenarios**:

- audit import, fetch, enable, disable, update, remove

---

### Edge Cases

- **Skill name collision on import**: Rejected; user must rename via SKILL.md frontmatter and retry.
- **Frontmatter name changes between updates**: Update rejected by default; `--allow-rename` performs an atomic rename of the master folder and rebuilds all enabled symlinks. The audit log retains the historical name on each prior event; the current Resource row's name reflects the post-rename value.
- **Master folder size exceeds limit (default 50 MB)**: Import or fetch rejected with the configured cap and a hint to adjust settings.
- **Git fetch hits a private repo or auth-required URL**: Rejected; v1 does not handle credentials for upstream skill sources.
- **Git fetch hits an unreachable host, DNS failure, or timeout**: Operation aborts cleanly with a network error; no master folder is partially written and no Resource row is persisted.
- **Symlink/junction creation fails on Windows (FAT32 or network share)**: Falls back to copy mode for that target with an audit flag `degraded=true`; UI shows a warning chip.
- **User edits `SKILL.md` inside an agent's `config_dir/skills` folder**: Because the agent's path is a symlink to master, the edit lands in master and is visible to all other agents on next read; no drift is detected.
- **User deletes a Coffer-managed file from inside an agent's `config_dir/skills` folder**: Master is affected (same reason); next `verify` flags any other agents whose links no longer resolve consistently.
- **Removing an agent (per spec 004) while it has skill bindings**: Spec 004 defines the agent kind's `on_delete` seam; the 005-skill-manager spec supplies the `cleanup_bindings_for_agent` callback at the composition root, so removing an agent first cleans up that agent's bindings and any associated symlinks before the agent row is deleted.
- **Agent's `config_dir` is moved or removed externally**: The next sync operation surfaces the failure; `verify` reports the affected bindings; user remediates by updating the agent's `config_dir` or removing the agent.

## Acceptance Scenarios

Per `agents/sdd.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="005-skill-manager", scenario="…")` (Python) or `acceptance("005-skill-manager", "…", …)` (TypeScript).

### Scenario: import a valid local skill folder

- **Given** the daemon is running and no skill named `my-skill` exists,
- **When** the user imports a folder containing a valid SKILL.md with frontmatter `name: my-skill`,
- **Then** Coffer copies the folder to `~/.coffer/skills/my-skill/`, persists a Resource of kind `skill`, and records an audit entry.

### Scenario: reject import of an invalid skill folder

- **Given** the daemon is running,
- **When** the user imports a folder that is missing `SKILL.md` or has empty `name`/`description` frontmatter,
- **Then** the request is rejected with a clear error, and nothing is written to `~/.coffer/skills/` or the database.

### Scenario: reject import containing path-escape symlinks

- **Given** the daemon is running,
- **When** the user imports a folder containing a symlink that resolves outside the folder,
- **Then** the request is rejected with the offending paths listed, and nothing is persisted.

### Scenario: fetch a public Git skill repo

- **Given** the daemon is running and a public Git URL hosts a valid skill at a known subpath,
- **When** the user runs `coffer skill fetch <url> --ref <ref> --subpath <path>`,
- **Then** Coffer shallow-clones the repo, validates the SKILL.md, copies the subpath to `~/.coffer/skills/<name>/`, and persists `source.type=git` with `git_url`, `git_ref`, `git_subpath`.

### Scenario: reject SSRF in fetch

- **Given** the daemon is running,
- **When** the user attempts to fetch from a loopback or RFC1918 URL,
- **Then** the SSRF-guarded client rejects the request before any network round-trip is made.

### Scenario: enable a skill for a registered agent

- **Given** an agent `claude_code` is registered (per spec 004) and a skill `my-skill` is imported,
- **When** the user enables `my-skill` for `claude_code`,
- **Then** a directory symlink (or junction on Windows) is created at `<config_dir>/skills/my-skill` pointing to `~/.coffer/skills/my-skill/`, and a `skill_agent_bindings` row records the link.

### Scenario: disable a skill for an agent

- **Given** a skill is enabled for an agent and the target symlink exists,
- **When** the user disables it for that agent,
- **Then** the symlink is removed, the binding is marked disabled, and the master folder is unchanged.

### Scenario: enable for multiple agents

- **Given** two agents are registered,
- **When** the user enables one skill for both,
- **Then** two symlinks (one per agent) exist, both pointing to the same master folder.

### Scenario: refuse to overwrite a non-Coffer target

- **Given** the user has placed a regular file or directory at the would-be link path,
- **When** the user enables a skill for that agent,
- **Then** the operation is rejected; with `--force`, the existing target is backed up to `<path>.coffer-backup-<ts>` and the link is created.

### Scenario: update a Git-sourced skill

- **Given** a skill was fetched from a Git URL,
- **When** the user runs `coffer skill update <name>` and the upstream now serves different content,
- **Then** the master folder is replaced atomically with the new content, an audit entry is recorded, and enabled agents see the new content through their existing symlinks.

### Scenario: detect frontmatter name change on update

- **Given** an update would change SKILL.md frontmatter `name`,
- **When** the user runs update without `--allow-rename`,
- **Then** the update is rejected with the new name in the error message; with `--allow-rename`, the master folder is renamed and every enabled symlink is recreated under the new name.

### Scenario: detect drift in agent skill directories

- **Given** a binding exists but its target on disk has been deleted, replaced, or relinked,
- **When** the user runs `coffer skill verify`,
- **Then** the report lists each drift type with a suggested remedy and exits with a non-zero status; no automatic remediation occurs.

### Scenario: remove a skill cleans up all bindings

- **Given** a skill is enabled for two agents,
- **When** the user removes the skill,
- **Then** both target symlinks are removed, the bindings are cascade-deleted, the master folder is deleted, and an audit entry records the removal with a config snapshot.

### Scenario: removing an agent (per spec 004) cleans up its skill bindings

- **Given** an agent has one or more enabled skills,
- **When** the user removes the agent,
- **Then** spec 004's `on_delete` hook for the agent kind invokes the skill module to remove each binding and its symlink before the agent row is deleted; master folders are unchanged.

### Scenario: desktop and CLI cover every operation

- **Given** the daemon is running,
- **When** the user performs each operation via desktop and via `coffer skill ...`,
- **Then** the same effect is achieved in either surface and CLI provides `--json` for read operations.

### Scenario: audit skill lifecycle

- **Given** the user has performed a representative sequence of operations,
- **When** they view the audit log,
- **Then** each event appears with timestamp, actor, target, event type, and any payload (e.g., before/after content hashes for updates).

### Scenario: view a skill's files as a tree

- **Given** an imported skill whose master folder contains `SKILL.md` and a nested subdirectory with a file,
- **When** the user requests the skill's file listing,
- **Then** Coffer returns a recursive read-only tree rooted at the master folder, each node carrying its name, folder-relative path, type (`file`/`dir`), file size, and children, sorted directories-first then by name, with no symlink target that escapes the folder included.

### Scenario: view a single skill file's contents

- **Given** an imported skill that contains a readable text file,
- **When** the user requests that file's contents by its folder-relative path,
- **Then** Coffer returns the file's text, its true byte size, and `binary=false`/`truncated=false`; a non-existent file path returns a not-found error.

### Scenario: reject reading a path outside the skill folder

- **Given** an imported skill,
- **When** the user requests file contents for a path that resolves outside the master folder (`..` traversal, an absolute path, or an escaping symlink),
- **Then** the request is rejected with a `400` error before any file is read, and no content is returned.

## Requirements

### Functional Requirements

**Resource model**

- **FR-001**: System MUST register each managed skill as a Resource of kind `skill`, identified by `skill:<name>` where `<name>` comes from SKILL.md frontmatter.
- **FR-002**: System MUST validate skill configuration against a kind-specific schema with fields `source` (variant: `local_import` | `git`), `skill_md_name`, `skill_md_description`, `version_hash`, and `last_synced_from_source_at`.

**Canonical storage**

- **FR-003**: System MUST store each managed skill's content under `~/.coffer/skills/<name>/`, with that path as the single editable source of truth.
- **FR-004**: System MUST validate every imported or fetched skill folder against the AgentSkills specification: `SKILL.md` present, frontmatter `name` and `description` present and non-empty, no path-escape symlinks, total size within a configurable limit (default 50 MB).

**Sources**

- **FR-005**: System MUST support importing a skill from a local filesystem path; the original source path is recorded for provenance but is not retained as a live dependency.
- **FR-006**: System MUST support fetching a skill from a public Git URL with a ref and optional subpath, using a shallow clone through an SSRF-guarded client (per the Coffer constitution).
- **FR-007**: v1 MUST reject Git URLs that require authentication; private-repo support is a future-spec change.

**Per-agent delivery**

- **FR-008**: Each `(skill, agent)` binding is tracked in a `skill_agent_bindings` table recording whether the binding is enabled and the last successful link path.
- **FR-009**: Enabling a binding MUST create a directory symlink (POSIX) or directory junction (Windows) at `<config_dir>/skills/<skill-name>` pointing to `~/.coffer/skills/<skill-name>/`.
- **FR-010**: Disabling a binding MUST remove the target link without touching the master folder.
- **FR-011**: Enabling MUST refuse to overwrite an existing non-Coffer target without `--force`; `--force` backs up the existing target before creating the link.
- **FR-012**: When directory junctions are unavailable (e.g., FAT32, network share), System MAY fall back to copy mode for that target with an audit `degraded=true` flag; UI MUST surface the degradation.

**Updates**

- **FR-013**: System MUST support refreshing a Git-sourced skill on user demand; local-imported skills MUST be re-imported rather than updated.
- **FR-014**: System MUST detect and reject updates that change SKILL.md frontmatter `name` unless the user passes `--allow-rename`, which triggers an atomic master-folder rename and rebuild of every enabled symlink.

**Drift**

- **FR-015**: System MUST provide a `verify` operation that compares each enabled binding to its on-disk target and reports drift categories (missing link, tampered link, missing master, orphan master) with suggested remedies.
- **FR-016**: System MUST NOT automatically remediate drift; remediation requires an explicit user action.

**Lifecycle**

- **FR-017**: Removing a skill MUST remove every enabled per-agent symlink, cascade-delete bindings, delete the master folder, and audit the removal with a snapshot.
- **FR-018**: Removing an agent (via spec 004) MUST trigger an `on_delete` hook in the skill module that removes that agent's bindings and symlinks before the agent row is deleted.

**Surfaces**

- **FR-019**: Every management operation MUST be available through (a) the REST API, (b) the `coffer skill ...` CLI with `--json`, and (c) the desktop Skills page.
- **FR-021**: System MUST expose a read-only view of a skill's master folder: a recursive file tree (name, folder-relative path, type, size, children) and the contents of an individual file. Reads MUST be contained to the master folder — any path that resolves outside it (`..` traversal, absolute path, or escaping symlink) MUST be rejected. File reads MUST be size-capped (truncating with a `truncated` flag) and MUST flag non-UTF-8 / NUL-containing files as binary with empty content. No mutation, no symlink-following out of the folder.

**Observability**

- **FR-020**: System MUST record an audit entry for every import, fetch, enable, disable, update, rename, remove, and drift remediation event.

### Key Entities

- **Skill**: A Resource of kind `skill`, identified by `skill:<name>` (name from SKILL.md frontmatter). Holds source provenance, content hash, and metadata; the content folder lives on disk at `~/.coffer/skills/<name>/`.
- **Skill Source**: A discriminated record (`local_import` or `git`) capturing where the skill came from. For Git, it includes URL, ref, and optional subpath. For local imports, it includes the original path for informational purposes only.
- **Skill–Agent Binding**: A row joining one skill Resource and one agent Resource (kind `agent`, per spec 004), with an `enabled` flag and last-link-path metadata. Symlink existence on disk is the live representation; binding state is the persistent representation.
- **Drift Report**: An ephemeral structure produced by `verify` listing each binding whose on-disk target disagrees with the binding state, categorized by drift type with a suggested remedy.

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user can import their existing `~/.claude/skills/<one-skill>/` folder, enable it for the auto-detected Claude Code agent, and reach the "ready" state within 60 seconds.
- **SC-002**: Fetching a 1-MB public Git skill completes in under 10 seconds on a normal home connection, including validation and copy.
- **SC-003**: Enabling a skill for two agents creates two valid directory symlinks (or junctions on Windows), and each agent's reading process sees identical SKILL.md content.
- **SC-004**: After manually deleting an agent-side symlink, `coffer skill verify` identifies it as drift within 5 seconds and exits with a non-zero status.
- **SC-005**: Removing a skill that is enabled for two agents leaves no residual symlinks, no residual master folder, and no orphan binding rows in the database.
- **SC-006**: Every Acceptance Scenario in this spec is covered by at least one test marked `acceptance(spec="005-skill-manager", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-007**: The full `make verify` suite passes locally and in CI; `make verify-all` (adding e2e) passes on macOS and Linux; Windows tests pass for both junction mode and copy-fallback mode.
- **SC-008**: No SKILL.md content ever leaves the user's machine except where the user explicitly fetches a known public URL; verified by an automated network-egress scan during integration tests.

## Assumptions

- Spec 004-agent-registry has shipped (PR #25); the agent kind, its CRUD, audit, and `on_delete` hook are available.
- The kind-agnostic Resource framework, audit log, and `<kind>:<name>` identity scheme defined by spec 001-mcp-gateway are in place.
- The application shell from spec 002-ui-shell — sidebar IA, layout, routing skeleton, and design system — is in place; the desktop Skills page is a feature surface that renders within that shell and fills the `/skills` nav slot 002-ui-shell reserved as a placeholder.
- Skills follow the open AgentSkills standard (`SKILL.md` with `name`/`description` frontmatter at minimum) as published at agentskills.io; non-conforming folders are out of scope.
- v1 supports public Git URLs only; authenticated upstream skill sources are future work.
- Local-imported skills are point-in-time copies; the source path is recorded for traceability, not for sync.
- Windows users have directory-junction support on their filesystem; FAT32 and network shares fall back to copy mode.
- v2 will explore: marketplace browsing (agentskills.io API), agent-to-agent skill recommendations, project-local skills (`.claude/skills/` in repo), and private Git sources via credential refs.
