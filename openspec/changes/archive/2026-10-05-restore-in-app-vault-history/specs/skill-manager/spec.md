## ADDED Requirements

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

## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: Cover skill management on REST and on the Skills page
**Reason**: A skill's history is a History tab again, with Restore this version; the History… dialog's scenario no longer holds, so the requirement is restated under a new title.
**Migration**: See "Manage skills on REST and on the Skills page"; its other scenarios are unchanged.
