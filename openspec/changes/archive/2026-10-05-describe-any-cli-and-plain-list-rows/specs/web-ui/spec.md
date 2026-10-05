## MODIFIED Requirements

### Requirement: Show every CLI a skill requires on the CLIs page
The CLIs page (`/clis`, under Capabilities) MUST list one row per command that
any skill requires or any enabled stdio MCP server starts with (spec
skill-manager "Check every required command where the agent runs"), with the
version found beside the minimum the skills ask for, the login state where the
command has one, and how many MCP servers and skills need it, problems first —
missing, older than the minimum, or not logged in, grouped under Needs attention above
Ready — as a split view with the selected CLI's detail beside the list
(`/clis/<command>`). The detail's Needed by MUST list the MCP servers started
with the command, each opening that server's page and naming its launcher, and
the skills that declare it, each opening that skill's Requires tab; each row
carries its kind when both need it. The app MUST NOT show an install, update or
login command, a "run it in a terminal" instruction, or run any of them: a CLI
that needs the user says what it costs in a plain sentence — which servers can't
start and which skills fail — and its detail page and the skill's Requires tab
MUST offer the daemon's hand-off prompt (spec skill-manager "Hand a required
command to an agent with a prompt") through the hand-off split button of "Hand a machine-dependent problem to an agent with one split button"
— **Hand off to <Agent>** starts the hand-off agent in the preferred terminal with the prompt sent, and **Copy prompt** copies it;
with no managed agent available only Copy prompt is offered. The page's **Check again** probes every command afresh, and the banner that
states a problem re-checks that one tool. Under the header's meta line every CLI —
added by hand or required — carries its description, edited in place (leaving the
field or Enter saves, an empty field clears it; spec skill-manager "Declare a
command-line tool without a skill"). A CLI a person added keeps **Edit** and a
**⋯** menu with **Remove** (a 420-wide confirmation saying the tool stays
installed on this machine); a CLI a skill or MCP server requires has neither, so
its header's right side is empty. **Add CLI** opens a 480-wide form for a command
name or path, which says what Coffer found — where, which version, and whether it
is already added or required — before anything is saved, and keeps a refused
save in the dialog with Retry (see skill-manager "Declare a command-line tool
without a skill"). With nothing required and nothing added the page shows one
empty state with Add CLI and a link to how `requires:` works; `requires:` entries
Coffer skipped are one muted line under the subtitle with a link to Skills. Coffer
reads no command's `--help` and shows no tree of subcommands. A skill's detail page MUST link each requirement it declares to
that CLI's page, and Overview MUST show an attention item while any required CLI
is missing, outdated or not logged in. What a skill declares and how a command
is probed are specified by skill-manager; this page shows what they report.

#### Scenario: the CLIs page lists problems first
- **GIVEN** skills requiring `jq` (not found), `gh` (minimum 2.40, found 2.30.0), `gcloud` (not logged in) and `uv` (found, current)
- **WHEN** the user opens `/clis`
- **THEN** `jq`, `gh` and `gcloud` are listed under Needs attention above `uv` under Ready, `gh` shows 2.30.0 against 2.40, `gcloud` shows not logged in, and each row counts the skills that need it

#### Scenario: a CLI that needs the user offers a prompt for an agent
- **GIVEN** a required CLI that is missing and a Coffer-managed agent
- **WHEN** the user opens its detail page and presses Hand off to <Agent>
- **THEN** the hand-off agent starts in the preferred terminal with the prompt sent
- **AND** the page offers Copy prompt, shows no install command, and with no managed agent available offers only Copy prompt

#### Scenario: check again after logging in
- **GIVEN** a CLI's detail page showing not logged in, with the hand-off to an agent and no login command shown
- **WHEN** the user logs in and chooses Check again
- **THEN** the page probes the command afresh and shows it as logged in

#### Scenario: a CLI an MCP server starts with lists that server
- **GIVEN** `uv` missing, needed by the MCP server `duckdb` (started with `uvx`) and the skill `data-profiling`
- **WHEN** the user opens `/clis/uv`
- **THEN** the list row reads "Not found · duckdb needs it" with "1 server · 1 skill", the header reads "needed by 1 MCP server and 1 skill", and the banner says duckdb can't start and data-profiling fails at the step that calls uv
- **AND** Needed by lists `duckdb` (MCP server, "starts with uvx") opening `/mcp-servers/duckdb` and `data-profiling` (Skill) opening its Requires tab

#### Scenario: a CLI added by hand has Edit and Remove, a required one has neither
- **GIVEN** `demo` added by hand and `uv` required by a skill
- **WHEN** the user opens each one's page
- **THEN** `demo` shows Edit and a ⋯ menu whose Remove asks "Remove demo?" and says the tool stays installed, and `uv` shows neither

#### Scenario: Add CLI shows what Coffer found before anything is saved
- **GIVEN** the Add CLI dialog
- **WHEN** the user types a command name
- **THEN** it says where Coffer found the command and which version, or that it is not on this machine and can still be added, and says when a skill or MCP server already requires it
- **AND** a refused declaration stays in the dialog with its reason

#### Scenario: the empty CLIs page offers Add CLI and the docs
- **GIVEN** no required command and no tool added by hand
- **WHEN** the user opens `/clis`
- **THEN** the page shows "No command-line tools yet" with one Add CLI button, a link to how `requires:` works and no header buttons

#### Scenario: a skill's requirement links to its CLI
- **GIVEN** a skill that requires `gh`
- **WHEN** the user opens the skill's detail page and chooses the `gh` requirement
- **THEN** the app opens `/clis/gh`

#### Scenario: overview flags a required CLI that needs attention
- **GIVEN** a required CLI that is outdated
- **WHEN** the user opens Overview
- **THEN** an attention item names the CLI and the problem, and its name and its Check action open the CLI's page
- **AND** once the daemon's list no longer reports it — every required CLI present, current and logged in — the item is gone

#### Scenario: a required CLI's description is edited in place
- **GIVEN** `uv`, required by a skill and not added by hand
- **WHEN** the user opens `/clis/uv`, types a description under the header and leaves the field
- **THEN** the page saves that description for `uv`, trimmed, with no Edit dialog

### Requirement: Manage stored secrets on the Secrets page
The Secrets page (`/secrets`, under the sidebar's System group) MUST be the one
page in the web UI that lists and manages stored secrets. A secret is shared
infrastructure data — one reference can be cited by MCP servers, model
providers, channels and skills at once (spec
[secret](../secret/spec.md) "Address a secret by an opaque reference") —
so it gets a page of its own rather than a section of any one kind's page, and
it is not a Settings tab, because it holds data the user manages rather than a
preference. A secret field inside a resource's own dialog stays there: a secret
is still entered where the thing that needs it is configured.

The page MUST carry:

- **List** — every secret the store holds or a resource cites, sorted by its
  displayed name, with whether this Mac holds it, so a reference cited but
  missing reads as missing on this Mac (spec [secret](../secret/spec.md) "List
  every stored and cited secret with what uses it"). The list's controls are
  those of the other library lists: a filter box, then a **Status: All / In use /
  Not used** filter chip (a select), then the secrets grouped under **In use**
  and **Not used** headings. The page has no owner line, no
  owner-type filter, no by-owner view and no "Delete unused".
- **Used by** — for each secret, what cites it, by kind, current name and slot,
  each opening that thing's page; a secret nothing cites reads Nothing and is
  found with the Not used filter.
- **Add and replace** — store a new secret at once, or replace the value of one
  that exists, at once and without the value ever being shown back (spec
  [secret](../secret/spec.md) "Store a secret through the API").
- **Reveal** — show one value behind an explicit, confirmed action, only in the
  desktop app, audited as `secret_revealed` (spec [secret](../secret/spec.md)
  "Release plaintext only to a present human in the desktop app"); in a
  browser the action is disabled and names the desktop app.
- **Delete** — refused while the secret is cited: the control MUST say what still
  uses it, naming each citer as the delete refusal does (spec
  [secret](../secret/spec.md) "Refuse to delete a secret still in use"), and
  the row MUST stay. Several rows can be ticked and deleted at once from the
  table's selection bar ("N of M selected"; Esc clears it); the confirmation
  names the secrets it deletes and skips those in use or waiting for approval.
- **Missing values** — a banner counting the secrets this Mac has no value for,
  with **Add values** (spec [secret](../secret/spec.md) "Show a secret this Mac
  cannot open as missing on this Mac"); it offers no master-key import.
- **List and detail** — the page is a split view like the other library pages:
  `/secrets/<id>` with the list on the left and the chosen secret on the
  right. A list row shows the secret's label — or, without one, the first
  citer's name and the slot, never a hex id — on one line with no description
  (that is in the detail's header), its status (missing on this Mac, waiting for approval) and how
  many things use it; search matches the label, description and id. The
  detail's header holds the label and description, each edited in place (spec
  [secret](../secret/spec.md) "Label and describe a secret without changing its
  reference"), with Replace value… and Reveal value… beside them and Copy
  reference and Delete… in its ⋯ menu. The detail shows the overview directly,
  with no tabs: the id and `coffer://secret/<id>`, each with Copy, whether this
  Mac holds it and whether local processes can read it, created and last used,
  and everything that uses it — by kind, current name and slot, each opening
  its page — with the approvals it holds or waits for. Wherever another page
  shows the secret a resource uses (a provider's API Key, a sync remote's push
  secret, the secret a server or custom tool is missing), it shows that
  secret's displayed name — never its id or URI — and the name opens
  `/secrets/<ref>`. Individual uses are not
  listed on the page; they are audit entries, read in Activity.
- **Find plaintext keys** — the entry point that moves plaintext secrets out of
  what Coffer manages and into the store (spec [secret](../secret/spec.md)
  "Move plaintext secrets in managed resources into the store").
- **Approvals** — a banner counting the changes waiting for approval, with
  **Review**, which opens the one approvals table (spec
  [secret](../secret/spec.md) "Approve several bindings in one confirmation").
  A rejection shows a toast; the page keeps no list of refused changes and has
  no "Ask again".

Each banner has an × that ignores it exactly as Ignore does on Overview, where
the same two situations are listed (spec [secret](../secret/spec.md) "List
secrets with no value here and waiting approvals on Overview"); the page's
header then says it is ignored on Overview and offers Show it again, and the
banner returns when the set changes. The help icon beside the title is gone: how
to run a command with a secret is in the documentation, not on the page.

This requirement fixes the page's place and its parts. What the store enumerates,
how each operation behaves, and the steps of finding plaintext keys are the
secret capability's, specified with it.

#### Scenario: the secrets page lists each secret with what uses it
- **GIVEN** a registered MCP server citing a stored reference, and a model provider citing a reference the store does not hold
- **WHEN** the user opens `/secrets`
- **THEN** both are listed, the first as present and the second as missing on this Mac
- **AND** choosing a row shows its citer in the detail by kind and current name, which opens that resource's page

#### Scenario: a secret in use cannot be deleted from the secrets page
- **GIVEN** a stored secret cited by a registered channel
- **WHEN** the user tries to delete it from the Secrets page
- **THEN** the delete is refused with the channel named as what still uses it
- **AND** the secret's row is still listed

#### Scenario: revealing a secret is an explicit, audited read
- **GIVEN** a stored secret listed on the Secrets page in the desktop app
- **WHEN** the page renders, and then the user chooses Reveal value on that row and confirms
- **THEN** no value is shown until the reveal is confirmed, and then only that secret's value is asked for and shown
- **AND** the page says the reveal is recorded as `secret_revealed`

#### Scenario: the secrets page offers to find plaintext keys
- **GIVEN** the Secrets page
- **WHEN** it is opened, with secrets and with none
- **THEN** its header offers Find plaintext keys beside Add secret, and the empty page offers both

#### Scenario: a secret opens on its own detail page with what uses it
- **GIVEN** the Secrets page listing a secret an MCP server cites under a hex ref, which the server has used
- **WHEN** its row is chosen
- **THEN** the list row reads as the server's name and the slot, the address becomes `/secrets/<id>`, and the detail shows the id, the times and the server under Used by, which opens the server's page, with no tabs
- **AND** a label and description typed in the header show on the row while the id stays the same

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
