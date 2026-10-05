## ADDED Requirements

### Requirement: Show a partition's memories read-only
The web UI MUST present partitions **as a table** once any exists; with none, it shows the first-run welcome every other empty surface shows — *Nothing distilled yet*, with **Update memory** and the connected agents whose memory Coffer found on this machine, or, with no agent connected, saying there is nothing to read and offering **Open Agents** to connect one. Each row MUST carry the partition's path ("Every project" for `global`), how many memories it holds, its sources (the agents it came from, "All agents" when every agent that contributed anywhere contributed here) and its state, in a column headed **Distilled**: when it was last distilled, "Not distilled yet", "Distilling…" while a pass over it runs, or "Repository missing". Healthy rows are grey: only **Repository missing** is coloured, and only that row offers a Delete, which asks first because it cannot be undone (a confirmation naming the partition, with Cancel and Delete partition). The partitions table has no section title and no count of partitions or memories, and a search box above it filters the rows by partition name and path. A partition's page MUST have no back link, and no Automatic control: its title is the partition's name alone, and its description line carries the path, the memory count and when it was last distilled (*~/code/coffer · 38 memories · distilled 2 h ago*). Its ⋯ menu holds **Reveal partition folder**, **Copy path**, **Distil history in Activity** and, only when its repository is gone, **Delete partition**. A partition not yet distilled shows no memory list: its Memories tab shows only the empty state, which offers no Update memory of its own because the header has one. Each memory in its list MUST name the agents it was learned from ("All agents" when that is every agent the partition came from). The partition listing MUST carry when its newest memory was last updated (`updated_at`, absent for a partition holding no memory), which the Overview's Memory tile words as "Last update 14 min ago". One partition's page MUST carry two tabs. **Memories** (the default) lists its memories — the web UI's label for what this spec and the disk call notes (中文 记忆条目) — beside the selected memory, with the partition's retired memories in a collapsed **Retired** group, each with the reason it was retired; choosing one opens it read-only beside the list (see below). The selected memory MUST be rendered with a meta line naming the agents it was learned from and when it was last updated, taken from its provenance ("Store each note as one Markdown file with frontmatter"), and its frontmatter MUST be shown as that metadata, not rendered as body text. The page MUST NOT show the agents' own memory: no native paths, no original agent text, no `.raw/` entry, no `MEMORY.md` index or `RETIRED.md` file, and no file tree — those stay in the data and on disk, and only this page leaves them out. The partition's own folder is reached through the partition's ⋯ menu (**Reveal partition folder**, **Copy path**); a memory's own file is reached from the memory (see below). The list and the memory MUST extend to the bottom of the window and scroll inside. The partition's page MUST offer **Tidy** in its header (see "Hand a partition's tidying to the agent"). The selected memory MUST be shown read-only and offer **Open in editor** as a visible button, and a ⋯ menu holding **Reveal in Finder** and **Delete…**; its body is rendered with find (⌘F). The page MUST NOT edit a memory: a person changes it in their own editor (see "Edit a memory in the person's own editor"). **Delete…** MUST ask first, and on confirming MUST retire the memory by hand (see "Delete a memory by hand"). A retired memory chosen from the Retired group MUST open read-only — its full title, a *Retired* tag, the date it was retired, its full reason and, when it was replaced by a memory still in the list, a **Replaced by <memory> →** link to it — and offers no Open in editor or Delete; the selection is addressed in the URL (`?retired=<index>`), and a Retired group so addressed opens expanded. The Memory page's title carries the **Experimental** tag ([experimental-features](../experimental-features/spec.md)); a partition's page does not. **Delivered** (`/memory/<uid>/delivered`) shows, read-only, the exact session-start text each agent receives in the partition's project, with a switch between agents ([web-ui](../web-ui/spec.md) "Show memory delivery on the Memory page"); it shows no hook state.

#### Scenario: browse a partition's memories with a read-only preview
- **GIVEN** the memory pages, with no partitions and then with one distilled partition that holds raw entries, a memory learned from Claude Code and Codex, and one retired memory
- **WHEN** the partitions page and the partition's page render and the memory is chosen
- **THEN** the partitions page shows the first-run welcome with none and the table with one, and the partition's page lists its memories beside the chosen one, whose meta line names Claude Code and Codex and when it was updated and whose frontmatter is not in the rendered body
- **AND** the retired memory is in a collapsed Retired group with its reason, the page shows no file tree, no `MEMORY.md`, `RETIRED.md` or `.raw/`, no native path and no agent's original text, and the chosen memory offers Open in editor and a ⋯ menu with Reveal in Finder and Delete…, and no Edit
- **AND** choosing the retired memory opens it read-only (`?retired=<index>`, group expanded) with its full title, a Retired tag, the retired date, its full reason and a **Replaced by <memory> →** link when a memory in the list replaced it, and no Open in editor or Delete…

#### Scenario: the selected memory opens in the person's editor
- **GIVEN** a partition's page with a memory selected
- **WHEN** the user chooses Open in editor, and then Reveal in Finder from its ⋯ menu
- **THEN** the daemon is asked to open the note's absolute path and then to reveal it, and the page offers no Edit
- **AND** a retired memory in the Retired group offers neither

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


### Requirement: Edit a memory in the person's own editor
A memory is its file under the partition's `notes/`, and a person MUST change it there, in their own editor, which the memory's **Open in editor** opens (see "Show a partition's memories read-only"); an agent changes it with its own file tools by the guide's memory section. No Coffer route writes a note's body. The next read of the note, the index line rendered from it and the next session's delivery carry the change.

An edited note is the note, not a suggestion: a distil pass never rewrites an existing note's body, so the edit persists until the note is retired or the derived tree is deleted. The derived tree stays disposable: deleting it and rebuilding reproduces the notes from the agents' own memory and loses every edit, and the guide says so.

#### Scenario: an edit made on disk needs no Coffer surface
- **GIVEN** a note's file under `notes/`
- **WHEN** a person changes its body in their own editor
- **THEN** the next read of the note, the index line rendered from it and the next session's delivery carry the changed text
- **AND** deleting the derived tree and rebuilding it gives back a note without that edit

## MODIFIED Requirements

### Requirement: Keep notes readable as plain files
A note MUST be readable and useful **as a file**, with no Coffer process in the loop: plain Markdown, frontmatter first, a path an agent or a human can open. The delivery path (see "Deliver the index and the notes path at session start") and the file tree (see "Show a partition's memories read-only") both depend on this, and so does the whole reason the index-plus-file shape was chosen over a search tool.

#### Scenario: open a note from disk with no daemon running
- **GIVEN** a distilled partition
- **WHEN** a note's file under `notes/` is read straight from disk, with no Coffer service involved
- **THEN** it opens with a YAML frontmatter fence carrying its title and description and continues with its Markdown body

### Requirement: Manage memory in the web UI
People MUST manage memory in the web UI: browse partitions and the memories in them, open a memory in their editor (see "Edit a memory in the person's own editor"), delete a memory (see "Delete a memory by hand"), run **Update memory** (see "Update memory in one action"), hand a partition's tidying to the agent (see "Hand a partition's tidying to the agent"), read a partition's Delivered view (see "Show what each agent is given at session start"), and read what was retired. The REST family under `/api/v1/memory` is the web UI's own interface: it carries what that page needs and no route that no page calls — no route writes a note's text, and no requirement promises it to anything else. The one route another program calls is `POST /api/v1/memory/hook`, which answers one fire of the memory hook, whose session-start answer is the composed session context. Installing, inspecting and removing an agent's delivery hook are part of that agent's Coffer connection (spec agent-registry "Connect an agent to Coffer in one action") and are not in this family.

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


### Requirement: Audit every lifecycle act
Every lifecycle act — aggregation, distil, retirement, delivery installed, removed or fired — MUST record an audit event with its actor. A memory changed in an editor is not a Coffer act and is not audited; `memory_note_edited` rows an earlier version recorded keep their wording in Activity.

#### Scenario: audit a requested aggregation and distil with their actor
- **GIVEN** a registered agent with native memory and a partition to distil
- **WHEN** a user updates memory, which requests an aggregation and then a distil pass
- **THEN** exactly one aggregation audit event and one distil audit event name that user as their actor, beside any the daemon's own worker recorded under its own actor

## REMOVED Requirements

### Requirement: Present a partition as its memories
**Reason**: The selected memory is no longer edited in the page (Coffer is not a second editor); the rest of the partition page is unchanged.
**Migration**: See "Show a partition's memories read-only".

### Requirement: Edit a memory in the web UI or in an editor
**Reason**: The web UI's note editor and its save route are removed; editing the note's file in the person's own editor was already a complete way to change it.
**Migration**: See "Edit a memory in the person's own editor". `PUT /api/v1/memory/partitions/{uid}/notes/{slug}`, the note read's `fingerprint` and `MEMORY_NOTE_CONFLICT` are removed, and `memory_note_edited` is no longer recorded.
