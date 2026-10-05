## ADDED Requirements

### Requirement: Cover skill management on REST and on the Skills page
Every management operation of a skill (import, update, remove, enable, disable, scope, verify) MUST be available through (a) the REST API and (b) the Skills page in the web UI; the command line carries no skill command. The REST routes are `GET /api/v1/skills` and `GET /api/v1/skills/{uid}` to read, the imports of "Import a skill from a local path", "Add skills from an archive" and "Add skills from a Git repository" (`POST /api/v1/skills/import` and `/stage/*`), the updates of "Update a Git-imported skill from its source" (`/api/v1/skills/{uid}/source/*`), `DELETE /api/v1/skills/{uid}`, the resource update route for `enabled` and `scope`, and `POST /skills/verify` for the drift report. Three repair operations are the web UI's and REST's alone: adopting or removing an orphan master folder (`/skills/orphans*`), resolving a copy an agent holds (`/skills/copies/{agent}/resolve`) and changing a Git-imported skill's source (`/skills/{name}/source/change`); the drift report names an orphan and what to do about it. `enable` and `disable` switch the skill resource's own `enabled` flag, which with its scope drives delivery ("Deliver a skill only where it is enabled and in scope"); there is no per-(skill, agent) switch on any surface, and the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes do not exist. There is no edit operation: a skill's name is fixed, it has no title, and its description is its SKILL.md's, edited in the file.

A skill's master folder is plain files a person edits in their own editor. Its absolute path is shown on the skill's page (**Copy master path**) and in the REST file tree, and it is read and edited on disk; the command line carries no command that lists, prints or writes a file inside it. The REST file tree and file read ("Show a skill's master folder read-only") serve the web UI's Files tab and programmatic clients; nothing in Coffer writes a file inside the folder on the person's behalf.

The Skills page is the library of managed skills beside the open skill: a list with search, an All / On / Off filter and row multi-select for bulk reach and bulk delete, next to the selected skill's detail. It has one **Add skill** action whose dialog offers three sources: **Folder** — a path field that takes a folder chosen with the folder picker or a path typed or pasted into it, trimmed of surrounding whitespace and quotes before it is sent; **Archive** — a `.zip` or `.skill` file uploaded from the browser; and **Git repository** — a URL with an optional ref and subpath; under the source, an **Available to** reach control whose choice every added skill takes (every agent unless narrowed). Each source first shows what it found — the skill or skills, their names and descriptions, any that cannot be added and why, and any whose name is taken, with Replace offered for those — and writes nothing until the user confirms. The dialog offers no way to create a new skill from scratch: a skill is authored in the user's own editor and added from where it lives. It shows each skill by its name, which it offers no way to edit. It lists only the skills Coffer manages: an agent's own (unmanaged) skills, and adopting them, live only on that agent's Skills tab (see "Expose unmanaged-skill operations on REST and the web"), and while no skill is managed the page's empty state may link to the agents' Skills tabs but lists nothing from them. It manages the skill resource itself, not per-agent bindings. A row carries a Built-in mark and an Off mark, and in place of its description the one thing that needs the reader, most urgent first: its master folder is gone ("Say when a skill's master folder is gone"), a folder is in the way of an agent's link ("Resolve a folder in the way of a skill's link"), a command it declares is missing, not logged in or too old, its Git source is unreachable, or an update is waiting ("Update a Git-imported skill from its source"). Folders in the skills store that no skill claims are listed apart, under **Not in your library** ("Act on a folder in the skills store that no skill claims"). A skill's detail (`/skills/<name>`, addressed by its fixed name as [web-ui](../web-ui/spec.md) "Lay out every detail page's tabs alike" says) shows its name, reach, a **⋯** menu — Open in editor, Reveal in Finder, Copy master path, History… (not on a builtin skill), Check agents' copies, Turn off, and Delete… (disabled on a builtin skill) — its description, and its master path or, for a Git skill, its repository, folder and pinned commit; above its tabs, a banner for each thing that needs the reader, with at most one action; and it has three tabs, in this order, each at its own path:

- **Files** (the default, `/skills/<name>`) — the file tree beside the read-only viewer of "Show a skill's master folder read-only", opening with `SKILL.md` selected and rendered; a **Preview / Source** toggle switches a Markdown file between rendered and raw text. A text file offers **Open in editor**, a binary file **Open in default app**, and both **Reveal in Finder**; a file too large to read whole shows its start. The tab edits nothing: a file is changed in the person's own editor. There is no separate SKILL.md tab.
- **Delivery** (`/skills/<name>/delivery`) — every registered agent with the state of its copy: linked, copied where links are not allowed ("Fall back to copying where links are unavailable"), differing from master (the drift kinds of "Report skill drift on request" — a folder in the way offers **Review…**), or not delivered and why (the skill is off or the agent is outside its reach); **Check again** runs the drift report afresh.
- **Requires** (`/skills/<name>/requires`) — the commands the skill declares it needs ("Show the commands a skill declares it needs"), each with its state on this machine and opening that command's page on the CLIs page ([web-ui](../web-ui/spec.md) "Show every CLI a skill requires on the CLIs page"); the tab offers nothing that installs or logs in — those live on the CLIs page.
The skill's **⋯** menu also holds **History…**, the dialog of [web-ui](../web-ui/spec.md) "Show where a file's history is and hand its restore to an agent" over the master folder (`skills/<name>/` in the vault): it names the folder, copies the `git log` command, reveals the folder and hands restoring an earlier version to the person's agent ([vault-storage](../vault-storage/spec.md) "Hand restoring an earlier version of a vault file to an agent"). Coffer's own builtin skill is not in the vault and offers no History….

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
- **THEN** the tabs read Files, Delivery and Requires, Files is selected with `SKILL.md` selected and rendered, and there is no SKILL.md tab
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

#### Scenario: a skill's history is handed to git and an agent
- **GIVEN** an imported skill and the builtin `coffer-guide` skill
- **WHEN** the user opens the imported skill's ⋯ menu and chooses History…, and then opens the builtin skill's ⋯ menu
- **THEN** the dialog names `skills/<name>/` in the vault and offers Copy git command, Reveal in Finder and the hand-off, and the skill has no History tab
- **AND** the builtin skill's menu offers no History…

## MODIFIED Requirements

### Requirement: Expose unmanaged-skill operations on REST and the web
Unmanaged-skill operations MUST be available through the REST API (`GET`, `POST .../adopt` and `DELETE` under `/api/v1/agents/{uid}/unmanaged-skills`) and through the agent's Skills tab in the web UI; the command line carries no unmanaged-skill command. Delivery itself is not an operation on this surface: it is controlled by the skill resource's `enabled` flag and `scope` through the resource routes and the Skills page. The agent detail page decides nothing about delivery: its Skills tab opens with one **From Coffer** row — how many skills Coffer delivers to that agent, their first names, and **Open Skills ›**, a link to the Skills page narrowed to that agent — and then lists the unmanaged skills found on that agent's disk (see [agent-registry](../agent-registry/spec.md) "Show what Coffer manages for an agent in one row"). The Skills page accepts an `agent` query parameter, `/skills?agent=<uid>`, and then lists only the managed skills that reach that agent, with the agent named in a filter beside the search. The agent's Skills tab is the only web surface that lists unmanaged skills or adopts them, one at a time or several at once (see [agent-registry](../agent-registry/spec.md) "Act on several of an agent's own items at once"); the Skills page lists managed skills only (see "Cover skill management on REST and on the Skills page").

#### Scenario: list, adopt and delete an unmanaged skill
- **GIVEN** a registered agent with two hand-placed skill folders in its skills directory
- **WHEN** the user lists `GET /api/v1/agents/{uid}/unmanaged-skills`, then adopts one with `POST .../unmanaged-skills/{skill}/adopt`, then deletes the other with `DELETE .../unmanaged-skills/{skill}` and confirms it
- **THEN** the list names both folders, the first becomes a managed skill and leaves the next list, and the second is removed from disk
- **AND** the command line offers no command that lists, adopts or deletes an unmanaged skill

#### Scenario: unmanaged skills are adopted only from the agent's Skills tab
- **GIVEN** an agent with a hand-placed skill folder
- **WHEN** the user looks for it in the web UI
- **THEN** the agent's Skills tab lists it as the agent's own, with Adopt, and the Skills page does not list it

### Requirement: Show a skill's master folder read-only
The system MUST expose over REST a **read-only** view of a skill's master folder, which the web UI's Files tab renders: a recursive file tree (name, folder-relative path, absolute on-disk path, type, size, children) and the contents of an individual file (with its absolute on-disk path and containing folder's absolute path). Markdown files render as formatted Markdown; other text files show raw. Reads MUST be contained to the master folder — any path that resolves outside it (`..` traversal, absolute path, or escaping symlink) MUST be rejected. File reads MUST be size-capped (truncating with a `truncated` flag) and MUST flag non-UTF-8 / NUL-containing files as binary with empty content. No symlink-following out of the folder. The folder's absolute path is shown on the skill's page (**Copy master path**), and the folder is edited on disk, in the person's own editor (see "Cover skill management on REST and on the Skills page"); no route writes a file inside it.

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


### Requirement: Hand unsettled skill drift to an agent with a prompt
The three drift kinds no pass settles — a folder Coffer did not make at a skill's link path, a folder in the skills store no skill owns, and a skill whose master folder is gone — MUST each carry a hand-off prompt (Principle IV, AI-Native) built from the finding alone, the same text on the drift report entry (`handoff` on `POST /skills/verify` and `POST /skills/repair`) and on the finding's attention item: for a folder in the way, compare it with the skill's master folder, say whether it holds edits worth keeping, and recommend **Adopt this folder** or **Replace it with Coffer's link**; for a folder no skill owns, say what it is and whether its `SKILL.md` names it, and recommend **Add to library** or **Delete folder**; for a missing master, look for a copy that can be restored (the folders Coffer set aside under `~/.coffer/content/backup/skills/`, a copied copy in an agent's skills folder, the skill's source, and the master folder's own versions in the vault's git history) and, once the person agrees, copy it back to where the master belongs. The prompts MUST tell the agent to move, delete or edit no folder itself except that one agreed copy; the choice stays the button the person presses, and the buttons stay (Check again, Repair, the two choices of "Resolve a folder in the way of a skill's link", Add to library and Delete folder, Remove the skill). The Skills page MUST offer Copy prompt and, where a managed agent is available, Ask an agent beside each such finding, in the compare of a folder in the way, on the pane of a folder no skill owns and on the Files tab of a skill whose master is gone. A missing or tampered link carries a `null` `handoff`: Repair is its fix. The attention items' reasons for these kinds MUST name no command to run.

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


## REMOVED Requirements

### Requirement: Save an existing skill file conditionally
**Reason**: Coffer is not a second editor (principles, What Coffer is not › Not a second agent). A skill's master folder is plain files the person edits in their own editor and an agent with its own file tools; the vault commits each edit found on disk.
**Migration**: Open the file from the Files tab (Open in editor). `PUT /api/v1/skills/{uid}/files/content`, the read's `fingerprint` and `SKILL_FILE_STALE` are removed.

### Requirement: Cover skill management on REST and the web
**Reason**: The Files tab no longer edits, and the History tab with its version list and restore is removed; version browsing is git's and an agent's.
**Migration**: See "Cover skill management on REST and on the Skills page". The skill's ⋯ menu's History… hands a restore to the agent.
