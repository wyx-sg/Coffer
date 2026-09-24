## MODIFIED Requirements

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
