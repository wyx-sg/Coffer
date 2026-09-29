# Memory

## Purpose

Every agent the developer runs keeps its own memory, and none of them can see any of the others'. Claude Code accrues per-fact notes per project; Codex distils its rollouts into task groups and a profile. Both work well and neither leaves its own directory, so the developer re-teaches each agent what the other already knows. Coffer **reads those native memories, without ever writing to them**, distils them into **notes of its own** — one file per topic, in Coffer's own format, filed by repository and by `global` — and hands each agent the **index** of that set at session start, with the absolute path to read the rest the same way it reads its own memory: as files. After the start it hands over two more things (ADR [Memory Reaches a Session at Three Moments](../../../docs/decisions/memory-reaches-a-session-at-prompt-time-and-before-a-known-trap.md)): the few notes a prompt names, and — before a shell command a person has marked as a known trap — that trap's note, holding the command once. What Claude Code learns in the morning, Codex opening the same repository in the afternoon already knows — not because Coffer wrote into Codex's memory, but because Coffer handed it that note's index line.

**Coffer aggregates memory; it does not own it.** Coffer never writes an agent's native memory files, so no agent's own loop is disturbed and nothing has to be reconciled. Everything under `~/.coffer/memory/` is **derived** and may be deleted and rebuilt at any time, which is what makes it safe to rewrite aggressively. It is not a second copy of the agents' words: an agent's raw memory is an input, and the distillation into Coffer's own notes is the layer's value. Reproducing it after a delete gives back an **equivalent** set of notes, not a byte-identical one.

**Memory is not knowledge.** [Knowledge](../knowledge/spec.md) holds what the user or an agent **wrote down about the world**; this layer holds what agents **learned while working** — the user's preferences, a project's decisions, a trap already hit.

| | Memory | Knowledge |
| --- | --- | --- |
| Where it comes from | agents' native memories, read-only | the human uploads it, or writes it with an agent |
| Partitioned by | project (and `global`) | collection |
| Who authors the stored text | **Coffer**, distilling | the human or an agent, directly |
| Delivered by | **push** — the index at session start, the notes a prompt names, and a known trap's note before the command that walks into it | **pull** — the agent reaches for it |
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
Aggregation MUST NOT read session transcripts, rollouts or raw capture files. Both supported agents already distil their own; this layer starts from that output. The one reading of a transcript this layer does is the count of "Count what memory delivered and what was read", which looks only at the file paths an agent's tool calls named and never at what any message, tool result or note says.

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
Raw entries MUST be written under the partition's hidden `.raw/` directory, **verbatim**, one file per entry, and MUST be excluded from the index and from delivery. They are aggregation's output and the distil pass's input, and they are the reason a distillation can be re-run without re-reading the agents.

#### Scenario: raw entries land hidden, and only aggregation writes them
- **GIVEN** a partition with notes already distilled
- **WHEN** aggregation runs
- **THEN** the entries it wrote are under the partition's `.raw/`, which is excluded from the index and from delivery
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
An entry MUST be filed into the partition of the repository it was learned in, except that one **about the person rather than a project** MUST be filed into `global` whichever repository it came from. An entry typed `user` — the user's own preferences and standing instructions — is about the person and MUST be filed into `global`. An entry typed `feedback` — guidance on how to work — MUST be filed into the partition of the project root it carries, and into `global` only when it carries none, because such guidance is usually about working in that one repository. A source whose project root is the user's home directory MUST resolve to `global`.

#### Scenario: the Codex profile becomes global raw entries
- **GIVEN** Codex's distilled profile summary beside its `MEMORY.md`
- **WHEN** the reader reads the summary
- **THEN** the profile and the standing preferences in it come back as entries with an **empty** project root — which files them into `global` (see "File personal entries into global") — and each typed `user`
- **AND** Codex's own general-tips roll-up of what `MEMORY.md` already holds is not read as entries

#### Scenario: a feedback entry stays with its project
- **GIVEN** a `feedback` entry and a `user` entry, both learned in one repository and carrying its project root, and a `feedback` entry carrying no project root
- **WHEN** the entries are filed
- **THEN** the first `feedback` entry lands in that repository's partition, the `user` entry in `global`, and the root-less `feedback` entry in `global`

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
A **distil** pass MUST run on its own interval — the `distil` pass's switch and interval in the internal engine's upkeep settings ([internal-engine](../internal-engine/spec.md) "Carry a switch and interval for each unattended pass") — rather than after each aggregation, over every partition that holds raw entries it has not yet distilled, driven by the internal connection; a partition with no new raw entries costs no model call. It MUST be **incremental**, and it MUST be incremental in the specific sense that **no single request carries the partition's bodies**. The pass therefore has two stages.

- **Routing**: one request per batch, carrying this round's new raw entries, the **index** of the partition's existing notes and its retirement record — and no note body at all. Its output MUST be confined to four actions per entry: **merge** it into a named existing note, **open** a new note, **retire** a note it contradicts, or **keep nothing**.
- **Writing**: one request per note the routing stage actually touched, carrying that one note's body and the entries routed to it, which returns the rewritten note.

A partition of a hundred notes that gained three entries therefore costs one routing request over a hundred index lines and at most three small writing requests — never a hundred bodies. "Keep nothing" is a first-class outcome, not a failure: it is how a scratch directory's incidental material (see "Create no partition for a non-repository directory") and an agent's transient observations stay out of the store.

#### Scenario: route over the index and write only the touched notes
- **GIVEN** a partition holding several notes and one new raw entry that belongs to one of them, and an internal connection that records every request
- **WHEN** the distil pass runs
- **THEN** the routing request carries the new entry and the notes' index lines but no note body
- **AND** exactly one writing request is made, carrying only the body of the note the entry was routed to

### Requirement: Distil mechanically with no internal connection
With no internal connection configured, distil MUST still produce a usable partition **mechanically**: each raw entry becomes a note of its own, and `MEMORY.md` is written from their frontmatter. It MUST NOT be a no-op — an installation with no internal model still gets an index and a delivery, thinner rather than absent — and it MUST NOT call a model on any path. It proposes no merge and no retirement by contradiction, because both are judgements about meaning; it still retires a note whose raw entries are all gone (see "Retire a note whose raw entries are all gone"), because that is not a judgement.

#### Scenario: distil degrades to a usable index with no internal connection
- **GIVEN** a partition holding raw entries and **no** internal connection configured
- **WHEN** the distil pass runs
- **THEN** no model is called, no merge and no retirement is proposed, and each raw entry is carried through to a note of its own
- **AND** `MEMORY.md` is still written, one line per note from its frontmatter, so an installation with no internal model still gets an index and a delivery — thinner, not absent (see "Distil mechanically with no internal connection")

### Requirement: Record retirements so they stick
A retirement MUST be recorded in the partition's `RETIRED.md`: the note's title, why it was retired, and the note that replaced it when there is one. The file MUST be part of the next pass's input, so a retired subject is not reinstated from the same unchanged raw entry — this is the only mechanism that makes a deletion stick in a store whose sources are outside it, and without it every pass would re-import what the last one removed. A retired note's file MUST leave `notes/` and MUST NOT appear in the index or in delivery.

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
Delivery MUST be bounded by a ceiling, and the ceiling MUST be sized for **an index** rather than for a handful of lines. A delivery that an installed hook prints MUST also stay within **9,500 UTF-8 bytes** of text. Both agents that run the hook cut anything longer, and both cuts lose the lines that matter. Claude Code keeps a hook's output inline only up to about 10,000 characters; past that, the model sees a ~2 KB preview holding the newest few `global` lines. Codex keeps `additionalContext` only up to 2,500 tokens, counted as UTF-8 bytes / 4, and cuts the middle. A byte count bounds both, because a text is never more characters than bytes.

When the index does not fit, the trim MUST drop the oldest lines, MUST state how many were dropped, and MUST name the directory holding them. A trimmed delivery still leaves every note reachable as a file, which is why a trim here is a much smaller loss than it was under the previous design. When the two partitions compete for the ceiling, **the current repository's lines MUST be preferred over `global`'s**. The previous design spent the budget the other way round: on a live vault of 189 entries it delivered 8 lines, and **none** were about the project the session was open in.

#### Scenario: an index too large for the ceiling is trimmed and says so
- **GIVEN** a partition whose index exceeds the delivery ceiling
- **WHEN** the session context is composed
- **THEN** the payload stays at or under the ceiling, the trim drops the oldest lines rather than an arbitrary set, and the text names how many were dropped **and the directory they are in**
- **AND** the current project's lines are preferred over `global`'s when the two compete, which is the reverse of what this layer did before and the reason it delivered nothing about the project it was open in (see "Bound delivery and prefer the current repository")

#### Scenario: a hook delivery fits both agents' hook output limits
- **GIVEN** a repository partition and a `global` partition of 300 notes each, written in English or in Chinese
- **WHEN** the context is composed for a hook
- **THEN** the text is at most 9,500 UTF-8 bytes, fewer than 10,000 characters, and at most 2,500 tokens by Codex's bytes / 4 count
- **AND** only repository lines are included, and one line names how many `global` lines were dropped and the `global` notes directory, and another does the same for the repository

### Requirement: Deliver to channel turns through the system prompt
A **channel-driven turn** MUST receive the same payload through the system-prompt append the turn platform already composes ([channels](../channels/spec.md)). It MUST NOT require a hook, since Coffer owns that context itself.

#### Scenario: a channel turn carries the index without a hook
- **GIVEN** a channel-driven conversation on a registered agent with a working directory, and no delivery hook installed anywhere
- **WHEN** a turn is taken
- **THEN** the index arrives in the **system-prompt append** the turn platform already composes, resolved once per turn from that agent's key and the conversation's own cwd
- **AND** when there is nothing to deliver the turn carries no memory header at all, rather than an empty one (see "Deliver to channel turns through the system prompt")

### Requirement: Install delivery hooks explicitly and removably
For an agent the developer drives themselves, delivery MUST go through that agent's own hook mechanism, invoking Coffer's existing CLI **by absolute path**. An agent runs its hooks under a shell that need not have `~/.coffer/bin` on its `PATH`: Codex runs them under `/bin/zsh` without the user's rc files, and Claude Code started from the Dock does not inherit the login shell's `PATH`. The bare name is used only when the build cannot locate its own CLI.

Coffer's hook is **four entries**, one on each moment memory reaches a session, for both supported agents: `SessionStart` (matched on `startup|resume|clear|compact`), `UserPromptSubmit`, and `PreToolUse` and `PostToolUse` matched on the `Bash` tool. Every entry runs the same command, `coffer memory hook --agent-uid <uid> --cwd "$PWD"`, which reads the event the agent hands its hook on stdin and prints that event's JSON `hookSpecificOutput` — `additionalContext` to add context, `permissionDecision: "deny"` with a reason to hold a command — which both agents read on every event. Nothing once-per-session MAY be keyed on a process id: every session of one Codex app-server shares a parent pid, so it is keyed on the hook's `session_id`. `coffer memory context` stays the command that composes the session-start text alone.

Installation MUST be an **explicit act** on Coffer's surface: connecting the agent to Coffer, of which the hook is one part (spec agent-registry "Connect an agent to Coffer in one action"), or switching `memory` on while the agent is connected. It MUST be marker-scoped, idempotent, and removable without disturbing entries Coffer did not write. An install or a remove MUST take out Coffer's marked entries on **every** event first, so an older build's entry on another event is never left behind beside the new ones. Coffer MUST NOT install the hook silently, and MUST NOT write into any file that is an agent's *memory*: a hook lives in the agent's settings, which is a different thing.

#### Scenario: hook installation is marker-scoped and removable
- **GIVEN** an agent whose settings file already carries a foreign hook on the same lifecycle events, other events' hooks, and unrelated top-level keys
- **WHEN** delivery is installed, installed a second time, and then removed
- **THEN** install adds exactly **one** entry carrying Coffer's marker on each of `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse`, all running `coffer memory hook` by absolute path, a second install leaves one on each, and every foreign hook, every other event and every unrelated key is untouched
- **AND** remove takes out only the marked entries — dropping an event array and the top-level hooks key once they are empty — and with nothing installed it is a clean no-op that writes no file and records no audit event (see "Install delivery hooks explicitly and removably")

#### Scenario: a Codex hook fire prints the session-start JSON Codex reads
- **GIVEN** a partition with notes and a registered agent
- **WHEN** `coffer memory context --agent-uid <uid> --cwd <repository> --hook-event SessionStart` runs, and `coffer memory hook --agent-uid <uid>` runs with a Codex `SessionStart` event on stdin
- **THEN** each prints one JSON object whose `hookSpecificOutput` names `SessionStart` as its `hookEventName` and carries the composed index as `additionalContext`
- **AND** each fire is recorded, exactly as a plain-text fire is

#### Scenario: both agents' hook fires answer in the JSON each reads
- **GIVEN** a Claude Code agent and a Codex agent connected on a fake home, a distilled partition, and an armed `block` trigger
- **WHEN** each agent's installed command is run with that agent's own `UserPromptSubmit` and `PreToolUse` input on stdin
- **THEN** each prints `hookSpecificOutput` with `additionalContext` for the prompt and `permissionDecision: "deny"` with the note as `permissionDecisionReason` for the command

### Requirement: Repair stale delivery hooks
An installed hook MUST be repaired when what Coffer would write is no longer what is installed, without waiting for a user to notice. This is the delivery-hook target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"), and it runs on every pass, not only at daemon start.

A hook is a string left in somebody else's settings file, and the CLI it invokes ships in a binary that keeps moving. When `coffer memory context` stopped taking `--agent` and started taking `--agent-uid`, every hook already on disk kept passing an option that no longer existed. The agent printed a usage error at the start of every session, and this layer never reached it again. Nothing reported the failure, because detection is marker-scoped and never reads the arguments. That same marker scoping is what lets a reinstall replace an entry in place, and it is why a stale entry reads as installed.

The target therefore judges a hook by the **set of events** its entries sit on and their **whole commands**, both against what would be installed now. An older build's single `SessionStart` entry, or an older Codex entry on `UserPromptSubmit`, is thereby rewritten into the four current entries by an ordinary pass. One unreadable settings file MUST be reported as blocked without stranding the others.

For an agent that runs a hook only after the user has approved it (Codex), the target MUST also read whether the agent will run **every** installed entry. A current hook the agent will not run MUST be **reported, never written**, with the reason and the remedy (approve it with `/hooks` in Codex). Coffer MUST NOT write the agent's approval record: approving a hook is the user's act in the agent (spec agent-registry/codex "Leave Codex's internal-state tables untouched").

With `memory` on, the hooks wanted are those of every connected agent and of every agent that already carries one. A pass MUST NOT install a hook for an agent that has none, unless it runs because `memory` was just switched on or because a person applied that item. Otherwise the missing hook is reported and the agent's connection reads partial. A repair that added the hook would be an install Coffer made silently, which "Install delivery hooks explicitly and removably" forbids.

#### Scenario: a hook whose command went stale is repaired without being asked
- **GIVEN** an agent with Coffer's hook installed, and a Coffer build whose delivery command is no longer the one in that agent's settings file,
- **WHEN** a reconcile pass runs — at daemon start or on its period,
- **THEN** the entries are rewritten in place to the ones this build would install, so the next session is served rather than shown a usage error,
- **AND** an agent whose hook is already current is left untouched, and an agent with no hook is not given one.

#### Scenario: an older build's Codex hook is moved to SessionStart
- **GIVEN** a connected Codex agent whose `hooks.json` carries an older build's Coffer entry on `UserPromptSubmit` (bare `coffer`, a `$PPID` guard) beside a foreign hook on that event
- **WHEN** a reconcile pass runs on its period
- **THEN** the difference is a modification of `command` and `event` and is repaired: Coffer's entries now sit on `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse` and call the CLI by absolute path
- **AND** the foreign `UserPromptSubmit` hook is untouched and no older Coffer entry is left beside it

#### Scenario: a current Codex hook Codex has not approved is reported, not written
- **GIVEN** a connected Codex agent carrying the current hook, and no approval for its entries in Codex's `config.toml`
- **WHEN** a reconcile pass runs on its period, and again when a person applies it
- **THEN** the only difference is `trust`, and it is reported as `hook_untrusted` with the remedy "run /hooks in Codex"; nothing is written, and Coffer records no approval
- **AND** once `config.toml` records Codex's approval of every one of those entries, the next pass finds nothing to do

### Requirement: Audit every delivery fire
Coffer MUST record **an audit event for every delivery fire**, so that whether delivery is actually happening is answerable after the fact: every session start, and every prompt, guard and error fire that delivered a note. The event MUST name its moment (`session_start`, `prompt`, `guard`, `error`), the session, and the notes it carried (and, for a trigger, the trigger) — never their text. A fire is an event, not a property of the agent: the hook's per-agent status MUST report installation only, and MUST NOT carry a last-fired timestamp.

#### Scenario: every hook fire is recorded in the audit log
- **GIVEN** an agent for which delivery has been installed
- **WHEN** the installed hook fires and the served context is recorded as a delivery
- **THEN** exactly one audit event is written naming that agent as both the resource and the actor
- **AND** the per-agent installed state is unchanged by a fire, and neither installing nor reading status records a fire of its own (see "Audit every delivery fire")

#### Scenario: a prompt and a guard fire each name their moment and notes
- **GIVEN** a session that is given a note at a prompt and has a command held by a trigger
- **WHEN** the audit log is read
- **THEN** one `memory_delivery_fired` event names moment `prompt` and the note, and another names moment `guard`, the trigger and its note, and neither carries the note's text

### Requirement: Cover memory management on REST and the CLI
A REST family under `/api/v1/memory` MUST cover: list partitions and notes, show one note with its provenance, browse a partition's own directory and read one file from it, update memory (see "Update memory in one action"), compose the session context, answer one fire of the memory hook (`POST /hook`), manage triggers (see "Keep triggers in the vault, armed only by a person"), read the delivery overview and a partition's Delivered view (see "Count what memory delivered and what was read", "Show what each agent is given at session start"), and read what has been retired. The `coffer memory` CLI group MUST offer `list`, `show`, `edit`, `rm`, `sync` (update memory: an aggregation, then a distil pass over every partition that gained entries, see "Update memory in one action"), `context` (compose the session-start context), `hook` (the command every installed memory hook entry runs), `trigger` (`list`, `add`, `arm`, `disarm`, `delete`) and `delivered` (the overview, or one partition's Delivered view). It offers no `add`, because partitions are created only by aggregation (see "Provision partitions only from aggregation"), and no `enable` or `disable`, because a partition has no switch (see "Serve every partition to every agent"). A partition's notes, its index, its retirement record and its file tree are plain files (see "Keep notes readable as plain files"), so on the command line `coffer path memory [<partition>]` prints the absolute path of the memory root or of one partition, and they are read on disk; the `coffer memory` group carries no command that lists or prints a note or a file. Installing, inspecting and removing an agent's delivery hook are part of that agent's Coffer connection (spec agent-registry "Connect an agent to Coffer in one action") and are not in this family: on the command line they are `coffer agent connect|disconnect <agent>`, and `coffer agent show <agent>` carries the hook as a part of its `coffer_connection`.

#### Scenario: a partition's own directory is browsable as a file tree
- **GIVEN** a distilled partition
- **WHEN** its file tree is requested, and then one file out of it
- **THEN** the tree's root carries the partition directory's absolute path and holds `MEMORY.md`, a `notes/` directory listing one Markdown file per note, and `RETIRED.md` when anything has been retired; reading `notes/<slug>.md` returns its text — not binary, not truncated — with the absolute path of the file and of the folder holding it
- **AND** `.raw/` is not in the tree and reading a path under it is refused, the family is read-only (a write is refused with 405), and a path escaping the partition is refused with `MEMORY_UNSAFE_PATH` (400) (see "Present partitions as a table and a file tree", "Confine reads to registered agents' memory paths")

#### Scenario: locate a partition's notes from the command line
- **GIVEN** a distilled partition named `coffer`
- **WHEN** `coffer path memory coffer` runs, and then `coffer path memory` with no partition
- **THEN** the first prints the absolute path of the partition directory, which holds `MEMORY.md` and `notes/`, and the second prints the absolute memory root that holds it
- **AND** `coffer memory` offers no `partitions`, `notes`, `note`, `retired`, `ls`, `read`, `distil`, `delivery`, `delivery-install` or `delivery-remove` command, and `coffer memory context` is unchanged

#### Scenario: the agent's command-line view reports delivery state
- **GIVEN** the `memory` feature on and two registered agents, one connected by `coffer agent connect <agent>` and one not
- **WHEN** `coffer agent show <name> --json` runs for each
- **THEN** the first's `coffer_connection` is `connected` with its `memory_hook` part installed, the second's is `disconnected`, and neither carries a last-fired time

### Requirement: Present partitions as a table and a file tree
The web UI MUST present partitions **as a table** once any exists; with none, it shows the first-run welcome every other empty surface shows. One partition MUST be presented as a **file tree over its own directory** with a read-only preview beside it — the same two panes a skill's Files tab is — showing `MEMORY.md`, `notes/` and `RETIRED.md`, and MUST offer open-in-editor and reveal-in-file-manager on the previewed file. A note's frontmatter MUST be shown as metadata above its body, not rendered as body text. The tree and the preview MUST extend to the bottom of the window and scroll inside. It MUST NOT carry per-note actions: a partition is a folder of derived Markdown, and the surface that browses it says so by looking like one.

#### Scenario: browse a partition as a file tree with a read-only preview
- **GIVEN** the memory pages, with no partitions and then with one distilled partition that holds raw entries
- **WHEN** the partitions page and the partition's page render and a note is chosen in the tree
- **THEN** the partitions page shows the first-run welcome with none and the table with one, and the partition's page shows a file tree holding `MEMORY.md` and `notes/` and no `.raw/`, beside a read-only preview of the chosen note whose frontmatter is not in the rendered body
- **AND** the preview offers open-in-editor and reveal-in-file-manager and no per-note edit or delete action

### Requirement: Audit every lifecycle act
Every lifecycle act — aggregation, distil, retirement, delivery installed, removed or fired — MUST record an audit event with its actor.

#### Scenario: audit a requested aggregation and distil with their actor
- **GIVEN** a registered agent with native memory and a partition to distil
- **WHEN** a user updates memory, which requests an aggregation and then a distil pass
- **THEN** exactly one aggregation audit event and one distil audit event name that user as their actor, beside any the daemon's own worker recorded under its own actor

### Requirement: Show memory events on the vault-wide audit surface
This layer MUST NOT carry an audit surface of its own. Its events are read on the vault-wide audit surface, and every event type this layer records MUST be legible there rather than shown as a raw event code.

#### Scenario: label every memory event type on the audit surface
- **GIVEN** every audit event type the memory layer records
- **WHEN** each is rendered by the vault-wide audit surface's event labelling
- **THEN** each has a human-readable label in both interface languages rather than its raw event code

### Requirement: Run one distil pass per partition at a time
Only **one distil pass per partition** may run at a time, whoever started it. An Update memory action that finds a partition's pass in flight MUST **skip** that partition and report it as skipped rather than start a second pass or fail (see "Update memory in one action"), and the interval worker MUST **skip** a partition already being distilled. Which partitions are being rewritten right now MUST be readable. The record is per-daemon and does not outlive it.

#### Scenario: a second distil pass over the same partition is refused while the first is running
- **GIVEN** a synced partition with a distil pass already in flight, and new raw entries for it
- **WHEN** memory is updated, and the interval worker sweeps
- **THEN** neither starts nor queues a second pass over that partition: the update reports it under `skipped`, and the worker moves on to the other partitions
- **AND** the in-flight pass is readable on the shared upkeep-runs surface as `memory` on that partition; once it finishes the runs list is empty again and the next pass runs (see "Run one distil pass per partition at a time")

### Requirement: Add no table of its own
This layer MUST add **no table of its own**. Notes, raw entries, the index and partition metadata are files or existing Resource rows.

#### Scenario: keep partitions in the resources table and files only
- **GIVEN** a database upgraded to head
- **WHEN** its tables are listed after an aggregation and a distil pass
- **THEN** no table is named for memory, and each partition is one `resources` row of kind `memory`

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

### Requirement: Retire a note whose raw entries are all gone
Every distil pass — the model-driven one and the mechanical one alike — MUST first retire each note **none** of whose provenance entries is still under its partition's `.raw/`. Aggregation removes a raw entry when its source stops producing it: the agent deleted the fact, or placement now files it into a different partition (see "File personal entries into global"). A note is derived from what `.raw/` holds (see "Keep the memory tree derived and local"), so one with no source left MUST NOT stay in `notes/`, in the index or in delivery — otherwise the same lesson is served from two partitions once placement moves its entries.

Such a retirement MUST be recorded in `RETIRED.md` like any other (see "Record retirements so they stick"), with a reason saying its sources are gone. Because nothing judged the note untrue, the record MUST NOT exclude anything from later passes: it names no raw entries, and its title MUST NOT be handed to routing as a retired subject, so material that comes back is distilled afresh. A note with at least one provenance entry still under `.raw/` MUST be left alone, and so MUST a note that names no provenance at all.

#### Scenario: a global note whose entries moved to the project partition is retired
- **GIVEN** a `global` note distilled from a `feedback` entry, and an aggregation that now files that entry into its repository's partition and removes it from `global`'s `.raw/`
- **WHEN** the distil pass runs over `global` and over the repository's partition
- **THEN** the `global` note's file is gone from `notes/`, no `global` index line mentions it, and `RETIRED.md` names it with a reason saying its raw entries are gone
- **AND** the repository's partition holds a note for that entry, so the lesson is served from exactly one partition

#### Scenario: a sources-gone retirement excludes nothing later
- **GIVEN** a note retired because its raw entries were all gone, and a note beside it one of whose two raw entries is still present
- **WHEN** a raw entry on the retired note's subject is aggregated into the partition again and the distil pass runs with an internal connection
- **THEN** the note with a surviving entry is untouched, the routing request does not list the sources-gone title among the retired subjects, and the returning entry is distilled like any new one

### Requirement: Expose no memory tool and name the memory root at session start
The MCP gateway MUST expose no built-in tool for this layer: no tool that locates, reads, searches or records a note. An agent records something the way it already does, and Coffer reads it on the next pass. An agent finds a note the way it finds any file: session-start delivery (see "Deliver the index and the notes path at session start") MUST name the **absolute memory root** and state that every partition's notes are Markdown files under `<root>/<partition>/notes/`, so an agent looking for a note in a partition the session was not opened in searches that one directory with its own tools. The memory root is one directory, so one search covers every partition. On the command line `coffer path memory` prints the same root.

#### Scenario: no memory tool is listed, and delivery names the memory root
- **GIVEN** a running daemon with the `memory` feature on, a partition holding notes, and a `global` partition holding more
- **WHEN** an agent lists the gateway's tools, and the session context is composed for a cwd inside that partition's repository
- **THEN** no `coffer__recall`, no `coffer__remember` and no other memory tool is listed
- **AND** the payload names the absolute memory root that `coffer path memory` prints, and states that each partition's notes are Markdown files under `<root>/<partition>/notes/` to be searched with the agent's own tools

### Requirement: Provision partitions only from aggregation
Partitions MUST be **created by aggregation**, not by the user, and MUST NOT be created by an agent's working directory at read time.

#### Scenario: compose context and locate the memory root without creating a partition
- **GIVEN** a memory root with no partitions and a working directory inside a git repository
- **WHEN** the session context is composed for that working directory and `coffer path memory` runs
- **THEN** no partition directory and no `memory` Resource exists afterwards

### Requirement: Send file content out only for distil
File content MUST leave the machine only through the internal connection the developer configured, and only for the distil pass (see "Distil incrementally in two stages") — and not at all when none is configured (see "Distil mechanically with no internal connection"). Delivery MUST send nothing anywhere.

#### Scenario: compose context without calling any model
- **GIVEN** a distilled partition and an internal connection rigged to fail the test if it is called
- **WHEN** the session context is composed
- **THEN** it answers, and the internal connection is never called

### Requirement: Serve every partition to every agent
A partition MUST NOT carry the Resource framework's per-agent reach or an enabled switch: the kind declares itself non-toggleable ([resource-framework](../resource-framework/spec.md) "Address every resource by an immutable uid through one kind-agnostic surface"). Every partition MUST be served to **every** agent on the path Coffer itself serves — delivery (see "Deliver the index and the notes path at session start", "Expose no memory tool and name the memory root at session start"). Aggregating the memory of several agents into one place exists so that each agent can read what the others learned, so a partition is served to the agents that contributed nothing to it as much as to those that did. Serving gates **what Coffer names**, not what a process on this machine can open: a note is a file an agent is given the path to, and the layer MUST NOT present serving as a filesystem boundary it is not.

#### Scenario: a partition is registered as a resource keyed on its repository
- **GIVEN** exactly one registered agent contributing one raw entry about a repository
- **WHEN** aggregation runs
- **THEN** a `memory` Resource exists for that partition, and its config records the repository's own absolute path — the identity of a partition is the repository, so that path is what a later pass resolves it by (see "Identify a partition by its repository")
- **AND** no per-agent reach is written for it, and a request to disable it through the generic resource route is refused: the partition is served to every agent, including the one that contributed nothing to it

### Requirement: Update memory in one action
`POST /api/v1/memory/sync` and `coffer memory sync` MUST run an aggregation (see "Aggregate on an interval and on demand") and then a distil pass over every partition holding raw entries it has not yet distilled (see "Distil incrementally in two stages"), and MUST answer with what the aggregation wrote and which partitions were distilled. A distil pass already running over a partition MUST NOT fail the action: that partition is reported as skipped. The web UI MUST offer this as one **Update memory** button, on the partitions page and on a partition's page, and MUST NOT offer aggregation or distillation as separate buttons.

#### Scenario: one action reads new agent memory and distils it
- **GIVEN** a registered agent whose native memory gained an entry about a repository with a distilled partition
- **WHEN** `POST /api/v1/memory/sync` is called
- **THEN** the entry is written under that partition's `.raw/` and the same call distils it into the partition's notes
- **AND** the answer names that partition among the distilled ones

### Requirement: Retrieve the notes a prompt names
For every prompt the developer sends a hook-driven session, Coffer MUST rank the notes of the session's repository partition and of `global` against the prompt — each note's title, description, search terms and body — with a lexical ranker (BM25, CJK text as bigrams), and MUST add to the session the **top three** notes that score at or above a **relevance floor** and that this session has not already been given. Each is delivered as the absolute path of its file and its substance (see "Word delivered notes as provenance plus fact"), and the whole delivery MUST stay within **1,500 UTF-8 bytes**. A prompt of fewer than three words, or a bare nudge such as `continue`, `ok` or `继续`, MUST retrieve nothing. What a session was already given is remembered per `session_id` — the id the agent hands its hook, never a process id — for the daemon's lifetime.

The ranking index is derived: it is held in memory, rebuilt from the note files when a partition's `notes/` changes, and never written. Nothing chunks or embeds a note.

#### Scenario: a prompt brings in the notes it names
- **GIVEN** a repository partition holding a note about running `make verify` under Node 20 and unrelated notes, and a `global` partition
- **WHEN** a session opened in that repository sends the prompt "why does make verify fail with undici AbortSignal under node"
- **THEN** the hook answers with `additionalContext` naming the Node 20 note's absolute path, at most three notes in all, every one scoring at or above the floor
- **AND** the text is at most 1,500 UTF-8 bytes

#### Scenario: a short or trivial prompt retrieves nothing
- **GIVEN** a partition whose notes would match the words of the prompt
- **WHEN** the session sends `继续`, then `ok`, then a two-word prompt
- **THEN** the hook prints nothing for each, and no delivery is audited

#### Scenario: a note already delivered in the session is not delivered again
- **GIVEN** a session that was given a note for one prompt
- **WHEN** the same session sends a prompt that ranks the same note first, and a second session sends that prompt too
- **THEN** the first session is not given the note again, and the second session is

### Requirement: Guard a known trap once per session
Before a hook-driven session runs a shell command, Coffer MUST check the command against every **armed** `block` trigger whose note the session can reach — a `global` note's trigger in every session, a repository note's trigger only in that repository's sessions. The command pattern MUST be matched **from the start** of each shell segment that **executes** — the program's base name and its arguments, after any `VAR=value` prefix, or, when the program is an interpreter running a script (`bash`, `sh`, `zsh`, `python3`, `node`, …), the script's base name and its arguments — so a command that only mentions the pattern in an argument (`cat scripts/e2e.sh`) does not match while the command that runs it (`bash scripts/e2e.sh`) does; an `unless` pattern matching the whole command keeps the trigger quiet. The first matching command in a session MUST be **denied once**, through the agent's own deny decision, with the note as the reason and a line saying it is held once; the same trigger MUST NOT hold another command in that session, so the agent's next attempt passes. After a shell command, an armed `context` trigger whose error pattern the command's output shows MUST add the note as context, once per session, and MUST NOT block. A fire without a `session_id` holds nothing.

#### Scenario: a matching command is denied once with the note as the reason
- **GIVEN** an armed `block` trigger on a repository note whose command pattern matches `make verify` unless `v20` appears, and a session opened in that repository
- **WHEN** the session runs `make verify`, then runs `make verify` again
- **THEN** the first answer is `permissionDecision: "deny"` whose reason names the note's file and its rule and says it is held once
- **AND** the second answer is nothing, so the command runs, and `PATH=$HOME/.nvm/versions/node/v20.20.2/bin:$PATH make verify` in a fresh session is not held either

#### Scenario: a command that only mentions the pattern passes
- **GIVEN** an armed `block` trigger whose command pattern names `e2e`
- **WHEN** the session runs `cat scripts/e2e.sh`, then `bash scripts/e2e.sh`
- **THEN** the first is not held and the second is

#### Scenario: an error in a command's output adds the note without blocking
- **GIVEN** an armed `context` trigger whose error pattern is `timeout: command not found`
- **WHEN** a session's shell command finishes with that text in its output, and then again
- **THEN** the first `PostToolUse` answer carries the note as `additionalContext` and no deny, and the second answer is nothing

#### Scenario: a trigger on another repository's note stays quiet
- **GIVEN** an armed `block` trigger on a note in repository A's partition
- **WHEN** a session opened in repository B runs the matching command
- **THEN** nothing is held

### Requirement: Keep triggers in the vault, armed only by a person
A trigger MUST be one Markdown file in the vault, `vault/memory-triggers/<id>.md`, whose frontmatter names its note (`<partition>/<slug>`), its kind (`block` or `context`), its command, `unless` and error patterns, who proposed it, who armed it and when, and when it was created. It lives beside the derived memory tree, never inside it, so deleting and rebuilding that tree keeps every trigger, and it travels with the vault to the user's other machines ([vault-sync](../vault-sync/spec.md) "Apply knowledge, skill and memory-trigger file changes"). A trigger takes effect only while **armed**, and only a person arms one: a trigger a person writes (`POST /api/v1/memory/triggers`, `coffer memory trigger add`) is armed by that person as it is written, while a trigger the distil pass proposes for a note it judges a known trap tied to a command lands **unarmed** and does nothing until a person arms it. Triggers MUST be listed, armed, disarmed and deleted from both REST (`GET /api/v1/memory/triggers`, `POST …/{id}/arm`, `POST …/{id}/disarm`, `DELETE …/{id}`) and the CLI (`coffer memory trigger list|add|arm|disarm|delete`), each act an audit event naming the trigger and its note. Nothing is seeded: a vault has no trigger until a person writes one or distil proposes one.

#### Scenario: a proposed trigger does nothing until a person arms it
- **GIVEN** a distil pass whose writing stage returned a trigger for the note it wrote
- **WHEN** the pass finishes, and a session then runs the matching command
- **THEN** `vault/memory-triggers/` holds one file for it with `proposed_by: distil` and no `armed_by`, a `memory_trigger_proposed` event is recorded, and the command is not held
- **AND** once a person arms it with `coffer memory trigger arm <id>`, the matching command in a new session is held

#### Scenario: triggers are managed from REST and the command line
- **GIVEN** a running daemon and no triggers
- **WHEN** a person adds a trigger with `coffer memory trigger add`, disarms it over REST, arms it again from the CLI, and deletes it over REST
- **THEN** the listing shows it armed, then unarmed, then armed, then gone, its file follows each step, and `memory_trigger_added`, `memory_trigger_disarmed`, `memory_trigger_armed` and `memory_trigger_deleted` are recorded with that person as actor
- **AND** a trigger whose pattern does not compile is refused with `MEMORY_TRIGGER_INVALID` and no file is written

#### Scenario: a fresh vault has no triggers
- **GIVEN** a new vault on which memory has been aggregated and distilled without an internal connection
- **WHEN** the triggers are listed
- **THEN** there are none, and `vault/memory-triggers/` holds no file

### Requirement: Fail open when Coffer cannot answer
Every memory hook MUST fail open: when the daemon is not running, does not answer within the hook's own short timeout, or answers with an error, the hook MUST print nothing and exit 0, so memory never stops a prompt or a command because Coffer is down. A fire that can deliver nothing — a trivial prompt, a shell command no armed trigger matches — MUST be answered without contacting the daemon.

#### Scenario: the hook prints nothing and exits 0 with no daemon
- **GIVEN** no daemon running and an armed `block` trigger that matches `make verify`
- **WHEN** `coffer memory hook` is given a `SessionStart`, a `UserPromptSubmit` and a `PreToolUse` event for `make verify` on stdin
- **THEN** each run prints nothing and exits 0

### Requirement: Word delivered notes as provenance plus fact
Every note delivered at a prompt, before a command or after one MUST read as **provenance plus fact**: it names the note's file, and states the note's substance as "the user's standing rule is: …" for a `feedback` note and as "a fact they recorded: …" otherwise. Delivered text MUST NOT be phrased as an instruction to the agent.

#### Scenario: a delivered note names its file and reads as a standing rule
- **GIVEN** a `feedback` note and a `project` note that both match a prompt
- **WHEN** the prompt's delivery is composed
- **THEN** the `feedback` note's line names its absolute path and reads "the user's standing rule is: …", and the `project` note's reads "a fact they recorded: …"

### Requirement: Count what memory delivered and what was read
`GET /api/v1/memory/deliveries` and `coffer memory delivered` MUST report, for every registered agent with a delivery hook, over the last **seven days**: the number of delivery fires recorded in the audit log, the same count by moment (`session_start`, `prompt`, `guard`, `error`), when memory last reached it, and how many **distinct notes** its sessions opened. The last is read off the file paths the agent's tool calls named — a path under the memory root naming a note — and never off what a note, a tool result or a message says; when the agent's transcripts cannot be read it MUST be reported as `unavailable` rather than as zero. The report MUST NOT carry whether a hook is installed or trusted.

#### Scenario: the overview counts a week of deliveries and the notes read
- **GIVEN** a Claude Code agent with five delivery fires in the last week and one older than that, and a transcript from this week whose tool calls read two distinct notes, one of them twice
- **WHEN** the overview is read
- **THEN** it reports five deliveries split by moment, the time of the newest, and two notes read
- **AND** it carries no field saying whether the hook is installed or trusted

#### Scenario: notes read is unavailable without transcripts
- **GIVEN** a registered Codex agent whose config directory has no `sessions/` directory
- **WHEN** the overview is read
- **THEN** its notes read is `null` with status `unavailable`, and its delivery count is still reported

### Requirement: Show what each agent is given at session start
`GET /api/v1/memory/partitions/{uid}/delivered` and `coffer memory delivered <partition>` MUST return, for every registered agent with a delivery hook, the **exact text** that agent's session-start hook would add in that partition's repository — composed by the same function and under the same ceiling the hook uses — read only, and without whether a hook is installed or trusted.

#### Scenario: the Delivered view carries each agent's exact session-start text
- **GIVEN** a distilled repository partition and a registered Claude Code and Codex agent
- **WHEN** the partition's Delivered view is read
- **THEN** each agent's entry carries `SessionStart` and text equal to what `POST /api/v1/memory/hook` answers a `SessionStart` fire from that repository with
- **AND** nothing is audited and no hook state is carried

### Requirement: Leave per-turn rules to the agent's own instructions
Memory delivery MUST NOT be presented as the place for a rule about **every** turn — the language of every reply, a tone — which no retrieval or trigger addresses: such a rule belongs in the instructions the agent loads on every turn (`CLAUDE.md`, `AGENTS.md`), which the user owns. Installing or firing Coffer's memory hook MUST NOT write those files.

#### Scenario: connecting an agent leaves its instructions files untouched
- **GIVEN** a Claude Code agent with a `CLAUDE.md` and a Codex agent with an `AGENTS.md`
- **WHEN** both are connected with `memory` on and every one of their hooks fires
- **THEN** both instructions files are byte-identical afterwards
