## ADDED Requirements

### Requirement: Hold a push token pointed at a new URL until approved
Setting the remote MUST resolve its push token for the remote's URL through the
secret boundary ([credentials](../credentials/spec.md) "Hold a secret for a new
destination until a person approves it"). An existing token pointed at a URL it
was not approved for MUST NOT be sent: the remote is saved without the
reachability probe, so the approval has a destination to name; the answer is
`SECRET_BINDING_PENDING` naming the approval, and `coffer sync remote set`
prints "waiting for approval in the Coffer app" and exits `9`, or with
`--wait` sets (and probes) the remote once the approval is applied. A round
MUST send the token only to the URL it is approved for, and fails with the same
refusal until then.

#### Scenario: a push token pointed at a new URL waits for approval
- **GIVEN** a push token already approved for one remote URL
- **WHEN** the remote is set to another URL citing the same token
- **THEN** the token is not sent and the answer names a pending approval for the new URL
- **AND** after the approval is applied, setting the remote again succeeds

## MODIFIED Requirements

### Requirement: Never write the master key into the repository
The master key MUST never be written into the repository. It is bootstrapped
onto another machine out-of-band: a backup is written only by the desktop app,
behind a presence check ([credentials](../credentials/spec.md) "Release
plaintext only to a present human in the desktop app"), and installed on the
other machine with `coffer sync key import`.

#### Scenario: the master key never enters the repository
- **GIVEN** a remote configured to carry credential ciphertext,
- **WHEN** a round pushes,
- **THEN** the tree holds Fernet ciphertext and no key material, and a machine
  without the key reports those refs locked rather than failing decryption.

### Requirement: Cover the sync lifecycle on the command line
The CLI MUST cover the round and the vault's lifecycle — `coffer sync now`,
`adopt [<url>] [--keep-local] [--yes]`, `status`, `history [--limit]`,
`restore [--at <rev|date>]`, `confirm`, `reject`, `rebuild [--yes]`
— and its administration:
`remote set <url> [--branch] [--interval <seconds>] [--with-credentials|--without-credentials] [--credential-ref] [--worktree <path>]`,
`remote clear`, `remote pause`, `remote resume`, `machine list`,
`machine rename <name>`, `machine rm <id>`,
`key import <file>`, `key fingerprint`. There is no `key export`: a key backup
leaves a machine only through the desktop app. An option `remote set` is not given
keeps the stored remote's value, the working tree included. `remote pause` and
`remote resume` switch the remote's `enabled` switch off and on (see "Pause a
configured remote without forgetting it") and change nothing else.

`status` MUST report the configured remote and every one of its settings — URL,
branch, interval, whether credentials travel, the push credential ref, the
working tree and whether the remote is switched on — beside how the last round
went, in plain and `--json` output; with no remote configured it says so and
names `remote set`. `restore` without `--at` undoes the last round that applied
something here (see "Snapshot before applying and roll back from it").

#### Scenario: the command line covers every sync operation
- **GIVEN** the `coffer sync` command group
- **WHEN** its commands and options are listed
- **THEN** it offers `now`, `adopt` with `--keep-local` and `--yes`, `status`, `history` with `--limit`, `restore` with an optional `--at`, `confirm`, `reject` and `rebuild` with `--yes`
- **AND** it offers `remote set` with `--branch`, `--interval`, `--with-credentials`, `--without-credentials`, `--credential-ref` and `--worktree`, `remote clear`, `remote pause`, `remote resume`, `machine list`, `machine rename`, `machine rm`, `key import` and `key fingerprint`, and no `key export`

#### Scenario: pause and resume a remote from the command line
- **GIVEN** a configured, enabled sync remote
- **WHEN** the user runs `coffer sync remote pause`, and then `coffer sync remote resume`
- **THEN** after the first the stored remote is switched off and a requested round reports `disabled`, and after the second it is switched on again
- **AND** the URL, branch, interval, credential settings and working tree are unchanged throughout

#### Scenario: the status command reports the remote's settings
- **GIVEN** a configured remote with a non-default branch, interval, push credential ref and working tree, carrying credentials
- **WHEN** the user runs `coffer sync status --json`
- **THEN** the output carries the remote's URL, branch, interval, credential setting, push credential ref, working tree and enabled switch as stored
- **AND** with no remote configured `coffer sync status` says none is configured and names `coffer sync remote set`

### Requirement: Cover the same operations over HTTP
The HTTP API MUST cover the same operations under `/api/v1/sync`:
`GET|PUT|DELETE /sync/remote`, `POST /sync/run`, `GET /sync/join`, `POST /sync/adopt`,
`GET /sync/status`, `GET /sync/runs`, `POST /sync/restore`,
`POST /sync/confirm`, `POST /sync/reject`, `POST /sync/rebuild`,
`POST /sync/rollback`, `GET /sync/machines`, `PATCH /sync/machines/self`,
`DELETE /sync/machines/{id}`, `GET /sync/key/fingerprint`,
`POST /sync/key/import`. No sync route returns the master key.

#### Scenario: the HTTP API serves every sync operation
- **GIVEN** the daemon's HTTP application
- **WHEN** its routes under `/api/v1/sync` are listed
- **THEN** every method and path the requirement names is served
