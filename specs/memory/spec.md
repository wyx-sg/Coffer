# Feature Specification: Memory

**Status**: Accepted
**Folder name**: this spec lives at `specs/memory/`, the spec id every inbound link and `scripts/audit_acceptance.py` keys on.

**Input**: Every agent the developer runs keeps its own memory, and none of them can see any of the others'. Claude Code accrues per-fact notes per project; Codex distils its rollouts into task groups and a profile. Both work well and neither leaves its own directory, so the developer re-teaches each agent what the other already knows. Coffer **reads those native memories, without ever writing to them**, distils them into **notes of its own** — one file per topic, in Coffer's own format, filed by project — and hands each agent the **index** of that set at session start, with the absolute path to read the rest the same way it reads its own memory: as files.

## The principle this layer answers to

**Coffer aggregates memory; it does not own it.** Every rule below follows from that. Coffer never writes an agent's native memory files, so no agent's own loop is disturbed and nothing has to be reconciled. Everything under `~/.coffer/memory/` is **derived** and may be deleted and rebuilt at any time, which is what makes it safe to rewrite aggressively.

What it is *not* is a second copy of the agents' words. An agent's raw memory is an input, not the product: Claude Code writes one file per topic and Codex writes a task group per session, and mixing the two verbatim yields neither. Coffer distils them into **its own notes**, and that distillation is the layer's actual value. Reproducing it after a delete gives back an **equivalent** set of notes, not a byte-identical one — a weaker guarantee than this layer used to make, and the price of the product being a distillation rather than a copy (FR-019).

## Memory is not knowledge

Spec [knowledge](../knowledge/spec.md) holds what the user or an agent **wrote down about the world**: a platform's API contract, a service's owner, an uploaded document. This layer holds what agents **learned while working**: the user's preferences, a project's decisions, a trap already hit. They are separate layers because they differ in every dimension that shapes a design.

| | Memory | Knowledge |
| --- | --- | --- |
| Where it comes from | agents' native memories, read-only | the human uploads it, or writes it with an agent |
| Partitioned by | project (and `global`) | collection |
| Who authors the stored text | **Coffer**, distilling | the human or an agent, directly |
| Delivered by | **push** — the index, at session start | **pull** — the agent reaches for it |
| Can an entry be retired | yes, and must be | no; it is updated |
| If the store is lost | rebuilt, equivalently, from the agents' own copies | gone |

## The shape this layer settled on

Both supported agents solved retrieval the same way, and neither built a search engine for it. Claude Code keeps one file per topic and an index over them, and loads **the whole index** into every session — 94 entries, ~9k tokens on the maintainer's machine — reaching a note's body with an ordinary file read. Codex keeps three tiers (raw capture, distilled task groups, an 11 KB summary index) and writes **the search terms into the index entry itself**, so the agent never has to guess a word.

This layer copies that shape rather than inventing a third one:

```
~/.coffer/memory/<partition>/
├── MEMORY.md     ← the index. What a session is given; what a human opens first.
├── notes/        ← Coffer's own notes. One topic per file.
├── RETIRED.md    ← what was retired, and why. Also the next pass's exclusion list.
└── .raw/         ← what was read out of the agents, verbatim. Derived, hidden.
```

Four jobs, kept apart: **`.raw/` is faithful, `notes/` is useful, `MEMORY.md` is findable, `RETIRED.md` is what makes a retirement stick.**

## What this does not repeat

**Transcript distillation** (removed 2026-09-09) read session transcripts and wrote a journal; this layer does not read a transcript at all — Claude Code and Codex each already distil their own, far better than Coffer did, and this layer starts from their output (FR-003).

**Session-context injection** (removed 2026-09-10) was a working hook that had never once been installed on the maintainer's machine. Delivery returns with the failure addressed head-on: installation is an explicit act with a visible outcome, and every fire is an audit event, so "it is installed" and "it is running" are separately answerable (FR-033, FR-039).

**A budgeted digest of a handful of facts** (this layer's own first design, replaced here) pushed the top few lines of a partition under a ~600-token ceiling and told the agent to call a tool for the rest. Measured on the maintainer's live vault it delivered **8 of 189** entries, every one of them from `global` because `global` was spent first, so the current project's notes never appeared at all — and the tool it pointed at was called **five times in its lifetime, none in the three weeks before the measurement**. The lesson is not that the budget was too small. It is that an agent will not go looking for what it has not been shown, and that an index it has been shown entirely needs no search at all.

## User Scenarios & Testing

### User Story 1 — What one agent learns, the others know (Priority: P1)

In the morning Claude Code learns that this repository must be developed in a worktree. In the afternoon the developer opens Codex on the same repository, and it already knows — not because Coffer wrote into Codex's memory, but because Coffer handed it that note's index entry at session start.

**Independent Test**: with both agents registered against fixture config directories, run a sync and a distil; confirm the note built from Claude Code's memory appears in the index composed for Codex, and that Codex's own memory files are byte-identical to before.

### User Story 2 — Two agents' words become one note (Priority: P1)

Claude Code recorded that this repo's worktrees have no `.venv`; Codex recorded the same trap in its own prose, in a task group. They share no phrasing, so no literal comparison will ever match them. Coffer distils both into **one note**, which names both agents as its sources.

**Independent Test**: seed each agent's fixture memory with the same lesson in unmistakably different words; distil; confirm one note results and its provenance names both agents.

### User Story 3 — Memory is filed by repository, and by `global` (Priority: P1)

Notes about a repository belong to that repository — whether they were learned in its main checkout, in a worktree, or in a second clone. Notes about the developer belong everywhere. A directory that is not a repository at all — a dated scratch folder a session happened to run in — gets no partition of its own; what was learned there is judged on its merits and either kept in `global` or not kept.

**Independent Test**: aggregate from a fixture repository, a worktree of it, and a non-repository directory; confirm the first two resolve to one partition, that the third creates none, and that a preference learned in any of them lands in `global`.

### User Story 4 — The session opens with the index, and the notes are files (Priority: P1)

A session starts with the whole index of this project's memory plus the index of what is known about the developer — every entry, one line each, the conclusion written into the line so most of them need no follow-up. Beneath it is the absolute path of the directory those notes live in. When the agent wants a body, it reads the file, exactly as it reads its own memory.

**Independent Test**: compose the context for a partition; confirm every non-retired note has a line, that the payload carries the partition's absolute notes path, and that reading a path named in it returns that note's text.

### User Story 5 — A superseded note stops being delivered, and says why (Priority: P2)

An older note recorded that a mechanism shipped; a newer one records that it was removed. Coffer retires the older, records what replaced it, and stops delivering it — and because the retirement is written down, the next pass does not read the same raw entry and reinstate it.

**Independent Test**: distil two rounds whose second contradicts the first; confirm the first note is in `RETIRED.md` with its replacement named and absent from the index; run a third pass over unchanged sources and confirm it is not reinstated.

### User Story 6 — Delivery is installed on purpose, and visibly (Priority: P1)

Session-start delivery requires touching an agent's own settings, so Coffer never does it silently. The developer installs it from Coffer and sees, on that agent's own page, that it is installed. Whether it has actually fired is a separate question answered separately: every fire is an audit event.

**Independent Test**: install into a fixture agent config, confirm the entry is marker-scoped and removable, and confirm the per-agent status reports installation and carries no last-fired field; then serve one context with `record_fired` set and confirm one audit event names that agent.

## Acceptance Scenarios

### Scenario: a Claude Code memory file becomes a raw entry

- **Given** a Claude Code per-project memory directory holding one fact file whose frontmatter carries `name`, `description` and `type`
- **When** the Claude Code reader lists its sources and reads that one
- **Then** exactly one raw entry comes back: its title is the `name`, its description the `description`, its type `feedback`, its body the prose with the frontmatter fence stripped out, its anchor the file's own stem, and its project root the project that memory directory belongs to
- **And** the agent's own roll-up file (`MEMORY.md`) is not among the sources at all, since Coffer regenerates that role itself

### Scenario: a Codex task group becomes raw entries carrying its own search terms

- **Given** Codex's `MEMORY.md` holding two task groups, one of which records the working directory it was learned in, and a `memory_summary.md` whose `What's in Memory` section lists those groups with their search terms
- **When** the Codex reader reads both files
- **Then** one raw entry comes back per populated bullet section of each group, each carrying that group's recorded cwd as its project root
- **And** each entry carries the **search terms** its group's summary entry lists, so the index built from it can state them rather than leaving the next agent to guess (FR-004, FR-029)
- **And** the group's own rollout-reference subsections never surface as entries

### Scenario: the Codex profile becomes global raw entries

- **Given** Codex's distilled profile summary beside its `MEMORY.md`
- **When** the reader reads the summary
- **Then** the profile and the standing preferences in it come back as entries with an **empty** project root — which files them into `global` (FR-011) — and each typed `user`
- **And** Codex's own general-tips roll-up of what `MEMORY.md` already holds is not read as entries

### Scenario: aggregation never modifies an agent's native memory files

- **Given** fixture config directories for both supported agents, snapshotted byte-for-byte with their modification times
- **When** a full aggregation reads every source out of both
- **Then** raw entries are produced from both
- **And** every file under either config directory is byte-identical, with an unchanged modification time — Coffer created, moved, reformatted and deleted nothing (FR-002)

### Scenario: raw entries land hidden, and only aggregation writes them

- **Given** a partition with notes already distilled
- **When** aggregation runs
- **Then** the entries it wrote are under the partition's `.raw/`, which is excluded from the index, from delivery and from recall
- **And** a distil pass over that partition writes nothing under `.raw/` (FR-008, FR-026)

### Scenario: aggregation runs unattended, without anyone asking for it

- **Given** the aggregate worker configured with an interval, and nobody having asked for a pass
- **When** the daemon starts it
- **Then** a pass runs **immediately**, not after the first interval elapses
- **And** the audit actor on that pass is the worker's own, so the log can tell a scheduled pass from a requested one (FR-038)

### Scenario: an unchanged source file is skipped on the next sync

- **Given** a source already aggregated once, whose content hash has not changed since
- **When** a second pass runs
- **Then** the source is counted as skipped and is **not read at all** — a reader rigged to raise if consulted again is never consulted
- **And** no failure is reported and the raw entries that source produced are still on disk

### Scenario: a worktree and its main checkout resolve to one partition

- **Given** a fixture git repository, a worktree created from it, and raw entries recorded against both paths
- **When** aggregation runs
- **Then** exactly one partition exists, its name derived from the repository's own directory name, and both paths resolve to it
- **And** a second clone of the same repository at a third path resolves to that same partition (FR-014)

### Scenario: a directory that is not a repository gets no partition

- **Given** raw entries whose project root is a plain directory under the user's home with no repository above it
- **When** aggregation runs
- **Then** no partition is created for it, and its entries are held for the distil pass to judge
- **And** a partition whose repository has since been deleted from disk is reported as unresolvable rather than silently delivered to nobody (FR-015, FR-016)

### Scenario: a partition is registered as a resource keyed on its repository

- **Given** exactly one registered agent contributing one raw entry about a repository
- **When** aggregation runs
- **Then** a `memory` Resource exists for that partition, and its config records the repository's own absolute path — the identity of a partition is the repository, so that path is what a later pass resolves it by (FR-014)
- **And** no per-agent reach is written for it: the partition is served to every agent, including the one that contributed nothing to it, which is the whole reason the memory of several agents is aggregated into one place (FR-013)

### Scenario: two agents' differently-worded entries distil into one note

- **Given** one partition's `.raw/` holding two entries from two agents that state the same lesson in no shared phrasing, and an internal connection whose answer merges them
- **When** the distil pass runs
- **Then** the partition holds **one** note covering that lesson, and its provenance names both agents and both raw entries
- **And** neither raw entry is modified or deleted — `.raw/` is aggregation's alone (FR-023, FR-026)

### Scenario: a new raw entry updates the note it belongs to rather than adding one

- **Given** a partition holding a note on a topic, and a newly aggregated raw entry that adds a detail to that same topic
- **When** the distil pass runs
- **Then** that note's body is rewritten to include the detail and its provenance gains the new entry
- **And** the number of notes is unchanged — the four actions a pass may take are *merge into an existing note*, *open a new note*, *retire a note*, and *keep nothing* (FR-023)

### Scenario: a retired note leaves the index and stays out

- **Given** a partition holding a note, and a later raw entry that contradicts it
- **When** the distil pass runs, and then runs again over unchanged sources
- **Then** after the first pass the note is named in `RETIRED.md` with the note that replaced it and the reason, its file is gone from `notes/`, and no index line mentions it
- **And** the second pass does not re-open it, because `RETIRED.md` is part of the pass's own input (FR-025)

### Scenario: distil degrades to a usable index with no internal connection

- **Given** a partition holding raw entries and **no** internal connection configured
- **When** the distil pass runs
- **Then** no model is called, no merge and no retirement is proposed, and each raw entry is carried through to a note of its own
- **And** `MEMORY.md` is still written, one line per note from its frontmatter, so an installation with no internal model still gets an index and a delivery — thinner, not absent (FR-024)

### Scenario: a second distil pass over the same partition is refused while the first is running

- **Given** a synced partition with a distil pass already in flight
- **When** a second pass over that same partition is requested
- **Then** it is **refused** with `UPKEEP_ALREADY_RUNNING` (409) rather than queued
- **And** the in-flight pass is readable on the shared upkeep-runs surface as `memory` on that partition; once it finishes the runs list is empty again and the next request runs (FR-041)

### Scenario: deleting the memory tree and re-syncing reproduces an equivalent set

- **Given** a distilled partition whose directories are then deleted by hand, with the source-digest cache deliberately left behind
- **When** aggregation and distil run again
- **Then** the partition is rebuilt: `.raw/` holds the same entries, `notes/` covers the same subjects, and `MEMORY.md` indexes them
- **And** a digest match alone therefore never suppresses a rebuild — but the notes' wording is **not** required to match the deleted set, because the product is a distillation and not a copy (FR-019, SC-002)

### Scenario: a partition's own directory is browsable as a file tree

- **Given** a distilled partition
- **When** its file tree is requested, and then one file out of it
- **Then** the tree's root carries the partition directory's absolute path and holds `MEMORY.md`, a `notes/` directory listing one Markdown file per note, and `RETIRED.md` when anything has been retired; reading `notes/<slug>.md` returns its text — not binary, not truncated — with the absolute path of the file and of the folder holding it
- **And** `.raw/` is reachable through the same tree but marked as derived input, the family is read-only (a write is refused with 405), and a path escaping the partition is refused with `MEMORY_UNSAFE_PATH` (400) (FR-037, FR-044)

### Scenario: a partition does not travel to the sync remote

- **Given** a vault with a synced remote, holding a `memory` partition row and an ordinary resource of another kind
- **When** the vault is exported
- **Then** the other kind's document is written and the partition's is not — neither the derived tree nor the Resource row leaves this machine
- **And** a partition document an older build had already published is removed by the export, and one arriving in the working tree creates no row here (FR-019)

### Scenario: the composed context carries the whole index and the path to the bodies

- **Given** a partition holding notes, and a `global` partition holding more
- **When** the session context is composed for a cwd inside that partition's repository
- **Then** every non-retired note in both partitions has exactly one line, rendered by the same function that writes `MEMORY.md`
- **And** the payload names the absolute path of the partition's `notes/` directory and states that a note's body is read as a file, naming no tool for it (FR-028)

### Scenario: an index too large for the ceiling is trimmed and says so

- **Given** a partition whose index exceeds the delivery ceiling
- **When** the session context is composed
- **Then** the payload stays at or under the ceiling, the trim drops the oldest lines rather than an arbitrary set, and the text names how many were dropped **and the directory they are in**
- **And** the current project's lines are preferred over `global`'s when the two compete, which is the reverse of what this layer did before and the reason it delivered nothing about the project it was open in (FR-030)

### Scenario: a channel turn carries the index without a hook

- **Given** a channel-driven conversation on a registered agent with a working directory, and no delivery hook installed anywhere
- **When** a turn is taken
- **Then** the index arrives in the **system-prompt append** the turn platform already composes, resolved once per turn from that agent's key and the conversation's own cwd
- **And** when there is nothing to deliver the turn carries no memory header at all, rather than an empty one (FR-031)

### Scenario: hook installation is marker-scoped and removable

- **Given** an agent whose settings file already carries a foreign hook on the same lifecycle event, other events' hooks, and unrelated top-level keys
- **When** delivery is installed, installed a second time, and then removed
- **Then** install adds exactly **one** entry carrying Coffer's marker, a second install leaves one entry, and every foreign hook, every other event and every unrelated key is untouched
- **And** remove takes out only the marked entry — dropping the event array and the top-level hooks key once they are empty — and with nothing installed it is a clean no-op that writes no file and records no audit event (FR-032)

### Scenario: every hook fire is recorded in the audit log

- **Given** an agent for which delivery has been installed
- **When** the installed hook fires and the served context is recorded as a delivery
- **Then** exactly one audit event is written naming that agent as both the resource and the actor
- **And** the per-agent installed state is unchanged by a fire, and neither installing nor reading status records a fire of its own (FR-033, FR-039)

### Scenario: recall answers with locations, and never with a retired note

- **Given** a partition holding notes, one of them retired, both matching a distinctive phrase
- **When** `coffer__recall` is called with that phrase
- **Then** the active note comes back with its **absolute path**, title and description, and the retired one does not
- **And** the answer spans every enabled partition, whichever agent is asking, and carries no score, no mode and no ranking (FR-013, FR-035)

### Scenario: an agent whose native memory shape is unreadable degrades loudly

- **Given** one agent holding a memory file whose frontmatter is missing, unterminated, not a mapping, or missing its name field, and a second agent whose memory is fine
- **When** aggregation runs
- **Then** the reader raises for the offending file with that file's own path, and the pass reports one failure naming the agent, the path and the reason
- **And** the other agent's raw entries are aggregated as normal, and notes from an earlier pass are left standing rather than deleted (FR-005, SC-006)

## Requirements

### Aggregation — the raw layer

- **FR-001**: Coffer MUST read the native memory of each **registered and enabled** agent, from a path derived from that agent's own `config_dir` (spec [agent-registry](../agent-registry/spec.md)). An agent that is not registered MUST NOT be read.
- **FR-002**: Aggregation MUST be **read-only**. Coffer MUST NOT create, modify, move, delete or reformat any file in an agent's own memory, and MUST NOT disable or reconfigure an agent's native memory. This is [Aggregate Agent Memory](../../docs/decisions/aggregate-agent-memory-never-write-it.md)'s prohibition, retained in full and still the load-bearing constraint of this design.
- **FR-003**: Coffer MUST NOT read session transcripts, rollouts or raw capture files. Both supported agents already distil their own; this layer starts from that output.
- **FR-004**: v1 MUST support two readers. **Claude Code**: per-fact Markdown files under its per-project memory directories, whose frontmatter carries the entry's name, description and type. **Codex**: its `MEMORY.md` task groups — each group's applicability, preferences, reusable knowledge and failures — and its distilled profile summary. Where the source states **search terms** for an entry, as Codex's summary does for each task group, the reader MUST carry them onto the raw entry: they are the source's own answer to "what would you look this up by", and discarding them is what left the previous design's retrieval to guesswork. Each reader MUST ignore the agent's own index or roll-up file, since Coffer regenerates that role itself.
- **FR-005**: A reader that cannot parse its source — the agent changed its format — MUST fail **loudly and in isolation**: that agent contributes nothing, the surface says so with the path and the reason, the other agent's aggregation still completes, and previously distilled notes are left standing rather than deleted.
- **FR-006**: Aggregation MUST skip a source file whose content hash is unchanged since the last pass, and MUST record enough per source to make that decision without re-parsing.
- **FR-007**: Aggregation MUST run on a background worker on an interval and MUST be triggerable by hand. It MAY default to on, because it only reads the agents' files and only writes derived ones. Its switch and its interval MUST both be settable by the operator and MUST be read per pass rather than at boot (spec [provider-switching](../provider-switching/spec.md) E3a).
- **FR-008**: Raw entries MUST be written under the partition's hidden `.raw/` directory, **verbatim**, one file per entry, and MUST be excluded from the index, from delivery and from recall. They are aggregation's output and the distil pass's input, and they are the reason a distillation can be re-run without re-reading the agents.
- **FR-009**: Only aggregation may write `.raw/`. A raw entry MUST carry the agent, the native path and the read time it came from, and MUST be reproducible from an unchanged source.

### Partitions

- **FR-010**: A **partition** is a top-level directory under `~/.coffer/memory/` and is one `memory` Resource. There MUST be exactly one partition per repository plus one named `global`; no other partitioning axis exists.
- **FR-011**: An entry MUST be filed into the partition of the repository it was learned in, except that one **about the person rather than a project** — the user's own preferences and standing instructions — MUST be filed into `global` whichever repository it came from. A source whose project root is the user's home directory MUST resolve to `global`.
- **FR-012**: Partitions MUST be **created by aggregation**, not by the user, and MUST NOT be created by an agent's working directory at read time.
- **FR-013**: A partition MUST NOT carry the Resource framework's per-agent reach. Every **enabled** partition MUST be served to **every** agent, on both paths Coffer itself serves — delivery (FR-028) and recall (FR-035). The per-agent form is withdrawn because its default worked directly against the point of aggregating: a partition was created scoped to the agents it had been aggregated from, so `memory/coffer` came out scoped to `claude-code` alone and a Codex session in the Coffer repository was served no project memory at all, while the `account*` partitions came out scoped to `codex` alone. Nobody chose any of that — a layer whose whole job is to let each agent read what the others learned was defaulting to withholding it from the one agent that had not learned it yet. `enabled` is the only gate. It gates **what Coffer serves**, not what a process on this machine can open: a note is a file an agent is given the path to (FR-028), so a partition that is not delivered is one nothing points at, and the layer MUST NOT present `enabled` as a filesystem boundary it is not.
- **FR-014**: A partition's identity is the **repository**, not a path. The main checkout, any worktree of it, and a second clone of it MUST resolve to one partition. The partition MUST be named by a readable slug — never an opaque id — and MUST record the repository's own absolute path on its Resource and restate it in its `MEMORY.md`. A name collision MUST be resolved by adding a distinguishing path segment.
- **FR-015**: A working directory that is **not** a repository MUST NOT create a partition. Its entries MUST be held for the distil pass, which decides on their merits whether they belong in `global` or nowhere. The previous design partitioned on the raw `cwd`, which turned six dated scratch folders on the maintainer's machine into six permanent partitions whose contents could never reach the project they were actually about.
- **FR-016**: A partition whose repository can no longer be resolved MUST be reported as unresolvable on the partitions surface and MUST remain deletable. It MUST NOT be silently delivered to nobody, which is what an orphaned partition does today.

### Notes — Coffer's own layer

- **FR-017**: Each note MUST be one Markdown file under its partition's `notes/`, carrying frontmatter with `title`, `description`, `type` (`user` | `feedback` | `project`), its provenance, `created_at` and `updated_at`. `description` MUST be one line and MUST be written to be read on its own: it is the index entry, and the index is what a session is actually given.
- **FR-018**: Provenance MUST name every raw entry a note was built from, and through them every contributing agent, and MUST survive recomputation — it is what answers "which of my agents already knows this". Two agents contributing the same lesson MUST produce **one** note naming both, and the match MUST be made by the distil pass on meaning, not by a literal comparison of their words: on the maintainer's live vault, 378 entries from two agents produced **zero** cross-agent matches under literal comparison, because the two agents never phrase anything the same way.
- **FR-019**: The whole tree under `~/.coffer/memory/` MUST be derived: deleting it and re-running aggregation and distil MUST reproduce an **equivalent** partition — the same subjects, from the same sources — though not necessarily the same wording, since the notes are a distillation. It MUST NOT converge with the sync remote (spec [vault-sync](../vault-sync/spec.md)): it is derived from the agents installed on *this* machine, so sending it to another would send notes that machine's own next pass would recompute away. **A partition's Resource row is covered by that prohibition too, not only the files** — the `memory` kind declares `converges=False`, so the exporter withholds such rows and the applier refuses such a document. Losing the machine loses the derived tree, and that is accepted.
- **FR-020**: A note's body is **Coffer's own writing**, distilled from one or more raw entries — not a copy of any of them. This reverses the previous design's rule that a stored body had to be the source's own words. That rule bought quotability and cost the product: Codex's memory is prose bullets with no titles, so carrying it verbatim produced 284 entries whose title, description and body were the same sentence three times over, against the 16 entries Codex's own index had already distilled the same material into. Quotability is preserved where it belongs — in `.raw/`, which the note's provenance points at.
- **FR-021**: Notes MUST be **one topic per file**, accumulated over time: a later raw entry on a topic already covered MUST rewrite that note, not add a second one beside it. This is the shape Claude Code's own memory has, and the shape that makes "deduplicate" and "drop what is stale" ordinary edits rather than judgement calls about which of two records to destroy.
- **FR-022**: A note MUST be readable and useful **as a file**, with no Coffer process in the loop: plain Markdown, frontmatter first, a path an agent or a human can open. The delivery path (FR-028) and the file tree (FR-037) both depend on this, and so does the whole reason the index-plus-file shape was chosen over a search tool.

### Distil

- **FR-023**: After aggregation, a **distil** pass MUST run over each changed partition, driven by the internal connection. It MUST be **incremental**, and it MUST be incremental in the specific sense that **no single request carries the partition's bodies**. The pass therefore has two stages. **Routing**: one request per batch, carrying this round's new raw entries, the **index** of the partition's existing notes and its retirement record — and no note body at all. Its output MUST be confined to four actions per entry: **merge** it into a named existing note, **open** a new note, **retire** a note it contradicts, or **keep nothing**. **Writing**: one request per note the routing stage actually touched, carrying that one note's body and the entries routed to it, which returns the rewritten note. A partition of a hundred notes that gained three entries therefore costs one routing request over a hundred index lines and at most three small writing requests — never a hundred bodies. "Keep nothing" is a first-class outcome, not a failure: it is how a scratch directory's incidental material (FR-015) and an agent's transient observations stay out of the store.
- **FR-024**: With no internal connection configured, distil MUST still produce a usable partition **mechanically**: each raw entry becomes a note of its own, and `MEMORY.md` is written from their frontmatter. It MUST NOT be a no-op — an installation with no internal model still gets an index and a delivery, thinner rather than absent — and it MUST NOT call a model on any path.
- **FR-025**: A retirement MUST be recorded in the partition's `RETIRED.md`: the note's title, why it was retired, and the note that replaced it when there is one. The file MUST be part of the next pass's input, so a retired subject is not reinstated from the same unchanged raw entry — this is the only mechanism that makes a deletion stick in a store whose sources are outside it, and without it every pass would re-import what the last one removed. A retired note's file MUST leave `notes/` and MUST NOT appear in the index, in delivery or in recall.
- **FR-026**: Distil MUST NOT write, modify or delete anything under `.raw/`. The two passes own two directories, which is what lets a bad distillation be re-run without re-reading the agents.
- **FR-027**: A distil pass MUST record what it did — merges, new notes, retirements, and entries it kept nothing from — so a developer can answer why a note reads the way it does. Malformed model output MUST degrade to no proposals for whatever it got wrong, logged and not raised, and MUST never leave a partition without an index.

### Delivery

- **FR-028**: Session-start delivery MUST carry, in this order: what is known about the developer (`global`'s index), the **whole index** of the current repository's partition, and the **absolute path** of that partition's `notes/` directory with the statement that a note's body is read as a file. It MUST NOT name a tool as the way to reach a body: every consumer of this payload — a hook-driven Claude Code session, a hook-driven Codex session, and a channel-driven turn, which runs a local agent with full filesystem access — reads files already.
- **FR-029**: An index line MUST be written to be **sufficient on its own** wherever it can be: the conclusion in the line, not a pointer to it. Where the source supplied search terms (FR-004), the line MUST state them. One function MUST render both `MEMORY.md` and the delivered line, and both surfaces MUST sort by one definition of "newest" — they were two, and drifted.
- **FR-030**: Delivery MUST be bounded by a ceiling, and the ceiling MUST be sized for **an index** rather than for a handful of lines. When the index does not fit, the trim MUST drop the oldest lines, MUST state how many were dropped, and MUST name the directory holding them — a trimmed delivery still leaves every note reachable as a file, which is why a trim here is a much smaller loss than it was under the previous design. When the two partitions compete for the ceiling, **the current repository's lines MUST be preferred over `global`'s**. The previous design spent the budget the other way round and, on a live vault of 189 entries, delivered 8 lines of which **none** were about the project the session was open in.
- **FR-031**: A **channel-driven turn** MUST receive the same payload through the system-prompt append the turn platform already composes (spec [channels](../channels/spec.md)). It MUST NOT require a hook, since Coffer owns that context itself.
- **FR-032**: For an agent the developer drives themselves, delivery MUST go through that agent's own hook mechanism, invoking Coffer's existing CLI. Where the agent has a session-start event, delivery MUST use it; where it has none, delivery MUST use its earliest per-session event with a **once-per-session guard**. Installation MUST be an **explicit act** on Coffer's surface, marker-scoped, removable without disturbing entries Coffer did not write, and idempotent. Coffer MUST NOT install it silently, and MUST NOT write into any file that is an agent's *memory* — a hook lives in the agent's settings, which is a different thing.
- **FR-033**: Coffer MUST record **an audit event for every delivery fire**, so that whether delivery is actually happening is answerable after the fact. A fire is an event, not a property of the agent: the per-agent delivery status MUST report installation only, and MUST NOT carry a last-fired timestamp.

### Surfaces

- **FR-034**: The MCP gateway MUST expose exactly one built-in tool for this layer, `coffer__recall`, and its description MUST state that it **locates** notes rather than returning them: matching is literal, and the answer is where to read. There MUST be no `remember` tool: an agent records something by recording it the way it already does, and Coffer reads it on the next pass.
- **FR-035**: `coffer__recall` MUST take a word or phrase, span every enabled partition (FR-013), exclude retired notes and `.raw/`, and return each match's **absolute path**, title and description — not its body, which the caller reads for itself (FR-022). Matching MUST be a case-insensitive literal scan with no score, no mode and no reason in the answer, and MUST need no internal connection. Its job is to answer "where is the note about X" for a partition the session was not opened in; for the partition it *was* opened in, the index is already in front of the caller and recall should not be needed at all.
- **FR-036**: A REST family under `/api/v1/memory` and a `coffer memory` CLI group MUST cover: list partitions and notes, show one note with its provenance, browse a partition's own directory and read one file from it, run an aggregation, run a distil pass, compose the session context, read what has been retired, and install/inspect/remove delivery for an agent.
- **FR-037**: The web UI MUST present partitions **as a table**, in the same shape whether or not any exist. One partition MUST be presented as a **file tree over its own directory** with a read-only preview beside it — the same two panes a skill's Files tab is — showing `MEMORY.md`, `notes/`, `RETIRED.md` and `.raw/`, and MUST offer open-in-editor and reveal-in-file-manager on the previewed file. It MUST NOT carry per-note actions: a partition is a folder of derived Markdown, and the surface that browses it says so by looking like one.
- **FR-038**: Every lifecycle act — aggregation, distil, retirement, delivery installed, removed or fired — MUST record an audit event with its actor. A recall MUST record the usual `mcp_invocations` row and nothing about its query or results.
- **FR-039**: Per-agent delivery state MUST be presented on **that agent's own detail page**, not on the partitions surface. That surface answers one question — installed or not; firing is read as events on the audit surface.
- **FR-040**: This layer MUST NOT carry an audit surface of its own. Its events are read on the vault-wide audit surface, and every event type this layer records MUST be legible there rather than shown as a raw event code.
- **FR-041**: Only **one distil pass per partition** may run at a time, whoever started it. A manual trigger arriving while a pass is in flight MUST be **refused** (`UPKEEP_ALREADY_RUNNING`, 409) rather than queued, and the interval worker MUST **skip** a partition already being distilled. Which partitions are being rewritten right now MUST be readable. The record is per-daemon and does not outlive it.

### Constraints

- **FR-042**: This layer MUST add **no table of its own**. Notes, raw entries, the index and partition metadata are files or existing Resource rows.
- **FR-043**: File content MUST leave the machine only through the internal connection the developer configured, and only for the distil pass (FR-023) — and not at all when none is configured (FR-024). Delivery and recall MUST send nothing anywhere.
- **FR-044**: Reading MUST be confined to the memory paths of registered agents' config directories. Every path built from a source's contents MUST pass a traversal guard.
- **FR-045**: This layer MUST NOT reintroduce transcript distillation, a journal lane, native-memory projection, or a per-agent capability matrix. The two readers are written as two readers; a third agent earns an abstraction, not before.


## Success Criteria

- **SC-001**: A lesson learned by one agent is present in the session context composed for a different agent, with no file in either agent's own memory having changed.
- **SC-002**: Deleting `~/.coffer/memory/` entirely and re-running aggregation and distil reproduces every subject, from the same sources.
- **SC-003**: The session context for a repository with a hundred notes carries a line for every one of them and the path to their bodies, and an agent reaches a body with an ordinary file read and no Coffer tool.
- **SC-004**: An installation with no internal connection configured still gets partitions, notes, an index, delivery and recall — with merging and retirement absent rather than the feature absent.
- **SC-005**: Two agents that record the same lesson in no shared phrasing produce one note naming both.
- **SC-006**: A malformed or unrecognised native memory in one agent leaves the other agent's aggregation, and all previously distilled notes, intact.
- **SC-007**: A repository developed in a worktree contributes to the same partition as its main checkout, and a dated scratch directory contributes no partition at all.

## Assumptions

- Each supported agent's native memory format is read at the shape it has today. A format change is expected to break the reader; FR-005 exists so that it breaks visibly and locally rather than silently emptying the store.
- Both supported agents distil their own memory well enough to be a good source. If one stops doing so, the answer is not for Coffer to start reading transcripts, but to reconsider that reader.
- A partition's index fits a session's opening comfortably. Claude Code loads a 94-entry, ~9k-token index into every session of its own accord, so an index of that order is a cost the ecosystem already treats as normal; FR-030's ceiling exists for the case that assumption breaks, not as the ordinary path.
- The distil pass's incremental input — new raw entries plus the existing index — stays small enough for one completion. A partition whose *new* material in one round does not fit is a partition the pass may split across completions; a partition whose *index* does not fit is the assumption above failing, not this one.
- Every consumer of delivery is a process on this machine with filesystem access. This is true of all three today, including a channel-driven turn, which drives a local Claude Code or Codex rather than answering from the daemon.
