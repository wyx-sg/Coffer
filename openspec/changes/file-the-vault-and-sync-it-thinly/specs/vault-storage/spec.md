## ADDED Requirements

### Requirement: Store state in five classes by nature
Coffer SHALL store its state under `~/.coffer/` in five class directories
chosen by what the state is, not by which code writes it: `vault/` (the user's
configuration and content), `local/` (true of this machine only), `content/`
(media and the chat workspace), `runs.db` (history) and `derived/` (rebuilt
from other state). Only `vault/` MUST ever be committed or pushed; nothing
machine-local MUST be written under `vault/`, and nothing that is the only
copy of a fact MUST be written under `derived/`. The reasoning is
[Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md).

#### Scenario: each class has its own directory
- **GIVEN** a vault that has been migrated to this layout
- **WHEN** a person lists `~/.coffer/`
- **THEN** it holds `vault/`, `local/`, `content/`, `derived/` and `runs.db`
- **AND** reach, the sync remote and retention settings are under `local/`, never under `vault/`

#### Scenario: deleting derived state loses nothing
- **GIVEN** a running vault with a memory tree, MCP health and skill delivery bindings under `derived/`
- **WHEN** `derived/` is deleted and the daemon restarts
- **THEN** every resource, secret, knowledge document and skill is still present
- **AND** the derived state is rebuilt

### Requirement: Keep the vault a git repository whether or not it syncs
`~/.coffer/vault/` SHALL be a local git repository from the moment it exists,
with a first commit, whether or not a sync remote is configured; configuring
sync SHALL only add a remote. The repository's own `.git/info/exclude` — never
a tracked `.gitignore` — SHALL keep out editor and system litter, hidden
entries inside knowledge collections other than the inbox, and
`secret/` unless the sync remote carries secrets. A path the exclude
file ignores MUST never be staged, neither as a change nor as a deletion.

#### Scenario: a fresh vault is a repository with a first commit
- **GIVEN** a home with no vault
- **WHEN** the vault is first used
- **THEN** `vault/.git` exists, `manifest.json` records schema version 3, and `HEAD` is one commit written by the daemon

#### Scenario: ciphertext is committed only when the remote carries credentials
- **GIVEN** a credential file under `vault/secret/` and a remote that does not carry credentials
- **WHEN** the vault commits
- **THEN** the ciphertext is in no commit
- **AND** once the remote carries credentials, the next commit includes it

### Requirement: Keep every vault document a JSON object that preserves what it does not know
Every document Coffer parses in the vault — resource files, state documents,
machine descriptors — SHALL be a JSON object written with one deterministic
encoding (two-space indent, a trailing newline, keys in the order the file
already has them), so a write that changes nothing makes no commit. A reader
SHALL validate the fields it knows and keep every other key verbatim, in
place, on every write; an unknown field MUST be reported as a warning and
MUST NOT be refused.

#### Scenario: a document round-trips to the same bytes
- **GIVEN** a resource file written by Coffer
- **WHEN** it is read and written back unchanged
- **THEN** its bytes are identical and no commit is made

#### Scenario: a field this build does not know survives a write
- **GIVEN** a resource file carrying a key this build does not know
- **WHEN** Coffer changes the resource's description
- **THEN** the key is still in the file, in the same place, with the same value

### Requirement: Identify a resource by the uid inside its file
A resource file SHALL carry its `uid`, `kind`, `format_version`, `name`,
`description` and `config` (and `title`, `created_at` where set); the path is
where Coffer filed it (`resources/<kind>/<name>.json`) and nothing SHALL key
on the path. A file without a `uid` SHALL be taken as a new resource and given
one by a daemon commit. When two paths claim one uid, the path that did not
hold it at `HEAD` MUST be refused and flagged, and the original MUST stay in
effect. The reasoning is
[A Resource's Identity Is the `uid` Inside Its File](../../../docs/decisions/identity-is-the-uid-inside-the-file.md).

#### Scenario: a copied resource file is flagged and the original is untouched
- **GIVEN** a registered resource and a person's copy of its file under another name
- **WHEN** the vault settles the copy
- **THEN** the copy is not committed and is flagged as a duplicate of the original's path
- **AND** the original resource is unchanged

#### Scenario: a hand-made resource file is given a uid
- **GIVEN** a person writes a valid resource file with no `uid`
- **WHEN** the vault settles it
- **THEN** the person's file is committed as a disk edit and a daemon commit then adds a freshly minted uid

#### Scenario: moving a resource file keeps the resource
- **GIVEN** a registered resource
- **WHEN** a person moves its file to another name in the same kind directory
- **THEN** the resource keeps its uid, its reach and everything that references it

### Requirement: Carry a format version on every vault document
Every vault document Coffer parses SHALL carry an integer `format_version`
for its kind. A file older than this build SHALL be read through the kind's
pure upgrade chain in memory and MUST NOT be rewritten at the new version by an
ordinary write; an edit to it is refused with the reason. A newer file SHALL be
read-only: readable when its `format_compat` is at or below this build's
version, otherwise flagged "written by a newer Coffer" while this build keeps
its last valid version. The reasoning is
[Every Vault File Carries Its Own Format Version](../../../docs/decisions/every-vault-file-carries-its-format-version.md).

#### Scenario: an older file is upgraded in memory only
- **GIVEN** a document at a version below the kind's current one
- **WHEN** this build reads it
- **THEN** the document it answers is at the current version and the file on disk is unchanged

#### Scenario: a newer file is read-only here
- **GIVEN** a document written by a newer build with `format_compat` at this build's version
- **WHEN** this build reads it
- **THEN** it reads the fields it knows and refuses to write the file

### Requirement: Admit every vault write through one compare-and-swap path
Every write to the vault — by the daemon for any surface, by sync, by curation —
SHALL go through one write path that, under the vault's single write lock,
re-reads each file and compares it with what the writer expects (the
fingerprint of the bytes it read, "absent", or "whatever `HEAD` holds"),
writes a sibling temporary file and renames it into place, validates every
touched path, and commits the operation as **one** commit whose author and
`Coffer-Writer`, `Coffer-Operation`, `Coffer-Actor` and `Coffer-Machine`
trailers name the writer. A mismatch MUST refuse the write with
`VAULT_FILE_STALE` (409) and change nothing; there is no unconditional mode,
and a file's modification time MUST NOT decide anything. The reasoning is
[Every Vault Write Is One Validated, Compare-and-Swap Commit That Names Its Writer](../../../docs/decisions/every-vault-write-is-a-validated-commit-naming-its-writer.md).

#### Scenario: a write is one commit naming its writer and machine
- **GIVEN** a vault on a machine with an id
- **WHEN** a person saves a file through Coffer
- **THEN** `HEAD` is one new commit touching exactly that file, whose trailers name the writer `user` and the machine

#### Scenario: a concurrent hand edit is refused rather than lost
- **GIVEN** a person has edited a vault file on disk and the edit is not settled yet
- **WHEN** the daemon writes the same file expecting what `HEAD` holds
- **THEN** the write is refused as stale and the person's bytes are still on disk

#### Scenario: an operation over many files is one commit
- **GIVEN** an operation that writes two files of one skill
- **WHEN** it completes
- **THEN** one commit holds both files

### Requirement: Keep the last valid version when a hand edit is invalid
A person's edits SHALL be found, not intercepted: a file-system watcher is a
hint, and a scan asking git which files differ from `HEAD` is the truth —
at boot, on every hint once the changed paths have been quiet for a second,
and periodically. A valid change SHALL be committed as a `disk` write. A change
that fails validation MUST stay in the working tree uncommitted, MUST be
reported on the attention list with its reason, and the version at `HEAD`
MUST stay in effect until the file is fixed.

#### Scenario: an edit is committed once it is quiet
- **GIVEN** a person saving a vault file twice within a second
- **WHEN** the scanner looks
- **THEN** nothing is committed until the content has stopped changing, and then one `disk` commit holds the last content

#### Scenario: an invalid hand edit stays out of HEAD and is flagged
- **GIVEN** a person saves a resource file that does not parse
- **WHEN** the vault settles it
- **THEN** the file is not committed, the resource keeps its last valid configuration, and the attention list names the file and the reason

### Requirement: Show, compare and restore any version of a vault file
The history of any vault file or folder SHALL be readable newest first, each
version with its writer, time and summary; the diff a version made and the
content it left SHALL be readable; and restoring a version SHALL write that
content back through the one write path — with the caller's expected
fingerprint, validated, as a new commit naming the writer and
`Coffer-Restored-From` — never by rewriting history. Restoring a folder SHALL
also remove the files that version did not have. All of this SHALL be reachable
on REST (`/api/v1/vault/history`, `/api/v1/vault/diff`, `/api/v1/vault/content`,
`/api/v1/vault/restore`) and on the CLI (`coffer vault history|diff|show|restore`).

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
