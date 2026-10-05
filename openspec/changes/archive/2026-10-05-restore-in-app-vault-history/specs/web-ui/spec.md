## ADDED Requirements

### Requirement: Show a vault file's history on a History tab
A knowledge document and a managed skill MUST each carry a **History** tab (spec knowledge "Show a collection as one tree of read-only documents in the web UI", spec skill-manager "Manage skills on REST and on the Skills page") that reads the history of the document's file or the skill's master folder in the vault ([vault-storage](../vault-storage/spec.md) "Show and restore any version of a vault file or folder"). It MUST be one bordered card split by a divider: on the left the versions, newest first, under a **Versions** header with their count — each row saying what the version did (Created, Edited, Deleted, a file added, removed or changed, N files changed, or which version a restore put back), who wrote it (You, Edited on disk, an agent by its product name, Coffer, Sync) and when, and the lines it moved — the newest marked **Current** and chosen when the tab opens; on the right the chosen version with its short id, writer and time, and every file it changed under its path, operation and line counts, drawn by the one diff renderer ("Draw every diff in the web UI with one renderer"). A version other than the current one MUST offer a switch between **Changes in this version** (against the version before it) and **Compare with current** (from that version to the path as it is now), and **Restore this version…**, which asks first — saying the result is a new version and, for a folder, that files added since are removed — and on confirmation restores it stating the newest version the tab listed, so a path changed since is refused and the refusal stays in the dialog; the restore never rewrites the past. A history that cannot be read MUST say so in one **Load error** row inside the tab with **Retry**, leaving the rest of the page working; a path with no recorded version says that its versions will be listed there. The divider moves both ways — the list narrows to 160 px and widens to leave the diff 320 px — and its position is remembered per kind. The knowledge document's and the skill's ⋯ menus offer no History… item.

#### Scenario: the history tab lists versions with their writers and restores one
- **GIVEN** a knowledge document the user created, an agent then changed, and the person then edited in their own editor
- **WHEN** the user opens its History tab, chooses the oldest version, compares it with current and chooses Restore this version… and confirms
- **THEN** the tab lists the three versions newest first with their writers and the lines each moved, the newest marked Current and offering no restore, and the chosen version shows its own change and then its difference from the current text
- **AND** the confirmation says the file comes back as a new version, and confirming restores it stating the newest version listed, after which the history is read again

#### Scenario: a history that fails to load says so in its tab
- **GIVEN** the history read failing
- **WHEN** the user opens the History tab and chooses Retry once the read works again
- **THEN** the tab shows one Load error row with Retry, and after Retry it lists the versions

## MODIFIED Requirements

### Requirement: Lay out the Skills page as the canvas draws it
The Skills page MUST follow canvas 4.3: a compact header (title, help) over the
library beside a reading pane. The library MUST group skills under **Needs
attention**, **In use**, **Off** and **Built-in**, without counts in the group
titles; a row MUST show no description (it is on the skill's page) and, as a second
line, only the one thing that needs the reader, and an Off row carries no reach word. The library offers a search, which
applies to the built-in skills too, and a reach filter — all skills, or the skills
that reach one chosen agent — but no filter by kind. Rows ticked
for bulk actions MUST show the selection as a bar above the list ("N of M
selected", Reach, Delete, ×) and in the reading pane, which names the selected
skills, says the built-in skill can't be selected and offers only what the bar does
not — **Check copies of N skills**.

The open skill's header MUST name it with a state pill, its source, its master
path and when it changed, and carry **Reach** and a **⋯** menu (Open in editor,
Reveal in Finder, Copy master path, Delete…) whatever the state; each problem is
answered in a banner under the tabs, never in the header. Its tabs — Files,
Delivery, Requires, History — carry no counts. The Files tab MUST be one card: the
folder's files with SKILL.md first beside the open file's header bar and body,
read-only, with Open in editor and Reveal in Finder on the header bar and no Edit. A folder the skills
store holds that no skill claims, listed under Not in your library, MUST show its
files in the same locked tree and viewer, with its meta line saying how many files
it holds and when it was found.

The Requires tab MUST list what the skill declares in four groups: **Commands**,
each with its state and a link to the CLIs page, **Secrets** (spec skill-manager
"Declare the secrets a skill requires"), **Tools** — the MCP servers and
custom-tool groups it names under `requires: tools:` (spec skill-manager "Declare
the tools a skill requires"), each with its state and a link to its page — and
**Skills** it needs. A row's name is shown in full, never cut short: a group's
name column is as wide as its longest name. **Check again** re-checks the commands. The rows carry no
install, copy-command or login step and no hand-off of their own: one banner
carries a single hand-off to an agent for every command that needs the person. A
secret that is not set MUST read "secret <name> is not set" and open the Secrets
page, with no hand-off to an agent, because setting a secret is the person's task.
A library row whose most urgent item is such a secret MUST read "Needs secret
<name> · not set", and the open skill MUST carry a banner naming each secret that
is not set with Open Secrets. A required tool that is off or failing puts the skill
under Needs attention with "Needs <tool> · off", a **Tool off** pill, and a banner
("<tool> is off, so <skill> can't call it", or why a failing group fails) with Open
<tool>, which opens the tool's own page; turning a tool on is the person's choice,
so the banner offers no hand-off.

A folder in the way of an agent's link, a delete Coffer refuses, a master folder
that is gone and a Git source to change MUST each be answered where they are
shown, with the choice confirmed before anything is written. When a delete is
refused because an agent's copy is a real folder Coffer did not make, the
confirmation MUST stay open, say "Nothing was deleted", name the folder and say
Coffer removes only what it made; its primary button then becomes **Delete, keep
<agent>'s folder**, which deletes the skill and leaves that folder where it is
(there is no Retry). A bulk delete MUST report each skill: the clean ones are
deleted, a refused one stays listed with the folder in the way, and the same
choice to keep that agent's folder is offered. The Add skill dialog is 640 wide,
validates its source inline and MUST carry the Available to reach control.

#### Scenario: a library row says what needs attention in place of its description
- **GIVEN** a skill whose declared command is missing and a Git skill with an update waiting
- **WHEN** the user opens the Skills page
- **THEN** the first row reads "Needs <command> · not installed" and the second "Update available" under their names, and a row with nothing to say shows its name alone

#### Scenario: selected skills are set or deleted together from the bar above the list
- **GIVEN** the built-in skill and two of the user's skills
- **WHEN** the user ticks the two skills
- **THEN** the bar above the list reads "2 skills selected", the reading pane names both, says the built-in skill can't be selected and offers Check copies of 2 skills, and the one Delete button deletes both after one confirmation

#### Scenario: the library filters by reach and groups skills by what they need
- **GIVEN** a skill that is on for every agent, one that is off and one limited to Claude Code
- **WHEN** the user opens the Skills page and chooses Codex in the Reach filter
- **THEN** the skills first sit under In use and Off, the list offers a search and a Reach filter but no kind filter, and with Codex chosen only the skill on for every agent is listed and the address carries `?agent=<Codex's uid>`

#### Scenario: a skill file is read-only in the Files tab
- **GIVEN** a skill whose folder holds `SKILL.md` and a script
- **WHEN** the user opens the script in the Files tab
- **THEN** its header bar offers Open in editor and Reveal in Finder, its body is read-only, and there is no Edit, Save or Not saved state

#### Scenario: the requires tab checks the commands again and keeps the hand-off out of its rows
- **GIVEN** a skill whose declared commands are missing or not logged in
- **WHEN** the user opens its Requires tab and chooses Check again
- **THEN** each command shows its state with a link to its CLI page, no install, Copy prompt or login step appears in a row, and every command is probed again

#### Scenario: a folder in the way of a skill's link is resolved by a confirmed choice
- **GIVEN** a skill whose link in one agent is a real folder Coffer did not make
- **WHEN** the user opens Review… from the skill's banner and chooses Adopt this folder
- **THEN** the dialog shows the difference first, and only the confirm button resolves that agent's copy by keeping its version

#### Scenario: a delete refused because a copy is not Coffer's stays open and offers to keep that folder
- **GIVEN** a skill whose delete the daemon refuses because an agent's copy is not Coffer's link
- **WHEN** the user confirms the delete
- **THEN** the dialog stays open, says "Nothing was deleted", names the folder and says Coffer only removes what it made
- **AND** its primary button becomes "Delete, keep Codex's folder", which deletes the skill and leaves that folder

#### Scenario: a bulk delete offers to keep the folder that stopped one skill
- **GIVEN** two selected skills of which one has a real folder in an agent where its link should be
- **WHEN** the user confirms the bulk delete
- **THEN** the dialog stays open listing the refused skill with the folder, and offers to delete it keeping that agent's folder

#### Scenario: a skill whose master folder is gone offers the ways forward
- **GIVEN** a skill whose master folder was removed outside Coffer
- **WHEN** the user opens it
- **THEN** its header pill says Master missing and a banner says the master folder is gone and offers the hand-off that looks for a copy to restore (spec skill-manager "Hand unsettled skill drift to an agent with a prompt") and Delete skill…, which opens the delete confirmation
- **AND** the Files tab says there are no files to show

#### Scenario: a folder no skill claims is added in place or moved out
- **GIVEN** a folder in the skills store that no skill claims
- **WHEN** the user opens it under Not in your library
- **THEN** it shows its path, whether its SKILL.md is valid and its file count, Delete folder… asks first, and Add to library… adds it and opens the new skill

#### Scenario: changing a skill's source shows the change before anything is replaced
- **GIVEN** a skill added from Git
- **WHEN** the user opens Change source…, enters another repository and chooses Check source
- **THEN** the dialog lists the names of the files that would change, with no diff, and a button to take it, and cancelling applies nothing and drops the staged source

#### Scenario: a skill is added with the reach chosen in the dialog
- **GIVEN** the Add skill dialog with Available to set to Disabled or to chosen agents
- **WHEN** the user adds the skill
- **THEN** each added skill is turned off, or scoped to the chosen agents, and with every agent nothing more is written

#### Scenario: the requires tab lists a skill's secrets and opens Secrets for a missing one
- **GIVEN** a skill declaring the command `jq` and the secrets `GITHUB_TOKEN`, which is set, and `NPM_TOKEN`, which is not
- **WHEN** the user opens its Requires tab
- **THEN** below the commands `GITHUB_TOKEN` reads Set and `NPM_TOKEN` reads "secret NPM_TOKEN is not set" with Open Secrets, which opens `/secrets`
- **AND** the secrets offer no Copy prompt and no command

#### Scenario: a skill that needs a secret that is not set says so and links to Secrets
- **GIVEN** a skill declaring `GITHUB_TOKEN`, which is not set, and `NPM_TOKEN`, which is
- **WHEN** the user opens the Skills page and the skill
- **THEN** its library row reads "Needs secret GITHUB_TOKEN · not set"
- **AND** a banner above its tabs says "secret GITHUB_TOKEN is not set." with Open Secrets linking to `/secrets`, and does not name `NPM_TOKEN`

#### Scenario: a skill whose tool is off says so in the list, the pill and a banner that opens the tool
- **GIVEN** a skill declaring the tool `github`, an MCP server that is off
- **WHEN** the user opens the Skills page and the skill
- **THEN** the row reads "Needs github · off" under Needs attention, the header pill reads Tool off, and a banner says github is off so the skill can't call it, with Open github linking to `/mcp-servers/github`
- **AND** the banner offers no Copy prompt or Ask an agent

### Requirement: Draw every diff in the web UI with one renderer
Every diff the web UI shows of a file's changed lines — a change preview of a write Coffer is about to make, a version on a History tab, a skill's copy or folder-in-the-way review, and a custom-tool group's re-import — MUST be drawn by one renderer: old and new line numbers, a sign, additions and deletions on their colour, hunk headers muted, and a long line wrapped at a word boundary with a ↳ on its continuation rows, never cut off. Each file is shown under its path, operation and line counts.

#### Scenario: a long changed line wraps instead of being cut off
- **GIVEN** a change preview whose file adds a line longer than the diff is wide
- **WHEN** the diff renders
- **THEN** the line shows its old and new line numbers and its sign, and wraps at a word boundary with a ↳ on the continuation row

## REMOVED Requirements

### Requirement: Show where a file's history is and hand its restore to an agent
**Reason**: A document's and a skill's history are shown on a History tab, and Coffer restores a version itself, so the dialog that only named the path and handed the restore to an agent has nothing left to do.
**Migration**: Open the document's or the skill's History tab ("Show a vault file's history on a History tab").
