## REMOVED Requirements

### Requirement: Read only registered and enabled agents' memory
**Reason**: An agent can no longer be disabled, so "registered and enabled" is just "registered".
**Migration**: See "Read only registered agents' memory". The acceptance marker for "read nothing from a disabled or unregistered agent" moves to "read nothing from an unregistered agent".

## MODIFIED Requirements

### Requirement: Retire a note whose raw entries are all gone
Every distil pass — the model-driven one and the mechanical one alike — MUST first retire each note **none** of whose provenance entries is still under its partition's `.raw/`. Aggregation removes a raw entry when its source stops producing it: the agent deleted the fact, or deleted the whole source file (judged only for a registered agent whose config directory is still there — a directory that is missing lists nothing and proves nothing), or placement now files it into a different partition (see "File personal entries into global"). A note is derived from what `.raw/` holds (see "Keep the memory tree derived and local"), so one with no source left MUST NOT stay in `notes/`, in the index or in delivery — otherwise the same lesson is served from two partitions once placement moves its entries.

Such a retirement MUST be recorded in `RETIRED.md` like any other (see "Record retirements so they stick"), with a reason saying its sources are gone. Because nothing judged the note untrue, the record MUST NOT exclude anything from later passes: it names no raw entries, and its title MUST NOT be handed to routing as a retired subject, so material that comes back is distilled afresh. A note with at least one provenance entry still under `.raw/` MUST be left alone, and so MUST a note that names no provenance at all.

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
- **WHEN** a raw entry on the retired note's subject is aggregated into the partition again and the distil pass runs with an internal connection
- **THEN** the note with a surviving entry is untouched, the routing request does not list the sources-gone title among the retired subjects, and the returning entry is distilled like any new one

## ADDED Requirements

### Requirement: Read only registered agents' memory
Coffer MUST read the native memory of each **registered** agent, from a path derived from that agent's own `config_dir` ([agent-registry](../agent-registry/spec.md)). An agent that is not registered MUST NOT be read.

#### Scenario: read nothing from an unregistered agent
- **GIVEN** fixture memory for a registered agent and in a config directory no registered agent names
- **WHEN** aggregation runs
- **THEN** raw entries come only from the registered agent's memory
- **AND** nothing is read from the unregistered directory
