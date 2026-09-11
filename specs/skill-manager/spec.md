# Feature Specification: Skill Manager

**Feature Branch**: `feature/skill-manager`
**Created**: 2026-05-22
**Status**: Accepted
**Input**: User description: "Coffer manages portable AI skills using the open AgentSkills standard (agentskills.io). One canonical store lives at `~/.coffer/skills/`; per-agent visibility is a directory symlink/junction into the `skills/` subfolder of each agent's config directory. Users can import skills from local paths; each skill's own `enabled` flag and `scope` decide which registered agents it is delivered to. v1 supports Claude Code and Codex CLI as sync targets (each registered as a Resource of kind `agent` per spec agent-registry-agent-registry)."

## User Scenarios & Testing

### User Story 1 — Import an existing skill folder (Priority: P1)

A developer already has skills in `~/.claude/skills/` (or elsewhere on disk). They import them into Coffer to make them portable across agents and centrally managed.

**Why this priority**: Migrating existing assets is most users' day-zero need. Without import, Coffer has no skills to manage.

**Independent Test**: From the command line, import an existing skill folder; verify the canonical copy exists at `~/.coffer/skills/<name>/`; verify the skill appears in `coffer skill list`.

**Covering scenarios**:

- import a valid skill folder
- reject import when SKILL.md is missing or has invalid frontmatter
- reject import on duplicate skill name (unless overwrite is requested)
- re-import with overwrite replaces the existing skill
- reject import containing path-escape symlinks

---


### User Story 3 — Choose which agents a skill reaches (Priority: P1)

The developer wants this skill available in Claude Code but not in Codex. They set the skill's **scope** to `["claude_code"]`, and Coffer delivers it there — a directory symlink into the `skills/` subfolder of that agent's config directory — and nowhere else. Narrowing the scope later reclaims the copies the excluded agents were holding.

**Why this priority**: This is the core "unify management" value. Without a per-agent delivery grant, Coffer has no advantage over copying files manually.

**Independent Test**: Register a Claude Code agent (per spec agent-registry); import a skill scoped to that agent; verify a directory symlink appears at `<config_dir>/skills/<skill-name>` pointing to `~/.coffer/skills/<skill-name>/`.

**Covering scenarios**:

- deliver a skill to a registered agent
- reclaim a skill from an agent (link removed, master untouched)
- deliver one skill to multiple agents (multiple links to one master)
- refuse to overwrite a non-Coffer target

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

### User Story 6 — Manage skills through the web UI (Priority: P2)

The user opens Coffer, sees the Skills page rendered as a data table (search, filter, pagination, row multi-select for bulk actions), can import via file picker and browse the list. The Skills page manages the skill resource itself, not its per-agent bindings: clicking a skill opens a detail view with an Overview metadata tab and a Files tab (file tree + a read-only file viewer that renders Markdown and shows other text files raw). The viewer does not edit content; to change a file the user opens it (or its containing folder) in their own external editor or file manager — every file and folder offers "open in external editor" and "reveal in file manager" affordances, performed by the local daemon. The delivery decision is made on the skill — its `enabled` switch and its scope — so the agent detail page reports rather than decides: the agent's "Skills" tab lists the skills currently delivered to that agent, read-only with respect to delivery.

**Why this priority**: Non-CLI users need a visual surface for daily management.

**Independent Test**: Open the web UI → Skills → import a folder via picker → see it listed in the table → open the skill and set its scope to one agent → confirm the symlink exists on disk and the agent's Skills tab lists the skill as delivered.

**Covering scenarios**:

- import a skill via the web UI file picker
- set a skill's scope via the web UI and see the delivered set follow
- surface drift count via a UI notification

---

### User Story 7 — Same operations from the command line (Priority: P2)

The developer scripts skill setup across machines via `coffer skill ...` subcommands with `--json` output.

**Independent Test**: A bash script imports skills, enables both for two agents, lists state, verifies drift, all without GUI.

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

Every import, delivery, reclaim, and remove is auditable.

**Independent Test**: Perform a representative sequence; view audit log; one row per change with actor, target, and event type.

**Covering scenarios**:

- audit import, delivery, reclaim, remove

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

### User Story 11 — One rule decides where a skill lands (Priority: P2)

The user should not have to configure delivery twice. A skill's own two fields settle it: `enabled` says whether the skill is live at all, and `scope` says which agents it reaches. A freshly imported skill has no scope, so it reaches every registered agent with no per-agent setup — "configure once, share everything", the filesystem counterpart of the MCP gateway's one-entry-serves-all model. When a skill only belongs in one place, the user narrows its scope and Coffer reclaims the copies the excluded agents were holding. When a skill should reach nobody for a while, the user disables it and every delivered copy is reclaimed; re-enabling redelivers it wherever the scope still grants it.

**The trade-off, stated plainly**: there is no longer a single per-agent "this agent gets nothing" switch. To exclude one agent from everything, remove it from each skill's scope — which is exactly how `mcp_server` resources already work. Per-agent exclusion of a specific skill is unchanged in power; it just moves from the agent side to the skill side.

**Why this priority**: One delivery rule instead of three overlapping ones is what makes the delivered set predictable from what the user can see on the skill.

**Independent Test**: Register two agents and import three unscoped skills; verify six links exist; scope one skill to a single agent; verify the other agent's copy is reclaimed; scope a second skill to `[]`; verify both its copies are reclaimed; disable a third skill and verify its copies go, then re-enable it and verify they come back.

**Covering scenarios**:

- a skill with no scope reaches every registered agent
- a skill scoped to no agent reaches nobody
- import delivers a skill only where its scope grants it
- disabling a skill reclaims every delivered copy
- re-enabling a skill redelivers it

---

### Edge Cases

- **Skill name collision on import**: Rejected by default; the user either renames via SKILL.md frontmatter and retries, or re-imports with `overwrite` (`--force`) to replace the existing skill in place — its per-agent bindings and delivered symlinks are preserved.
- **Master folder size exceeds limit (default 50 MB)**: Import rejected with the configured cap and a hint to adjust settings.
- **Symlink/junction creation fails on Windows (FAT32 or network share)**: Falls back to copy mode for that target with an audit flag `degraded=true`; UI shows a warning chip.
- **User edits `SKILL.md` in an external editor from inside an agent's `config_dir/skills` folder**: Coffer's UI never edits file content; the user makes the change in their own editor (reached via Coffer's "open in external editor" / "reveal in file manager" affordances or directly). Because the agent's path is a symlink to master, the external edit lands in master and is visible to all other agents on next read; no drift is detected.
- **User deletes a Coffer-managed file from inside an agent's `config_dir/skills` folder**: Master is affected (same reason); next `verify` flags any other agents whose links no longer resolve consistently.
- **Removing an agent (per spec agent-registry) while it has skill bindings**: Spec agent-registry defines the agent kind's `on_delete` seam; the 005-skill-manager spec supplies the `cleanup_bindings_for_agent` callback at the composition root, so removing an agent first cleans up that agent's bindings and any associated symlinks before the agent row is deleted.
- **Agent's `config_dir` is moved or removed externally**: The next sync operation surfaces the failure; `verify` reports the affected bindings; user remediates by updating the agent's `config_dir` or removing the agent.
- **`~/.agents/skills` is shared with other tools**: The scan lists what it finds and classifies only Coffer's own links as managed; everything else is unmanaged. Deletion is always an explicit user action — Coffer never garbage-collects another tool's skills.
- **Unmanaged entry is a symlink pointing outside the master store**: Listed as unmanaged-but-not-adoptable (adopting would move someone else's source of truth); the user can follow the link's target manually or delete the link.
- **Unmanaged skill without a valid SKILL.md**: Listed with `valid=false` and the reason; it can be deleted but not adopted until it validates.
- **A skill is delivered while a target path holds a non-Coffer folder of the same name**: That skill is reported as a conflict (same rule as FR-011) instead of being overwritten; the rest of the master store is delivered normally.
- **Per-agent delivery target**: Coffer delivers a managed skill in exactly one way — the master skill folder is symlinked (copy fallback) into `<config_dir>/skills/<name>`. Each agent's skill subpath comes from the capability manifest, so adding a future agent's delivery target is data, not a new branch.

## Skill delivery scope ([ADR per-agent-resource-scope](../../docs/decisions/per-agent-resource-scope.md))

A `skill` resource carries a framework-level `scope` — a list of agent names,
or `None` for "every agent". Together with the resource's own `enabled` flag it
is the WHOLE delivery rule:

```
delivered(skill, agent)  ⟺  skill.enabled AND agent_in_scope(skill.scope, agent)
```

Nothing else gates delivery. This is the same shape `mcp_server` already uses,
where scope alone decides which agent sees a server's tools.

- **The three scope states.** `None` — every registered agent receives the
  skill (the default for a fresh import). `["claude_code"]` — only the named
  agents receive it; names that are not registered yet are legal and simply
  never match. `[]` — no agent receives it, while the skill stays in the
  library, exported and visible.
- **`enabled` is the on/off switch, and it is real.** Disabling a skill
  reclaims every delivered copy — each symlink is removed, the master folder
  untouched. Re-enabling redelivers it to every agent its scope still grants.
- **Scope is a hard grant.** Narrowing a skill's scope to exclude an agent it
  was previously delivered to reclaims that delivery on the next reconcile,
  even if the copy got there some other way; widening the scope delivers it.
  There is no per-agent state that can hold a copy against the skill's scope,
  and none that can keep a copy away from an agent the scope grants.
- **Reconcile is the enforcement seam** — including the post-import reconcile
  hook (spec vault-export-import). It runs whenever the answer to the predicate can have
  changed: a skill is enabled or disabled, a skill's scope is edited, a skill
  is imported, a skill is removed, an agent is registered, an agent's
  `config_dir` changes, and after a sync import. Each run recomputes the
  agent's wanted set, delivers what is missing, and reclaims what is no longer
  wanted.
- **The trade-off, stated plainly.** There is no longer a single per-agent
  "this agent gets nothing" switch. To exclude one agent from everything,
  remove it from each skill's scope — which is exactly how `mcp_server`
  resources already work. Per-agent exclusion of a specific skill is unchanged
  in power; it just moves from the agent side to the skill side. The agent
  resource carries no skill-delivery policy at all.

## Acceptance Scenarios

Per `agents/sdd.md`, every scenario in this section is referenced by at least one test marked `@pytest.mark.acceptance(spec="skill-manager", scenario="…")` (Python) or `acceptance("skill-manager", "…", …)` (TypeScript).

### Scenario: import a valid local skill folder

- **Given** the daemon is running and no skill named `my-skill` exists,
- **When** the user imports a folder containing a valid SKILL.md with frontmatter `name: my-skill`,
- **Then** Coffer copies the folder to `~/.coffer/skills/my-skill/`, persists a Resource of kind `skill`, and records an audit entry.

### Scenario: re-import a skill with overwrite replaces it

- **Given** a skill named `my-skill` is already imported and enabled for an agent,
- **When** the user imports a folder with frontmatter `name: my-skill` again with `overwrite` (`--force`),
- **Then** the master folder content is replaced atomically, the skill's `version_hash` is refreshed, the existing per-agent binding and its delivered symlink are preserved, and a skill-update audit entry is recorded — whereas the same re-import without `overwrite` is rejected with `conflict` (409).

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

### Scenario: deliver a skill to a registered agent

- **Given** an agent `claude_code` is registered (per spec agent-registry) and an enabled skill `my-skill` is imported whose scope grants `claude_code`,
- **When** the delivery reconcile for that skill runs,
- **Then** a directory symlink (or junction on Windows) is created at `<config_dir>/skills/my-skill` pointing to `~/.coffer/skills/my-skill/`, and a `skill_agent_bindings` row records that the agent holds a delivered copy.

### Scenario: reclaim a skill from an agent

- **Given** a skill is delivered to an agent and the target symlink exists,
- **When** the skill stops being delivered to that agent (its scope no longer grants the agent, or the skill is disabled),
- **Then** the symlink is removed, the delivery record for that agent is cleared, and the master folder is unchanged.

### Scenario: deliver one skill to multiple agents

- **Given** two agents are registered,
- **When** an enabled skill whose scope grants both is reconciled,
- **Then** two symlinks (one per agent) exist, both pointing to the same master folder.

### Scenario: refuse to overwrite a non-Coffer target

- **Given** the user has placed a regular file or directory at the would-be link path,
- **When** a skill is delivered to that agent,
- **Then** the conflict is reported and the existing target is left untouched; the rest of the delivery proceeds.

### Scenario: detect drift in agent skill directories

- **Given** a binding exists but its target on disk has been deleted, replaced, or relinked,
- **When** the user runs `coffer skill verify`,
- **Then** the report lists each drift type with a suggested remedy and exits with a non-zero status; no automatic remediation occurs.

### Scenario: remove a skill cleans up all bindings

- **Given** a skill is enabled for two agents,
- **When** the user removes the skill,
- **Then** both target symlinks are removed, the bindings are cascade-deleted, the master folder is deleted, and an audit entry records the removal with a config snapshot.

### Scenario: removing an agent (per spec agent-registry) cleans up its skill bindings

- **Given** an agent has one or more enabled skills,
- **When** the user removes the agent,
- **Then** spec agent-registry's `on_delete` hook for the agent kind invokes the skill module to remove each binding and its symlink before the agent row is deleted; master folders are unchanged.

### Scenario: desktop and CLI cover every operation

- **Given** the daemon is running,
- **When** the user performs each operation via the web UI and via `coffer skill ...`,
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

### Scenario: edit and save a skill file

- **Given** an imported skill that contains an existing text file,
- **When** the user edits that file in the in-app editor (or a programmatic REST/CLI client saves new contents for it) by its folder-relative path, passing back the fingerprint the read returned,
- **Then** Coffer overwrites the file atomically and returns the file's new fingerprint, and a subsequent read returns the new contents; writing a non-existent path, a path outside the master folder, an existing binary file, or content over the size cap is rejected (`404`/`400`) and the file is left unchanged. A save that omits the fingerprint still writes, so programmatic clients that never read the file first keep working.

### Scenario: reject a stale save of a skill file

- **Given** an imported skill file opened in the in-app editor, whose read returned a content fingerprint,
- **When** the user changes that same file in their own external editor and only then saves the in-app buffer with the now-stale fingerprint,
- **Then** Coffer rejects the save with `conflict` (409, `SKILL_FILE_STALE`) and leaves the externally edited file byte-identical on disk; re-reading yields the current fingerprint and the retried save succeeds.

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

### Scenario: a skill with no scope reaches every registered agent

- **Given** two registered agents and an enabled skill whose scope is unset (`None`),
- **When** the delivery reconcile runs for each agent,
- **Then** both agents hold a delivered copy, and registering a third agent delivers the skill there too with no further user action.

### Scenario: a skill scoped to no agent reaches nobody

- **Given** two registered agents each holding a delivered copy of an enabled skill,
- **When** the user sets the skill's scope to `[]`,
- **Then** both delivered copies are reclaimed, the skill remains in the library (still listed, still exported), and no agent receives it until its scope grants one again.

### Scenario: import delivers a skill only where its scope grants it

- **Given** two registered agents, `claude_code` and `codex`,
- **When** the user imports a skill scoped to `["claude_code"]`,
- **Then** the post-import reconcile delivers it to `claude_code` only, and `codex` receives nothing.

### Scenario: disabling a skill reclaims every delivered copy

- **Given** an enabled skill delivered to two agents,
- **When** the user disables the skill resource,
- **Then** both symlinks are removed and both delivery records are cleared, while the skill's scope and its master folder are unchanged.

### Scenario: re-enabling a skill redelivers it

- **Given** a disabled skill with no delivered copies and a scope granting two agents,
- **When** the user re-enables the skill resource,
- **Then** it is redelivered to both agents — links re-created, delivery records restored — with no per-agent action.

### Scenario: scoping a skill away from an agent reclaims the delivered copy

- **Given** an enabled skill currently delivered to an agent whose name its scope includes,
- **When** the user edits the skill's scope to exclude this agent and the next reconcile runs,
- **Then** the delivered symlink is removed and the delivery record is cleared — scope is a hard grant, and no per-agent state can hold the copy against it.

### Scenario: opt-in repair re-delivers repairable drift from master

- **Given** an agent skill directory where one enabled binding has a missing Coffer link, another has a tampered Coffer link (a stale link pointing elsewhere), a third binding's path is occupied by a foreign regular directory the user owns, and a fourth binding's master folder no longer exists,
- **When** the user runs the opt-in repair (`coffer skill verify --fix` / `POST /skills/repair`),
- **Then** the missing link is re-created pointing to master, the tampered link is backed up to `<path>.coffer-backup-<ts>` and then re-created pointing to master, the foreign regular directory is left completely untouched and still appears in the report as requiring manual action, the missing-master entry is left and reported as requiring manual action, and each re-delivery is recorded as a repair event in the audit log.

## Requirements

### Functional Requirements

**Resource model**

- **FR-001**: System MUST register each managed skill as a Resource of kind `skill`, identified by `skill:<name>` where `<name>` comes from SKILL.md frontmatter.
- **FR-002**: System MUST validate skill configuration against a kind-specific schema with fields `source` (variant: `local_import` only), `skill_md_name`, `skill_md_description`, `version_hash`, and `last_synced_from_source_at`.

**Canonical storage**

- **FR-003**: System MUST store each managed skill's content under `~/.coffer/skills/<name>/`, with that path as the single editable source of truth.
- **FR-004**: System MUST validate every imported skill folder against the AgentSkills specification: `SKILL.md` present; frontmatter `name` present and non-empty (lowercase alphanumerics, hyphen, or underscore, ≤64 chars) and `description` present, non-empty, and ≤1024 chars; no path-escape symlinks; total size within a configurable limit (default 50 MB). A folder that violates any of these is rejected with `unprocessable_entity` (422) and nothing is persisted.
- **FR-027**: System MUST recognize the optional agentskills.io frontmatter fields it understands — `license` and the experimental `allowed-tools` — parsing and retaining them rather than discarding them, while tolerating any other unrecognized frontmatter field so non-Coffer-authored skills validate cleanly. `allowed-tools` accepts either a list or a comma/whitespace-separated string and is normalized to a list of tool names; a malformed value is tolerated (treated as absent), never a validation failure. Likewise a non-string `license` scalar (e.g. an unquoted year or version) is coerced to a string rather than rejected.

**Sources**

- **FR-005**: System MUST support importing a skill from a local filesystem path; the original source path is recorded for provenance but is not retained as a live dependency. Re-importing a name that already exists is rejected by default (`conflict`, 409); with an explicit `overwrite` flag (CLI `--force`) the existing skill is replaced in place — the master folder content is swapped atomically, its `version_hash` and `last_synced_from_source_at` are refreshed, and its per-agent bindings and delivered symlinks are preserved (the master folder name is unchanged). Re-import overwrite is the only skill update mechanism (there is no live source to re-fetch); the replacement is audited as an update.

**Per-agent delivery**

- **FR-008**: Each `(skill, agent)` binding is internal delivery bookkeeping, tracked in a `skill_agent_bindings` table: a row records that this agent currently holds a delivered copy, plus the last successful link path, the link mode, and when it was last linked. It is not a user-facing axis and no surface exposes it as a toggle.
- **FR-009**: Delivering a skill to an agent MUST create a directory symlink (POSIX) or directory junction (Windows) at `<config_dir>/skills/<skill-name>` pointing to `~/.coffer/skills/<skill-name>/`.
- **FR-010**: Reclaiming a delivered copy MUST remove the target link without touching the master folder.
- **FR-011**: Delivery MUST report, never overwrite: when the target path already holds something that is not a Coffer-managed link, that skill is reported as a conflict and the existing target is left exactly as it was, while the rest of the delivery proceeds. (Backing a target up before relinking exists only inside the explicit opt-in drift repair of FR-029.)
- **FR-012**: When symlinks/directory junctions are unavailable (e.g., FAT32, network share), System MAY fall back to copy mode for that target; the binding records `link_mode=copy_fallback` (audited as `mode: copy_fallback` on the enable event) and the UI MUST surface the degradation (the agent Skills tab shows a "Copied" warning chip on such bindings).
- **FR-012a** ([ADR per-agent-resource-scope](../../docs/decisions/per-agent-resource-scope.md)): A skill MUST be delivered to an agent if and only if the skill resource is enabled AND the agent is within the skill's scope — `skill.enabled AND agent_in_scope(skill.scope, agent)`. No other flag decides which agents a skill is FOR: neither the delivery bookkeeping of FR-008 nor any field on the agent resource. A DISABLED AGENT is a separate matter and is never written into at all — the predicate names the agents a skill belongs to, while an agent the user switched off is one Coffer does not touch; its held copies are reclaimed and re-enabling it reconciles them back. A reconcile that finds a delivered copy the predicate no longer grants MUST reclaim it (remove the link, clear the delivery record) per FR-010, and MUST deliver a copy the predicate now grants but the agent does not hold.

**Drift**

- **FR-015**: System MUST provide a `verify` operation that compares each enabled binding to its on-disk target and reports drift categories (missing link, tampered link, missing master, orphan master) with suggested remedies.
- **FR-016**: System MUST NOT automatically remediate drift; remediation requires an explicit user action.
- **FR-029**: System MUST provide an explicit, opt-in drift repair (`coffer skill verify --fix`, `POST /skills/repair`) that re-delivers repairable drift — missing link and tampered link — from the master library, and MUST NOT modify foreign/user content (replaced-with-regular), a missing master, or an orphan master; those are left intact and reported as requiring manual action. Each repair is audited.

**Unmanaged skills (workspace amendment)**

- **FR-022**: System MUST scan a registered agent's skill locations — `<config_dir>/skills` for both types, plus `~/.agents/skills` for `codex` — and list **unmanaged** entries: everything that is not a Coffer-managed link (a link whose target resolves inside `~/.coffer/skills/`) and not Codex's `.system` entry. Each result carries name, path, location, and a `valid` flag (FR-004 validation) with the failure reason when invalid. The scan is read-only and derived at request time.
- **FR-023**: Users MUST be able to adopt a valid unmanaged skill. Adoption validates the folder per FR-004, moves it to `~/.coffer/skills/<name>/`, registers the `skill` resource, delivers the managed link (FR-009), and records an enabled binding for that agent — in that order, with any failure before registration leaving the original folder unmoved and unchanged (after registration the master copy is authoritative; a delivery failure is surfaced and retried via the binding, never rolled back). The managed link is always delivered to the agent's canonical delivery location `<config_dir>/skills/<name>`: adopting from `<config_dir>/skills` replaces the original path in place, while adopting from `~/.agents/skills` consolidates — the original folder there is removed and the link lands in `<config_dir>/skills` (Codex reads both locations, so the agent keeps seeing the skill). Name collisions are rejected with `conflict` (409); invalid folders and symlinks pointing outside the master store are rejected with `unprocessable_entity` (422). Audited as an adoption event.
- **FR-024**: Users MUST be able to delete an unmanaged entry as an explicit, confirmed action. Deletion removes only that entry from disk, never master content or bindings, and is audited.

**Delivery reconciliation (workspace amendment)**

- **FR-025**: The system MUST reconcile deliveries per agent from the FR-012a predicate alone. A reconcile computes the agent's wanted set as `{s.name for s in skills if s.enabled and agent_in_scope(s.scope, agent_name)}`, delivers every wanted skill the agent does not hold, and reclaims every held copy that is no longer wanted. It MUST run on: a skill being enabled or disabled, a skill's scope being edited, a skill being imported, a skill being removed, an agent being registered, an agent being enabled or disabled, an agent's `config_dir` changing, and the post-import hook after a sync import. A disabled agent's wanted set is empty, so the same reconcile reclaims its copies and restores them when it is enabled again. Conflicts at target paths follow FR-011 (report, never overwrite). The agent resource carries no skill-delivery policy of any kind — no follow flag, no exclusion list, no per-agent opt-out; the only inputs are the skill's `enabled` flag and its `scope`.
- **FR-026**: Unmanaged-skill operations MUST be available through the REST API, the `coffer agent skill …` / `coffer skill …` CLI (with `--json` on reads), and the agent's Skills tab in the web UI. Delivery itself is not an operation on this surface: it is controlled by the skill resource's `enabled` flag and `scope` through the generic resource enable/disable and scope surfaces.

**Lifecycle**

- **FR-017**: Removing a skill MUST remove every enabled per-agent symlink, cascade-delete bindings, delete the master folder, and audit the removal with a snapshot.
- **FR-018**: Removing an agent (via spec agent-registry) MUST trigger an `on_delete` hook in the skill module that removes that agent's bindings and symlinks before the agent row is deleted.

**Surfaces**

- **FR-019**: Every management operation MUST be available through (a) the REST API, (b) the `coffer skill ...` CLI with `--json`, and (c) the Skills page in the web UI. Per-(skill, agent) enable/disable is not among them: the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes and the `coffer skill enable|disable` CLI commands are REMOVED. Delivery is driven by the skill's `enabled` flag and `scope` through the generic resource surfaces — `coffer scope set skill:<name> --agents …` and `coffer resource enable|disable skill:<name>`.
- **FR-021**: System MUST expose a **read-only** view of a skill's master folder: a recursive file tree (name, folder-relative path, absolute on-disk path, type, size, children) and the contents of an individual file (with its absolute on-disk path and containing folder's absolute path). Markdown files render as formatted Markdown; other text files show raw. Every file read MUST also return a content fingerprint (FR-028) so an in-app edit of that file can be saved conditionally. Reads MUST be contained to the master folder — any path that resolves outside it (`..` traversal, absolute path, or escaping symlink) MUST be rejected. File reads MUST be size-capped (truncating with a `truncated` flag) and MUST flag non-UTF-8 / NUL-containing files as binary with empty content. No symlink-following out of the folder.
- **FR-006**: The in-app file viewer MUST offer, at both file and containing-folder granularity, affordances to (a) open the target in the user's preferred external editor (the global preference is specced in ui-shell; default = the OS default application) and (b) reveal the target in the OS file manager (Finder / Explorer). Open and reveal perform the real OS action through the daemon filesystem-action endpoints (spec agent-registry FR-039), since the loopback daemon is on the user's own machine (ADR daemon-proxies-os-file-actions). There is no copy-path fallback. These affordances sit alongside in-app editing (FR-028): the user saves small edits in Coffer and reaches for their own editor for anything larger.
- **FR-028**: System MUST provide a write that overwrites an **existing text file** in the master folder, under the same containment guard and size cap as FR-021; it MUST refuse to create new files/directories here, to write outside the folder, or to overwrite a binary file with text. The write MUST be atomic with no symlink-following out of the folder. The in-app editor and programmatic clients (REST/CLI) share this one endpoint. Because the master folder is also a folder the user edits in their own editor, file reads MUST return a **content fingerprint** (a digest of the file's raw on-disk bytes — not of the possibly-truncated text returned, so an oversized file's fingerprint still round-trips and an edit past the truncation point is still detected), and a write MAY carry that fingerprint back: when it no longer matches the bytes on disk the write MUST be rejected with `conflict` (409) and the file left byte-identical, so the user re-reads and reapplies rather than silently losing the other edit. A write that omits the fingerprint stays unconditional (last writer wins), which is what a programmatic client that never read the file first needs.
- **FR-030**: The "Add skill" import dialog MUST offer a folder picker (reusing the shared component from spec agent-registry FR-023/FR-024 — the host's native directory dialog opened through the daemon, falling back to the daemon-backed folder browser) so the user picks the skill folder instead of typing its absolute path. The picked absolute path feeds the existing import operation (FR-005); typing a path by hand stays supported.

**Observability**

- **FR-020**: System MUST record an audit entry for every import, delivery, reclaim, remove, and drift remediation event.

### Key Entities

- **Skill**: A Resource of kind `skill`, identified by `skill:<name>` (name from SKILL.md frontmatter). Holds source provenance, content hash, and metadata; the content folder lives on disk at `~/.coffer/skills/<name>/`. Carries a framework-level `scope` (a list of agent names, or `None` for every agent) which, together with the resource's own `enabled` flag, determines delivery outright (ADR per-agent-resource-scope; see "Skill delivery scope").
- **Skill Source**: A record capturing where the skill came from. For local imports, it includes the original path for informational purposes only.
- **Skill–Agent Binding**: Internal delivery bookkeeping, not a user-facing toggle. A row joining one skill Resource and one agent Resource (kind `agent`, per spec agent-registry) records that this agent currently holds a delivered copy, with last-link-path, link-mode and last-linked-at metadata. Symlink existence on disk is the live representation; the row is the persistent record of what was delivered.
- **Drift Report**: An ephemeral structure produced by `verify` listing each binding whose on-disk target disagrees with the binding state, categorized by drift type with a suggested remedy.
- **Unmanaged Skill**: A derived (never stored) view of a skill-shaped entry found in an agent's skill locations that Coffer does not manage — name, path, location, `valid` flag. The filesystem is the source of truth; adoption or deletion are the only mutations.

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user can import their existing `~/.claude/skills/<one-skill>/` folder, enable it for the auto-detected Claude Code agent, and reach the "ready" state within 60 seconds.
- **SC-003**: Enabling a skill for two agents creates two valid directory symlinks (or junctions on Windows), and each agent's reading process sees identical SKILL.md content.
- **SC-004**: After manually deleting an agent-side symlink, `coffer skill verify` identifies it as drift within 5 seconds and exits with a non-zero status.
- **SC-005**: Removing a skill that is enabled for two agents leaves no residual symlinks, no residual master folder, and no orphan binding rows in the database.
- **SC-006**: Every Acceptance Scenario in this spec is covered by at least one test marked `acceptance(spec="skill-manager", scenario="…")`, and `make verify-acceptance` reports zero uncovered scenarios.
- **SC-007**: The full `make verify` suite passes locally and in CI; `make verify-all` (adding e2e) passes on macOS and Linux; Windows tests pass for both junction mode and copy-fallback mode.
- **SC-008**: No SKILL.md content ever leaves the user's machine; verified by an automated network-egress scan during integration tests.
- **SC-009**: A newly imported skill is delivered within 5 seconds to every agent its scope grants, with no user action beyond the import itself.
- **SC-010**: On a machine with a mix of managed links and hand-placed skills, the unmanaged scan lists exactly the hand-placed entries — zero managed links, zero `.system` entries — verified by integration tests over a constructed fixture tree.

## Assumptions

- Spec agent-registry-agent-registry has shipped (PR #25); the agent kind, its CRUD, audit, and `on_delete` hook are available.
- The kind-agnostic Resource framework, audit log, and `<kind>:<name>` identity scheme defined by spec mcp-gateway-mcp-gateway are in place.
- The application shell from spec ui-shell-ui-shell — sidebar IA, layout, routing skeleton, and design system — is in place; the Skills page is a feature surface that renders within that shell and fills the `/skills` nav slot 002-ui-shell reserved as a placeholder.
- Skills follow the open AgentSkills standard (`SKILL.md` with `name`/`description` frontmatter at minimum) as published at agentskills.io, validated against the standard's exact constraints (`name` ≤64 chars, `description` ≤1024 chars) with the optional `license` and experimental `allowed-tools` fields recognized; non-conforming folders are out of scope.
- Local-imported skills are point-in-time copies; the source path is recorded for traceability, not for sync.
- Windows users have directory-junction support on their filesystem; FAT32 and network shares fall back to copy mode.
- Delivery stays at `<config_dir>/skills` for both agent types. Codex additionally reads `~/.agents/skills` (its newer standard location) and treats `<config_dir>/skills` as a backward-compatible legacy location — the unmanaged scan covers both; migrating Coffer's delivery target is a recorded decision deferred to a future change.
- The agent resource carries no skill-delivery policy at all. Delivery lives entirely on the skill resource — its `enabled` flag and its `scope` — and this spec owns those semantics.
- A browse-and-install skill catalog (discovery) was prototyped then withdrawn (simplification, 2026-06-20) for lack of a content ecosystem; an install catalog remains possible future work.
- v2 will explore: a remote catalog index, agent-to-agent skill recommendations, and project-local skills (`.claude/skills/` in repo).
