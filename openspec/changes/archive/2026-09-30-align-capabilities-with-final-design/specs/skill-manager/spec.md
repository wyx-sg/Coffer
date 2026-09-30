## ADDED Requirements

### Requirement: Resolve a folder in the way of a skill's link
When an agent's link path for a skill holds a real folder that is not Coffer's link (drift kind "foreign content at the link path"), the system MUST offer two confirmed choices for that one agent's copy, on REST (`GET /skills/{uid}/copies/{agent_uid}` compares the two sides, `POST /skills/{uid}/copies/{agent_uid}/resolve` with `keep: master | agent` acts) and on the Skills page: **keep master** — the folder is moved to `~/.coffer/backup/skills/<agent>/<name>-<time>/`, never deleted, and Coffer's link is made in its place; **keep the agent's version** — its files become the master (its SKILL.md must name the same skill), so every other agent sees them through its link, and the folder is then backed up and linked the same way. The compare MUST show, per file, how the agent's folder differs from the master. Nothing else is touched, the choice is audited, and a builtin skill refuses both. Automatic repair keeps its rule: it never makes this choice.

#### Scenario: restoring from master backs the folder up and links it again
- **GIVEN** a skill delivered to an agent whose link was replaced by an edited real folder
- **WHEN** the user compares the copy and chooses to keep master
- **THEN** the compare lists the edited file with its diff, the folder is moved under `~/.coffer/backup/skills/<agent>/`, the agent's path is Coffer's link again, and the drift report no longer lists it

#### Scenario: adopting the agent's version makes it the master for every agent
- **GIVEN** a skill delivered to two agents, and the first agent's link replaced by an edited real folder
- **WHEN** the user chooses to keep that agent's version
- **THEN** the master holds the edited files, the first agent's path is Coffer's link again, and the second agent reads the edited files through its link

### Requirement: Refuse deleting a skill whose copy Coffer did not make
Deleting a skill MUST be refused with `409 SKILL_COPY_NOT_OURS` — naming the path and the agent — when any agent's delivery path for it holds a real folder that is not Coffer's link and not a copy Coffer made; nothing is removed then (not the master, not the record, not any other agent's link). The Skills page's delete confirmation stays open on the refusal and says which folder and what to do.

#### Scenario: a folder Coffer did not make stops the delete
- **GIVEN** a skill whose link in one agent was replaced by a real folder
- **WHEN** the user deletes the skill
- **THEN** the delete is refused with the folder's path, and the master folder, the skill record and the agent's folder are all still there

### Requirement: Act on a folder in the skills store that no skill claims
The system MUST list the folders in `~/.coffer/skills/` that no skill record claims (`GET /skills/orphans`: each with its path, whether its SKILL.md is valid and names the folder, and its file count) and offer two actions on one: add it to the library in place (`POST /skills/orphans/{name}/adopt`, validated like an import, reach as for a fresh import) or move it out of the store (`DELETE /skills/orphans/{name}`, to `~/.coffer/backup/skills/orphans/`, never a hard delete). A folder a record claims is not an orphan, and both actions refuse it with `404 SKILL_ORPHAN_NOT_FOUND`.

#### Scenario: an orphan folder is added in place or moved out
- **GIVEN** two folders with valid SKILL.md files in the skills store that no skill claims
- **WHEN** the user adds the first to the library and moves the second out
- **THEN** the first is a skill in the library, the second is under the backup folder and no longer in the store, and neither is listed as an orphan

### Requirement: Say when a skill's master folder is gone
Every read of a skill MUST carry `master_missing` — true when its master folder is no longer on disk — whether or not the skill is enabled, so a surface can say so even for a skill that is off and has no delivery the drift report would look at.

#### Scenario: a skill whose master is gone says so
- **GIVEN** an imported skill
- **WHEN** its master folder is removed outside Coffer
- **THEN** reading the skill reports `master_missing: true`, and it reported false before

### Requirement: Change a Git-imported skill's source
The system MUST let the user move a Git-imported skill to another repository, ref or folder (`POST /skills/{uid}/source/change` with `url`, `ref` and `path`) without replacing anything first: the new source is staged the way an add from Git is, must hold one valid skill with the skill's fixed name, and the answer is the same preview an update gives, measured against the skill's current folder. Applying it (`POST /skills/{uid}/source/apply` with that stage) swaps the folder in and records the new source; cancelling the stage leaves the skill and its source as they were.

#### Scenario: a new source is shown against the current version first
- **GIVEN** a skill added from one repository
- **WHEN** the user changes its source to a folder of another repository and then applies the preview
- **THEN** the preview lists the files that differ from the current folder while the folder is still unchanged, and after applying the folder holds the new source's files and the skill records the new repository, folder and commit

## MODIFIED Requirements

### Requirement: Report skill drift on request
The system MUST provide a `verify` operation — a read-only facility on the CLI (`coffer skill verify`), on REST (`POST /skills/verify`) and on the Skills page (**Check copies**) — that compares each enabled binding to its on-disk target — and each delivery the rule wants whose path a folder Coffer did not put there already occupies — and reports drift categories (missing link, tampered link, foreign content at the link path, missing master, orphan master) with suggested remedies, and exits non-zero on the CLI when drift is found. Asking for the report MUST NOT itself repair anything. The drift report is ephemeral: each binding whose on-disk target disagrees with the binding state, categorized by drift type with a suggested remedy. The Skills page lists the report's findings with the skill, the agent, the path and the suggested remedy, and offers the repair of "Repair repairable drift from master" for the findings it covers; the other findings stay listed for the user to act on.

#### Scenario: detect drift in agent skill directories
- **GIVEN** a binding exists but its target on disk has been deleted, replaced, or relinked,
- **WHEN** the user runs `coffer skill verify` (CLI) or calls `POST /skills/verify` (REST),
- **THEN** the report lists each drift type with a suggested remedy and exits with a non-zero status; asking for the report never itself repairs anything — repair runs only along the separate paths in "opt-in repair re-delivers repairable drift from master" and the boot-heal scenarios below.

#### Scenario: check agents' copies from the skills page
- **GIVEN** one skill whose delivered link is missing and another whose link path holds a folder Coffer did not put there
- **WHEN** the user chooses Check copies on the Skills page
- **THEN** both findings are listed with the skill, the agent and the path, and nothing on disk has changed
- **AND** choosing Repair re-creates the missing link, while the foreign folder is left as it was and stays listed

#### Scenario: a folder in the way of a first delivery is reported
- **GIVEN** an agent whose skills directory already holds a real folder named like a skill, and that skill is then imported with a reach that grants the agent
- **WHEN** the drift report runs
- **THEN** it lists that path as foreign content at the link path for the skill and the agent, and the folder is left exactly as it was

### Requirement: Fall back to copying where links are unavailable
When symlinks/directory junctions are unavailable (e.g., FAT32, network share), the system MAY fall back to copy mode for that target; the binding records `link_mode=copy_fallback` (audited as `mode: copy_fallback` on the enable event) and the UI MUST say so where the copy is shown: the skill's Delivery tab lists that agent's copy as **Copied, not linked**, naming the folder links are not allowed in and that Coffer copies again after each edit. A copy made this way is a working delivery, not a warning, so the library row carries no mark for it.

#### Scenario: fall back to a copy where a directory link cannot be made
- **GIVEN** a registered agent on a filesystem where neither a directory symlink nor a junction can be created
- **WHEN** an enabled skill is delivered to it
- **THEN** a real copy of the master folder is placed at `<config_dir>/skills/<name>`, the binding records `link_mode=copy_fallback`, the delivery audit entry carries `mode: copy_fallback`, and `verify` treats the copy as healthy rather than as drift
- **AND** the skill's Delivery tab shows that agent's copy as Copied, not linked, with the reason, while a plain symlink delivery shows Linked

### Requirement: Cover skill management on REST, the CLI and the web
Every management operation MUST be available through (a) the REST API, (b) the `coffer skill` CLI group with `--json` on every read, and (c) the Skills page in the web UI. The `coffer skill` group MUST offer `list`, `show`, `add <folder|archive|git-url>` (the imports of "Import a skill from a local path", "Add skills from an archive" and "Add skills from a Git repository", with `--ref` and `--path` for a repository, `--skill <name>` (repeatable) or `--all` to pick among several skills, `--yes` to skip the confirmation and `--force` to replace a skill of the same name), `update <name>` ("Update a Git-imported skill from its source", with `--check`, `--yes`, `--take-theirs` and `--keep-mine`), `rm`, `enable`, `disable`, `scope <name> [--agents a,b | --all | --none]` and `verify [--fix]`. `enable` and `disable` switch the skill resource's own `enabled` flag, which with its scope drives delivery ("Deliver a skill only where it is enabled and in scope"); there is no per-(skill, agent) switch on any surface, and the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes do not exist. The group offers no `edit`: a skill's name is fixed, it has no title, and its description is its SKILL.md's, edited in the file.

A skill's master folder is plain files a person edits in their own editor. On the command line it is named by `coffer path skill <name>`, which prints the folder's absolute path, and it is read and edited on disk; the `coffer skill` group carries no command that lists, prints or writes a file inside it. The REST file tree, file read and conditional file write ("Show a skill's master folder read-only", "Save an existing skill file conditionally") serve the web UI's Files tab and programmatic clients.

The Skills page is the library of managed skills beside the open skill: a list with search, an All / On / Off filter and row multi-select for bulk reach and bulk delete, next to the selected skill's detail. It has one **Add skill** action whose dialog offers three sources: **Folder** — a path field that takes a folder chosen with the folder picker or a path typed or pasted into it, trimmed of surrounding whitespace and quotes before it is sent; **Archive** — a `.zip` or `.skill` file uploaded from the browser; and **Git repository** — a URL with an optional ref and subpath; under the source, an **Available to** reach control whose choice every added skill takes (every agent unless narrowed). Each source first shows what it found — the skill or skills, their names and descriptions, any that cannot be added and why, and any whose name is taken, with Replace offered for those — and writes nothing until the user confirms. The dialog offers no way to create a new skill from scratch: a skill is authored in the user's own editor and added from where it lives. It shows each skill by its name, which it offers no way to edit. It lists only the skills Coffer manages: an agent's own (unmanaged) skills, and adopting them, live only on that agent's Skills tab (see "Expose unmanaged-skill operations on REST, CLI and web"), and while no skill is managed the page's empty state may link to the agents' Skills tabs but lists nothing from them. It manages the skill resource itself, not per-agent bindings. A row carries a Built-in mark and an Off mark, and in place of its description the one thing that needs the reader, most urgent first: its master folder is gone ("Say when a skill's master folder is gone"), a folder is in the way of an agent's link ("Resolve a folder in the way of a skill's link"), a command it declares is missing, not logged in or too old, its Git source is unreachable, or an update is waiting ("Update a Git-imported skill from its source"). Folders in the skills store that no skill claims are listed apart, under **Not in your library** ("Act on a folder in the skills store that no skill claims"). A skill's detail (`/skills/<name>`, addressed by its fixed name as [web-ui](../web-ui/spec.md) "Lay out every detail page's tabs alike" says) shows its name, reach, a **⋯** menu — Open in editor, Reveal in Finder, Copy master path, Check agents' copies, Turn off, and Delete… (disabled on a builtin skill) — its description, and its master path or, for a Git skill, its repository, folder and pinned commit; above its tabs, a banner for each thing that needs the reader, with at most one action; and it has four tabs, in this order, each at its own path:

- **Files** (the default, `/skills/<name>`) — the file tree beside the viewer of "Show a skill's master folder read-only", opening with `SKILL.md` selected and rendered; a **Preview / Source** toggle switches a Markdown file between rendered and raw text, and **Edit** edits the file in place and saves it through "Save an existing skill file conditionally" (not offered on a builtin skill, which Coffer rewrites at every start). A text file offers **Open in editor**, a binary file **Open in default app** and **Reveal in Finder**, and a file too large to read whole shows its start read-only. A save refused because the file changed on disk keeps the edited text and offers Reload, Compare and Copy my text. There is no separate SKILL.md tab.
- **Delivery** (`/skills/<name>/delivery`) — every registered agent with the state of its copy: linked, copied where links are not allowed ("Fall back to copying where links are unavailable"), differing from master (the drift kinds of "Report skill drift on request" — a folder in the way offers **Review…**), or not delivered and why (the skill is off, the agent is outside its reach, or the agent is switched off); **Check again** runs the drift report afresh.
- **Requires** (`/skills/<name>/requires`) — the commands the skill declares it needs ("Show the commands a skill declares it needs"), each with its state on this machine and opening that command's page on the CLIs page ([web-ui](../web-ui/spec.md) "Show every CLI a skill requires on the CLIs page"); the tab offers nothing that installs or logs in — those live on the CLIs page.
- **History** (`/skills/<name>/history`) — the folder's past versions, from the vault's history once it records a skill's versions; until then the tab says that a skill's versions are not recorded yet.

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
