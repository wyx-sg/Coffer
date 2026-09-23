# Skill Manager

## Purpose
Coffer manages portable AI skills in the open AgentSkills standard (agentskills.io): a `SKILL.md` with `name`/`description` frontmatter at minimum, validated against the standard's exact constraints, with the optional `license` and experimental `allowed-tools` fields recognized; non-conforming folders are out of scope. One canonical store lives at `~/.coffer/skills/`, and a skill reaches a coding agent as a directory symlink (junction on Windows, copy as a last resort) into the `skills/` subfolder of that agent's config directory. Claude Code and Codex CLI are the delivery targets, each registered as a resource of kind `agent` per spec agent-registry. Developers rely on it to migrate the skills they already have (import, or one-click adoption of skills an agent accumulated outside Coffer), to decide once — on the skill — which agents a skill reaches, and to trust that what is on disk matches what Coffer says, because drift self-heals at boot and the rest stays inspectable.

Delivery is one rule with no second switch: a skill's own `enabled` flag and its `scope` decide which agents receive it. A freshly imported skill has no scope and reaches every registered agent — "configure once, share everything", the filesystem counterpart of the MCP gateway's one-entry-serves-all model. The trade-off is stated plainly: there is no per-agent "this agent gets nothing" switch; to exclude one agent from everything, remove it from each skill's scope, exactly as `mcp_server` resources already work. Per-agent exclusion of a specific skill is unchanged in power; it moves from the agent side to the skill side.

Local-imported skills are point-in-time copies; the source path is kept for traceability, not for sync. Because an agent's delivered path is a link to master, a user editing `SKILL.md` from inside an agent's `skills/` folder edits master, and every other agent sees it on its next read without any drift being reported; deleting a file there likewise affects master. If an agent's `config_dir` is moved or removed externally, the next sync operation surfaces the failure and `verify` reports the affected bindings. Codex also reads `~/.agents/skills` (its newer standard location) and treats `<config_dir>/skills` as backward-compatible; delivery stays at `<config_dir>/skills` for both agent types and the unmanaged scan covers both. `~/.agents/skills` is shared with other tools, so Coffer classifies only its own links as managed and never garbage-collects another tool's skills.

This spec owns the three `/api/v1/agents/{uid}/unmanaged-skills` routes (list, adopt, delete): their code (`surfaces/http/agent_unmanaged_skill_routes.py`), their contract (this spec's `contracts/api.openapi.yaml`) and their import-linter fence (the module sits on the `skill` kind's side of a zero-exception contract in `backend/pyproject.toml`) all say so, and the agent is an argument to these operations, not their subject. The web UI's open-in-external-editor and reveal-in-file-manager affordances in the file viewer are the daemon's filesystem-action endpoints ([ADR daemon-proxies-os-file-actions](../../../docs/decisions/daemon-proxies-os-file-actions.md)) opening the user's preferred external editor ([web-ui](../web-ui/spec.md) "Let the user choose an external editor"), and the Add-skill dialog uses the shared folder picker from spec agent-registry; this spec assumes both and feeds the chosen path to the import unchanged. A browse-and-install skill catalogue was prototyped and withdrawn for lack of a content ecosystem.

## Requirements

### Requirement: Register each skill as a resource with a SKILL.md-safe name
The system MUST register each managed skill as a Resource of kind `skill`, identified by the framework's immutable `uid` ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)). Its `name` is a mutable label taken from SKILL.md frontmatter at import, unique within the kind, and MUST satisfy the frontmatter's own charset (`^[a-z0-9][a-z0-9_-]{0,63}$`) on every write — registration and rename alike — because Coffer writes that name back into SKILL.md and must not produce a file its own importer would reject.

#### Scenario: refuse a skill name its own SKILL.md could not carry
- **GIVEN** an imported skill `before` delivered to a registered agent
- **WHEN** the user renames it to `My.Skill`, `MySkill` or `-leading` — names the framework's own rule would accept but the frontmatter charset does not
- **THEN** each rename is refused as a validation error before anything moves
- **AND** the row, the master folder, its SKILL.md `name: before` and the delivered link all still carry the old name, and `verify` reports no drift

### Requirement: Validate the skill configuration schema
The system MUST validate skill configuration against a kind-specific schema with fields `source` (variants: `local_import`, carrying the path it was imported from, and `builtin`, carrying nothing at all — see "Regenerate Coffer's builtin skill from the build"), `skill_md_description`, `version_hash`, and `last_synced_from_source_at`. The config MUST NOT restate the skill's name; that is `Resource.name`.

#### Scenario: store a skill's config without restating its name
- **GIVEN** a skill imported from a local folder
- **WHEN** its resource is read back
- **THEN** its config holds a `local_import` source carrying the original path, `skill_md_description`, `version_hash` and `last_synced_from_source_at`, and no field restating the name
- **AND** a config carrying a field the schema does not define (such as `skill_md_name`) is refused, and a `builtin` source validates to its variant name and nothing else

### Requirement: Keep one master folder per skill and carry it through a rename
The system MUST store each managed skill's content under `~/.coffer/skills/<name>/`, with that path as the single editable source of truth. Because that path is named after the skill's label, a rename MUST carry it: the kind's rename hook ([resource-framework](../resource-framework/spec.md) "Treat a resource's name as a mutable label") MUST move the master folder, re-point every delivered copy at `<skill_dir>/<new name>`, and rewrite the master `SKILL.md`'s frontmatter `name` — that last one because the agent product reads it, so a rename it never sees is not a rename. Only that one frontmatter field changes; the rest of the file MUST survive byte-for-byte, since it is a document the user writes and edits themselves. `version_hash` MUST be recomputed over the rewritten bytes. A rename MUST NOT rewrite any other reference: per-agent bindings hold the resource's identity, not its name, and MUST survive untouched. A move that cannot be completed MUST abort the rename with nothing changed; a delivered copy that cannot be re-pointed is ordinary drift (see "Report skill drift on request") and MUST NOT abort it.

#### Scenario: renaming a skill carries its master folder, links and frontmatter name
- **GIVEN** an imported skill `before` delivered to a registered agent, whose SKILL.md carries comments, other frontmatter fields and a body
- **WHEN** the user renames it to `after`
- **THEN** the master folder and the agent's delivered link are at `after` (the link resolving to the new master), and the same binding row still records the delivery
- **AND** the SKILL.md differs from before only in `name: after`, and `version_hash` is the digest of the rewritten bytes
- **AND** when a folder already occupies the destination the rename is refused with the row, the master folder and the link all left under the old name

### Requirement: Validate imported skill folders against AgentSkills
The system MUST validate every imported skill folder against the AgentSkills specification: `SKILL.md` present; frontmatter `name` present and non-empty (lowercase alphanumerics, hyphen, or underscore, ≤64 chars) and `description` present, non-empty, and ≤1024 chars; no path-escape symlinks; total size within a configurable limit (default 50 MB). A folder that violates any of these MUST be rejected with `unprocessable_entity` (422) and nothing persisted. A folder over the size limit is rejected with the configured cap and a hint to adjust settings.

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
The system MUST support importing a skill from a local filesystem path; the original source path is recorded for provenance but is not retained as a live dependency. Re-importing a name that already exists MUST be rejected by default (`conflict`, 409); with an explicit `overwrite` flag (CLI `--force`) the existing skill is replaced in place — the master folder content is swapped atomically, its `version_hash` and `last_synced_from_source_at` are refreshed, and its per-agent bindings and delivered symlinks are preserved (the master folder name is unchanged). Re-import overwrite is the only skill update mechanism (there is no live source to re-fetch); the replacement is audited as an update. On a name collision the user either renames via SKILL.md frontmatter and retries, or re-imports with `overwrite`.

#### Scenario: import a valid local skill folder
- **GIVEN** the daemon is running and no skill named `my-skill` exists,
- **WHEN** the user imports a folder containing a valid SKILL.md with frontmatter `name: my-skill`,
- **THEN** Coffer copies the folder to `~/.coffer/skills/my-skill/`, persists a Resource of kind `skill`, and records an audit entry.

#### Scenario: re-import a skill with overwrite replaces it
- **GIVEN** a skill named `my-skill` is already imported and enabled for an agent,
- **WHEN** the user imports a folder with frontmatter `name: my-skill` again with `overwrite` (`--force`),
- **THEN** the master folder content is replaced atomically, the skill's `version_hash` is refreshed, the existing per-agent binding and its delivered symlink are preserved, and a skill-update audit entry is recorded — whereas the same re-import without `overwrite` is rejected with `conflict` (409).

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
- `{"agents": ["claude_code"]}` — only the named agents receive it; names that are not registered yet are legal and simply never match.
- `{"agents": []}` — nobody receives it, while the skill stays in the library, converged and visible.

Those two together are the skill's REACH, and reach is machine-local: it is set on the machine it applies to, a converge round neither carries it away nor writes over it (spec vault-sync, "Keep reach machine-local"), and the predicate therefore takes no machine argument and has no machine to take. What converges is the skill — its files, its metadata — unless it is Coffer's own generated one (see "Regenerate Coffer's builtin skill from the build"). A skill can still be delivered here and dormant on another machine — that is two machines each holding their own `enabled` flag and their own scope, not one scope naming machines. The surface that sets reach MUST say that the setting stops at this machine.

No other flag decides which agents a skill is FOR: neither the delivery bookkeeping of "Track delivered copies as internal bookkeeping" nor any field on the agent resource; the agent resource carries no skill-delivery policy at all. `enabled` is a real switch: disabling a skill reclaims every delivered copy (master untouched) and re-enabling redelivers it to every agent its scope still grants. Scope is a hard grant: narrowing it to exclude an agent reclaims that delivery on the next reconcile even if the copy got there some other way, and widening it delivers; no per-agent state can hold a copy against the scope or keep one away from an agent the scope grants. A DISABLED AGENT is a separate matter and is never written into at all — the predicate names the agents a skill belongs to, while an agent the user switched off is one Coffer does not touch; its held copies are reclaimed and re-enabling it reconciles them back. A reconcile that finds a delivered copy the predicate no longer grants MUST reclaim it (remove the link, clear the delivery record) per "Reclaim a delivered copy without touching master", and MUST deliver a copy the predicate now grants but the agent does not hold. This predicate governs **delivery** — writing a skill into an agent's own filesystem — and is the only path by which a skill reaches an agent (see "Expose no skill tools over MCP").

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
- **GIVEN** an enabled skill currently delivered to an agent whose name its scope includes,
- **WHEN** the user edits the skill's scope to exclude this agent and the next reconcile runs,
- **THEN** the delivered symlink is removed and the delivery record is cleared — scope is a hard grant, and no per-agent state can hold the copy against it.

### Requirement: Report skill drift on request
The system MUST provide a `verify` operation — a read-only CLI/REST facility (`coffer skill verify`, `POST /skills/verify`; there is no web UI surface for it) — that compares each enabled binding to its on-disk target and reports drift categories (missing link, tampered link, missing master, orphan master) with suggested remedies, and exits non-zero on the CLI when drift is found. Asking for the report MUST NOT itself repair anything. The drift report is ephemeral: each binding whose on-disk target disagrees with the binding state, categorized by drift type with a suggested remedy.

#### Scenario: detect drift in agent skill directories
- **GIVEN** a binding exists but its target on disk has been deleted, replaced, or relinked,
- **WHEN** the user runs `coffer skill verify` (CLI) or calls `POST /skills/verify` (REST) — there is no web UI surface for this,
- **THEN** the report lists each drift type with a suggested remedy and exits with a non-zero status; asking for the report never itself repairs anything — repair runs only along the separate paths in "opt-in repair re-delivers repairable drift from master" and the boot-heal scenarios below.

### Requirement: Heal safely repairable drift at daemon boot
The system MUST remediate the drift kinds "Repair repairable drift from master" designates safely repairable automatically at daemon boot, without waiting for a person to act — boot is the point nothing else ever reconciled: delivery reconciliation ("Reconcile deliveries per agent on every trigger") keeps each agent's delivered *set* of skills correct on its own triggers, but never inspects an already-delivered link's on-disk health, so a broken or tampered link (an agent's own installer rewriting its skills directory, a user tidying files, a restore from backup) previously stayed broken until someone happened to run the manual repair by hand. Drift kinds that repair does not consider safely repairable MUST never be auto-remediated, boot included, and stay reported only — logged with skill, agent, drift kind, on-disk path and suggested remedy — for manual action via the on-demand repair path.

#### Scenario: skill drift self-heals at daemon boot
- **GIVEN** an agent's delivered skill link is missing (deleted) or tampered (repointed elsewhere) while the daemon is not running,
- **WHEN** the daemon starts,
- **THEN** the link is re-created pointing to master exactly as the opt-in repair would do it, the repair is recorded in the audit log with an actor identifying the boot heal rather than a person, and startup completes normally whether or not anything needed repair.

#### Scenario: boot heal leaves unsafe drift for a human to find
- **GIVEN** a foreign regular directory occupies a delivered skill's link path, or a binding's master folder no longer exists,
- **WHEN** the daemon starts,
- **THEN** neither is touched — the foreign content and the missing master are left exactly as found — and each is logged clearly enough (skill, agent, drift kind, on-disk path, suggested remedy) for a person to find, since this log line is now the only surface residual drift has.

#### Scenario: a boot heal failure never blocks startup
- **GIVEN** the boot heal encounters an error while inspecting or repairing a binding (e.g. a filesystem it cannot read),
- **WHEN** the daemon starts,
- **THEN** the error is logged and the daemon still comes up — a boot heal that can crash the daemon would be worse than the drift it exists to fix.

### Requirement: Repair repairable drift from master
The system MUST provide a drift repair that re-delivers repairable drift — missing link and tampered link — from the master library, and MUST NOT modify foreign/user content (replaced-with-regular), a missing master, or an orphan master; those are left intact and reported as requiring manual action. This repair runs (a) automatically per "Heal safely repairable drift at daemon boot", once at every daemon boot, audited with an actor that identifies the automatic path rather than a person, and never allowed to fail startup; and (b) on demand via the CLI (`coffer skill verify --fix`) and REST (`POST /skills/repair`) for anyone who wants to trigger or inspect a repair directly. Each repair, automatic or on-demand, MUST be audited.

#### Scenario: opt-in repair re-delivers repairable drift from master
- **GIVEN** an agent skill directory where one enabled binding has a missing Coffer link, another has a tampered Coffer link (a stale link pointing elsewhere), a third binding's path is occupied by a foreign regular directory the user owns, and a fourth binding's master folder no longer exists,
- **WHEN** the user runs the opt-in repair (`coffer skill verify --fix` / `POST /skills/repair`),
- **THEN** the missing link is re-created pointing to master, the tampered link is backed up to `<path>.coffer-backup-<ts>` and then re-created pointing to master, the foreign regular directory is left completely untouched and still appears in the report as requiring manual action, the missing-master entry is left and reported as requiring manual action, and each re-delivery is recorded as a repair event in the audit log.

### Requirement: List unmanaged skills in an agent's skill locations
The system MUST scan a registered agent's skill locations — `<config_dir>/skills` for both types, plus `~/.agents/skills` for `codex` — and list **unmanaged** entries: everything that is not a Coffer-managed link (a link whose target resolves inside `~/.coffer/skills/`) and not Codex's `.system` entry. Each result carries name, path, location, and a `valid` flag (validation per "Validate imported skill folders against AgentSkills") with the failure reason when invalid. The scan is read-only and derived at request time; an unmanaged skill is never stored. An entry that is a symlink pointing outside the master store is listed as unmanaged but not adoptable; an entry without a valid SKILL.md is listed with `valid=false` and the reason, deletable but not adoptable until it validates.

#### Scenario: list unmanaged skills across an agent's skill locations
- **GIVEN** a registered `codex` agent with one Coffer-managed link in `<config_dir>/skills`, one hand-copied skill folder there, and another skill folder in `~/.agents/skills`,
- **WHEN** the user lists the agent's unmanaged skills,
- **THEN** Coffer returns exactly the two hand-placed skills — each with name, path, location, and a `valid` flag from SKILL.md validation — and excludes the managed link.

#### Scenario: exclude managed links and system entries from the unmanaged scan
- **GIVEN** an agent's skill directory containing Coffer-managed links and (for Codex) a `.system` entry,
- **WHEN** the user lists unmanaged skills,
- **THEN** neither the managed links nor the `.system` entry appear in the result.

### Requirement: Adopt an unmanaged skill
Users MUST be able to adopt a valid unmanaged skill. Adoption validates the folder per "Validate imported skill folders against AgentSkills", moves it to `~/.coffer/skills/<name>/`, registers the `skill` resource, delivers the managed link (see "Deliver a skill as a directory link"), and records an enabled binding for that agent — in that order, with any failure before registration leaving the original folder unmoved and unchanged (after registration the master copy is authoritative; a delivery failure is surfaced and retried via the binding, never rolled back). The managed link is always delivered to the agent's canonical delivery location `<config_dir>/skills/<name>`: adopting from `<config_dir>/skills` replaces the original path in place, while adopting from `~/.agents/skills` consolidates — the original folder there is removed and the link lands in `<config_dir>/skills` (Codex reads both locations, so the agent keeps seeing the skill). Name collisions MUST be rejected with `conflict` (409); invalid folders and symlinks pointing outside the master store MUST be rejected with `unprocessable_entity` (422). Adoption is audited as an adoption event.

#### Scenario: adopt an unmanaged skill into the master store
- **GIVEN** an unmanaged skill folder with a valid SKILL.md whose name collides with no master skill,
- **WHEN** the user adopts it,
- **THEN** Coffer validates it per "Validate imported skill folders against AgentSkills", moves the folder to `~/.coffer/skills/<name>/`, registers the `skill` resource, replaces the original path with the managed link, records a binding for that agent, and audits the adoption — and on any failure the original folder is left exactly where and as it was.

#### Scenario: reject adopting an invalid or conflicting unmanaged skill
- **GIVEN** an unmanaged entry that lacks a valid SKILL.md, collides with an existing master skill's name, or is a symlink pointing outside the master store,
- **WHEN** the user attempts to adopt it,
- **THEN** the request is rejected with a reason-specific error (invalid: `unprocessable_entity` 422; name conflict: `conflict` 409; foreign link: `unprocessable_entity` 422), and nothing is moved, registered, or linked.

### Requirement: Delete an unmanaged skill on explicit request
Users MUST be able to delete an unmanaged entry as an explicit, confirmed action. Deletion MUST remove only that entry from disk, never master content or bindings, and MUST be audited. Coffer never deletes an unmanaged entry on its own.

#### Scenario: delete an unmanaged skill
- **GIVEN** an unmanaged skill folder in an agent's skill location,
- **WHEN** the user deletes it (an explicit, confirmed action),
- **THEN** the folder is removed from disk, an audit entry is recorded, and no master content or binding is touched.

### Requirement: Reconcile deliveries per agent on every trigger
The system MUST reconcile deliveries per agent from the predicate of "Deliver a skill only where it is enabled and in scope" alone. A reconcile computes the agent's wanted set as `{s.name for s in skills if s.enabled and is_active(s.scope, agent_name)}` — a free function over the agent alone, with no evaluator object to build and no machine to bind into one. The same skill row can still be wanted here and unwanted on another machine, because the `enabled` flag and the scope this predicate reads are this machine's own, and the round that brought the skill here brought neither. It delivers every wanted skill the agent does not hold, and reclaims every held copy that is no longer wanted. It MUST run on: a skill being enabled or disabled, a skill's scope being edited, a skill being imported, a skill being removed, an agent being registered, an agent being enabled or disabled, an agent's `config_dir` changing, and the post-import hook after a sync import. A disabled agent's wanted set is empty, so the same reconcile reclaims its copies and restores them when it is enabled again. Conflicts at target paths follow "Report a foreign target instead of overwriting it" (report, never overwrite). The agent resource carries no skill-delivery policy of any kind — no follow flag, no exclusion list, no per-agent opt-out; the only inputs are the skill's `enabled` flag and its `scope`.

#### Scenario: import delivers a skill only where its scope grants it
- **GIVEN** two registered agents, `claude_code` and `codex`,
- **WHEN** the user imports a skill scoped to `["claude_code"]`,
- **THEN** the post-import reconcile delivers it to `claude_code` only, and `codex` receives nothing.

### Requirement: Expose unmanaged-skill operations under the skill surfaces
Unmanaged-skill operations MUST be available through the REST API, the `coffer skill unmanaged|adopt|rm-unmanaged` CLI (with `--json` on reads), and the agent's Skills tab in the web UI. They live under `coffer skill` and not under `coffer agent`: the agent is an argument to them, not their subject, and `coffer agent` carries only the groups whose subject IS the agent (`config`, `mcp`, `plugin`). Delivery itself is not an operation on this surface: it is controlled by the skill resource's `enabled` flag and `scope` through the generic resource enable/disable and scope surfaces. The agent detail page decides nothing about delivery: its Skills tab points at the Skills page and otherwise carries only the unmanaged skills found on that agent's disk.

#### Scenario: manage unmanaged skills from the skill command group
- **GIVEN** a registered agent with two hand-placed skill folders in its skills directory
- **WHEN** the user runs `coffer skill unmanaged <agent> --json`, then `coffer skill adopt <agent> <one>`, then `coffer skill rm-unmanaged <agent> <other> --force`
- **THEN** the listing is JSON naming both folders, the first becomes a managed skill and leaves the listing, and the second is removed from disk
- **AND** `coffer agent` offers no `unmanaged`, `adopt` or `rm-unmanaged` command

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

### Requirement: Offer every skill operation on REST, CLI and web
Every management operation MUST be available through (a) the REST API, (b) the `coffer skill ...` CLI with `--json`, and (c) the Skills page in the web UI. Per-(skill, agent) enable/disable is not among them: the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes and the `coffer skill enable|disable` CLI commands are REMOVED. Delivery is driven by the skill's `enabled` flag and `scope` through the generic resource surfaces — `coffer scope set skill <name> --agents …` and `coffer resource enable|disable skill <name>`.

The Skills page is a data table (search, filter, pagination, row multi-select for bulk actions) with import via a folder picker. It manages the skill resource itself, not per-agent bindings: a skill's detail view has an Overview metadata tab and a Files tab (file tree plus the viewer of "Show a skill's master folder read-only"), where every file and folder offers "open in external editor" and "reveal in file manager". The list's reach column and the detail page carry one reach button labelled with the answer ("Every agent", "2 agents", "Disabled") that opens a panel whose choices are Disabled, Every agent and Only selected agents — the last over the scope's list of agents, staged there and written once when the panel closes — and the list's reach filter offers those same states.

#### Scenario: desktop and CLI cover every operation
- **GIVEN** the daemon is running,
- **WHEN** the user performs each operation via the web UI and via `coffer skill ...`,
- **THEN** the same effect is achieved in either surface and CLI provides `--json` for read operations.

### Requirement: Show a skill's master folder read-only
The system MUST expose a **read-only** view of a skill's master folder: a recursive file tree (name, folder-relative path, absolute on-disk path, type, size, children) and the contents of an individual file (with its absolute on-disk path and containing folder's absolute path). Markdown files render as formatted Markdown; other text files show raw. Every file read MUST also return a content fingerprint (see "Save an existing skill file conditionally") so an in-app edit of that file can be saved conditionally. Reads MUST be contained to the master folder — any path that resolves outside it (`..` traversal, absolute path, or escaping symlink) MUST be rejected. File reads MUST be size-capped (truncating with a `truncated` flag) and MUST flag non-UTF-8 / NUL-containing files as binary with empty content. No symlink-following out of the folder.

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
The system MUST provide a write that overwrites an **existing text file** in the master folder, under the same containment guard and size cap as "Show a skill's master folder read-only"; it MUST refuse to create new files/directories here, to write outside the folder, or to overwrite a binary file with text. The write MUST be atomic with no symlink-following out of the folder. The in-app editor and programmatic clients (REST/CLI) share this one endpoint. Because the master folder is also a folder the user edits in their own editor, file reads MUST return a **content fingerprint** (a digest of the file's raw on-disk bytes — not of the possibly-truncated text returned, so an oversized file's fingerprint still round-trips and an edit past the truncation point is still detected), and a write MAY carry that fingerprint back: when it no longer matches the bytes on disk the write MUST be rejected with `conflict` (409) and the file left byte-identical, so the user re-reads and reapplies rather than silently losing the other edit. A write that omits the fingerprint stays unconditional (last writer wins), which is what a programmatic client that never read the file first needs.

#### Scenario: edit and save a skill file
- **GIVEN** an imported skill that contains an existing text file,
- **WHEN** the user edits that file in the in-app editor (or a programmatic REST/CLI client saves new contents for it) by its folder-relative path, passing back the fingerprint the read returned,
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
