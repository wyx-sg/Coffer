## MODIFIED Requirements

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

#### Scenario: a skill's title is edited without touching disk
- **GIVEN** an imported skill `before` delivered to a registered agent
- **WHEN** the user submits the title `Release checklist` for it through the resource update route
- **THEN** the title is refused as a validation error, `GET /api/v1/skills` and the Skills page still show `before`, and `GET /api/v1/skills/{uid}` carries no `title`
- **AND** the master folder, its SKILL.md and the delivered link are byte-identical to before the request

### Requirement: Import a skill from a local path
The system MUST support importing a skill from a local filesystem path; the original source path is recorded for provenance but is not retained as a live dependency. Re-importing a name that already exists MUST be rejected by default (`conflict`, 409); with an explicit `overwrite` flag (the Add dialog's Replace) the existing skill is replaced in place — the master folder content is swapped atomically, its `version_hash` and `last_synced_from_source_at` are refreshed, and its per-agent bindings and delivered symlinks are preserved (the master folder name is unchanged). For a skill added from a folder or an archive, re-import overwrite is the only update mechanism (there is no live source to re-fetch); a skill added from a Git repository is updated from its source instead (see "Update a Git-imported skill from its source"). The replacement is audited as an update. On a name collision the user either renames via SKILL.md frontmatter and retries, or re-imports with `overwrite`. A folder added from the web UI is looked at before anything is copied, as an archive is ("Add skills from an archive"): the dialog shows the skill it found, or the skills one folder down when the folder itself holds no `SKILL.md`, and copies nothing until the user confirms. `POST /api/v1/skills/import` imports at once, since naming the folder in the request is the confirmation.

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

### Requirement: Deliver a skill only where it is enabled and in scope
A skill MUST be delivered to an agent if and only if the skill resource is enabled AND the skill's scope admits that agent — `skill.enabled AND is_active(skill.scope, agent=<agent>)`, one allow-list, left `null` admitting anything ([ADR per-agent-resource-scope](../../../docs/decisions/per-agent-resource-scope.md)). This is the same shape `mcp_server` uses, where scope alone decides which agents see a server's tools. The scope states:

- `None` — every registered agent receives the skill (the default for a fresh import).
- `{"agents": ["<agent uid>"]}` — only those agents receive it. The scope holds agent uids ([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)); the web UI lets the user pick agents by name and stores their uids. A uid that matches no agent registered here is legal and simply never matches.
- `{"agents": []}` — nobody receives it, while the skill stays in the library, synced and visible.

Those two together are the skill's REACH, and reach is machine-local: it is set on the machine it applies to, it lives in this machine's reach record, so a sync round neither carries it away nor writes over it (spec vault-sync, "Keep reach machine-local"), and the predicate therefore takes no machine argument and has no machine to take. What travels is the skill — its master folder and its resource file in the vault — unless it is Coffer's own generated one (see "Regenerate Coffer's builtin skill from the build"). A skill can still be delivered here and dormant on another machine — that is two machines each holding their own `enabled` flag and their own scope, not one scope naming machines. The surface that sets reach MUST say that the setting stops at this machine.

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

#### Scenario: the command-line scan lists unmanaged skills as skill rows
- **GIVEN** a registered agent with one Coffer-managed link and one hand-placed skill folder in its skills directory
- **WHEN** `GET /api/v1/agents/{uid}/unmanaged-skills` is read
- **THEN** the answer holds exactly one skill, naming the hand-placed folder by its path with its `valid` flag
- **AND** the managed link is not among them

### Requirement: Adopt an unmanaged skill
Users MUST be able to adopt a valid unmanaged skill. Adoption validates the folder per "Validate imported skill folders against AgentSkills", moves it to `~/.coffer/vault/skills/<name>/`, registers the `skill` resource, delivers the managed link (see "Deliver a skill as a directory link"), and records an enabled binding for that agent — in that order, with any failure before registration leaving the original folder unmoved and unchanged (after registration the master copy is authoritative; a delivery failure is surfaced and retried via the binding, never rolled back). The managed link is always delivered to the agent's canonical delivery location `<config_dir>/skills/<name>`: adopting from `<config_dir>/skills` replaces the original path in place, while adopting from `~/.agents/skills` consolidates — the original folder there is removed and the link lands in `<config_dir>/skills` (Codex reads both locations, so the agent keeps seeing the skill). Name collisions MUST be rejected with `conflict` (409); invalid folders and symlinks pointing outside the master store MUST be rejected with `unprocessable_entity` (422). Adoption is audited as an adoption event. Adopting from a disabled agent is allowed and links in place exactly as for an enabled one, recording the binding — the folder was already there, so the agent sees no new content; the exception this makes to "Deliver a skill only where it is enabled and in scope" ends at the agent's next reconcile, which reclaims the link as it does every copy a disabled agent holds, and re-enabling the agent delivers it back.

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

#### Scenario: adopting from a disabled agent links the skill in place
- **GIVEN** a disabled agent whose skills directory holds a valid unmanaged skill folder,
- **WHEN** the user adopts that folder,
- **THEN** the folder's content is in the master store, the original path is now the managed link to it, an enabled binding for that agent is recorded, and the adoption is audited under the skill's name.

### Requirement: Delete an unmanaged skill on explicit request
Users MUST be able to delete an unmanaged entry as an explicit, confirmed action. Deletion MUST remove only that entry from disk, never master content or bindings, and MUST be audited. Coffer never deletes an unmanaged entry on its own.

#### Scenario: delete an unmanaged skill
- **GIVEN** an unmanaged skill folder in an agent's skill location,
- **WHEN** the user deletes it (an explicit, confirmed action),
- **THEN** the folder is removed from disk, an audit entry is recorded, and no master content or binding is touched.

### Requirement: Show a skill's master folder read-only
The system MUST expose over REST a **read-only** view of a skill's master folder, which the web UI's Files tab renders: a recursive file tree (name, folder-relative path, absolute on-disk path, type, size, children) and the contents of an individual file (with its absolute on-disk path and containing folder's absolute path). Markdown files render as formatted Markdown; other text files show raw. Every file read MUST also return a content fingerprint (see "Save an existing skill file conditionally") so an in-app edit of that file can be saved conditionally. Reads MUST be contained to the master folder — any path that resolves outside it (`..` traversal, absolute path, or escaping symlink) MUST be rejected. File reads MUST be size-capped (truncating with a `truncated` flag) and MUST flag non-UTF-8 / NUL-containing files as binary with empty content. No symlink-following out of the folder. The folder's absolute path is shown on the skill's page (**Copy master path**), and the folder is read and edited on disk (see "Cover skill management on REST, the CLI and the web").

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

### Requirement: Expose unmanaged-skill operations on REST, CLI and web
Unmanaged-skill operations MUST be available through the REST API (`GET`, `POST .../adopt` and `DELETE` under `/api/v1/agents/{uid}/unmanaged-skills`) and through the agent's Skills tab in the web UI; the command line carries no unmanaged-skill command. Delivery itself is not an operation on this surface: it is controlled by the skill resource's `enabled` flag and `scope` through the resource routes and the Skills page. The agent detail page decides nothing about delivery: its Skills tab opens with one **From Coffer** row — how many skills Coffer delivers to that agent, their first names, and **Open Skills ›**, a link to the Skills page narrowed to that agent — and then lists the unmanaged skills found on that agent's disk (see [agent-registry](../agent-registry/spec.md) "Show what Coffer manages for an agent in one row"). The Skills page accepts an `agent` query parameter, `/skills?agent=<uid>`, and then lists only the managed skills that reach that agent, with the agent named in a filter beside the search. The agent's Skills tab is the only web surface that lists unmanaged skills or adopts them; the Skills page lists managed skills only (see "Cover skill management on REST, the CLI and the web").

#### Scenario: manage unmanaged skills with scan, adopt and discard
- **GIVEN** a registered agent with two hand-placed skill folders in its skills directory
- **WHEN** the user lists `GET /api/v1/agents/{uid}/unmanaged-skills`, then adopts one with `POST .../unmanaged-skills/{skill}/adopt`, then deletes the other with `DELETE .../unmanaged-skills/{skill}` and confirms it
- **THEN** the list names both folders, the first becomes a managed skill and leaves the next list, and the second is removed from disk
- **AND** the command line offers no command that lists, adopts or deletes an unmanaged skill

#### Scenario: unmanaged skills are adopted only from the agent's Skills tab
- **GIVEN** an agent with a hand-placed skill folder
- **WHEN** the user looks for it in the web UI
- **THEN** the agent's Skills tab lists it as the agent's own, with Adopt, and the Skills page does not list it

### Requirement: Cover skill management on REST, the CLI and the web
Every management operation of a skill (import, update, remove, enable, disable, scope, verify) MUST be available through (a) the REST API and (b) the Skills page in the web UI; the command line carries no `coffer skill` command. The REST routes are `GET /api/v1/skills` and `GET /api/v1/skills/{uid}` to read, the imports of "Import a skill from a local path", "Add skills from an archive" and "Add skills from a Git repository" (`POST /api/v1/skills/import` and `/stage/*`), the updates of "Update a Git-imported skill from its source" (`/api/v1/skills/{uid}/source/*`), `DELETE /api/v1/skills/{uid}`, the resource update route for `enabled` and `scope`, and `POST /skills/verify` for the drift report. Three repair operations are the web UI's and REST's alone: adopting or removing an orphan master folder (`/skills/orphans*`), resolving a copy an agent holds (`/skills/copies/{agent}/resolve`) and changing a Git-imported skill's source (`/skills/{name}/source/change`); the drift report names an orphan and what to do about it. `enable` and `disable` switch the skill resource's own `enabled` flag, which with its scope drives delivery ("Deliver a skill only where it is enabled and in scope"); there is no per-(skill, agent) switch on any surface, and the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes do not exist. There is no edit operation: a skill's name is fixed, it has no title, and its description is its SKILL.md's, edited in the file.

A skill's master folder is plain files a person edits in their own editor. Its absolute path is shown on the skill's page (**Copy master path**) and in the REST file tree, and it is read and edited on disk; the command line carries no command that lists, prints or writes a file inside it. The REST file tree, file read and conditional file write ("Show a skill's master folder read-only", "Save an existing skill file conditionally") serve the web UI's Files tab and programmatic clients.

The Skills page is the library of managed skills beside the open skill: a list with search, an All / On / Off filter and row multi-select for bulk reach and bulk delete, next to the selected skill's detail. It has one **Add skill** action whose dialog offers three sources: **Folder** — a path field that takes a folder chosen with the folder picker or a path typed or pasted into it, trimmed of surrounding whitespace and quotes before it is sent; **Archive** — a `.zip` or `.skill` file uploaded from the browser; and **Git repository** — a URL with an optional ref and subpath; under the source, an **Available to** reach control whose choice every added skill takes (every agent unless narrowed). Each source first shows what it found — the skill or skills, their names and descriptions, any that cannot be added and why, and any whose name is taken, with Replace offered for those — and writes nothing until the user confirms. The dialog offers no way to create a new skill from scratch: a skill is authored in the user's own editor and added from where it lives. It shows each skill by its name, which it offers no way to edit. It lists only the skills Coffer manages: an agent's own (unmanaged) skills, and adopting them, live only on that agent's Skills tab (see "Expose unmanaged-skill operations on REST, CLI and web"), and while no skill is managed the page's empty state may link to the agents' Skills tabs but lists nothing from them. It manages the skill resource itself, not per-agent bindings. A row carries a Built-in mark and an Off mark, and in place of its description the one thing that needs the reader, most urgent first: its master folder is gone ("Say when a skill's master folder is gone"), a folder is in the way of an agent's link ("Resolve a folder in the way of a skill's link"), a command it declares is missing, not logged in or too old, its Git source is unreachable, or an update is waiting ("Update a Git-imported skill from its source"). Folders in the skills store that no skill claims are listed apart, under **Not in your library** ("Act on a folder in the skills store that no skill claims"). A skill's detail (`/skills/<name>`, addressed by its fixed name as [web-ui](../web-ui/spec.md) "Lay out every detail page's tabs alike" says) shows its name, reach, a **⋯** menu — Open in editor, Reveal in Finder, Copy master path, Check agents' copies, Turn off, and Delete… (disabled on a builtin skill) — its description, and its master path or, for a Git skill, its repository, folder and pinned commit; above its tabs, a banner for each thing that needs the reader, with at most one action; and it has four tabs, in this order, each at its own path:

- **Files** (the default, `/skills/<name>`) — the file tree beside the viewer of "Show a skill's master folder read-only", opening with `SKILL.md` selected and rendered; a **Preview / Source** toggle switches a Markdown file between rendered and raw text, and **Edit** edits the file in place and saves it through "Save an existing skill file conditionally" (not offered on a builtin skill, which Coffer rewrites at every start). A text file offers **Open in editor**, a binary file **Open in default app** and **Reveal in Finder**, and a file too large to read whole shows its start read-only. A save refused because the file changed on disk keeps the edited text and offers Reload, Compare and Copy my text. There is no separate SKILL.md tab.
- **Delivery** (`/skills/<name>/delivery`) — every registered agent with the state of its copy: linked, copied where links are not allowed ("Fall back to copying where links are unavailable"), differing from master (the drift kinds of "Report skill drift on request" — a folder in the way offers **Review…**), or not delivered and why (the skill is off, the agent is outside its reach, or the agent is switched off); **Check again** runs the drift report afresh.
- **Requires** (`/skills/<name>/requires`) — the commands the skill declares it needs ("Show the commands a skill declares it needs"), each with its state on this machine and opening that command's page on the CLIs page ([web-ui](../web-ui/spec.md) "Show every CLI a skill requires on the CLIs page"); the tab offers nothing that installs or logs in — those live on the CLIs page.
- **History** (`/skills/<name>/history`) — the master folder's versions from the vault's history ([vault-storage](../vault-storage/spec.md) "Show, compare and restore any version of a vault file"), newest first, each with who wrote it and when; choosing one shows the diff of every file it changed, and **Restore this version** asks first and then restores the whole folder as a new commit, removing files added since, with a refusal shown in its dialog. Coffer's own builtin skill is not in the vault and says it has no history.

A skill added from a Git repository also shows its source — the repository, the folder, the pinned commit and the update status — with **Check now** and **Change source…** ("Change a Git-imported skill's source").

The list's reach mark and the detail carry one reach button labelled with the answer ("All agents", the chosen agents' badges, "Off") that opens a panel whose choices are Off, All agents and Chosen agents — the last over the scope's list of agents, each switch and tick written at once — and the list's filter offers those same states.

#### Scenario: desktop and CLI cover every operation
- **GIVEN** the daemon is running,
- **WHEN** the user performs each operation via the web UI and via the REST routes,
- **THEN** the same effect is achieved in either surface,
- **AND** the skill's page shows the absolute path of the same master folder the Files tab shows, and the command line offers no `skill` command at all.

#### Scenario: switch and scope a skill from its own command group
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
- **AND** switching to Source shows the raw text, and Edit then saving writes the file through the conditional save

#### Scenario: the delivery tab shows each agent's copy
- **GIVEN** a skill scoped to one of two registered agents and delivered to it as a link
- **WHEN** the user opens the skill's Delivery tab
- **THEN** the first agent shows its copy as linked with its path, and the second as not delivered because it is outside the skill's reach

#### Scenario: the history tab says versions are not recorded yet
- **GIVEN** a skill whose master folder has no version in the vault's history yet
- **WHEN** the user opens its History tab
- **THEN** the tab says that no versions are recorded yet and what will appear there, and offers no restore

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
- **THEN** the versions are listed newest first, each with its writer and how many files it changed
- **AND** the newest is marked current, shown with its diff, and offers no restore

#### Scenario: restoring a version asks first and restores the whole folder
- **GIVEN** a skill's History tab with an older version chosen
- **WHEN** the user chooses Restore this version and confirms
- **THEN** the dialog first says that files added since are removed
- **AND** once confirmed, the whole folder is restored from that version and the dialog closes

#### Scenario: Coffer's own skill has no history
- **GIVEN** the builtin `coffer-guide` skill
- **WHEN** the user opens its History tab
- **THEN** the tab says Coffer's own skill has no history and reads none

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

#### Scenario: read an unmanaged skill's files from the command line
- **GIVEN** an agent with a hand-placed skill folder holding a nested file
- **WHEN** the user reads `GET /api/v1/agents/{uid}/unmanaged-skills` and reads the nested file at the path the skill's entry reports
- **THEN** the entry carries the folder's name, `valid` true and its absolute path, and the file on disk holds the nested file's contents
- **AND** the folder is still listed as unmanaged afterwards

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

#### Scenario: an archive from the command line asks before adding
- **GIVEN** `skills.zip` holding two skills
- **WHEN** the archive is staged with `POST /api/v1/skills/stage/archive`
- **THEN** the answer lists what would be added and nothing is added until `POST /api/v1/skills/stage/{staging_id}/confirm` names `review`, which then adds `review` only

### Requirement: Add skills from a Git repository
Users MUST be able to add skills from a Git repository given its URL, an optional ref (branch, tag or commit; the default branch when omitted) and an optional subpath — in the Add skill dialog, or by staging it with `POST /api/v1/skills/stage/git`. A GitHub folder address (`https://github.com/<owner>/<repo>/tree/<ref>/<path>`) is read as the repository, the ref and the subpath. The system MUST fetch the repository with this machine's own `git` into a staging area, resolve the ref to one commit, and find skills under the subpath by the rule archives use (a `SKILL.md` at the subpath's top or one folder down), offering a choice when there are several. Git runs with no prompt and no secret Coffer supplies: a repository URL MUST NOT carry a user name or password (an `ssh://git@host/…` user name is allowed; a token or password in the URL is refused, because the URL is stored in the vault, in the skill's metadata and in API answers), and a repository is reachable when it is public or when this machine's git already holds a credential for it (its credential helper or SSH keys), and Coffer stores none. Only the `https`, `http`, `ssh`, `git` and `file` transports are allowed, and submodules are not fetched. Symlinks that leave the skill folder, and a checkout of the subpath past the 50 MB skill cap, MUST be rejected before anything is written. A chosen skill is validated, named and confirmed as an archive's is, and is recorded with a `git_import` source pinned to the commit it was copied from and the content hash of its folder there. It stays pinned to that commit until the user takes a newer one through "Update a Git-imported skill from its source". A repository that cannot be fetched, a ref that names no commit and a subpath the commit does not hold MUST each be reported with git's own message, and nothing is written. When this machine has no `git`, staging MUST be refused `SKILL_SOURCE_UNREACHABLE` whose details carry `reason: "git_missing"` and `handoff`, a prompt (Principle IV, AI-Native) asking the person's agent to install git on this machine — naming its OS and architecture — and to confirm with `git --version`, naming no install command; the add dialog MUST offer it beside the refusal, as the change-source and update dialogs do beside theirs.

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

### Requirement: Update a Git-imported skill from its source
A skill with a `git_import` source MUST be checked for newer commits on its ref — on demand, from a **Check for updates** action on the skill's page (`POST /api/v1/skills/{uid}/source/check`), and periodically, every six hours — by fetching the repository with this machine's `git` into a staging area; a check writes nothing to the master store and its result is kept on this machine only. When the ref has moved past the pinned commit with commits that change the skill's folder, the skill MUST show **Update available** on the Skills page and its detail page, with the commit range from the pinned commit to the new one. Choosing it MUST show a preview of the change to the skill's folder — the files added, removed and changed, with a diff, and the commits in the range — and apply nothing until the user confirms; confirming replaces the folder's content atomically with the new commit's, moves the pin to it, keeps the skill's reach and delivered links, and is audited as an update. An update whose `SKILL.md` names a different skill, or which fails the checks of "Validate imported skill folders against AgentSkills", is refused and changes nothing. When the skill's folder has been edited locally since the pinned commit (its content no longer matches the content hash recorded for that commit), the update MUST show a **conflict** instead of a plain preview, offering **Keep mine** (leave the folder and the pin as they are and stop offering this update until a newer commit arrives), **Take theirs** (apply the new commit, discarding the local edits), **Compare** (the local folder, the pinned commit and the new commit side by side) and **Merge with an agent**: the preview carries `handoff`, a prompt (Principle IV, AI-Native) that asks the person's agent to merge the new commit into the local edits in the master folder — naming the skill, the master folder as the only place to edit, the files edited since the pin, the pinned and new commits with the commits' subjects, and the repository (without any credential in its URL), ref and folder to read upstream from, read-only — to show the person the diff, and to leave recording the merge to the person, who then records it per "Record an update merged into local edits". A preview with no local edits carries a `null` `handoff`. Building the prompt writes nothing. A source that cannot be fetched MUST be reported on the skill with git's message and the time of the last successful check, and changes nothing. Over REST the preview (`POST /api/v1/skills/{uid}/source/preview`) shows the change and applies nothing, applying (`.../source/apply`) refuses a conflict until the request says which side to keep, and the merge hand-off is the preview's `handoff`, exactly as served.

#### Scenario: a newer commit shows update available
- **GIVEN** a skill pinned to commit `a1` of `main`, and `main` now at `c3` with commits that change the skill's folder
- **WHEN** the periodic check runs, or the user chooses Check for updates
- **THEN** the skill shows Update available with the range `a1..c3` on the Skills page and its detail page
- **AND** nothing under `~/.coffer/vault/skills/` has changed

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

#### Scenario: a conflict hands merging the update to an agent
- **GIVEN** a skill pinned to `a1` whose `notes.txt` the user edited, and `main` at `c3` with a commit that changes the skill's folder
- **WHEN** the user opens the update and chooses Merge with an agent
- **THEN** the dialog offers Copy prompt and, where a managed agent is available, Ask an agent, beside Keep mine and Take theirs
- **AND** the prompt names the master folder, `notes.txt` as a local edit, `a1` and `c3` with the commit's subject and the repository to read upstream from, tells the agent to edit only the master folder and not to record the merge itself, and nothing on disk or in the pin has changed

#### Scenario: an unreachable source is reported and changes nothing
- **GIVEN** a Git-imported skill whose repository can no longer be fetched
- **WHEN** the user chooses Check for updates
- **THEN** the skill shows git's message and the time of its last successful check
- **AND** the folder and the pin are unchanged

#### Scenario: update a skill from the command line
- **GIVEN** a Git-imported skill whose ref has a newer commit that changes its folder
- **WHEN** the user reads `POST /api/v1/skills/{uid}/source/preview` and then applies the update
- **THEN** the preview carries the commit range and the files that change, and after the apply the folder holds the new commit's content and the pin has moved
- **AND** with a local edit the apply is refused until the request says to take theirs, while keeping mine leaves the folder and the pin as they are

### Requirement: Show the commands a skill declares it needs
The system MUST read the commands a skill declares it needs from the `requires` field of its `SKILL.md` frontmatter — a list, or a mapping whose `commands` key holds one — where each entry is a command name, a command name with a minimum version (`gh>=2.40`), or a mapping with `command` and an optional `version`. The skill's read model carries them as `requires`, each with its command and its minimum version when one is given, in the order declared; an entry that names no command is ignored rather than failing the skill. Declaring a requirement changes nothing about delivery: the skill is delivered whether or not the command is present. The web UI's Requires tab lists them, each linking to the command's page on the CLIs page, and says so when the skill declares none.

#### Scenario: a skill's requires tab links each command
- **GIVEN** a skill whose `SKILL.md` declares `requires: [jq, "gh>=2.40"]`
- **WHEN** the user opens its Requires tab
- **THEN** it lists `jq` and `gh` with the minimum `2.40`, and choosing `gh` opens `/clis/gh`
- **AND** `GET /api/v1/skills/{uid}` carries the same two requirements

### Requirement: Serve required commands on REST, the command line and the web
The required commands MUST be readable and checkable through
`GET /api/v1/clis`, `GET /api/v1/clis/{command}`, `POST /api/v1/clis/check`
and `POST /api/v1/clis/{command}/check`, each command carrying its hand-off
prompt and the MCP servers started with it (`needed_by_servers`: each server's
uid, name and launcher) beside the skills that need it (`needed_by`), and
the command line carries no `coffer cli` command. Lists MUST put problems first: missing, then outdated, then not
logged in, then ready. The web UI's CLIs page shows them (spec web-ui "Show
every CLI a skill requires on the CLIs page") and a skill's detail page
carries a **Requires** tab listing what the skill declares, each linked to its
command's page and offering the hand-off for a command that needs the user.

#### Scenario: the command line lists required commands problems first
- **GIVEN** skills requiring a missing `jq`, an outdated `gh` and a ready `uv`
- **WHEN** the user reads `GET /api/v1/clis`
- **THEN** the commands come back in the order `jq`, `gh`, `uv`, each with its status and the skills that need it

#### Scenario: the command line prints the same prompt
- **GIVEN** a missing required command `jq` and a ready `uv`
- **WHEN** the user reads `GET /api/v1/clis/jq` and the CLIs page's Copy prompt for `jq`
- **THEN** both carry exactly the same `handoff.prompt`
- **AND** `GET /api/v1/clis/uv` carries a `null` `handoff` and the page offers no prompt for it

#### Scenario: a CLI page lists the MCP servers started with the command
- **GIVEN** an enabled stdio MCP server `duckdb` started with `uvx`, a skill `data-profiling` requiring `uv`, and no `uv` on the agent's `PATH`
- **WHEN** the user reads `GET /api/v1/clis/uv`
- **THEN** it is `missing`, `needed_by` names `data-profiling`, `needed_by_servers` names `duckdb` with launcher `uvx`, and its hand-off prompt names both

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

### Requirement: Record an update merged into local edits
After the local edits of a Git-imported skill have been merged with an upstream update (by the person's agent, per the hand-off of "Update a Git-imported skill from its source"), the person MUST be able to record it — **I merged it** in the update dialog, confirmed first; `POST /api/v1/skills/{uid}/source/merged` with the upstream `commit`. Recording MUST move the pin to that commit and MUST NOT touch the master folder's files; the pin's content hash becomes that commit's own content, so the merged folder still counts as locally edited against its new base and a later update is a conflict again that lists exactly the edits carried over. The update is no longer offered, and the recording is audited as `skill_update_merged` with the old and the new commit. The commit MUST be an update waiting for the skill — the ref's newest commit or one of the commits between the pin and it that change the skill's folder, given in full or by a unique prefix of at least seven characters — and anything else (no newer commit, the pinned commit itself, a commit not on the ref) MUST be refused with `409 SKILL_UPDATE_NOT_PENDING`, changing nothing.

#### Scenario: recording a merge moves the pin and keeps the merged files
- **GIVEN** a skill pinned to `a1` with a local edit, `main` at `c3`, and the master folder merged with `c3` by an agent
- **WHEN** the user chooses I merged it and confirms, or posts `c3` to `POST /api/v1/skills/{uid}/source/merged`
- **THEN** the skill is pinned to `c3`, the master folder's files are exactly as the merge left them, `c3` is no longer offered, and the recording is audited as `skill_update_merged` from `a1` to `c3`
- **AND** when `main` moves on again the update is a conflict listing only the edit carried over

#### Scenario: recording a merge refuses a commit that is not the update
- **GIVEN** a skill pinned to `a1`
- **WHEN** a merge is recorded against `a1` itself, against a commit that is not on the ref, or while the ref has nothing newer
- **THEN** it is refused with `409 SKILL_UPDATE_NOT_PENDING`, the pin stays at `a1`, and nothing is audited

### Requirement: Hand unsettled skill drift to an agent with a prompt
The three drift kinds no pass settles — a folder Coffer did not make at a skill's link path, a folder in the skills store no skill owns, and a skill whose master folder is gone — MUST each carry a hand-off prompt (Principle IV, AI-Native) built from the finding alone, the same text on the drift report entry (`handoff` on `POST /skills/verify` and `POST /skills/repair`) and on the finding's attention item: for a folder in the way, compare it with the skill's master folder, say whether it holds edits worth keeping, and recommend **Adopt this folder** or **Replace it with Coffer's link**; for a folder no skill owns, say what it is and whether its `SKILL.md` names it, and recommend **Add to library** or **Delete folder**; for a missing master, look for a copy that can be restored (the folders Coffer set aside under `~/.coffer/content/backup/skills/`, a copied copy in an agent's skills folder, the skill's source, beside the Files tab's own Restore from the vault's history) and, once the person agrees, copy it back to where the master belongs. The prompts MUST tell the agent to move, delete or edit no folder itself except that one agreed copy; the choice stays the button the person presses, and the buttons stay (Check again, Repair, the two choices of "Resolve a folder in the way of a skill's link", Add to library and Delete folder, Remove the skill). The Skills page MUST offer Copy prompt and, where a managed agent is available, Ask an agent beside each such finding, in the compare of a folder in the way, on the pane of a folder no skill owns and on the Files tab of a skill whose master is gone. A missing or tampered link carries a `null` `handoff`: Repair is its fix. The attention items' reasons for these kinds MUST name no command to run.

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

### Requirement: Declare the secrets a skill requires
The mapping form of a skill's `requires:` frontmatter MAY name the Coffer
secrets the skill needs under `secrets:` — `requires: {commands: [...],
secrets: [...]}` — each entry a secret name as the secret store accepts it.
The list form of `requires:` MUST stay commands only. An entry that is not a
valid secret name, and a name given twice, MUST be skipped with a warning
without failing the skill. A key of the mapping other than `commands` and
`secrets` MUST be refused: it is reported as a warning and nothing under it
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
- **GIVEN** a SKILL.md declaring `requires: {commands: [jq], tools: [rg], env: {A: b}}`
- **WHEN** its requirements are read
- **THEN** `jq` is the one requirement and nothing under `tools` or `env` is read
- **AND** one warning names `env` and `tools` as refused

#### Scenario: the read model says whether each declared secret is set
- **GIVEN** an imported skill declaring the secrets `GH_TOKEN` and `NPM_TOKEN`, with only `NPM_TOKEN` in the secret store
- **WHEN** the skill is read through `GET /api/v1/skills/{uid}`
- **THEN** `requires_secrets` is `GH_TOKEN` not set and `NPM_TOKEN` set, and no secret value appears in the response
- **AND** once `GH_TOKEN` is stored the skill list reports both set
