## MODIFIED Requirements

### Requirement: Cover memory management on REST and the CLI
A REST family under `/api/v1/memory` MUST cover: list partitions and notes, show one note with its provenance, browse a partition's own directory and read one file from it, update memory (see "Update memory in one action"), compose the session context, and read what has been retired. The `coffer memory` CLI group MUST offer `list`, `show`, `edit`, `rm`, `sync` (update memory: an aggregation, then a distil pass over every partition that gained entries, see "Update memory in one action") and `context` (compose the session context; the command an installed delivery hook runs). It offers no `add`, because partitions are created only by aggregation (see "Provision partitions only from aggregation"), and no `enable` or `disable`, because a partition has no switch (see "Serve every partition to every agent"). A partition's notes, its index, its retirement record and its file tree are plain files (see "Keep notes readable as plain files"), so on the command line `coffer path memory [<partition>]` prints the absolute path of the memory root or of one partition, and they are read on disk; the `coffer memory` group carries no command that lists or prints a note or a file. Installing, inspecting and removing an agent's delivery hook are part of that agent's Coffer connection (spec agent-registry "Connect an agent to Coffer in one action") and are not in this family: on the command line they are `coffer agent connect|disconnect <agent>`, and `coffer agent show <agent>` carries the hook as a part of its `coffer_connection`.

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

### Requirement: Audit every lifecycle act
Every lifecycle act — aggregation, distil, retirement, delivery installed, removed or fired — MUST record an audit event with its actor.

#### Scenario: audit a requested aggregation and distil with their actor
- **GIVEN** a registered agent with native memory and a partition to distil
- **WHEN** a user updates memory, which requests an aggregation and then a distil pass
- **THEN** exactly one aggregation audit event and one distil audit event name that user as their actor, beside any the daemon's own worker recorded under its own actor

### Requirement: Run one distil pass per partition at a time
Only **one distil pass per partition** may run at a time, whoever started it. An Update memory action that finds a partition's pass in flight MUST **skip** that partition and report it as skipped rather than start a second pass or fail (see "Update memory in one action"), and the interval worker MUST **skip** a partition already being distilled. Which partitions are being rewritten right now MUST be readable. The record is per-daemon and does not outlive it.

#### Scenario: a second distil pass over the same partition is refused while the first is running
- **GIVEN** a synced partition with a distil pass already in flight, and new raw entries for it
- **WHEN** memory is updated, and the interval worker sweeps
- **THEN** neither starts nor queues a second pass over that partition: the update reports it under `skipped`, and the worker moves on to the other partitions
- **AND** the in-flight pass is readable on the shared upkeep-runs surface as `memory` on that partition; once it finishes the runs list is empty again and the next pass runs (see "Run one distil pass per partition at a time")
