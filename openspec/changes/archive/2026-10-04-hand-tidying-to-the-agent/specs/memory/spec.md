# Delta for memory

## ADDED Requirements

### Requirement: Distil each raw entry into a note mechanically
A **distil** pass MUST run on its own interval — the `distil` pass's switch and interval in the engine's upkeep settings ([internal-engine](../internal-engine/spec.md) "Carry a switch and interval for each unattended pass") — rather than after each aggregation, over every partition that holds raw entries it has not yet distilled. Each such raw entry MUST become one note of its own as it stands: the raw entry's title, description, type, body, search terms and origin, with `created_at` and `updated_at`. Notes are one topic per file: a later raw entry on a topic a note already covers opens a note of its own beside it, and collapsing the two is tidying, which an agent does. Then the pass MUST retire every note none of whose raw entries is left (see "Retire a note whose raw entries are all gone"), process every note an agent marked retired (see "Retire a note an agent marked retired"), and render `MEMORY.md` from the notes' frontmatter. It MUST NOT be a no-op on any installation, and it MUST NOT call a model, and send file content anywhere, on any path: judging which notes are the same subject, or which statement is stale, is the agent's work (see "Teach tidying in the coffer-guide's memory section"). A partition with no undistilled raw entry and nothing to retire costs nothing. Whenever an aggregation files entries into a partition or a distil pass finishes over one, Coffer MUST announce the partition on the daemon's event stream as a `memory` event carrying the partition's uid, because notes and raw entries change without any write to the partition's row ([resource-framework](../resource-framework/spec.md) "Announce every change on one daemon-wide event stream").

#### Scenario: distil turns each raw entry into a note and writes the index
- **GIVEN** a partition holding two raw entries no pass has distilled
- **WHEN** the distil pass runs
- **THEN** each raw entry is carried through to a note of its own whose body is the entry's body, and `MEMORY.md` has one line per note from its frontmatter
- **AND** no model is called and no note is merged or rewritten

#### Scenario: a later raw entry on a covered topic opens a note of its own
- **GIVEN** a partition holding a note on a topic, and a newly aggregated raw entry that adds a detail to that same topic
- **WHEN** the distil pass runs
- **THEN** the partition holds both notes, the first unchanged and the second carrying the new entry as its origin
- **AND** neither note is merged until an agent tidies the partition

#### Scenario: no memory path calls a model
- **GIVEN** a distilled partition and a model connection rigged to fail the test if it is called
- **WHEN** a distil pass runs and the session context is composed
- **THEN** both complete and the connection is never called

#### Scenario: aggregating and distilling announce the partition that changed
- **GIVEN** a registered partition and a client reading the event stream
- **WHEN** an aggregation files a new entry into it, and then a distil pass finishes over it
- **THEN** a `memory` event naming the partition's uid is announced after each

### Requirement: Retire a note an agent marked retired
A note whose frontmatter carries `retired: <reason>`, with an optional `replaced_by: <slug>`, MUST be processed by the next distil pass: the pass records it in the partition's `RETIRED.md` with its title, the reason, the `replaced_by` note when given and the note's origin entry ids, deletes its file from `notes/`, and re-renders `MEMORY.md` without it. A note retired this way MUST NOT be recreated: its origin entry ids are in `RETIRED.md`, so the raw entries it was built from are not distilled again (see "Record retirements so they stick"). The mark is how an agent retires a note without deleting the file, because deleting the file alone would let the next pass recreate it from the raw entry.

#### Scenario: an agent-retired note is recorded with its entry ids and not recreated
- **GIVEN** a partition holding a note whose raw entry is still present, and an agent that adds `retired: superseded by the lockfile note` and `replaced_by: python-lockfile` to the note's frontmatter
- **WHEN** the distil pass runs, and then runs again after the next update
- **THEN** `RETIRED.md` holds a record naming the note's title, the reason, `python-lockfile` as its replacement and the note's origin entry ids, the note's file is gone from `notes/`, and no index line mentions it
- **AND** the second pass does not recreate the note from its raw entry

#### Scenario: a retired mark without a replacement is recorded without one
- **GIVEN** a note whose frontmatter carries `retired: the service was removed` and no `replaced_by`
- **WHEN** the distil pass runs
- **THEN** its `RETIRED.md` record carries the reason and no replacement, and its file is gone from `notes/`

### Requirement: Teach tidying in the coffer-guide's memory section
The `coffer-guide` skill's memory section MUST teach an agent to tidy a memory partition, because Coffer runs no model over memory. It MUST say to work one partition at a time under the memory root, and to read the partition's `MEMORY.md` and then the notes in full before changing them. It MUST teach **merging** notes about the same subject by rewriting the surviving note so it holds every fact of both and appending every entry of the merged note's `origins:` list to the survivor's `origins:`, unchanged, then deleting the merged file — origins are how Coffer knows a memory is already accounted for, so a dropped origin brings the merged note back. It MUST teach **retiring** a note that is no longer true by adding `retired:` with the reason, and `replaced_by:` with the surviving note's file name when there is one, rather than deleting the file (see "Retire a note an agent marked retired"). It MUST state that where two notes disagree the newer statement wins unless the older one is shown to be right by a source, a date, a command's output or the code, whoever wrote either; that a note keeps one topic and a one-line `description`; and that `.raw/`, `MEMORY.md`, `RETIRED.md` and the agents' own memory files are left alone. The text MUST be present whenever the `memory` feature is on and absent when it is off.

#### Scenario: the memory section teaches merging by origins and retiring by frontmatter
- **GIVEN** the guide rendered with the `memory` feature on
- **WHEN** its memory section is read
- **THEN** it tells the agent to append a merged note's `origins:` to the survivor's, to retire by adding `retired:` and `replaced_by:` to a note's frontmatter, and to treat the newer or better-evidenced statement as the winner
- **AND** it names `.raw/`, `MEMORY.md` and `RETIRED.md` as files to leave alone

#### Scenario: the memory section is absent with the memory feature off
- **GIVEN** the guide rendered with the `memory` feature off
- **WHEN** its text is read
- **THEN** it carries no tidying instruction for memory

### Requirement: Hand a partition's tidying to the agent
Reading one partition (`GET /api/v1/memory/partitions/{uid}`) MUST carry `tidy_handoff`: a prompt, produced by the domain's hand-off text, that names the partition, its absolute directory and the `coffer-guide` section to follow (see "Teach tidying in the coffer-guide's memory section"). The partition's page MUST offer a **Tidy** button. With a default managed agent available, **Tidy** MUST open a new conversation on that agent with the `tidy_handoff` prompt, send it at once and land on the conversation; with none available, the page MUST offer **Copy prompt** only. The Memory page MUST also offer **Tidy all** in its header, backed by `GET /api/v1/memory/tidy-handoff`: a prompt that names the memory root and every partition with its absolute notes directory and note count, and asks the agent to tidy them one at a time by the same section; it behaves as **Tidy** does. Nothing MUST tidy a partition unattended: a partition is tidied only when a person chooses Tidy or asks an agent to.

#### Scenario: Tidy sends the prompt to the default managed agent
- **GIVEN** a partition's page and a default managed agent
- **WHEN** the person chooses **Tidy**
- **THEN** a new conversation opens on that agent with the partition's `tidy_handoff` prompt already sent, and the page lands on it
- **AND** the prompt names the partition, its absolute directory and the coffer-guide section to follow

#### Scenario: Tidy all hands every partition to the agent in one conversation
- **GIVEN** the Memory page with two partitions and a default managed agent
- **WHEN** the person chooses **Tidy all**
- **THEN** one new conversation opens on that agent with the `GET /api/v1/memory/tidy-handoff` prompt already sent
- **AND** the prompt names the memory root and both partitions with their notes directories and note counts

#### Scenario: with no managed agent the page offers Copy prompt only
- **GIVEN** a partition's page and no managed agent
- **WHEN** the person opens Tidy
- **THEN** the page offers **Copy prompt**, which copies the `tidy_handoff` prompt, and starts no conversation

#### Scenario: nothing tidies a partition unattended
- **GIVEN** a partition holding near-duplicate notes, with the aggregate and distil switches on
- **WHEN** the workers run through several intervals and no person chooses Tidy
- **THEN** every note is as the distil pass wrote it, and no conversation was opened

### Requirement: Edit a memory in the web UI or in an editor
A person MUST be able to edit a memory in the web UI or in their own editor. `PUT /api/v1/memory/partitions/{uid}/notes/{slug}` MUST replace the note's **body** with the text it is given, keep the note's frontmatter, stamp `updated_at`, and take the fingerprint the note's read returned. A note that changed since — an agent merged or rewrote it, or it was edited on disk — MUST be refused with `MEMORY_NOTE_CONFLICT` (409) and left untouched, and the refusal MUST carry what an editor needs to recover without a second save over the note: `saved: false`, and the note as it is now, its body and its fingerprint. An accepted save MUST record a `memory_note_edited` audit event naming the partition, the note and the user. Editing the file under `notes/` with any other tool needs no Coffer surface: the note is the file.

An edited note is the note, not a suggestion: a distil pass never rewrites an existing note's body, so the edit persists until the note is retired or the derived tree is deleted. The derived tree stays disposable: deleting it and rebuilding reproduces the notes from the agents' own memory and loses every edit, and the guide says so.

#### Scenario: a save replaces the body and keeps the frontmatter
- **GIVEN** a note read with its fingerprint
- **WHEN** a new body is saved with that fingerprint
- **THEN** the note's body is the saved text, its `title`, `description`, `type` and provenance are unchanged, its `updated_at` is stamped, and the answer carries the new fingerprint
- **AND** a `memory_note_edited` event names the partition, the note and the user

#### Scenario: a save over a note that changed is refused with the current text
- **GIVEN** a note read with its fingerprint, and an agent that then rewrote it
- **WHEN** the save arrives with the fingerprint the editor loaded
- **THEN** it is refused with 409 `MEMORY_NOTE_CONFLICT` with `saved` false and the body and fingerprint the note has now
- **AND** the file still holds the agent's text, and saving the user's text again needs the new fingerprint


#### Scenario: an edit made on disk needs no Coffer surface
- **GIVEN** a note's file under `notes/`
- **WHEN** a person changes its body in their own editor
- **THEN** the next read of the note, the index line rendered from it and the next session's delivery carry the changed text
- **AND** deleting the derived tree and rebuilding it gives back a note without that edit

### Requirement: Leave the raw directory to aggregation
Distil MUST NOT write, modify or delete anything under `.raw/`. The two passes own two directories, which is what lets a distil pass be re-run without re-reading the agents.

#### Scenario: leave the raw directory byte-identical through a distil pass
- **GIVEN** a partition whose `.raw/` holds entries, snapshotted byte-for-byte, an undistilled entry, and a note marked retired
- **WHEN** the distil pass runs
- **THEN** every file under `.raw/` is byte-identical afterwards and no file has been added to or removed from it

### Requirement: Record what each distil pass wrote and retired
A distil pass MUST record what it did — the notes it wrote, the notes it retired and why, and the partition it ran over — so a developer can answer why a note is in the partition or gone from it. A partition MUST never be left without an index, even when the pass finds nothing to write.

#### Scenario: report what a distil pass wrote and retired
- **GIVEN** a partition holding one undistilled raw entry, a note whose raw entries are all gone, and a note marked retired
- **WHEN** the distil pass runs
- **THEN** its record names the partition and counts one note written and two notes retired
- **AND** the partition's `MEMORY.md` is present afterwards

## MODIFIED Requirements

### Requirement: Keep the memory tree derived and local
The whole tree under `~/.coffer/derived/memory/` MUST be derived: deleting it and re-running aggregation and distil MUST reproduce an **equivalent** partition — the same subjects, from the same sources. A note's body is its raw entry as it stands, so only what an agent or a person did to the notes afterwards — an edit, a merge, a retirement — is not reproduced. It MUST NOT be in the vault, so it never reaches the sync remote ([vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves"): it is derived from the agents installed on *this* machine, so sending it to another would send notes that machine's own next pass would recompute away. **A partition's resource is covered by that too, not only the files** — the `memory` kind files its resources in the derived class, `~/.coffer/derived/resources/memory/`, where no commit and no round ever reaches them ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature"). Losing the machine loses the derived tree, and that is accepted.

#### Scenario: deleting the memory tree and re-syncing reproduces an equivalent set
- **GIVEN** a distilled partition whose directories are then deleted by hand, with the source-digest cache deliberately left behind
- **WHEN** aggregation and distil run again
- **THEN** the partition is rebuilt: `.raw/` holds the same entries, `notes/` covers the same subjects, and `MEMORY.md` indexes them
- **AND** a digest match alone therefore never suppresses a rebuild, and edits and merges made to the deleted notes are not required to come back (see "Keep the memory tree derived and local")

#### Scenario: a partition does not travel to the sync remote
- **GIVEN** the partitions an aggregation and a distil pass produced
- **WHEN** Coffer's home is listed
- **THEN** each partition is one resource file under `~/.coffer/derived/resources/memory/` and one directory under `~/.coffer/derived/memory/`, and nothing of either is in the vault, so no commit and no sync round carries them
- **AND** the `memory` kind files every partition in the derived class

### Requirement: Record retirements so they stick
A retirement MUST be recorded in the partition's `RETIRED.md`: the note's title, why it was retired, the origin entry ids it accounts for, and the note that replaced it when there is one. A person's hand deletion of a memory is a retirement like any other, with the reason `Deleted by hand` (see "Delete a memory by hand"), and so is a note an agent marked retired (see "Retire a note an agent marked retired"). The file MUST be part of the next pass's input, so a retired subject is not reinstated from the same unchanged raw entry — this is the only mechanism that makes a deletion stick in a store whose sources are outside it, and without it every pass would re-import what the last one removed. A retired note's file MUST leave `notes/` and MUST NOT appear in the index or in delivery.

#### Scenario: a retired note leaves the index and stays out
- **GIVEN** a partition holding a note whose raw entry is still present in an agent's own memory, and that note then retired
- **WHEN** the distil pass runs, and then runs again over unchanged sources
- **THEN** after the first pass the note is named in `RETIRED.md` with its reason, its file is gone from `notes/`, and no index line mentions it
- **AND** the second pass does not recreate it, because `RETIRED.md` is part of the pass's own input (see "Record retirements so they stick")

### Requirement: Present a partition as its memories
The web UI MUST present partitions **as a table** once any exists; with none, it shows the first-run welcome every other empty surface shows — *Nothing distilled yet*, with **Update memory** and the connected agents whose memory Coffer found on this machine, or, with no agent connected, saying there is nothing to read and offering **Open Agents** to connect one. Each row MUST carry the partition's path ("Every project" for `global`), how many memories it holds, its sources (the agents it came from, "All agents" when every agent that contributed anywhere contributed here) and its state, in a column headed **Distilled**: when it was last distilled, "Not distilled yet", "Distilling…" while a pass over it runs, or "Repository missing". Healthy rows are grey: only **Repository missing** is coloured, and only that row offers a Delete, which asks first because it cannot be undone (a confirmation naming the partition, with Cancel and Delete partition). The partitions table has no section title and no count of partitions or memories, and a search box above it filters the rows by partition name and path. A partition's page MUST have no back link, and no Automatic control: its title is the partition's name alone, and its description line carries the path, the memory count and when it was last distilled (*~/code/coffer · 38 memories · distilled 2 h ago*). Its ⋯ menu holds **Reveal partition folder**, **Copy path**, **Distil history in Activity** and, only when its repository is gone, **Delete partition**. A partition not yet distilled shows no memory list: its Memories tab shows only the empty state, which offers no Update memory of its own because the header has one. Each memory in its list MUST name the agents it was learned from ("All agents" when that is every agent the partition came from). The partition listing MUST carry when its newest memory was last updated (`updated_at`, absent for a partition holding no memory), which the Overview's Memory tile words as "Last update 14 min ago". One partition's page MUST carry two tabs. **Memories** (the default) lists its memories — the web UI's label for what this spec and the disk call notes (中文 记忆条目) — beside the selected memory, with the partition's retired memories in a collapsed **Retired** group, each with the reason it was retired; choosing one opens it read-only beside the list (see below). The selected memory MUST be rendered with a meta line naming the agents it was learned from and when it was last updated, taken from its provenance ("Store each note as one Markdown file with frontmatter"), and its frontmatter MUST be shown as that metadata, not rendered as body text. The page MUST NOT show the agents' own memory: no native paths, no original agent text, no `.raw/` entry, no `MEMORY.md` index or `RETIRED.md` file, and no file tree — those stay in the data and on disk, and only this page leaves them out. The partition's own folder is reached through the partition's ⋯ menu (**Reveal partition folder**, **Copy path**); a memory's own file is reached from the memory (see below). The list and the memory MUST extend to the bottom of the window and scroll inside. The partition's page MUST offer **Tidy** in its header (see "Hand a partition's tidying to the agent"). The selected memory MUST offer **Edit** (see "Edit a memory in the web UI or in an editor") and **Open in editor** as visible buttons, and a ⋯ menu holding **Reveal in Finder** and **Delete…**; its body is rendered with find (⌘F). **Delete…** MUST ask first, and on confirming MUST retire the memory by hand (see "Delete a memory by hand"). A retired memory chosen from the Retired group MUST open read-only — its full title, a *Retired* tag, the date it was retired, its full reason and, when it was replaced by a memory still in the list, a **Replaced by <memory> →** link to it — and offers no Edit or Delete; the selection is addressed in the URL (`?retired=<index>`), and a Retired group so addressed opens expanded. The Memory page's title carries the **Experimental** tag ([experimental-features](../experimental-features/spec.md)); a partition's page does not. **Delivered** (`/memory/<uid>/delivered`) shows, read-only, the exact session-start text each agent receives in the partition's project, with a switch between agents ([web-ui](../web-ui/spec.md) "Show memory delivery on the Memory page"); it shows no hook state.

#### Scenario: browse a partition's memories with a read-only preview
- **GIVEN** the memory pages, with no partitions and then with one distilled partition that holds raw entries, a memory learned from Claude Code and Codex, and one retired memory
- **WHEN** the partitions page and the partition's page render and the memory is chosen
- **THEN** the partitions page shows the first-run welcome with none and the table with one, and the partition's page lists its memories beside the chosen one, whose meta line names Claude Code and Codex and when it was updated and whose frontmatter is not in the rendered body
- **AND** the retired memory is in a collapsed Retired group with its reason, the page shows no file tree, no `MEMORY.md`, `RETIRED.md` or `.raw/`, no native path and no agent's original text, and the chosen memory offers Edit, Open in editor and a ⋯ menu with Reveal in Finder and Delete…
- **AND** choosing the retired memory opens it read-only (`?retired=<index>`, group expanded) with its full title, a Retired tag, the retired date, its full reason and a **Replaced by <memory> →** link when a memory in the list replaced it, and no Edit or Delete…

#### Scenario: the selected memory is edited in place
- **GIVEN** a partition's page with a memory selected
- **WHEN** the user chooses Edit, changes the body and saves
- **THEN** the memory renders the saved body with a refreshed update time, and a save refused as changed offers the current text so nothing is lost (see "Edit a memory in the web UI or in an editor")
- **AND** a retired memory in the Retired group offers no Edit

#### Scenario: a partition lists when its newest memory was updated
- **GIVEN** a partition holding a memory
- **WHEN** the partitions are listed over REST
- **THEN** the partition carries the time its newest memory was last updated as `updated_at`

#### Scenario: provenance paths stay in the data, not on the page
- **GIVEN** a memory whose provenance names a Claude Code fact file by its native path
- **WHEN** the memory is read over the REST note route and shown on the partition's page
- **THEN** the route's provenance still carries the agent, the native path and the read time, while the page shows only the agent's name and the update time

#### Scenario: a partition's page names the partition and offers no way back
- **GIVEN** a distilled partition for a repository, with 38 memories
- **WHEN** its page renders
- **THEN** the title is the partition's name with no Experimental tag and no back link, the description line carries the path, *38 memories* and when it was distilled, and there is no Automatic control
- **AND** its header offers Tidy beside Update memory

#### Scenario: deleting a partition still asks
- **GIVEN** a partition whose repository is gone
- **WHEN** the user chooses Delete on its row
- **THEN** a confirmation names the partition and nothing is deleted until the user chooses Delete partition

#### Scenario: a partition has a memories tab and a delivered tab
- **GIVEN** a partition with memories and two connected agents
- **WHEN** the user opens the partition and then its Delivered tab
- **THEN** the page opens on Memories, and Delivered shows each agent's session-start text read-only with an agent switch and no hook state

#### Scenario: the partitions table names each partition's sources and distil state
- **GIVEN** a distilled partition learned from every agent, a partition holding entries read from Codex that no pass has distilled, and a partition whose repository is gone
- **WHEN** the partitions page renders
- **THEN** the Distilled column's first row shows when it was distilled, the second reads "Not distilled yet", and the third reads "Repository missing", the only coloured one and the only one with Delete
- **AND** the first row shows "All agents", and the table has no sample memory column and no section title, and a search box filters the rows by partition name and path

### Requirement: Retire a note whose raw entries are all gone
Every distil pass MUST first retire each note **none** of whose provenance entries is still under its partition's `.raw/`. Aggregation removes a raw entry when its source stops producing it: the agent deleted the fact, or deleted the whole source file (judged only for a registered agent whose config directory is still there — a directory that is missing lists nothing and proves nothing), or placement now files it into a different partition (see "File personal entries into global"). A note is derived from what `.raw/` holds (see "Keep the memory tree derived and local"), so one with no source left MUST NOT stay in `notes/`, in the index or in delivery — otherwise the same lesson is served from two partitions once placement moves its entries.

Such a retirement MUST be recorded in `RETIRED.md` like any other (see "Record retirements so they stick"), with a reason saying its sources are gone. Because nothing judged the note untrue, the record MUST NOT exclude anything from later passes: it names no raw entries and it MUST NOT hold back material that comes back, which is distilled afresh. A note with at least one provenance entry still under `.raw/` MUST be left alone, and so MUST a note that names no provenance at all.

#### Scenario: a deleted source file takes its raw entries with it
- **GIVEN** a registered agent with two native memory files, aggregated, and a second agent with one
- **WHEN** the agent deletes one of its files and aggregation runs again
- **THEN** that file's raw entries are gone from `.raw/`, the agent's other file's and the other agent's entries remain, and an agent whose config directory is missing loses nothing

#### Scenario: a global note whose entries moved to the project partition is retired
- **GIVEN** a `global` note distilled from a `feedback` entry, and an aggregation that now files that entry into its repository's partition and removes it from `global`'s `.raw/`
- **WHEN** the distil pass runs over `global` and over the repository's partition
- **THEN** the `global` note's file is gone from `notes/`, no `global` index line mentions it, and `RETIRED.md` names it with a reason saying its raw entries are gone
- **AND** the repository's partition holds a note for that entry, so the lesson is served from exactly one partition

#### Scenario: a sources-gone retirement excludes nothing later
- **GIVEN** a note retired because its raw entries were all gone, and a note beside it one of whose two raw entries is still present
- **WHEN** a raw entry on the retired note's subject is aggregated into the partition again and the distil pass runs
- **THEN** the note with a surviving entry is untouched, and the returning entry becomes a note like any new one

### Requirement: Reintroduce no retired mechanism
This layer MUST NOT reintroduce transcript distillation, a journal lane, a Coffer-run model over memory, native-memory projection, or a per-agent capability matrix. The two readers are written as two readers; a third agent earns an abstraction, not before.

#### Scenario: register exactly the two readers
- **GIVEN** the memory layer's reader registry
- **WHEN** its readers are listed
- **THEN** there is exactly one reader for Claude Code and one for Codex
- **AND** a full aggregation and distil writes no journal directory and nothing outside `MEMORY.md`, `notes/`, `RETIRED.md` and `.raw/` in a partition

### Requirement: Update memory in one action
`POST /api/v1/memory/sync` MUST run an aggregation (see "Aggregate on an interval and on demand") and then a distil pass over every partition with something to distil — raw entries it has not yet distilled (see "Distil each raw entry into a note mechanically"), or a note none of whose raw entries is left (see "Retire a note whose raw entries are all gone") — and MUST answer with what the aggregation wrote and which partitions were distilled. A distil pass already running over a partition MUST NOT fail the action: that partition is reported as skipped. The web UI MUST offer this as one **Update memory** button — the partitions page's primary action, beside the **Automatic · hourly** control whose popover holds the switch and the interval, and also on a partition's page — and MUST NOT offer aggregation or distillation as separate buttons.

#### Scenario: one action reads new agent memory and distils it
- **GIVEN** a registered agent whose native memory gained an entry about a repository with a distilled partition
- **WHEN** `POST /api/v1/memory/sync` is called
- **THEN** the entry is written under that partition's `.raw/` and the same call distils it into the partition's notes
- **AND** the answer names that partition among the distilled ones

#### Scenario: a partition whose only change is a deleted source is still distilled
- **GIVEN** a partition whose single note was built from a native memory file the agent has since deleted, so its raw entries are gone and nothing new arrived
- **WHEN** memory is updated
- **THEN** the note is retired and the answer names that partition among the distilled ones

### Requirement: Manage memory in the web UI
People MUST manage memory in the web UI: browse partitions and the memories in them, edit or delete a memory (see "Edit a memory in the web UI or in an editor" and "Delete a memory by hand"), run **Update memory** (see "Update memory in one action"), hand a partition's tidying to the agent (see "Hand a partition's tidying to the agent"), read a partition's Delivered view (see "Show what each agent is given at session start"), and read what was retired. The REST family under `/api/v1/memory` is the web UI's own interface: it carries what that page needs and no route that no page calls, and no requirement promises it to anything else. The one route another program calls is `POST /api/v1/memory/hook`, which answers one fire of the memory hook, whose session-start answer is the composed session context. Installing, inspecting and removing an agent's delivery hook are part of that agent's Coffer connection (spec agent-registry "Connect an agent to Coffer in one action") and are not in this family.

There MUST be no command group for memory beyond one hidden entry, and no `coffer path` target for it. The single exception is `coffer memory hook`, the command every installed memory hook entry runs: it MUST be hidden from `coffer --help` and from the CLI reference, because a person never types it. A partition's notes, its index and its retirement record are plain files (see "Keep notes readable as plain files"), so the way to them is the memory root that session-start delivery names (see "Expose no memory tool and name the memory root at session start"), not a command.

#### Scenario: memory is managed from the web UI and has no command group
- **GIVEN** a running daemon with a distilled partition
- **WHEN** the command tree of `coffer` is listed, including its hidden commands
- **THEN** the only command under `memory` is `hook`, it is absent from the help output and the CLI reference, and there is no `path memory` target
- **AND** the memory page lists the partition and its memories, runs Update memory and shows the Delivered view without any command

#### Scenario: a path segment that escapes the memory root is refused
- **GIVEN** a request on the memory family naming a partition or a note slug that is `..`, holds a path separator or is hidden
- **WHEN** the route runs
- **THEN** it is refused with `MEMORY_UNSAFE_PATH` (400) and nothing outside the partition is read or written

#### Scenario: the delivery state of an agent is read on the agent's page
- **GIVEN** two registered agents, one connected to Coffer and one not
- **WHEN** the agent's detail data is read for each
- **THEN** the first's `coffer_connection` is `connected` with its `memory_hook` part installed, the second's is `disconnected`, and neither carries a last-fired time

### Requirement: Keep raw entries verbatim and hidden
Raw entries MUST be written under the partition's hidden `.raw/` directory, **verbatim**, one file per entry, and MUST be excluded from the index and from delivery. They are aggregation's output and the distil pass's input, and they are the reason a distillation can be re-run without re-reading the agents.

#### Scenario: raw entries land hidden, and only aggregation writes them
- **GIVEN** a partition with notes already distilled
- **WHEN** aggregation runs
- **THEN** the entries it wrote are under the partition's `.raw/`, which is excluded from the index and from delivery
- **AND** a distil pass over that partition writes nothing under `.raw/` (see "Keep raw entries verbatim and hidden", "Leave the raw directory to aggregation")

## REMOVED Requirements

### Requirement: Keep one topic per note
**Reason**: Each raw entry becomes one note of its own, and collapsing notes about one subject is the agent's tidying.
**Migration**: "Distil each raw entry into a note mechanically" carries the one-note-per-entry rule.

### Requirement: Keep distil out of the raw directory
**Reason**: Restated without the model-driven pass.
**Migration**: "Leave the raw directory to aggregation".

### Requirement: Record what each distil pass did
**Reason**: The record no longer carries merges, kept-nothing entries or model output.
**Migration**: "Record what each distil pass wrote and retired".

### Requirement: Edit a memory in the web UI or on disk
**Reason**: Restated without the distil writing stage, which no longer exists.
**Migration**: "Edit a memory in the web UI or in an editor".

### Requirement: Record provenance and merge by meaning
**Reason**: Provenance is carried by each note's `origins` frontmatter, which "Store each note as one Markdown file with frontmatter" requires; matching two agents' differently worded entries is a judgement about meaning that the agent makes when it tidies.
**Migration**: "Teach tidying in the coffer-guide's memory section" makes merging, with the union of origins, the agent's work.

### Requirement: Write notes in Coffer's own words
**Reason**: Distil is mechanical: a note's body is its raw entry as it stands, and Coffer writes no prose of its own.
**Migration**: "Distil each raw entry into a note mechanically" states the body rule.

### Requirement: Distil incrementally in two stages
**Reason**: No model call runs over memory, so there is no routing or writing stage.
**Migration**: "Distil each raw entry into a note mechanically" carries the interval, the event announcement and the per-entry rule.

### Requirement: Distil mechanically with no internal connection
**Reason**: The mechanical pass is the only distil pass.
**Migration**: "Distil each raw entry into a note mechanically".

### Requirement: Send file content out only for distil
**Reason**: No path of this layer sends file content to a model.
**Migration**: "Distil each raw entry into a note mechanically" forbids calling a model on any path.

### Requirement: Judge a contradiction by evidence, not by who wrote it
**Reason**: The judgement is made by the agent that tidies, not by a Coffer pass.
**Migration**: "Teach tidying in the coffer-guide's memory section" states the rule.
