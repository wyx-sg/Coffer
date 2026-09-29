## MODIFIED Requirements

### Requirement: Expose unmanaged-skill operations on REST, CLI and web
Unmanaged-skill operations MUST be available through the REST API, through the top-level `coffer scan`, `coffer adopt skill <path>` and `coffer discard skill <path>` commands (with `--json` on `scan`), and through the agent's Skills tab in the web UI. The command line groups them with every other thing an agent holds that Coffer does not manage, so neither `coffer skill` nor `coffer agent` carries an unmanaged-skill command. Delivery itself is not an operation on this surface: it is controlled by the skill resource's `enabled` flag and `scope` through `coffer skill enable|disable|scope` and the matching resource routes. The agent detail page decides nothing about delivery: its Skills tab points at the Skills page and otherwise carries only the unmanaged skills found on that agent's disk. The agent's Skills tab is the only web surface that lists unmanaged skills or adopts them; the Skills page lists managed skills only (see "Cover skill management on REST, the CLI and the web"). The REST routes and CLI commands for unmanaged skills are unchanged.

#### Scenario: manage unmanaged skills with scan, adopt and discard
- **GIVEN** a registered agent with two hand-placed skill folders in its skills directory
- **WHEN** the user runs `coffer scan --agent <agent> --json`, then `coffer adopt skill <one path>`, then `coffer discard skill <other path>` and confirms it
- **THEN** the scan is JSON naming both folders as rows of kind `skill`, the first becomes a managed skill and leaves the next scan, and the second is removed from disk
- **AND** neither `coffer skill` nor `coffer agent` offers an `unmanaged`, `adopt` or `rm-unmanaged` command

#### Scenario: unmanaged skills are adopted only from the agent's Skills tab
- **GIVEN** an agent with a hand-placed skill folder
- **WHEN** the user looks for it in the web UI
- **THEN** the agent's Skills tab lists it with Adopt, and the Skills page does not list it

### Requirement: Act on an unmanaged skill from its detail page
The agent's Skills tab MUST open an unmanaged skill's detail page when its row is clicked; the rows carry Adopt and Delete and no Open folder. The detail page MUST show the skill's name with an Unmanaged badge and its location, a back link to that tab, and the actions Open folder (the folder in the OS file manager), Adopt ("Adopt an unmanaged skill"; disabled with its reason for an invalid folder or a foreign link) and Delete ("Delete an unmanaged skill on explicit request", confirmed first). A successful adoption MUST go on to the new managed skill's detail page, since the folder is no longer unmanaged; a successful delete MUST return to that tab.

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

### Requirement: Cover skill management on REST, the CLI and the web
Every management operation MUST be available through (a) the REST API, (b) the `coffer skill` CLI group with `--json` on every read, and (c) the Skills page in the web UI — except `verify`, which has no web surface ("Report skill drift on request"). The `coffer skill` group MUST offer `list`, `show`, `add <folder|archive|git-url>` (the imports of "Import a skill from a local path", "Add skills from an archive" and "Add skills from a Git repository", with `--ref` and `--path` for a repository, `--skill <name>` to pick among several skills, `--yes` to skip the confirmation and `--force` to overwrite), `rm`, `enable`, `disable`, `scope <name> [--agents a,b | --all | --none]` and `verify [--fix]`. `enable` and `disable` switch the skill resource's own `enabled` flag, which with its scope drives delivery ("Deliver a skill only where it is enabled and in scope"); there is no per-(skill, agent) switch on any surface, and the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes do not exist. The group offers no `edit`: a skill's name is fixed, it has no title, and its description is its SKILL.md's, edited in the file.

A skill's master folder is plain files a person edits in their own editor. On the command line it is named by `coffer path skill <name>`, which prints the folder's absolute path, and it is read and edited on disk; the `coffer skill` group carries no command that lists, prints or writes a file inside it. The REST file tree, file read and conditional file write ("Show a skill's master folder read-only", "Save an existing skill file conditionally") serve the web UI's Files tab and programmatic clients.

The Skills page is a data table (search, filter, pagination, row multi-select for bulk actions) with one **Add skill** action whose dialog offers three sources: **Folder** — a path field that takes a folder chosen with the folder picker or a path typed or pasted into it, trimmed of surrounding whitespace and quotes before it is sent; **Archive** — a `.zip` or `.skill` file uploaded from the browser; and **Git repository** — a URL with an optional ref and subpath. Each source first shows what it found — the skill or skills, their names and descriptions, any that cannot be added and why, and any whose name is taken, with Replace offered for those — and writes nothing until the user confirms. The dialog offers no way to create a new skill from scratch: a skill is authored in the user's own editor and added from where it lives. It shows each skill by its name, which it offers no way to edit. It lists only the skills Coffer manages: an agent's own (unmanaged) skills, and adopting them, live only on that agent's Skills tab (see "Expose unmanaged-skill operations on REST, CLI and web"), and while no skill is managed the page's empty state may link to the agents' Skills tabs but lists nothing from them. It manages the skill resource itself, not per-agent bindings. A skill's detail page (`/skills/<name>`, addressed by its fixed name as [web-ui](../web-ui/spec.md) "Lay out every detail page's tabs alike" says) has four tabs, in this order, each at its own path:

- **Files** (the default, `/skills/<name>`) — the file tree beside the viewer of "Show a skill's master folder read-only", opening with `SKILL.md` selected and rendered; a **Preview / Source** toggle switches a Markdown file between rendered and raw text, and **Edit** edits the file in place and saves it through "Save an existing skill file conditionally" (not offered on a builtin skill, which Coffer rewrites at every start). Every file and folder offers "open in external editor" and "reveal in file manager". There is no separate SKILL.md tab.
- **Delivery** (`/skills/<name>/delivery`) — the skill's description, source and version, its reach, and which agents hold a delivered copy and how (link or copy).
- **Requires** (`/skills/<name>/requires`) — the commands the skill declares it needs, each opening that command's page on the CLIs page ([web-ui](../web-ui/spec.md) "Show every CLI a skill requires on the CLIs page").
- **History** (`/skills/<name>/history`) — the folder's past versions with who wrote each, a diff and a restore, from the vault history specified with the change that records it.

The old `/skills/<uid>` address MUST redirect to `/skills/<name>`, `?tab=overview` to Delivery and `?tab=files` to Files. The list's reach column and the detail page carry one reach button labelled with the answer ("Every agent", "2 agents", "Disabled") that opens a panel whose choices are Disabled, Every agent and Only selected agents — the last over the scope's list of agents, staged there and written once when the panel closes — and the list's reach filter offers those same states.

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

#### Scenario: the add dialog offers three sources and no create
- **GIVEN** the Skills page
- **WHEN** the user chooses Add skill
- **THEN** the dialog offers Folder, Archive and Git repository, and no option to create a new skill

#### Scenario: nothing is added until the user confirms
- **GIVEN** the Add skill dialog showing the skills found in an uploaded archive
- **WHEN** the user closes the dialog without confirming
- **THEN** no skill resource exists for them and nothing is under `~/.coffer/skills/` for them

### Requirement: Validate the skill configuration schema
The system MUST validate skill configuration against a kind-specific schema with fields `source` (variants: `local_import`, carrying the path it was imported from; `archive_import`, carrying the archive's file name and the folder inside it the skill came from; `git_import`, carrying the repository URL, the ref asked for, the subpath and the commit it was pinned to; and `builtin`, carrying nothing at all — see "Regenerate Coffer's builtin skill from the build"), `skill_md_description`, `version_hash`, and `last_synced_from_source_at`. The config MUST NOT restate the skill's name; that is `Resource.name`.

#### Scenario: store a skill's config without restating its name
- **GIVEN** a skill imported from a local folder
- **WHEN** its resource is read back
- **THEN** its config holds a `local_import` source carrying the original path, `skill_md_description`, `version_hash` and `last_synced_from_source_at`, and no field restating the name
- **AND** a config carrying a field the schema does not define (such as `skill_md_name`) is refused, and a `builtin` source validates to its variant name and nothing else

#### Scenario: a git-imported skill records the commit it was pinned to
- **GIVEN** a skill added from a Git repository at ref `main` and subpath `skills/review`
- **WHEN** its resource is read back
- **THEN** its config holds a `git_import` source carrying the URL, `main`, `skills/review` and the full commit id that was checked out

### Requirement: Import a skill from a local path
The system MUST support importing a skill from a local filesystem path; the original source path is recorded for provenance but is not retained as a live dependency. Re-importing a name that already exists MUST be rejected by default (`conflict`, 409); with an explicit `overwrite` flag (CLI `--force`) the existing skill is replaced in place — the master folder content is swapped atomically, its `version_hash` and `last_synced_from_source_at` are refreshed, and its per-agent bindings and delivered symlinks are preserved (the master folder name is unchanged). For a skill added from a folder or an archive, re-import overwrite is the only update mechanism (there is no live source to re-fetch); a skill added from a Git repository is updated from its source instead (see "Update a Git-imported skill from its source"). The replacement is audited as an update. On a name collision the user either renames via SKILL.md frontmatter and retries, or re-imports with `overwrite`.

#### Scenario: import a valid local skill folder
- **GIVEN** the daemon is running and no skill named `my-skill` exists,
- **WHEN** the user imports a folder containing a valid SKILL.md with frontmatter `name: my-skill`,
- **THEN** Coffer copies the folder to `~/.coffer/skills/my-skill/`, persists a Resource of kind `skill`, and records an audit entry.

#### Scenario: re-import a skill with overwrite replaces it
- **GIVEN** a skill named `my-skill` is already imported and enabled for an agent,
- **WHEN** the user imports a folder with frontmatter `name: my-skill` again with `overwrite` (`--force`),
- **THEN** the master folder content is replaced atomically, the skill's `version_hash` is refreshed, the existing per-agent binding and its delivered symlink are preserved, and a skill-update audit entry is recorded — whereas the same re-import without `overwrite` is rejected with `conflict` (409).

## ADDED Requirements

### Requirement: Add skills from an archive
Users MUST be able to add skills from a `.zip` or `.skill` archive — uploaded from the web UI, or
named on the command line (`coffer skill add <file.zip>`). The archive is read into a staging area
outside the master store, and before anything is written the system MUST reject the whole archive,
naming the offending entries, when an entry has an absolute path or a `..` segment (zip-slip), is a
symlink, or would take the archive past the 50 MB skill cap once uncompressed — judged on each
entry's uncompressed size as it is read, not only on what the archive declares. A skill is a folder
whose `SKILL.md` is at the top of the archive or one folder down; an archive holding several such
folders offers each, and the user chooses which to add (on the command line, `--skill <name>`,
repeatable, or `--all`). An archive with no `SKILL.md` in either place MUST be rejected with a message
saying where one was looked for. Each chosen skill is then validated as a folder is ("Validate
imported skill folders against AgentSkills"), and a name already taken follows "Import a skill from
a local path": refused unless the user chooses Replace (`--force`), or renames it in its `SKILL.md`
and adds it again. Nothing is copied into `~/.coffer/skills/` or registered until the user confirms
(on the command line, answers the prompt or passes `--yes`); the staging area is removed either way.

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
- **GIVEN** a skill named `review` already added
- **WHEN** the user uploads an archive whose skill is also named `review`
- **THEN** the dialog marks it as taken and offers Replace; adding without Replace is refused with `conflict` (409), and choosing Replace swaps the content in place keeping its bindings

#### Scenario: an archive from the command line asks before adding
- **GIVEN** `skills.zip` holding two skills
- **WHEN** the user runs `coffer skill add skills.zip --skill review`
- **THEN** the command prints what it will add and asks for confirmation, and adds `review` only when the user answers yes

### Requirement: Add skills from a Git repository
Users MUST be able to add skills from a Git repository given its URL, an optional ref (branch, tag or
commit; the default branch when omitted) and an optional subpath — in the Add skill dialog, or with
`coffer skill add <git-url> [--ref <ref>] [--path <subpath>]`. The system MUST fetch the repository
with this machine's own `git` and credentials into a staging area, resolve the ref to one commit, and
find skills under the subpath by the rule archives use (a `SKILL.md` at the subpath's top or one folder
down), offering a choice when there are several. Symlinks that leave the checkout, and a checkout past
the 50 MB skill cap, MUST be rejected before anything is written. A chosen skill is validated, named
and confirmed as an archive's is, and is recorded with a `git_import` source pinned to the commit it
was copied from. It stays pinned to that commit until the user takes a newer one through "Update a Git-imported
skill from its source". A repository that cannot be fetched MUST be reported
with git's own message, and nothing is written.

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
A skill with a `git_import` source MUST be checked for newer commits on its ref — on demand, from a
**Check for updates** action on the skill's page, and periodically, every six hours — by fetching the
repository with this machine's `git` into a staging area; a check writes nothing to the master store.
When the ref has moved past the pinned commit, the skill MUST show **Update available** on the Skills
page and its detail page, with the commit range from the pinned commit to the new one. Choosing it
MUST show a preview of the change to the skill's folder — the files added, removed and changed, with a
diff — and apply nothing until the user confirms; confirming replaces the folder's content atomically
with the new commit's, moves the pin to it, keeps the skill's reach and delivered links, and is
audited as an update. When the skill's folder has been edited locally since the pinned commit (its
content no longer matches that commit), the update MUST show a **conflict** instead of a plain
preview, offering **Keep mine** (leave the folder and the pin as they are and stop offering this
update until a newer commit arrives), **Take theirs** (apply the new commit, discarding the local
edits) and **Compare** (the local folder, the pinned commit and the new commit side by side). A
source that cannot be fetched MUST be reported on the skill with git's message and the time of the
last successful check, and changes nothing.

#### Scenario: a newer commit shows update available
- **GIVEN** a skill pinned to commit `a1` of `main`, and `main` now at `c3`
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
