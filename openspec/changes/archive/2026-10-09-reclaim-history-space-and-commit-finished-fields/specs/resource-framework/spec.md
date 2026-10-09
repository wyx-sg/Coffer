## ADDED Requirements

### Requirement: Give the space pruning frees back to the disk
Pruning deletes rows from `~/.coffer/runs.db`, and SQLite keeps the pages those rows
used as free pages inside the file. After each periodic retention pass the daemon MUST
rebuild the history database (`VACUUM`) when its free pages are at least half of the
file and add up to at least 8 MB, then truncate its write-ahead log, so the file shrinks
to the history it holds. A file below either threshold MUST be left untouched. The rebuild
MUST NOT stop the daemon serving: it runs off the request path, readers carry on while
it runs, and a writer waits for it as for any other lock. The reasons and the options
weighed are in [Audit Every Change With Its Actor, Log Every Invocation, Prune Per Table](../../../docs/decisions/audit-and-retention.md).

#### Scenario: a prune that leaves runs.db mostly empty shrinks the file
- **GIVEN** a `runs.db` that held 3,000 audit rows of about 4 KB and kept 10 after a prune
- **WHEN** the retention worker finishes its pass
- **THEN** the file holds no free pages and is as large as its pages, and the 10 rows are still there
- **AND** a file where most pages hold data, or whose free pages add up to less than 8 MB, is left as it was
