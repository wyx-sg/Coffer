# vault-storage Specification

## Purpose
Where Coffer keeps what it stores and how anything is written there. State is
split by what it is into five classes under `~/.coffer/`; the vault — the
user's configuration, skills, knowledge and secret ciphertext
— is plain files in a git repository that every writer (a person, the daemon,
sync) changes through one validated, compare-and-swap write that is committed
naming its writer, so any file's history can be read and restored. The
one-time upgrade from the single-database layout lives here too. Sync
(`vault-sync`) only adds a remote to this repository.

## Requirements

### Requirement: Store state in five classes by nature
Coffer SHALL store its state under `~/.coffer/` in five class directories
chosen by what the state is, not by which code writes it: `vault/` (the user's
configuration and content), `local/` (true of this machine only), `content/`
(media and the chat workspace), `runs.db` (history) and `derived/` (rebuilt
from other state). Only `vault/` MUST ever be committed or pushed; nothing
machine-local MUST be written under `vault/`, and nothing that is the only
copy of a fact MUST be written under `derived/`. Everything under `derived/` MUST be
rebuilt by the daemon when it is missing: removing the directory while the daemon is stopped
MUST NOT stop the next start, and that start MUST write it again. The reasoning is
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

#### Scenario: clearing derived state rebuilds it
- **GIVEN** a stopped daemon whose `derived/` holds the health database and Coffer's own skill, delivered to an agent
- **WHEN** `derived/` is removed and the daemon starts again
- **THEN** the start succeeds, `derived/derived.db` and the skill's master folder exist again, and the agent's link into it works
- **AND** the person's own knowledge collections are unchanged

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

### Requirement: Keep every vault document a JSON object that preserves what it does not know
Every document Coffer parses in the vault — resource files, state documents,
machine descriptors — SHALL be a JSON object written with one deterministic
encoding (two-space indent, a trailing newline, keys in the order the file
already has them), so a write that changes nothing makes no commit. A reader
SHALL validate the fields it knows and keep every other top-level field
verbatim, in place, on every write; an unknown top-level field MUST be
reported as a warning and MUST NOT be refused. A resource file's `config` is
its kind's and SHALL hold only the keys the kind's schema declares: a file
whose config holds any other key, a name the kind's name rule refuses, and a
`title` on a kind that has no titles, MUST be refused with a finding naming it — the same rules a registration
through the API meets — whether a person wrote the file or a sync merge
brought it.

#### Scenario: a document round-trips to the same bytes
- **GIVEN** a resource file written by Coffer
- **WHEN** it is read and written back unchanged
- **THEN** its bytes are identical and no commit is made

#### Scenario: a field this build does not know survives a write
- **GIVEN** a resource file carrying a top-level field this build does not know
- **WHEN** Coffer changes the resource's config
- **THEN** the field is still in the file, in the same place, with the same value

#### Scenario: a config key the kind does not declare is refused
- **GIVEN** a registered resource
- **WHEN** a person adds a config key its kind does not declare to its file
- **THEN** the edit is not committed and a finding names the key
- **AND** the resource keeps its last valid config

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

### Requirement: Keep secret ciphertext as one file per reference
The ciphertext of every stored secret SHALL be one file, `vault/secret/<ref>.enc`,
holding the Fernet token and a trailing newline, with `/` in a reference as a
directory separator and every other byte outside `[A-Za-z0-9._-]` encoded
reversibly; a reference that would leave its directory MUST be refused. A
machine-local secret (a model-proxy token) SHALL be kept under `local/secret/`
and MUST NEVER be written into the vault. The files SHALL be `0600` in `0700`
directories, and no directory Coffer creates for secrets SHALL be named
`secrets`.

#### Scenario: a secret is only ciphertext in its file
- **GIVEN** a secret stored through Coffer
- **WHEN** its file under `vault/secret/` is read
- **THEN** it holds the Fernet token and a newline, never the value

#### Scenario: a proxy token stays machine-local
- **GIVEN** a model-proxy token stored for an agent
- **WHEN** the vault and `local/` are listed
- **THEN** the token's ciphertext is under `local/secret/` and nowhere under `vault/`

### Requirement: Read a held file from disk and tell the reconciler about every change
A file sync deliberately leaves different from `HEAD` (a joined machine's file
waiting for the person's choice) SHALL be in effect as it is on disk and MUST
NOT be settled. Every commit another writer makes to a resource or state
document — a settled hand edit, a sync checkout, a restore — SHALL refresh the
stores and reach the reconciler and the event stream exactly as an API write
does, once.

#### Scenario: a held file is in effect from disk
- **GIVEN** a resource file held by a join with this machine's version on disk
- **WHEN** the resource is read
- **THEN** it answers the version on disk, and the file is not committed

#### Scenario: a hand edit reaches the reconciler like an API write
- **GIVEN** a person edits a resource file and the vault settles it
- **WHEN** the commit lands
- **THEN** one change for that resource reaches the reconciler and the event stream

### Requirement: Move an existing home into the vault layout once, on request, reversibly
Moving a home from the single-database layout SHALL be one explicit step,
`coffer migrate`, run with the daemon stopped; the daemon MUST refuse to start
on a home that still holds only `coffer.db` and name that command. The step
SHALL back up `coffer.db` (and its `-wal`/`-shm`) as `coffer.db.pre-vault` and
keep the old knowledge history, the stamped documents and `daemon-config.json`
under `~/.coffer/pre-vault/` before changing anything; SHALL write every
resource, secret, boundary record, state document and machine-local setting
with the stores' own encoding; SHALL move every tree by rename into its class
directory; SHALL replay the old knowledge history into the vault under
`knowledge/`; SHALL commit the vault as one daemon commit with
`Coffer-Layout: db -> 3`; and SHALL rename the database to `runs.db`. Every step
SHALL be recorded before it runs, so `coffer migrate --rollback` restores the
old home byte for byte from a finished or a half-finished upgrade and holds the
home until `coffer migrate --resume`; `coffer migrate --rehearse` SHALL run the
whole upgrade on a copy and leave the source untouched. A sync remote in the old
layout MUST NOT be converted: it is refused until it is rebuilt from an upgraded
machine. When the home holds secrets, the report MUST say, by count only, that
the upgrade carries no approvals, so each secret's first use at each destination
(a provider, an MCP server, a channel, the sync remote) waits once for the
person's approval in the Coffer app.

#### Scenario: the upgrade carries every item
- **GIVEN** a home at the single-database layout with resources of every kind, secrets, approvals, knowledge with history, skills, memory and media
- **WHEN** `coffer migrate` runs
- **THEN** every item is in its class directory with its uid, reach and bytes, and the knowledge history is readable in the vault

#### Scenario: the report says carried secrets wait for approval
- **GIVEN** a home at the single-database layout that holds secrets
- **WHEN** `coffer migrate` finishes
- **THEN** its report counts the secrets and says each one's first use at each destination waits once for approval in the Coffer app

#### Scenario: the daemon refuses a home that was not upgraded
- **GIVEN** a home that holds only `coffer.db`
- **WHEN** the daemon starts
- **THEN** it refuses and names `coffer migrate`

#### Scenario: rollback restores the old home byte for byte
- **GIVEN** a home upgraded by `coffer migrate`
- **WHEN** `coffer migrate --rollback` runs
- **THEN** every file of the old home has its old bytes, the vault is set aside, and the home is held until `coffer migrate --resume`

#### Scenario: a rehearsal leaves the source untouched
- **GIVEN** a home at the single-database layout
- **WHEN** `coffer migrate --rehearse` runs
- **THEN** it reports what the upgrade carries and every byte of the source home is unchanged

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

### Requirement: Refuse to start on a git older than 2.40
The vault's history and every sync round run on the machine's own `git`, and a
round's merge (`merge-tree --write-tree --merge-base`) needs git 2.40. The
daemon MUST check the version before it opens the vault and MUST refuse to
start on an older one, saying which version it found and which it needs. How
git is updated depends on the machine, so the refusal MUST name no installer or
package manager: it carries a prompt the person can give their agent to update
git, as a missing git's refusal does.

#### Scenario: a git older than 2.40 stops the daemon with a hand-off
- **GIVEN** a machine whose `git` reports version 2.30
- **WHEN** the daemon opens the vault
- **THEN** it refuses to start, naming 2.30 and 2.40
- **AND** the refusal carries a prompt asking an agent to update git and confirm with `git --version`, and names no installer
