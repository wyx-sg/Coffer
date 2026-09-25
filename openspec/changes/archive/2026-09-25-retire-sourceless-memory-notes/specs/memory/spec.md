## ADDED Requirements

### Requirement: Retire a note whose raw entries are all gone
Every distil pass — the model-driven one and the mechanical one alike — MUST first retire each note **none** of whose provenance entries is still under its partition's `.raw/`. Aggregation removes a raw entry when its source stops producing it: the agent deleted the fact, or placement now files it into a different partition (see "File personal entries into global"). A note is derived from what `.raw/` holds (see "Keep the memory tree derived and local"), so one with no source left MUST NOT stay in `notes/`, in the index, in delivery or in recall — otherwise the same lesson is served from two partitions once placement moves its entries.

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

## MODIFIED Requirements

### Requirement: Distil mechanically with no internal connection
With no internal connection configured, distil MUST still produce a usable partition **mechanically**: each raw entry becomes a note of its own, and `MEMORY.md` is written from their frontmatter. It MUST NOT be a no-op — an installation with no internal model still gets an index and a delivery, thinner rather than absent — and it MUST NOT call a model on any path. It proposes no merge and no retirement by contradiction, because both are judgements about meaning; it still retires a note whose raw entries are all gone (see "Retire a note whose raw entries are all gone"), because that is not a judgement.

#### Scenario: distil degrades to a usable index with no internal connection
- **GIVEN** a partition holding raw entries and **no** internal connection configured
- **WHEN** the distil pass runs
- **THEN** no model is called, no merge and no retirement is proposed, and each raw entry is carried through to a note of its own
- **AND** `MEMORY.md` is still written, one line per note from its frontmatter, so an installation with no internal model still gets an index and a delivery — thinner, not absent (see "Distil mechanically with no internal connection")
