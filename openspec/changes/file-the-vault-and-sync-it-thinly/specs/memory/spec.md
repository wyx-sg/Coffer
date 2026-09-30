## MODIFIED Requirements

### Requirement: Partition by repository plus global
A **partition** is a top-level directory under `~/.coffer/derived/memory/` and is one `memory` Resource. There MUST be exactly one partition per repository plus one named `global`; no other partitioning axis exists.

#### Scenario: produce one partition per repository and one global
- **GIVEN** raw entries from two different repositories and one entry about the user's own preferences
- **WHEN** aggregation runs
- **THEN** exactly three partitions exist — one named for each repository and one named `global`
- **AND** each is one `memory` Resource

### Requirement: Keep the memory tree derived and local
The whole tree under `~/.coffer/derived/memory/` MUST be derived: deleting it and re-running aggregation and distil MUST reproduce an **equivalent** partition — the same subjects, from the same sources — though not necessarily the same wording, since the notes are a distillation. It MUST NOT be in the vault, so it never reaches the sync remote ([vault-sync](../vault-sync/spec.md) "Withhold derived output in both halves"): it is derived from the agents installed on *this* machine, so sending it to another would send notes that machine's own next pass would recompute away. **A partition's resource is covered by that too, not only the files** — the `memory` kind files its resources in the derived class, `~/.coffer/derived/resources/memory/`, where no commit and no round ever reaches them ([vault-storage](../vault-storage/spec.md) "Store state in five classes by nature"). Losing the machine loses the derived tree, and that is accepted.

#### Scenario: deleting the memory tree and re-syncing reproduces an equivalent set
- **GIVEN** a distilled partition whose directories are then deleted by hand, with the source-digest cache deliberately left behind
- **WHEN** aggregation and distil run again
- **THEN** the partition is rebuilt: `.raw/` holds the same entries, `notes/` covers the same subjects, and `MEMORY.md` indexes them
- **AND** a digest match alone therefore never suppresses a rebuild — but the notes' wording is **not** required to match the deleted set, because the product is a distillation and not a copy (see "Keep the memory tree derived and local")

#### Scenario: a partition does not travel to the sync remote
- **GIVEN** the partitions an aggregation and a distil pass produced
- **WHEN** Coffer's home is listed
- **THEN** each partition is one resource file under `~/.coffer/derived/resources/memory/` and one directory under `~/.coffer/derived/memory/`, and nothing of either is in the vault, so no commit and no sync round carries them
- **AND** the `memory` kind files every partition in the derived class

### Requirement: Add no table of its own
This layer MUST add **no table of its own**. Notes, raw entries, the index and partition metadata are files, and each partition is one resource file in the derived class.

#### Scenario: keep partitions in the resources table and files only
- **GIVEN** a history database upgraded to head
- **WHEN** its tables are listed after an aggregation and a distil pass
- **THEN** no table is named for memory, and each partition is one resource of kind `memory`, filed under `~/.coffer/derived/resources/memory/`
