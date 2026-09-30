# Skill Manager

## Purpose
Coffer manages portable AI skills in the open AgentSkills standard (agentskills.io): a `SKILL.md` with `name`/`description` frontmatter at minimum, validated against the standard's exact constraints, with the optional `license` and experimental `allowed-tools` fields recognized; non-conforming folders are out of scope. One canonical store lives at `~/.coffer/skills/`, and a skill reaches a coding agent as a directory symlink (junction on Windows, copy as a last resort) into the `skills/` subfolder of that agent's config directory. Claude Code and Codex CLI are the delivery targets, each registered as a resource of kind `agent` per spec agent-registry. Developers rely on it to migrate the skills they already have (import, or one-click adoption of skills an agent accumulated outside Coffer), to decide once — on the skill — which agents a skill reaches, and to trust that what is on disk matches what Coffer says, because drift self-heals at boot and the rest stays inspectable.

Delivery is one rule with no second switch: a skill's own `enabled` flag and its `scope` decide which agents receive it. A freshly imported skill has no scope and reaches every registered agent — "configure once, share everything", the filesystem counterpart of the MCP gateway's one-entry-serves-all model. The trade-off is stated plainly: there is no per-agent "this agent gets nothing" switch; to exclude one agent from everything, remove it from each skill's scope, exactly as `mcp_server` resources already work. Per-agent exclusion of a specific skill is unchanged in power; it moves from the agent side to the skill side.

A skill enters the library from a folder, a `.zip` / `.skill` archive or a folder of a Git repository, each staged and confirmed before anything is written. Folder- and archive-imported skills are point-in-time copies; the source is kept for traceability, not for sync. A Git-imported skill is pinned to the commit it came from and offered that repository's newer commits as a reviewed update. Because an agent's delivered path is a link to master, a user editing `SKILL.md` from inside an agent's `skills/` folder edits master, and every other agent sees it on its next read without any drift being reported; deleting a file there likewise affects master. If an agent's `config_dir` is moved or removed externally, the next sync operation surfaces the failure and `verify` reports the affected bindings. Codex also reads `~/.agents/skills` (its newer standard location) and treats `<config_dir>/skills` as backward-compatible; delivery stays at `<config_dir>/skills` for both agent types and the unmanaged scan covers both. `~/.agents/skills` is shared with other tools, so Coffer classifies only its own links as managed and never garbage-collects another tool's skills.

This spec owns the three `/api/v1/agents/{uid}/unmanaged-skills` routes (list, adopt, delete): their code (`surfaces/http/agent_unmanaged_skill_routes.py`), their contract (this spec's `contracts/api.openapi.yaml`) and their import-linter fence (the module sits on the `skill` kind's side of a zero-exception contract in `backend/pyproject.toml`) all say so, and the agent is an argument to these operations, not their subject. The web UI's open-in-external-editor and reveal-in-file-manager affordances in the file viewer are the daemon's filesystem-action endpoints ([ADR daemon-proxies-os-file-actions](../../../docs/decisions/daemon-proxies-os-file-actions.md)) opening the user's preferred external editor ([web-ui](../web-ui/spec.md) "Let the user choose an external editor"), and the Add-skill dialog uses the shared folder picker from spec agent-registry and also takes a typed or pasted path; this spec assumes both and feeds the chosen path to the import with only surrounding whitespace and quotes removed. A browse-and-install skill catalogue was prototyped and withdrawn for lack of a content ecosystem. The master-folder file viewer and editor ("Show a skill's master folder read-only", "Save an existing skill file conditionally") are served over REST to the web UI's Files tab; on the command line the folder is named by `coffer path skill <name>` and read and edited on disk.

## Requirements

### Requirement: Register each skill as a resource with a SKILL.md-safe name
The system MUST register each managed skill as a Resource of kind `skill`, identified by the framework's immutable `uid` ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)). Its `name` is taken from SKILL.md frontmatter at import or adoption, unique within the kind, and MUST satisfy the frontmatter's own charset (`^[a-z0-9][a-z0-9_-]{0,63}$`), so Coffer never registers a skill under a name its own importer would reject. The `name` MUST be **fixed** once the skill is registered, because it is the directory an agent loads the skill from and the identifier an agent invokes it by, so it is quoted in places Coffer cannot see ([resource-framework](../resource-framework/spec.md), the requirement that lets a kind declare its name fixed). An update whose `name` differs from the current one MUST be refused with `NAME_IMMUTABLE` (409) before anything moves, on REST and on the web UI alike. The refusal MUST say that a different name means removing the skill and importing it again, and that doing so resets its `enabled` flag, its scope and its deliveries. A skill carries no title ([resource-framework](../resource-framework/spec.md) "Carry an optional editable title on the kinds that have one"): every surface shows its fixed name, beside the SKILL.md `description` agents choose it by, and a title submitted for one is refused as a validation error with nothing changed.

#### Scenario: refuse a skill name its own SKILL.md could not carry
- **GIVEN** the daemon is running and no skill is registered under any of the names below
- **WHEN** the user imports, or adopts, a folder whose SKILL.md frontmatter `name` is `My.Skill`, `MySkill` or `-leading`
- **THEN** each is refused as a validation error before anything is written
- **AND** no `skill` resource exists afterwards and nothing is under `~/.coffer/skills/` for any of them

#### Scenario: refuse changing a registered skill's name
- **GIVEN** an imported skill `before` delivered to a registered agent
- **WHEN** the user submits the name `after` through the resource update route and through the web UI
- **THEN** each is refused with `NAME_IMMUTABLE` (409), and the message says that a new name means removing the skill and importing it again, which resets its enabled flag, scope and deliveries
- **AND** the row, the master folder `before`, its SKILL.md `name: before` and the delivered link are all exactly as they were, and `verify` reports no drift

#### Scenario: a skill's title is edited without touching disk
- **GIVEN** an imported skill `before` delivered to a registered agent
- **WHEN** the user submits the title `Release checklist` for it through the resource update route
- **THEN** the title is refused as a validation error, `coffer skill list` and the Skills page still show `before`, and `coffer skill show before --json` carries no `title`
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
The system MUST validate every imported skill folder against the AgentSkills specification: `SKILL.md` present; frontmatter `name` present and non-empty (lowercase alphanumerics, hyphen, or underscore, ≤64 chars) and `description` present, non-empty, and ≤1024 chars; no path-escape symlinks; total size at most 50 MB, a fixed cap. A folder that violates any of these MUST be rejected with `unprocessable_entity` (422) and nothing persisted. A folder over the size limit is rejected as `SKILL_INVALID` with `details.reason` `size_limit_exceeded`.

#### Scenario: reject import of an invalid skill folder
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder that is missing `SKILL.md` or has empty `name`/`description` frontmatter,
- **THEN** the request is rejected with a clear error, and nothing is written to `~/.coffer/skills/` or the database.

#### Scenario: reject import containing path-escape symlinks
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder containing a symlink that resolves outside the folder,
- **THEN** the request is rejected with the offending paths listed, and nothing is persisted.

#### Scenario: reject a skill with an over-long description
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder whose SKILL.md `description` exceeds 1024 characters,
- **THEN** the request is rejected as invalid frontmatter, and nothing is written to `~/.coffer/skills/` or the database.

### Requirement: Retain optional AgentSkills frontmatter fields
The system MUST recognize the optional agentskills.io frontmatter fields it understands — `license` and the experimental `allowed-tools` — parsing and retaining them rather than discarding them, while tolerating any other unrecognized frontmatter field so non-Coffer-authored skills validate cleanly. `allowed-tools` accepts either a list or a comma/whitespace-separated string and is normalized to a list of tool names; a malformed value is tolerated (treated as absent), never a validation failure. Likewise a non-string `license` scalar (e.g. an unquoted year or version) is coerced to a string rather than rejected.

#### Scenario: recognize optional agentskills.io frontmatter fields
- **GIVEN** a valid SKILL.md that also declares `license` and the experimental `allowed-tools`,
- **WHEN** the folder is validated,
- **THEN** validation succeeds and the parsed frontmatter retains `license` and a normalized `allowed-tools` list (rather than discarding them).

### Requirement: Import a skill from a local path
The system MUST support importing a skill from a local filesystem path; the original source path is recorded for provenance but is not retained as a live dependency. Re-importing a name that already exists MUST be rejected by default (`conflict`, 409); with an explicit `overwrite` flag (CLI `--force`) the existing skill is replaced in place — the master folder content is swapped atomically, its `version_hash` and `last_synced_from_source_at` are refreshed, and its per-agent bindings and delivered symlinks are preserved (the master folder name is unchanged). For a skill added from a folder or an archive, re-import overwrite is the only update mechanism (there is no live source to re-fetch); a skill added from a Git repository is updated from its source instead (see "Update a Git-imported skill from its source"). The replacement is audited as an update. On a name collision the user either renames via SKILL.md frontmatter and retries, or re-imports with `overwrite`. A folder added from the web UI is looked at before anything is copied, as an archive is ("Add skills from an archive"): the dialog shows the skill it found, or the skills one folder down when the folder itself holds no `SKILL.md`, and copies nothing until the user confirms. `coffer skill add <folder>` imports at once, since naming the folder on the command line is the confirmation.

#### Scenario: import a valid local skill folder
- **GIVEN** the daemon is running and no skill named `my-skill` exists,
- **WHEN** the user imports a folder containing a valid SKILL.md with frontmatter `name: my-skill`,
- **THEN** Coffer copies the folder to `~/.coffer/skills/my-skill/`, persists a Resource of kind `skill`, and records an audit entry.

#### Scenario: re-import a skill with overwrite replaces it
- **GIVEN** a skill named `my-skill` is already imported and enabled for an agent,
- **WHEN** the user imports a folder with frontmatter `name: my-skill` again with `overwrite` (`--force`),
- **THEN** the master folder content is replaced atomically, the skill's `version_hash` is refreshed, the existing per-agent binding and its delivered symlink are preserved, and a skill-update audit entry is recorded — whereas the same re-import without `overwrite` is rejected with `conflict` (409).

#### Scenario: a folder is looked at before it is added
- **GIVEN** a folder holding a valid skill `release-notes`
- **WHEN** the user stages it in the Add skill dialog
- **THEN** the dialog shows `release-notes` with its description and file count, and nothing is under `~/.coffer/skills/` for it and no skill resource exists until the user confirms

### Requirement: Track delivered copies as internal bookkeeping
The system MUST track each `(skill, agent)` binding as internal delivery bookkeeping in a `skill_agent_bindings` table: a row records that this agent currently holds a delivered copy, plus the last successful link path, the link mode, and when it was last linked. It is not a user-facing axis and MUST NOT be exposed as a toggle on any surface. Symlink existence on disk is the live representation; the row is the persistent record of what was delivered.

#### Scenario: deliver a skill to a registered agent
- **GIVEN** an agent `claude_code` is registered (per spec agent-registry) and an enabled skill `my-skill` is imported whose scope grants `claude_code`,
- **WHEN** the delivery reconcile for that skill runs,
- **THEN** a directory symlink (or junction on Windows) is created at `<config_dir>/skills/my-skill` pointing to `~/.coffer/skills/my-skill/`, and a `skill_agent_bindings` row records that the agent holds a delivered copy.

### Requirement: Deliver a skill as a directory link
Delivering a skill to an agent MUST create a directory symlink (POSIX) or directory junction (Windows) at `<config_dir>/skills/<skill-name>` pointing to `~/.coffer/skills/<skill-name>/`. Each agent's skill subpath comes from the capability manifest, so a future agent's delivery target is data, not a new branch; this is the only way Coffer delivers a managed skill.

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
When symlinks/directory junctions are unavailable (e.g., FAT32, network share), the system MAY fall back to copy mode for that target; the binding records `link_mode=copy_fallback` (audited as `mode: copy_fallback` on the enable event) and the UI MUST surface the degradation (the Skills page badges such a skill with a "Copied" warning chip).

#### Scenario: fall back to a copy where a directory link cannot be made
- **GIVEN** a registered agent on a filesystem where neither a directory symlink nor a junction can be created
- **WHEN** an enabled skill is delivered to it
- **THEN** a real copy of the master folder is placed at `<config_dir>/skills/<name>`, the binding records `link_mode=copy_fallback`, the delivery audit entry carries `mode: copy_fallback`, and `verify` treats the copy as healthy rather than as drift
- **AND** the Skills page badges that skill with the "Copied" warning chip, which a plain symlink delivery does not carry

### Requirement: Deliver a skill only where it is enabled and in scope
A skill MUST be delivered to an agent if and only if the skill resource is enabled AND the skill's scope admits that agent — `skill.enabled AND is_active(skill.scope, agent=<agent>)`, one allow-list, left `null` admitting anything ([ADR per-agent-resource-scope](../../../docs/decisions/per-agent-resource-scope.md)). This is the same shape `mcp_server` uses, where scope alone decides which agents see a server's tools. The scope states:

- `None` — every registered agent receives the skill (the default for a fresh import).
- `{"agents": ["<agent uid>"]}` — only those agents receive it. The scope holds agent uids ([ADR resource-identity-is-an-immutable-uid](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)); the CLI and web UI let the user pick agents by name and store their uids. A uid that matches no agent registered here is legal and simply never matches.
- `{"agents": []}` — nobody receives it, while the skill stays in the library, converged and visible.

Those two together are the skill's REACH, and reach is machine-local: it is set on the machine it applies to, a converge round neither carries it away nor writes over it (spec vault-sync, "Keep reach machine-local"), and the predicate therefore takes no machine argument and has no machine to take. What converges is the skill — its files, its metadata — unless it is Coffer's own generated one (see "Regenerate Coffer's builtin skill from the build"). A skill can still be delivered here and dormant on another machine — that is two machines each holding their own `enabled` flag and their own scope, not one scope naming machines. The surface that sets reach MUST say that the setting stops at this machine.

No other flag decides which agents a skill is FOR: neither the delivery bookkeeping of "Track delivered copies as internal bookkeeping" nor any field on the agent resource; the agent resource carries no skill-delivery policy at all. `enabled` is a real switch: disabling a skill reclaims every delivered copy (master untouched) and re-enabling redelivers it to every agent its scope still grants. Scope is a hard grant: narrowing it to exclude an agent reclaims that delivery on the next reconcile even if the copy got there some other way, and widening it delivers; no per-agent state can hold a copy against the scope or keep one away from an agent the scope grants. A DISABLED AGENT is a separate matter and is never written into by delivery — the predicate names the agents a skill belongs to, while an agent the user switched off ([agent-registry](../agent-registry/spec.md) "Switch an agent off with the kind-agnostic enabled flag") is one Coffer does not deliver into; its held copies are reclaimed and re-enabling it reconciles them back. The one exception is adoption ("Adopt an unmanaged skill"): the folder being adopted is already in that agent's skills directory, so it is replaced in place by the managed link even when the agent is disabled — and, like any copy a disabled agent holds, that link is reclaimed by the agent's next reconcile. A reconcile that finds a delivered copy the predicate no longer grants MUST reclaim it (remove the link, clear the delivery record) per "Reclaim a delivered copy without touching master", and MUST deliver a copy the predicate now grants but the agent does not hold. This predicate governs **delivery** — writing a skill into an agent's own filesystem — and is the only path by which a skill reaches an agent (see "Expose no skill tools over MCP").

#### Scenario: a skill with no scope reaches every registered agent
- **GIVEN** two registered agents and an enabled skill whose scope is unset (`None`),
- **WHEN** the delivery reconcile runs for each agent,
- **THEN** both agents hold a delivered copy, and registering a third agent delivers the skill there too with no further user action.

#### Scenario: a skill scoped to no agent reaches nobody
- **GIVEN** two registered agents each holding a delivered copy of an enabled skill,
- **WHEN** the user sets the skill's scope to `[]`,
- **THEN** both delivered copies are reclaimed, the skill remains in the library (still listed, still exported), and no agent receives it until its scope grants one again.

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
The system MUST provide a `verify` operation — a read-only facility on the CLI (`coffer skill verify`), on REST (`POST /skills/verify`) and on the Skills page (**Check copies**) — that compares each enabled binding to its on-disk target and reports drift categories (missing link, tampered link, foreign content at the link path, missing master, orphan master) with suggested remedies, and exits non-zero on the CLI when drift is found. Asking for the report MUST NOT itself repair anything. The drift report is ephemeral: each binding whose on-disk target disagrees with the binding state, categorized by drift type with a suggested remedy. The Skills page lists the report's findings with the skill, the agent, the path and the suggested remedy, and offers the repair of "Repair repairable drift from master" for the findings it covers; the other findings stay listed for the user to act on.

#### Scenario: detect drift in agent skill directories
- **GIVEN** a binding exists but its target on disk has been deleted, replaced, or relinked,
- **WHEN** the user runs `coffer skill verify` (CLI) or calls `POST /skills/verify` (REST),
- **THEN** the report lists each drift type with a suggested remedy and exits with a non-zero status; asking for the report never itself repairs anything — repair runs only along the separate paths in "opt-in repair re-delivers repairable drift from master" and the boot-heal scenarios below.

#### Scenario: check agents' copies from the skills page
- **GIVEN** one skill whose delivered link is missing and another whose link path holds a folder Coffer did not put there
- **WHEN** the user chooses Check copies on the Skills page
- **THEN** both findings are listed with the skill, the agent and the path, and nothing on disk has changed
- **AND** choosing Repair re-creates the missing link, while the foreign folder is left as it was and stays listed

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
The system MUST provide a drift repair that re-delivers repairable drift — missing link and tampered link — from the master library, and MUST NOT modify foreign/user content (replaced-with-regular), a missing master, or an orphan master; those are left intact and reported as requiring manual action. This repair runs (a) automatically per "Heal safely repairable drift on every pass", audited with actor `system`, and never allowed to fail startup; and (b) on demand via the CLI (`coffer skill verify --fix`, or `coffer drift repair`) and REST (`POST /skills/repair`, or `POST /api/v1/reconcile/apply`) for anyone who wants to trigger or inspect a repair directly, audited with the caller as actor. Each repair, automatic or on-demand, MUST be audited.

#### Scenario: opt-in repair re-delivers repairable drift from master
- **GIVEN** an agent skill directory where one enabled binding has a missing Coffer link, another has a tampered Coffer link (a stale link pointing elsewhere), a third binding's path is occupied by a foreign regular directory the user owns, and a fourth binding's master folder no longer exists,
- **WHEN** the user runs the opt-in repair (`coffer skill verify --fix` / `POST /skills/repair`),
- **THEN** the missing link is re-created pointing to master, the tampered link is backed up to `<path>.coffer-backup-<ts>` and then re-created pointing to master, the foreign regular directory is left completely untouched and still appears in the report as requiring manual action, the missing-master entry is left and reported as requiring manual action, and each re-delivery is recorded as a repair event in the audit log.

### Requirement: List unmanaged skills in an agent's skill locations
The system MUST scan a registered agent's skill locations — `<config_dir>/skills` for both types, plus `~/.agents/skills` for `codex` — and list **unmanaged** entries: everything that is not a Coffer-managed link (a link whose target resolves inside `~/.coffer/skills/`) and not Codex's `.system` entry. Each result carries name, path, location, and a `valid` flag (validation per "Validate imported skill folders against AgentSkills") with the failure reason when invalid. The scan is read-only and derived at request time; an unmanaged skill is never stored. An entry that is a symlink pointing outside the master store is listed as unmanaged but not adoptable; an entry without a valid SKILL.md is listed with `valid=false` and the reason, deletable but not adoptable until it validates. On the command line these entries are the rows of kind `skill` that `coffer scan` prints, across every registered agent or, with `--agent <name>`, for one; each row's reference is the entry's path.

#### Scenario: list unmanaged skills across an agent's skill locations
- **GIVEN** a registered `codex` agent with one Coffer-managed link in `<config_dir>/skills`, one hand-copied skill folder there, and another skill folder in `~/.agents/skills`,
- **WHEN** the user lists the agent's unmanaged skills,
- **THEN** Coffer returns exactly the two hand-placed skills — each with name, path, location, and a `valid` flag from SKILL.md validation — and excludes the managed link.

#### Scenario: exclude managed links and system entries from the unmanaged scan
- **GIVEN** an agent's skill directory containing Coffer-managed links and (for Codex) a `.system` entry,
- **WHEN** the user lists unmanaged skills,
- **THEN** neither the managed links nor the `.system` entry appear in the result.

#### Scenario: the command-line scan lists unmanaged skills as skill rows
- **GIVEN** a registered agent with one Coffer-managed link and one hand-placed skill folder in its skills directory
- **WHEN** the user runs `coffer scan --agent <name> --json`
- **THEN** the output holds exactly one row of kind `skill`, naming the hand-placed folder by its path with its `valid` flag
- **AND** the managed link is not among the rows

### Requirement: Adopt an unmanaged skill
Users MUST be able to adopt a valid unmanaged skill. Adoption validates the folder per "Validate imported skill folders against AgentSkills", moves it to `~/.coffer/skills/<name>/`, registers the `skill` resource, delivers the managed link (see "Deliver a skill as a directory link"), and records an enabled binding for that agent — in that order, with any failure before registration leaving the original folder unmoved and unchanged (after registration the master copy is authoritative; a delivery failure is surfaced and retried via the binding, never rolled back). The managed link is always delivered to the agent's canonical delivery location `<config_dir>/skills/<name>`: adopting from `<config_dir>/skills` replaces the original path in place, while adopting from `~/.agents/skills` consolidates — the original folder there is removed and the link lands in `<config_dir>/skills` (Codex reads both locations, so the agent keeps seeing the skill). Name collisions MUST be rejected with `conflict` (409); invalid folders and symlinks pointing outside the master store MUST be rejected with `unprocessable_entity` (422). Adoption is audited as an adoption event. Adopting from a disabled agent is allowed and links in place exactly as for an enabled one, recording the binding — the folder was already there, so the agent sees no new content; the exception this makes to "Deliver a skill only where it is enabled and in scope" ends at the agent's next reconcile, which reclaims the link as it does every copy a disabled agent holds, and re-enabling the agent delivers it back. On the command line adoption is `coffer adopt skill <path>`, where `<path>` is the reference `coffer scan` printed for the entry.

#### Scenario: adopt an unmanaged skill into the master store
- **GIVEN** an unmanaged skill folder with a valid SKILL.md whose name collides with no master skill,
- **WHEN** the user adopts it,
- **THEN** Coffer validates it per "Validate imported skill folders against AgentSkills", moves the folder to `~/.coffer/skills/<name>/`, registers the `skill` resource, replaces the original path with the managed link, records a binding for that agent, and audits the adoption — and on any failure the original folder is left exactly where and as it was.

#### Scenario: reject adopting an invalid or conflicting unmanaged skill
- **GIVEN** an unmanaged entry that lacks a valid SKILL.md, collides with an existing master skill's name, or is a symlink pointing outside the master store,
- **WHEN** the user attempts to adopt it,
- **THEN** the request is rejected with a reason-specific error (invalid: `unprocessable_entity` 422; name conflict: `conflict` 409; foreign link: `unprocessable_entity` 422), and nothing is moved, registered, or linked.

#### Scenario: adopting from a disabled agent links the skill in place
- **GIVEN** a disabled agent whose skills directory holds a valid unmanaged skill folder,
- **WHEN** the user adopts that folder,
- **THEN** the folder's content is in the master store, the original path is now the managed link to it, an enabled binding for that agent is recorded, and the adoption is audited under the skill's name.

### Requirement: Delete an unmanaged skill on explicit request
Users MUST be able to delete an unmanaged entry as an explicit, confirmed action. Deletion MUST remove only that entry from disk, never master content or bindings, and MUST be audited. Coffer never deletes an unmanaged entry on its own. On the command line deletion is `coffer discard skill <path>`, where `<path>` is the reference `coffer scan` printed for the entry.

#### Scenario: delete an unmanaged skill
- **GIVEN** an unmanaged skill folder in an agent's skill location,
- **WHEN** the user deletes it (an explicit, confirmed action),
- **THEN** the folder is removed from disk, an audit entry is recorded, and no master content or binding is touched.

### Requirement: Reconcile deliveries from state on every pass
The system MUST keep every agent's delivered set equal to the predicate of "Deliver a skill only where it is enabled and in scope" alone, as the skill-link target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"). An agent's wanted set is `{s.uid for s in skills if s.enabled and is_active(s.scope, agent.uid)}` for an enabled agent and empty for a disabled one — a free function over the agent alone, with no evaluator object to build and no machine to bind into one. The same skill row can still be wanted here and unwanted on another machine, because the `enabled` flag and the scope this predicate reads are this machine's own, and the round that brought the skill here brought neither. Each wanted delivery is a link at `<agent skill dir>/<skill name>` pointing at the skill's master folder, judged by both paths: a wanted skill the agent does not hold is delivered, a held copy no longer wanted is reclaimed, and a held link whose path no longer matches the agent's skill directory (its `config_dir` moved) is re-delivered at the new path and removed from the old one. Because the reconciler runs on every pass, this holds whatever changed the state — a skill enabled, disabled, rescoped, imported or removed, an agent registered, enabled, disabled or moved, a sync import, or nothing Coffer heard about — and a user's own write runs the pass for skills at once, so the change is visible when the write answers. A disabled agent's copies are reclaimed and restored when it is enabled again. Conflicts at target paths follow "Report a foreign target instead of overwriting it" (report, never overwrite). The agent resource carries no skill-delivery policy of any kind — no follow flag, no exclusion list, no per-agent opt-out; the only inputs are the skill's `enabled` flag and its `scope`.

#### Scenario: import delivers a skill only where its scope grants it
- **GIVEN** two registered agents, `claude_code` and `codex`,
- **WHEN** the user imports a skill whose scope names only the `claude_code` agent's uid,
- **THEN** the pass that follows delivers it to `claude_code` only, and `codex` receives nothing.

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
The system MUST expose over REST a **read-only** view of a skill's master folder, which the web UI's Files tab renders: a recursive file tree (name, folder-relative path, absolute on-disk path, type, size, children) and the contents of an individual file (with its absolute on-disk path and containing folder's absolute path). Markdown files render as formatted Markdown; other text files show raw. Every file read MUST also return a content fingerprint (see "Save an existing skill file conditionally") so an in-app edit of that file can be saved conditionally. Reads MUST be contained to the master folder — any path that resolves outside it (`..` traversal, absolute path, or escaping symlink) MUST be rejected. File reads MUST be size-capped (truncating with a `truncated` flag) and MUST flag non-UTF-8 / NUL-containing files as binary with empty content. No symlink-following out of the folder. On the command line the same folder is named by `coffer path skill <name>` and read on disk (see "Cover skill management on REST, the CLI and the web").

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

### Requirement: Save an existing skill file conditionally
The system MUST provide a write that overwrites an **existing text file** in the master folder, under the same containment guard and size cap as "Show a skill's master folder read-only"; it MUST refuse to create new files/directories here, to write outside the folder, or to overwrite a binary file with text. The write MUST be atomic with no symlink-following out of the folder. The in-app editor and programmatic REST clients share this one endpoint. Because the master folder is also a folder the user edits in their own editor, file reads MUST return a **content fingerprint** (a digest of the file's raw on-disk bytes — not of the possibly-truncated text returned, so an oversized file's fingerprint still round-trips and an edit past the truncation point is still detected), and a write MAY carry that fingerprint back: when it no longer matches the bytes on disk the write MUST be rejected with `conflict` (409) and the file left byte-identical, so the user re-reads and reapplies rather than silently losing the other edit. A write that omits the fingerprint stays unconditional (last writer wins), which is what a programmatic client that never read the file first needs.

#### Scenario: edit and save a skill file
- **GIVEN** an imported skill that contains an existing text file,
- **WHEN** the user edits that file in the in-app editor (or a programmatic REST client saves new contents for it) by its folder-relative path, passing back the fingerprint the read returned,
- **THEN** Coffer overwrites the file atomically and returns the file's new fingerprint, and a subsequent read returns the new contents; writing a non-existent path, a path outside the master folder, an existing binary file, or content over the size cap is rejected (`404`/`400`) and the file is left unchanged. A save that omits the fingerprint still writes, so programmatic clients that never read the file first keep working.

#### Scenario: reject a stale save of a skill file
- **GIVEN** an imported skill file opened in the in-app editor, whose read returned a content fingerprint,
- **WHEN** the user changes that same file in their own external editor and only then saves the in-app buffer with the now-stale fingerprint,
- **THEN** Coffer rejects the save with `conflict` (409, `SKILL_FILE_STALE`) and leaves the externally edited file byte-identical on disk; re-reading yields the current fingerprint and the retried save succeeds.

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
The system MUST support a **builtin** skill — one whose `source` is `builtin` and whose master folder Coffer writes itself rather than a person importing it. Its content MUST be rewritten from the running build whenever the material it describes moves: at every daemon boot, and on each change to what it carries (for `coffer-guide`, a curation pass or a collection being created, deleted, enabled or disabled — [knowledge](../knowledge/spec.md) "Deliver the catalogue through the coffer-guide skill"). A write MUST be skipped when the master already holds exactly that text, so an unchanged boot registers, audits and re-delivers nothing. Everything downstream of the master folder is the ordinary machinery: the same validation ("Validate imported skill folders against AgentSkills"), the same resource row, the same delivery predicate ("Deliver a skill only where it is enabled and in scope") and the same links ("Deliver a skill as a directory link"), the same drift verification and repair ("Report skill drift on request", "Repair repairable drift from master"). It follows that **an edit to a builtin skill does not survive** — the next rewrite replaces it — and the surfaces MUST say so rather than letting a person discover it; a correction belongs in the build, not in the folder.

A builtin skill MUST NOT converge — neither its master folder nor its resource row ([vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves"): it is derived output, regenerated on each machine from material that already converges plus that machine's own reach, so publishing it is churn. The `skill` kind therefore declares the row derived while every other skill row keeps travelling, and the mirrored `skills/` tree leaves that one folder alone in both directions. The `builtin` source variant MUST still carry no fields — a path, a timestamp or a build id would each be a fact about one machine stored in a shape nothing reads. Seeding MUST NOT be able to fail a startup: a render or a write that fails leaves the previous master exactly where it was and every other skill still delivers.

#### Scenario: Coffer's own skill is rewritten from the build at every start
- **GIVEN** a registered builtin skill whose master `SKILL.md` a person has edited by hand,
- **WHEN** the daemon starts and the builtin seed runs,
- **THEN** the master folder holds the text the running build renders, the hand edit is gone, the resource row's `version_hash` and description match the new text, and every agent the delivery predicate grants reads the new text through its existing link,
- **AND** a second start over an unchanged catalogue writes nothing, registers nothing and records no audit entry, while a render or a write that fails leaves the previous master intact and does not fail startup.

### Requirement: Refuse deleting a builtin skill
Deleting a builtin skill MUST be **refused** — `RESOURCE_PROTECTED`, 409 — through the framework's pre-write delete guard ([resource-framework](../resource-framework/spec.md) "Let a kind refuse a deletion before anything is torn down"), so the refusal is identical on `DELETE /api/v1/skills/{uid}`, on `DELETE /api/v1/resources/{uid}` and on the CLI, and nothing is torn down on the way. The reason is honesty rather than protection: the next boot writes the master folder back, so a delete would read as destructive and behave as a no-op that had removed some links in passing. `enabled` and `scope` MUST stay fully available on a builtin skill, and the refusal MUST name them — those two decide **reach**, which is the owner's call, while **existence** is not.

#### Scenario: deleting Coffer's own skill is refused on every surface
- **GIVEN** a registered builtin skill, delivered to an agent,
- **WHEN** a delete is attempted through the skill route, through the kind-agnostic resource route, and through the CLI,
- **THEN** each is refused with `RESOURCE_PROTECTED` (409) and a message naming the skill and pointing at disable and scope instead,
- **AND** nothing was torn down on the way — the master folder, the resource row, the bindings and the agent's link are all exactly as they were — while disabling the same skill and narrowing its scope both succeed and reclaim its links normally.

### Requirement: Mark the builtin skill on every surface
Every surface that lists or shows a skill MUST mark a builtin one as built-in and MUST NOT offer its deletion: the read model carries an explicit `builtin` flag rather than leaving each client to infer it from the source variant, the web UI marks the row and withholds it from both the per-row delete and any bulk selection, and the CLI reports the same refusal the API does if a delete is attempted anyway. Enable, disable and scope controls MUST remain offered unchanged — a surface that hid them would be hiding the only decisions the owner still has over this skill.

#### Scenario: the skills surface marks the built-in skill and offers no delete
- **GIVEN** the Skills page listing one imported skill and one builtin skill,
- **WHEN** the list is read,
- **THEN** the builtin row is marked as built-in with the reason available on the mark, and it offers neither the per-row delete nor a selection checkbox for the bulk delete, while the imported row offers both,
- **AND** the builtin row still offers enable/disable and scope, and the read model carries an explicit `builtin` flag rather than requiring the client to infer it from the source variant.

### Requirement: Keep one master folder per skill
The system MUST store each managed skill's content under `~/.coffer/skills/<name>/`, with that path as the single editable source of truth. Because the skill's `name` is fixed after registration (see "Register each skill as a resource with a SKILL.md-safe name"), the master folder, every delivered link at `<config_dir>/skills/<name>` and the SKILL.md frontmatter `name` MUST keep that name for the life of the skill. No operation on any surface moves the master folder or rewrites that frontmatter field. Per-agent bindings hold the resource's identity, not its name.

#### Scenario: a refused name change leaves the master folder where it is
- **GIVEN** an imported skill `before` delivered to a registered agent, whose SKILL.md carries comments, other frontmatter fields and a body
- **WHEN** the user tries to change its name to `after`, and then to give it a title
- **THEN** both are refused, and the master folder and the agent's delivered link are still at `before`, the link resolving to that master, with the same binding row recording the delivery
- **AND** SKILL.md and the skill's `version_hash` are unchanged by either request, and nothing exists at `~/.coffer/skills/after/`

### Requirement: Expose unmanaged-skill operations on REST, CLI and web
Unmanaged-skill operations MUST be available through the REST API, through the top-level `coffer scan`, `coffer adopt skill <path>` and `coffer discard skill <path>` commands (with `--json` on `scan`), and through the agent's Skills tab in the web UI. The command line groups them with every other thing an agent holds that Coffer does not manage, so neither `coffer skill` nor `coffer agent` carries an unmanaged-skill command. Delivery itself is not an operation on this surface: it is controlled by the skill resource's `enabled` flag and `scope` through `coffer skill enable|disable|scope` and the matching resource routes. The agent detail page decides nothing about delivery: its Skills tab points at the Skills page and otherwise carries only the unmanaged skills found on that agent's disk.

#### Scenario: manage unmanaged skills with scan, adopt and discard
- **GIVEN** a registered agent with two hand-placed skill folders in its skills directory
- **WHEN** the user runs `coffer scan --agent <agent> --json`, then `coffer adopt skill <one path>`, then `coffer discard skill <other path>` and confirms it
- **THEN** the scan is JSON naming both folders as rows of kind `skill`, the first becomes a managed skill and leaves the next scan, and the second is removed from disk
- **AND** neither `coffer skill` nor `coffer agent` offers an `unmanaged`, `adopt` or `rm-unmanaged` command

### Requirement: Cover skill management on REST, the CLI and the web
Every management operation MUST be available through (a) the REST API, (b) the `coffer skill` CLI group with `--json` on every read, and (c) the Skills page in the web UI. The `coffer skill` group MUST offer `list`, `show`, `add <folder|archive|git-url>` (the imports of "Import a skill from a local path", "Add skills from an archive" and "Add skills from a Git repository", with `--ref` and `--path` for a repository, `--skill <name>` (repeatable) or `--all` to pick among several skills, `--yes` to skip the confirmation and `--force` to replace a skill of the same name), `update <name>` ("Update a Git-imported skill from its source", with `--check`, `--yes`, `--take-theirs` and `--keep-mine`), `rm`, `enable`, `disable`, `scope <name> [--agents a,b | --all | --none]` and `verify [--fix]`. `enable` and `disable` switch the skill resource's own `enabled` flag, which with its scope drives delivery ("Deliver a skill only where it is enabled and in scope"); there is no per-(skill, agent) switch on any surface, and the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes do not exist. The group offers no `edit`: a skill's name is fixed, it has no title, and its description is its SKILL.md's, edited in the file.

A skill's master folder is plain files a person edits in their own editor. On the command line it is named by `coffer path skill <name>`, which prints the folder's absolute path, and it is read and edited on disk; the `coffer skill` group carries no command that lists, prints or writes a file inside it. The REST file tree, file read and conditional file write ("Show a skill's master folder read-only", "Save an existing skill file conditionally") serve the web UI's Files tab and programmatic clients.

The Skills page is the library of managed skills beside the open skill: a list with search, an All / On / Off filter and row multi-select for bulk reach and bulk delete, next to the selected skill's detail. It has one **Add skill** action whose dialog offers three sources: **Folder** — a path field that takes a folder chosen with the folder picker or a path typed or pasted into it, trimmed of surrounding whitespace and quotes before it is sent; **Archive** — a `.zip` or `.skill` file uploaded from the browser; and **Git repository** — a URL with an optional ref and subpath. Each source first shows what it found — the skill or skills, their names and descriptions, any that cannot be added and why, and any whose name is taken, with Replace offered for those — and writes nothing until the user confirms. The dialog offers no way to create a new skill from scratch: a skill is authored in the user's own editor and added from where it lives. It shows each skill by its name, which it offers no way to edit. It lists only the skills Coffer manages: an agent's own (unmanaged) skills, and adopting them, live only on that agent's Skills tab (see "Expose unmanaged-skill operations on REST, CLI and web"), and while no skill is managed the page's empty state may link to the agents' Skills tabs but lists nothing from them. It manages the skill resource itself, not per-agent bindings. A row carries a Built-in mark, an Off mark, a Copied mark ("Fall back to copying where links are unavailable") and the update states of "Update a Git-imported skill from its source". A skill's detail (`/skills/<name>`, addressed by its fixed name as [web-ui](../web-ui/spec.md) "Lay out every detail page's tabs alike" says) shows its name, reach, description, master path and source, and has four tabs, in this order, each at its own path:

- **Files** (the default, `/skills/<name>`) — the file tree beside the viewer of "Show a skill's master folder read-only", opening with `SKILL.md` selected and rendered; a **Preview / Source** toggle switches a Markdown file between rendered and raw text, and **Edit** edits the file in place and saves it through "Save an existing skill file conditionally" (not offered on a builtin skill, which Coffer rewrites at every start). Every file and folder offers "open in external editor" and "reveal in file manager". There is no separate SKILL.md tab.
- **Delivery** (`/skills/<name>/delivery`) — every registered agent with the state of its copy: linked, copied, differing from master (the drift kinds of "Report skill drift on request", after Check again), or not delivered and why (the skill is off, the agent is outside its reach, or the agent is switched off), and the reach control.
- **Requires** (`/skills/<name>/requires`) — the commands the skill declares it needs ("Show the commands a skill declares it needs"), each opening that command's page on the CLIs page ([web-ui](../web-ui/spec.md) "Show every CLI a skill requires on the CLIs page").
- **History** (`/skills/<name>/history`) — the folder's past versions, from the vault's history once it records a skill's versions; until then the tab says that a skill's versions are not recorded yet.

A skill added from a Git repository also shows its source — the repository, the folder, the pinned commit and the update status — with **Check for updates**.

The old `/skills/<uid>` address MUST redirect to `/skills/<name>`, `?tab=overview` to Delivery and `?tab=files` to Files. The list's reach mark and the detail carry one reach button labelled with the answer ("Every agent", "2 agents", "Disabled") that opens a panel whose choices are Disabled, Every agent and Only selected agents — the last over the scope's list of agents, staged there and written once when the panel closes — and the list's filter offers those same states.

#### Scenario: desktop and CLI cover every operation
- **GIVEN** the daemon is running,
- **WHEN** the user performs each operation via the web UI and via `coffer skill ...`,
- **THEN** the same effect is achieved in either surface and CLI provides `--json` for read operations,
- **AND** `coffer path skill <name>` prints the absolute path of the same master folder the Files tab shows, and `coffer skill` offers no `import`, `files`, `cat`, `write` or `edit` command.

#### Scenario: switch and scope a skill from its own command group
- **GIVEN** two registered agents and an enabled skill with no scope, delivered to both
- **WHEN** the user runs `coffer skill scope <name> --agents <first agent>`, then `coffer skill disable <name>`, then `coffer skill enable <name>`
- **THEN** after the scope change only the first agent holds a delivered link, after `disable` neither does, and after `enable` the first agent holds it again
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
- **AND** switching to Source shows the raw text, and Edit then saving writes the file through the conditional save

#### Scenario: the old overview address opens delivery
- **GIVEN** a skill named `release-notes` and a bookmark to `/skills/<its uid>?tab=overview`
- **WHEN** it is opened
- **THEN** the app lands on `/skills/release-notes/delivery` with the Delivery tab selected

#### Scenario: the delivery tab shows each agent's copy
- **GIVEN** a skill scoped to one of two registered agents and delivered to it as a link
- **WHEN** the user opens the skill's Delivery tab
- **THEN** the first agent shows its copy as linked with its path, and the second as not delivered because it is outside the skill's reach

#### Scenario: the history tab says versions are not recorded yet
- **GIVEN** an imported skill
- **WHEN** the user opens its History tab
- **THEN** the tab says that the skill's versions are not recorded yet, and offers no restore

#### Scenario: the add dialog offers three sources and no create
- **GIVEN** the Skills page
- **WHEN** the user chooses Add skill
- **THEN** the dialog offers Folder, Archive and Git repository, and no option to create a new skill

#### Scenario: nothing is added until the user confirms
- **GIVEN** the Add skill dialog showing the skills found in an uploaded archive
- **WHEN** the user closes the dialog without confirming
- **THEN** no skill resource exists for them and nothing is under `~/.coffer/skills/` for them
- **AND** the staging area the archive was read into is removed

### Requirement: Preview an unmanaged skill read-only
Users MUST be able to open one unmanaged skill (see "List unmanaged skills in an agent's skill locations") and read it without adopting it: its metadata — name, path, location, `valid` with the failure reason, whether it is a foreign link, and the SKILL.md `description` when the folder validates — a recursive file tree of the folder, and the contents of each file. The entry is found by the same scan the list runs, addressed by the agent, the scan location and the folder name, so a name the scan does not list — a missing folder, a dot-entry, a Coffer-managed link — is not found. The tree and file reads MUST follow the containment, size cap and binary detection of "Show a skill's master folder read-only", rooted at the unmanaged folder: a path that resolves outside it (`..` traversal, an absolute path, an escaping symlink) is rejected with `400` before anything is read. Nothing here writes. An invalid folder MUST still open, with its reason. The preview is on REST (`GET /agents/{uid}/unmanaged-skills/{skill}`, `.../files`, `.../files/content`, each taking `location`), on the web as the unmanaged skill's detail page, and on the CLI as a plain folder: `coffer scan --agent <agent> --json` reports each unmanaged skill's name, absolute path, location, `valid` and reason, and its files are read on disk at that path (see [resource-framework](../resource-framework/spec.md) "Locate file-backed state with coffer path").

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

#### Scenario: read an unmanaged skill's files from the command line
- **GIVEN** an agent with a hand-placed skill folder holding a nested file
- **WHEN** the user runs `coffer scan --agent <agent> --json` and reads the nested file at the path its skill row reports
- **THEN** the row carries the folder's name, `valid` true and its absolute path, and the file on disk holds the nested file's contents
- **AND** the folder is still listed as unmanaged afterwards

### Requirement: Act on an unmanaged skill from its detail page
The agent's Skills tab MUST open an unmanaged skill's detail page when its row is clicked; the rows carry Adopt and Delete and no Open folder. The detail page MUST show the skill's name with an Unmanaged badge and its location, a back link to the agent's Skills tab, and the actions Open folder (the folder in the OS file manager), Adopt ("Adopt an unmanaged skill"; disabled with its reason for an invalid folder or a foreign link) and Delete ("Delete an unmanaged skill on explicit request", confirmed first). A successful adoption MUST go on to the new managed skill's detail page, since the folder is no longer unmanaged; a successful delete MUST return to the agent's Skills tab.

#### Scenario: open an unmanaged skill's detail page from the agent's Skills tab
- **GIVEN** an agent's Skills tab listing unmanaged skills
- **WHEN** the user clicks one row
- **THEN** that skill's detail page opens, and its Files tab shows the folder's tree and a read-only preview of the chosen file
- **AND** no row in the table carries an Open folder button

#### Scenario: adopt or delete an unmanaged skill from its detail page
- **GIVEN** an unmanaged skill's detail page
- **WHEN** the user adopts it
- **THEN** the page moves to the new managed skill's detail page
- **AND** when the user instead deletes it and confirms, the folder is deleted and the page returns to the agent's Skills tab

### Requirement: Add skills from an archive
Users MUST be able to add skills from a `.zip` or `.skill` archive — uploaded from the web UI, or named on the command line (`coffer skill add <file.zip>`), both through the same REST upload. The archive is read into a staging area outside the master store, and before anything is extracted the system MUST reject the whole archive, naming the offending entries, when an entry has an absolute path or a `..` segment (zip-slip), is a symlink, or would take the archive past the 50 MB skill cap once uncompressed — judged on each entry's uncompressed size as it is read, not only on what the archive declares; an upload itself larger than the cap is refused before it is read. A skill is a folder whose `SKILL.md` is at the top of the archive or one folder down; an archive holding several such folders offers each, and the user chooses which to add (on the command line, `--skill <name>`, repeatable, or `--all`). An archive with no `SKILL.md` in either place MUST be rejected with a message saying where one was looked for. Each chosen skill is then validated as a folder is ("Validate imported skill folders against AgentSkills"), and a name already taken follows "Import a skill from a local path": refused unless the user chooses Replace (`--force`), or renames it in its `SKILL.md` and adds it again. Nothing is copied into `~/.coffer/skills/` or registered until the user confirms (on the command line, answers the prompt or passes `--yes`); the staging area is removed either way, and one never confirmed is removed after an hour. The skill's source records the archive's file name and the folder inside it.

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
- **THEN** each is rejected naming the offending entry, and nothing is written outside the staging area, to `~/.coffer/skills/` or to the database

#### Scenario: a taken name offers replace
- **GIVEN** a skill named `review` already added and delivered to an agent
- **WHEN** the user uploads an archive whose skill is also named `review`
- **THEN** the dialog marks it as taken and offers Replace; adding without Replace is refused with `conflict` (409), and choosing Replace swaps the content in place keeping its bindings

#### Scenario: an archive from the command line asks before adding
- **GIVEN** `skills.zip` holding two skills
- **WHEN** the user runs `coffer skill add skills.zip --skill review`
- **THEN** the command prints what it will add and asks for confirmation, and adds `review` only when the user answers yes

### Requirement: Add skills from a Git repository
Users MUST be able to add skills from a Git repository given its URL, an optional ref (branch, tag or commit; the default branch when omitted) and an optional subpath — in the Add skill dialog, or with `coffer skill add <git-url> [--ref <ref>] [--path <subpath>]`. A GitHub folder address (`https://github.com/<owner>/<repo>/tree/<ref>/<path>`) is read as the repository, the ref and the subpath. The system MUST fetch the repository with this machine's own `git` into a staging area, resolve the ref to one commit, and find skills under the subpath by the rule archives use (a `SKILL.md` at the subpath's top or one folder down), offering a choice when there are several. Git runs with no prompt and no secret Coffer supplies: a repository is reachable when it is public or when this machine's git already holds a credential for it (its credential helper or SSH keys), and Coffer stores none. Only the `https`, `http`, `ssh`, `git` and `file` transports are allowed, and submodules are not fetched. Symlinks that leave the skill folder, and a checkout of the subpath past the 50 MB skill cap, MUST be rejected before anything is written. A chosen skill is validated, named and confirmed as an archive's is, and is recorded with a `git_import` source pinned to the commit it was copied from and the content hash of its folder there. It stays pinned to that commit until the user takes a newer one through "Update a Git-imported skill from its source". A repository that cannot be fetched, a ref that names no commit and a subpath the commit does not hold MUST each be reported with git's own message, and nothing is written.

#### Scenario: add a skill from a repository subpath at a ref
- **GIVEN** a repository whose `skills/review/SKILL.md` is valid on tag `v1.2`
- **WHEN** the user adds it with ref `v1.2` and subpath `skills/review` and confirms
- **THEN** the skill is added from that commit, and its source records the URL, `v1.2`, `skills/review` and the commit id
- **AND** a later commit on the repository changes nothing until the user applies it as an update

#### Scenario: an unreachable repository writes nothing
- **GIVEN** a URL that git cannot fetch
- **WHEN** the user tries to add from it
- **THEN** the dialog shows git's message and nothing is written

### Requirement: Update a Git-imported skill from its source
A skill with a `git_import` source MUST be checked for newer commits on its ref — on demand, from a **Check for updates** action on the skill's page (`coffer skill update <name> --check`), and periodically, every six hours — by fetching the repository with this machine's `git` into a staging area; a check writes nothing to the master store and its result is kept on this machine only. When the ref has moved past the pinned commit with commits that change the skill's folder, the skill MUST show **Update available** on the Skills page and its detail page, with the commit range from the pinned commit to the new one. Choosing it MUST show a preview of the change to the skill's folder — the files added, removed and changed, with a diff, and the commits in the range — and apply nothing until the user confirms; confirming replaces the folder's content atomically with the new commit's, moves the pin to it, keeps the skill's reach and delivered links, and is audited as an update. An update whose `SKILL.md` names a different skill, or which fails the checks of "Validate imported skill folders against AgentSkills", is refused and changes nothing. When the skill's folder has been edited locally since the pinned commit (its content no longer matches the content hash recorded for that commit), the update MUST show a **conflict** instead of a plain preview, offering **Keep mine** (leave the folder and the pin as they are and stop offering this update until a newer commit arrives), **Take theirs** (apply the new commit, discarding the local edits) and **Compare** (the local folder, the pinned commit and the new commit side by side). A source that cannot be fetched MUST be reported on the skill with git's message and the time of the last successful check, and changes nothing. On the command line `coffer skill update <name>` previews and asks before applying, refuses a conflict unless `--take-theirs` or `--keep-mine` says which side to keep, and `--yes` skips the question.

#### Scenario: a newer commit shows update available
- **GIVEN** a skill pinned to commit `a1` of `main`, and `main` now at `c3` with commits that change the skill's folder
- **WHEN** the periodic check runs, or the user chooses Check for updates
- **THEN** the skill shows Update available with the range `a1..c3` on the Skills page and its detail page
- **AND** nothing under `~/.coffer/skills/` has changed

#### Scenario: an update is applied after its preview
- **GIVEN** a skill showing Update available and not edited locally
- **WHEN** the user opens the update, reviews the preview of added, removed and changed files, and confirms
- **THEN** the folder holds `c3`'s content, the source is pinned to `c3`, the skill's reach and delivered links are unchanged, and the update is audited
- **AND** closing the preview without confirming leaves the folder and the pin at `a1`

#### Scenario: a local edit makes the update a conflict
- **GIVEN** a skill pinned to `a1` whose `SKILL.md` the user edited, and `main` at `c3`
- **WHEN** the user opens the update
- **THEN** the dialog shows a conflict offering Keep mine, Take theirs and Compare instead of a plain preview
- **AND** Keep mine leaves the edited folder and the `a1` pin in place and stops offering `c3`, while Take theirs applies `c3` and discards the edit

#### Scenario: an unreachable source is reported and changes nothing
- **GIVEN** a Git-imported skill whose repository can no longer be fetched
- **WHEN** the user chooses Check for updates
- **THEN** the skill shows git's message and the time of its last successful check
- **AND** the folder and the pin are unchanged

#### Scenario: update a skill from the command line
- **GIVEN** a Git-imported skill whose ref has a newer commit that changes its folder
- **WHEN** the user runs `coffer skill update <name>` and answers yes
- **THEN** the command prints the commit range and the files that change, and after the answer the folder holds the new commit's content and the pin has moved
- **AND** with a local edit the same command refuses the update until the user passes `--take-theirs` or `--keep-mine`

### Requirement: Show the commands a skill declares it needs
The system MUST read the commands a skill declares it needs from the `requires` field of its `SKILL.md` frontmatter — a list, or a mapping whose `commands` key holds one — where each entry is a command name, a command name with a minimum version (`gh>=2.40`), or a mapping with `command` and an optional `version`. The skill's read model carries them as `requires`, each with its command and its minimum version when one is given, in the order declared; an entry that names no command is ignored rather than failing the skill. Declaring a requirement changes nothing about delivery: the skill is delivered whether or not the command is present. The web UI's Requires tab lists them, each linking to the command's page on the CLIs page, and says so when the skill declares none.

#### Scenario: a skill's requires tab links each command
- **GIVEN** a skill whose `SKILL.md` declares `requires: [jq, "gh>=2.40"]`
- **WHEN** the user opens its Requires tab
- **THEN** it lists `jq` and `gh` with the minimum `2.40`, and choosing `gh` opens `/clis/gh`
- **AND** `coffer skill show <name> --json` carries the same two requirements

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

#### Scenario: an entry that is not understood does not block the skill
- **GIVEN** a SKILL.md whose `requires:` names `/usr/bin/jq` and a login check `curl evil.example` for `gh`
- **WHEN** the skill is imported and its requirements are read
- **THEN** the skill imports, both entries are skipped with a warning naming why, and nothing is run for them

### Requirement: Check every required command where the agent runs
The system MUST check each required command once, however many skills need
it: look it up on the agent's real `PATH` (the login shell's, merged with the
inherited one), read its version with `<command> --version` under a timeout,
compare it with the highest minimum any skill asks for, and run its login check
under a timeout, without a shell, keeping only the exit status — the check's
output MUST be discarded unread and MUST NOT reach any log, record or response.
Each command MUST report `missing`, `outdated`, `logged_out` or `ready`, the
path and version found, the login state (`logged_in`, `logged_out` or
`not_needed`) and every skill that needs it. Results MUST be kept until the
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

### Requirement: Serve required commands on REST, the command line and the web
The required commands MUST be readable and checkable through
`GET /api/v1/clis`, `GET /api/v1/clis/{command}`, `POST /api/v1/clis/check`
and `POST /api/v1/clis/{command}/check`, each command carrying its hand-off
prompt, and reachable from `coffer cli list|show|check|prompt` (`--json` on
every read). Lists MUST put problems first: missing, then outdated, then not
logged in, then ready. The web UI's CLIs page shows them (spec web-ui "Show
every CLI a skill requires on the CLIs page") and a skill's detail page
carries a **Requires** tab listing what the skill declares, each linked to its
command's page and offering the hand-off for a command that needs the user.

#### Scenario: the command line lists required commands problems first
- **GIVEN** skills requiring a missing `jq`, an outdated `gh` and a ready `uv`
- **WHEN** the user runs `coffer cli list --json`
- **THEN** the commands come back in the order `jq`, `gh`, `uv`, each with its status and the skills that need it

#### Scenario: the command line prints the same prompt
- **GIVEN** a missing required command `jq` and a ready `uv`
- **WHEN** the user runs `coffer cli prompt jq`
- **THEN** it prints exactly the `handoff.prompt` that `GET /api/v1/clis/jq` returns
- **AND** `coffer cli prompt uv` exits non-zero saying there is nothing to hand off

### Requirement: Hand a required command to an agent with a prompt
The system MUST NOT install, update or log in to a required command itself.
For a command that is `missing` or `outdated` it MUST offer a prompt, built by
the daemon, for the user to give their agent, which names the command (and its
title), every skill that needs it with the minimum version each asks for, what
was found for an outdated one, and this machine's operating system and CPU
architecture; asks the agent to choose the install method that suits this
machine, to check with the user before running anything that needs `sudo` or
changes system settings, and to confirm with `<command> --version` when it is
done; and says that any login is left to the user, whose credentials the agent
does not handle. For a command that is `logged_out` the prompt MUST ask only
for help logging in: it names the login check that failed and the declared
login command, asks the agent to tell the user what to run, and leaves running
it and entering credentials to the user. A `ready` command MUST carry no
prompt. The prompt MUST be served as `handoff.prompt` on every response that
carries the command, and the same text by `coffer cli prompt <command>`.

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
