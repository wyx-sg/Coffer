## MODIFIED Requirements

### Requirement: Register each skill as a resource with a SKILL.md-safe name
The system MUST register each managed skill as a Resource of kind `skill`, identified by the framework's immutable `uid` ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)). Its `name` is taken from SKILL.md frontmatter at import or adoption, unique within the kind, and MUST satisfy the frontmatter's own charset (`^[a-z0-9][a-z0-9_-]{0,63}$`), so Coffer never registers a skill under a name its own importer would reject. The `name` MUST be **fixed** once the skill is registered, because it is the directory an agent loads the skill from and the identifier an agent invokes it by, so it is quoted in places Coffer cannot see ([resource-framework](../resource-framework/spec.md), the requirement that lets a kind declare its name fixed). An update whose `name` differs from the current one MUST be refused with `NAME_IMMUTABLE` (409) before anything moves, on REST and on the web UI alike. The refusal MUST say that a different name means removing the skill and importing it again, and that doing so resets its `enabled` flag, its scope and its deliveries. A skill carries no title ([resource-framework](../resource-framework/spec.md) "Carry an optional editable title on the kinds that have one"): every surface shows its fixed name, beside the SKILL.md `description` agents choose it by, and a title submitted for one is refused as a validation error with nothing changed.

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
- **THEN** the title is refused as a validation error, `coffer skill list` and the Skills page still show `before`, and `coffer skill show before --json` carries no `title`
- **AND** the master folder, its SKILL.md and the delivered link are byte-identical to before the request

### Requirement: Validate imported skill folders against AgentSkills
The system MUST validate every imported skill folder against the AgentSkills specification: `SKILL.md` present; frontmatter `name` present and non-empty (lowercase alphanumerics, hyphen, or underscore, ≤64 chars) and `description` present, non-empty, and ≤1024 chars; no path-escape symlinks; total size at most 50 MB, a fixed cap. A folder that violates any of these MUST be rejected with `unprocessable_entity` (422) and nothing persisted. A folder over the size limit is rejected as `SKILL_INVALID` with `details.reason` `size_limit_exceeded`.

#### Scenario: reject import of an invalid skill folder
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder that is missing `SKILL.md` or has empty `name`/`description` frontmatter,
- **THEN** the request is rejected with a clear error, and nothing is written to `~/.coffer/vault/skills/` or the vault.

#### Scenario: reject import containing path-escape symlinks
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder containing a symlink that resolves outside the folder,
- **THEN** the request is rejected with the offending paths listed, and nothing is persisted.

#### Scenario: reject a skill with an over-long description
- **GIVEN** the daemon is running,
- **WHEN** the user imports a folder whose SKILL.md `description` exceeds 1024 characters,
- **THEN** the request is rejected as invalid frontmatter, and nothing is written to `~/.coffer/vault/skills/` or the vault.

### Requirement: Import a skill from a local path
The system MUST support importing a skill from a local filesystem path; the original source path is recorded for provenance but is not retained as a live dependency. Re-importing a name that already exists MUST be rejected by default (`conflict`, 409); with an explicit `overwrite` flag (CLI `--force`) the existing skill is replaced in place — the master folder content is swapped atomically, its `version_hash` and `last_synced_from_source_at` are refreshed, and its per-agent bindings and delivered symlinks are preserved (the master folder name is unchanged). For a skill added from a folder or an archive, re-import overwrite is the only update mechanism (there is no live source to re-fetch); a skill added from a Git repository is updated from its source instead (see "Update a Git-imported skill from its source"). The replacement is audited as an update. On a name collision the user either renames via SKILL.md frontmatter and retries, or re-imports with `overwrite`. A folder added from the web UI is looked at before anything is copied, as an archive is ("Add skills from an archive"): the dialog shows the skill it found, or the skills one folder down when the folder itself holds no `SKILL.md`, and copies nothing until the user confirms. `coffer skill add <folder>` imports at once, since naming the folder on the command line is the confirmation.

#### Scenario: import a valid local skill folder
- **GIVEN** the daemon is running and no skill named `my-skill` exists,
- **WHEN** the user imports a folder containing a valid SKILL.md with frontmatter `name: my-skill`,
- **THEN** Coffer copies the folder to `~/.coffer/vault/skills/my-skill/`, persists a Resource of kind `skill`, and records an audit entry.

#### Scenario: re-import a skill with overwrite replaces it
- **GIVEN** a skill named `my-skill` is already imported and enabled for an agent,
- **WHEN** the user imports a folder with frontmatter `name: my-skill` again with `overwrite` (`--force`),
- **THEN** the master folder content is replaced atomically, the skill's `version_hash` is refreshed, the existing per-agent binding and its delivered symlink are preserved, and a skill-update audit entry is recorded — whereas the same re-import without `overwrite` is rejected with `conflict` (409).

#### Scenario: a folder is looked at before it is added
- **GIVEN** a folder holding a valid skill `release-notes`
- **WHEN** the user stages it in the Add skill dialog
- **THEN** the dialog shows `release-notes` with its description and file count, and nothing is under `~/.coffer/vault/skills/` for it and no skill resource exists until the user confirms

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

### Requirement: Deliver a skill only where it is enabled and in scope
A skill MUST be delivered to an agent if and only if the skill resource is enabled AND the skill's scope admits that agent — `skill.enabled AND is_active(skill.scope, agent=<agent>)`, one allow-list, left `null` admitting anything ([ADR per-agent-resource-scope](../../../docs/decisions/per-agent-resource-scope.md)). This is the same shape `mcp_server` uses, where scope alone decides which agents see a server's tools. The scope states:

- `None` — every registered agent receives the skill (the default for a fresh import).
- `{"agents": ["<agent uid>"]}` — only those agents receive it. The scope holds agent uids ([ADR resource-identity-is-an-immutable-uid](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)); the CLI and web UI let the user pick agents by name and store their uids. A uid that matches no agent registered here is legal and simply never matches.
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

### Requirement: List unmanaged skills in an agent's skill locations
The system MUST scan a registered agent's skill locations — `<config_dir>/skills` for both types, plus `~/.agents/skills` for `codex` — and list **unmanaged** entries: everything that is not a Coffer-managed link (a link whose target resolves inside `~/.coffer/vault/skills/`, or `~/.coffer/derived/skills/` for Coffer's own skill) and not Codex's `.system` entry. Each result carries name, path, location, and a `valid` flag (validation per "Validate imported skill folders against AgentSkills") with the failure reason when invalid. The scan is read-only and derived at request time; an unmanaged skill is never stored. An entry that is a symlink pointing outside the master store is listed as unmanaged but not adoptable; an entry without a valid SKILL.md is listed with `valid=false` and the reason, deletable but not adoptable until it validates. On the command line these entries are the rows of kind `skill` that `coffer scan` prints, across every registered agent or, with `--agent <name>`, for one; each row's reference is the entry's path.

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
Users MUST be able to adopt a valid unmanaged skill. Adoption validates the folder per "Validate imported skill folders against AgentSkills", moves it to `~/.coffer/vault/skills/<name>/`, registers the `skill` resource, delivers the managed link (see "Deliver a skill as a directory link"), and records an enabled binding for that agent — in that order, with any failure before registration leaving the original folder unmoved and unchanged (after registration the master copy is authoritative; a delivery failure is surfaced and retried via the binding, never rolled back). The managed link is always delivered to the agent's canonical delivery location `<config_dir>/skills/<name>`: adopting from `<config_dir>/skills` replaces the original path in place, while adopting from `~/.agents/skills` consolidates — the original folder there is removed and the link lands in `<config_dir>/skills` (Codex reads both locations, so the agent keeps seeing the skill). Name collisions MUST be rejected with `conflict` (409); invalid folders and symlinks pointing outside the master store MUST be rejected with `unprocessable_entity` (422). Adoption is audited as an adoption event. Adopting from a disabled agent is allowed and links in place exactly as for an enabled one, recording the binding — the folder was already there, so the agent sees no new content; the exception this makes to "Deliver a skill only where it is enabled and in scope" ends at the agent's next reconcile, which reclaims the link as it does every copy a disabled agent holds, and re-enabling the agent delivers it back. On the command line adoption is `coffer adopt skill <path>`, where `<path>` is the reference `coffer scan` printed for the entry.

#### Scenario: adopt an unmanaged skill into the master store
- **GIVEN** an unmanaged skill folder with a valid SKILL.md whose name collides with no master skill,
- **WHEN** the user adopts it,
- **THEN** Coffer validates it per "Validate imported skill folders against AgentSkills", moves the folder to `~/.coffer/vault/skills/<name>/`, registers the `skill` resource, replaces the original path with the managed link, records a binding for that agent, and audits the adoption — and on any failure the original folder is left exactly where and as it was.

#### Scenario: reject adopting an invalid or conflicting unmanaged skill
- **GIVEN** an unmanaged entry that lacks a valid SKILL.md, collides with an existing master skill's name, or is a symlink pointing outside the master store,
- **WHEN** the user attempts to adopt it,
- **THEN** the request is rejected with a reason-specific error (invalid: `unprocessable_entity` 422; name conflict: `conflict` 409; foreign link: `unprocessable_entity` 422), and nothing is moved, registered, or linked.

#### Scenario: adopting from a disabled agent links the skill in place
- **GIVEN** a disabled agent whose skills directory holds a valid unmanaged skill folder,
- **WHEN** the user adopts that folder,
- **THEN** the folder's content is in the master store, the original path is now the managed link to it, an enabled binding for that agent is recorded, and the adoption is audited under the skill's name.

### Requirement: Save an existing skill file conditionally
The system MUST provide a write that overwrites an **existing text file** in the master folder, under the same containment guard and size cap as "Show a skill's master folder read-only"; it MUST refuse to create new files/directories here, to write outside the folder, or to overwrite a binary file with text. The write MUST be atomic with no symlink-following out of the folder. The in-app editor and programmatic REST clients share this one endpoint. Because the master folder is also a folder the user edits in their own editor, file reads MUST return a **content fingerprint** (a digest of the file's raw on-disk bytes — not of the possibly-truncated text returned, so an oversized file's fingerprint still round-trips and an edit past the truncation point is still detected), and a write MUST carry that fingerprint back: when it no longer matches the bytes on disk the write MUST be rejected with `conflict` (409) and the file left byte-identical, so the user re-reads and reapplies rather than silently losing the other edit. A write that omits the fingerprint MUST be refused as a validation error (422) with nothing written: the master folder is a vault folder, every save is one compare-and-swap commit naming the user against the bytes that were read ([vault-storage](../vault-storage/spec.md) "Admit every vault write through one compare-and-swap path"), and a client that never read the file has nothing to compare.

#### Scenario: edit and save a skill file
- **GIVEN** an imported skill that contains an existing text file,
- **WHEN** the user edits that file in the in-app editor (or a programmatic REST client saves new contents for it) by its folder-relative path, passing back the fingerprint the read returned,
- **THEN** Coffer overwrites the file atomically and returns the file's new fingerprint, and a subsequent read returns the new contents; writing a non-existent path, a path outside the master folder, an existing binary file, or content over the size cap is rejected (`404`/`400`) and the file is left unchanged.

#### Scenario: reject a stale save of a skill file
- **GIVEN** an imported skill file opened in the in-app editor, whose read returned a content fingerprint,
- **WHEN** the user changes that same file in their own external editor and only then saves the in-app buffer with the now-stale fingerprint,
- **THEN** Coffer rejects the save with `conflict` (409, `SKILL_FILE_STALE`) and leaves the externally edited file byte-identical on disk; re-reading yields the current fingerprint and the retried save succeeds.

#### Scenario: a save without a fingerprint is refused
- **GIVEN** an imported skill that contains an existing text file
- **WHEN** a client saves new contents for it without the fingerprint a read returned
- **THEN** the save is refused as a validation error (422) and the file is byte-identical on disk

### Requirement: Regenerate Coffer's builtin skill from the build
The system MUST support a **builtin** skill — one whose `source` is `builtin` and whose master folder Coffer writes itself rather than a person importing it. Its content MUST be rewritten from the running build whenever the material it describes moves: at every daemon boot, and on each change to what it carries (for `coffer-guide`, a curation pass or a collection being created, deleted, enabled or disabled — [knowledge](../knowledge/spec.md) "Deliver the catalogue through the coffer-guide skill"). A write MUST be skipped when the master already holds exactly that text, so an unchanged boot registers, audits and re-delivers nothing. Everything downstream of the master folder is the ordinary machinery: the same validation ("Validate imported skill folders against AgentSkills"), the same resource, the same delivery predicate ("Deliver a skill only where it is enabled and in scope") and the same links ("Deliver a skill as a directory link"), the same drift verification and repair ("Report skill drift on request", "Repair repairable drift from master"). It follows that **an edit to a builtin skill does not survive** — the next rewrite replaces it — and the surfaces MUST say so rather than letting a person discover it; a correction belongs in the build, not in the folder.

A builtin skill MUST NOT be in the vault — neither its master folder nor its resource: both are filed in the derived class, the master under `~/.coffer/derived/skills/<name>/` and the resource under `~/.coffer/derived/resources/skill/` ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature", [vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves"). It is derived output, regenerated on each machine from material that already converges plus that machine's own reach, so publishing it is churn. The `skill` kind therefore files that one resource as derived while every other skill is a vault file, so no commit and no sync round carries it. The `builtin` source variant MUST still carry no fields — a path, a timestamp or a build id would each be a fact about one machine stored in a shape nothing reads. Seeding MUST NOT be able to fail a startup: a render or a write that fails leaves the previous master exactly where it was and every other skill still delivers.

#### Scenario: Coffer's own skill is rewritten from the build at every start
- **GIVEN** a registered builtin skill whose master `SKILL.md` a person has edited by hand,
- **WHEN** the daemon starts and the builtin seed runs,
- **THEN** the master folder holds the text the running build renders, the hand edit is gone, the resource's `version_hash` and description match the new text, and every agent the delivery predicate grants reads the new text through its existing link,
- **AND** a second start over an unchanged catalogue writes nothing, registers nothing and records no audit entry, while a render or a write that fails leaves the previous master intact and does not fail startup.

### Requirement: Keep one master folder per skill
The system MUST store each managed skill's content under `~/.coffer/vault/skills/<name>/`, with that path as the single editable source of truth; it is a vault folder, so every change to it — through Coffer or in the person's own editor — becomes a vault commit naming its writer ([vault-storage](../vault-storage/spec.md) "Admit every vault write through one compare-and-swap path"). Coffer's own builtin skill is the one exception, kept under `~/.coffer/derived/skills/` (see "Regenerate Coffer's builtin skill from the build"). Because the skill's `name` is fixed after registration (see "Register each skill as a resource with a SKILL.md-safe name"), the master folder, every delivered link at `<config_dir>/skills/<name>` and the SKILL.md frontmatter `name` MUST keep that name for the life of the skill. No operation on any surface moves the master folder or rewrites that frontmatter field. Per-agent bindings hold the resource's identity, not its name.

#### Scenario: a refused name change leaves the master folder where it is
- **GIVEN** an imported skill `before` delivered to a registered agent, whose SKILL.md carries comments, other frontmatter fields and a body
- **WHEN** the user tries to change its name to `after`, and then to give it a title
- **THEN** both are refused, and the master folder and the agent's delivered link are still at `before`, the link resolving to that master, with the same binding row recording the delivery
- **AND** SKILL.md and the skill's `version_hash` are unchanged by either request, and nothing exists at `~/.coffer/vault/skills/after/`

### Requirement: Cover skill management on REST, the CLI and the web
Every management operation MUST be available through (a) the REST API, (b) the `coffer skill` CLI group with `--json` on every read, and (c) the Skills page in the web UI. The `coffer skill` group MUST offer `list`, `show`, `add <folder|archive|git-url>` (the imports of "Import a skill from a local path", "Add skills from an archive" and "Add skills from a Git repository", with `--ref` and `--path` for a repository, `--skill <name>` (repeatable) or `--all` to pick among several skills, `--yes` to skip the confirmation and `--force` to replace a skill of the same name), `update <name>` ("Update a Git-imported skill from its source", with `--check`, `--yes`, `--take-theirs` and `--keep-mine`), `rm`, `enable`, `disable`, `scope <name> [--agents a,b | --all | --none]` and `verify [--fix]`. `enable` and `disable` switch the skill resource's own `enabled` flag, which with its scope drives delivery ("Deliver a skill only where it is enabled and in scope"); there is no per-(skill, agent) switch on any surface, and the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes do not exist. The group offers no `edit`: a skill's name is fixed, it has no title, and its description is its SKILL.md's, edited in the file.

A skill's master folder is plain files a person edits in their own editor. On the command line it is named by `coffer path skill <name>`, which prints the folder's absolute path, and it is read and edited on disk; the `coffer skill` group carries no command that lists, prints or writes a file inside it. The REST file tree, file read and conditional file write ("Show a skill's master folder read-only", "Save an existing skill file conditionally") serve the web UI's Files tab and programmatic clients.

The Skills page is the library of managed skills beside the open skill: a list with search, an All / On / Off filter and row multi-select for bulk reach and bulk delete, next to the selected skill's detail. It has one **Add skill** action whose dialog offers three sources: **Folder** — a path field that takes a folder chosen with the folder picker or a path typed or pasted into it, trimmed of surrounding whitespace and quotes before it is sent; **Archive** — a `.zip` or `.skill` file uploaded from the browser; and **Git repository** — a URL with an optional ref and subpath; under the source, an **Available to** reach control whose choice every added skill takes (every agent unless narrowed). Each source first shows what it found — the skill or skills, their names and descriptions, any that cannot be added and why, and any whose name is taken, with Replace offered for those — and writes nothing until the user confirms. The dialog offers no way to create a new skill from scratch: a skill is authored in the user's own editor and added from where it lives. It shows each skill by its name, which it offers no way to edit. It lists only the skills Coffer manages: an agent's own (unmanaged) skills, and adopting them, live only on that agent's Skills tab (see "Expose unmanaged-skill operations on REST, CLI and web"), and while no skill is managed the page's empty state may link to the agents' Skills tabs but lists nothing from them. It manages the skill resource itself, not per-agent bindings. A row carries a Built-in mark and an Off mark, and in place of its description the one thing that needs the reader, most urgent first: its master folder is gone ("Say when a skill's master folder is gone"), a folder is in the way of an agent's link ("Resolve a folder in the way of a skill's link"), a command it declares is missing, not logged in or too old, its Git source is unreachable, or an update is waiting ("Update a Git-imported skill from its source"). Folders in the skills store that no skill claims are listed apart, under **Not in your library** ("Act on a folder in the skills store that no skill claims"). A skill's detail (`/skills/<name>`, addressed by its fixed name as [web-ui](../web-ui/spec.md) "Lay out every detail page's tabs alike" says) shows its name, reach, a **⋯** menu — Open in editor, Reveal in Finder, Copy master path, Check agents' copies, Turn off, and Delete… (disabled on a builtin skill) — its description, and its master path or, for a Git skill, its repository, folder and pinned commit; above its tabs, a banner for each thing that needs the reader, with at most one action; and it has four tabs, in this order, each at its own path:

- **Files** (the default, `/skills/<name>`) — the file tree beside the viewer of "Show a skill's master folder read-only", opening with `SKILL.md` selected and rendered; a **Preview / Source** toggle switches a Markdown file between rendered and raw text, and **Edit** edits the file in place and saves it through "Save an existing skill file conditionally" (not offered on a builtin skill, which Coffer rewrites at every start). A text file offers **Open in editor**, a binary file **Open in default app** and **Reveal in Finder**, and a file too large to read whole shows its start read-only. A save refused because the file changed on disk keeps the edited text and offers Reload, Compare and Copy my text. There is no separate SKILL.md tab.
- **Delivery** (`/skills/<name>/delivery`) — every registered agent with the state of its copy: linked, copied where links are not allowed ("Fall back to copying where links are unavailable"), differing from master (the drift kinds of "Report skill drift on request" — a folder in the way offers **Review…**), or not delivered and why (the skill is off, the agent is outside its reach, or the agent is switched off); **Check again** runs the drift report afresh.
- **Requires** (`/skills/<name>/requires`) — the commands the skill declares it needs ("Show the commands a skill declares it needs"), each with its state on this machine and opening that command's page on the CLIs page ([web-ui](../web-ui/spec.md) "Show every CLI a skill requires on the CLIs page"); the tab offers nothing that installs or logs in — those live on the CLIs page.
- **History** (`/skills/<name>/history`) — the master folder's versions from the vault's history ([vault-storage](../vault-storage/spec.md) "Show, compare and restore any version of a vault file"), newest first, each with who wrote it and when; choosing one shows the diff of every file it changed, and **Restore this version** asks first and then restores the whole folder as a new commit, removing files added since, with a refusal shown in its dialog. Coffer's own builtin skill is not in the vault and says it has no history.

A skill added from a Git repository also shows its source — the repository, the folder, the pinned commit and the update status — with **Check now** and **Change source…** ("Change a Git-imported skill's source").

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

### Requirement: Add skills from an archive
Users MUST be able to add skills from a `.zip` or `.skill` archive — uploaded from the web UI, or named on the command line (`coffer skill add <file.zip>`), both through the same REST upload. The archive is read into a staging area outside the master store, and before anything is extracted the system MUST reject the whole archive, naming the offending entries, when an entry has an absolute path or a `..` segment (zip-slip), is a symlink, or would take the archive past the 50 MB skill cap once uncompressed — judged on each entry's uncompressed size as it is read, not only on what the archive declares; an upload itself larger than the cap is refused before it is read. A skill is a folder whose `SKILL.md` is at the top of the archive or one folder down; an archive holding several such folders offers each, and the user chooses which to add (on the command line, `--skill <name>`, repeatable, or `--all`). An archive with no `SKILL.md` in either place MUST be rejected with a message saying where one was looked for. Each chosen skill is then validated as a folder is ("Validate imported skill folders against AgentSkills"), and a name already taken follows "Import a skill from a local path": refused unless the user chooses Replace (`--force`), or renames it in its `SKILL.md` and adds it again. Nothing is copied into `~/.coffer/vault/skills/` or registered until the user confirms (on the command line, answers the prompt or passes `--yes`); the staging area is removed either way, and one never confirmed is removed after an hour. The skill's source records the archive's file name and the folder inside it.

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
- **WHEN** the user runs `coffer skill add skills.zip --skill review`
- **THEN** the command prints what it will add and asks for confirmation, and adds `review` only when the user answers yes

### Requirement: Update a Git-imported skill from its source
A skill with a `git_import` source MUST be checked for newer commits on its ref — on demand, from a **Check for updates** action on the skill's page (`coffer skill update <name> --check`), and periodically, every six hours — by fetching the repository with this machine's `git` into a staging area; a check writes nothing to the master store and its result is kept on this machine only. When the ref has moved past the pinned commit with commits that change the skill's folder, the skill MUST show **Update available** on the Skills page and its detail page, with the commit range from the pinned commit to the new one. Choosing it MUST show a preview of the change to the skill's folder — the files added, removed and changed, with a diff, and the commits in the range — and apply nothing until the user confirms; confirming replaces the folder's content atomically with the new commit's, moves the pin to it, keeps the skill's reach and delivered links, and is audited as an update. An update whose `SKILL.md` names a different skill, or which fails the checks of "Validate imported skill folders against AgentSkills", is refused and changes nothing. When the skill's folder has been edited locally since the pinned commit (its content no longer matches the content hash recorded for that commit), the update MUST show a **conflict** instead of a plain preview, offering **Keep mine** (leave the folder and the pin as they are and stop offering this update until a newer commit arrives), **Take theirs** (apply the new commit, discarding the local edits) and **Compare** (the local folder, the pinned commit and the new commit side by side). A source that cannot be fetched MUST be reported on the skill with git's message and the time of the last successful check, and changes nothing. On the command line `coffer skill update <name>` previews and asks before applying, refuses a conflict unless `--take-theirs` or `--keep-mine` says which side to keep, and `--yes` skips the question.

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
