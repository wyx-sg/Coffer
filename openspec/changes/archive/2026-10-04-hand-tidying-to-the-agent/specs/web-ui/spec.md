## ADDED Requirements

### Requirement: Offer a knowledge refusal's hand-off as one Ask an agent control
When the daemon refuses a knowledge operation with a hand-off in the error's details
(`details.handoff.prompt`), the Knowledge page MUST offer that prompt as one **Ask an agent ▾**
control — Ask an agent opens a draft conversation with the prompt, and its menu holds Copy prompt,
which is the only action when no managed agent is available — passing the prompt on as served and
never assembling it. A History tab or Recent changes that cannot be read because git is not
installed MUST say so in one neutral row — **History needs git** or **Recent changes needs git**,
*Install git on this Mac to see versions. The document itself is fine.* — with **Check again** and
the hand-off, and no Retry or Open Activity. The page MUST NOT
show an install command.

#### Scenario: a history that needs git offers the prompt for installing it
- **GIVEN** a machine with no git, whose history reads are refused with the install hand-off
- **WHEN** a document's History tab opens
- **THEN** it shows the row *History needs git* with Check again and Ask an agent ▾, whose menu copies the served prompt, and names no install command
- **AND** it offers no Retry and no Open Activity

#### Scenario: recent changes that need git offer the same row
- **GIVEN** a machine with no git, whose history reads are refused with the install hand-off
- **WHEN** Recent changes opens
- **THEN** it shows the row *Recent changes needs git* with Check again and Ask an agent ▾

### Requirement: List recent knowledge changes across collections
The Knowledge page MUST carry a **Recent changes** view: one timeline across every collection, newest
first, of documents people and agents wrote or deleted. A version an earlier curation pass wrote
keeps its curation label. It MUST be filtered with **Collection** and **Author** filter pills and a
**Clear filters** control, the choice kept in the URL. A delete carries **Restore**. The view has no
waiting items and no pass to inspect or undo; a refusal because git is not installed is handled as in
"Offer a knowledge refusal's hand-off as one Ask an agent control".

#### Scenario: recent changes shows a cross-collection timeline
- **GIVEN** an agent's write in one collection and a person's edit in another
- **WHEN** the user opens Recent changes
- **THEN** both changes are listed, newest first, each linking the document it wrote, and the view shows no waiting items and no Curate now

#### Scenario: the filter pills narrow the timeline and live in the URL
- **GIVEN** changes in two collections by the user and by an agent
- **WHEN** the user picks one collection in the Collection pill and the agent in the Author pill, then chooses Clear filters
- **THEN** the timeline lists only that collection's changes by that agent and the URL carries both choices, and Clear filters empties both and the URL

## MODIFIED Requirements

### Requirement: Organise Settings into six tabs
Settings — the modal of "Open Settings as a modal from the sidebar footer" —
MUST carry six tabs, in this order, in every build, grouped by what they manage
rather than by how Coffer is built, and MUST open on General:

- **General** (`/settings/general`) — display preferences (the interface language
  and the theme, the default page size and the preferred external editor), and a
  **Speech-to-text** section: the connection and model that transcribe voice
  messages and the bound on one model call (spec
  [internal-engine](../internal-engine/spec.md) "Show the speech-to-text pair and the call bound in Settings › General").
  It carries no experimental-features card; the switches are on the Features
  tab. While `models` is off the connection choice for speech-to-text is left out.
- **Security** (`/settings/security`) — what is about this machine only: where
  the master encryption key lives — in a signed release its Keychain access
  group; in a development build the file `~/.coffer/master.key` or the login
  keychain, with the switch that moves it — with its backup, import and
  fingerprint; the daemon's access token (see "Show, copy and rotate the access
  token on Settings › Security"); and whether a secret waits for approval
  before it goes somewhere new. It lists and edits no stored secret; those are
  on the Secrets page (see "Manage stored secrets on the Secrets page").
- **Data** (`/settings/data`) — what Coffer stores, by kind: Vault, Local content, History
  and Rebuildable cache (see "Group the Data tab by what kind of data it is").
- **Daemon** (`/settings/daemon`) — the daemon's state and the controls a user
  needs for it (see "Show and manage the daemon on Settings → Daemon").
- **Features** (`/settings/features`) — the four experimental features, each
  marked Experimental, with its switch (spec
  [experimental-features](../experimental-features/spec.md) "Show the Features tab in every build").
- **About** (`/settings/about`) — version, license, source, whether a newer
  version is available (see "Check for and install updates on Settings › About"),
  and a small **Copy diagnostics** action beside the version.

Clicking a tab
swaps the modal's right pane without a full page reload and without closing the
modal.

Every pane follows the page grammar: it opens with the tab's title (an `h1`) and
one muted intro line, then its sections 32px apart. A section is not boxed — its
title carries its meta and action on one line, its description is one muted line
under the title, and its rows are separated by hairlines; a tab with a single
section (Features) prints no section title. Settings save on change: no pane has
a Save button, and a text field applies on Enter or when it loses focus.

#### Scenario: settings layout uses the redesigned tabbed sidebar
- **GIVEN** the user navigates to `/settings`
- **WHEN** the route resolves
- **THEN** the Settings modal opens on the General tab
- **AND** the modal's tab list shows General, Security, Data, Daemon, Features and About — exactly those six, in that order — with the current route highlighted
- **AND** clicking a tab swaps the right pane content without a full page reload and the modal stays open

#### Scenario: every settings tab opens with its title and an intro line
- **GIVEN** the Settings modal
- **WHEN** each of the six tabs is opened
- **THEN** its pane starts with an `h1` named for the tab, followed by one intro line
- **AND** the pane has no Save button

#### Scenario: the security tab keeps only machine-level settings
- **GIVEN** stored secrets cited by a registered MCP server and a model provider
- **WHEN** the user opens `/settings/security`
- **THEN** the tab shows where the master key lives and, in a development build, its move control, and the access token's Show, Copy and Rotate controls
- **AND** it lists no stored secret and offers no control that adds, reveals or deletes one

### Requirement: Group the Data tab by what kind of data it is
The Data tab MUST show what Coffer stores in four blocks, one per kind of data
([Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md)),
and no other — in particular no "This Mac only" block, since what is true of this
machine only is a setting shown on the tab it belongs to:

- **Vault** — the git repository at `~/.coffer/vault/` holding the user's
  configuration, skills, knowledge and encrypted secrets, a repository whether
  or not it syncs ([vault-storage](../vault-storage/spec.md) "Keep the vault a
  git repository whether or not it syncs"): its size (with its history), how
  many versions it holds, when and by whom it last changed, whether it syncs to
  a remote or is this machine's only copy, and **Open folder**, whose tooltip
  names the folder (no separate location row).
- **Local content** — what is not synced and the user must back up themselves:
  chat and channel attachments and media only, with their size and **Open
  folder**, and one short line saying how they are kept: "Include this folder in
  your own backups." under keep forever, or that attachments are deleted
  automatically after N days. Its **Attachments** row is the retention of those
  files, a Keep forever switch and a number of days (30 by default) that auto-saves like
  every History row, and shortening it asks first, counting the files the shorter
  window deletes.
- **History** — the retention of each record kind — changes, MCP calls,
  conversations, **Skill working files** (the logs, journals and temporary files skill scripts write under `~/.coffer/skill-data`, 30 days by default, a row whose confirmation counts files) and **Config backups** (the copies Coffer keeps of an agent's config file before it rewrites it, under `~/.coffer/config-backups`, 30 days by default, with the newest copy of each file always kept; a row whose confirmation counts files) — Keep forever or a number of days, cleaned up by the retention
  worker's schedule (at daemon start and every six hours), with a
  **Clear expired now** action behind a confirmation, which reports what it
  removed; the last cleanup reads "Last cleared today at 12:00 — 1,284 rows" ("30 Sep at 12:00" for another day); a saved value survives a reload. Shortening a
  window (or turning Keep forever off) MUST ask first, and the confirmation
  MUST say how many records the shorter window deletes at the next cleanup and
  how many the table holds now and would hold after, counted by the daemon
  without deleting anything. **Clear expired now** also removes attachments past their window and reports them, and skill working files and config backups past theirs, as files. A refused save MUST say so above the blocks with
  **Try again**, name the window still in place, and mark the row "Not saved".
- **Rebuildable cache** — Coffer's memory tree and the transcript summary cache,
  both under `~/.coffer/derived/`, which Coffer rebuilds on its own: one **Clear** action,
  behind a confirmation saying that memory is rebuilt from the agents' own
  memory on the next update, each entry becoming a note as it stands, and that
  notes whose sources are gone do not come back.

Edits auto-save, like every settings surface: there is no Save button.

#### Scenario: retention period persists across reload
- **GIVEN** the user opens the Data settings tab
- **WHEN** they turn off "Keep forever" for a record kind in History, set a specific number of retention days, and commit the field (blur or Enter), which auto-saves
- **THEN** reloading the page shows the same retention-days value that was saved

#### Scenario: the data tab shows four blocks and no this-mac block
- **GIVEN** a vault with versions, chat media on disk, and memory partitions
- **WHEN** the user opens `/settings/data`
- **THEN** it shows Vault (size, versions, Open folder), Local content (attachments and media, size, Open folder, not synced, and the Attachments retention row), History (retention for changes, MCP calls, conversations, skill working files and config backups with Clear expired now) and Rebuildable cache (memory tree and transcript summary cache with Clear), and no This Mac only block

#### Scenario: the attachments retention is set where the attachments are listed
- **GIVEN** attachments kept for 30 days
- **WHEN** the user opens `/settings/data`
- **THEN** Local content has an Attachments row at 30 days and says attachments are deleted automatically after 30 days, and History has no Attachments row
- **AND** after the user turns Keep forever on, the line reads "Include this folder in your own backups." and the choice is saved

#### Scenario: skill working files are kept for a chosen window
- **GIVEN** the `skill_data` policy at 30 days
- **WHEN** the user opens `/settings/data`
- **THEN** History has a Skill working files row at 30 days, after Conversations
- **AND** shortening it asks first and the confirmation counts files, not records

#### Scenario: shortening a retention window counts what it deletes
- **GIVEN** MCP calls kept for 30 days, some of them older than 7 days
- **WHEN** the user sets the MCP calls window to 7 days
- **THEN** a confirmation asks "Keep MCP calls for 7 days?", says how many calls older than 7 days the next cleanup deletes, and shows the count now and after
- **AND** nothing is deleted or saved until the user confirms

#### Scenario: clear expired now removes what retention has passed
- **GIVEN** changes kept for 7 days and changes older than that
- **WHEN** the user chooses Clear expired now and confirms
- **THEN** the older changes are removed and the rest remain, as the scheduled cleanup would have done
- **AND** the page reports how many records it removed, by record kind

#### Scenario: clearing the cache is confirmed and rebuilt
- **GIVEN** memory partitions with notes
- **WHEN** the user chooses Clear in Rebuildable cache
- **THEN** a confirmation says the next memory update rebuilds memory from the agents' own memory and that notes whose sources are gone do not come back, and nothing is cleared until the user confirms
- **AND** once confirmed only the memory tree and the transcript summary cache are cleared, with no vault or local content touched

#### Scenario: config backups are kept for a chosen window
- **GIVEN** the `config_backups` policy at 30 days
- **WHEN** the user opens `/settings/data`
- **THEN** History has a Config backups row at 30 days, after Skill working files, whose help text says the newest backup of each file is always kept
- **AND** shortening it asks first and the confirmation counts files, not records

### Requirement: Show a knowledge document's history on its History tab
A knowledge document's pane MUST carry two tabs, **Document** (the default) and **History**, neither
with a count. History is the version-history split of "Show every version history as one split": the
document's versions on the left, newest first — who wrote each (the user, an agent, an edit found on disk, or sync; a version an
earlier curation pass wrote keeps its curation label), when, and its added and removed line counts — and the chosen
version on the right, the newest chosen when the tab opens. The right side MUST carry a switch between
**Changes in this version** (against the one before) and **Compare with current**, **Restore this
version** on every version but the current one, which writes a new version rather than rewriting the
past, and the diff. A history that cannot be read
MUST say so in one **Load error** row inside the tab — *Couldn't load the history*, the reason,
**Retry** and **Open Activity** — leaving the Document tab working; without git the row is *History
needs git* (see "Offer a knowledge refusal's hand-off as one Ask an agent control").

#### Scenario: the history tab lists versions with their writers
- **GIVEN** a document the user created, that an agent then changed
- **WHEN** the user opens its History tab and chooses the older version's row
- **THEN** the tab lists both versions newest first with their writers, its diff shows on the right beside the list, and Restore this version is offered on it and not on the current version
- **AND** restoring it writes it back as a new version

#### Scenario: a history that fails to load leaves the document readable
- **GIVEN** the history read failing
- **WHEN** the user opens the History tab
- **THEN** the tab shows one Load error row with Retry and Open Activity, and the Document tab still renders

## REMOVED Requirements

### Requirement: Choose Coffer's model in Settings › General
**Reason**: Coffer runs no model over knowledge or memory, so there is no engine model to choose. The speech-to-text pair and the per-call bound are set in the Speech-to-text section of Settings › General.
**Migration**: Use "Show the speech-to-text pair and the call bound in Settings › General" in the internal-engine capability.

### Requirement: Offer the hand-off a knowledge refusal carries beside it
**Reason**: The requirement described an undo-pass refusal that no longer exists; the remaining hand-off behaviour is restated under a new title.
**Migration**: Use "Offer a knowledge refusal's hand-off as one Ask an agent control".

### Requirement: Follow knowledge changes in Recent changes
**Reason**: The view lists no curation passes, waiting items or pass undo; the remaining behaviour is restated under a new title.
**Migration**: Use "List recent knowledge changes across collections".
