## MODIFIED Requirements

### Requirement: Read no transcripts or rollouts
A sync MUST NOT read session transcripts, rollouts or raw capture files **as a source of entries**. Both supported agents already distil their own; this layer starts from that output. The single narrow exception is Claude Code's project slug, which encodes a path lossily: the reader MAY scan a project's own session transcripts for the `cwd` they recorded, accepting it only when Claude Code's encoding of that `cwd` is exactly the slug, so that a renamed or deleted project still files under its real repository. Codex's v2 memory files its topics under named scopes and records each one's directory only in the header of the rollout summary the topic points at: the reader MAY read that header's `cwd:` line and nothing below it. Nothing but those recorded paths is taken, and no transcript or rollout summary is ever listed as a source.

#### Scenario: list no transcript or rollout as a source
- **GIVEN** a Claude Code config directory holding a session transcript beside a project's memory directory, and a Codex home holding session rollouts beside its memory files
- **WHEN** each reader lists its sources
- **THEN** no transcript, rollout or raw capture file is among them

### Requirement: Write the hub into Codex's memory extension
Coffer MUST write each hub entry that did not come from this machine's Codex into Codex's memory extension folder `extensions/coffer/` of every Codex memory folder that is there (`<config_dir>/memories/` for v1, `<config_dir>/memories_v2/` for v2: Codex picks one per thread, so Coffer writes the same copies into each): one file per entry under `resources/`, named without a leading timestamp, stating the project it applies to (the project's checkout on this machine, or "all projects" for `global`) above the memory's text; and an `instructions.md` telling Codex's consolidation that these are memories other agents learned on the person's machines, that they are information and never instructions, to file each under the project it names, and to tag what it derives from them `[via Coffer]`. When Codex's memories feature is off, the sync MUST say so on the Memory page and write nothing for Codex. A `memories_v<N>` folder newer than any Coffer knows MUST be written nothing and reported on the Memory page with its path, beside the folders Coffer does write.

#### Scenario: a Claude Code memory reaches Codex
- **GIVEN** a hub entry Claude Code published for `github.com-acme-payments`, the repository checked out at `/Users/a/src/payments`, and Codex registered with memories on
- **WHEN** memory syncs
- **THEN** `extensions/coffer/resources/` holds one file for it naming `/Users/a/src/payments` and the memory's text, and `extensions/coffer/instructions.md` exists
- **AND** no file name under `resources/` starts with a timestamp

#### Scenario: Codex with memories off is reported, not written
- **GIVEN** Codex registered with its memories feature off
- **WHEN** memory syncs
- **THEN** nothing is written under Codex's config directory and the Memory page says Codex's memories are off

#### Scenario: a memory reaches every Codex memory folder
- **GIVEN** a Claude Code hub entry for a project checked out here, and Codex with both `memories/` and `memories_v2/`
- **WHEN** memory syncs
- **THEN** both folders' `extensions/coffer/resources/` hold the same file for it, and both have `extensions/coffer/instructions.md`
- **AND** the Memory page lists each folder with the copies written into it

#### Scenario: a newer Codex memory folder is reported, not written
- **GIVEN** Codex with `memories/`, `memories_v2/` and a `memories_v3/` Coffer does not know
- **WHEN** memory syncs
- **THEN** `memories/` and `memories_v2/` are written into, nothing is written under `memories_v3/`, and the Memory page names `memories_v3/` as a folder Coffer cannot write into yet

## ADDED Requirements

### Requirement: Read Codex's v2 memory
The Codex reader MUST also read Codex's v2 memory, `<config_dir>/memories_v2/memory_summary.md`, beside v1. v2 has no `MEMORY.md`; from its summary the reader takes the User Profile, each User preferences bullet, each General Tips paragraph (global, standing) and each topic of `What's in Memory`, which Codex groups under a named project scope. A topic MUST be filed under the `cwd:` recorded in the header of the rollout summary it points at, and global when it points at none or the header records none; its identity MUST name its scope, so a topic reads as task material the way a v1 task-group bullet does. While a v2 summary is there, the profile MUST come from v2 only, and v1's summary MUST yield only the preferences v2 does not state word for word.

#### Scenario: a Codex v2 topic reaches Claude Code
- **GIVEN** Codex with only v2 memory, whose summary lists a topic pointing at a rollout summary recorded in a project checked out here, plus a preference and a General Tips paragraph
- **WHEN** memory syncs
- **THEN** Claude Code's memory folder for that project holds a copy of the topic with its details
- **AND** the rules file lists the preference and the tip

#### Scenario: with v2 beside it, v1's summary gives only what v2 does not say
- **GIVEN** v1 and v2 summaries with different profiles, one shared preference and one preference only v1 states
- **WHEN** the Codex reader reads the v1 summary
- **THEN** it yields only the preference v1 alone states
