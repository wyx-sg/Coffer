# Feature Specification: Skill Manager

**Feature Branch**: `feature/skill-manager`
**Created**: 2026-05-22
**Status**: Accepted
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

The user opens Coffer, sees the Skills page rendered as a data table (search, filter, pagination, row multi-select for bulk actions), can import via file picker or paste a Git URL, and browse the list. The Skills page manages the skill resource itself, not its per-agent bindings: clicking a skill opens a detail view with an Overview metadata tab and a Files tab (file tree + a read-only file viewer that renders Markdown and shows other text files raw). The viewer does not edit content; to change a file the user opens it (or its containing folder) in their own external editor or file manager — every file and folder offers "open in external editor", "reveal in file manager", and "copy absolute path" affordances. Per-agent enable/disable lives on the agent detail page — the agent's "Skills" tab lists the skills bound to that agent with per-binding toggles.

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

### User Story 10 — Surface and adopt unmanaged skills (Priority: P2)

Agents accumulate skills Coffer never delivered — hand-copied folders, skills installed by other tools. Today these are invisible: the agent's Skills tab lists only Coffer-managed bindings. The user opens the tab and additionally sees the **unmanaged** skills found in the agent's skill locations — `<config_dir>/skills` for both types, plus `~/.agents/skills` for Codex (the newer standard location Codex also reads). Coffer-managed links and Codex's `.system` internal entries are excluded. For each unmanaged skill the user can **adopt** it (move it into the master store, leave a managed link in its place so the agent keeps seeing it, and record a binding) or delete it.

**Why this priority**: The hub model only works if existing assets can flow into it. Adoption is User Story 1's import, made one-click and in-place.

**Independent Test**: Place a valid skill folder in a registered agent's `skills/` directory; open the agent's Skills tab; observe it listed as unmanaged; adopt it; verify the master copy exists at `~/.coffer/skills/<name>/`, the original path is now a managed symlink, and a binding row exists.

**Covering scenarios**:

- list unmanaged skills across an agent's skill locations
- adopt an unmanaged skill into the master store
- reject adopting an invalid or conflicting unmanaged skill
- delete an unmanaged skill
- exclude managed links and system entries from the unmanaged scan

---

### User Story 11 — Follow the master library (Priority: P2)

Per-skill bindings are precise but chatty: every new skill must be enabled agent by agent. The user flips a per-agent **"follow the master library"** switch; from then on, every skill in the master store is delivered to that agent automatically — new skills appear on registration, removed skills disappear — with a per-agent exclusion list for the rare opt-outs. Per-skill bindings remain the mode for agents that don't follow. Turning follow off keeps the currently delivered set as explicit bindings, so nothing vanishes by surprise.

**Why this priority**: This is "configure once, share everything" for skills — the filesystem counterpart of the MCP gateway's one-entry-serves-all model.

**Independent Test**: Enable follow for an agent with three master skills; verify three links exist; register a fourth skill; verify its link appears without further action; exclude one skill; verify its link is removed while the rest stay.

**Covering scenarios**:

- enable follow-all and deliver every master skill
- auto-deliver new skills to following agents
- auto-remove deleted skills from following agents
- exclude a skill from a following agent
- disable follow-all preserving current bindings

---

### Edge Cases

- **Skill name collision on import**: Rejected; user must rename via SKILL.md frontmatter and retry.
- **Frontmatter name changes between updates**: Update rejected by default; `--allow-rename` performs an atomic rename of the master folder and rebuilds all enabled symlinks. The audit log retains the historical name on each prior event; the current Resource row's name reflects the post-rename value.
- **Master folder size exceeds limit (default 50 MB)**: Import or fetch rejected with the configured cap and a hint to adjust settings.
- **Git fetch hits a private repo or auth-required URL**: Rejected; v1 does not handle credentials for upstream skill sources.
- **Git fetch hits an unreachable host, DNS failure, or timeout**: Operation aborts cleanly with a network error; no master folder is partially written and no Resource row is persisted.
- **Symlink/junction creation fails on Windows (FAT32 or network share)**: Falls back to copy mode for that target with an audit flag `degraded=true`; UI shows a warning chip.
- **User edits `SKILL.md` in an external editor from inside an agent's `config_dir/skills` folder**: Coffer's UI never edits file content; the user makes the change in their own editor (reached via Coffer's "open in external editor" / "reveal in file manager" affordances or directly). Because the agent's path is a symlink to master, the external edit lands in master and is visible to all other agents on next read; no drift is detected.
- **User deletes a Coffer-managed file from inside an agent's `config_dir/skills` folder**: Master is affected (same reason); next `verify` flags any other agents whose links no longer resolve consistently.
- **Removing an agent (per spec 004) while it has skill bindings**: Spec 004 defines the agent kind's `on_delete` seam; the 005-skill-manager spec supplies the `cleanup_bindings_for_agent` callback at the composition root, so removing an agent first cleans up that agent's bindings and any associated symlinks before the agent row is deleted.
- **Agent's `config_dir` is moved or removed externally**: The next sync operation surfaces the failure; `verify` reports the affected bindings; user remediates by updating the agent's `config_dir` or removing the agent.
- **`~/.agents/skills` is shared with other tools**: The scan lists what it finds and classifies only Coffer's own links as managed; everything else is unmanaged. Deletion is always an explicit user action — Coffer never garbage-collects another tool's skills.
- **Unmanaged entry is a symlink pointing outside the master store**: Listed as unmanaged-but-not-adoptable (adopting would move someone else's source of truth); the user can follow the link's target manually or delete the link.
- **Unmanaged skill without a valid SKILL.md**: Listed with `valid=false` and the reason; it can be deleted but not adopted until it validates.
- **Follow-all enabled while a target path holds a non-Coffer folder of the same name**: That skill is reported as a conflict (same rule as FR-011) instead of being overwritten; the rest of the master store is delivered normally.
- **Per-agent delivery target**: Folder-mode agents deliver into the skill subpath under their config dir — `<config_dir>/skills/<name>` for Claude Code, Codex, and OpenCode; `<config_dir>/workspace/skills/<name>` for OpenClaw. Hermes (`external_dir`) folder-delivers into a Coffer-owned external directory (`~/.coffer/agent-skills/<agent>/<name>`) that Coffer registers under `skills.external_dirs` in the agent's `config.yaml`. Each agent's mode, subpath, and registration come from the capability manifest, so adding an agent's delivery target is data, not a new branch.
- **Agent whose delivery mode is not yet wired (Cursor)**: Cursor's `rules_mdc` is a recognized delivery-mode extension point whose end-to-end delivery is deferred — its `.mdc` rules are project-scoped, with no officially-supported global/agent-level `.mdc` location to deliver an agent-wide skill into (global User Rules live in Cursor's internal settings, not files). Enabling a skill for such an agent is refused with an explicit "delivery mode not yet supported" error (HTTP 422) before any filesystem write, rather than mis-delivering via the folder model; the follow / relink reconcilers skip these agents so registration and policy changes still succeed.

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

### Scenario: reject a skill with an over-long description

- **Given** the daemon is running,
- **When** the user imports a folder whose SKILL.md `description` exceeds 1024 characters,
- **Then** the request is rejected as invalid frontmatter, and nothing is written to `~/.coffer/skills/` or the database.

### Scenario: recognize optional agentskills.io frontmatter fields

- **Given** a valid SKILL.md that also declares `license` and the experimental `allowed-tools`,
- **When** the folder is validated,
- **Then** validation succeeds and the parsed frontmatter retains `license` and a normalized `allowed-tools` list (rather than discarding them).

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

### Scenario: scan flags risky content on import

- **Given** a skill folder whose bundled script pipes a download into a shell,
- **When** the user imports it,
- **Then** the skill is registered with a `critical` scan verdict, the scan is audited, and the skill is NOT auto-delivered to following agents (auto-bind is skipped) until the risk is acknowledged.

### Scenario: refuse to enable an unacknowledged risky skill

- **Given** an imported skill with a `high`/`critical` scan verdict that has not been acknowledged,
- **When** the user tries to enable it for an agent,
- **Then** the request is rejected with `conflict` (409) and no link is created.

### Scenario: acknowledge risk then enable a flagged skill

- **Given** a flagged skill whose risk the user has explicitly acknowledged,
- **When** the user enables it for an agent,
- **Then** the link is created and the binding is recorded; a later content change resets the acknowledgment.

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
- **Then** Coffer returns a recursive read-only tree rooted at the master folder, each node carrying its name, folder-relative path, absolute on-disk path, type (`file`/`dir`), file size, and children, sorted directories-first then by name, with no symlink target that escapes the folder included.

### Scenario: view a single skill file's contents

- **Given** an imported skill that contains a readable text file,
- **When** the user requests that file's contents by its folder-relative path,
- **Then** Coffer returns the file's text, its true byte size, its absolute on-disk path and its containing folder's absolute path, and `binary=false`/`truncated=false`; a non-existent file path returns a not-found error.

### Scenario: reject reading a path outside the skill folder

- **Given** an imported skill,
- **When** the user requests file contents for a path that resolves outside the master folder (`..` traversal, an absolute path, or an escaping symlink),
- **Then** the request is rejected with a `400` error before any file is read, and no content is returned.

### Scenario: programmatically overwrite a skill file via the write API

- **Given** an imported skill that contains an existing text file,
- **When** a programmatic client (REST/CLI) saves new contents for that file by its folder-relative path,
- **Then** Coffer overwrites the file atomically and a subsequent read returns the new contents; writing a non-existent path, a path outside the master folder, an existing binary file, or content over the size cap is rejected (`404`/`400`) and the file is left unchanged. (The in-app UI does not call this endpoint to edit content; it is a programmatic write surface only.)

### Scenario: list unmanaged skills across an agent's skill locations

- **Given** a registered `codex` agent with one Coffer-managed link in `<config_dir>/skills`, one hand-copied skill folder there, and another skill folder in `~/.agents/skills`,
- **When** the user lists the agent's unmanaged skills,
- **Then** Coffer returns exactly the two hand-placed skills — each with name, path, location, and a `valid` flag from SKILL.md validation — and excludes the managed link.

### Scenario: adopt an unmanaged skill into the master store

- **Given** an unmanaged skill folder with a valid SKILL.md whose name collides with no master skill,
- **When** the user adopts it,
- **Then** Coffer validates it per FR-004, moves the folder to `~/.coffer/skills/<name>/`, registers the `skill` resource, replaces the original path with the managed link, records a binding for that agent, and audits the adoption — and on any failure the original folder is left exactly where and as it was.

### Scenario: reject adopting an invalid or conflicting unmanaged skill

- **Given** an unmanaged entry that lacks a valid SKILL.md, collides with an existing master skill's name, or is a symlink pointing outside the master store,
- **When** the user attempts to adopt it,
- **Then** the request is rejected with a reason-specific error (invalid: `unprocessable_entity` 422; name conflict: `conflict` 409; foreign link: `unprocessable_entity` 422), and nothing is moved, registered, or linked.

### Scenario: delete an unmanaged skill

- **Given** an unmanaged skill folder in an agent's skill location,
- **When** the user deletes it (an explicit, confirmed action),
- **Then** the folder is removed from disk, an audit entry is recorded, and no master content or binding is touched.

### Scenario: exclude managed links and system entries from the unmanaged scan

- **Given** an agent's skill directory containing Coffer-managed links and (for Codex) a `.system` entry,
- **When** the user lists unmanaged skills,
- **Then** neither the managed links nor the `.system` entry appear in the result.

### Scenario: enable follow-all and deliver every master skill

- **Given** a registered agent not yet following, and three skills in the master store,
- **When** the user enables the agent's follow-master-library switch,
- **Then** the sync engine delivers all three skills to the agent (links + binding rows) and the agent's effective set equals the master store minus its (empty) exclusion list.

### Scenario: auto-deliver new skills to following agents

- **Given** an agent with follow enabled,
- **When** a new skill is registered in the master store (import, fetch, or adoption),
- **Then** the daemon delivers it to that agent without further user action.

### Scenario: auto-remove deleted skills from following agents

- **Given** an agent with follow enabled and a delivered skill,
- **When** that skill is removed from the master store,
- **Then** the agent's link and binding are cleaned up as part of the removal.

### Scenario: exclude a skill from a following agent

- **Given** an agent with follow enabled and a delivered skill,
- **When** the user excludes that skill for this agent,
- **Then** its link and binding are removed, the skill joins the agent's exclusion list, and later master changes never re-deliver it until the exclusion is lifted.

### Scenario: disable follow-all preserving current bindings

- **Given** an agent with follow enabled and several delivered skills,
- **When** the user disables the follow switch,
- **Then** every currently delivered skill remains as an explicit per-skill binding with its link intact, and subsequent master-store additions are no longer auto-delivered.

### Scenario: deliver a skill to OpenCode under skills/

- **Given** a registered OpenCode agent and an imported master skill,
- **When** the skill is delivered to the agent,
- **Then** it lands at `<config_dir>/skills/<name>` (with its `SKILL.md`) resolving to the canonical master folder.

### Scenario: deliver a skill to OpenClaw under workspace/skills/

- **Given** a registered OpenClaw agent and an imported master skill,
- **When** the skill is delivered to the agent,
- **Then** it lands at `<config_dir>/workspace/skills/<name>` (resolving to the master folder) and not at the flat `skills/` location.

### Scenario: deliver a skill to an external-dir agent and register the directory

- **Given** a registered Hermes agent (`external_dir` delivery) and an imported master skill,
- **When** the skill is delivered to the agent,
- **Then** the skill folder lands in a Coffer-owned external directory (resolving to the master folder) — not under the agent's own `skills/` — and that directory is registered under `skills.external_dirs` in the agent's `config.yaml`, preserving the user's other config keys/comments and de-duplicating by resolved path.

### Scenario: deregister an external-dir agent's directory when its last skill is removed

- **Given** a Hermes agent whose Coffer-owned external directory is registered in its `config.yaml`,
- **When** the last delivered skill is disabled (or the agent is deleted),
- **Then** the Coffer entry is removed from `skills.external_dirs` (pruning the now-empty list) while any directories the user added themselves are left intact.

### Scenario: enabling a skill for a non-folder-delivery agent fails cleanly

- **Given** a registered agent whose skill-delivery mode is not folder-based (Cursor's `rules_mdc`),
- **When** the user enables a skill for that agent,
- **Then** the request is rejected with `unprocessable_entity` (422) before any filesystem write, and follow-driven auto-delivery skips the agent without error.

## Requirements

### Functional Requirements

**Resource model**

- **FR-001**: System MUST register each managed skill as a Resource of kind `skill`, identified by `skill:<name>` where `<name>` comes from SKILL.md frontmatter.
- **FR-002**: System MUST validate skill configuration against a kind-specific schema with fields `source` (variant: `local_import` | `git`), `skill_md_name`, `skill_md_description`, `version_hash`, and `last_synced_from_source_at`.

**Canonical storage**

- **FR-003**: System MUST store each managed skill's content under `~/.coffer/skills/<name>/`, with that path as the single editable source of truth.
- **FR-004**: System MUST validate every imported or fetched skill folder against the AgentSkills specification: `SKILL.md` present; frontmatter `name` present and non-empty (lowercase alphanumerics, hyphen, or underscore, ≤64 chars) and `description` present, non-empty, and ≤1024 chars; no path-escape symlinks; total size within a configurable limit (default 50 MB). A folder that violates any of these is rejected with `unprocessable_entity` (422) and nothing is persisted.
- **FR-027**: System MUST recognize the optional agentskills.io frontmatter fields it understands — `license` and the experimental `allowed-tools` — parsing and retaining them rather than discarding them, while tolerating any other unrecognized frontmatter field so non-Coffer-authored skills validate cleanly. `allowed-tools` accepts either a list or a comma/whitespace-separated string and is normalized to a list of tool names; a malformed value is tolerated (treated as absent), never a validation failure. Likewise a non-string `license` scalar (e.g. an unquoted year or version) is coerced to a string rather than rejected.

**Content trust (trust layer L2)**

- **FR-028**: System MUST run a heuristic content scan over a skill's files on every ingest (import, fetch, adopt) and on every content-changing operation (update that changes `SKILL.md`, and in-place file edits), and MUST cache the result on the skill — a verdict (`low`/`medium`/`high`/`critical` or none), a findings count, the ruleset version, and the scan time. The scan is advisory: it never blocks ingest and a clean result is not a safety guarantee (Coffer delivers skills but does not execute them, so it cannot enforce runtime behavior — see ADR-027). A user MUST be able to re-scan a managed skill on demand. Every scan is audited.
- **FR-029**: When a skill's scan verdict is `high` or `critical`, System MUST refuse to enable it for an agent until the user explicitly acknowledges the risk; the refusal is reported as `conflict` (409) and the follow/auto-bind reconcilers skip such a skill (audited) rather than delivering it. Acknowledgment is an explicit, audited action and MUST be reset whenever the skill's content subsequently changes (an acknowledgment is for the content it was made against). Adoption is exempt — it consolidates a skill already present in the agent's workspace, so it records the verdict but is not blocked.

**Sources**

- **FR-005**: System MUST support importing a skill from a local filesystem path; the original source path is recorded for provenance but is not retained as a live dependency.
- **FR-006**: System MUST support fetching a skill from a public Git URL with a ref and optional subpath, using a shallow clone through an SSRF-guarded client (per the Coffer constitution).
- **FR-007**: v1 MUST reject Git URLs that require authentication; private-repo support is a future-spec change.

**Per-agent delivery**

- **FR-008**: Each `(skill, agent)` binding is tracked in a `skill_agent_bindings` table recording whether the binding is enabled and the last successful link path.
- **FR-009**: Enabling a binding MUST create a directory symlink (POSIX) or directory junction (Windows) at `<config_dir>/skills/<skill-name>` pointing to `~/.coffer/skills/<skill-name>/`.
- **FR-010**: Disabling a binding MUST remove the target link without touching the master folder.
- **FR-011**: Enabling MUST refuse to overwrite an existing non-Coffer target without `--force`; `--force` backs up the existing target before creating the link.
- **FR-012**: When symlinks/directory junctions are unavailable (e.g., FAT32, network share), System MAY fall back to copy mode for that target; the binding records `link_mode=copy_fallback` (audited as `mode: copy_fallback` on the enable event) and the UI MUST surface the degradation (the agent Skills tab shows a "Copied" warning chip on such bindings).

**Updates**

- **FR-013**: System MUST support refreshing a Git-sourced skill on user demand; local-imported skills MUST be re-imported rather than updated.
- **FR-014**: System MUST detect and reject updates that change SKILL.md frontmatter `name` unless the user passes `--allow-rename`, which triggers an atomic master-folder rename and rebuild of every enabled symlink.

**Drift**

- **FR-015**: System MUST provide a `verify` operation that compares each enabled binding to its on-disk target and reports drift categories (missing link, tampered link, missing master, orphan master) with suggested remedies.
- **FR-016**: System MUST NOT automatically remediate drift; remediation requires an explicit user action.

**Unmanaged skills (workspace amendment)**

- **FR-022**: System MUST scan a registered agent's skill locations — `<config_dir>/skills` for both types, plus `~/.agents/skills` for `codex` — and list **unmanaged** entries: everything that is not a Coffer-managed link (a link whose target resolves inside `~/.coffer/skills/`) and not Codex's `.system` entry. Each result carries name, path, location, and a `valid` flag (FR-004 validation) with the failure reason when invalid. The scan is read-only and derived at request time.
- **FR-023**: Users MUST be able to adopt a valid unmanaged skill. Adoption validates the folder per FR-004, moves it to `~/.coffer/skills/<name>/`, registers the `skill` resource, delivers the managed link (FR-009), and records an enabled binding for that agent — in that order, with any failure before registration leaving the original folder unmoved and unchanged (after registration the master copy is authoritative; a delivery failure is surfaced and retried via the binding, never rolled back). The managed link is always delivered to the agent's canonical delivery location `<config_dir>/skills/<name>`: adopting from `<config_dir>/skills` replaces the original path in place, while adopting from `~/.agents/skills` consolidates — the original folder there is removed and the link lands in `<config_dir>/skills` (Codex reads both locations, so the agent keeps seeing the skill). Name collisions are rejected with `conflict` (409); invalid folders and symlinks pointing outside the master store are rejected with `unprocessable_entity` (422). Audited as an adoption event.
- **FR-024**: Users MUST be able to delete an unmanaged entry as an explicit, confirmed action. Deletion removes only that entry from disk, never master content or bindings, and is audited.

**Follow the master library (workspace amendment)**

- **FR-025**: Each agent MUST carry a follow-master-library flag and a per-agent skill exclusion list (stored on the agent resource's config, spec 004). While following, the agent's effective skill set is the entire master store minus its exclusions; the sync engine MUST reconcile deliveries when the flag changes, when a skill is registered or removed, and when the exclusion list changes. Conflicts at target paths follow FR-011 (report, never overwrite). Disabling the flag MUST preserve the currently delivered skills as explicit per-skill bindings. The flag defaults to enabled for newly registered agents, matching the pre-amendment auto-bind behavior.
- **FR-026**: Unmanaged-skill and follow operations MUST be available through the REST API, the `coffer agent skill …` / `coffer skill …` CLI (with `--json` on reads), and the agent's Skills tab in the desktop app.

**Lifecycle**

- **FR-017**: Removing a skill MUST remove every enabled per-agent symlink, cascade-delete bindings, delete the master folder, and audit the removal with a snapshot.
- **FR-018**: Removing an agent (via spec 004) MUST trigger an `on_delete` hook in the skill module that removes that agent's bindings and symlinks before the agent row is deleted.

**Surfaces**

- **FR-019**: Every management operation MUST be available through (a) the REST API, (b) the `coffer skill ...` CLI with `--json`, and (c) the desktop Skills page.
- **FR-021**: System MUST expose a **read-only** view of a skill's master folder: a recursive file tree (name, folder-relative path, absolute on-disk path, type, size, children) and the contents of an individual file (with its absolute on-disk path and containing folder's absolute path). Markdown files render as formatted Markdown; other text files show raw. The in-app UI viewer is read-only and never edits file content. Reads MUST be contained to the master folder — any path that resolves outside it (`..` traversal, absolute path, or escaping symlink) MUST be rejected. File reads MUST be size-capped (truncating with a `truncated` flag) and MUST flag non-UTF-8 / NUL-containing files as binary with empty content. No symlink-following out of the folder.
- **FR-027**: The in-app file viewer MUST offer, at both file and containing-folder granularity, affordances to (a) open the target in the user's preferred external editor (the global preference is specced in 002-ui-shell; default = the OS default application), (b) reveal the target in the OS file manager (Finder / Explorer), and (c) copy the target's absolute path. On desktop (Tauri) open and reveal perform the real OS action; on the web surface, where the host OS is out of reach, all three fall back to copy-absolute-path. These affordances replace in-app content editing: the user edits in their own external editor.
- **FR-028**: System MUST provide a **programmatic** (REST/CLI) write that overwrites an **existing text file** in the master folder, under the same containment guard and size cap as FR-021; it MUST refuse to create new files/directories here, to write outside the folder, or to overwrite a binary file with text. The write MUST be atomic with no symlink-following out of the folder. This write surface is for programmatic clients only; the in-app UI does not use it to edit content (see FR-027).

**Observability**

- **FR-020**: System MUST record an audit entry for every import, fetch, enable, disable, update, rename, remove, and drift remediation event.

### Key Entities

- **Skill**: A Resource of kind `skill`, identified by `skill:<name>` (name from SKILL.md frontmatter). Holds source provenance, content hash, and metadata; the content folder lives on disk at `~/.coffer/skills/<name>/`.
- **Skill Source**: A discriminated record (`local_import` or `git`) capturing where the skill came from. For Git, it includes URL, ref, and optional subpath. For local imports, it includes the original path for informational purposes only.
- **Skill–Agent Binding**: A row joining one skill Resource and one agent Resource (kind `agent`, per spec 004), with an `enabled` flag and last-link-path metadata. Symlink existence on disk is the live representation; binding state is the persistent representation.
- **Drift Report**: An ephemeral structure produced by `verify` listing each binding whose on-disk target disagrees with the binding state, categorized by drift type with a suggested remedy.
- **Unmanaged Skill**: A derived (never stored) view of a skill-shaped entry found in an agent's skill locations that Coffer does not manage — name, path, location, `valid` flag. The filesystem is the source of truth; adoption or deletion are the only mutations.
- **Follow Policy**: Per-agent state (flag + exclusion list, stored on the agent resource's config per spec 004) declaring that the agent receives the entire master store. Bindings remain the persistent delivery record; the policy drives the sync engine's reconciliation.

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
- **SC-009**: With follow enabled, a newly registered skill is delivered to the following agent within 5 seconds, with no user action beyond the registration itself.
- **SC-010**: On a machine with a mix of managed links and hand-placed skills, the unmanaged scan lists exactly the hand-placed entries — zero managed links, zero `.system` entries — verified by integration tests over a constructed fixture tree.

## Assumptions

- Spec 004-agent-registry has shipped (PR #25); the agent kind, its CRUD, audit, and `on_delete` hook are available.
- The kind-agnostic Resource framework, audit log, and `<kind>:<name>` identity scheme defined by spec 001-mcp-gateway are in place.
- The application shell from spec 002-ui-shell — sidebar IA, layout, routing skeleton, and design system — is in place; the desktop Skills page is a feature surface that renders within that shell and fills the `/skills` nav slot 002-ui-shell reserved as a placeholder.
- Skills follow the open AgentSkills standard (`SKILL.md` with `name`/`description` frontmatter at minimum) as published at agentskills.io, validated against the standard's exact constraints (`name` ≤64 chars, `description` ≤1024 chars) with the optional `license` and experimental `allowed-tools` fields recognized; non-conforming folders are out of scope.
- v1 supports public Git URLs only; authenticated upstream skill sources are future work.
- Local-imported skills are point-in-time copies; the source path is recorded for traceability, not for sync.
- Windows users have directory-junction support on their filesystem; FAT32 and network shares fall back to copy mode.
- Delivery stays at `<config_dir>/skills` for both agent types. Codex additionally reads `~/.agents/skills` (its newer standard location) and treats `<config_dir>/skills` as a backward-compatible legacy location — the unmanaged scan covers both; migrating Coffer's delivery target is a recorded decision deferred to a future change.
- The follow-master-library flag and exclusion list live on the agent resource's config (spec 004's schema); this spec owns their delivery semantics.
- v2 will explore: marketplace browsing (agentskills.io API), agent-to-agent skill recommendations, project-local skills (`.claude/skills/` in repo), and private Git sources via credential refs.
