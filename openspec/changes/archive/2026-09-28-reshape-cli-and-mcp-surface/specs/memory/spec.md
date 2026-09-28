## ADDED Requirements

### Requirement: Expose no memory tool and name the memory root at session start
The MCP gateway MUST expose no built-in tool for this layer: no tool that locates, reads, searches or records a note. An agent records something the way it already does, and Coffer reads it on the next pass. An agent finds a note the way it finds any file: session-start delivery (see "Deliver the index and the notes path at session start") MUST name the **absolute memory root** and state that every enabled partition's notes are Markdown files under `<root>/<partition>/notes/`, so an agent looking for a note in a partition the session was not opened in searches that one directory with its own tools. The memory root is one directory, so one search covers every partition. On the command line `coffer path memory` prints the same root.

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

## MODIFIED Requirements

### Requirement: Keep raw entries verbatim and hidden
Raw entries MUST be written under the partition's hidden `.raw/` directory, **verbatim**, one file per entry, and MUST be excluded from the index and from delivery. They are aggregation's output and the distil pass's input, and they are the reason a distillation can be re-run without re-reading the agents.

#### Scenario: raw entries land hidden, and only aggregation writes them
- **GIVEN** a partition with notes already distilled
- **WHEN** aggregation runs
- **THEN** the entries it wrote are under the partition's `.raw/`, which is excluded from the index and from delivery
- **AND** a distil pass over that partition writes nothing under `.raw/` (see "Keep raw entries verbatim and hidden", "Keep distil out of the raw directory")

### Requirement: Serve every enabled partition to every agent
A partition MUST NOT carry the Resource framework's per-agent reach. Every **enabled** partition MUST be served to **every** agent on the path Coffer itself serves — delivery (see "Deliver the index and the notes path at session start", "Expose no memory tool and name the memory root at session start"). The per-agent form is withdrawn because its default worked directly against the point of aggregating: a partition was created scoped to the agents it had been aggregated from, so `memory/coffer` came out scoped to `claude-code` alone and a Codex session in the Coffer repository was served no project memory at all, while the `account*` partitions came out scoped to `codex` alone. Nobody chose any of that — a layer whose whole job is to let each agent read what the others learned was defaulting to withholding it from the one agent that had not learned it yet. `enabled` is the only gate. It gates **what Coffer serves**, not what a process on this machine can open: a note is a file an agent is given the path to, so a partition that is not delivered is one nothing points at, and the layer MUST NOT present `enabled` as a filesystem boundary it is not.

#### Scenario: a partition is registered as a resource keyed on its repository
- **GIVEN** exactly one registered agent contributing one raw entry about a repository
- **WHEN** aggregation runs
- **THEN** a `memory` Resource exists for that partition, and its config records the repository's own absolute path — the identity of a partition is the repository, so that path is what a later pass resolves it by (see "Identify a partition by its repository")
- **AND** no per-agent reach is written for it: the partition is served to every agent, including the one that contributed nothing to it, which is the whole reason the memory of several agents is aggregated into one place (see "Serve every enabled partition to every agent")

### Requirement: Record retirements so they stick
A retirement MUST be recorded in the partition's `RETIRED.md`: the note's title, why it was retired, and the note that replaced it when there is one. The file MUST be part of the next pass's input, so a retired subject is not reinstated from the same unchanged raw entry — this is the only mechanism that makes a deletion stick in a store whose sources are outside it, and without it every pass would re-import what the last one removed. A retired note's file MUST leave `notes/` and MUST NOT appear in the index or in delivery.

#### Scenario: a retired note leaves the index and stays out
- **GIVEN** a partition holding a note, and a later raw entry that contradicts it
- **WHEN** the distil pass runs, and then runs again over unchanged sources
- **THEN** after the first pass the note is named in `RETIRED.md` with the note that replaced it and the reason, its file is gone from `notes/`, and no index line mentions it
- **AND** the second pass does not re-open it, because `RETIRED.md` is part of the pass's own input (see "Record retirements so they stick")

### Requirement: Show delivery state on the agent's own page
Per-agent delivery state MUST be presented on **that agent's own detail page** and in `coffer agent show <name>` as the field `memory_delivery`, not on the partitions surface. That state answers one question — installed or not; firing is read as events on the audit surface.

#### Scenario: show installed or not on the agent page
- **GIVEN** an agent's detail page, for an agent with delivery installed and one without
- **WHEN** its memory delivery section renders
- **THEN** it states whether delivery is installed and offers the matching install or remove action
- **AND** it shows no last-fired time

#### Scenario: the agent's command-line view reports delivery state
- **GIVEN** two registered agents, one with delivery installed by `coffer memory delivery on <agent>` and one without
- **WHEN** `coffer agent show <name> --json` runs for each
- **THEN** `memory_delivery` reports installed for the first and not installed for the second, and neither carries a last-fired time

### Requirement: Cover memory management on REST and the CLI
A REST family under `/api/v1/memory` MUST cover: list partitions and notes, show one note with its provenance, browse a partition's own directory and read one file from it, run an aggregation, run a distil pass, compose the session context, read what has been retired, and install/inspect/remove delivery for an agent. The `coffer memory` CLI group MUST offer `list`, `show`, `edit`, `rm`, `enable`, `disable`, `sync` (run an aggregation), `distil`, `context` (compose the session context; the command an installed delivery hook runs) and `delivery on|off <agent>` (install or remove delivery). It offers no `add`, because partitions are created only by aggregation (see "Provision partitions only from aggregation"). A partition's notes, its index, its retirement record and its file tree are plain files (see "Keep notes readable as plain files"), so on the command line `coffer path memory [<partition>]` prints the absolute path of the memory root or of one partition, and they are read on disk; the `coffer memory` group carries no command that lists or prints a note or a file. Delivery state is read with `coffer agent show` (see "Show delivery state on the agent's own page").

#### Scenario: a partition's own directory is browsable as a file tree
- **GIVEN** a distilled partition
- **WHEN** its file tree is requested, and then one file out of it
- **THEN** the tree's root carries the partition directory's absolute path and holds `MEMORY.md`, a `notes/` directory listing one Markdown file per note, and `RETIRED.md` when anything has been retired; reading `notes/<slug>.md` returns its text — not binary, not truncated — with the absolute path of the file and of the folder holding it
- **AND** `.raw/` is reachable through the same tree but marked as derived input, the family is read-only (a write is refused with 405), and a path escaping the partition is refused with `MEMORY_UNSAFE_PATH` (400) (see "Present partitions as a table and a file tree", "Confine reads to registered agents' memory paths")

#### Scenario: locate a partition's notes from the command line
- **GIVEN** a distilled partition named `coffer`
- **WHEN** `coffer path memory coffer` runs, and then `coffer path memory` with no partition
- **THEN** the first prints the absolute path of the partition directory, which holds `MEMORY.md` and `notes/`, and the second prints the absolute memory root that holds it
- **AND** `coffer memory` offers no `partitions`, `notes`, `note`, `retired`, `ls`, `read`, `delivery-install` or `delivery-remove` command, and `coffer memory context` is unchanged

### Requirement: Audit every lifecycle act
Every lifecycle act — aggregation, distil, retirement, delivery installed, removed or fired — MUST record an audit event with its actor.

#### Scenario: audit a requested aggregation and distil with their actor
- **GIVEN** a registered agent with native memory and a partition to distil
- **WHEN** a user requests an aggregation and then a distil pass
- **THEN** exactly one aggregation audit event and one distil audit event name that user as their actor, beside any the daemon's own worker recorded under its own actor

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

## REMOVED Requirements

### Requirement: Expose only coffer__recall
**Reason**: An agent answers "where is the note about X" with its own search over the memory root, which session-start delivery already names, so a gateway tool that only returned paths duplicated a file search.
**Migration**: Search the memory root named in the session-start delivery, or printed by `coffer path memory`, for the word or phrase; each match under `<partition>/notes/` is a note to read as a file. See "Expose no memory tool and name the memory root at session start".

### Requirement: Recall locations by literal match
**Reason**: The literal cross-partition scan it described is what a search over the memory root does, with the agent's own tools and no daemon in the loop.
**Migration**: Search `<memory root>/*/notes/` for the phrase; `RETIRED.md` and `.raw/` are outside `notes/`, so retired notes and raw entries do not match. `coffer path memory` prints the root.

### Requirement: Create partitions only by aggregation
**Reason**: Its scenario exercised `coffer__recall`, which is removed; the rule itself is unchanged.
**Migration**: The same rule is stated in "Provision partitions only from aggregation", whose scenario composes the context and runs `coffer path memory`. Code comments and tests that cite the old title follow the new one.

### Requirement: Send content out only for distil
**Reason**: Its text and scenario named `coffer__recall`, which is removed; the rule for delivery is unchanged.
**Migration**: The same rule, without recall, is stated in "Send file content out only for distil". Code comments and tests that cite the old title follow the new one.
