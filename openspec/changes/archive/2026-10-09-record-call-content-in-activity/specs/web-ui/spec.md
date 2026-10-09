## MODIFIED Requirements

### Requirement: Filter each Activity tab and expand any row
Every Activity tab MUST filter in one row — the search first (240 wide), then
the time range and the pills, with **Clear filters** at the far right while
anything is set — and show no counts in it. Everything: search, time range,
**By** and **Kind**; Changes: search, time range, **By** and **Kind**; Tool calls:
a segmented **All / OK / Failed** first (Failed is an error, a timeout or a
denial), then search, time range and **By**; Daemon log: a segmented **All /
Info / Warnings / Errors** first, then search, time range and **Logger**. There
is no filter for a server: the search matches a server's name. **By** chooses
several values, listing the agents and, under "Not an agent", you (the web UI,
the desktop app), the command line, Coffer itself and sync, last; on Tool calls
it lists agents only. **Kind** on Everything is three flat values — Tool calls,
Changes, Daemon records — and on Changes the eleven kinds of change (a resource
kind, or secrets, sync, settings and CLIs for a change that names no resource),
flat. A pill lists no counts and searches only above eight values. The time
range is the shared picker: Last hour, Last 24 h, Last 7 days, Last 30 days and
a custom range (calendar days, optional HH:MM, an end of "now", at most 90 days
back); a tab opens on the last hour, the Daemon log on the last 24 hours, until
the user picks one. A record passes when it matches any chosen value.

Selecting a row on Everything, Changes or Tool calls MUST open it in the shared
right-hand drawer (640 wide until its left edge is dragged, the page dimmed behind it; Esc, a click outside or
its ✕ closes it, ↑ ↓ step to the previous or next record, focus returns to the
row), answer first — a failed call's error and how its server has been doing
(since when it has been failing, and its errors in the last 24 hours), a
change's who and what, then its configuration before and after as a diff, a
daemon record's message and traceback — then the records written within five
minutes of it, ending in its raw underlying record, pretty-printed in a
monospace, scrollable block, open and foldable. The footer holds
the next step: **Open** the resource's own detail page beside **Copy details**. A call's drawer
shows, after its answer, the content the call recorded ([mcp-gateway](../mcp-gateway/spec.md)
"Record invocations with redacted, bounded content"), read when the drawer opens: **Arguments**,
**Result** (or **Error**), and for a custom tool **Request** and **Response**, each a foldable
monospace block — JSON laid out, other text as it is — with **Copy**, and a cut part ending in
"Cut at 16 KB — the call carried N KB". A call recorded while recording was off says "Content
was not recorded for this call" with a link to the setting, and the drawer notes that secret
values are masked before anything is stored. A
change whose event the page has no sentence for reads through the same facts and
diff. On the Daemon log a row opens in place under its own line instead, with its
traceback, **Copy record** and, when the record names a server and tool, **Show
the tool call**, which opens the Tool calls tab looking for that call.

#### Scenario: activity row expands to its raw record
- **GIVEN** an Activity tab has at least one row
- **WHEN** the user clicks (or presses Enter/Space on) that row on Everything, Changes or Tool calls
- **THEN** the shared drawer opens over the page with its raw underlying record open — the full JSON, pretty-printed in a monospace, scrollable block

#### Scenario: a daemon log row opens in place
- **GIVEN** the Daemon log tab with an error record carrying a traceback and naming `server=github tool=search_issues`
- **WHEN** the user selects that row, then chooses Show the tool call
- **THEN** the row opens under its own line with the traceback and Copy record, and no drawer opens
- **AND** Show the tool call opens the Tool calls tab searching `github.search_issues`

#### Scenario: who and kind choose several values
- **GIVEN** Everything holding a call by an agent, a change made in the web UI, a change made from the command line and a daemon warning
- **WHEN** the user chooses the agent and "You" under By, then Tool calls and Changes under Kind
- **THEN** the list keeps the agent's call and the web UI's change and drops the others, and the Kind pill reads "Kind: Tool calls, Changes"

#### Scenario: a call's drawer shows its arguments and result
- **GIVEN** a recorded tool call with arguments, a cut result and a call recorded while recording was off
- **WHEN** the user opens each on the Tool calls tab
- **THEN** the first drawer shows Arguments and Result as laid-out JSON with Copy, the result ending in its cut note
- **AND** the second says its content was not recorded and links to Settings › Data

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
  channel attachments and media only, with their size and **Open
  folder**, and one short line saying how they are kept: "Include this folder in
  your own backups." under keep forever, or that attachments are deleted
  automatically after N days. Its **Attachments** row is the retention of those
  files, a Keep forever switch and a number of days (30 by default) that auto-saves like
  every History row, and shortening it asks first, counting the files the shorter
  window deletes.
- **History** — the retention of each record kind — changes, tool calls,
  **Skill working files** (the logs, journals and temporary files skill scripts write under `~/.coffer/skill-data`, 30 days by default, a row whose confirmation counts files) and **Config backups** (the copies Coffer keeps of an agent's config file before it rewrites it, under `~/.coffer/config-backups`, 30 days by default, with the newest copy of each file always kept; a row whose confirmation counts files) — Keep forever or a number of days, cleaned up by the retention
  worker's schedule (at daemon start and every six hours), and, under the tool
  calls row, a **Record tool call content** switch (on by default; [mcp-gateway](../mcp-gateway/spec.md)
  "Switch call content recording per machine") whose help says that arguments and
  results are kept with secrets masked and that turning it off keeps metadata only, with a
  **Clear expired now** action behind a confirmation, which reports what it
  removed; the last cleanup reads "Last cleared today at 12:00 — 1,284 rows" ("30 Sep at 12:00" for another day); a saved value survives a reload. Shortening a
  window (or turning Keep forever off) MUST ask first, and the confirmation
  MUST say how many records the shorter window deletes at the next cleanup and
  how many the table holds now and would hold after, counted by the daemon
  without deleting anything. **Clear expired now** also removes attachments past their window and reports them, and skill working files and config backups past theirs, as files. A refused save MUST say so above the blocks with
  **Try again**, name the window still in place, and mark the row "Not saved".
- **Rebuildable cache** — Coffer's memory tree under `~/.coffer/derived/`,
  which Coffer rebuilds on its own: one **Clear** action,
  behind a confirmation saying that memory is rebuilt from the agents' own
  memory on the next update, each entry becoming a note as it stands, and that
  notes whose sources are gone do not come back.

Edits auto-save, like every settings surface: there is no Save button.

#### Scenario: retention period persists across reload
- **GIVEN** the user opens the Data settings tab
- **WHEN** they turn off "Keep forever" for a record kind in History, set a specific number of retention days, and commit the field (blur or Enter), which auto-saves
- **THEN** reloading the page shows the same retention-days value that was saved

#### Scenario: the data tab shows four blocks and no this-mac block
- **GIVEN** a vault with versions, channel media on disk, and memory partitions
- **WHEN** the user opens `/settings/data`
- **THEN** it shows Vault (size, versions, Open folder), Local content (attachments and media, size, Open folder, not synced, and the Attachments retention row), History (retention for changes, tool calls, skill working files and config backups, the Record tool call content switch, and Clear expired now) and Rebuildable cache (memory tree with Clear), and no This Mac only block

#### Scenario: the attachments retention is set where the attachments are listed
- **GIVEN** attachments kept for 30 days
- **WHEN** the user opens `/settings/data`
- **THEN** Local content has an Attachments row at 30 days and says attachments are deleted automatically after 30 days, and History has no Attachments row
- **AND** after the user turns Keep forever on, the line reads "Include this folder in your own backups." and the choice is saved

#### Scenario: skill working files are kept for a chosen window
- **GIVEN** the `skill_data` policy at 30 days
- **WHEN** the user opens `/settings/data`
- **THEN** History has a Skill working files row at 30 days, after Tool calls
- **AND** shortening it asks first and the confirmation counts files, not records

#### Scenario: shortening a retention window counts what it deletes
- **GIVEN** Tool calls kept for 30 days, some of them older than 7 days
- **WHEN** the user sets the tool calls window to 7 days
- **THEN** a confirmation asks "Keep tool calls for 7 days?", says how many calls older than 7 days the next cleanup deletes, and shows the count now and after
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
- **AND** once confirmed only the memory tree is cleared, with no vault or local content touched

#### Scenario: config backups are kept for a chosen window
- **GIVEN** the `config_backups` policy at 30 days
- **WHEN** the user opens `/settings/data`
- **THEN** History has a Config backups row at 30 days, after Skill working files, whose help text says the newest backup of each file is always kept
- **AND** shortening it asks first and the confirmation counts files, not records

#### Scenario: tool call content recording is switched on the Data tab
- **GIVEN** recording on, its default
- **WHEN** the user turns Record tool call content off on `/settings/data` and reloads
- **THEN** the switch reads off, and calls made from then on open with "Content was not recorded for this call"
