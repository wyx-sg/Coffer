## MODIFIED Requirements

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
  a remote or is this machine's only copy, its location, and **Open folder**.
- **Local content** — what is not synced and the user must back up themselves:
  chat and channel attachments and media only, with their size and **Open
  folder**, and a line saying so.
- **History** — the retention of each record kind — changes, MCP calls and
  conversations — Keep forever or a number of days, cleaned up by the retention
  worker's schedule (at daemon start and every six hours), with a
  **Clear expired now** action behind a confirmation, which reports what it
  removed; the last cleanup reads "Last cleared today at 12:00 — 1,284 rows" ("30 Sep at 12:00" for another day); a saved value survives a reload. Shortening a
  window (or turning Keep forever off) MUST ask first, and the confirmation
  MUST say how many records the shorter window deletes at the next cleanup and
  how many the table holds now and would hold after, counted by the daemon
  without deleting anything. A refused save MUST say so above the blocks with
  **Try again**, name the window still in place, and mark the row "Not saved".
- **Rebuildable cache** — Coffer's memory tree and the transcript summary cache,
  both under `~/.coffer/derived/`, which Coffer rebuilds on its own: one **Clear** action,
  behind a confirmation saying that memory is rebuilt from the agents' own
  memory on the next update, that an equivalent rebuild needs Coffer's model
  (without it each entry becomes a note of its own), and that notes whose
  sources are gone do not come back.

Edits auto-save, like every settings surface: there is no Save button.

#### Scenario: retention period persists across reload
- **GIVEN** the user opens the Data settings tab
- **WHEN** they turn off "Keep forever" for a record kind in History, set a specific number of retention days, and commit the field (blur or Enter), which auto-saves
- **THEN** reloading the page shows the same retention-days value that was saved

#### Scenario: the data tab shows four blocks and no this-mac block
- **GIVEN** a vault with versions, chat media on disk, and memory partitions
- **WHEN** the user opens `/settings/data`
- **THEN** it shows Vault (size, versions, Open folder), Local content (attachments and media, size, Open folder, not synced), History (retention for changes, MCP calls and conversations with Clear expired now) and Rebuildable cache (memory tree and transcript summary cache with Clear), and no This Mac only block

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
