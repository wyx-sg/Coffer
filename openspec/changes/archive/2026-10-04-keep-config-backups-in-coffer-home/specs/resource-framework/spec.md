## ADDED Requirements

### Requirement: Retain config backups on an adjustable policy
The copies Coffer makes of an agent's own config file before it rewrites or deletes it MUST
live in Coffer's own folder and MUST NOT accumulate without bound: `~/.coffer/config-backups/`,
outside the vault so they never sync. Each config file has one folder there, named
`<file name>-<12 hex digits of the sha-256 of its absolute path>` so that two files with the same
name stay apart, and each backup in it is named by the UTC time it was taken
(`YYYYMMDDTHHMMSSffffffZ`) with the file's own extension. One retention policy named
`config_backups` covers the whole directory. It is listed by `GET /api/v1/retention/policies`
and set by `PATCH /api/v1/retention/policies/config_backups` like any other policy (a whole
number of days, or `forever`; the change is audited), its default is 30 days, and it is seeded
at daemon start. A backup is past the window when its modification time is older than the
window. On the retention cadence and on a full prune, backups past the window are deleted
EXCEPT the newest backup of each config file, which is kept however old it is so that an undo
of the last write is always possible; folders left empty are removed (never `config-backups`
itself), and the prune answers how many files it removed under `config_backups`; under
`forever` nothing is deleted. A prune naming `config_backups` sweeps only it, a symlink is
neither followed nor deleted, and a sweep that fails is logged and skipped. `GET
/api/v1/retention/policies/config_backups/preview?days=<n>` counts the files held now and how
many a window of `n` days would delete (the newest of each file excluded), and deletes nothing.

#### Scenario: old config backups are swept but each file's newest is kept
- **GIVEN** a fresh daemon, three backups of one config file 40, 35 and 2 days old, and two backups of another 90 and 60 days old
- **WHEN** a full retention prune runs
- **THEN** `GET /api/v1/retention/policies` lists `config_backups` at 30 days
- **AND** the 40 and 35 day old backups of the first file and the 90 day old backup of the second are deleted, the 2 day old one and the 60 day old one (the newest of its file) are kept, and the prune answers three files under `config_backups`

#### Scenario: config backups kept forever are never swept
- **GIVEN** the `config_backups` policy set to `forever` and two backups of one file, 400 and 500 days old
- **WHEN** a full retention prune runs
- **THEN** both are kept and the prune answers no files removed under `config_backups`

#### Scenario: the config backups preview counts files and deletes none
- **GIVEN** the `config_backups` policy at 30 days and five backups of one file, aged 1, 3, 10, 20 and 40 days
- **WHEN** a client asks for the preview for 7 days
- **THEN** the answer carries 5 now and 3 to delete, and every file is still there
