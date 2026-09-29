## MODIFIED Requirements

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

### Requirement: Keep one master folder per skill
The system MUST store each managed skill's content under `~/.coffer/skills/<name>/`, with that path as the single editable source of truth. Because the skill's `name` is fixed after registration (see "Register each skill as a resource with a SKILL.md-safe name"), the master folder, every delivered link at `<config_dir>/skills/<name>` and the SKILL.md frontmatter `name` MUST keep that name for the life of the skill. No operation on any surface moves the master folder or rewrites that frontmatter field. Per-agent bindings hold the resource's identity, not its name.

#### Scenario: a refused name change leaves the master folder where it is
- **GIVEN** an imported skill `before` delivered to a registered agent, whose SKILL.md carries comments, other frontmatter fields and a body
- **WHEN** the user tries to change its name to `after`, and then to give it a title
- **THEN** both are refused, and the master folder and the agent's delivered link are still at `before`, the link resolving to that master, with the same binding row recording the delivery
- **AND** SKILL.md and the skill's `version_hash` are unchanged by either request, and nothing exists at `~/.coffer/skills/after/`

### Requirement: Cover skill management on REST, the CLI and the web
Every management operation MUST be available through (a) the REST API, (b) the `coffer skill` CLI group with `--json` on every read, and (c) the Skills page in the web UI — except `verify`, which has no web surface ("Report skill drift on request"). The `coffer skill` group MUST offer `list`, `show`, `add <folder>` (the import of "Import a skill from a local path", with `--force` to overwrite), `rm`, `enable`, `disable`, `scope <name> [--agents a,b | --all | --none]` and `verify [--fix]`. `enable` and `disable` switch the skill resource's own `enabled` flag, which with its scope drives delivery ("Deliver a skill only where it is enabled and in scope"); there is no per-(skill, agent) switch on any surface, and the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes do not exist. The group offers no `edit`: a skill's name is fixed, it has no title, and its description is its SKILL.md's, edited in the file.

A skill's master folder is plain files a person edits in their own editor. On the command line it is named by `coffer path skill <name>`, which prints the folder's absolute path, and it is read and edited on disk; the `coffer skill` group carries no command that lists, prints or writes a file inside it. The REST file tree, file read and conditional file write ("Show a skill's master folder read-only", "Save an existing skill file conditionally") serve the web UI's Files tab and programmatic clients.

The Skills page is a data table (search, filter, pagination, row multi-select for bulk actions) with import from a path field that takes a folder chosen with the folder picker or a path typed or pasted into it, trimmed of surrounding whitespace and quotes before it is sent. It shows each skill by its name, which it offers no way to edit. It manages the skill resource itself, not per-agent bindings: a skill's detail view has an Overview metadata tab and a Files tab (file tree plus the viewer of "Show a skill's master folder read-only"), where every file and folder offers "open in external editor" and "reveal in file manager". The list's reach column and the detail page carry one reach button labelled with the answer ("Every agent", "2 agents", "Disabled") that opens a panel whose choices are Disabled, Every agent and Only selected agents — the last over the scope's list of agents, staged there and written once when the panel closes — and the list's reach filter offers those same states.

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
