## ADDED Requirements

### Requirement: Draw every diff in the web UI with one renderer
Every diff the web UI shows of a file's changed lines — a change preview of a write Coffer is about to make, a skill's copy or folder-in-the-way review, and a custom-tool group's re-import — MUST be drawn by one renderer: old and new line numbers, a sign, additions and deletions on their colour, hunk headers muted, and a long line wrapped at a word boundary with a ↳ on its continuation rows, never cut off. Each file is shown under its path, operation and line counts.

#### Scenario: a long changed line wraps instead of being cut off
- **GIVEN** a change preview whose file adds a line longer than the diff is wide
- **WHEN** the diff renders
- **THEN** the line shows its old and new line numbers and its sign, and wraps at a word boundary with a ↳ on the continuation row

### Requirement: Show where a file's history is and hand its restore to an agent
A knowledge document's ⋯ menu and a managed skill's ⋯ menu (not the builtin skill's) MUST offer **History…**, which opens one dialog over the page: the path of the document or the skill's folder in the vault, an optional date and time to restore to, **Copy git command** — the `git -C <vault> log -p -- <path>` the daemon serves — **Reveal in Finder**, and the hand-off split button of "Hand a machine-dependent problem to an agent with one split button", labelled **Hand off to <Agent> to restore**, whose prompt is the one [vault-storage](../vault-storage/spec.md) "Hand restoring an earlier version of a vault file to an agent" builds for that path and time. The dialog MUST NOT list versions, show a diff or restore anything itself, and the page assembles no prompt of its own.

#### Scenario: a document's history dialog copies the git command and hands the restore off
- **GIVEN** a knowledge document open in its collection
- **WHEN** the user chooses History… from its ⋯ menu, picks a time and presses the hand-off
- **THEN** the dialog shows the document's path in the vault, Copy git command copies the served `git log` command, and the hand-off starts the agent with the prompt the daemon built for that path and time
- **AND** the dialog lists no versions and offers no Restore of its own

### Requirement: Lay out the Skills page as the canvas draws it
The Skills page MUST follow canvas 4.3: a compact header (title, help) over the
library beside a reading pane. The library MUST group skills under **Needs
attention**, **In use**, **Off** and **Built-in**, without counts in the group
titles; a row MUST show, in place of its description, the one thing that needs the
reader, and an Off row carries no reach word. The library offers a search, which
applies to the built-in skills too, and a reach filter — all skills, or the skills
that reach one chosen agent — but no filter by kind. Rows ticked
for bulk actions MUST show the selection as a bar above the list ("N of M
selected", Reach, Delete, ×) and in the reading pane, which names the selected
skills, says the built-in skill can't be selected and offers only what the bar does
not — **Check copies of N skills**.

The open skill's header MUST name it with a state pill, its source, its master
path and when it changed, and carry **Reach** and a **⋯** menu (Open in editor,
Reveal in Finder, Copy master path, History…, Delete…) whatever the state; each problem is
answered in a banner under the tabs, never in the header. Its tabs — Files,
Delivery, Requires — carry no counts. The Files tab MUST be one card: the
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
- **THEN** the first row reads "Needs <command> · not installed" and the second "Update available" where their descriptions would be

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

## MODIFIED Requirements

### Requirement: Show memory delivery on the Memory page
The Memory page MUST show what each partition delivers, and the agent detail page MUST show only
the delivery hook's state:

- The **Memory page** MUST show no per-agent delivery statistics: it lists the partitions in a table with no section title and a search box that filters the rows by partition name and path, each row carrying the partition's path, its memory count, its sources and its Distilled state (memory "Show a partition's memories read-only").
- A **partition's page** has a **Delivered** tab (see memory "Show a partition's memories read-only")
  showing, read-only, the exact session-start text each agent receives in that partition's project
  (spec [memory](../memory/spec.md) "Deliver the index and the notes path at session start"), with a
  switch between agents. The text is shown as formatted Markdown by default, with a **Rendered** /
  **Raw** toggle: Raw is the exact text, and **Copy** copies the raw text in either mode. In Rendered
  mode each entry's title and file name link to that memory on its partition's page
  (`/memory/<uid>?memory=<slug>`; entries under "Known about you" go to the `global` partition), an
  entry whose partition is unknown stays plain text, and a hint says that editing a memory changes
  what is delivered.
- The delivery hook's state — installed and current, stale, missing, never fired, and Repair — MUST
  appear only on the agent detail page — on its Hooks tab, in the Overview's Coffer connection
  block ([agent-registry](../agent-registry/spec.md) "Show the Coffer connection on the agent pages") and, while the `memory` feature is on, in the **Coffer's memory** section that opens the agent's Memory tab, which links back to this page. Below that section the Memory tab lists the agent's own native memory stores.

#### Scenario: the Memory page shows the partitions with a search and no delivery block
- **GIVEN** two partitions, `coffer` and `global`
- **WHEN** the user opens the Memory page and types `coff` in the search box
- **THEN** the page shows no delivery statistics and no section title above the table, and the table lists only the `coffer` row, with its path, memory count, sources and Distilled state and no sample memory column

#### Scenario: a partition's delivered tab shows each agent's session-start text
- **GIVEN** a partition for the `coffer` repository and both agents connected
- **WHEN** the user opens the partition's Delivered tab and switches from Claude Code to Codex
- **THEN** the tab shows, read-only, the exact session-start text each agent receives in that project
- **AND** the Raw view shows that text exactly, and Copy copies it unchanged

#### Scenario: a delivered entry links to the memory it came from on its partition's page
- **GIVEN** a partition's Delivered tab showing an agent's session-start text in Rendered mode, with entries under "Known about you" and under a repository partition heading
- **WHEN** the user clicks an entry's title or file name
- **THEN** the app opens that memory on its partition's page, global for "Known about you" entries, an entry whose partition is unknown stays plain text, and a hint says that editing a memory changes what is delivered

#### Scenario: hook state appears only on the agent page
- **GIVEN** Claude Code's delivery hook stale
- **WHEN** the user opens the Memory page and then Claude Code's Memory tab
- **THEN** the Memory page shows no hook state or Repair action
- **AND** the Memory tab's Coffer's memory section shows the hook's state with Repair, above Claude Code's own native memory stores

### Requirement: Let the user choose an external editor
The General tab MUST also expose a **preferred external editor**: the
application Coffer uses when the user opens a managed file, or its containing
folder, from a read-only file viewer or file list — a knowledge document, a
memory, a skill file, an agent's config file, a conflicting sync file's copy.
These open in that editor because Coffer edits none of them itself. The default
is the operating system's
default application; the user MAY override it by picking an editor the daemon
detected as installed (enumerated via `GET /api/v1/fs/editors`,
[daemon](../daemon/spec.md) "Open and reveal existing absolute paths"; a browser cannot list installed applications) or by entering
a custom application or launch command. Like the other display preferences the
value is persisted in `localStorage` and never sent to the daemon, except
transiently as the target when opening a file.

#### Scenario: general tab persists the preferred editor
- **GIVEN** the user opens the General settings tab
- **WHEN** they set a preferred external editor (by picking a detected editor or entering a custom launch command)
- **THEN** reloading the page shows the same preferred-editor value
- **AND** clearing the override restores the operating-system default

## REMOVED Requirements

### Requirement: Show the Skills page as the final canvas draws it
**Reason**: The Files tab no longer edits and the History tab is gone, so the stale-save scenario has nothing left to describe.
**Migration**: See "Lay out the Skills page as the canvas draws it".

### Requirement: Guard unsaved edits when leaving a document editor
**Reason**: The web UI holds no document editor any more — skill files, knowledge documents, memories and agent config files are edited in the person's own editor — so there is never an unsaved edit to guard.
**Migration**: None. The "Leave without saving?" dialog and the window-close confirmation are removed.

### Requirement: Show a knowledge document's history on its History tab
**Reason**: Coffer is not a second git client (principles, What Coffer is not › Not a second agent). A document's versions are read with git or by the person's agent.
**Migration**: See "Show where a file's history is and hand its restore to an agent". `/knowledge/<uid>/history` addresses open the document.

### Requirement: Show every version history as one split
**Reason**: Both version histories it laid out are removed. Its rule for drawing a diff stays for the diffs that remain.
**Migration**: See "Draw every diff in the web UI with one renderer".

### Requirement: List recent knowledge changes across collections
**Reason**: The Recent changes timeline is version browsing, which is git's and the agent's. The feed behind it stays only for a delete's Undo.
**Migration**: `git log -- knowledge/` in the vault. The Knowledge page with no collection open shows the collections.

### Requirement: Offer a knowledge refusal's hand-off as one hand-off control
**Reason**: Its two cases — a History tab and Recent changes that need git — are removed with those views.
**Migration**: None. A git that is missing is still reported by the daemon's setup state and the CLIs page.
