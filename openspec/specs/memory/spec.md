# Memory

## Purpose

Every agent the developer runs keeps its own memory, and none of them can see any of the others'. Claude Code accrues per-fact notes per project; Codex distils its rollouts into task groups and a profile. Both work well and neither leaves its own directory, so the developer re-teaches each agent what the other already knows. Coffer **reads those native memories, without ever writing to them**, turns them into **notes of its own** — one file per raw entry, in Coffer's own format, filed by repository and by `global` — and hands each agent the **index** of that set at session start, with the absolute path to read the rest the same way it reads its own memory: as files. After the start it hands over the few notes a prompt names. What Claude Code learns in the morning, Codex opening the same repository in the afternoon already knows — not because Coffer wrote into Codex's memory, but because Coffer handed it that note's index line.

**Coffer aggregates memory; it does not own it.** Coffer never writes an agent's native memory files, so no agent's own loop is disturbed and nothing has to be reconciled. Everything under `~/.coffer/derived/memory/` is **derived** and may be deleted and rebuilt at any time, which is what makes it safe to rewrite aggressively. Reproducing it after a delete gives back an **equivalent** set of notes, not a byte-identical one.

**Coffer runs no model over memory.** The distil pass is mechanical: each new raw entry becomes one note as it stands, and the index is rendered. The judgement — which notes are the same subject, which are stale — belongs to the person's own coding agent. A **Tidy** button on a partition, and **Tidy all** on the Memory page, hand that job to the default managed agent, which follows the `coffer-guide` memory section: it merges notes by listing the merged entries in the survivor's `origins`, and retires a note by giving it a `retired:` frontmatter key, which the next distil pass records in `RETIRED.md` and removes. Nothing tidies unattended; until someone presses Tidy, notes from different agents may duplicate each other.

**Memory is not knowledge.** [Knowledge](../knowledge/spec.md) holds what the user or an agent **wrote down about the world**; this layer holds what agents **learned while working** — the user's preferences, a project's decisions, a trap already hit.

| | Memory | Knowledge |
| --- | --- | --- |
| Where it comes from | agents' native memories, read-only | the human uploads it, or writes it with an agent |
| Partitioned by | project (and `global`) | collection |
| Who authors the stored text | **Coffer**, one note per raw entry as it stands; a person or an agent may edit or tidy a note | the human or an agent, directly |
| Delivered by | **push** — the index at session start and the notes a prompt names | **pull** — the agent reaches for it |
| Can an entry be retired | yes, and must be | no; it is updated |
| If the store is lost | rebuilt, equivalently, from the agents' own copies | gone |

Both supported agents solved retrieval the same way, and neither built a search engine for it: Claude Code loads **the whole index** into every session (94 entries, ~9k tokens on the maintainer's machine) and reaches a body with a file read; Codex writes **the search terms into the index entry itself**. This layer copies that shape:

```
~/.coffer/derived/memory/<partition>/
├── MEMORY.md     ← the index. What a session is given; what a human opens first.
├── notes/        ← Coffer's own notes. One topic per file.
├── RETIRED.md    ← what was retired, and why. Also the next pass's exclusion list.
└── .raw/         ← what was read out of the agents, verbatim. Derived, hidden.
```

Four jobs, kept apart: **`.raw/` is faithful, `notes/` is a readable copy that agents tidy, `MEMORY.md` is findable, `RETIRED.md` is what makes a retirement stick.** Three earlier designs are not repeated: transcript distillation (removed 2026-09-09), session-context injection that had never once been installed on the maintainer's machine (removed 2026-09-10; delivery returns as an explicit install with every fire audited), and a budgeted digest that on a live vault delivered 8 of 189 entries, none about the current project, pointing at a tool called five times in its lifetime — an agent will not go looking for what it has not been shown.

Assumptions: each agent's native memory is read at the shape it has today, and a format change is expected to break the reader visibly and locally; both agents distil their own memory well enough to be a good source; a partition's index fits a session's opening comfortably, and the delivery ceiling exists for when it does not; and every consumer of delivery is a process on this machine with filesystem access, including a channel-driven turn, which drives a local Claude Code or Codex.

While the `memory` feature is switched off (spec [experimental-features](../experimental-features/spec.md) "Close the memory feature's surfaces"), the memory routes are closed, the memory delivery hook is withdrawn from agents, and the distil and aggregate passes skip their rounds, and a note's `retired:` marker is not acted on meanwhile; stored memory stays untouched and the hook returns when the feature is switched on. Requirements below describe the feature while it is on.

## Requirements

### Requirement: Never write an agent's native memory
Aggregation MUST be **read-only**. Coffer MUST NOT create, modify, move, delete or reformat any file in an agent's own memory, and MUST NOT disable or reconfigure an agent's native memory. This is [Aggregate Agent Memory](../../../docs/decisions/aggregate-agent-memory-never-write-it.md)'s prohibition, retained in full and still the load-bearing constraint of this design.

#### Scenario: aggregation never modifies an agent's native memory files
- **GIVEN** fixture config directories for both supported agents, snapshotted byte-for-byte with their modification times
- **WHEN** a full aggregation reads every source out of both
- **THEN** raw entries are produced from both
- **AND** every file under either config directory is byte-identical, with an unchanged modification time — Coffer created, moved, reformatted and deleted nothing (see "Never write an agent's native memory")

### Requirement: Read no transcripts or rollouts
Aggregation MUST NOT read session transcripts, rollouts or raw capture files **as a source of entries**. Both supported agents already distil their own; this layer starts from that output. The single narrow exception is Claude Code's project slug, which encodes a path lossily: the reader MAY scan a project's own session transcripts for the `cwd` they recorded, accepting it only when Claude Code's encoding of that `cwd` is exactly the slug, so that a renamed or deleted project still files under its real repository. Nothing but that one recorded path is taken, it is looked up once per project per pass, and no transcript is ever listed as a source.

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
- **AND** a distil pass over that partition writes nothing under `.raw/` (see "Keep raw entries verbatim and hidden", "Leave the raw directory to aggregation")

### Requirement: Let only aggregation write raw entries
Only aggregation may write `.raw/`. A raw entry MUST carry the agent, the native path and the read time it came from, and MUST be reproducible from an unchanged source.

#### Scenario: stamp a raw entry with its agent, native path and read time
- **GIVEN** a Claude Code memory fact file aggregated once into a partition's `.raw/`
- **WHEN** the stored raw entry is read back, and the same unchanged source is aggregated again after the partition's `.raw/` is deleted
- **THEN** the entry names the agent, the fact file's native path and the time it was read
- **AND** the second aggregation writes an entry with the same id, title, description and body

### Requirement: Partition by repository plus global
A **partition** is a top-level directory under `~/.coffer/derived/memory/` and is one `memory` Resource. There MUST be exactly one partition per repository plus one named `global`; no other partitioning axis exists.

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

#### Scenario: a second clone resolves by repository identity and a gone checkout is replaced
- **GIVEN** a partition recording one checkout's path and its repository key, and a second clone of the same remote at a path the partition does not record
- **WHEN** a session's directory in that clone is resolved, and later aggregation reads the clone after the recorded checkout has left the disk
- **THEN** the session resolves to the partition by key, and the partition records the clone's path as its repository path

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

### Requirement: Keep notes readable as plain files
A note MUST be readable and useful **as a file**, with no Coffer process in the loop: plain Markdown, frontmatter first, a path an agent or a human can open. The delivery path (see "Deliver the index and the notes path at session start") and the file tree (see "Show a partition's memories read-only") both depend on this, and so does the whole reason the index-plus-file shape was chosen over a search tool.

#### Scenario: open a note from disk with no daemon running
- **GIVEN** a distilled partition
- **WHEN** a note's file under `notes/` is read straight from disk, with no Coffer service involved
- **THEN** it opens with a YAML frontmatter fence carrying its title and description and continues with its Markdown body

### Requirement: Record retirements so they stick
A retirement MUST be recorded in the partition's `RETIRED.md`: the note's title, why it was retired, the origin entry ids it accounts for, and the note that replaced it when there is one. A person's hand deletion of a memory is a retirement like any other, with the reason `Deleted by hand` (see "Delete a memory by hand"), and so is a note an agent marked retired (see "Retire a note an agent marked retired"). The file MUST be part of the next pass's input, so a retired subject is not reinstated from the same unchanged raw entry — this is the only mechanism that makes a deletion stick in a store whose sources are outside it, and without it every pass would re-import what the last one removed. A retired note's file MUST leave `notes/` and MUST NOT appear in the index or in delivery.

#### Scenario: a retired note leaves the index and stays out
- **GIVEN** a partition holding a note whose raw entry is still present in an agent's own memory, and that note then retired
- **WHEN** the distil pass runs, and then runs again over unchanged sources
- **THEN** after the first pass the note is named in `RETIRED.md` with its reason, its file is gone from `notes/`, and no index line mentions it
- **AND** the second pass does not recreate it, because `RETIRED.md` is part of the pass's own input (see "Record retirements so they stick")

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
A **channel-driven turn** MUST receive the same payload through the system-prompt append the turn platform already composes ([channels](../channels/spec.md)). It MUST NOT require a hook, since Coffer owns that context itself, and the delivery MUST be audited as a `session_start` fire of the answering agent with the conversation as the session (see "Audit every delivery fire").

The agent process Coffer spawns for a channel turn still loads the agent's own settings, so an installed delivery hook fires inside it as well. Coffer MUST mark that process's environment, and in a marked process the hook MUST answer nothing, and record nothing, on `SessionStart` and `UserPromptSubmit`: those two moments belong to the turn, so the index and the prompt's notes each arrive once and are counted once. A turn the developer drives MUST NOT be marked.

#### Scenario: a channel turn carries the index without a hook
- **GIVEN** a channel-driven conversation on a registered agent with a working directory, and no delivery hook installed anywhere
- **WHEN** a turn is taken
- **THEN** the index arrives in the **system-prompt append** the turn platform already composes, resolved once per turn from that agent's key and the conversation's own cwd
- **AND** when there is nothing to deliver the turn carries no memory header at all, rather than an empty one (see "Deliver to channel turns through the system prompt")

#### Scenario: a channel turn's own hook leaves the index and the notes to the turn
- **GIVEN** a connected agent whose delivery hook is installed and trusted, a channel-driven conversation on it, and a conversation the developer drives on the same agent
- **WHEN** the channel turn's agent process fires the hook on `SessionStart` and `UserPromptSubmit`
- **THEN** the hook answers nothing and records nothing, and the index and the prompt's notes reach the agent once, from the turn, each audited as one fire with event `ChannelTurn` (`session_start` and `prompt`)
- **AND** the developer-driven conversation's process is not marked, and its hook answers both

### Requirement: Install delivery hooks explicitly and removably
For an agent the developer drives themselves, delivery MUST go through that agent's own hook mechanism, invoking Coffer's existing CLI **by absolute path**. An agent runs its hooks under a shell that need not have `~/.coffer/bin` on its `PATH`: Codex runs them under `/bin/zsh` without the user's rc files, and Claude Code started from the Dock does not inherit the login shell's `PATH`. The bare name is used only when the build cannot locate its own CLI.

Coffer's hook is **two entries**, one on each moment memory reaches a session, for both supported agents: `SessionStart` (matched on `startup|resume|clear|compact`), which adds the bounded index, and `UserPromptSubmit`, which adds the notes the prompt names. Both entries run the same command, `coffer memory hook --agent-uid <uid> --cwd "$PWD"`, which reads the event the agent hands its hook on stdin and prints that event's JSON `hookSpecificOutput` with `additionalContext`, which both agents read on every event. Nothing once-per-session MAY be keyed on a process id: every session of one Codex app-server shares a parent pid, so it is keyed on the hook's `session_id`. The command is an internal entry point, hidden from help and from the CLI reference (see "Manage memory in the web UI").

Installation MUST be an **explicit act** on Coffer's surface: connecting the agent to Coffer, of which the hook is one part (spec agent-registry "Connect an agent to Coffer in one action"), or a person applying the missing hook's reconcile item. It MUST be marker-scoped, idempotent, and removable without disturbing entries Coffer did not write. An install or a remove MUST take out Coffer's marked entries on **every** event first, so a marked entry on any other event — a `PreToolUse` or `PostToolUse` entry an earlier version wrote, for one — is never left behind beside the new ones. Coffer MUST NOT install the hook silently, and MUST NOT write into any file that is an agent's *memory*: a hook lives in the agent's settings, which is a different thing.

#### Scenario: hook installation is marker-scoped and removable
- **GIVEN** an agent whose settings file already carries a foreign hook on the same lifecycle events, other events' hooks, and unrelated top-level keys
- **WHEN** delivery is installed, installed a second time, and then removed
- **THEN** install adds exactly **one** entry carrying Coffer's marker on each of `SessionStart` and `UserPromptSubmit`, both running `coffer memory hook` by absolute path, a second install leaves one on each, and every foreign hook, every other event and every unrelated key is untouched
- **AND** remove takes out only the marked entries — dropping an event array and the top-level hooks key once they are empty — and with nothing installed it is a clean no-op that writes no file and records no audit event (see "Install delivery hooks explicitly and removably")

#### Scenario: an install clears marked entries on events it no longer uses
- **GIVEN** an agent whose settings carry Coffer's marked entries on `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse`, and a foreign `PreToolUse` hook
- **WHEN** delivery is installed
- **THEN** the marked `PreToolUse` and `PostToolUse` entries are gone, the foreign `PreToolUse` hook is untouched, and exactly one marked entry sits on each of `SessionStart` and `UserPromptSubmit`

#### Scenario: a Codex hook fire prints the session-start JSON Codex reads
- **GIVEN** a partition with notes and a registered agent
- **WHEN** `coffer memory hook --agent-uid <uid>` runs with a Codex `SessionStart` event on stdin whose `cwd` is the partition's repository
- **THEN** it prints one JSON object whose `hookSpecificOutput` names `SessionStart` as its `hookEventName` and carries the composed index as `additionalContext`
- **AND** the fire is recorded

#### Scenario: both agents' hook fires answer in the JSON each reads
- **GIVEN** a Claude Code agent and a Codex agent connected on a fake home, and a distilled partition
- **WHEN** each agent's installed command is run with that agent's own `SessionStart` and `UserPromptSubmit` input on stdin
- **THEN** each prints `hookSpecificOutput` with `additionalContext` for the session start and for the prompt
- **AND** neither prints a `permissionDecision` for any input

### Requirement: Repair stale delivery hooks
An installed hook MUST be repaired when what Coffer would write is no longer what is installed, without waiting for a user to notice. This is the delivery-hook target of the unified reconciler ([resource-framework](../resource-framework/spec.md) "Converge what Coffer writes outside its database with one reconciler"), and it runs on every pass, not only at daemon start.

A hook is a string left in somebody else's settings file, and the CLI it invokes ships in a binary that keeps moving. When the command a hook runs stops taking an option, every hook already on disk keeps passing it. The agent prints a usage error at the start of every session, and this layer never reaches it again. Nothing reports the failure, because detection is marker-scoped and never reads the arguments. That same marker scoping is what lets a reinstall replace an entry in place, and it is why a stale entry reads as installed.

The target therefore judges a hook by the **set of events** its entries sit on and their **whole commands**, both against what would be installed now, and rewrites a hook that differs into the two current entries — which includes a hook an earlier version installed on four events, whose `PreToolUse` and `PostToolUse` entries are removed. The two kept entries keep their command and their position, so the approval Codex recorded for each still holds. One unreadable settings file MUST be reported as blocked without stranding the others.

For an agent that runs a hook only after the user has approved it (Codex), the target MUST also read whether the agent will run **every** installed entry. A current hook the agent will not run MUST be **reported, never written**, with the reason and the remedy (approve it with `/hooks` in Codex). Coffer MUST NOT write the agent's approval record: approving a hook is the user's act in the agent (spec agent-registry/codex "Leave Codex's internal-state tables untouched").

The hooks wanted are those of every connected agent and of every agent that already carries one. A pass — at boot or on its period — MUST NOT install a hook for an agent that has none; only a person applying that item, or connecting the agent, installs it. Otherwise the missing hook is reported and the agent's connection reads partial. A repair that added the hook would be an install Coffer made silently, which "Install delivery hooks explicitly and removably" forbids.

#### Scenario: a hook whose command went stale is repaired without being asked
- **GIVEN** an agent with Coffer's hook installed, and a Coffer build whose delivery command is no longer the one in that agent's settings file,
- **WHEN** a reconcile pass runs — at daemon start or on its period,
- **THEN** the entries are rewritten in place to the ones this build would install, so the next session is served rather than shown a usage error,
- **AND** an agent whose hook is already current is left untouched, and an agent with no hook is not given one.

#### Scenario: a four-entry hook is rewritten to two without losing Codex's approvals
- **GIVEN** a connected Codex agent carrying Coffer's hook on `SessionStart`, `UserPromptSubmit`, `PreToolUse` and `PostToolUse`, with `config.toml` recording its approval of all four
- **WHEN** a reconcile pass runs
- **THEN** the hook is two entries, on `SessionStart` and `UserPromptSubmit`, with the commands and positions they had
- **AND** the two kept entries' approvals in `config.toml` still match, so the next pass reports no `hook_untrusted`, and Coffer wrote no approval

#### Scenario: a current Codex hook Codex has not approved is reported, not written
- **GIVEN** a connected Codex agent carrying the current hook, and no approval for its entries in Codex's `config.toml`
- **WHEN** a reconcile pass runs on its period, and again when a person applies it
- **THEN** the only difference is `trust`, and it is reported as `hook_untrusted` with the remedy "run /hooks in Codex"; nothing is written, and Coffer records no approval
- **AND** once `config.toml` records Codex's approval of every one of those entries, the next pass finds nothing to do

### Requirement: Audit every delivery fire
Coffer MUST record **an audit event for every delivery fire**, so that whether delivery is actually happening is answerable after the fact: every session start, and every prompt fire that delivered a note. The event MUST name its moment (`session_start` or `prompt`), the session, and the notes it carried — never their text. A fire is an event, not a property of the agent: the hook's per-agent status MUST report installation only, and MUST NOT carry a last-fired timestamp.

#### Scenario: every hook fire is recorded in the audit log
- **GIVEN** an agent for which delivery has been installed
- **WHEN** the installed hook fires and the served context is recorded as a delivery
- **THEN** exactly one audit event is written naming that agent as both the resource and the actor
- **AND** the per-agent installed state is unchanged by a fire, and neither installing nor reading status records a fire of its own (see "Audit every delivery fire")

#### Scenario: name the moment and the notes of a session-start fire and a prompt fire
- **GIVEN** a session that is given the index at its start and a note at a prompt
- **WHEN** the audit log is read
- **THEN** one `memory_delivery_fired` event names moment `session_start`, and another names moment `prompt` and the note, and neither carries the note's text

### Requirement: Audit every lifecycle act
Every lifecycle act — aggregation, distil, retirement, delivery installed, removed or fired — MUST record an audit event with its actor. A memory changed in an editor is not a Coffer act and is not audited; `memory_note_edited` rows an earlier version recorded keep their wording in Activity.

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
This layer MUST add **no table of its own**. Notes, raw entries, the index and partition metadata are files, and each partition is one resource file in the derived class.

#### Scenario: keep partitions as resource files and plain files only
- **GIVEN** a history database upgraded to head
- **WHEN** its tables are listed after an aggregation and a distil pass
- **THEN** no table is named for memory, and each partition is one resource of kind `memory`, filed under `~/.coffer/derived/resources/memory/`

### Requirement: Confine reads to registered agents' memory paths
Reading MUST be confined to the memory paths of registered agents' config directories. Every path built from a source's contents MUST pass a traversal guard.

#### Scenario: refuse a path segment built from source contents that escapes
- **GIVEN** a partition name or raw entry id taken from a source's contents that is `..`, contains a path separator, or is hidden
- **WHEN** a path under the memory root is built from it
- **THEN** it is refused with `UnsafeMemoryPath` rather than resolved outside the partition

### Requirement: Reintroduce no retired mechanism
This layer MUST NOT reintroduce transcript distillation, a journal lane, a Coffer-run model over memory, native-memory projection, or a per-agent capability matrix. The two readers are written as two readers; a third agent earns an abstraction, not before.

#### Scenario: register exactly the two readers
- **GIVEN** the memory layer's reader registry
- **WHEN** its readers are listed
- **THEN** there is exactly one reader for Claude Code and one for Codex
- **AND** a full aggregation and distil writes no journal directory and nothing outside `MEMORY.md`, `notes/`, `RETIRED.md` and `.raw/` in a partition

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

### Requirement: Expose no memory tool and name the memory root at session start
The MCP gateway MUST expose no built-in tool for this layer: no tool that locates, reads, searches or records a note. An agent records something the way it already does, and Coffer reads it on the next pass. An agent finds a note the way it finds any file: session-start delivery (see "Deliver the index and the notes path at session start") MUST name the **absolute memory root** and state that every partition's notes are Markdown files under `<root>/<partition>/notes/`, so an agent looking for a note in a partition the session was not opened in searches that one directory with its own tools. The memory root is one directory, so one search covers every partition. No command prints the root: the session-start payload is where it is named.

#### Scenario: no memory tool is listed, and delivery names the memory root
- **GIVEN** a running daemon, a partition holding notes, and a `global` partition holding more
- **WHEN** an agent lists the gateway's tools, and the session context is composed for a cwd inside that partition's repository
- **THEN** no `coffer__recall`, no `coffer__remember` and no other memory tool is listed
- **AND** the payload names the absolute memory root and states that each partition's notes are Markdown files under `<root>/<partition>/notes/` to be searched with the agent's own tools

### Requirement: Provision partitions only from aggregation
Partitions MUST be **created by aggregation**, not by the user, and MUST NOT be created by an agent's working directory at read time.

#### Scenario: compose session context without creating a partition
- **GIVEN** a memory root with no partitions and a working directory inside a git repository
- **WHEN** the session context is composed for that working directory
- **THEN** no partition directory and no `memory` Resource exists afterwards

### Requirement: Serve every partition to every agent
A partition MUST NOT carry the Resource framework's per-agent reach or an enabled switch: the kind declares itself non-toggleable ([resource-framework](../resource-framework/spec.md) "Address every resource by an immutable uid through one kind-agnostic surface"). Every partition MUST be served to **every** agent on the path Coffer itself serves — delivery (see "Deliver the index and the notes path at session start", "Expose no memory tool and name the memory root at session start"). Aggregating the memory of several agents into one place exists so that each agent can read what the others learned, so a partition is served to the agents that contributed nothing to it as much as to those that did. Serving gates **what Coffer names**, not what a process on this machine can open: a note is a file an agent is given the path to, and the layer MUST NOT present serving as a filesystem boundary it is not.

#### Scenario: a partition is registered as a resource keyed on its repository
- **GIVEN** exactly one registered agent contributing one raw entry about a repository
- **WHEN** aggregation runs
- **THEN** a `memory` Resource exists for that partition, and its config records the repository's own absolute path — the identity of a partition is the repository, so that path is what a later pass resolves it by (see "Identify a partition by its repository")
- **AND** no per-agent reach is written for it, and a request to disable it through the generic resource route is refused: the partition is served to every agent, including the one that contributed nothing to it

### Requirement: Update memory in one action
`POST /api/v1/memory/sync` MUST run an aggregation (see "Aggregate on an interval and on demand") and then a distil pass over every partition with something to distil — raw entries it has not yet distilled (see "Distil each raw entry into a note mechanically"), or a note none of whose raw entries is left (see "Retire a note whose raw entries are all gone") — and MUST answer with what the aggregation wrote and which partitions were distilled. A distil pass already running over a partition MUST NOT fail the action: that partition is reported as skipped. The web UI MUST offer this as one **Update memory** button — the partitions page's primary action, a split button whose ▾ opens the automatic-read schedule (the switch and the interval), kept apart from **Tidy all** because that one costs model tokens, and also on a partition's page — and MUST NOT offer aggregation or distillation as separate buttons.

#### Scenario: one action reads new agent memory and distils it
- **GIVEN** a registered agent whose native memory gained an entry about a repository with a distilled partition
- **WHEN** `POST /api/v1/memory/sync` is called
- **THEN** the entry is written under that partition's `.raw/` and the same call distils it into the partition's notes
- **AND** the answer names that partition among the distilled ones

#### Scenario: a partition whose only change is a deleted source is still distilled
- **GIVEN** a partition whose single note was built from a native memory file the agent has since deleted, so its raw entries are gone and nothing new arrived
- **WHEN** memory is updated
- **THEN** the note is retired and the answer names that partition among the distilled ones

### Requirement: Retrieve the notes a prompt names
For every prompt the developer sends a hook-driven session, Coffer MUST rank the notes of the session's repository partition and of `global` against the prompt — each note's title, description, search terms and body — with a lexical ranker (BM25, CJK text as bigrams), and MUST add to the session the **top three** notes that score at or above a **relevance floor** and that this session has not already been given. Each is delivered as the absolute path of its file and its substance (see "Word delivered notes as provenance plus fact"), and the whole delivery MUST stay within **1,500 UTF-8 bytes**. A prompt of fewer than three words, or a bare nudge such as `continue`, `ok` or `继续`, MUST retrieve nothing. What a session was already given is remembered per `session_id` — the id the agent hands its hook, never a process id — and survives a daemon restart (see "Remember what a session was given across daemon restarts").

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

### Requirement: Fail open when Coffer cannot answer
Every memory hook MUST fail open: when the daemon is not running, does not answer within the hook's own short timeout, or answers with an error, the hook MUST print nothing and exit 0, so memory never stops a prompt because Coffer is down. A fire that can deliver nothing — a trivial prompt — MUST be answered without contacting the daemon.

#### Scenario: the hook prints nothing and exits 0 with no daemon
- **GIVEN** no daemon running
- **WHEN** `coffer memory hook` is given a `SessionStart` and a `UserPromptSubmit` event on stdin
- **THEN** each run prints nothing and exits 0

### Requirement: Word delivered notes as provenance plus fact
Every note delivered at a prompt MUST read as **provenance plus fact**: it names the note's file, and states the note's substance as "the user's standing rule is: …" for a `feedback` note and as "a fact they recorded: …" otherwise. Delivered text MUST NOT be phrased as an instruction to the agent.

#### Scenario: a delivered note names its file and reads as a standing rule
- **GIVEN** a `feedback` note and a `project` note that both match a prompt
- **WHEN** the prompt's delivery is composed
- **THEN** the `feedback` note's line names its absolute path and reads "the user's standing rule is: …", and the `project` note's reads "a fact they recorded: …"

### Requirement: Show what each agent is given at session start
`GET /api/v1/memory/partitions/{uid}/delivered` MUST return, for every registered agent with a delivery hook, the **exact text** that agent's session-start hook would add in that partition's repository — composed by the same function and under the same ceiling the hook uses — read only, and without whether a hook is installed or trusted. The web UI's partition page shows it on its Delivered tab.

#### Scenario: the Delivered view carries each agent's exact session-start text
- **GIVEN** a distilled repository partition and a registered Claude Code and Codex agent
- **WHEN** the partition's Delivered view is read
- **THEN** each agent's entry carries `SessionStart` and text equal to what `POST /api/v1/memory/hook` answers a `SessionStart` fire from that repository with
- **AND** nothing is audited and no hook state is carried

### Requirement: Leave per-turn rules to the agent's own instructions
Memory delivery MUST NOT be presented as the place for a rule about **every** turn — the language of every reply, a tone — which no retrieval or trigger addresses: such a rule belongs in the instructions the agent loads on every turn (`CLAUDE.md`, `AGENTS.md`), which the user owns. Installing or firing Coffer's memory hook MUST NOT write those files.

#### Scenario: connecting an agent leaves its instructions files untouched
- **GIVEN** a Claude Code agent with a `CLAUDE.md` and a Codex agent with an `AGENTS.md`
- **WHEN** both are connected and every one of their hooks fires
- **THEN** both instructions files are byte-identical afterwards

### Requirement: Retrieve the notes a prompt names for a channel turn
A **channel-driven turn** gets its prompt's notes from Coffer rather than from its hook (see "Deliver to channel turns through the system prompt"), so Coffer MUST retrieve for each of its prompts itself: the prompt MUST be ranked by the same retrieval "Retrieve the notes a prompt names" defines — the same partitions, ranker, relevance floor, top three, 1,500-byte ceiling and trivial-prompt rule — with the conversation as the session, so a note is given once per conversation. What it finds MUST be added after the user's text in the prompt the agent receives, where a `UserPromptSubmit` hook's context would land; the message stored in the conversation MUST stay the user's own text. Each delivery MUST be audited as a `prompt` fire of the answering agent (see "Audit every delivery fire"). A turn the developer drives from the web page MUST NOT be ranked here, since its agent's own hook does that, and a retrieval that fails MUST cost the turn only its notes.

#### Scenario: a channel turn's prompt brings in the notes it names
- **GIVEN** a channel-driven conversation on a registered agent in a repository whose partition holds a note about running `make verify` under Node 20, and a conversation the developer drives in the same repository
- **WHEN** each sends the prompt "why does make verify fail with undici AbortSignal under node", and the channel conversation sends it again
- **THEN** the channel turn's agent receives the prompt followed by the same text the `UserPromptSubmit` hook would add, naming the Node 20 note's file, and one `memory_delivery_fired` event names moment `prompt`, the conversation and the note
- **AND** the second channel turn is given nothing new, and the developer-driven turn's prompt reaches its agent unchanged

### Requirement: Remember what a session was given across daemon restarts
What each session was given — the notes delivered at its prompts — MUST survive a daemon restart, so a restart does not bring a note into a session again. The record MUST be the audit log's delivery fires (see "Audit every delivery fire"), which already name each fire's session and notes: the daemon MUST rebuild the per-session record from the fires of the last **seven days** before it answers its first prompt, and MUST add no table for it (see "Add no table of its own"). A session idle for longer than that is treated as new. A rebuild that fails MUST be logged and leave the record empty rather than stop delivery.

#### Scenario: a daemon restart gives a session nothing twice
- **GIVEN** a session that was given a note at a prompt, and then the daemon is restarted
- **WHEN** the same session sends the same prompt, and a new session sends it too
- **THEN** the first session is given nothing
- **AND** the new session is given the note

### Requirement: Report the last read of the agents' memory
`GET /api/v1/memory/reading` MUST answer when Coffer last read the agents' memory
(`read_at`, `null` before the first read) and, for each agent whose memory that read could not
parse, the agent, the source path, the reason and when that agent's memory was last read with
nothing failing, if known. The answer MUST be read from the `memory_aggregated` audit events,
which therefore carry each failure's agent, path and reason, so it is the same whoever started
the read — the timer or Update memory — and survives a daemon restart. Only
the newest read decides what failed. When the last read left an agent unread the Memory page MUST
show a warning banner naming the agent and the path, saying that agent's memories stay as its last full read
left them, with **Retry** (Update memory) and **Ask an agent ▾**, whose prompt asks the agent to fix
the path's read permission.

#### Scenario: the last read and an agent it could not read are reported
- **GIVEN** three reads recorded, the newest two unable to parse Codex's memory and the oldest
  reading every agent
- **WHEN** the last read is asked for
- **THEN** it is the newest read's time, with one failure naming Codex, its path and its reason
- **AND** that failure's last full read is the oldest read's time

### Requirement: Show Update memory's progress
While Update memory runs, `GET /api/v1/upkeep/runs` MUST list it as one `memory` run named
`update` beside the per-partition claims: with no count while it is reading the agents' memory,
then with `done` and `total` over the partitions it has to distil. The Update memory button MUST
read "Updating…" while it is listed, and each partition row whose distil pass is in flight MUST
read "Distilling…"; the Memory page's header carries no status line beside the button.

#### Scenario: update memory reports how many partitions it has distilled
- **GIVEN** four partitions, three of them holding entries no pass has distilled
- **WHEN** Update memory runs
- **THEN** its run carries no count while it reads the agents' memory, then 0, 1 and 2 of 3 as it
  distils the three partitions in turn, leaving the fourth alone
- **AND** it is no longer listed once it has answered

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

### Requirement: Delete a memory by hand
A person MUST be able to delete a memory from its partition's page. `DELETE /api/v1/memory/partitions/{uid}/notes/{slug}` MUST **retire** the note, not merely remove it: the sources it was distilled from still live in the agents' own memory, so a bare file removal would be undone by the next distil pass. It MUST append a record to the partition's `RETIRED.md` with the reason `Deleted by hand` carrying the note's origin entry ids (see "Record retirements so they stick"), remove the note's file from `notes/`, re-render `MEMORY.md` without it, and record a `memory_note_deleted` audit event naming the partition, the note and the user. An unknown note is refused with 404. The web UI's **Delete…** MUST ask first, in a confirmation naming the memory, and MUST close that dialog only on success: a delete that fails leaves it open and shows the reason.

#### Scenario: a memory deleted by hand is retired and not recreated
- **GIVEN** a partition whose memory `python-lockfile` was distilled from raw entries still present in an agent's own memory
- **WHEN** the person chooses **Delete…** on it and confirms
- **THEN** the memory leaves the list, `RETIRED.md` gains a record with reason "Deleted by hand" carrying the note's entry ids, `MEMORY.md` no longer lists it, and an audit entry `memory_note_deleted` is written
- **AND** the next Update memory does not recreate it
- **AND** a failed delete leaves the dialog open with the reason

### Requirement: Read only registered agents' memory
Coffer MUST read the native memory of each **registered** agent, from a path derived from that agent's own `config_dir` ([agent-registry](../agent-registry/spec.md)). An agent that is not registered MUST NOT be read.

#### Scenario: read nothing from an unregistered agent
- **GIVEN** fixture memory for a registered agent and in a config directory no registered agent names
- **WHEN** aggregation runs
- **THEN** raw entries come only from the registered agent's memory
- **AND** nothing is read from the unregistered directory

### Requirement: Distil each raw entry into a note mechanically
A **distil** pass MUST run on its own interval — the `distil` pass's switch and interval in the engine's upkeep settings ([internal-engine](../internal-engine/spec.md) "Carry a switch and interval for each of the two unattended passes") — rather than after each aggregation, over every partition that holds raw entries it has not yet distilled. Each such raw entry MUST become one note of its own as it stands: the raw entry's title, description, type, body, search terms and origin, with `created_at` and `updated_at`. Notes are one topic per file: a later raw entry on a topic a note already covers opens a note of its own beside it, and collapsing the two is tidying, which an agent does. Then the pass MUST retire every note none of whose raw entries is left (see "Retire a note whose raw entries are all gone"), process every note an agent marked retired (see "Retire a note an agent marked retired"), and render `MEMORY.md` from the notes' frontmatter. It MUST NOT be a no-op on any installation, and it MUST NOT call a model, and send file content anywhere, on any path: judging which notes are the same subject, or which statement is stale, is the agent's work (see "Teach tidying in the coffer-guide's memory section"). A partition with no undistilled raw entry and nothing to retire costs nothing. Whenever an aggregation files entries into a partition or a distil pass finishes over one, Coffer MUST announce the partition on the daemon's event stream as a `memory` event carrying the partition's uid, because notes and raw entries change without any write to the partition's row ([resource-framework](../resource-framework/spec.md) "Announce every change on one daemon-wide event stream").

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
Reading one partition (`GET /api/v1/memory/partitions/{uid}`) MUST carry `tidy_handoff`: a prompt, produced by the domain's hand-off text, that names the partition, its absolute directory and the `coffer-guide` section to follow (see "Teach tidying in the coffer-guide's memory section"). The partition's page MUST offer a **Tidy** button. With a managed agent available, **Tidy** MUST start the hand-off agent in the person's preferred terminal with the `tidy_handoff` prompt sent at once ([web-ui](../web-ui/spec.md) "Hand a machine-dependent problem to an agent with one split button") and leave the page where it is; with none available, the page MUST offer **Copy prompt** only. The Memory page MUST also offer **Tidy all** in its header, backed by `GET /api/v1/memory/tidy-handoff`: a prompt that names the memory root and every partition with its absolute notes directory and note count, and asks the agent to tidy them one at a time by the same section; it behaves as **Tidy** does. Nothing MUST tidy a partition unattended: a partition is tidied only when a person chooses Tidy or asks an agent to.

#### Scenario: Tidy sends the prompt to the default managed agent
- **GIVEN** a partition's page and a managed agent
- **WHEN** the person chooses **Tidy**
- **THEN** the hand-off agent starts in the preferred terminal with the partition's `tidy_handoff` prompt already sent, and the page stays where it is
- **AND** the prompt names the partition, its absolute directory and the coffer-guide section to follow

#### Scenario: Tidy all hands every partition to the agent in one conversation
- **GIVEN** the Memory page with two partitions and a managed agent
- **WHEN** the person chooses **Tidy all**
- **THEN** one session of the hand-off agent starts in the preferred terminal with the `GET /api/v1/memory/tidy-handoff` prompt already sent
- **AND** the prompt names the memory root and both partitions with their notes directories and note counts

#### Scenario: with no managed agent the page offers Copy prompt only
- **GIVEN** a partition's page and no managed agent
- **WHEN** the person opens Tidy
- **THEN** the page offers **Copy prompt**, which copies the `tidy_handoff` prompt, and starts no terminal

#### Scenario: nothing tidies a partition unattended
- **GIVEN** a partition holding near-duplicate notes, with the aggregate and distil switches on
- **WHEN** the workers run through several intervals and no person chooses Tidy
- **THEN** every note is as the distil pass wrote it, and no terminal or agent session was started

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

### Requirement: Show a partition's memories read-only
The web UI MUST present partitions **as a table** once any exists; with none, it shows the first-run welcome every other empty surface shows — *Nothing distilled yet*, with **Update memory** and the connected agents whose memory Coffer found on this machine, or, with no agent connected, saying there is nothing to read and offering **Open Agents** to connect one. Each row MUST carry the partition's path ("Every project" for `global`), how many memories it holds, its sources (the agents it came from, "All agents" when every agent that contributed anywhere contributed here) and its state, in a column headed **Distilled**: when it was last distilled, "Not distilled yet", "Distilling…" while a pass over it runs, or "Repository missing". Healthy rows are grey: only **Repository missing** is coloured, and only that row offers a Delete, which asks first because it cannot be undone (a confirmation naming the partition, with Cancel and Delete partition). The partitions table has no section title and no count of partitions or memories, and a search box above it filters the rows by partition name and path. A partition's page MUST have no back link, and no automatic-read schedule: its title is the partition's name alone, and its description line carries the path, the memory count and when it was last distilled (*~/code/coffer · 38 memories · distilled 2 h ago*). Its ⋯ menu holds **Reveal partition folder**, **Copy path**, **Distil history in Activity** and, only when its repository is gone, **Delete partition**. A partition not yet distilled shows no memory list: its Memories tab shows only the empty state, which offers no Update memory of its own because the header has one. Each memory in its list MUST name the agents it was learned from ("All agents" when that is every agent the partition came from). The partition listing MUST carry when its newest memory was last updated (`updated_at`, absent for a partition holding no memory), which the Overview's Memory tile words as "Last update 14 min ago". One partition's page MUST carry two tabs. **Memories** (the default) lists its memories — the web UI's label for what this spec and the disk call notes (中文 记忆条目) — beside the selected memory, with the partition's retired memories in a collapsed **Retired** group, each with the reason it was retired; choosing one opens it read-only beside the list (see below). The selected memory MUST be rendered with a meta line naming the agents it was learned from and when it was last updated, taken from its provenance ("Store each note as one Markdown file with frontmatter"), and its frontmatter MUST be shown as that metadata, not rendered as body text. The page MUST NOT show the agents' own memory: no native paths, no original agent text, no `.raw/` entry, no `MEMORY.md` index or `RETIRED.md` file, and no file tree — those stay in the data and on disk, and only this page leaves them out. The partition's own folder is reached through the partition's ⋯ menu (**Reveal partition folder**, **Copy path**); a memory's own file is reached from the memory (see below). The list and the memory MUST extend to the bottom of the window and scroll inside. The partition's page MUST offer **Tidy** in its header (see "Hand a partition's tidying to the agent"). The selected memory MUST be shown read-only and offer **Open in editor** as a visible button, and a ⋯ menu holding **Reveal in Finder** and **Delete…**; its body is rendered with find (⌘F). The page MUST NOT edit a memory: a person changes it in their own editor (see "Edit a memory in the person's own editor"). **Delete…** MUST ask first, and on confirming MUST retire the memory by hand (see "Delete a memory by hand"). A retired memory chosen from the Retired group MUST open read-only — its full title, a *Retired* tag, the date it was retired, its full reason and, when it was replaced by a memory still in the list, a **Replaced by <memory> →** link to it — and offers no Open in editor or Delete; the selection is addressed in the URL (`?retired=<index>`), and a Retired group so addressed opens expanded. The Memory page's title carries the **Experimental** tag ([experimental-features](../experimental-features/spec.md)); a partition's page does not. **Delivered** (`/memory/<uid>/delivered`) shows, read-only, the exact session-start text each agent receives in the partition's project, with a switch between agents ([web-ui](../web-ui/spec.md) "Show memory delivery on the Memory page"); it shows no hook state.

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
- **THEN** the title is the partition's name with no Experimental tag and no back link, the description line carries the path, *38 memories* and when it was distilled, and there is no automatic-read schedule
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
