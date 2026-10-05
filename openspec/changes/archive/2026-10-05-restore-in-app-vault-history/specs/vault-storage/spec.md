## ADDED Requirements

### Requirement: Show and restore any version of a vault file or folder
The history of any vault file or folder SHALL be readable newest first, each version with its writer — the `Coffer-Writer` of its commit, `agent:<type>` for an agent — its time, its summary, the version it restored when it is a restore, and the files it touched inside the path with their line counts (`GET /api/v1/vault/history`). A version's diff SHALL be readable file by file, either as what that version changed or as how the path differs now from how that version left it (`GET /api/v1/vault/diff` with `against=previous` or `against=current`). Before either read, an edit found on disk under the path SHALL be committed as a `disk` write, so the newest version is the path as it is. Restoring a version (`POST /api/v1/vault/restore`) SHALL write that content back through the one write path, validated, as one new commit naming the writer and carrying `Coffer-Operation: restore` and `Coffer-Restored-From`, never by rewriting history; restoring a folder SHALL also remove the files that version did not have. The caller SHALL state the newest version it saw (`expected_current`), and a restore after the path changed — a later commit, or an edit on disk — SHALL be refused `409 VAULT_FILE_STALE` with nothing written. Each restore SHALL be audited as `vault_file_restored`. A path under `secret/` or outside the vault SHALL be refused `400 VAULT_PATH_INVALID`, and a version that is not in the path's history `404 VAULT_VERSION_NOT_FOUND`. The command line carries none of it; the web UI reads and restores through these routes.

#### Scenario: a file's history lists its versions with their writers
- **GIVEN** a document the user wrote, an agent then changed through Coffer, and the person then edited in their own editor
- **WHEN** its history is read
- **THEN** three versions are listed newest first, written on disk, by the agent and by the user, each with the file it touched and its line counts

#### Scenario: a version's diff reads against the one before it or the current
- **GIVEN** a skill folder whose `SKILL.md` was written twice and that later gained a file
- **WHEN** the second version's diff is read against the one before it, and the first version's against the current
- **THEN** the first shows `SKILL.md`'s changed line, and the second shows `SKILL.md` modified and the later file added
- **AND** a version that did not touch the path, or that is not a version at all, is not found

#### Scenario: restore is a new commit through the same checks
- **GIVEN** a file with two versions
- **WHEN** a person restores the first, stating the second as the newest version they saw
- **THEN** the file holds the first version's bytes, `HEAD` is a new commit naming the person and carrying `Coffer-Restored-From`, no earlier commit was rewritten, and the restore is audited
- **AND** the same restore stating the first as the newest version they saw is refused as stale and changes nothing

#### Scenario: restoring a folder removes files the version did not have
- **GIVEN** a skill folder that gained a file after a version
- **WHEN** a person restores the folder to that version
- **THEN** the folder holds exactly that version's files

#### Scenario: a secret's history is never read or restored
- **GIVEN** a credential file under `secret/`
- **WHEN** its history, a diff or a restore is asked for, or the history of a path that leaves the vault
- **THEN** each is refused `VAULT_PATH_INVALID`

## REMOVED Requirements

### Requirement: Hand restoring an earlier version of a vault file to an agent
**Reason**: Coffer reads a vault file's history and restores a version itself (see "Show and restore any version of a vault file or folder"), so the hand-off has no caller.
**Migration**: `POST /api/v1/vault/history/handoff` is removed. Read a file's versions with `GET /api/v1/vault/history` and restore one with `POST /api/v1/vault/restore`, or open the document's or skill's History tab.
