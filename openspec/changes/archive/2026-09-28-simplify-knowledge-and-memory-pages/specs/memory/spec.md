## ADDED Requirements

### Requirement: Serve every partition to every agent
A partition MUST NOT carry the Resource framework's per-agent reach or an enabled switch: the kind declares itself non-toggleable ([resource-framework](../resource-framework/spec.md) "Address every resource by an immutable uid through one kind-agnostic surface"). Every partition MUST be served to **every** agent, on both paths Coffer itself serves — delivery (see "Deliver the index and the notes path at session start") and recall (see "Recall locations by literal match"). Aggregating the memory of several agents into one place exists so that each agent can read what the others learned, so a partition is served to the agents that contributed nothing to it as much as to those that did.

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

## MODIFIED Requirements

### Requirement: Cover memory management on REST and the CLI
A REST family under `/api/v1/memory` and a `coffer memory` CLI group MUST cover: list partitions and notes, show one note with its provenance, browse a partition's own directory and read one file from it, update memory (see "Update memory in one action"), run a distil pass over one partition, compose the session context, read what has been retired, and install/inspect/remove delivery for an agent.

#### Scenario: a partition's own directory is browsable as a file tree
- **GIVEN** a distilled partition
- **WHEN** its file tree is requested, and then one file out of it
- **THEN** the tree's root carries the partition directory's absolute path and holds `MEMORY.md`, a `notes/` directory listing one Markdown file per note, and `RETIRED.md` when anything has been retired; reading `notes/<slug>.md` returns its text — not binary, not truncated — with the absolute path of the file and of the folder holding it
- **AND** `.raw/` is not in the tree and reading a path under it is refused, the family is read-only (a write is refused with 405), and a path escaping the partition is refused with `MEMORY_UNSAFE_PATH` (400) (see "Present partitions as a table and a file tree", "Confine reads to registered agents' memory paths")

### Requirement: Present partitions as a table and a file tree
The web UI MUST present partitions **as a table** once any exists; with none, it shows the first-run welcome every other empty surface shows. One partition MUST be presented as a **file tree over its own directory** with a read-only preview beside it — the same two panes a skill's Files tab is — showing `MEMORY.md`, `notes/` and `RETIRED.md`, and MUST offer open-in-editor and reveal-in-file-manager on the previewed file. A note's frontmatter MUST be shown as metadata above its body, not rendered as body text. The tree and the preview MUST extend to the bottom of the window and scroll inside. It MUST NOT carry per-note actions: a partition is a folder of derived Markdown, and the surface that browses it says so by looking like one.

#### Scenario: browse a partition as a file tree with a read-only preview
- **GIVEN** the memory pages, with no partitions and then with one distilled partition that holds raw entries
- **WHEN** the partitions page and the partition's page render and a note is chosen in the tree
- **THEN** the partitions page shows the first-run welcome with none and the table with one, and the partition's page shows a file tree holding `MEMORY.md` and `notes/` and no `.raw/`, beside a read-only preview of the chosen note whose frontmatter is not in the rendered body
- **AND** the preview offers open-in-editor and reveal-in-file-manager and no per-note edit or delete action

### Requirement: Recall locations by literal match
`coffer__recall` MUST take a word or phrase, span every partition (see "Serve every partition to every agent"), exclude retired notes and `.raw/`, and return each match's **absolute path**, title and description — not its body, which the caller reads for itself (see "Keep notes readable as plain files"). Matching MUST be a case-insensitive literal scan with no score, no mode and no reason in the answer, and MUST need no internal connection. Its job is to answer "where is the note about X" for a partition the session was not opened in; for the partition it *was* opened in, the index is already in front of the caller and recall should not be needed at all.

#### Scenario: recall answers with locations, and never with a retired note
- **GIVEN** a partition holding notes, one of them retired, both matching a distinctive phrase
- **WHEN** `coffer__recall` is called with that phrase
- **THEN** the active note comes back with its **absolute path**, title and description, and the retired one does not
- **AND** the answer spans every partition, whichever agent is asking, and carries no score, no mode and no ranking (see "Serve every partition to every agent", "Recall locations by literal match")

## REMOVED Requirements

### Requirement: Serve every enabled partition to every agent
**Reason**: Nobody disables a partition, and a disabled partition was still a file any agent could open.
**Migration**: Replaced by "Serve every partition to every agent"; a migration enables every partition stored disabled.
