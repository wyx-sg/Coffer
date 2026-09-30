## MODIFIED Requirements

### Requirement: Add no table of its own
This layer MUST add **no table of its own**. Notes, raw entries, the index and partition metadata are files, and each partition is one resource file in the derived class.

#### Scenario: keep partitions as resource files and plain files only
- **GIVEN** a history database upgraded to head
- **WHEN** its tables are listed after an aggregation and a distil pass
- **THEN** no table is named for memory, and each partition is one resource of kind `memory`, filed under `~/.coffer/derived/resources/memory/`
