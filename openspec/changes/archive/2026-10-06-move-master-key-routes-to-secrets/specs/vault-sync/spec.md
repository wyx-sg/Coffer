## REMOVED Requirements

### Requirement: Import a master key after showing whose key it is
**Reason**: The master key is the secret store's, not sync's. Its routes sat under `/api/v1/sync`, behind the experimental `sync` feature, while Settings › Security shows the key's fingerprint and offers the import whatever that switch says, so with sync off both were refused.
**Migration**: The requirement moves unchanged in substance to [secret](../secret/spec.md) "Import a master key after showing whose key it is". `GET /api/v1/sync/key/fingerprint`, `POST /api/v1/sync/key/import/preview` and `POST /api/v1/sync/key/import` become `/api/v1/secrets/key/fingerprint`, `/api/v1/secrets/key/import/preview` and `/api/v1/secrets/key/import`; `coffer sync key fingerprint`, `import-preview` and `import` become `coffer secret key-fingerprint`, `key-preview` and `key-install`. The web UI and the desktop app move with it in the same release.

## MODIFIED Requirements

### Requirement: Cover the same operations over HTTP
The HTTP API MUST cover the same operations under `/api/v1/sync`:

- `GET /status`, `POST /run`, `GET /runs` and `GET /runs/{id}`;
- `GET /runs/{id}/rollback-plan` and `POST /runs/{id}/rollback`;
- `GET|PUT|DELETE /remote`, `POST /remote/check` and `POST /remote/restore`;
- `GET /join/preview`, `POST /join`, `GET|POST /join-choices`, and `POST /join-choices/editor`,
  `/join-choices/handoff` and `/join-choices/discard`;
- `GET /stop`, `POST /stop/files/answer`, `POST /stop/files/editor`, `GET /stop/files/versions`,
  `POST /stop/handoff`, `POST /stop/files/discard` and `POST /continue`;
- `POST /hold/confirm` and `POST /hold/restore`;
- `POST /plaintext/push-anyway`;
- `GET /machines`, `PATCH /machines/self`, `DELETE /machines/{id}` and `POST /machines/{id}/restore`.

No sync route returns the master key: the key's own routes are the secret
store's, under `/api/v1/secrets/key` ([secret](../secret/spec.md)
"Import a master key after showing whose key it is").

#### Scenario: the HTTP API serves every sync operation
- **GIVEN** the daemon's sync routes
- **WHEN** they are listed
- **THEN** every method and path the requirement names is served, and none exports a key

### Requirement: Publish the key fingerprint in the descriptor
`key_fingerprint` MUST be the same short hash `GET /api/v1/secrets/key/fingerprint`
returns, so the machines table can state directly that another machine's
secrets cannot be decrypted here instead of the user comparing fingerprints
by hand.

#### Scenario: a peer holding another master key is flagged
- **GIVEN** a machine that has converged
- **WHEN** its descriptor is read and `GET /api/v1/secrets/key/fingerprint` is asked on that machine
- **THEN** the descriptor's `key_fingerprint` is the value the route returns
- **AND** the machines table says that a peer whose fingerprint differs from this machine's has secrets that cannot be decrypted here

### Requirement: Never write the master key into the repository
The master key MUST never be written into the vault: it stays in the OS
credential store or `~/.coffer/master.key`, outside the repository. It is
bootstrapped onto another machine out-of-band: a backup is written only by the
desktop app, behind a presence check ([secret](../secret/spec.md)
"Release plaintext only to a present human in the desktop app"), and installed
on the other machine from Settings › Security ([secret](../secret/spec.md) "Import a master key after showing whose key it is").

#### Scenario: the master key never enters the repository
- **GIVEN** a remote configured to carry secret ciphertext, and a key file beside the vault
- **WHEN** a round pushes
- **THEN** the remote holds the ciphertext files and no key material

### Requirement: Answer each conflicting file and continue the round
A round stopped on conflicts SHALL list each conflicting file with why it
conflicts (both sides changed it, one side deleted what the other changed, a
same-name resource with another uid, a merged file validation refused) and the
machine whose version it met. The person SHALL answer each file — **keep this
machine's**, **take the other's**, or **edit** it by hand in an editor copy
Coffer writes under `derived/sync-conflicts/` with git's conflict markers — and
then continue the round, which validates, guards, snapshots, checks out and
pushes the resolved tree. An edited answer MUST be refused while a conflict
marker is left in the file, naming the line. The answers SHALL stand only while
neither side moves: when this vault or the remote has a new commit, the round is
asked again. Answering SHALL be reachable on REST (`GET /api/v1/sync/stop`,
`POST /api/v1/sync/stop/files/answer`, `POST /api/v1/sync/stop/files/editor`,
`GET /api/v1/sync/stop/files/versions`, `POST /api/v1/sync/continue`), on the command line
(`coffer sync file-answer`, whose help names exactly the answers the route accepts:
`mine`, `theirs` and `edited`, the last keeping the editor copy) and on the Sync page.

#### Scenario: keeping this machine's version continues the round
- **GIVEN** a round stopped because both machines changed the same lines of one document
- **WHEN** the person keeps this machine's version and continues
- **THEN** the round pushes that version, the stop is cleared, and the other machine takes it on its next round

#### Scenario: a hand merge with conflict markers left is refused
- **GIVEN** a stopped round whose conflicting file was opened in the editor copy, which holds git's conflict markers
- **WHEN** the person answers "edited" with a marker still in the file
- **THEN** the answer is refused naming the line
- **AND** once the markers are gone the edited text is what both machines end up holding

#### Scenario: a stop is asked again when the remote moves
- **GIVEN** a round stopped on a conflict nobody has answered
- **WHEN** the other machine pushes another change to the same file and a round runs here
- **THEN** the round stops again on the remote's new commit rather than on the one first asked about
