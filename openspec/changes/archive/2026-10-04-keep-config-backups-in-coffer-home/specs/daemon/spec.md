## MODIFIED Requirements

### Requirement: Report what Coffer stores and clear the rebuildable cache
The daemon MUST report, for Settings › Data, what Coffer keeps on this machine in the four kinds
of [Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md)
the user acts on, through `GET /api/v1/storage`: the **vault** (the vault repository
`~/.coffer/vault/`, a git repository whether or not it syncs — its path, its size with its
history and how many versions it holds; no version count before the repository has been created), the
**local content** (chat uploads and channel media under `~/.coffer/content/`, which never sync:
their locations, the one folder to open, and their size), the **history** (the database file
holding the records, `~/.coffer/runs.db` unless `COFFER_DB_URL` names another, with its WAL, and
its size together with the log directory's, `~/.coffer/logs/` unless `COFFER_LOG_DIR` names
another, and with the skills' working files in `~/.coffer/skill-data/` and the config backups in `~/.coffer/config-backups/`) and the **rebuildable cache** (the memory tree and the transcript summary cache under
`~/.coffer/derived/`, and their size). Every path MUST come from the same place its owner
resolves it, so an override the owner honours is honoured here.

`POST /api/v1/storage/cache/clear` MUST delete the files of the memory tree and of the transcript
summary cache, and nothing else: no vault, local content, history or other file
under `derived/`, and no partition row, so the next memory update rebuilds each partition from the
agents' own memory. It MUST be refused (`UPKEEP_ALREADY_RUNNING`) while a memory pass is running,
because that pass is writing into the tree, and MUST record the clear in the audit log with the
bytes freed.

#### Scenario: the storage summary reports the four kinds
- **GIVEN** a vault repository of three commits, chat and channel media, a database with its WAL, a memory tree and a transcript summary cache
- **WHEN** `GET /api/v1/storage` is called
- **THEN** it reports the vault as `~/.coffer/vault` with 3 versions, the local content with both media locations under `~/.coffer/content` and their size, the history as `runs.db` with its WAL plus the log directory, `skill-data` and `config-backups`, and the cache as the size of the memory tree and the transcript cache
- **AND** before the vault repository has been created it reports the vault with no version count

#### Scenario: clearing the cache leaves everything else
- **GIVEN** a memory tree, a transcript summary cache, a knowledge document in the vault, chat media, a sync round's hand-merge copy and the database
- **WHEN** `POST /api/v1/storage/cache/clear` is called
- **THEN** the memory tree and the transcript cache are empty, everything else is untouched, the answer carries the bytes freed and the audit log records the clear
- **AND** while a memory pass is running the clear is refused and nothing is deleted
