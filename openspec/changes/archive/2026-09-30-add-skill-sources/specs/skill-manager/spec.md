## MODIFIED Requirements

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

## ADDED Requirements

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
Users MUST be able to add skills from a Git repository given its URL, an optional ref (branch, tag or commit; the default branch when omitted) and an optional subpath — in the Add skill dialog, or with `coffer skill add <git-url> [--ref <ref>] [--path <subpath>]`. A GitHub folder address (`https://github.com/<owner>/<repo>/tree/<ref>/<path>`) is read as the repository, the ref and the subpath. The system MUST fetch the repository with this machine's own `git` into a staging area, resolve the ref to one commit, and find skills under the subpath by the rule archives use (a `SKILL.md` at the subpath's top or one folder down), offering a choice when there are several. Git runs with no prompt and no credential Coffer supplies: a repository is reachable when it is public or when this machine's git already holds a credential for it (its credential helper or SSH keys), and Coffer stores none. Only the `https`, `http`, `ssh`, `git` and `file` transports are allowed, and submodules are not fetched. Symlinks that leave the skill folder, and a checkout of the subpath past the 50 MB skill cap, MUST be rejected before anything is written. A chosen skill is validated, named and confirmed as an archive's is, and is recorded with a `git_import` source pinned to the commit it was copied from and the content hash of its folder there. It stays pinned to that commit until the user takes a newer one through "Update a Git-imported skill from its source". A repository that cannot be fetched, a ref that names no commit and a subpath the commit does not hold MUST each be reported with git's own message, and nothing is written.

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
