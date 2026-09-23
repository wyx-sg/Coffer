# Memory

## Purpose

Every agent the developer runs keeps its own memory, and none of them can see any of the others'. Claude Code accrues per-fact notes per project; Codex distils its rollouts into task groups and a profile. Both work well and neither leaves its own directory, so the developer re-teaches each agent what the other already knows. Coffer **reads those native memories, without ever writing to them**, distils them into **notes of its own** — one file per topic, in Coffer's own format, filed by repository and by `global` — and hands each agent the **index** of that set at session start, with the absolute path to read the rest the same way it reads its own memory: as files. What Claude Code learns in the morning, Codex opening the same repository in the afternoon already knows — not because Coffer wrote into Codex's memory, but because Coffer handed it that note's index line.

**Coffer aggregates memory; it does not own it.** Coffer never writes an agent's native memory files, so no agent's own loop is disturbed and nothing has to be reconciled. Everything under `~/.coffer/memory/` is **derived** and may be deleted and rebuilt at any time, which is what makes it safe to rewrite aggressively. It is not a second copy of the agents' words: an agent's raw memory is an input, and the distillation into Coffer's own notes is the layer's value. Reproducing it after a delete gives back an **equivalent** set of notes, not a byte-identical one.

**Memory is not knowledge.** [Knowledge](../knowledge/spec.md) holds what the user or an agent **wrote down about the world**; this layer holds what agents **learned while working** — the user's preferences, a project's decisions, a trap already hit.

| | Memory | Knowledge |
| --- | --- | --- |
| Where it comes from | agents' native memories, read-only | the human uploads it, or writes it with an agent |
| Partitioned by | project (and `global`) | collection |
| Who authors the stored text | **Coffer**, distilling | the human or an agent, directly |
| Delivered by | **push** — the index, at session start | **pull** — the agent reaches for it |
| Can an entry be retired | yes, and must be | no; it is updated |
| If the store is lost | rebuilt, equivalently, from the agents' own copies | gone |

Both supported agents solved retrieval the same way, and neither built a search engine for it: Claude Code loads **the whole index** into every session (94 entries, ~9k tokens on the maintainer's machine) and reaches a body with a file read; Codex writes **the search terms into the index entry itself**. This layer copies that shape:

```
~/.coffer/memory/<partition>/
├── MEMORY.md     ← the index. What a session is given; what a human opens first.
├── notes/        ← Coffer's own notes. One topic per file.
├── RETIRED.md    ← what was retired, and why. Also the next pass's exclusion list.
└── .raw/         ← what was read out of the agents, verbatim. Derived, hidden.
```

Four jobs, kept apart: **`.raw/` is faithful, `notes/` is useful, `MEMORY.md` is findable, `RETIRED.md` is what makes a retirement stick.** Three earlier designs are not repeated: transcript distillation (removed 2026-09-09), session-context injection that had never once been installed on the maintainer's machine (removed 2026-09-10; delivery returns as an explicit install with every fire audited), and a budgeted digest that on a live vault delivered 8 of 189 entries, none about the current project, pointing at a tool called five times in its lifetime — an agent will not go looking for what it has not been shown.

Assumptions: each agent's native memory is read at the shape it has today, and a format change is expected to break the reader visibly and locally; both agents distil their own memory well enough to be a good source; a partition's index fits a session's opening comfortably, and the delivery ceiling exists for when it does not; one round's new raw entries plus the existing index fit one completion; and every consumer of delivery is a process on this machine with filesystem access, including a channel-driven turn, which drives a local Claude Code or Codex.

## Requirements

### Requirement: Read only registered and enabled agents' memory
Coffer MUST read the native memory of each **registered and enabled** agent, from a path derived from that agent's own `config_dir` ([agent-registry](../agent-registry/spec.md)). An agent that is not registered MUST NOT be read.

#### Scenario: read nothing from a disabled or unregistered agent
- **GIVEN** fixture memory for an enabled registered agent, for a registered agent that is disabled, and in a config directory no registered agent names
- **WHEN** aggregation runs
- **THEN** raw entries come only from the enabled agent's memory
- **AND** nothing is read from the disabled agent or the unregistered directory

### Requirement: Never write an agent's native memory
Aggregation MUST be **read-only**. Coffer MUST NOT create, modify, move, delete or reformat any file in an agent's own memory, and MUST NOT disable or reconfigure an agent's native memory. This is [Aggregate Agent Memory](../../../docs/decisions/aggregate-agent-memory-never-write-it.md)'s prohibition, retained in full and still the load-bearing constraint of this design.

#### Scenario: aggregation never modifies an agent's native memory files
- **GIVEN** fixture config directories for both supported agents, snapshotted byte-for-byte with their modification times
- **WHEN** a full aggregation reads every source out of both
- **THEN** raw entries are produced from both
- **AND** every file under either config directory is byte-identical, with an unchanged modification time — Coffer created, moved, reformatted and deleted nothing (see "Never write an agent's native memory")

### Requirement: Read no transcripts or rollouts
Coffer MUST NOT read session transcripts, rollouts or raw capture files. Both supported agents already distil their own; this layer starts from that output.

#### Scenario: list no transcript or rollout as a source
- **GIVEN** a Claude Code config directory holding a session transcript beside a project's memory directory, and a Codex home holding session rollouts beside its memory files
- **WHEN** each reader lists its sources
- **THEN** no transcript, rollout or raw capture file is among them

### Requirement: Read Claude Code and Codex memory with their search terms
v1 MUST support two readers. **Claude Code**: per-fact Markdown files under its per-project memory directories, whose frontmatter carries the entry's name, description and type. **Codex**: its `MEMORY.md` task groups — each group's applicability, preferences, reusable knowledge and failures — and its distilled profile summary. Where the source states **search terms** for an entry, as Codex's summary does for each task group, the reader MUST carry them onto the raw entry: they are the source's own answer to "what would you look this up by", and discarding them is what left the previous design's retrieval to guesswork. Each reader MUST ignore the agent's own index or roll-up file, since Coffer regenerates that role itself.

#### Scenario: a Claude Code memory file becomes a raw entry
- **GIVEN** a Claude Code per-project memory directory holding one fact file whose frontmatter carries `name`, `description` and `type`
- **WHEN** the Claude Code reader lists its sources and reads that one
- **THEN** exactly one raw entry comes back: its title is the `name`, its description the `description`, its type `feedback`, its body the prose with the frontmatter fence stripped out, its anchor the file's own stem, and its project root the project that memory directory belongs to
- **AND** the agent's own roll-up file (`MEMORY.md`) is not among the sources at all, since Coffer regenerates that role itself

#### Scenario: a Codex task group becomes raw entries carrying its own search terms
- **GIVEN** Codex's `MEMORY.md` holding two task groups, one of which records the working directory it was learned in, and a `memory_summary.md` whose `What's in Memory` section lists those groups with their search terms
- **WHEN** the Codex reader reads both files
- **THEN** one raw entry comes back per populated bullet section of each group, each carrying that group's recorded cwd as its project root
- **AND** each entry carries the **search terms** its group's summary entry lists, so the index built from it can state them rather than leaving the next agent to guess (see "Read Claude Code and Codex memory with their search terms", "Write each index line to stand on its own")
- **AND** the group's own rollout-reference subsections never surface as entries

### Requirement: Fail a broken reader loudly and in isolation
A reader that cannot parse its source — the agent changed its format — MUST fail **loudly and in isolation**: that agent contributes nothing, the surface says so with the path and the reason, the other agent's aggregation still completes, and previously distilled notes are left standing rather than deleted.

#### Scenario: an agent whose native memory shape is unreadable degrades loudly
- **GIVEN** one agent holding a memory file whose frontmatter is missing, unterminated, not a mapping, or missing its name field, and a second agent whose memory is fine
- **WHEN** aggregation runs
- **THEN** the reader raises for the offending file with that file's own path, and the pass reports one failure naming the agent, the path and the reason
- **AND** the other agent's raw entries are aggregated as normal, and notes from an earlier pass are left standing rather than deleted (see "Fail a broken reader loudly and in isolation")

### Requirement: Skip unchanged sources
Aggregation MUST skip a source file whose content hash is unchanged since the last pass, and MUST record enough per source to make that decision without re-parsing.

#### Scenario: an unchanged source file is skipped on the next sync
- **GIVEN** a source already aggregated once, whose content hash has not changed since
- **WHEN** a second pass runs
- **THEN** the source is counted as skipped and is **not read at all** — a reader rigged to raise if consulted again is never consulted
- **AND** no failure is reported and the raw entries that source produced are still on disk

### Requirement: Aggregate on an interval and on demand
Aggregation MUST run on a background worker on an interval and MUST be triggerable by hand. It MAY default to on, because it only reads the agents' files and only writes derived ones. Its switch and its interval MUST both be settable by the operator and MUST be read per pass rather than at boot ([internal-engine](../internal-engine/spec.md) "Apply a changed switch or interval without a restart").

#### Scenario: aggregation runs unattended, without anyone asking for it
- **GIVEN** the aggregate worker configured with an interval, and nobody having asked for a pass
- **WHEN** the daemon starts it
- **THEN** a pass runs **immediately**, not after the first interval elapses
- **AND** the audit actor on that pass is the worker's own, so the log can tell a scheduled pass from a requested one (see "Audit every lifecycle act")

### Requirement: Keep raw entries verbatim and hidden
Raw entries MUST be written under the partition's hidden `.raw/` directory, **verbatim**, one file per entry, and MUST be excluded from the index, from delivery and from recall. They are aggregation's output and the distil pass's input, and they are the reason a distillation can be re-run without re-reading the agents.

#### Scenario: raw entries land hidden, and only aggregation writes them
- **GIVEN** a partition with notes already distilled
- **WHEN** aggregation runs
- **THEN** the entries it wrote are under the partition's `.raw/`, which is excluded from the index, from delivery and from recall
- **AND** a distil pass over that partition writes nothing under `.raw/` (see "Keep raw entries verbatim and hidden", "Keep distil out of the raw directory")

### Requirement: Let only aggregation write raw entries
Only aggregation may write `.raw/`. A raw entry MUST carry the agent, the native path and the read time it came from, and MUST be reproducible from an unchanged source.

#### Scenario: stamp a raw entry with its agent, native path and read time
- **GIVEN** a Claude Code memory fact file aggregated once into a partition's `.raw/`
- **WHEN** the stored raw entry is read back, and the same unchanged source is aggregated again after the partition's `.raw/` is deleted
- **THEN** the entry names the agent, the fact file's native path and the time it was read
- **AND** the second aggregation writes an entry with the same id, title, description and body

### Requirement: Partition by repository plus global
A **partition** is a top-level directory under `~/.coffer/memory/` and is one `memory` Resource. There MUST be exactly one partition per repository plus one named `global`; no other partitioning axis exists.

#### Scenario: produce one partition per repository and one global
- **GIVEN** raw entries from two different repositories and one entry about the user's own preferences
- **WHEN** aggregation runs
- **THEN** exactly three partitions exist — one named for each repository and one named `global`
- **AND** each is one `memory` Resource

### Requirement: File personal entries into global
An entry MUST be filed into the partition of the repository it was learned in, except that one **about the person rather than a project** — the user's own preferences and standing instructions — MUST be filed into `global` whichever repository it came from. A source whose project root is the user's home directory MUST resolve to `global`.

#### Scenario: the Codex profile becomes global raw entries
- **GIVEN** Codex's distilled profile summary beside its `MEMORY.md`
- **WHEN** the reader reads the summary
- **THEN** the profile and the standing preferences in it come back as entries with an **empty** project root — which files them into `global` (see "File personal entries into global") — and each typed `user`
- **AND** Codex's own general-tips roll-up of what `MEMORY.md` already holds is not read as entries

### Requirement: Create partitions only by aggregation
Partitions MUST be **created by aggregation**, not by the user, and MUST NOT be created by an agent's working directory at read time.

#### Scenario: compose context and recall without creating a partition
- **GIVEN** a memory root with no partitions and a working directory inside a git repository
- **WHEN** the session context is composed for that working directory and `coffer__recall` is called
- **THEN** no partition directory and no `memory` Resource exists afterwards

### Requirement: Serve every enabled partition to every agent
A partition MUST NOT carry the Resource framework's per-agent reach. Every **enabled** partition MUST be served to **every** agent, on both paths Coffer itself serves — delivery (see "Deliver the index and the notes path at session start") and recall (see "Recall locations by literal match"). The per-agent form is withdrawn because its default worked directly against the point of aggregating: a partition was created scoped to the agents it had been aggregated from, so `memory/coffer` came out scoped to `claude-code` alone and a Codex session in the Coffer repository was served no project memory at all, while the `account*` partitions came out scoped to `codex` alone. Nobody chose any of that — a layer whose whole job is to let each agent read what the others learned was defaulting to withholding it from the one agent that had not learned it yet. `enabled` is the only gate. It gates **what Coffer serves**, not what a process on this machine can open: a note is a file an agent is given the path to, so a partition that is not delivered is one nothing points at, and the layer MUST NOT present `enabled` as a filesystem boundary it is not.

#### Scenario: a partition is registered as a resource keyed on its repository
- **GIVEN** exactly one registered agent contributing one raw entry about a repository
- **WHEN** aggregation runs
- **THEN** a `memory` Resource exists for that partition, and its config records the repository's own absolute path — the identity of a partition is the repository, so that path is what a later pass resolves it by (see "Identify a partition by its repository")
- **AND** no per-agent reach is written for it: the partition is served to every agent, including the one that contributed nothing to it, which is the whole reason the memory of several agents is aggregated into one place (see "Serve every enabled partition to every agent")

### Requirement: Identify a partition by its repository
A partition's identity is the **repository**, not a path. The main checkout, any worktree of it, and a second clone of it MUST resolve to one partition. The partition MUST be named by a readable slug — never an opaque id — and MUST record the repository's own absolute path on its Resource and restate it in its `MEMORY.md`. A name collision MUST be resolved by adding a distinguishing path segment.

#### Scenario: a worktree and its main checkout resolve to one partition
- **GIVEN** a fixture git repository, a worktree created from it, and raw entries recorded against both paths
- **WHEN** aggregation runs
- **THEN** exactly one partition exists, its name derived from the repository's own directory name, and both paths resolve to it
- **AND** a second clone of the same repository at a third path resolves to that same partition (see "Identify a partition by its repository")

### Requirement: Create no partition for a non-repository directory
A working directory that is **not** a repository MUST NOT create a partition. Its entries MUST be held for the distil pass, which decides on their merits whether they belong in `global` or nowhere. The previous design partitioned on the raw `cwd`, which turned six dated scratch folders on the maintainer's machine into six permanent partitions whose contents could never reach the project they were actually about.

#### Scenario: a directory that is not a repository gets no partition
- **GIVEN** raw entries whose project root is a plain directory under the user's home with no repository above it
- **WHEN** aggregation runs
- **THEN** no partition is created for it, and its entries are held for the distil pass to judge
- **AND** a partition whose repository has since been deleted from disk is reported as unresolvable rather than silently delivered to nobody (see "Create no partition for a non-repository directory", "Report unresolvable partitions")

### Requirement: Report unresolvable partitions
A partition whose repository can no longer be resolved MUST be reported as unresolvable on the partitions surface and MUST remain deletable. It MUST NOT be silently delivered to nobody, which is what an orphaned partition does.

#### Scenario: list an orphaned partition as unresolvable and delete it
- **GIVEN** a partition whose recorded repository has been deleted from disk
- **WHEN** the partitions are listed over `/api/v1/memory` and the partition's resource is then deleted
- **THEN** the listing marks it unresolvable
- **AND** the delete succeeds and the partition is gone from the next listing

### Requirement: Store each note as one Markdown file with frontmatter
Each note MUST be one Markdown file under its partition's `notes/`, carrying frontmatter with `title`, `description`, `type` (`user` | `feedback` | `project`), its provenance, `created_at` and `updated_at`. `description` MUST be one line and MUST be written to be read on its own: it is the index entry, and the index is what a session is actually given.

#### Scenario: write a note's frontmatter with a one-line description
- **GIVEN** a partition holding one raw entry whose description spans two lines
- **WHEN** a distil pass writes its note
- **THEN** the note is one Markdown file under `notes/` whose frontmatter carries `title`, `description`, `type`, provenance, `created_at` and `updated_at`
- **AND** its `type` is one of `user`, `feedback` or `project`, and its `description` is a single line

### Requirement: Record provenance and merge by meaning
Provenance MUST name every raw entry a note was built from, and through them every contributing agent, and MUST survive recomputation — it is what answers "which of my agents already knows this". Two agents contributing the same lesson MUST produce **one** note naming both, and the match MUST be made by the distil pass on meaning, not by a literal comparison of their words: on the maintainer's live vault, 378 entries from two agents produced **zero** cross-agent matches under literal comparison, because the two agents never phrase anything the same way.

#### Scenario: two agents' differently-worded entries distil into one note
- **GIVEN** one partition's `.raw/` holding two entries from two agents that state the same lesson in no shared phrasing, and an internal connection whose answer merges them
- **WHEN** the distil pass runs
- **THEN** the partition holds **one** note covering that lesson, and its provenance names both agents and both raw entries
- **AND** neither raw entry is modified or deleted — `.raw/` is aggregation's alone (see "Distil incrementally in two stages", "Keep distil out of the raw directory")

### Requirement: Keep the memory tree derived and local
The whole tree under `~/.coffer/memory/` MUST be derived: deleting it and re-running aggregation and distil MUST reproduce an **equivalent** partition — the same subjects, from the same sources — though not necessarily the same wording, since the notes are a distillation. It MUST NOT converge with the sync remote ([vault-sync](../vault-sync/spec.md)): it is derived from the agents installed on *this* machine, so sending it to another would send notes that machine's own next pass would recompute away. **A partition's Resource row is covered by that prohibition too, not only the files** — the `memory` kind declares `converges=False`, so the exporter withholds such rows and the applier refuses such a document. Losing the machine loses the derived tree, and that is accepted.

#### Scenario: deleting the memory tree and re-syncing reproduces an equivalent set
- **GIVEN** a distilled partition whose directories are then deleted by hand, with the source-digest cache deliberately left behind
- **WHEN** aggregation and distil run again
- **THEN** the partition is rebuilt: `.raw/` holds the same entries, `notes/` covers the same subjects, and `MEMORY.md` indexes them
- **AND** a digest match alone therefore never suppresses a rebuild — but the notes' wording is **not** required to match the deleted set, because the product is a distillation and not a copy (see "Keep the memory tree derived and local")

#### Scenario: a partition does not travel to the sync remote
- **GIVEN** a vault with a synced remote, holding a `memory` partition row and an ordinary resource of another kind
- **WHEN** the vault is exported
- **THEN** the other kind's document is written and the partition's is not — neither the derived tree nor the Resource row leaves this machine
- **AND** a partition document an older build had already published is removed by the export, and one arriving in the working tree creates no row here (see "Keep the memory tree derived and local")

### Requirement: Write notes in Coffer's own words
A note's body MUST be **Coffer's own writing**, distilled from one or more raw entries — not a copy of any of them. This reverses the previous design's rule that a stored body had to be the source's own words. That rule bought quotability and cost the product: Codex's memory is prose bullets with no titles, so carrying it verbatim produced 284 entries whose title, description and body were the same sentence three times over, against the 16 entries Codex's own index had already distilled the same material into. Quotability is preserved where it belongs — in `.raw/`, which the note's provenance points at.

#### Scenario: write the note body the distil model wrote
- **GIVEN** a partition holding one raw entry and an internal connection whose writing answer rewords it
- **WHEN** the distil pass runs
- **THEN** the note's body is the model's rewritten text, not the raw entry's body
- **AND** the raw entry still holds the original words, and the note's provenance names it

### Requirement: Keep one topic per note
Notes MUST be **one topic per file**, accumulated over time: a later raw entry on a topic already covered MUST rewrite that note, not add a second one beside it. This is the shape Claude Code's own memory has, and the shape that makes "deduplicate" and "drop what is stale" ordinary edits rather than judgement calls about which of two records to destroy.

#### Scenario: a new raw entry updates the note it belongs to rather than adding one
- **GIVEN** a partition holding a note on a topic, and a newly aggregated raw entry that adds a detail to that same topic
- **WHEN** the distil pass runs
- **THEN** that note's body is rewritten to include the detail and its provenance gains the new entry
- **AND** the number of notes is unchanged — the four actions a pass may take are *merge into an existing note*, *open a new note*, *retire a note*, and *keep nothing* (see "Distil incrementally in two stages")

### Requirement: Keep notes readable as plain files
A note MUST be readable and useful **as a file**, with no Coffer process in the loop: plain Markdown, frontmatter first, a path an agent or a human can open. The delivery path (see "Deliver the index and the notes path at session start") and the file tree (see "Present partitions as a table and a file tree") both depend on this, and so does the whole reason the index-plus-file shape was chosen over a search tool.

#### Scenario: open a note from disk with no daemon running
- **GIVEN** a distilled partition
- **WHEN** a note's file under `notes/` is read straight from disk, with no Coffer service involved
- **THEN** it opens with a YAML frontmatter fence carrying its title and description and continues with its Markdown body

### Requirement: Distil incrementally in two stages
After aggregation, a **distil** pass MUST run over each changed partition, driven by the internal connection. It MUST be **incremental**, and it MUST be incremental in the specific sense that **no single request carries the partition's bodies**. The pass therefore has two stages.

- **Routing**: one request per batch, carrying this round's new raw entries, the **index** of the partition's existing notes and its retirement record — and no note body at all. Its output MUST be confined to four actions per entry: **merge** it into a named existing note, **open** a new note, **retire** a note it contradicts, or **keep nothing**.
- **Writing**: one request per note the routing stage actually touched, carrying that one note's body and the entries routed to it, which returns the rewritten note.

A partition of a hundred notes that gained three entries therefore costs one routing request over a hundred index lines and at most three small writing requests — never a hundred bodies. "Keep nothing" is a first-class outcome, not a failure: it is how a scratch directory's incidental material (see "Create no partition for a non-repository directory") and an agent's transient observations stay out of the store.

#### Scenario: route over the index and write only the touched notes
- **GIVEN** a partition holding several notes and one new raw entry that belongs to one of them, and an internal connection that records every request
- **WHEN** the distil pass runs
- **THEN** the routing request carries the new entry and the notes' index lines but no note body
- **AND** exactly one writing request is made, carrying only the body of the note the entry was routed to

### Requirement: Distil mechanically with no internal connection
With no internal connection configured, distil MUST still produce a usable partition **mechanically**: each raw entry becomes a note of its own, and `MEMORY.md` is written from their frontmatter. It MUST NOT be a no-op — an installation with no internal model still gets an index and a delivery, thinner rather than absent — and it MUST NOT call a model on any path.

#### Scenario: distil degrades to a usable index with no internal connection
- **GIVEN** a partition holding raw entries and **no** internal connection configured
- **WHEN** the distil pass runs
- **THEN** no model is called, no merge and no retirement is proposed, and each raw entry is carried through to a note of its own
- **AND** `MEMORY.md` is still written, one line per note from its frontmatter, so an installation with no internal model still gets an index and a delivery — thinner, not absent (see "Distil mechanically with no internal connection")

### Requirement: Record retirements so they stick
A retirement MUST be recorded in the partition's `RETIRED.md`: the note's title, why it was retired, and the note that replaced it when there is one. The file MUST be part of the next pass's input, so a retired subject is not reinstated from the same unchanged raw entry — this is the only mechanism that makes a deletion stick in a store whose sources are outside it, and without it every pass would re-import what the last one removed. A retired note's file MUST leave `notes/` and MUST NOT appear in the index, in delivery or in recall.

#### Scenario: a retired note leaves the index and stays out
- **GIVEN** a partition holding a note, and a later raw entry that contradicts it
- **WHEN** the distil pass runs, and then runs again over unchanged sources
- **THEN** after the first pass the note is named in `RETIRED.md` with the note that replaced it and the reason, its file is gone from `notes/`, and no index line mentions it
- **AND** the second pass does not re-open it, because `RETIRED.md` is part of the pass's own input (see "Record retirements so they stick")

### Requirement: Keep distil out of the raw directory
Distil MUST NOT write, modify or delete anything under `.raw/`. The two passes own two directories, which is what lets a bad distillation be re-run without re-reading the agents.

#### Scenario: leave the raw directory byte-identical through a model-driven pass
- **GIVEN** a partition whose `.raw/` holds entries, snapshotted byte-for-byte, and an internal connection whose routing merges one entry, opens a note for another and retires an existing note
- **WHEN** the distil pass runs
- **THEN** every file under `.raw/` is byte-identical afterwards and no file has been added to or removed from it

### Requirement: Record what each distil pass did
A distil pass MUST record what it did — merges, new notes, retirements, and entries it kept nothing from — so a developer can answer why a note reads the way it does. Malformed model output MUST degrade to no proposals for whatever it got wrong, logged and not raised, and MUST never leave a partition without an index.

#### Scenario: survive malformed routing output and still write the index
- **GIVEN** a partition holding notes and new raw entries, and an internal connection whose routing answer is not valid output
- **WHEN** the distil pass runs
- **THEN** the pass completes without raising, proposes nothing for what the model got wrong, and reports its merges, new notes, retirements and kept-nothing counts
- **AND** the partition's `MEMORY.md` is still present afterwards

### Requirement: Deliver the index and the notes path at session start
Session-start delivery MUST carry, in this order: what is known about the developer (`global`'s index), the **whole index** of the current repository's partition, and the **absolute path** of that partition's `notes/` directory with the statement that a note's body is read as a file. It MUST NOT name a tool as the way to reach a body: every consumer of this payload — a hook-driven Claude Code session, a hook-driven Codex session, and a channel-driven turn, which runs a local agent with full filesystem access — reads files already.

#### Scenario: the composed context carries the whole index and the path to the bodies
- **GIVEN** a partition holding notes, and a `global` partition holding more
- **WHEN** the session context is composed for a cwd inside that partition's repository
- **THEN** every non-retired note in both partitions has exactly one line, rendered by the same function that writes `MEMORY.md`
- **AND** the payload names the absolute path of the partition's `notes/` directory and states that a note's body is read as a file, naming no tool for it (see "Deliver the index and the notes path at session start")

### Requirement: Write each index line to stand on its own
An index line MUST be written to be **sufficient on its own** wherever it can be: the conclusion in the line, not a pointer to it. Where the source supplied search terms (see "Read Claude Code and Codex memory with their search terms"), the line MUST state them. One function MUST render both `MEMORY.md` and the delivered line, and both surfaces MUST sort by one definition of "newest" — they were two, and drifted.

#### Scenario: state the source's search terms in the index line
- **GIVEN** a partition holding a note built from a raw entry that carried search terms, and an older note without any
- **WHEN** `MEMORY.md` is written and the session context is composed
- **THEN** the note's line states its search terms in both
- **AND** the two surfaces render the same lines in the same newest-first order

### Requirement: Bound delivery and prefer the current repository
Delivery MUST be bounded by a ceiling, and the ceiling MUST be sized for **an index** rather than for a handful of lines. When the index does not fit, the trim MUST drop the oldest lines, MUST state how many were dropped, and MUST name the directory holding them — a trimmed delivery still leaves every note reachable as a file, which is why a trim here is a much smaller loss than it was under the previous design. When the two partitions compete for the ceiling, **the current repository's lines MUST be preferred over `global`'s**. The previous design spent the budget the other way round and, on a live vault of 189 entries, delivered 8 lines of which **none** were about the project the session was open in.

#### Scenario: an index too large for the ceiling is trimmed and says so
- **GIVEN** a partition whose index exceeds the delivery ceiling
- **WHEN** the session context is composed
- **THEN** the payload stays at or under the ceiling, the trim drops the oldest lines rather than an arbitrary set, and the text names how many were dropped **and the directory they are in**
- **AND** the current project's lines are preferred over `global`'s when the two compete, which is the reverse of what this layer did before and the reason it delivered nothing about the project it was open in (see "Bound delivery and prefer the current repository")

### Requirement: Deliver to channel turns through the system prompt
A **channel-driven turn** MUST receive the same payload through the system-prompt append the turn platform already composes ([channels](../channels/spec.md)). It MUST NOT require a hook, since Coffer owns that context itself.

#### Scenario: a channel turn carries the index without a hook
- **GIVEN** a channel-driven conversation on a registered agent with a working directory, and no delivery hook installed anywhere
- **WHEN** a turn is taken
- **THEN** the index arrives in the **system-prompt append** the turn platform already composes, resolved once per turn from that agent's key and the conversation's own cwd
- **AND** when there is nothing to deliver the turn carries no memory header at all, rather than an empty one (see "Deliver to channel turns through the system prompt")

### Requirement: Install delivery hooks explicitly and removably
For an agent the developer drives themselves, delivery MUST go through that agent's own hook mechanism, invoking Coffer's existing CLI. Where the agent has a session-start event, delivery MUST use it; where it has none, delivery MUST use its earliest per-session event with a **once-per-session guard**. Installation MUST be an **explicit act** on Coffer's surface, marker-scoped, removable without disturbing entries Coffer did not write, and idempotent. Coffer MUST NOT install it silently, and MUST NOT write into any file that is an agent's *memory* — a hook lives in the agent's settings, which is a different thing.

#### Scenario: hook installation is marker-scoped and removable
- **GIVEN** an agent whose settings file already carries a foreign hook on the same lifecycle event, other events' hooks, and unrelated top-level keys
- **WHEN** delivery is installed, installed a second time, and then removed
- **THEN** install adds exactly **one** entry carrying Coffer's marker, a second install leaves one entry, and every foreign hook, every other event and every unrelated key is untouched
- **AND** remove takes out only the marked entry — dropping the event array and the top-level hooks key once they are empty — and with nothing installed it is a clean no-op that writes no file and records no audit event (see "Install delivery hooks explicitly and removably")

### Requirement: Repair stale delivery hooks
An installed hook MUST be repaired when the command Coffer would write is no longer the command that is installed, without waiting for a user to notice. A hook is a string left in somebody else's settings file, and the CLI it invokes ships in a binary that keeps moving: when `coffer memory context` stopped taking `--agent` and started taking `--agent-uid`, every hook already on disk kept passing an option that no longer existed, so the agent printed a usage error at the start of every session and this layer reached it never again. Nothing reported it, because detection is marker-scoped and never reads the arguments — which is exactly what lets a reinstall replace an entry in place, and exactly why a stale entry reads as installed. The repair MUST therefore be the install, chosen by comparing what is installed against what would be installed now, and it MUST be best-effort per agent so one unreadable settings file cannot strand the rest. It MUST NOT install a hook for an agent that has none: an agent without one chose that, and a repair that added one would be an install Coffer made silently, which "Install delivery hooks explicitly and removably" forbids.

#### Scenario: a hook whose command went stale is repaired without being asked
- **GIVEN** an agent with Coffer's hook installed, and a Coffer build whose delivery command is no longer the one in that agent's settings file,
- **WHEN** the daemon starts,
- **THEN** the entry is rewritten in place to the command this build would install, so the next session is served rather than shown a usage error,
- **AND** an agent whose hook is already current is left untouched, and an agent with no hook is not given one.

### Requirement: Audit every delivery fire
Coffer MUST record **an audit event for every delivery fire**, so that whether delivery is actually happening is answerable after the fact. A fire is an event, not a property of the agent: the per-agent delivery status MUST report installation only, and MUST NOT carry a last-fired timestamp.

#### Scenario: every hook fire is recorded in the audit log
- **GIVEN** an agent for which delivery has been installed
- **WHEN** the installed hook fires and the served context is recorded as a delivery
- **THEN** exactly one audit event is written naming that agent as both the resource and the actor
- **AND** the per-agent installed state is unchanged by a fire, and neither installing nor reading status records a fire of its own (see "Audit every delivery fire", "Show delivery state on the agent's own page")

### Requirement: Expose only coffer__recall
The MCP gateway MUST expose exactly one built-in tool for this layer, `coffer__recall`, and its description MUST state that it **locates** notes rather than returning them: matching is literal, and the answer is where to read. There MUST be no `remember` tool: an agent records something by recording it the way it already does, and Coffer reads it on the next pass.

#### Scenario: advertise recall as a locator and no remember tool
- **GIVEN** the built-in tools Coffer's gateway advertises
- **WHEN** they are listed
- **THEN** `coffer__recall` is among them and its description says it locates notes by literal match and answers with where to read
- **AND** no tool named `coffer__remember`, and no other memory tool, is listed

### Requirement: Recall locations by literal match
`coffer__recall` MUST take a word or phrase, span every enabled partition (see "Serve every enabled partition to every agent"), exclude retired notes and `.raw/`, and return each match's **absolute path**, title and description — not its body, which the caller reads for itself (see "Keep notes readable as plain files"). Matching MUST be a case-insensitive literal scan with no score, no mode and no reason in the answer, and MUST need no internal connection. Its job is to answer "where is the note about X" for a partition the session was not opened in; for the partition it *was* opened in, the index is already in front of the caller and recall should not be needed at all.

#### Scenario: recall answers with locations, and never with a retired note
- **GIVEN** a partition holding notes, one of them retired, both matching a distinctive phrase
- **WHEN** `coffer__recall` is called with that phrase
- **THEN** the active note comes back with its **absolute path**, title and description, and the retired one does not
- **AND** the answer spans every enabled partition, whichever agent is asking, and carries no score, no mode and no ranking (see "Serve every enabled partition to every agent", "Recall locations by literal match")

### Requirement: Cover memory management on REST and the CLI
A REST family under `/api/v1/memory` and a `coffer memory` CLI group MUST cover: list partitions and notes, show one note with its provenance, browse a partition's own directory and read one file from it, run an aggregation, run a distil pass, compose the session context, read what has been retired, and install/inspect/remove delivery for an agent.

#### Scenario: a partition's own directory is browsable as a file tree
- **GIVEN** a distilled partition
- **WHEN** its file tree is requested, and then one file out of it
- **THEN** the tree's root carries the partition directory's absolute path and holds `MEMORY.md`, a `notes/` directory listing one Markdown file per note, and `RETIRED.md` when anything has been retired; reading `notes/<slug>.md` returns its text — not binary, not truncated — with the absolute path of the file and of the folder holding it
- **AND** `.raw/` is reachable through the same tree but marked as derived input, the family is read-only (a write is refused with 405), and a path escaping the partition is refused with `MEMORY_UNSAFE_PATH` (400) (see "Present partitions as a table and a file tree", "Confine reads to registered agents' memory paths")

### Requirement: Present partitions as a table and a file tree
The web UI MUST present partitions **as a table** once any exists; with none, it shows the first-run welcome every other empty surface shows. One partition MUST be presented as a **file tree over its own directory** with a read-only preview beside it — the same two panes a skill's Files tab is — showing `MEMORY.md`, `notes/`, `RETIRED.md` and `.raw/`, and MUST offer open-in-editor and reveal-in-file-manager on the previewed file. It MUST NOT carry per-note actions: a partition is a folder of derived Markdown, and the surface that browses it says so by looking like one.

#### Scenario: browse a partition as a file tree with a read-only preview
- **GIVEN** the memory pages, with no partitions and then with one distilled partition
- **WHEN** the partitions page and the partition's page render and a note is chosen in the tree
- **THEN** the partitions page shows the first-run welcome with none and the table with one, and the partition's page shows a file tree holding `MEMORY.md` and `notes/` beside a read-only preview of the chosen note
- **AND** the preview offers open-in-editor and reveal-in-file-manager and no per-note edit or delete action

### Requirement: Audit every lifecycle act
Every lifecycle act — aggregation, distil, retirement, delivery installed, removed or fired — MUST record an audit event with its actor. A recall MUST record the usual `mcp_invocations` row and nothing about its query or results.

#### Scenario: audit a requested aggregation and distil with their actor
- **GIVEN** a registered agent with native memory and a partition to distil
- **WHEN** a user requests an aggregation and then a distil pass
- **THEN** exactly one aggregation audit event and one distil audit event name that user as their actor, beside any the daemon's own worker recorded under its own actor

### Requirement: Show delivery state on the agent's own page
Per-agent delivery state MUST be presented on **that agent's own detail page**, not on the partitions surface. That surface answers one question — installed or not; firing is read as events on the audit surface.

#### Scenario: show installed or not on the agent page
- **GIVEN** an agent's detail page, for an agent with delivery installed and one without
- **WHEN** its memory delivery section renders
- **THEN** it states whether delivery is installed and offers the matching install or remove action
- **AND** it shows no last-fired time

### Requirement: Show memory events on the vault-wide audit surface
This layer MUST NOT carry an audit surface of its own. Its events are read on the vault-wide audit surface, and every event type this layer records MUST be legible there rather than shown as a raw event code.

#### Scenario: label every memory event type on the audit surface
- **GIVEN** every audit event type the memory layer records
- **WHEN** each is rendered by the vault-wide audit surface's event labelling
- **THEN** each has a human-readable label in both interface languages rather than its raw event code

### Requirement: Run one distil pass per partition at a time
Only **one distil pass per partition** may run at a time, whoever started it. A manual trigger arriving while a pass is in flight MUST be **refused** (`UPKEEP_ALREADY_RUNNING`, 409) rather than queued, and the interval worker MUST **skip** a partition already being distilled. Which partitions are being rewritten right now MUST be readable. The record is per-daemon and does not outlive it.

#### Scenario: a second distil pass over the same partition is refused while the first is running
- **GIVEN** a synced partition with a distil pass already in flight
- **WHEN** a second pass over that same partition is requested
- **THEN** it is **refused** with `UPKEEP_ALREADY_RUNNING` (409) rather than queued
- **AND** the in-flight pass is readable on the shared upkeep-runs surface as `memory` on that partition; once it finishes the runs list is empty again and the next request runs (see "Run one distil pass per partition at a time")

### Requirement: Add no table of its own
This layer MUST add **no table of its own**. Notes, raw entries, the index and partition metadata are files or existing Resource rows.

#### Scenario: keep partitions in the resources table and files only
- **GIVEN** a database upgraded to head
- **WHEN** its tables are listed after an aggregation and a distil pass
- **THEN** no table is named for memory, and each partition is one `resources` row of kind `memory`

### Requirement: Send content out only for distil
File content MUST leave the machine only through the internal connection the developer configured, and only for the distil pass (see "Distil incrementally in two stages") — and not at all when none is configured (see "Distil mechanically with no internal connection"). Delivery and recall MUST send nothing anywhere.

#### Scenario: compose context and recall without calling any model
- **GIVEN** a distilled partition and an internal connection rigged to fail the test if it is called
- **WHEN** the session context is composed and `coffer__recall` is called
- **THEN** both answer, and the internal connection is never called

### Requirement: Confine reads to registered agents' memory paths
Reading MUST be confined to the memory paths of registered agents' config directories. Every path built from a source's contents MUST pass a traversal guard.

#### Scenario: refuse a path segment built from source contents that escapes
- **GIVEN** a partition name or raw entry id taken from a source's contents that is `..`, contains a path separator, or is hidden
- **WHEN** a path under the memory root is built from it
- **THEN** it is refused with `UnsafeMemoryPath` rather than resolved outside the partition

### Requirement: Reintroduce no retired mechanism
This layer MUST NOT reintroduce transcript distillation, a journal lane, native-memory projection, or a per-agent capability matrix. The two readers are written as two readers; a third agent earns an abstraction, not before.

#### Scenario: register exactly the two readers
- **GIVEN** the memory layer's reader registry
- **WHEN** its readers are listed
- **THEN** there is exactly one reader for Claude Code and one for Codex
- **AND** a full aggregation and distil writes no journal directory and nothing outside `MEMORY.md`, `notes/`, `RETIRED.md` and `.raw/` in a partition
