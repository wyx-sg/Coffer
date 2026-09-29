## ADDED Requirements

### Requirement: Keep one master folder per skill
The system MUST store each managed skill's content under `~/.coffer/skills/<name>/`, with that path as the single editable source of truth. Because the skill's `name` is fixed after registration (see "Register each skill as a resource with a SKILL.md-safe name"), the master folder, every delivered link at `<config_dir>/skills/<name>` and the SKILL.md frontmatter `name` MUST keep that name for the life of the skill. No operation on any surface moves the master folder or rewrites that frontmatter field. Per-agent bindings hold the resource's identity, not its name.

#### Scenario: a refused name change leaves the master folder where it is
- **GIVEN** an imported skill `before` delivered to a registered agent, whose SKILL.md carries comments, other frontmatter fields and a body
- **WHEN** the user tries to change its name to `after`, and then sets its title instead
- **THEN** the name change is refused, and the master folder and the agent's delivered link are still at `before`, the link resolving to that master, with the same binding row recording the delivery
- **AND** SKILL.md and the skill's `version_hash` are unchanged by either request, and nothing exists at `~/.coffer/skills/after/`

### Requirement: Expose unmanaged-skill operations on REST, CLI and web
Unmanaged-skill operations MUST be available through the REST API, through the top-level `coffer scan`, `coffer adopt skill <path>` and `coffer discard skill <path>` commands (with `--json` on `scan`), and through the agent's Skills tab in the web UI. The command line groups them with every other thing an agent holds that Coffer does not manage, so neither `coffer skill` nor `coffer agent` carries an unmanaged-skill command. Delivery itself is not an operation on this surface: it is controlled by the skill resource's `enabled` flag and `scope` through `coffer skill enable|disable|scope` and the matching resource routes. The agent detail page decides nothing about delivery: its Skills tab points at the Skills page and otherwise carries only the unmanaged skills found on that agent's disk.

#### Scenario: manage unmanaged skills with scan, adopt and discard
- **GIVEN** a registered agent with two hand-placed skill folders in its skills directory
- **WHEN** the user runs `coffer scan --agent <agent> --json`, then `coffer adopt skill <one path>`, then `coffer discard skill <other path>` and confirms it
- **THEN** the scan is JSON naming both folders as rows of kind `skill`, the first becomes a managed skill and leaves the next scan, and the second is removed from disk
- **AND** neither `coffer skill` nor `coffer agent` offers an `unmanaged`, `adopt` or `rm-unmanaged` command

### Requirement: Cover skill management on REST, the CLI and the web
Every management operation MUST be available through (a) the REST API, (b) the `coffer skill` CLI group with `--json` on every read, and (c) the Skills page in the web UI — except `verify`, which has no web surface ("Report skill drift on request"). The `coffer skill` group MUST offer `list`, `show`, `add <folder>` (the import of "Import a skill from a local path", with `--force` to overwrite), `edit` (`--title`; a `--name` that differs from the current one is refused per "Register each skill as a resource with a SKILL.md-safe name"), `rm`, `enable`, `disable`, `scope <name> [--agents a,b | --all | --none]` and `verify [--fix]`. `enable` and `disable` switch the skill resource's own `enabled` flag, which with its scope drives delivery ("Deliver a skill only where it is enabled and in scope"); there is no per-(skill, agent) switch on any surface, and the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes do not exist.

A skill's master folder is plain files a person edits in their own editor. On the command line it is named by `coffer path skill <name>`, which prints the folder's absolute path, and it is read and edited on disk; the `coffer skill` group carries no command that lists, prints or writes a file inside it. The REST file tree, file read and conditional file write ("Show a skill's master folder read-only", "Save an existing skill file conditionally") serve the web UI's Files tab and programmatic clients.

The Skills page is a data table (search, filter, pagination, row multi-select for bulk actions) with import via a folder picker. It shows a skill's `title` where one is set and its name otherwise, and it offers editing the title but not the name. It manages the skill resource itself, not per-agent bindings: a skill's detail view has an Overview metadata tab and a Files tab (file tree plus the viewer of "Show a skill's master folder read-only"), where every file and folder offers "open in external editor" and "reveal in file manager". The list's reach column and the detail page carry one reach button labelled with the answer ("Every agent", "2 agents", "Disabled") that opens a panel whose choices are Disabled, Every agent and Only selected agents — the last over the scope's list of agents, staged there and written once when the panel closes — and the list's reach filter offers those same states.

#### Scenario: desktop and CLI cover every operation
- **GIVEN** the daemon is running,
- **WHEN** the user performs each operation via the web UI and via `coffer skill ...`,
- **THEN** the same effect is achieved in either surface and CLI provides `--json` for read operations,
- **AND** `coffer path skill <name>` prints the absolute path of the same master folder the Files tab shows, and `coffer skill` offers no `import`, `files`, `cat` or `write` command.

#### Scenario: switch and scope a skill from its own command group
- **GIVEN** two registered agents and an enabled skill with no scope, delivered to both
- **WHEN** the user runs `coffer skill scope <name> --agents <first agent>`, then `coffer skill disable <name>`, then `coffer skill enable <name>`
- **THEN** after the scope change only the first agent holds a delivered link, after `disable` neither does, and after `enable` the first agent holds it again
- **AND** each change is recorded in the audit log

## MODIFIED Requirements

### Requirement: Register each skill as a resource with a SKILL.md-safe name
The system MUST register each managed skill as a Resource of kind `skill`, identified by the framework's immutable `uid` ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)). Its `name` is taken from SKILL.md frontmatter at import or adoption, unique within the kind, and MUST satisfy the frontmatter's own charset (`^[a-z0-9][a-z0-9_-]{0,63}$`), so Coffer never registers a skill under a name its own importer would reject. The `name` MUST be **fixed** once the skill is registered, because it is the directory an agent loads the skill from and the identifier an agent invokes it by, so it is quoted in places Coffer cannot see ([resource-framework](../resource-framework/spec.md), the requirement that lets a kind declare its name fixed). An update whose `name` differs from the current one MUST be refused with `NAME_IMMUTABLE` (409) before anything moves, on REST, on `coffer skill edit` and on the web UI alike. The refusal MUST say that a different name means removing the skill and importing it again, and that doing so resets its `enabled` flag, its scope and its deliveries. What a person wants to call the skill on Coffer's own surfaces goes in the skill's optional `title` ([resource-framework](../resource-framework/spec.md), the requirement that gives every resource an editable `title`). A `title` MAY be set and changed at any time, and it MUST NOT be written into SKILL.md or change anything on disk.

#### Scenario: refuse a skill name its own SKILL.md could not carry
- **GIVEN** the daemon is running and no skill is registered under any of the names below
- **WHEN** the user imports, or adopts, a folder whose SKILL.md frontmatter `name` is `My.Skill`, `MySkill` or `-leading`
- **THEN** each is refused as a validation error before anything is written
- **AND** no `skill` resource exists afterwards and nothing is under `~/.coffer/skills/` for any of them

#### Scenario: refuse changing a registered skill's name
- **GIVEN** an imported skill `before` delivered to a registered agent
- **WHEN** the user submits the name `after` through the resource update route, through `coffer skill edit before --name after`, and through the web UI
- **THEN** each is refused with `NAME_IMMUTABLE` (409), and the message says that a new name means removing the skill and importing it again, which resets its enabled flag, scope and deliveries
- **AND** the row, the master folder `before`, its SKILL.md `name: before` and the delivered link are all exactly as they were, and `verify` reports no drift

#### Scenario: a skill's title is edited without touching disk
- **GIVEN** an imported skill `before` delivered to a registered agent
- **WHEN** the user sets its title to `Release checklist` with `coffer skill edit before --title "Release checklist"`
- **THEN** `coffer skill list` and the Skills page show `Release checklist` for that row, and `coffer skill show before --json` carries both the `name` `before` and the `title`
- **AND** the master folder, its SKILL.md and the delivered link are byte-identical to before the edit

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

## REMOVED Requirements

### Requirement: Keep one master folder per skill and carry it through a rename
**Reason**: A skill's name is fixed after registration, so there is no rename for the master folder, the delivered links or the SKILL.md frontmatter to follow.
**Migration**: The master folder keeps the name the skill was registered under; see "Keep one master folder per skill". To give a skill a different name, remove it and import it again; to change what Coffer's surfaces call it, set its `title`.

### Requirement: Expose unmanaged-skill operations under the skill surfaces
**Reason**: The command line handles everything an agent holds that Coffer does not manage with one set of top-level commands, so the unmanaged-skill commands leave `coffer skill`.
**Migration**: `coffer skill unmanaged <agent>` becomes `coffer scan --agent <agent>` (rows of kind `skill`), `coffer skill adopt` becomes `coffer adopt skill <path>`, and `coffer skill rm-unmanaged` becomes `coffer discard skill <path>`. The REST routes are unchanged. See "Expose unmanaged-skill operations on REST, CLI and web".

### Requirement: Offer every skill operation on REST, CLI and web
**Reason**: The skill group moves to the lifecycle verbs every kind shares, and a skill's master files are plain files that the command line names with `coffer path` instead of printing and writing them.
**Migration**: `coffer skill import` becomes `coffer skill add <folder>`; `coffer resource enable|disable skill <name>` becomes `coffer skill enable|disable <name>`; `coffer scope set skill <name>` becomes `coffer skill scope <name>`; `coffer skill files|cat|write` become `coffer path skill <name>` and editing the files on disk. The REST file routes stay for the web UI. See "Cover skill management on REST, the CLI and the web".
