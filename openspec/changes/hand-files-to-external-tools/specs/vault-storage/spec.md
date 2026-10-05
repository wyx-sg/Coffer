## ADDED Requirements

### Requirement: Hand restoring an earlier version of a vault file to an agent
The vault's history is git's, read and restored with git or by the person's agent; Coffer SHALL NOT list, diff or restore versions itself. `POST /api/v1/vault/history/handoff` SHALL take a vault-relative `path` — a file, or a folder ending in `/` — and an optional `at` time, and answer the path's absolute location, the vault's absolute path, the command that prints the path's history (`git -C <vault> log -p -- <path>`) and a hand-off prompt built by the daemon from the same module every hand-off uses. The prompt SHALL state the path and, when `at` is given, that it is to be brought back to how it was at that time — otherwise that the agent lists its recent versions and asks the person which one; that the vault is a git repository at the vault's path whose history is never rewritten (no reset, amend, rebase or force push); that the earlier content is written back into the working tree touching only that path — for a folder, removing the files that version did not have — and committed as one new commit whose message carries `Coffer-Writer: agent`, `Coffer-Operation: restore` and `Coffer-Restored-From: <commit>`, the trailers that name a vault commit's writer; and that the agent tells the person what it restored. The prompt SHALL carry no secret, and a path under `secret/` or outside the vault SHALL be refused (`VAULT_PATH_REFUSED`). The route writes nothing and records no audit event; the commit the agent makes is validated like any other change to the vault.

#### Scenario: the restore hand-off names the file, the time and the commit rules
- **GIVEN** a knowledge document in the vault
- **WHEN** the restore hand-off is asked for with the document's path and a time
- **THEN** the answer carries the document's absolute path, the vault's path and `git -C <vault> log -p -- <path>`, and the prompt names the path, the time, that history is never rewritten and the three `Coffer-` trailers of the commit to make
- **AND** asked without a time, the prompt says to list the recent versions and ask which one

#### Scenario: a secret's history is never handed over
- **GIVEN** a credential file under `secret/`
- **WHEN** the restore hand-off is asked for with its path, or with a path that leaves the vault
- **THEN** each is refused `VAULT_PATH_REFUSED` and no prompt is built

#### Scenario: a version written back and committed outside Coffer is a new commit
- **GIVEN** a file with two versions in the vault's history
- **WHEN** the first version's bytes are written back into the file and committed outside Coffer with the restore trailers
- **THEN** `HEAD` is a new commit whose writer reads `agent` and that names the commit restored from, and no earlier commit was rewritten

### Requirement: List the hand edits the vault kept out
The hand edits the vault refused (see "Keep the last valid version when a hand
edit is invalid") SHALL be listed with the path, the finding's code, severity
and message — on REST as `GET /api/v1/vault/problems` and on the CLI as
`coffer vault problems` (`--json` for scripts), which says so when there are
none. `coffer vault problems` is the only vault command the CLI keeps, because
no page lists the refused edits.

#### Scenario: refused hand edits are listed on REST and the command line
- **GIVEN** a resource file hand-edited into something that does not parse
- **WHEN** `GET /api/v1/vault/problems` is read
- **THEN** it names the file with the code `invalid_document` and severity `error`
- **AND** with nothing refused, `coffer vault problems` says there are no problems and `--json` prints an empty list

## MODIFIED Requirements

### Requirement: Keep the vault a git repository whether or not it syncs
`~/.coffer/vault/` SHALL be a local git repository from the moment it exists,
with a first commit, whether or not a sync remote is configured; configuring
sync SHALL only add a remote. The repository's own `.git/info/exclude` — never
a tracked `.gitignore` — SHALL keep out editor and system litter, hidden
entries inside knowledge collections other than the inbox, and
`secret/` unless the sync remote carries secrets, which the daemon reads from this machine's stored
remote when it opens the vault, not only once a sync round has run. A path the exclude
file ignores MUST never be staged, neither as a change nor as a deletion, and
neither MUST a symbolic link or anything inside a nested git repository.

#### Scenario: a fresh vault is a repository with a first commit
- **GIVEN** a home with no vault
- **WHEN** the vault is first used
- **THEN** `vault/.git` exists, `manifest.json` records schema version 3, and `HEAD` is one commit written by the daemon

#### Scenario: ciphertext is committed only when the remote carries secrets
- **GIVEN** a credential file under `vault/secret/` and a remote that does not carry credentials
- **WHEN** the vault commits
- **THEN** the ciphertext is in no commit
- **AND** once the remote carries secrets, the next commit includes it

#### Scenario: a secret written before the first sync round is committed
- **GIVEN** a machine whose stored remote carries secrets, and a daemon that has just started
- **WHEN** the daemon opens the vault, before any sync round has run
- **THEN** `secret/` is not excluded, so a secret written now is committed with that write

#### Scenario: a symlink and a nested repository are never recorded
- **GIVEN** a skill folder holding a symbolic link and a nested git repository beside its files
- **WHEN** the vault settles the folder
- **THEN** only the regular files are committed, and nothing about the link or the nested repository stays pending

## REMOVED Requirements

### Requirement: Show, compare and restore any version of a vault file
**Reason**: Coffer is not a second git client (principles, What Coffer is not › Not a second agent). Reading a file's versions, their diffs and restoring one is what git and the person's agent do; the web UI's History tabs that called these routes are removed.
**Migration**: `GET /api/v1/vault/history`, `/vault/diff`, `/vault/content`, `POST /vault/restore` and `VAULT_VERSION_NOT_FOUND` are removed. Use `git log -p` in the vault or the hand-off of "Hand restoring an earlier version of a vault file to an agent". The symlink rule moves to "Keep the vault a git repository whether or not it syncs".

### Requirement: List recent vault changes and the hand edits kept out
**Reason**: `GET /api/v1/vault/changes` had no caller once the version browsers were removed; the vault's recent commits are `git log`'s.
**Migration**: The refused hand edits keep their list, in "List the hand edits the vault kept out". `GET /api/v1/vault/changes` is removed.
