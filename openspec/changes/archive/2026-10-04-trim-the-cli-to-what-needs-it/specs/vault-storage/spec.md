## MODIFIED Requirements

### Requirement: Show, compare and restore any version of a vault file
The history of any vault file or folder SHALL be readable newest first, each
version with its writer, time and summary; the diff a version made and the
content it left SHALL be readable; and restoring a version SHALL write that
content back through the one write path — with the caller's expected
fingerprint, validated, as a new commit naming the writer and
`Coffer-Restored-From` — never by rewriting history. Restoring a folder SHALL
also remove the files that version did not have. All of this SHALL be reachable
on REST (`/api/v1/vault/history`, `/api/v1/vault/diff`, `/api/v1/vault/content`,
`/api/v1/vault/restore`); the command line carries none of it, and the web UI
shows a version's diff and restores through these routes.

#### Scenario: a file's history lists its versions with their writers
- **GIVEN** a skill file saved twice
- **WHEN** its history is read
- **THEN** two versions are listed, newest first, each naming its writer

#### Scenario: restore is a new commit through the same checks
- **GIVEN** a file with two versions
- **WHEN** a person restores the first, stating the fingerprint of the current content
- **THEN** the file holds the first version's bytes, `HEAD` is a new commit carrying `Coffer-Restored-From`, and no earlier commit was rewritten
- **AND** the same restore with a stale fingerprint is refused and changes nothing

#### Scenario: restoring a folder removes files the version did not have
- **GIVEN** a skill folder that gained a file after a version
- **WHEN** a person restores the folder to that version
- **THEN** the folder holds exactly that version's files

#### Scenario: a symlink and a nested repository are never recorded
- **GIVEN** a skill folder holding a symbolic link and a nested git repository beside its files
- **WHEN** the vault settles the folder
- **THEN** only the regular files are committed, and nothing about the link or the nested repository stays pending

### Requirement: List recent vault changes and the hand edits kept out
The vault's recent commits SHALL be readable newest first, across the whole
vault or under one path prefix, each with its writer, time, summary and the
paths it changed, a page at a time (`GET /api/v1/vault/changes`; one folder's
commits are `GET /api/v1/vault/history` for that folder). The hand edits the
vault refused (see "Keep the last valid version when a hand edit is invalid")
SHALL be listed with the path, the finding's code, severity and message — on
REST as `GET /api/v1/vault/problems` and on the CLI as `coffer vault problems`
(`--json` for scripts), which says so when there are none. `coffer vault
problems` is the only vault command the CLI keeps, because no page lists the
refused edits.

#### Scenario: recent changes list the vault's commits newest first
- **GIVEN** one commit under `knowledge/` and a later one under `skills/`
- **WHEN** the recent changes are read under the prefix `knowledge`, and then for the whole vault two at a time
- **THEN** the first lists only the knowledge commit with the path it changed
- **AND** the second lists two commits and a cursor to the older ones

#### Scenario: refused hand edits are listed on REST and the command line
- **GIVEN** a resource file hand-edited into something that does not parse
- **WHEN** `GET /api/v1/vault/problems` is read
- **THEN** it names the file with the code `invalid_document` and severity `error`
- **AND** with nothing refused, `coffer vault problems` says there are no problems and `--json` prints an empty list
