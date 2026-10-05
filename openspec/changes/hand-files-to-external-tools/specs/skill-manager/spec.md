## ADDED Requirements

### Requirement: Hand a Git-imported skill's update to an agent
A skill with a `git_import` source MUST be checked for newer commits on its ref — on demand, from a **Check for updates** action on the skill's page (`POST /api/v1/skills/{uid}/source/check`), and periodically, every six hours — by fetching the repository with this machine's `git` into a staging area; a check writes nothing to the master store and its result is kept on this machine only. When the ref has moved past the pinned commit with commits that change the skill's folder, the skill MUST show **Update available** on the Skills page and its detail page, with the commit range from the pinned commit to the new one. A source that cannot be fetched MUST be reported on the skill with git's message and the time of the last successful check, and changes nothing.

Coffer MUST NOT apply an update itself: there is no preview of the update's files, no apply, no Keep mine / Take theirs / Compare and no merge of its own. While an update is available, and only then, the skill MUST offer one primary action, **Hand off to <Agent> to update** — the hand-off split button of [web-ui](../web-ui/spec.md) "Hand a machine-dependent problem to an agent with one split button", which starts the default agent in the preferred terminal with the prompt sent, its menu holding the other installed agent and Copy prompt — whether or not the folder has local edits, with **I merged it** beside it ("Record an update merged into local edits"). `POST /api/v1/skills/{uid}/source/handoff` MUST answer the newest commit and the prompt (Principle IV, AI-Native), built by the daemon from the same module every hand-off uses: the skill's name; its master folder as the only place to edit; the pinned commit and the upstream commit with the subjects of the commits between them; the repository (without any credential in its URL), ref and folder to read upstream from, read-only; the files edited in the master folder since the pinned commit, or that there are none; to bring the new commit's content into the master folder keeping the local edits, asking the person where the two really disagree, and to show the person the diff; and that the person records the merge in Coffer when it is done, so the agent never calls that route itself. Building the prompt fetches upstream into a staging area that is removed again, and writes nothing to the master store or the pin. With no update available the route MUST be refused `409 SKILL_UPDATE_NOT_PENDING`.

#### Scenario: a newer commit shows update available
- **GIVEN** a skill pinned to commit `a1` of `main`, and `main` now at `c3` with commits that change the skill's folder
- **WHEN** the periodic check runs, or the user chooses Check for updates
- **THEN** the skill shows Update available with the range `a1..c3` on the Skills page and its detail page
- **AND** nothing under `~/.coffer/vault/skills/` has changed

#### Scenario: an unreachable source is reported and changes nothing
- **GIVEN** a Git-imported skill whose repository can no longer be fetched
- **WHEN** the user chooses Check for updates
- **THEN** the skill shows git's message and the time of its last successful check
- **AND** the folder and the pin are unchanged

#### Scenario: the update hand-off names the commits, the local edits and the read-only source
- **GIVEN** a skill pinned to `a1` whose `notes.txt` the user edited, and `main` at `c3` with a commit that changes the skill's folder
- **WHEN** the update hand-off is read
- **THEN** the prompt names the skill, the master folder as the only place to edit, `a1` and `c3` with the commit's subject, the repository, ref and folder to read upstream from with no credential in the URL, and `notes.txt` as a local edit, and tells the agent to keep the local edits, show the diff and leave recording the merge to the person
- **AND** for a skill with no local edit the prompt says there are none, and nothing on disk or in the pin has changed either way

#### Scenario: the update is offered only as a hand-off while an update is available
- **GIVEN** a skill showing Update available and a skill that is up to date
- **WHEN** the user opens each skill's page
- **THEN** the first offers Hand off to <Agent> to update and I merged it, and no preview, apply, Keep mine, Take theirs or Compare
- **AND** the second offers neither, and its update hand-off over REST is refused `409 SKILL_UPDATE_NOT_PENDING`

### Requirement: Cover skill management on REST and on the Skills page
Every management operation of a skill (import, update, remove, enable, disable, scope, verify) MUST be available through (a) the REST API and (b) the Skills page in the web UI; the command line carries no skill command. The REST routes are `GET /api/v1/skills` and `GET /api/v1/skills/{uid}` to read, the imports of "Import a skill from a local path", "Add skills from an archive" and "Add skills from a Git repository" (`POST /api/v1/skills/import` and `/stage/*`), the update check, hand-off and merge record of "Hand a Git-imported skill's update to an agent" and the source change (`/api/v1/skills/{uid}/source/*`), `DELETE /api/v1/skills/{uid}`, the resource update route for `enabled` and `scope`, and `POST /skills/verify` for the drift report. Three repair operations are the web UI's and REST's alone: adopting or removing an orphan master folder (`/skills/orphans*`), resolving a copy an agent holds (`/skills/copies/{agent}/resolve`) and changing a Git-imported skill's source (`/skills/{name}/source/change`); the drift report names an orphan and what to do about it. `enable` and `disable` switch the skill resource's own `enabled` flag, which with its scope drives delivery ("Deliver a skill only where it is enabled and in scope"); there is no per-(skill, agent) switch on any surface, and the `POST /skills/{name}/enable` and `POST /skills/{name}/disable` routes do not exist. There is no edit operation: a skill's name is fixed, it has no title, and its description is its SKILL.md's, edited in the file.

A skill's master folder is plain files a person edits in their own editor. Its absolute path is shown on the skill's page (**Copy master path**) and in the REST file tree, and it is read and edited on disk; the command line carries no command that lists, prints or writes a file inside it. The REST file tree and file read ("Show a skill's master folder read-only") serve the web UI's Files tab and programmatic clients; nothing in Coffer writes a file inside the folder on the person's behalf.

The Skills page is the library of managed skills beside the open skill: a list with search, an All / On / Off filter and row multi-select for bulk reach and bulk delete, next to the selected skill's detail. It has one **Add skill** action whose dialog offers three sources: **Folder** — a path field that takes a folder chosen with the folder picker or a path typed or pasted into it, trimmed of surrounding whitespace and quotes before it is sent; **Archive** — a `.zip` or `.skill` file uploaded from the browser; and **Git repository** — a URL with an optional ref and subpath; under the source, an **Available to** reach control whose choice every added skill takes (every agent unless narrowed). Each source first shows what it found — the skill or skills, their names and descriptions, any that cannot be added and why, and any whose name is taken, with Replace offered for those — and writes nothing until the user confirms. The dialog offers no way to create a new skill from scratch: a skill is authored in the user's own editor and added from where it lives. It shows each skill by its name, which it offers no way to edit. It lists only the skills Coffer manages: an agent's own (unmanaged) skills, and adopting them, live only on that agent's Skills tab (see "Expose unmanaged-skill operations on REST and the web"), and while no skill is managed the page's empty state may link to the agents' Skills tabs but lists nothing from them. It manages the skill resource itself, not per-agent bindings. A row carries a Built-in mark and an Off mark, and in place of its description the one thing that needs the reader, most urgent first: its master folder is gone ("Say when a skill's master folder is gone"), a folder is in the way of an agent's link ("Resolve a folder in the way of a skill's link"), a command it declares is missing, not logged in or too old, its Git source is unreachable, or an update is waiting ("Hand a Git-imported skill's update to an agent"). Folders in the skills store that no skill claims are listed apart, under **Not in your library** ("Act on a folder in the skills store that no skill claims"). A skill's detail (`/skills/<name>`, addressed by its fixed name as [web-ui](../web-ui/spec.md) "Lay out every detail page's tabs alike" says) shows its name, reach, a **⋯** menu — Open in editor, Reveal in Finder, Copy master path, History… (not on a builtin skill), Check agents' copies, Turn off, and Delete… (disabled on a builtin skill) — its description, and its master path or, for a Git skill, its repository, folder and pinned commit; above its tabs, a banner for each thing that needs the reader, with at most one action; and it has three tabs, in this order, each at its own path:

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

### Requirement: Add skills from a Git repository
Users MUST be able to add skills from a Git repository given its URL, an optional ref (branch, tag or commit; the default branch when omitted) and an optional subpath — in the Add skill dialog, or by staging it with `POST /api/v1/skills/stage/git`. A GitHub folder address (`https://github.com/<owner>/<repo>/tree/<ref>/<path>`) is read as the repository, the ref and the subpath. The system MUST fetch the repository with this machine's own `git` into a staging area, resolve the ref to one commit, and find skills under the subpath by the rule archives use (a `SKILL.md` at the subpath's top or one folder down), offering a choice when there are several. Git runs with no prompt and no secret Coffer supplies: a repository URL MUST NOT carry a user name or password (an `ssh://git@host/…` user name is allowed; a token or password in the URL is refused, because the URL is stored in the vault, in the skill's metadata and in API answers), and a repository is reachable when it is public or when this machine's git already holds a credential for it (its credential helper or SSH keys), and Coffer stores none. Only the `https`, `http`, `ssh`, `git` and `file` transports are allowed, and submodules are not fetched. Symlinks that leave the skill folder, and a checkout of the subpath past the 50 MB skill cap, MUST be rejected before anything is written. A chosen skill is validated, named and confirmed as an archive's is, and is recorded with a `git_import` source pinned to the commit it was copied from and the content hash of its folder there. It stays pinned to that commit until the person records a newer one after their agent brought it in ("Hand a Git-imported skill's update to an agent", "Record an update merged into local edits"), or changes its source. A repository that cannot be fetched, a ref that names no commit and a subpath the commit does not hold MUST each be reported with git's own message, and nothing is written. When this machine has no `git`, staging MUST be refused `SKILL_SOURCE_UNREACHABLE` whose details carry `reason: "git_missing"` and `handoff`, a prompt (Principle IV, AI-Native) asking the person's agent to install git on this machine — naming its OS and architecture — and to confirm with `git --version`, naming no install command; the add dialog MUST offer it beside the refusal, as the change-source dialog and the update check do beside theirs.

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


### Requirement: Import a skill from a local path
The system MUST support importing a skill from a local filesystem path; the original source path is recorded for provenance but is not retained as a live dependency. Re-importing a name that already exists MUST be rejected by default (`conflict`, 409); with an explicit `overwrite` flag (the Add dialog's Replace) the existing skill is replaced in place — the master folder content is swapped atomically, its `version_hash` and `last_synced_from_source_at` are refreshed, and its per-agent bindings and delivered symlinks are preserved (the master folder name is unchanged). For a skill added from a folder or an archive, re-import overwrite is the only update mechanism (there is no live source to re-fetch); a skill added from a Git repository is updated from its source instead, by the person's agent (see "Hand a Git-imported skill's update to an agent"). The replacement is audited as an update. On a name collision the user either renames via SKILL.md frontmatter and retries, or re-imports with `overwrite`. A folder added from the web UI is looked at before anything is copied, as an archive is ("Add skills from an archive"): the dialog shows the skill it found, or the skills one folder down when the folder itself holds no `SKILL.md`, and copies nothing until the user confirms. `POST /api/v1/skills/import` imports at once, since naming the folder in the request is the confirmation.

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

#### Scenario: a folder whose skill is one folder down names that folder when it cannot be added
- **GIVEN** a folder with no `SKILL.md` at its top whose only `SKILL.md` is in the sub-folder `skill/`, and that skill cannot be added (a link inside it leaves the folder)
- **WHEN** the user stages the folder
- **THEN** the stage is refused with the sub-folder skill's own reason and `details.candidate_folder` `skill` (with its absolute path as `details.candidate_path`), so the dialog can offer that folder as the one to add


### Requirement: Record an update merged into local edits
After a Git-imported skill's master folder has taken an upstream update (by the person's agent, per the hand-off of "Hand a Git-imported skill's update to an agent", whether or not it had local edits), the person MUST be able to record it — **I merged it** beside the hand-off, confirmed first; `POST /api/v1/skills/{uid}/source/merged` with the upstream `commit`. Recording MUST move the pin to that commit and MUST NOT touch the master folder's files; the pin's content hash becomes that commit's own content, so a folder that kept local edits still counts as locally edited against its new base and the next update's hand-off lists exactly the edits carried over. The update is no longer offered, and the recording is audited as `skill_update_merged` with the old and the new commit. The commit MUST be an update waiting for the skill — the ref's newest commit or one of the commits between the pin and it that change the skill's folder, given in full or by a unique prefix of at least seven characters — and anything else (no newer commit, the pinned commit itself, a commit not on the ref) MUST be refused with `409 SKILL_UPDATE_NOT_PENDING`, changing nothing.

#### Scenario: recording a merge moves the pin and keeps the merged files
- **GIVEN** a skill pinned to `a1` with a local edit, `main` at `c3`, and the master folder merged with `c3` by an agent
- **WHEN** the user chooses I merged it and confirms, or posts `c3` to `POST /api/v1/skills/{uid}/source/merged`
- **THEN** the skill is pinned to `c3`, the master folder's files are exactly as the merge left them, `c3` is no longer offered, and the recording is audited as `skill_update_merged` from `a1` to `c3`
- **AND** when `main` moves on again the update's hand-off lists only the edit carried over as a local edit

#### Scenario: recording a merge refuses a commit that is not the update
- **GIVEN** a skill pinned to `a1`
- **WHEN** a merge is recorded against `a1` itself, against a commit that is not on the ref, or while the ref has nothing newer
- **THEN** it is refused with `409 SKILL_UPDATE_NOT_PENDING`, the pin stays at `a1`, and nothing is audited


### Requirement: Change a Git-imported skill's source
The system MUST let the user move a Git-imported skill to another repository, ref or folder (`POST /skills/{uid}/source/change` with `url`, `ref` and `path`) without replacing anything first: the new source is staged the way an add from Git is, must hold one valid skill with the skill's fixed name, and the answer carries the stage, the new commit and the names of the files that would be added, removed or changed against the skill's current folder — names only, no diff. Confirming it (`POST /skills/{uid}/source/change/apply` with that stage) swaps the folder in atomically, keeps the skill's reach and delivered links, records the new source pinned to the new commit and is audited as an update; cancelling the stage (`DELETE /skills/stage/{staging_id}`) leaves the skill and its source as they were. A stage that is gone, or belongs to another skill, is refused and changes nothing.

#### Scenario: a new source is shown against the current version first
- **GIVEN** a skill added from one repository
- **WHEN** the user changes its source to a folder of another repository and then applies the preview
- **THEN** the answer lists the names of the files that differ from the current folder, with no diff, while the folder is still unchanged, and after applying the folder holds the new source's files and the skill records the new repository, folder and commit


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

### Requirement: Update a Git-imported skill from its source
**Reason**: Coffer is not a second agent (principles, What Coffer is not; IV. AI-Native lists merging a skill's upstream update with local edits as a hand-off). The update preview, the apply, the conflict's Keep mine / Take theirs / Compare and Coffer's own merge redid what the person's agent does better. Coffer keeps what is its own: where the skill came from, the commit it is pinned to, and whether upstream has a newer one.
**Migration**: See "Hand a Git-imported skill's update to an agent" and "Record an update merged into local edits". `POST /api/v1/skills/{uid}/source/preview`, `GET /source/compare`, `POST /source/keep` and the update use of `POST /source/apply` are removed; changing the source confirms with `POST /source/change/apply`. A skill that a previous version told to skip an update (Keep mine) offers that update again.
