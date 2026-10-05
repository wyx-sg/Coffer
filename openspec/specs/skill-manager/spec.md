# Skill Manager

## Purpose
Coffer manages portable AI skills in the open AgentSkills standard (agentskills.io): a `SKILL.md` with `name`/`description` frontmatter at minimum, validated against the standard's exact constraints, with the optional `license` and experimental `allowed-tools` fields recognized; non-conforming folders are out of scope. One canonical store lives at `~/.coffer/vault/skills/`, and a skill reaches a coding agent as a directory symlink (junction on Windows, copy as a last resort) into the `skills/` subfolder of that agent's config directory. Claude Code and Codex CLI are the delivery targets, each registered as a resource of kind `agent` per spec agent-registry. Developers rely on it to migrate the skills they already have (import, or one-click adoption of skills an agent accumulated outside Coffer), to decide once — on the skill — which agents a skill reaches, and to trust that what is on disk matches what Coffer says, because drift self-heals at boot and the rest stays inspectable.

Delivery is one rule with no second switch: a skill's own `enabled` flag and its `scope` decide which agents receive it. A freshly imported skill has no scope and reaches every registered agent — "configure once, share everything", the filesystem counterpart of the MCP gateway's one-entry-serves-all model. The trade-off is stated plainly: there is no per-agent "this agent gets nothing" switch; to exclude one agent from everything, remove it from each skill's scope, exactly as `mcp_server` resources already work. Per-agent exclusion of a specific skill is unchanged in power; it moves from the agent side to the skill side.

A skill enters the library from a folder, a `.zip` / `.skill` archive or a folder of a Git repository, each staged and confirmed before anything is written. Folder- and archive-imported skills are point-in-time copies; the source is kept for traceability, not for sync. A Git-imported skill is pinned to the commit it came from and offered that repository's newer commits as a reviewed update. Because an agent's delivered path is a link to master, a user editing `SKILL.md` from inside an agent's `skills/` folder edits master, and every other agent sees it on its next read without any drift being reported; deleting a file there likewise affects master. If an agent's `config_dir` is moved or removed externally, the next sync operation surfaces the failure and `verify` reports the affected bindings. Codex also reads `~/.agents/skills` (its newer standard location) and treats `<config_dir>/skills` as backward-compatible; delivery stays at `<config_dir>/skills` for both agent types and the unmanaged scan covers both. `~/.agents/skills` is shared with other tools, so Coffer classifies only its own links as managed and never garbage-collects another tool's skills.

This spec owns the three `/api/v1/agents/{uid}/unmanaged-skills` routes (list, adopt, delete): their code (`surfaces/http/agent_unmanaged_skill_routes.py`), their contract (this spec's `contracts/api.openapi.yaml`) and their import-linter fence (the module sits on the `skill` kind's side of a zero-exception contract in `backend/pyproject.toml`) all say so, and the agent is an argument to these operations, not their subject. The web UI's open-in-external-editor and reveal-in-file-manager affordances in the file viewer are the daemon's filesystem-action endpoints ([ADR daemon-proxies-os-file-actions](../../../docs/decisions/daemon-proxies-os-file-actions.md)) opening the user's preferred external editor ([web-ui](../web-ui/spec.md) "Let the user choose an external editor"), and the Add-skill dialog uses the shared folder picker from spec agent-registry and also takes a typed or pasted path; this spec assumes both and feeds the chosen path to the import with only surrounding whitespace and quotes removed. A browse-and-install skill catalogue was prototyped and withdrawn for lack of a content ecosystem. The master-folder file viewer and editor ("Show a skill's master folder read-only", "Save an existing skill file conditionally") are served over REST to the web UI's Files tab; on disk the folder is the path the skill's page shows (**Copy master path**), read and edited with the person's own tools.

## Requirements

### Requirement: Register each skill as a resource with a SKILL.md-safe name
The system MUST register each managed skill as a Resource of kind `skill`, identified by the framework's immutable `uid` ([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)). Its `name` is taken from SKILL.md frontmatter at import or adoption, unique within the kind, and MUST satisfy the frontmatter's own charset (`^[a-z0-9][a-z0-9-]{0,63}$`), so Coffer never registers a skill under a name its own importer would reject. The `name` MUST be **fixed** once the skill is registered, because it is the directory an agent loads the skill from and the identifier an agent invokes it by, so it is quoted in places Coffer cannot see ([resource-framework](../resource-framework/spec.md), the requirement that lets a kind declare its name fixed). An update whose `name` differs from the current one MUST be refused with `NAME_IMMUTABLE` (409) before anything moves, on REST and on the web UI alike. The refusal MUST say that a different name means removing the skill and importing it again, and that doing so resets its `enabled` flag, its scope and its deliveries. A skill carries no title ([resource-framework](../resource-framework/spec.md) "Carry an optional editable title on the kinds that have one"): every surface shows its fixed name, beside the SKILL.md `description` agents choose it by, and a title submitted for one is refused as a validation error with nothing changed.

#### Scenario: refuse a skill name its own SKILL.md could not carry
- **GIVEN** the daemon is running and no skill is registered under any of the names below
- **WHEN** the user imports, or adopts, a folder whose SKILL.md frontmatter `name` is `My.Skill`, `MySkill` or `-leading`
- **THEN** each is refused as a validation error before anything is written
- **AND** no `skill` resource exists afterwards and nothing is under `~/.coffer/vault/skills/` for any of them

#### Scenario: refuse changing a registered skill's name
- **GIVEN** an imported skill `before` delivered to a registered agent
- **WHEN** the user submits the name `after` through the resource update route and through the web UI
- **THEN** each is refused with `NAME_IMMUTABLE` (409), and the message says that a new name means removing the skill and importing it again, which resets its enabled flag, scope and deliveries
- **AND** the row, the master folder `before`, its SKILL.md `name: before` and the delivered link are all exactly as they were, and `verify` reports no drift

#### Scenario: a skill takes no title
- **GIVEN** an imported skill `before` delivered to a registered agent
- **WHEN** the user submits the title `Release checklist` for it through the resource update route
- **THEN** the title is refused as a validation error, `GET /api/v1/skills` and the Skills page still show `before`, and `GET /api/v1/skills/{uid}` carries no `title`
- **AND** the master folder, its SKILL.md and the delivered link are byte-identical to before the request

### Requirement: Validate the skill configuration schema
The system MUST validate skill configuration against a kind-specific schema with fields `source` (variants: `local_import`, carrying the path it was imported from; `archive_import`, carrying the archive's file name and the folder inside it the skill came from; `git_import`, carrying the repository URL, the ref asked for, the subpath of the skill's folder in the repository, the commit it was pinned to and the content hash of that folder at that commit; and `builtin`, carrying nothing at all — see "Regenerate Coffer's builtin skill from the build"), `skill_md_description`, `version_hash`, and `last_synced_from_source_at`. The config MUST NOT restate the skill's name; that is `Resource.name`.

#### Scenario: store a skill's config without restating its name
- **GIVEN** a skill imported from a local folder
- **WHEN** its resource is read back
- **THEN** its config holds a `local_import` source carrying the original path, `skill_md_description`, `version_hash` and `last_synced_from_source_at`, and no field restating the name
- **AND** a config carrying a field the schema does not define (such as `skill_md_name`) is refused, and a `builtin` source validates to its variant name and nothing else

#### Scenario: a git-imported skill records the commit it was pinned to
- **GIVEN** a skill added from a Git repository at ref `main` and subpath `skills/review`
- **WHEN** its resource is read back
- **THEN** its config holds a `git_import` source carrying the URL, `main`, `skills/review`, the full commit id that was checked out and the content hash of the folder at that commit

### Requirement: Validate imported skill folders against AgentSkills
The system MUST validate every imported skill folder against the AgentSkills specification: `SKILL.md` present; frontmatter `name` present and non-empty (lowercase alphanumerics or hyphen, ≤64 chars) and `description` present, non-empty, and ≤1024 chars; no path-escape symlinks and no symlink to a folder (the master copy follows links, so a link to its own root would recurse); total size at most 50 MB, a fixed cap, in which a link to a file counts as the file's bytes. A folder that violates any of these MUST be rejected with `unprocessable_entity` (422) and nothing persisted. A folder over the size limit is rejected as `SKILL_INVALID` with `details.reason` `size_limit_exceeded`.

#### Scenario: reject import of an invalid skill folder
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder that is missing `SKILL.md` or has empty `name`/`description` frontmatter,
- **THEN** the request is rejected with a clear error, and nothing is written to `~/.coffer/vault/skills/` or the vault.

#### Scenario: reject import containing path-escape symlinks
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder containing a symlink that resolves outside the folder,
- **THEN** the request is rejected with the offending paths listed, and nothing is persisted.

#### Scenario: reject a skill folder holding a link to a folder
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder in which `loop` is a symlink to `.` and `alias` is a symlink to a sub-folder,
- **THEN** the request is rejected as `directory_symlinks` listing `loop` and `alias`, and nothing is copied or persisted.

#### Scenario: reject a skill with an over-long description
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder whose SKILL.md `description` exceeds 1024 characters,
- **THEN** the request is rejected as invalid frontmatter, and nothing is written to `~/.coffer/vault/skills/` or the vault.

### Requirement: Retain optional AgentSkills frontmatter fields
The system MUST recognize the optional agentskills.io frontmatter fields it understands — `license` and the experimental `allowed-tools` — parsing and retaining them rather than discarding them, while tolerating any other unrecognized frontmatter field so non-Coffer-authored skills validate cleanly. `allowed-tools` accepts either a list or a comma/whitespace-separated string and is normalized to a list of tool names; a malformed value is tolerated (treated as absent), never a validation failure. Likewise a non-string `license` scalar (e.g. an unquoted year or version) is coerced to a string rather than rejected.

#### Scenario: recognize optional agentskills.io frontmatter fields
- **GIVEN** a valid SKILL.md that also declares `license` and the experimental `allowed-tools`,
- **WHEN** the folder is validated,
- **THEN** validation succeeds and the parsed frontmatter retains `license` and a normalized `allowed-tools` list (rather than discarding them).

### Requirement: Import a skill from a local path
The system MUST support importing a skill from a local filesystem path; the original source path is recorded for provenance but is not retained as a live dependency. Re-importing a name that already exists MUST be rejected by default (`conflict`, 409); with an explicit `overwrite` flag (the Add dialog's Replace) the existing skill is replaced in place — the master folder content is swapped atomically, its `version_hash` and `last_synced_from_source_at` are refreshed, and its per-agent bindings and delivered symlinks are preserved (the master folder name is unchanged). For a skill added from a folder or an archive, re-import overwrite is the only update mechanism (there is no live source to re-fetch); a skill added from a Git repository is updated from its source instead, by the person's agent (see "Hand a Git-imported skill's update to an agent"). The replacement is audited as an update. On a name collision the user either renames via SKILL.md frontmatter and retries, or re-imports with `overwrite`. A folder added from the web UI is looked at before anything is copied, as an archive is ("Add skills from an archive"): the dialog shows the skill it found, or the skills one folder down when the folder itself holds no `SKILL.md`, and copies nothing until the user confirms. `POST /api/v1/skills/import` imports at once, since naming the folder in the request is the confirmation.

#### Scenario: import a valid local skill folder
- **GIVEN** the daemon is running and no skill named `my-skill` exists,
- **WHEN** the user imports a folder containing a valid SKILL.md with frontmatter `name: my-skill`,
- **THEN** Coffer copies the folder to `~/.coffer/vault/skills/my-skill/`, persists a Resource of kind `skill`, and records an audit entry.

#### Scenario: re-import a skill with overwrite replaces it
- **GIVEN** a skill named `my-skill` is already imported and enabled for an agent,
- **WHEN** the user imports a folder with frontmatter `name: my-skill` again with `overwrite`,
- **THEN** the master folder content is replaced atomically, the skill's `version_hash` is refreshed, the existing per-agent binding and its delivered symlink are preserved, and a skill-update audit entry is recorded — whereas the same re-import without `overwrite` is rejected with `conflict` (409).

#### Scenario: a folder is looked at before it is added
- **GIVEN** a folder holding a valid skill `release-notes`
- **WHEN** the user stages it in the Add skill dialog
- **THEN** the dialog shows `release-notes` with its description and file count, and nothing is under `~/.coffer/vault/skills/` for it and no skill resource exists until the user confirms

#### Scenario: a folder whose skill is one folder down names that folder when it cannot be added
- **GIVEN** a folder with no `SKILL.md` at its top whose only `SKILL.md` is in the sub-folder `skill/`, and that skill cannot be added (a link inside it leaves the folder)
- **WHEN** the user stages the folder
- **THEN** the stage is refused with the sub-folder skill's own reason and `details.candidate_folder` `skill` (with its absolute path as `details.candidate_path`), so the dialog can offer that folder as the one to add

### Requirement: Track delivered copies as internal bookkeeping
The system MUST track each `(skill, agent)` binding as internal delivery bookkeeping in a `skill_agent_bindings` table of this machine's derived database, `~/.coffer/derived/derived.db`, keyed by the skill's and the agent's uids — a fact about this machine's disks that never enters the vault or travels with sync: a row records that this agent currently holds a delivered copy, plus the last successful link path, the link mode, and when it was last linked. It is not a user-facing axis and MUST NOT be exposed as a toggle on any surface. Symlink existence on disk is the live representation; the row is the persistent record of what was delivered.

#### Scenario: deliver a skill to a registered agent
- **GIVEN** an agent `claude_code` is registered (per spec agent-registry) and an enabled skill `my-skill` is imported whose scope grants `claude_code`,
- **WHEN** the delivery reconcile for that skill runs,
- **THEN** a directory symlink (or junction on Windows) is created at `<config_dir>/skills/my-skill` pointing to `~/.coffer/vault/skills/my-skill/`, and a `skill_agent_bindings` row records that the agent holds a delivered copy.

### Requirement: Deliver a skill as a directory link
Delivering a skill to an agent MUST create a directory symlink (POSIX) or directory junction (Windows) at `<config_dir>/skills/<skill-name>` pointing to the skill's master folder, `~/.coffer/vault/skills/<skill-name>/` (`~/.coffer/derived/skills/<skill-name>/` for Coffer's own builtin skill). Each agent's skill subpath comes from the capability manifest, so a future agent's delivery target is data, not a new branch; this is the only way Coffer delivers a managed skill.

#### Scenario: deliver one skill to multiple agents
- **GIVEN** two agents are registered,
- **WHEN** an enabled skill whose scope grants both is reconciled,
- **THEN** two symlinks (one per agent) exist, both pointing to the same master folder.

### Requirement: Reclaim a delivered copy without touching master
Reclaiming a delivered copy MUST remove the target link without touching the master folder.

#### Scenario: reclaim a skill from an agent
- **GIVEN** a skill is delivered to an agent and the target symlink exists,
- **WHEN** the skill stops being delivered to that agent (its scope no longer grants the agent, or the skill is disabled),
- **THEN** the symlink is removed, the delivery record for that agent is cleared, and the master folder is unchanged.

### Requirement: Report a foreign target instead of overwriting it
Delivery MUST report, never overwrite: when the target path already holds something that is not a Coffer-managed link, that skill is reported as a conflict and the existing target is left exactly as it was, while the rest of the delivery (the rest of the master store) proceeds. Backing a target up before relinking exists only inside the explicit opt-in drift repair of "Repair repairable drift from master".

#### Scenario: refuse to overwrite a non-Coffer target
- **GIVEN** the user has placed a regular file or directory at the would-be link path,
- **WHEN** a skill is delivered to that agent,
- **THEN** the conflict is reported and the existing target is left untouched; the rest of the delivery proceeds.

### Requirement: Fall back to copying where links are unavailable
When symlinks/directory junctions are unavailable (e.g., FAT32, network share), the system MAY fall back to copy mode for that target; the binding records `link_mode=copy_fallback` (audited as `mode: copy_fallback` on the enable event) and the UI MUST say so where the copy is shown: the skill's Delivery tab lists that agent's copy as **Copied, not linked**, naming the folder links are not allowed in and that the copy follows the master only through repair: a copy whose content no longer matches master is reported as drift (a tampered link) and replaced from master, the old copy kept in the backup folder. Only a Windows machine without links reaches this fallback. A copy made this way is a working delivery, not a warning, so the library row carries no mark for it.

#### Scenario: fall back to a copy where a directory link cannot be made
- **GIVEN** a registered agent on a filesystem where neither a directory symlink nor a junction can be created
- **WHEN** an enabled skill is delivered to it
- **THEN** a real copy of the master folder is placed at `<config_dir>/skills/<name>`, the binding records `link_mode=copy_fallback`, the delivery audit entry carries `mode: copy_fallback`, and `verify` treats a copy that matches master as healthy rather than as drift
- **AND** the skill's Delivery tab shows that agent's copy as Copied, not linked, with the reason, while a plain symlink delivery shows Linked

#### Scenario: a copy that master has moved past is replaced
- **GIVEN** an agent holding a copy-fallback delivery, and a master folder edited since the copy was made
- **WHEN** a pass runs
- **THEN** the copy is reported as a tampered link, replaced from master, and the old copy is kept under the backup folder

### Requirement: Deliver a skill only where it is enabled and in scope
A skill MUST be delivered to an agent if and only if the skill resource is enabled AND the skill's scope admits that agent — `skill.enabled AND is_active(skill.scope, agent=<agent>)`, one allow-list, left `null` admitting anything ([ADR per-agent-resource-scope](../../../docs/decisions/per-agent-resource-scope.md)). This is the same shape `mcp_server` uses, where scope alone decides which agents see a server's tools. The scope states:

- `None` — every registered agent receives the skill (the default for a fresh import).
- `{"agents": ["<agent uid>"]}` — only those agents receive it. The scope holds agent uids ([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)); the web UI lets the user pick agents by name and stores their uids. A uid that matches no agent registered here is legal and simply never matches.
- An empty list is refused (`SCOPE_INVALID`). A skill that no agent should receive is switched off; it stays in the library, synced and visible, and keeps the agents that were chosen.

Those two together are the skill's REACH, and reach is machine-local: it is set on the machine it applies to, it lives in this machine's reach record, so a sync round neither carries it away nor writes over it (spec vault-sync, "Keep reach machine-local"), and the predicate therefore takes no machine argument and has no machine to take. What travels is the skill — its master folder and its resource file in the vault — unless it is Coffer's own generated one (see "Regenerate Coffer's builtin skill from the build"). A skill can still be delivered here and switched off on another machine — that is two machines each holding their own `enabled` flag and their own scope, not one scope naming machines. The surface that sets reach MUST say that the setting stops at this machine.

No other flag decides which agents a skill is FOR: neither the delivery bookkeeping of "Track delivered copies as internal bookkeeping" nor any field on the agent resource; the agent resource carries no skill-delivery policy at all. `enabled` is a real switch: disabling a skill reclaims every delivered copy (master untouched) and re-enabling redelivers it to every agent its scope still grants. Scope is a hard grant: narrowing it to exclude an agent reclaims that delivery on the next reconcile even if the copy got there some other way, and widening it delivers; no per-agent state can hold a copy against the scope or keep one away from an agent the scope grants. A reconcile that finds a delivered copy the predicate no longer grants MUST reclaim it (remove the link, clear the delivery record) per "Reclaim a delivered copy without touching master", and MUST deliver a copy the predicate now grants but the agent does not hold. This predicate governs **delivery** — writing a skill into an agent's own filesystem — and is the only path by which a skill reaches an agent (see "Expose no skill tools over MCP").

#### Scenario: a skill with no scope reaches every registered agent
- **GIVEN** two registered agents and an enabled skill whose scope is unset (`None`),
- **WHEN** the delivery reconcile runs for each agent,
- **THEN** both agents hold a delivered copy, and registering a third agent delivers the skill there too with no further user action.

#### Scenario: an empty agent list is refused for a skill
- **GIVEN** two registered agents each holding a delivered copy of an enabled skill,
- **WHEN** the user sets the skill's scope to `{"agents": []}`,
- **THEN** the write is refused with `422` `SCOPE_INVALID`, both delivered copies stay, and the way to reach nobody is to disable the skill, which reclaims both copies while the skill remains in the library (still listed, still exported).

#### Scenario: disabling a skill reclaims every delivered copy
- **GIVEN** an enabled skill delivered to two agents,
- **WHEN** the user disables the skill resource,
- **THEN** both symlinks are removed and both delivery records are cleared, while the skill's scope and its master folder are unchanged.

#### Scenario: re-enabling a skill redelivers it
- **GIVEN** a disabled skill with no delivered copies and a scope granting two agents,
- **WHEN** the user re-enables the skill resource,
- **THEN** it is redelivered to both agents — links re-created, delivery records restored — with no per-agent action.

#### Scenario: scoping a skill away from an agent reclaims the delivered copy
- **GIVEN** an enabled skill currently delivered to an agent whose uid its scope includes,
- **WHEN** the user edits the skill's scope to exclude this agent and the next reconcile runs,
- **THEN** the delivered symlink is removed and the delivery record is cleared — scope is a hard grant, and no per-agent state can hold the copy against it.

### Requirement: Report skill drift on request
The system MUST provide a `verify` operation — a read-only facility on REST (`POST /skills/verify`) and on the Skills page (**Check copies**) — that compares each enabled binding to its on-disk target — and each delivery the rule wants whose path a folder Coffer did not put there already occupies — and reports drift categories (missing link, tampered link, foreign content at the link path, missing master, orphan master), Asking for the report MUST NOT itself repair anything. The drift report is ephemeral: each binding whose on-disk target disagrees with the binding state, categorized by drift type. A report entry carries the skill, the agent, the kind and the path, and no remedy text: the Skills page says what to do about a kind in its own words — that **Repair** puts a missing or repointed link back. An entry of a kind no repair settles also carries the hand-off of "Hand unsettled skill drift to an agent with a prompt". The Skills page lists the report's findings with the skill, the agent, the path and what the kind means, and offers the repair of "Repair repairable drift from master" for the findings it covers; the other findings stay listed for the user to act on.

#### Scenario: detect drift in agent skill directories
- **GIVEN** a binding exists but its target on disk has been deleted, replaced, or relinked,
- **WHEN** the user calls `POST /skills/verify` (REST) or chooses Check copies on the Skills page,
- **THEN** the report lists each drift type with its skill, agent and path, and the Skills page says what each kind needs; asking for the report never itself repairs anything — repair runs only along the separate paths in "opt-in repair re-delivers repairable drift from master" and the boot-heal scenarios below.

#### Scenario: check agents' copies from the skills page
- **GIVEN** one skill whose delivered link is missing and another whose link path holds a folder Coffer did not put there
- **WHEN** the user chooses Check copies on the Skills page
- **THEN** both findings are listed with the skill, the agent and the path, the missing link saying that Repair puts it back, and nothing on disk has changed
- **AND** choosing Repair re-creates the missing link, while the foreign folder is left as it was and stays listed

#### Scenario: a folder in the way of a first delivery is reported
- **GIVEN** an agent whose skills directory already holds a real folder named like a skill, and that skill is then imported with a reach that grants the agent
- **WHEN** the drift report runs
- **THEN** it lists that path as foreign content at the link path for the skill and the agent, and the folder is left exactly as it was

### Requirement: Heal safely repairable drift on every pass
The system MUST remediate the drift kinds "Repair repairable drift from master" designates safely repairable — a missing link and a tampered link — on every reconcile pass, without waiting for a person to act: at daemon start, on the reconciler's period and whenever a pass is brought forward, so drift that accumulated while the daemon was down, or between any two events, is found on the next pass. Drift kinds that repair does not consider safely repairable — a foreign directory at a link path, a missing master, an orphan master folder — MUST never be auto-remediated and stay reported: in the reconciler's plan (`GET /api/v1/reconcile/plan`), in the attention list and in the log, each with skill, agent, drift kind, on-disk path and a reason, for manual action.

#### Scenario: skill drift self-heals at daemon boot
- **GIVEN** an agent's delivered skill link is missing (deleted) or tampered (repointed elsewhere), whether while the daemon was not running or while it was
- **WHEN** the next reconcile pass runs — at daemon start or on its period
- **THEN** the link is re-created pointing to master exactly as the opt-in repair would do it, a tampered one backed up first, and the repair is recorded in the audit log with actor `system`

#### Scenario: boot heal leaves unsafe drift for a human to find
- **GIVEN** a foreign regular directory occupies a delivered skill's link path, or a binding's master folder no longer exists
- **WHEN** a reconcile pass runs
- **THEN** neither is touched — the foreign content and the missing master are left exactly as found — and each is reported as blocked with skill, agent, drift kind, path and reason

#### Scenario: a boot heal failure never blocks startup
- **GIVEN** the skill-link target raises while reading its state (e.g. a filesystem it cannot read)
- **WHEN** the daemon starts
- **THEN** the failure is reported and logged, the other targets are still reconciled, and the daemon still comes up

### Requirement: Repair repairable drift from master
The system MUST provide a drift repair that re-delivers repairable drift — missing link and tampered link — from the master library, and MUST NOT modify foreign/user content (replaced-with-regular), a missing master, or an orphan master; those are left intact and reported as requiring manual action. This repair runs (a) automatically per "Heal safely repairable drift on every pass", audited with actor `system`, and never allowed to fail startup; and (b) on demand via REST (`POST /skills/repair`, or `POST /api/v1/reconcile/apply`) and the Skills page's **Repair** for anyone who wants to trigger or inspect a repair directly, audited with the caller as actor. Each repair, automatic or on-demand, MUST be audited.

#### Scenario: opt-in repair re-delivers repairable drift from master
- **GIVEN** an agent skill directory where one enabled binding has a missing Coffer link, another has a tampered Coffer link (a stale link pointing elsewhere), a third binding's path is occupied by a foreign regular directory the user owns, and a fourth binding's master folder no longer exists,
- **WHEN** the user runs the opt-in repair (`POST /skills/repair`, or Repair on the Skills page),
- **THEN** the missing link is re-created pointing to master, the tampered link is moved to `~/.coffer/content/backup/skills/<agent>/<name>.coffer-backup-<ts>` (never left in the agent's skills directory, where the agent would load it as a second skill) and then re-created pointing to master, the foreign regular directory is left completely untouched and still appears in the report as requiring manual action, the missing-master entry is left and reported as requiring manual action, and each re-delivery is recorded as a repair event in the audit log.

### Requirement: List unmanaged skills in an agent's skill locations
The system MUST scan a registered agent's skill locations — `<config_dir>/skills` for both types, plus `~/.agents/skills` for `codex` — and list **unmanaged** entries: everything that is not a Coffer-managed link (a link whose target resolves inside `~/.coffer/vault/skills/`, or `~/.coffer/derived/skills/` for Coffer's own skill) and not Codex's `.system` entry. Each result carries name, path, location, and a `valid` flag (validation per "Validate imported skill folders against AgentSkills") with the failure reason when invalid. The scan is read-only and derived at request time; an unmanaged skill is never stored. An entry that is a symlink pointing outside the master store is listed as unmanaged but not adoptable; an entry without a valid SKILL.md is listed with `valid=false` and the reason, deletable but not adoptable until it validates.

#### Scenario: list unmanaged skills across an agent's skill locations
- **GIVEN** a registered `codex` agent with one Coffer-managed link in `<config_dir>/skills`, one hand-copied skill folder there, and another skill folder in `~/.agents/skills`,
- **WHEN** the user lists the agent's unmanaged skills,
- **THEN** Coffer returns exactly the two hand-placed skills — each with name, path, location, and a `valid` flag from SKILL.md validation — and excludes the managed link.

#### Scenario: exclude managed links and system entries from the unmanaged scan
- **GIVEN** an agent's skill directory containing Coffer-managed links and (for Codex) a `.system` entry,
- **WHEN** the user lists unmanaged skills,
- **THEN** neither the managed links nor the `.system` entry appear in the result.

#### Scenario: the unmanaged-skill list holds skill rows
- **GIVEN** a registered agent with one Coffer-managed link and one hand-placed skill folder in its skills directory
- **WHEN** `GET /api/v1/agents/{uid}/unmanaged-skills` is read
- **THEN** the answer holds exactly one skill, naming the hand-placed folder by its path with its `valid` flag
- **AND** the managed link is not among them

### Requirement: Delete an unmanaged skill on explicit request
Users MUST be able to delete an unmanaged entry as an explicit, confirmed action. Deletion MUST remove only that entry from disk, never master content or bindings, and MUST be audited. Coffer never deletes an unmanaged entry on its own.

#### Scenario: delete an unmanaged skill
- **GIVEN** an unmanaged skill folder in an agent's skill location,
- **WHEN** the user deletes it (an explicit, confirmed action),
- **THEN** the folder is removed from disk, an audit entry is recorded, and no master content or binding is touched.

### Requirement: Reconcile deliveries from state on every pass
The system MUST keep every agent's delivered set equal to the predicate of "Deliver a skill only where it is enabled and in scope" alone, as the skill-link target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"). An agent's wanted set is `{s.uid for s in skills if s.enabled and is_active(s.scope, agent.uid)}` — a free function over the agent alone, with no evaluator object to build and no machine to bind into one. The same skill row can still be wanted here and unwanted on another machine, because the `enabled` flag and the scope this predicate reads are this machine's own, and the round that brought the skill here brought neither. Each wanted delivery is a link at `<agent skill dir>/<skill name>` pointing at the skill's master folder, judged by both paths: a wanted skill the agent does not hold is delivered, a held copy no longer wanted is reclaimed, and a held link whose path no longer matches the agent's skill directory (its `config_dir` moved) is re-delivered at the new path and removed from the old one. Because the reconciler runs on every pass, this holds whatever changed the state — a skill enabled, disabled, rescoped, imported or removed, an agent registered or moved, a sync import, or nothing Coffer heard about — and a user's own write runs the pass for skills at once, so the change is visible when the write answers. An agent whose config does not parse is unknown, not an agent that wants nothing: its delivered links are left alone until the config reads again. Conflicts at target paths follow "Report a foreign target instead of overwriting it" (report, never overwrite). The agent resource carries no skill-delivery policy of any kind — no follow flag, no exclusion list, no per-agent opt-out; the only inputs are the skill's `enabled` flag and its `scope`.

#### Scenario: import delivers a skill only where its scope grants it
- **GIVEN** two registered agents, `claude_code` and `codex`,
- **WHEN** the user imports a skill whose scope names only the `claude_code` agent's uid,
- **THEN** the pass that follows delivers it to `claude_code` only, and `codex` receives nothing.

#### Scenario: an agent whose config cannot be read keeps its deliveries
- **GIVEN** an agent holding a delivered skill
- **WHEN** its config stops parsing and a pass runs
- **THEN** the link is left in place and nothing is reclaimed or reported

#### Scenario: moving an agent's config directory moves its deliveries
- **GIVEN** an agent holding a delivered skill, whose `config_dir` is then changed to another existing directory
- **WHEN** the change is saved
- **THEN** the skill is linked under the new directory's skills folder, the link under the old one is gone, and the move is recorded as a relink in the audit log

### Requirement: Remove a skill with all its deliveries
Removing a skill MUST remove every enabled per-agent symlink, cascade-delete bindings, delete the master folder, and audit the removal with a snapshot. A builtin skill is the one exception, and it is refused before any of this begins (see "Refuse deleting a builtin skill").

#### Scenario: remove a skill cleans up all bindings
- **GIVEN** a skill is enabled for two agents,
- **WHEN** the user removes the skill,
- **THEN** both target symlinks are removed, the bindings are cascade-deleted, the master folder is deleted, and an audit entry records the removal with a config snapshot.

### Requirement: Clean up an agent's skill bindings when the agent is removed
Removing an agent (via spec agent-registry) MUST trigger an `on_delete` hook in the skill module that removes that agent's bindings and symlinks before the agent row is deleted. This spec supplies the `cleanup_bindings_for_agent` callback at the composition root for the agent kind's `on_delete` seam.

#### Scenario: removing an agent (per spec agent-registry) cleans up its skill bindings
- **GIVEN** an agent has one or more enabled skills,
- **WHEN** the user removes the agent,
- **THEN** spec agent-registry's `on_delete` hook for the agent kind invokes the skill module to remove each binding and its symlink before the agent row is deleted; master folders are unchanged.

### Requirement: Show a skill's master folder read-only
The system MUST expose over REST a **read-only** view of a skill's master folder, which the web UI's Files tab renders: a recursive file tree (name, folder-relative path, absolute on-disk path, type, size, children) and the contents of an individual file (with its absolute on-disk path and containing folder's absolute path). Markdown files render as formatted Markdown; other text files show raw. Reads MUST be contained to the master folder — any path that resolves outside it (`..` traversal, absolute path, or escaping symlink) MUST be rejected. File reads MUST be size-capped (truncating with a `truncated` flag) and MUST flag non-UTF-8 / NUL-containing files as binary with empty content. No symlink-following out of the folder. The folder's absolute path is shown on the skill's page (**Copy master path**), and the folder is edited on disk, in the person's own editor (see "Manage skills on REST and on the Skills page"); no skill route writes a file inside it, and the one write Coffer makes there at the person's request is restoring an earlier version of the whole folder from its History tab ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder").

#### Scenario: view a skill's files as a tree
- **GIVEN** an imported skill whose master folder contains `SKILL.md` and a nested subdirectory with a file,
- **WHEN** the user requests the skill's file listing,
- **THEN** Coffer returns a recursive read-only tree rooted at the master folder, each node carrying its name, folder-relative path, absolute on-disk path, type (`file`/`dir`), file size, and children, sorted directories-first then by name, with no symlink target that escapes the folder included.

#### Scenario: view a single skill file's contents
- **GIVEN** an imported skill that contains a readable text file,
- **WHEN** the user requests that file's contents by its folder-relative path,
- **THEN** Coffer returns the file's text, its true byte size, its absolute on-disk path and its containing folder's absolute path, and `binary=false`/`truncated=false`; a non-existent file path returns a not-found error.

#### Scenario: reject reading a path outside the skill folder
- **GIVEN** an imported skill,
- **WHEN** the user requests file contents for a path that resolves outside the master folder (`..` traversal, an absolute path, or an escaping symlink),
- **THEN** the request is rejected with a `400` error before any file is read, and no content is returned.

### Requirement: Audit every skill lifecycle event
The system MUST record an audit entry for every import, delivery, reclaim, remove, and drift remediation event, each with timestamp, actor, target, event type and payload.

#### Scenario: audit skill lifecycle
- **GIVEN** the user has performed a representative sequence of operations,
- **WHEN** they view the audit log,
- **THEN** each event appears with timestamp, actor, target, event type, and any payload (e.g., before/after content hashes for updates).

### Requirement: Expose no skill tools over MCP
Coffer MUST expose no skill tool over MCP. Delivery is the whole delivery mechanism: Coffer supports exactly two agent types, `claude_code` and `codex`, and both read skills natively from `<config_dir>/skills/` — which is precisely where "Deliver a skill as a directory link" puts them. A `list_skills` / `load_skill` pair exists only for an agent with no native skill mechanism, and that set is empty. Serving skill content over MCP would also be a second, unscoped delivery path: it would read the master store directly, with no per-agent scope, and so hand an agent skills the predicate of "Deliver a skill only where it is enabled and in scope" does not grant it — including the rendered skill that tells an agent which knowledge collections it may reach. The gateway's builtin roster and the `initialize` instructions MUST therefore name no skill tool.

#### Scenario: Coffer exposes no skill tools over MCP
- **GIVEN** a client has completed the MCP handshake against Coffer's gateway,
- **WHEN** it calls `tools/list`,
- **THEN** no skill tool is among the results — `coffer__list_skills` and `coffer__load_skill` are absent — and the `initialize` instructions name no skill tool either, because every supported agent already reads its delivered skills from disk.

### Requirement: Regenerate Coffer's builtin skill from the build
The system MUST support a **builtin** skill — one whose `source` is `builtin` and whose master folder Coffer writes itself rather than a person importing it. Its content MUST be rewritten from the running build whenever the material it describes moves: at every daemon boot, and on each change to what it carries (for `coffer-guide`, a curation pass or a collection being created, deleted, enabled or disabled — [knowledge](../knowledge/spec.md) "Deliver the catalogue through the coffer-guide skill"). A write MUST be skipped when the master already holds exactly that text, so an unchanged boot registers, audits and re-delivers nothing. Everything downstream of the master folder is the ordinary machinery: the same validation ("Validate imported skill folders against AgentSkills"), the same resource, the same delivery predicate ("Deliver a skill only where it is enabled and in scope") and the same links ("Deliver a skill as a directory link"), the same drift verification and repair ("Report skill drift on request", "Repair repairable drift from master"). It follows that **an edit to a builtin skill does not survive** — the next rewrite replaces it — and the surfaces MUST say so rather than letting a person discover it; a correction belongs in the build, not in the folder.

A builtin skill MUST NOT be in the vault — neither its master folder nor its resource: both are filed in the derived class, the master under `~/.coffer/derived/skills/<name>/` and the resource under `~/.coffer/derived/resources/skill/` ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature", [vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves"). It is derived output, regenerated on each machine from material that already converges plus that machine's own reach, so publishing it is churn. The `skill` kind therefore files that one resource as derived while every other skill is a vault file, so no commit and no sync round carries it. The `builtin` source variant MUST still carry no fields — a path, a timestamp or a build id would each be a fact about one machine stored in a shape nothing reads. Seeding MUST NOT be able to fail a startup: a render or a write that fails leaves the previous master exactly where it was and every other skill still delivers.

#### Scenario: Coffer's own skill is rewritten from the build at every start
- **GIVEN** a registered builtin skill whose master `SKILL.md` a person has edited by hand,
- **WHEN** the daemon starts and the builtin seed runs,
- **THEN** the master folder holds the text the running build renders, the hand edit is gone, the resource's `version_hash` and description match the new text, and every agent the delivery predicate grants reads the new text through its existing link,
- **AND** a second start over an unchanged catalogue writes nothing, registers nothing and records no audit entry, while a render or a write that fails leaves the previous master intact and does not fail startup.

### Requirement: Refuse deleting a builtin skill
Deleting a builtin skill MUST be **refused** — `RESOURCE_PROTECTED`, 409 — through the framework's pre-write delete guard ([resource-framework](../resource-framework/spec.md) "Let a kind refuse a deletion before anything is torn down"), so the refusal is identical on `DELETE /api/v1/skills/{uid}` and on `DELETE /api/v1/resources/{uid}`, and nothing is torn down on the way. The reason is honesty rather than protection: the next boot writes the master folder back, so a delete would read as destructive and behave as a no-op that had removed some links in passing. `enabled` and `scope` MUST stay fully available on a builtin skill, and the refusal MUST name them — those two decide **reach**, which is the owner's call, while **existence** is not.

#### Scenario: deleting Coffer's own skill is refused on every surface
- **GIVEN** a registered builtin skill, delivered to an agent,
- **WHEN** a delete is attempted through the skill route and through the kind-agnostic resource route,
- **THEN** each is refused with `RESOURCE_PROTECTED` (409) and a message naming the skill and pointing at disable and scope instead,
- **AND** nothing was torn down on the way — the master folder, the resource row, the bindings and the agent's link are all exactly as they were — while disabling the same skill and narrowing its scope both succeed and reclaim its links normally.

### Requirement: Mark the builtin skill on every surface
Every surface that lists or shows a skill MUST mark a builtin one as built-in and MUST NOT offer its deletion: the read model carries an explicit `builtin` flag rather than leaving each client to infer it from the source variant, the web UI marks the row and withholds it from both the per-row delete and any bulk selection, and the API answers the same refusal if a delete is attempted anyway. Enable, disable and scope controls MUST remain offered unchanged — a surface that hid them would be hiding the only decisions the owner still has over this skill.

#### Scenario: the skills surface marks the built-in skill and offers no delete
- **GIVEN** the Skills page listing one imported skill and one builtin skill,
- **WHEN** the list is read,
- **THEN** the builtin row is marked as built-in with the reason available on the mark, and it offers neither the per-row delete nor a selection checkbox for the bulk delete, while the imported row offers both,
- **AND** the builtin row still offers enable/disable and scope, and the read model carries an explicit `builtin` flag rather than requiring the client to infer it from the source variant.

### Requirement: Keep one master folder per skill
The system MUST store each managed skill's content under `~/.coffer/vault/skills/<name>/`, with that path as the single editable source of truth; it is a vault folder, so every change to it — through Coffer or in the person's own editor — becomes a vault commit naming its writer ([vault-storage](../vault-storage/spec.md) "Admit every vault write through one compare-and-swap path"). Coffer's own builtin skill is the one exception, kept under `~/.coffer/derived/skills/` (see "Regenerate Coffer's builtin skill from the build"). Because the skill's `name` is fixed after registration (see "Register each skill as a resource with a SKILL.md-safe name"), the master folder, every delivered link at `<config_dir>/skills/<name>` and the SKILL.md frontmatter `name` MUST keep that name for the life of the skill. No operation on any surface moves the master folder or rewrites that frontmatter field. Per-agent bindings hold the resource's identity, not its name.

#### Scenario: a refused name change leaves the master folder where it is
- **GIVEN** an imported skill `before` delivered to a registered agent, whose SKILL.md carries comments, other frontmatter fields and a body
- **WHEN** the user tries to change its name to `after`, and then to give it a title
- **THEN** both are refused, and the master folder and the agent's delivered link are still at `before`, the link resolving to that master, with the same binding row recording the delivery
- **AND** SKILL.md and the skill's `version_hash` are unchanged by either request, and nothing exists at `~/.coffer/vault/skills/after/`

### Requirement: Expose unmanaged-skill operations on REST and the web
Unmanaged-skill operations MUST be available through the REST API (`GET`, `POST .../adopt` and `DELETE` under `/api/v1/agents/{uid}/unmanaged-skills`) and through the agent's Skills tab in the web UI; the command line carries no unmanaged-skill command. Delivery itself is not an operation on this surface: it is controlled by the skill resource's `enabled` flag and `scope` through the resource routes and the Skills page. The agent detail page decides nothing about delivery: its Skills tab opens with one **From Coffer** row — how many skills Coffer delivers to that agent, their first names, and **Open Skills ›**, a link to the Skills page narrowed to that agent — and then lists the unmanaged skills found on that agent's disk (see [agent-registry](../agent-registry/spec.md) "Show what Coffer manages for an agent in one row"). The Skills page accepts an `agent` query parameter, `/skills?agent=<uid>`, and then lists only the managed skills that reach that agent, with the agent named in a filter beside the search. The agent's Skills tab is the only web surface that lists unmanaged skills or adopts them, one at a time or several at once (see [agent-registry](../agent-registry/spec.md) "Act on several of an agent's own items at once"); the Skills page lists managed skills only (see "Manage skills on REST and on the Skills page").

#### Scenario: list, adopt and delete an unmanaged skill
- **GIVEN** a registered agent with two hand-placed skill folders in its skills directory
- **WHEN** the user lists `GET /api/v1/agents/{uid}/unmanaged-skills`, then adopts one with `POST .../unmanaged-skills/{skill}/adopt`, then deletes the other with `DELETE .../unmanaged-skills/{skill}` and confirms it
- **THEN** the list names both folders, the first becomes a managed skill and leaves the next list, and the second is removed from disk
- **AND** the command line offers no command that lists, adopts or deletes an unmanaged skill

#### Scenario: unmanaged skills are adopted only from the agent's Skills tab
- **GIVEN** an agent with a hand-placed skill folder
- **WHEN** the user looks for it in the web UI
- **THEN** the agent's Skills tab lists it as the agent's own, with Adopt, and the Skills page does not list it

### Requirement: Preview an unmanaged skill read-only
Users MUST be able to open one unmanaged skill (see "List unmanaged skills in an agent's skill locations") and read it without adopting it: its metadata — name, path, location, `valid` with the failure reason, whether it is a foreign link, and the SKILL.md `description` when the folder validates — a recursive file tree of the folder, and the contents of each file. The entry is found by the same scan the list runs, addressed by the agent, the scan location and the folder name, so a name the scan does not list — a missing folder, a dot-entry, a Coffer-managed link — is not found. The tree and file reads MUST follow the containment, size cap and binary detection of "Show a skill's master folder read-only", rooted at the unmanaged folder: a path that resolves outside it (`..` traversal, an absolute path, an escaping symlink) is rejected with `400` before anything is read. Nothing here writes. An invalid folder MUST still open, with its reason. The preview is on REST (`GET /agents/{uid}/unmanaged-skills/{skill}`, `.../files`, `.../files/content`, each taking `location`) and on the web as the unmanaged skill's detail page; the list read reports each unmanaged skill's name, absolute path, location, `valid` and reason, and its files can also be read on disk at that path.

#### Scenario: preview an unmanaged skill's metadata and files
- **GIVEN** an agent whose skills directory holds a hand-placed skill folder with a valid SKILL.md and a nested file
- **WHEN** the user requests that folder's metadata, its file tree and its SKILL.md
- **THEN** the metadata carries the folder's name, path, location, `valid` true and the SKILL.md description
- **AND** the tree lists the folder's entries directories-first, and the file read returns the SKILL.md text, with the folder left unchanged

#### Scenario: an invalid unmanaged skill still opens and says why
- **GIVEN** an agent whose skills directory holds a folder without a valid SKILL.md
- **WHEN** the user opens it
- **THEN** its metadata carries `valid` false with the reason and no description, and its files are still listed
- **AND** the detail page shows the reason before anything else and offers no adoption

#### Scenario: reject reading a path outside an unmanaged skill folder
- **GIVEN** an unmanaged skill folder
- **WHEN** the user requests file contents for a path that resolves outside it (`..` traversal, an absolute path, or a symlink pointing out)
- **THEN** the request is rejected with a `400` error and no content is returned

#### Scenario: read an unmanaged skill's files from its reported path
- **GIVEN** an agent with a hand-placed skill folder holding a nested file
- **WHEN** the user reads `GET /api/v1/agents/{uid}/unmanaged-skills` and reads the nested file at the path the skill's entry reports
- **THEN** the entry carries the folder's name, `valid` true and its absolute path, and the file on disk holds the nested file's contents
- **AND** the folder is still listed as unmanaged afterwards

### Requirement: Act on an unmanaged skill from its detail page
The agent's Skills tab MUST open an unmanaged skill's detail page when its row is clicked. The page's header carries the skill's name with an Unmanaged badge, a line naming whose skill it is, where it lives and how many files it has, **Adopt** as its one button ("Adopt an unmanaged skill into the master store"; left out for an invalid folder or a foreign link, whose reason shows first), and a ⋯ menu whose only item is **Delete…** ("Delete an unmanaged skill on explicit request", confirmed first). Below it are two tabs, **Overview** — the properties: description, folder, where it was found, how many files it has with a link to the Files tab (never the paths listed in a row) — and **Files**, the folder's tree beside a read-only viewer in the shared file tree and viewer toolbar. There is no Open folder action beside the header, because the files are shown here; opening a file in an editor or revealing it is on the viewer. A successful delete MUST return to the agent's Skills tab.

#### Scenario: open an unmanaged skill's detail page from the agent's Skills tab
- **GIVEN** an agent's Skills tab listing unmanaged skills
- **WHEN** the user clicks one row
- **THEN** that skill's detail page opens, and its Files tab shows the folder's tree and a read-only preview of the chosen file
- **AND** no row in the list carries an Open folder button

#### Scenario: adopt or delete an unmanaged skill from its detail page
- **GIVEN** an unmanaged skill's detail page
- **WHEN** the user chooses Adopt
- **THEN** the Adopt form for that folder opens
- **AND** when the user instead deletes it from the ⋯ menu and confirms, the folder is deleted and the page returns to the agent's Skills tab

### Requirement: Add skills from an archive
Users MUST be able to add skills from a `.zip` or `.skill` archive — uploaded from the web UI through the REST upload (`POST /api/v1/skills/stage/archive`). The archive is read into a staging area outside the master store, and before anything is extracted the system MUST reject the whole archive, naming the offending entries, when an entry has an absolute path or a `..` segment (zip-slip), is a symlink, or would take the archive past the 50 MB skill cap once uncompressed — judged on each entry's uncompressed size as it is read, not only on what the archive declares; an upload itself larger than the cap is refused before it is read. A skill is a folder whose `SKILL.md` is at the top of the archive or one folder down; an archive holding several such folders offers each, and the user chooses which to add. An archive with no `SKILL.md` in either place MUST be rejected with a message saying where one was looked for. Each chosen skill is then validated as a folder is ("Validate imported skill folders against AgentSkills"), and a name already taken follows "Import a skill from a local path": refused unless the user chooses Replace, or renames it in its `SKILL.md` and adds it again. Nothing is copied into `~/.coffer/vault/skills/` or registered until the user confirms (`POST /api/v1/skills/stage/{staging_id}/confirm`); the staging area is removed either way, and one never confirmed is removed after an hour. The skill's source records the archive's file name and the folder inside it. A script keeps the executable bit the archive recorded; no other recorded mode (setuid, write bits for others) is applied.

#### Scenario: a script from an archive stays executable
- **GIVEN** an archive whose `scripts/run.sh` was recorded executable, with setuid and world-write bits too, beside a plain data file
- **WHEN** it is extracted
- **THEN** `run.sh` is executable for owner, group and others with neither setuid nor world-write, and the data file is not executable

#### Scenario: a SKILL.md at the top or one folder down is found
- **GIVEN** one archive with `SKILL.md` at its top and another whose only entry is `review/SKILL.md`
- **WHEN** each is uploaded in the Add skill dialog
- **THEN** each shows one skill found, named from its `SKILL.md`

#### Scenario: an archive with several skills offers a choice
- **GIVEN** an archive holding `review/SKILL.md`, `release/SKILL.md` and `triage/SKILL.md`
- **WHEN** the user uploads it and picks `review` and `triage`
- **THEN** after confirming, those two skills are added and `release` is not

#### Scenario: an archive with no SKILL.md is rejected
- **GIVEN** an archive whose `SKILL.md` is two folders down
- **WHEN** it is uploaded
- **THEN** it is rejected with a message saying `SKILL.md` must be at the top or one folder down, and nothing is written

#### Scenario: unsafe archive entries are rejected before anything is written
- **GIVEN** archives with an entry named `../evil.sh`, an entry with an absolute path, a symlink entry, and an entry that decompresses past 50 MB
- **WHEN** each is added
- **THEN** each is rejected naming the offending entry, and nothing is written outside the staging area, to `~/.coffer/vault/skills/` or to the vault

#### Scenario: a taken name offers replace
- **GIVEN** a skill named `review` already added and delivered to an agent
- **WHEN** the user uploads an archive whose skill is also named `review`
- **THEN** the dialog marks it as taken and offers Replace; adding without Replace is refused with `conflict` (409), and choosing Replace swaps the content in place keeping its bindings

#### Scenario: a staged archive asks before adding
- **GIVEN** `skills.zip` holding two skills
- **WHEN** the archive is staged with `POST /api/v1/skills/stage/archive`
- **THEN** the answer lists what would be added and nothing is added until `POST /api/v1/skills/stage/{staging_id}/confirm` names `review`, which then adds `review` only

### Requirement: Add skills from a Git repository
Users MUST be able to add skills from a Git repository given its URL, an optional ref (branch, tag or commit; the default branch when omitted) and an optional subpath — in the Add skill dialog, or by staging it with `POST /api/v1/skills/stage/git`. A GitHub folder address (`https://github.com/<owner>/<repo>/tree/<ref>/<path>`) is read as the repository, the ref and the subpath. The system MUST fetch the repository with this machine's own `git` into a staging area, resolve the ref to one commit, and find skills under the subpath by the rule archives use (a `SKILL.md` at the subpath's top or one folder down), offering a choice when there are several. Git runs with no prompt and no secret Coffer supplies: a repository URL MUST NOT carry a user name or password (an `ssh://git@host/…` user name is allowed; a token or password in the URL is refused, because the URL is stored in the vault, in the skill's metadata and in API answers), and a repository is reachable when it is public or when this machine's git already holds a credential for it (its credential helper or SSH keys), and Coffer stores none. Only the `https`, `http`, `ssh`, `git` and `file` transports are allowed, and submodules are not fetched. Symlinks that leave the skill folder, and a checkout of the subpath past the 50 MB skill cap, MUST be rejected before anything is written. A chosen skill is validated, named and confirmed as an archive's is, and is recorded with a `git_import` source pinned to the commit it was copied from and the content hash of its folder there. It stays pinned to that commit until the person records a newer one after their agent brought it in ("Hand a Git-imported skill's update to an agent", "Record an update merged into local edits"), or changes its source. A repository that cannot be fetched, a ref that names no commit and a subpath the commit does not hold MUST each be reported with git's own message, and nothing is written. When this machine has no `git`, staging MUST be refused `SKILL_SOURCE_UNREACHABLE` whose details carry `reason: "git_missing"` and `handoff`, a prompt (Principle IV, AI-Native) asking the person's agent to install git on this machine — naming its OS and architecture — and to confirm with `git --version`, naming no install command; the add dialog MUST offer it beside the refusal, as the change-source dialog and the update check do beside theirs.

#### Scenario: a repository URL carrying a credential is refused
- **GIVEN** the daemon is running
- **WHEN** the user adds a skill from `https://user:token@github.com/acme/skills.git`, or from `https://token@github.com/acme/skills.git`
- **THEN** each is refused as an invalid location saying the URL must not carry a user name or password, and nothing is fetched or stored

#### Scenario: add a skill from a repository subpath at a ref
- **GIVEN** a repository whose `skills/review/SKILL.md` is valid on tag `v1.2`
- **WHEN** the user adds it with ref `v1.2` and subpath `skills/review` and confirms
- **THEN** the skill is added from that commit, and its source records the URL, `v1.2`, `skills/review` and the commit id
- **AND** a later commit on the repository changes nothing until the user applies it as an update

#### Scenario: an unreachable repository writes nothing
- **GIVEN** a URL that git cannot fetch
- **WHEN** the user tries to add from it
- **THEN** the dialog shows git's message and nothing is written

#### Scenario: a skill import with no git hands installing it to an agent
- **GIVEN** a machine with no `git`
- **WHEN** a Git source is staged
- **THEN** it is refused `SKILL_SOURCE_UNREACHABLE` with `reason: "git_missing"` and a prompt that names this machine's OS and architecture and `git --version`, naming no install command, and nothing is written
- **AND** the add dialog offers Copy prompt beside the refusal

### Requirement: Show the commands a skill declares it needs
The system MUST read the commands a skill declares it needs from the `requires` field of its `SKILL.md` frontmatter — a list, or a mapping whose `commands` key holds one — where each entry is a command name, a command name with a minimum version (`gh>=2.40`), or a mapping with `command` and an optional `version`. The skill's read model carries them as `requires`, each with its command and its minimum version when one is given, in the order declared; an entry that names no command is ignored rather than failing the skill. Declaring a requirement changes nothing about delivery: the skill is delivered whether or not the command is present. The web UI's Requires tab lists them, each naming the profiles that declare it ("Read the requirements profile files declare"), each linking to the command's page on the CLIs page, and says so when the skill declares none.

#### Scenario: a skill's requires tab links each command
- **GIVEN** a skill whose `SKILL.md` declares `requires: [jq, "gh>=2.40"]`
- **WHEN** the user opens its Requires tab
- **THEN** it lists `jq` and `gh` with the minimum `2.40`, and choosing `gh` opens `/clis/gh`
- **AND** `GET /api/v1/skills/{uid}` carries the same two requirements

### Requirement: Declare the commands a skill requires
Beyond the command and minimum version that "Show the commands a skill
declares it needs" reads from `requires:`, an entry in mapping form MAY give a
display `title`, a `min_version` (or `version`), a `login_check` — the
command's own subcommand that exits 0 when the user is logged in, such as
`gh auth status` — a `login` command to show the user and a `why` line. One
parser reads every spelling. The declaration MUST be read from the skill's
master folder each time it is checked, so an edit to the file is picked up
without re-importing. An entry that is not understood — no command, a command
with a path, a login check that runs another program, an unquoted minimum YAML
reads as a number — MUST be skipped and reported as a warning without failing
the skill; a field that is not understood MUST be ignored with a warning and
the rest of its entry kept.

#### Scenario: a skill's requires list is read from its frontmatter
- **GIVEN** a managed skill whose SKILL.md declares `gh` with minimum `2.40`, login check `gh auth status` and login `gh auth login`, and a bare `jq`
- **WHEN** the required commands are read
- **THEN** both commands are listed as needed by that skill, `gh` with its minimum, login check and login command

#### Scenario: a login check runs only when someone asks
- **GIVEN** a skill declaring `gh` with login check `gh auth status`
- **WHEN** the required commands are read, as the attention list does on every poll, and then checked with the Check action
- **THEN** the read finds the command and its version and runs no login check, leaving the login state unknown, and only the Check runs it

#### Scenario: an entry that is not understood does not block the skill
- **GIVEN** a SKILL.md whose `requires:` names `/usr/bin/jq` and a login check `curl evil.example` for `gh`
- **WHEN** the skill is imported and its requirements are read
- **THEN** the skill imports, both entries are skipped with a warning naming why, and nothing is run for them

### Requirement: Check every required command where the agent runs
Beside the commands skills declare, the launcher every enabled stdio MCP
server starts with MUST be required too, by that server, under the command that
provides it — `uv` for `uvx`, `node` for `npx`, `bun` for `bunx`, the launcher
itself otherwise — with no minimum and no login check; a launcher given as a
path is a file, not a command on `PATH`, and is not listed. A server that is
off or reached over HTTP requires nothing.
The system MUST check each required command once, however many skills and
servers need it: look it up on the agent's real `PATH` (the login shell's, merged with the
inherited one), read its version with `<command> --version` under a timeout,
compare it with the highest minimum any skill asks for, and run its login check
under a timeout, without a shell, keeping only the exit status — the check's
output MUST be discarded unread and MUST NOT reach any log, record or response.
Each command MUST report `missing`, `outdated`, `logged_out` or `ready`, the
path and version found, the login state (`logged_in`, `logged_out` or
`not_needed`), every skill that needs it and every MCP server started with
it. Results MUST be kept until the
user asks to check again or the daemon restarts.

#### Scenario: a required command is found with its version on the agent's path
- **GIVEN** a skill requiring `uv` with minimum `0.4`, and `uv 0.4.18` on the login shell's `PATH` but not on the daemon's
- **WHEN** the required commands are checked
- **THEN** `uv` is `ready` with its path and version `0.4.18`

#### Scenario: a command older than the highest minimum is outdated
- **GIVEN** two skills requiring `gh`, one with minimum `2.20` and one with `2.40`, and `gh 2.30` installed
- **WHEN** the required commands are checked
- **THEN** `gh` is `outdated` against `2.40` and names both skills

#### Scenario: a failed login check reports not logged in without keeping its output
- **GIVEN** a command whose login check exits 1 after printing an account name
- **WHEN** the required commands are checked
- **THEN** the command is `logged_out`, and the printed text appears in no response, log line or audit record

#### Scenario: checking again probes afresh
- **GIVEN** a command reported `logged_out`
- **WHEN** the user logs in and asks to check it again
- **THEN** the command is probed again and reported `ready`

#### Scenario: a stdio MCP server's launcher is listed under the command that provides it
- **GIVEN** an enabled stdio MCP server `duckdb` started with `uvx`, one `files` started with `npx`, one started with `./run.sh`, and a skill requiring `uv` with minimum `0.4`
- **WHEN** the required commands are checked
- **THEN** `uv` is listed as needed by the skill and by `duckdb` (launcher `uvx`), and `node` as needed by `files` alone
- **AND** nothing is listed for `./run.sh`

### Requirement: Serve required commands on REST and the web
The required commands MUST be readable and checkable through
`GET /api/v1/clis`, `GET /api/v1/clis/{command}`, `POST /api/v1/clis/check`
and `POST /api/v1/clis/{command}/check`, each command carrying its hand-off
prompt and the MCP servers started with it (`needed_by_servers`: each server's
uid, name and launcher) beside the skills that need it (`needed_by`). An
agent reads the same list with `coffer cli list` (`--json` for the full rows,
hand-off prompts included), the one required-command command: it reads what
Coffer last found and MUST NOT run a check or a login check. Lists MUST put problems first: missing, then outdated, then not
logged in, then ready. The web UI's CLIs page shows them (spec web-ui "Show
every CLI a skill requires on the CLIs page") and a skill's detail page
carries a **Requires** tab listing what the skill declares, each linked to its
command's page and offering the hand-off for a command that needs the user.

#### Scenario: required commands list problems first
- **GIVEN** skills requiring a missing `jq`, an outdated `gh` and a ready `uv`
- **WHEN** the user reads `GET /api/v1/clis`
- **THEN** the commands come back in the order `jq`, `gh`, `uv`, each with its status and the skills that need it

#### Scenario: the route and the page carry the same prompt
- **GIVEN** a missing required command `jq` and a ready `uv`
- **WHEN** the user reads `GET /api/v1/clis/jq` and the CLIs page's Copy prompt for `jq`
- **THEN** both carry exactly the same `handoff.prompt`
- **AND** `GET /api/v1/clis/uv` carries a `null` `handoff` and the page offers no prompt for it

#### Scenario: a CLI page lists the MCP servers started with the command
- **GIVEN** an enabled stdio MCP server `duckdb` started with `uvx`, a skill `data-profiling` requiring `uv`, and no `uv` on the agent's `PATH`
- **WHEN** the user reads `GET /api/v1/clis/uv`
- **THEN** it is `missing`, `needed_by` names `data-profiling`, `needed_by_servers` names `duckdb` with launcher `uvx`, and its hand-off prompt names both

#### Scenario: an agent lists the command-line tools Coffer manages
- **GIVEN** a skill requiring a missing `gh`, an MCP server started with `uvx` and a ready `uv`, and `jq` added by hand with the title `JSON` and a description
- **WHEN** an agent runs `coffer cli list`, and then `coffer cli list --json`
- **THEN** the table lists `gh`, `uv` and `jq` problems first, each with its status, what it is for and who needs it — the skill, the MCP server, or added by hand
- **AND** the JSON carries the same rows as `GET /api/v1/clis`, and the command made that one read and started no check

### Requirement: Declare a command-line tool without a skill
The system MUST let a person add a command-line tool by hand, with no skill and
no MCP server behind it: `POST /api/v1/clis` takes a bare command name or the
absolute path of an executable, and optionally a `title`, a `description`, a
`min_version` and a `login_check` (a command line whose first word is the
command itself, run without a shell exactly as a skill's login check is). The
tool is kept as one entry in the vault's `cli-tools` state document — the
declaration only; where the command is found on one machine is machine-local and
never written there — and is then listed, checked and read like every required
command, with `added` true. When a skill or an MCP server also requires the
command the two are one entry, the hand-added title, description and minimum
taking precedence. `POST /api/v1/clis/preview` MUST report what Coffer finds for
a name or path before anything is saved — where, which version, whether it was
already added and whether a skill or server already requires it — and a tool that
is not on this machine MUST still be addable, then reading `missing`. A tool
added by hand and missing raises no attention item, because nobody asked for it
to work. `PATCH /api/v1/clis/{command}` changes the fields it carries (`null`
clears one; the command itself is fixed) and `DELETE /api/v1/clis/{command}`
drops the declaration only — a skill or server that requires the command keeps
it listed — and both refuse a command nobody added by hand with 404
`CLI_TOOL_NOT_DECLARED`, except that `PATCH` carrying only `description` MUST
keep that description for any listed command: a command a skill or server
requires is not the person's to declare, but what it is for is theirs to write.
Such a description is kept in the same `cli-tools` document, under `notes`, and
a hand-added tool's own description wins over it; a command nobody lists is
refused with 404 `CLI_NOT_KNOWN`. A name added twice is refused with 409
`CLI_TOOL_EXISTS`, and a bad name, path, minimum version or login check with 400
`CLI_TOOL_INVALID`. Each add, edit and removal MUST be audited. Coffer MUST NOT
read a command's `--help`, build a tree of its subcommands or keep one: what it
knows of a tool is its path, its version and its login state.

#### Scenario: a command-line tool is added with no skill
- **GIVEN** no skill and no MCP server requiring `jq`, and `jq 1.7.1` on the path
- **WHEN** the user adds `jq` with a title, a description and the minimum `1.6`
- **THEN** `GET /api/v1/clis` lists `jq` as `ready`, added by hand, needed by nobody, and the vault's `cli-tools` document holds the declaration and no path
- **AND** adding it again is refused with `CLI_TOOL_EXISTS`, and a minimum of `latest` with `CLI_TOOL_INVALID`

#### Scenario: a hand-added tool and a skill are one entry
- **GIVEN** a skill requiring `jq` with minimum `1.5`, and `jq` added by hand with the title `Mine` and minimum `1.7`
- **WHEN** the commands are listed, and then the hand-added declaration is removed
- **THEN** one entry `jq` is listed, titled `Mine` with minimum `1.7` and needed by the skill
- **AND** after the removal it is still listed, no longer added by hand, with the skill's title and minimum `1.5`

#### Scenario: add, edit and remove a tool over REST
- **GIVEN** `jq` on the path and no declaration
- **WHEN** the user adds `jq` with the title `JSON`, then sends `PATCH /api/v1/clis/jq` with the title `null`, then `DELETE /api/v1/clis/jq`
- **THEN** the tool is listed as added by hand after the first, its title is cleared by the second, and it is gone after the third
- **AND** repeating the delete is refused with 404 `CLI_TOOL_NOT_DECLARED`

#### Scenario: a required tool takes a description and nothing else
- **GIVEN** a skill requiring `jq` and no declaration
- **WHEN** the user sends `PATCH /api/v1/clis/jq` with only a description, then one with a title, then one describing a command nobody lists
- **THEN** `jq` reads that description, still not added by hand, and the vault's `cli-tools` document keeps it under `notes`
- **AND** the title is refused with 404 `CLI_TOOL_NOT_DECLARED` and the unknown command with 404 `CLI_NOT_KNOWN`

### Requirement: Hand a required command to an agent with a prompt
The system MUST NOT install, update or log in to a required command itself.
For a command that is `missing` or `outdated` it MUST offer a prompt, built by
the daemon, for the user to give their agent, which names the command (and its
title), every skill that needs it with the minimum version each asks for, every
MCP server started with it and the launcher it is started with, what was found
for an outdated one, and this machine's operating system and CPU
architecture; asks the agent to choose the install method that suits this
machine, to check with the user before running anything that needs `sudo` or
changes system settings, and to confirm with `<command> --version` when it is
done; and says that any login is left to the user, whose credentials the agent
does not handle. For a command that is `logged_out` the prompt MUST ask only
for help logging in: it names the login check that failed and the declared
login command, asks the agent to tell the user what to run, and leaves running
it and entering credentials to the user. A prompt MUST NOT name an install
command. A `ready` command MUST carry no prompt. The prompt MUST be served as
`handoff.prompt` on every response that carries the command, and the CLIs page's Copy prompt offers the same text.

#### Scenario: a missing command carries an install prompt for an agent
- **GIVEN** skills `issues` (minimum `2.40`) and `triage` requiring `gh` (titled GitHub CLI), and no `gh` on the agent's `PATH`
- **WHEN** the user reads `GET /api/v1/clis/gh`
- **THEN** its `handoff.prompt` asks to install `gh` (GitHub CLI), names `issues (version 2.40 or newer)` and `triage`, names the machine's OS and architecture, asks the agent to choose the install method, to check before anything that needs `sudo` or changes system settings, and to run `gh --version`, and leaves any login to the user
- **AND** the list carries the same prompt, and there is no route that installs

#### Scenario: a command that is not logged in carries a prompt that asks only for help logging in
- **GIVEN** `gh` installed with login check `gh auth status` failing and login command `gh auth login`
- **WHEN** the user reads its prompt
- **THEN** the prompt asks for help logging in, names the failing check and `gh auth login`, says the user runs the login and enters anything it asks for, and asks for no install

#### Scenario: a ready command carries no prompt
- **GIVEN** a required command that is present, current and needs no login
- **WHEN** the user reads it
- **THEN** its `handoff` is null

### Requirement: Resolve a folder in the way of a skill's link
When an agent's link path for a skill holds a real folder that is not Coffer's link (drift kind "foreign content at the link path"), the system MUST offer two confirmed choices for that one agent's copy, on REST (`GET /skills/{uid}/copies/{agent_uid}` compares the two sides, `POST /skills/{uid}/copies/{agent_uid}/resolve` with `keep: master | agent` acts) and on the Skills page: **keep master** — the folder is moved to `~/.coffer/content/backup/skills/<agent>/<name>-<time>/`, never deleted, and Coffer's link is made in its place; **keep the agent's version** — its files become the master (its SKILL.md must name the same skill), so every other agent sees them through its link, and the folder is then backed up and linked the same way. The compare MUST show, per file, how the agent's folder differs from the master. Nothing else is touched, the choice is audited, and a builtin skill refuses both. Automatic repair keeps its rule: it never makes this choice.

#### Scenario: restoring from master backs the folder up and links it again
- **GIVEN** a skill delivered to an agent whose link was replaced by an edited real folder
- **WHEN** the user compares the copy and chooses to keep master
- **THEN** the compare lists the edited file with its diff, the folder is moved under `~/.coffer/content/backup/skills/<agent>/`, the agent's path is Coffer's link again, and the drift report no longer lists it

#### Scenario: adopting the agent's version makes it the master for every agent
- **GIVEN** a skill delivered to two agents, and the first agent's link replaced by an edited real folder
- **WHEN** the user chooses to keep that agent's version
- **THEN** the master holds the edited files, the first agent's path is Coffer's link again, and the second agent reads the edited files through its link

### Requirement: Refuse deleting a skill whose copy Coffer did not make
Deleting a skill MUST be refused with `409 SKILL_COPY_NOT_OURS` — naming the path and the agent — when any agent's delivery path for it holds a real folder that is not Coffer's link and not a copy Coffer made; nothing is removed then (not the master, not the record, not any other agent's link). The Skills page's delete confirmation stays open on the refusal and says which folder and what to do.

The delete MUST also be possible while leaving such a folder alone: `DELETE /api/v1/skills/{uid}?keep_foreign_copies=true` removes the master, the record and every link Coffer made, leaves each folder Coffer did not make exactly where it is, and answers `kept_copies` — the agent name and path of each folder left. Without the option the answer is `kept_copies: []`. `POST /api/v1/skills/bulk-delete` takes `uids` and the same `keep_foreign_copies` flag and deletes each skill on its own: one refused never stops the others, and every skill gets a result — `uid`, `name`, `deleted`, `kept_copies` and, when it was not deleted, the error's `error_code`, `error_message` and `error_details`. The Skills page's delete confirmation offers "Delete, keep <agent>'s folder" on the refusal.

#### Scenario: a folder Coffer did not make stops the delete
- **GIVEN** a skill whose link in one agent was replaced by a real folder
- **WHEN** the user deletes the skill
- **THEN** the delete is refused with the folder's path, and the master folder, the skill record and the agent's folder are all still there

#### Scenario: a skill is deleted and the agent's own folder kept
- **GIVEN** a skill delivered to two agents, one of whose links was replaced by a real folder
- **WHEN** the user deletes it with `keep_foreign_copies`
- **THEN** the master folder, the record and the other agent's link are gone, the real folder is untouched, and `kept_copies` names that agent and path

#### Scenario: a bulk delete reports each skill
- **GIVEN** two skills, one of which has a real folder in an agent in place of its link
- **WHEN** both are deleted through `POST /api/v1/skills/bulk-delete` without `keep_foreign_copies`
- **THEN** the clean one is deleted, the other is not and carries `SKILL_COPY_NOT_OURS` with the folder's path, and a second call with `keep_foreign_copies` deletes it and names the folder it kept

### Requirement: Act on a folder in the skills store that no skill claims
The system MUST list the folders in `~/.coffer/vault/skills/` that no skill record claims (`GET /skills/orphans`: each with its path, whether its SKILL.md is valid and names the folder, its file count and when the folder last changed) and let the person read one's files without touching them (`GET /skills/orphans/{name}/files` for the tree and `GET /skills/orphans/{name}/files/content?path=` for one file — the shapes, containment and size limits of a managed skill's file reads; a path outside the folder is refused with 400, a name that is no orphan with `404 SKILL_ORPHAN_NOT_FOUND`) and offer two actions on one: add it to the library in place (`POST /skills/orphans/{name}/adopt`, validated like an import, reach as for a fresh import) or move it out of the store (`DELETE /skills/orphans/{name}`, to `~/.coffer/content/backup/skills/orphans/`, never a hard delete). A folder a record claims is not an orphan, and both actions refuse it with `404 SKILL_ORPHAN_NOT_FOUND`. A folder whose name is not a safe skill name is not listed as one and is left alone, so one stray folder never stops delivery for every skill.

#### Scenario: a folder with an unsafe name does not stop delivery
- **GIVEN** a skills store holding a valid skill and a folder named `my skill`
- **WHEN** deliveries are reconciled and the orphans are listed
- **THEN** the valid skill is delivered, the odd folder is not listed or touched, and nothing fails

#### Scenario: an orphan folder is added in place or moved out
- **GIVEN** two folders with valid SKILL.md files in the skills store that no skill claims
- **WHEN** the user adds the first to the library and moves the second out
- **THEN** the first is a skill in the library, the second is under the backup folder and no longer in the store, and neither is listed as an orphan

#### Scenario: an orphan folder's files can be read
- **GIVEN** an orphan folder holding SKILL.md, a text file and a binary file
- **WHEN** the person reads its file tree and each file, and asks for a path outside the folder
- **THEN** the tree and the text come back, the binary file is flagged binary with no text, the outside path is refused with 400, and a name that is no orphan is refused with `SKILL_ORPHAN_NOT_FOUND`

### Requirement: Say when a skill's master folder is gone
Every read of a skill MUST carry `master_missing` — true when its master folder is no longer on disk — whether or not the skill is enabled, so a surface can say so even for a skill that is off and has no delivery the drift report would look at.

#### Scenario: a skill whose master is gone says so
- **GIVEN** an imported skill
- **WHEN** its master folder is removed outside Coffer
- **THEN** reading the skill reports `master_missing: true`, and it reported false before

### Requirement: Change a Git-imported skill's source
The system MUST let the user move a Git-imported skill to another repository, ref or folder (`POST /skills/{uid}/source/change` with `url`, `ref` and `path`) without replacing anything first: the new source is staged the way an add from Git is, must hold one valid skill with the skill's fixed name, and the answer carries the stage, the new commit and the names of the files that would be added, removed or changed against the skill's current folder — names only, no diff. Confirming it (`POST /skills/{uid}/source/change/apply` with that stage) swaps the folder in atomically, keeps the skill's reach and delivered links, records the new source pinned to the new commit and is audited as an update; cancelling the stage (`DELETE /skills/stage/{staging_id}`) leaves the skill and its source as they were. A stage that is gone, or belongs to another skill, is refused and changes nothing.

#### Scenario: a new source is shown against the current version first
- **GIVEN** a skill added from one repository
- **WHEN** the user changes its source to a folder of another repository and then applies the preview
- **THEN** the answer lists the names of the files that differ from the current folder, with no diff, while the folder is still unchanged, and after applying the folder holds the new source's files and the skill records the new repository, folder and commit

### Requirement: Record an update merged into local edits
After a Git-imported skill's master folder has taken an upstream update (by the person's agent, per the hand-off of "Hand a Git-imported skill's update to an agent", whether or not it had local edits), the person MUST be able to record it — **I merged it** beside the hand-off, confirmed first; `POST /api/v1/skills/{uid}/source/merged` with the upstream `commit`. Recording MUST move the pin to that commit and MUST NOT touch the master folder's files; the pin's content hash becomes that commit's own content, so a folder that kept local edits still counts as locally edited against its new base and the next update's hand-off lists exactly the edits carried over. The update is no longer offered, and the recording is audited as `skill_update_merged` with the old and the new commit. The commit MUST be an update waiting for the skill — the ref's newest commit or one of the commits between the pin and it that change the skill's folder, given in full or by a unique prefix of at least seven characters — and anything else (no newer commit, the pinned commit itself, a commit not on the ref) MUST be refused with `409 SKILL_UPDATE_NOT_PENDING`, changing nothing.

#### Scenario: recording a merge moves the pin and keeps the merged files
- **GIVEN** a skill pinned to `a1` with a local edit, `main` at `c3`, and the master folder merged with `c3` by an agent
- **WHEN** the user chooses I merged it and confirms, or posts `c3` to `POST /api/v1/skills/{uid}/source/merged`
- **THEN** the skill is pinned to `c3`, the master folder's files are exactly as the merge left them, `c3` is no longer offered, and the recording is audited as `skill_update_merged` from `a1` to `c3`
- **AND** when `main` moves on again the update's hand-off lists only the edit carried over as a local edit

#### Scenario: recording a merge refuses a commit that is not the update
- **GIVEN** a skill pinned to `a1`
- **WHEN** a merge is recorded against `a1` itself, against a commit that is not on the ref, or while the ref has nothing newer
- **THEN** it is refused with `409 SKILL_UPDATE_NOT_PENDING`, the pin stays at `a1`, and nothing is audited

### Requirement: Hand unsettled skill drift to an agent with a prompt
The three drift kinds no pass settles — a folder Coffer did not make at a skill's link path, a folder in the skills store no skill owns, and a skill whose master folder is gone — MUST each carry a hand-off prompt (Principle IV, AI-Native) built from the finding alone, the same text on the drift report entry (`handoff` on `POST /skills/verify` and `POST /skills/repair`) and on the finding's attention item: for a folder in the way, compare it with the skill's master folder, say whether it holds edits worth keeping, and recommend **Adopt this folder** or **Replace it with Coffer's link**; for a folder no skill owns, say what it is and whether its `SKILL.md` names it, and recommend **Add to library** or **Delete folder**; for a missing master, look for a copy that can be restored (the folders Coffer set aside under `~/.coffer/content/backup/skills/`, a copied copy in an agent's skills folder, the skill's source, and the master folder's own versions in the vault's git history) and, once the person agrees, copy it back to where the master belongs. The prompts MUST tell the agent to move, delete or edit no folder itself except that one agreed copy; the choice stays the button the person presses, and the buttons stay (Check again, Repair, the two choices of "Resolve a folder in the way of a skill's link", Add to library and Delete folder, Remove the skill). The Skills page MUST offer Copy prompt and, where a managed agent is available, Ask an agent beside each such finding, in the compare of a folder in the way, on the pane of a folder no skill owns and on the Files tab of a skill whose master is gone. A missing or tampered link carries a `null` `handoff`: Repair is its fix. The attention items' reasons for these kinds MUST name no command to run.

#### Scenario: a folder in the way is handed to an agent to compare
- **GIVEN** a skill whose link path in an agent's skills folder holds a real folder with a file of the user's
- **WHEN** the drift report runs and the attention list is read
- **THEN** the report entry's hand-off names that folder and the skill's master folder, offers the choice between Adopt this folder and Replace it with Coffer's link, and tells the agent to move, delete or edit no folder itself
- **AND** the attention item carries the same prompt, its reason names no command, and the folder is left exactly as it was

#### Scenario: a missing master is handed to an agent to find a copy
- **GIVEN** a delivered skill whose master folder was removed outside Coffer
- **WHEN** the drift report runs and the attention list is read
- **THEN** the report entry's hand-off names where the master folder belongs, the backup folder under `~/.coffer/content/backup/skills/` and the skill's recorded source, and asks for a copy to be copied, not moved, back once the person agrees
- **AND** the attention item carries the same prompt and its reason names no command

### Requirement: Tell a skill that declares nothing from one that has not declared
A skill whose SKILL.md and every `profiles/*.md` frontmatter lack a `requires` key MUST be **undeclared**: Coffer does not know what it needs, which is not the same as needing nothing. A `requires:` key anywhere — even an empty `[]` or `{}` — MUST make the skill **declared**, and an explicit empty declaration means it needs nothing. The skill's read model MUST carry `requires_declared` (`true` when declared), read from the master folder each time like the rest of `requires_*`. Being undeclared MUST NOT change delivery, add an attention item or mark the skill in the Skills list; the Requires tab alone says so (spec web-ui "Lay out the Skills page as the canvas draws it"). Declaring is the skill author's choice: Coffer never requires it.

#### Scenario: a skill with no requires key has not declared
- **GIVEN** a skill whose SKILL.md and profile files carry no `requires` key
- **WHEN** it is read through `GET /api/v1/skills/{uid}`
- **THEN** `requires_declared` is `false` and every `requires_*` list is empty

#### Scenario: an empty requires is a declaration
- **GIVEN** a SKILL.md declaring `requires: []`
- **WHEN** its requirements are read
- **THEN** the skill is declared and has no requirements

#### Scenario: a profile's requires key makes the skill declared
- **GIVEN** a SKILL.md with no `requires` key and a profile file whose frontmatter declares `requires: []`
- **WHEN** the skill is read
- **THEN** `requires_declared` is `true`

### Requirement: Hand a skill's review to an agent
`POST /api/v1/skills/conformance/handoff` with `{uids: [...]}` (at least one; an unknown uid is `404`) MUST answer `{prompt}`: one hand-off prompt (Principle IV, AI-Native) covering every named skill, built when asked from the master folders as they are, so it is never stale. Per skill the prompt MUST name the skill, its master folder (the only place to edit), whether it is undeclared or declared, and its source; for a Git-imported skill it MUST say that edits are recorded as local edits against the pinned commit and kept across updates, and suggest proposing the change upstream too. The prompt MUST ask the agent to read the coffer-guide skill and each skill's whole folder, then to review and propose what it would change and why, ask which proposals to apply, edit only what the person agrees to and the master folder only, show the diff and commit nothing. Everything in it is a suggestion the person can decline; Coffer never requires a skill to change. The only thing Coffer reads is `requires:`, so the prompt MUST say that a declaration, if wanted, lists only what the skill itself uses — the commands it runs (with `min_version`, `login_check` — a subcommand of the same command that exits 0 when logged in — `login` and `why`), the Coffer secrets it uses by id, and the MCP servers and tool groups it calls by their Coffer name — and never what another skill it delegates to needs; that `requires: []` says it needs nothing; and that `metadata.requires` stays for the skills it loads. The prompt MUST tell the agent not to restructure a skill, add a profiles folder or rename or move files for a library convention, and, where a file holds a secret's value or the person's own identity, to point it out and suggest Coffer's secret store or deriving it at run time while leaving it as it is when the person prefers. It MUST name no install command. A Built-in skill's prompt says not to edit it.

#### Scenario: the review prompt names each skill's folder, declaration and source
- **GIVEN** an undeclared Git-imported skill and a declared skill imported from a folder
- **WHEN** one prompt is asked for both
- **THEN** it names both master folders, says the first declares nothing and the second has a declaration, says edits to the Git-imported skill are kept across updates as local edits and suggests proposing them upstream

#### Scenario: the review prompt offers suggestions and restructures nothing
- **GIVEN** a prompt asked for one skill
- **WHEN** its text is read
- **THEN** it says everything is a suggestion the person can decline, asks the agent to ask which suggestions to apply, forbids restructuring, a profiles folder and renames, leaves secrets and identity as they are when the person prefers, tells the agent to commit nothing, and names the coffer-guide skill

### Requirement: Declare the secrets a skill requires
The mapping form of a skill's `requires:` frontmatter MAY name the Coffer
secrets the skill needs under `secrets:` — `requires: {commands: [...],
secrets: [...]}` — each entry a secret name as the secret store accepts it.
The list form of `requires:` MUST stay commands only. An entry that is not a
valid secret name, and a name given twice, MUST be skipped with a warning
without failing the skill. A key of the mapping other than `commands`,
`secrets` and `tools` MUST be refused: it is reported as a warning and nothing under it
is read. The declaration MUST be read from the skill's master folder each time
it is read. The skill's read model MUST carry the declared secrets as
`requires_secrets`, in the order declared, each with its `name` and whether the
secret store holds a secret under that name (`is_set`) — answered by presence
alone: no secret value is read, and no value appears in the read model. The value is set by
the person on the Secrets page, and the skill's commands receive it through
`coffer run --secret`. Declaring a secret changes nothing about delivery: the
skill is delivered whether or not the secret is set.

#### Scenario: a skill's secrets are read from the mapping form
- **GIVEN** a SKILL.md declaring `requires: {commands: [gh], secrets: [GITHUB_TOKEN, "bad name", GITHUB_TOKEN, npm.token]}`
- **WHEN** its requirements are read
- **THEN** `gh` is the one command and `GITHUB_TOKEN` and `npm.token` are the secrets, in that order
- **AND** `bad name` and the second `GITHUB_TOKEN` are skipped, each with a warning naming why

#### Scenario: an unknown key under requires is refused
- **GIVEN** a SKILL.md declaring `requires: {commands: [jq], flags: [rg], env: {A: b}}`
- **WHEN** its requirements are read
- **THEN** `jq` is the one requirement and nothing under `flags` or `env` is read
- **AND** one warning names `env` and `flags` as refused

#### Scenario: the read model says whether each declared secret is set
- **GIVEN** an imported skill declaring the secrets `GH_TOKEN` and `NPM_TOKEN`, with only `NPM_TOKEN` in the secret store
- **WHEN** the skill is read through `GET /api/v1/skills/{uid}`
- **THEN** `requires_secrets` is `GH_TOKEN` not set and `NPM_TOKEN` set, and no secret value appears in the response
- **AND** once `GH_TOKEN` is stored the skill list reports both set

### Requirement: Report per agent whether a reach change was delivered
`PUT /api/v1/resources/{uid}/scope` for a skill MUST answer, beside the resource, `delivery`: one row per registered agent the new reach grants (and per agent a failed or blocked write names), each with `agent_uid`, `agent_name`, `ok` and, when it is not ok, the `reason` the link was not made. The reach is saved whether or not every delivery succeeded, so the page can say which agent was saved and which could not be linked. Kinds that deliver nothing answer `delivery: null`.

#### Scenario: a reach change reports delivery per agent
- **GIVEN** a skill and two agents, one of which already holds a real folder where the skill's link would go
- **WHEN** the skill's reach is set to every agent
- **THEN** the response's `delivery` lists the first agent ok and the second not ok with a reason, and a scope write on an agent answers `delivery: null`

### Requirement: Declare the tools a skill requires
The mapping form of a skill's `requires:` frontmatter MAY name the MCP servers and custom-tool groups the skill calls under `tools:` — `requires: {commands: [...], tools: [github, billing-api]}` — each entry the name the server or group has in Coffer, or a mapping with that `name` and a `why` line. The list form of `requires:` MUST stay commands only. An entry that is not a name, and a name given twice, MUST be skipped with a warning without failing the skill; so MUST a name that no MCP server and no custom-tool group has, the warning counted with the other skipped `requires:` entries in the CLIs list's `warnings`. The declaration MUST be read from the skill's master folder each time it is read. The skill's read model MUST carry the known tools as `requires_tools`, in the order declared, each with its `name`, its `uid`, its `kind` (`mcp_server` or `custom_tools`), its `status` — `off` when it is switched off, `failing` when its last connection test failed, `healthy` otherwise — and its `why`; and the skills it loads (`metadata.requires`, a list of skill names) as `requires_skills`, each with its `name`, whether it was `found` in the library, its `uid`, whether it is `delivered_to_same_agents` — every agent that gets this skill also gets that one — and the `missing_agent_names` that do not. Declaring a tool changes nothing about delivery: the skill is delivered whether or not the tool is on. The skill's Requires tab lists commands, secrets, tools and skills in that order, each tool and skill linking to its page; a skill whose required tool is `off` or `failing` is in the Skills list's "Needs attention" group, reading "Needs <tool> · off", and its header shows the pill "Tool off".

#### Scenario: a skill's tools are read from the mapping form
- **GIVEN** a SKILL.md declaring `requires: {commands: [gh], tools: [github, {name: billing-api, why: Reads invoices.}, "bad name", github]}`
- **WHEN** its requirements are read
- **THEN** `gh` is the one command and `github` and `billing-api` are the tools, in that order, `billing-api` with its why
- **AND** `bad name` and the second `github` are skipped, each with a warning naming why

#### Scenario: the read model says what state each declared tool is in
- **GIVEN** a skill declaring the tools `github` (an MCP server that is switched off), `billing-api` (a custom-tool group that is on) and `ghost` (nothing by that name), and `metadata.requires: [coffer-evidence]` for a skill delivered to fewer agents than this one
- **WHEN** the skill is read through `GET /api/v1/skills/{uid}`
- **THEN** `requires_tools` is `github` as `mcp_server` `off` and `billing-api` as `custom_tools` `healthy`, and `ghost` is not listed
- **AND** `requires_skills` is `coffer-evidence`, found, not delivered to the same agents, naming the agents it misses
- **AND** `GET /api/v1/clis` carries a warning for the skill naming `ghost` as skipped

### Requirement: Read the requirements profile files declare
A skill library MAY keep per-skill profiles at `<skill folder>/profiles/<name>.md`, one per environment, each with YAML frontmatter. A profile's frontmatter MAY carry the same `requires:` as `SKILL.md` (commands, secrets and tools, one parser). An agent chooses one profile at run time, which Coffer cannot know, so Coffer MUST read the union of the `requires:` of `SKILL.md` and of every `profiles/*.md`, read from the master folder each time, and MUST name the profiles that declared each requirement: a command, secret or tool several sources declare is one requirement carrying the highest minimum version, the first non-empty title, why, login check and login command, and the profiles that declare it — none when `SKILL.md` declares it too, because then it is needed whichever profile the agent picks. A warning from a profile MUST name its file (`profiles/<name>.md: ...`); an unreadable profile is skipped. The CLIs list's `needed_by` entry for a skill and the skill's Requires-tab commands, secrets and tools carry these names as `profiles`; the missing-secret and tool-off attention items count the profile-declared ones too. Coffer reads only what a skill declares and never scans its files to guess.

#### Scenario: a profile's requires joins the skill's
- **GIVEN** a skill whose `SKILL.md` declares `gh>=2.40` and whose `profiles/acme-team.md` frontmatter declares `gh>=2.50`, `smc` with a login check and the secret `ACME_TOKEN`
- **WHEN** its requirements are read
- **THEN** `gh` is one requirement with minimum `2.50` that names no profile, because `SKILL.md` declares it too
- **AND** `smc` and `ACME_TOKEN` are declared by `acme-team`

### Requirement: Report a secret a skill requires that is not set
A managed skill that declares a secret the secret store does not hold MUST
raise one item in the "needs you" list (spec resource-framework "Report what
needs a person across every kind"), of kind `skill` with the skill's uid and
name, reason code `skill_missing_secret`, a reason naming each such secret as
"secret <name> is not set", and as its action the Secrets page's own write
(`POST /api/v1/secrets`) with the secret's ref and no value. Setting a secret
is the person's task, so the item MUST carry no hand-off prompt. The check
MUST be made afresh on each read, so a secret the person has just set clears
the item.

#### Scenario: a secret a skill requires that is not set raises a needs-you item
- **GIVEN** a skill `triage` declaring `GH_TOKEN`, `NPM_TOKEN` and `SLACK_TOKEN`, and a skill `publish` declaring `NPM_TOKEN`, with only `NPM_TOKEN` stored
- **WHEN** the needs-you list is read
- **THEN** there is one item, for `triage`, reason code `skill_missing_secret`, naming `GH_TOKEN` and `SLACK_TOKEN` as not set
- **AND** its action is `POST /api/v1/secrets` with the ref `secret/GH_TOKEN` and no value, and it carries no hand-off prompt

### Requirement: Adopt an unmanaged skill into the master store
Users MUST be able to adopt a valid unmanaged skill. Adoption validates the folder per "Validate imported skill folders against AgentSkills", moves it to `~/.coffer/vault/skills/<name>/`, registers the `skill` resource, delivers the managed link (see "Deliver a skill as a directory link"), and records an enabled binding for that agent — in that order, with any failure before registration leaving the original folder unmoved and unchanged (after registration the master copy is authoritative; a delivery failure is surfaced and retried via the binding, never rolled back). The managed link is always delivered to the agent's canonical delivery location `<config_dir>/skills/<name>`: adopting from `<config_dir>/skills` replaces the original path in place, while adopting from `~/.agents/skills` consolidates — the original folder there is removed and the link lands in `<config_dir>/skills` (Codex reads both locations, so the agent keeps seeing the skill). Name collisions MUST be rejected with `conflict` (409); invalid folders and symlinks pointing outside the master store MUST be rejected with `unprocessable_entity` (422). Adoption is audited as an adoption event.

The adoption MAY name the skill and its reach. A `name` registers the skill under that name instead of the one its SKILL.md front matter carries: the master copy's `name:` line is rewritten, no other line is, and the original folder is untouched until the adoption has succeeded. A `reach` is one of every agent (the default), only the listed agents, or off — the skill is adopted switched off — which becomes the skill's `enabled` flag and `scope` ([resource-framework](../resource-framework/spec.md) "Carry a per-agent reach on every resource"); a request that names neither behaves as before. On the web, Adopt opens a form with exactly these two — **Name in Coffer**, checked against the library as it is typed, and **Reach** — and shows an error inside the form.

#### Scenario: adopt an unmanaged skill into the master store
- **GIVEN** an unmanaged skill folder with a valid SKILL.md whose name collides with no master skill,
- **WHEN** the user adopts it,
- **THEN** Coffer validates it per "Validate imported skill folders against AgentSkills", moves the folder to `~/.coffer/vault/skills/<name>/`, registers the `skill` resource, replaces the original path with the managed link, records a binding for that agent, and audits the adoption — and on any failure the original folder is left exactly where and as it was.

#### Scenario: adopt an unmanaged skill under another name and a narrower reach
- **GIVEN** an unmanaged skill `loose` that Claude Code holds
- **WHEN** the user adopts it as `notes` reaching only Codex
- **THEN** the managed skill is named `notes`, its master SKILL.md carries `name: notes` with every other line unchanged, and its scope names Codex alone
- **AND** adopting it switched off leaves the skill registered and disabled

#### Scenario: reject adopting an invalid or conflicting unmanaged skill
- **GIVEN** an unmanaged entry that lacks a valid SKILL.md, collides with an existing master skill's name, or is a symlink pointing outside the master store,
- **WHEN** the user attempts to adopt it,
- **THEN** the request is rejected with a reason-specific error (invalid: `unprocessable_entity` 422; name conflict: `conflict` 409; foreign link: `unprocessable_entity` 422), and nothing is moved, registered, or linked.

### Requirement: List the commands Coffer itself runs
Beside the commands skills declare, the stdio MCP launchers and the tools added
by hand, the system MUST list every command Coffer runs itself as a required
command — `git`, titled Git, which keeps the vault's history and syncs it —
with no minimum and no login check, whether or not anything else needs it. Such
a command is checked, cached and handed off like every required command and is
one entry with any skill, server or hand-added declaration of the same name
(the hand-added title taking precedence, then Coffer's). Each command MUST carry
`needed_by_coffer`, the uses Coffer runs it for (`vault_history`, `sync`), empty
when Coffer does not run it; `coffer cli list` names those uses, and the
hand-off prompt for a missing or outdated one says what Coffer itself uses it
for. A command Coffer needs MUST raise the same `cli_*` attention item as one a
skill requires, whether or not a skill needs it too: its reason says what Coffer
cannot do without it, and a missing one is an error rather than a warning, because
the vault's history stops. Sync raises no item of its own for a missing `git`.

#### Scenario: git is listed as needed by Coffer itself
- **GIVEN** no skill, MCP server or hand-added tool requiring `git`, and no `git` on the agent's `PATH`
- **WHEN** the user reads `GET /api/v1/clis/git`
- **THEN** it is `missing`, titled Git, with `needed_by_coffer` `vault_history` and `sync` and no skills or servers, and its hand-off prompt says Coffer itself uses it to keep the vault's history and to sync the vault
- **AND** the attention list carries exactly one `cli` item for it, an error whose reason says Coffer needs it to keep the vault's history and to sync the vault, and once `git` is installed a check reports it `ready` with no prompt

### Requirement: Hand a Git-imported skill's update to an agent
A skill with a `git_import` source MUST be checked for newer commits on its ref — on demand, from a **Check for updates** action on the skill's page (`POST /api/v1/skills/{uid}/source/check`), and in the background on the schedule the person chooses — by fetching the repository with this machine's `git` into a staging area; a check writes nothing to the master store and its result is kept on this machine only. When the ref has moved past the pinned commit with commits that change the skill's folder, the skill MUST show **Update available** on the Skills page and its detail page, with the commit range from the pinned commit to the new one. A source that cannot be fetched MUST be reported on the skill with git's message and the time of the last successful check, and changes nothing.

How often the background check runs MUST be a setting of this machine, **Check skills for updates** on Settings › General: **Every 6 hours** (the default), **Every day**, **Every week** or **Only when I ask**. It decides this machine's background `git fetch`, so it MUST be kept by the daemon in `~/.coffer/daemon-config.json` — never in the vault, never synced — and read and written over REST (`GET` / `PUT /api/v1/skills/update-check`). A change MUST take effect at once: the next background check is scheduled from the new choice, and **Only when I ask** stops background checks. **Check for updates** on a skill's page MUST work whatever the choice.

Beside the hand-off, while an update is available, the skill MUST offer two ways to look at the change outside Coffer, and Coffer draws no diff of its own: **Open in editor**, which opens the master folder in the preferred editor (`POST /api/v1/fs/open`), and **View upstream changes**. The skill's source status MUST carry the link for the latter, built by the daemon from the repository, the pinned commit and the newest commit: for a GitHub repository `https://github.com/<owner>/<repo>/compare/<pinned>...<new>`, for a GitLab repository (`gitlab.com` or a host whose name starts with `gitlab.`) `https://<host>/<group>/<repo>/-/compare/<pinned>...<new>` — read alike from an `https`, `ssh://` or `git@host:` URL — and none for any other host, where the page instead shows the commit range, which can be copied, and the subjects of the commits in it. A link MUST never carry a credential.

Coffer MUST NOT apply an update itself: there is no preview of the update's files, no apply, no Keep mine / Take theirs / Compare and no merge of its own. While an update is available, and only then, the skill MUST offer one primary action, **Hand off to <Agent> to update** — the hand-off split button of [web-ui](../web-ui/spec.md) "Hand a machine-dependent problem to an agent with one split button", which starts the default agent in the preferred terminal with the prompt sent, its menu holding the other installed agent and Copy prompt — whether or not the folder has local edits, with **I merged it** beside it ("Record an update merged into local edits"). `POST /api/v1/skills/{uid}/source/handoff` MUST answer the newest commit and the prompt (Principle IV, AI-Native), built by the daemon from the same module every hand-off uses: the skill's name; its master folder as the only place to edit; the pinned commit and the upstream commit with the subjects of the commits between them; the repository (without any credential in its URL), ref and folder to read upstream from, read-only; the files edited in the master folder since the pinned commit, or that there are none; to bring the new commit's content into the master folder keeping the local edits, asking the person where the two really disagree, and to show the person the diff; and that the person records the merge in Coffer when it is done, so the agent never calls that route itself. Building the prompt fetches upstream into a staging area that is removed again, and writes nothing to the master store or the pin. With no update available the route MUST be refused `409 SKILL_UPDATE_NOT_PENDING`.

#### Scenario: a newer commit shows update available
- **GIVEN** a skill pinned to commit `a1` of `main`, and `main` now at `c3` with commits that change the skill's folder
- **WHEN** the periodic check runs, or the user chooses Check for updates
- **THEN** the skill shows Update available with the range `a1..c3` on the Skills page and its detail page
- **AND** nothing under `~/.coffer/vault/skills/` has changed

#### Scenario: an unreachable source is reported and changes nothing
- **GIVEN** a Git-imported skill whose repository can no longer be fetched
- **WHEN** the user chooses Check for updates
- **THEN** the skill shows git's message and the time of its last successful check
- **AND** the folder and the pin are unchanged

#### Scenario: the update hand-off names the commits, the local edits and the read-only source
- **GIVEN** a skill pinned to `a1` whose `notes.txt` the user edited, and `main` at `c3` with a commit that changes the skill's folder
- **WHEN** the update hand-off is read
- **THEN** the prompt names the skill, the master folder as the only place to edit, `a1` and `c3` with the commit's subject, the repository, ref and folder to read upstream from with no credential in the URL, and `notes.txt` as a local edit, and tells the agent to keep the local edits, show the diff and leave recording the merge to the person
- **AND** for a skill with no local edit the prompt says there are none, and nothing on disk or in the pin has changed either way

#### Scenario: the update is offered only as a hand-off while an update is available
- **GIVEN** a skill showing Update available and a skill that is up to date
- **WHEN** the user opens each skill's page
- **THEN** the first offers Hand off to <Agent> to update and I merged it, and no preview, apply, Keep mine, Take theirs or Compare
- **AND** the second offers neither, and its update hand-off over REST is refused `409 SKILL_UPDATE_NOT_PENDING`

#### Scenario: an update is looked at in the editor or on the source's host
- **GIVEN** a skill pinned to `a1` with an update to `c3` available, from a GitHub repository, and another from a self-hosted repository
- **WHEN** the user opens each skill's page
- **THEN** the first offers Open in editor, which opens the master folder through the daemon, and View upstream changes, which opens `https://github.com/<owner>/<repo>/compare/a1...c3`
- **AND** the second offers no link and shows the range `a1..c3`, which can be copied, with the commits' subjects, and neither page draws a diff

#### Scenario: the compare link is built for GitHub and GitLab only
- **GIVEN** sources at `https://github.com/acme/skills.git`, `git@github.com:acme/skills.git`, `ssh://git@gitlab.com/group/sub/skills.git`, `https://gitlab.example.com/group/skills` and `https://git.example.com/acme/skills.git`
- **WHEN** the compare link from `a1` to `c3` is built for each
- **THEN** the GitHub ones read `https://github.com/acme/skills/compare/a1...c3`, the GitLab ones `https://gitlab.com/group/sub/skills/-/compare/a1...c3` and `https://gitlab.example.com/group/skills/-/compare/a1...c3`, and the last has none
- **AND** no link carries a user name or password

#### Scenario: the update check follows this machine's setting
- **GIVEN** a daemon with a Git-imported skill and the setting at its default
- **WHEN** the setting is read, changed to Every day, and then to Only when I ask
- **THEN** it first reads Every 6 hours, each change is written to `~/.coffer/daemon-config.json` and nothing in the vault changes, the next background check is scheduled a day after the last one, and with Only when I ask no background check runs
- **AND** Check for updates on the skill's page still checks the skill

### Requirement: Manage skills on REST and on the Skills page
Every management operation of a skill (import, update, remove, enable, disable, scope, verify) MUST be available through (a) the REST API and (b) the Skills page in the web UI; the command line carries no skill command. The REST routes are `GET /api/v1/skills` and `GET /api/v1/skills/{uid}` to read, the imports of "Import a skill from a local path", "Add skills from an archive" and "Add skills from a Git repository" (`POST /api/v1/skills/import` and `/stage/*`), the update check, hand-off and merge record of "Hand a Git-imported skill's update to an agent" and the source change (`/api/v1/skills/{uid}/source/*`), `DELETE /api/v1/skills/{uid}`, the resource update route for `enabled` and `scope`, and `POST /skills/verify` for the drift report. Three repair operations are the web UI's and REST's alone: adopting or removing an orphan master folder (`/skills/orphans*`), resolving a copy an agent holds (`/skills/copies/{agent}/resolve`) and changing a Git-imported skill's source (`/skills/{name}/source/change`); the drift report names an orphan and what to do about it. `enable` and `disable` switch the skill resource's own `enabled` flag, which with its scope drives delivery ("Deliver a skill only where it is enabled and in scope"); there is no per-(skill, agent) switch on any surface, and the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes do not exist. There is no edit operation: a skill's name is fixed, it has no title, and its description is its SKILL.md's, edited in the file.

A skill's master folder is plain files a person edits in their own editor. Its absolute path is shown on the skill's page (**Copy master path**) and in the REST file tree, and it is read and edited on disk; the command line carries no command that lists, prints or writes a file inside it. The REST file tree and file read ("Show a skill's master folder read-only") serve the web UI's Files tab and programmatic clients; nothing in Coffer writes a file inside the folder on the person's behalf, except putting back an earlier version the person chose on the History tab.

The Skills page is the library of managed skills beside the open skill: a list with search, an All / On / Off filter and row multi-select for bulk reach and bulk delete, next to the selected skill's detail. It has one **Add skill** action whose dialog offers three sources: **Folder** — a path field that takes a folder chosen with the folder picker or a path typed or pasted into it, trimmed of surrounding whitespace and quotes before it is sent; **Archive** — a `.zip` or `.skill` file uploaded from the browser; and **Git repository** — a URL with an optional ref and subpath; under the source, an **Available to** reach control whose choice every added skill takes (every agent unless narrowed). Each source first shows what it found — the skill or skills, their names and descriptions, any that cannot be added and why, and any whose name is taken, with Replace offered for those — and writes nothing until the user confirms. The dialog offers no way to create a new skill from scratch: a skill is authored in the user's own editor and added from where it lives. It shows each skill by its name, which it offers no way to edit. It lists only the skills Coffer manages: an agent's own (unmanaged) skills, and adopting them, live only on that agent's Skills tab (see "Expose unmanaged-skill operations on REST and the web"), and while no skill is managed the page's empty state may link to the agents' Skills tabs but lists nothing from them. It manages the skill resource itself, not per-agent bindings. A row carries a Built-in mark and an Off mark, and in place of its description the one thing that needs the reader, most urgent first: its master folder is gone ("Say when a skill's master folder is gone"), a folder is in the way of an agent's link ("Resolve a folder in the way of a skill's link"), a command it declares is missing, not logged in or too old, its Git source is unreachable, or an update is waiting ("Hand a Git-imported skill's update to an agent"). Folders in the skills store that no skill claims are listed apart, under **Not in your library** ("Act on a folder in the skills store that no skill claims"). A skill's detail (`/skills/<name>`, addressed by its fixed name as [web-ui](../web-ui/spec.md) "Lay out every detail page's tabs alike" says) shows its name, reach, a **⋯** menu — Open in editor, Reveal in Finder, Copy master path, Check agents' copies, Turn off, and Delete… (disabled on a builtin skill) — its description, and its master path or, for a Git skill, its repository, folder and pinned commit; above its tabs, a banner for each thing that needs the reader, with at most one action; and it has four tabs, in this order, each at its own path:

- **Files** (the default, `/skills/<name>`) — the file tree beside the read-only viewer of "Show a skill's master folder read-only", opening with `SKILL.md` selected and rendered; a **Preview / Source** toggle switches a Markdown file between rendered and raw text. A text file offers **Open in editor**, a binary file **Open in default app**, and both **Reveal in Finder**; a file too large to read whole shows its start. The tab edits nothing: a file is changed in the person's own editor. There is no separate SKILL.md tab.
- **Delivery** (`/skills/<name>/delivery`) — every registered agent with the state of its copy: linked, copied where links are not allowed ("Fall back to copying where links are unavailable"), differing from master (the drift kinds of "Report skill drift on request" — a folder in the way offers **Review…**), or not delivered and why (the skill is off or the agent is outside its reach); **Check again** runs the drift report afresh.
- **Requires** (`/skills/<name>/requires`) — the commands the skill declares it needs ("Show the commands a skill declares it needs"), each with its state on this machine and opening that command's page on the CLIs page ([web-ui](../web-ui/spec.md) "Show every CLI a skill requires on the CLIs page"); the tab offers nothing that installs or logs in — those live on the CLIs page.
- **History** (`/skills/<name>/history`) — the master folder's versions from the vault's history ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder"), newest first, each with who wrote it, when and what it changed; choosing one shows the diff of every file it changed, or how the folder differs now with **Compare with current**, and **Restore this version…** asks first and then restores the whole folder as a new version, removing files added since, with a refusal shown in its dialog ([web-ui](../web-ui/spec.md) "Show a vault file's history on a History tab"). Coffer's own builtin skill is not in the vault: its History tab says it has no history and reads none.

A skill added from a Git repository also shows its source — the repository, the folder, the pinned commit and the update status — with **Check now** and **Change source…** ("Change a Git-imported skill's source").

The list's reach mark and the detail carry one reach button labelled with the answer ("All agents", the chosen agents' badges, "Off") that opens a panel whose choices are Off, All agents and Chosen agents — the last over the scope's list of agents, each switch and tick written at once. The list has a reach filter beside its search — every skill, or only the skills that reach one chosen agent — which reads and writes the same `agent` query parameter the agent's Skills tab links with; each row shows its reach, and the list groups by state.

#### Scenario: the web UI and REST cover every operation
- **GIVEN** the daemon is running,
- **WHEN** the user performs each operation via the web UI and via the REST routes,
- **THEN** the same effect is achieved in either surface,
- **AND** the skill's page shows the absolute path of the same master folder the Files tab shows, and the command line offers no `skill` command at all.

#### Scenario: switch and scope a skill through the resource update route
- **GIVEN** two registered agents and an enabled skill with no scope, delivered to both
- **WHEN** the user sets the skill's scope to the first agent, then turns the skill off, then turns it on again, through the resource update route (the reach button on the Skills page)
- **THEN** after the scope change only the first agent holds a delivered link, after turning it off neither does, and after turning it on the first agent holds it again
- **AND** each change is recorded in the audit log

#### Scenario: the skills page lists only managed skills
- **GIVEN** one managed skill and an agent whose skills directory holds two hand-placed skill folders
- **WHEN** the user opens the Skills page
- **THEN** it lists the managed skill only, and offers no Adopt action and no row for either hand-placed folder
- **AND** with no managed skill at all, the empty state links to the agents' Skills tabs and lists no skill

#### Scenario: a skill opens on its files with SKILL.md rendered
- **GIVEN** an imported skill whose folder holds `SKILL.md` and a script
- **WHEN** the user opens its detail page
- **THEN** the tabs read Files, Delivery, Requires and History, Files is selected with `SKILL.md` selected and rendered, and there is no SKILL.md tab
- **AND** switching to Source shows the raw text, and the file offers Open in editor and Reveal in Finder but no Edit

#### Scenario: the delivery tab shows each agent's copy
- **GIVEN** a skill scoped to one of two registered agents and delivered to it as a link
- **WHEN** the user opens the skill's Delivery tab
- **THEN** the first agent shows its copy as linked with its path, and the second as not delivered because it is outside the skill's reach

#### Scenario: the add dialog offers three sources and no create
- **GIVEN** the Skills page
- **WHEN** the user chooses Add skill
- **THEN** the dialog offers Folder, Archive and Git repository, and no option to create a new skill

#### Scenario: nothing is added until the user confirms
- **GIVEN** the Add skill dialog showing the skills found in an uploaded archive
- **WHEN** the user closes the dialog without confirming
- **THEN** no skill resource exists for them and nothing is under `~/.coffer/vault/skills/` for them
- **AND** the staging area the archive was read into is removed

#### Scenario: the history tab lists the folder's versions with their writers
- **GIVEN** a skill whose master folder has two versions, the newer written by the user and the older by Claude Code
- **WHEN** the user opens its History tab
- **THEN** the versions are listed newest first, each with its writer and what it changed
- **AND** the newest is marked current, shown with its diff, and offers no restore

#### Scenario: restoring a version asks first and restores the whole folder
- **GIVEN** a skill's History tab with an older version chosen
- **WHEN** the user compares it with the current folder, chooses Restore this version… and confirms
- **THEN** the dialog first says that files added since are removed, and nothing is restored before the confirmation
- **AND** once confirmed, the whole folder is restored from that version, stating the newest version the tab listed, and the dialog closes

#### Scenario: Coffer's own skill has no history
- **GIVEN** the builtin `coffer-guide` skill
- **WHEN** the user opens its History tab and its ⋯ menu
- **THEN** the tab says Coffer's own skill has no history and reads none, and the menu offers no History…
