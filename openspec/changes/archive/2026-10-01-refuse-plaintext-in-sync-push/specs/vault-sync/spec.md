## ADDED Requirements

### Requirement: Refuse to push a plaintext secret
Before a round pushes — a round that merged, a push with nothing to pull, or a join — it MUST read
every file version the push would publish: each blob reachable from the commit being pushed and
not from the remote's head, from every commit in between. It reads them with the detection
`coffer secret scan` uses (an assignment whose name says secret, and the well-known token shapes).
An encrypted `secret/<ref>.enc` file is ciphertext and MUST NOT be read; a binary file or one over
1 MB is not read either.

When a file still holds a value at the commit being pushed, the round MUST push nothing and record
the status `plaintext_found`. The record's `plaintext` names each place: the file, the line, and
the name the value is assigned to (`token` for a value recognised by its shape alone). Nothing the
round records, reports or hands off carries the value. The status's `problem` is
`plaintext_found`, with the places and an agent hand-off. The hand-off asks for each value to be
moved into a Coffer secret and the file pointed at it, without printing the value, and it leaves
Retry to the person. The attention list carries the `sync_plaintext_found` item with the same
hand-off, and `coffer sync status --prompt` prints it.

When only an earlier, unpushed commit holds a value, because the file was fixed since, the round
MUST NOT publish that commit. It folds the unpushed commits into one commit on the remote's head,
with the same files, checks it out in their place, and pushes that. It records how many commits it
folded as `folded`. No file on disk changes.

"Push anyway" (`POST /api/v1/sync/plaintext/push-anyway`, `coffer sync push-anyway`) MUST allow
exactly the file versions the last round found, record the audit event `sync_plaintext_pushed`
with the files and lines, and run a round. A file changed since is a new version and is read
again. When the last round is not `plaintext_found`, it MUST be refused with
`SYNC_NO_PLAINTEXT_FOUND` (409).

#### Scenario: a plaintext secret stops the round before anything is pushed
- **GIVEN** a joined machine whose knowledge document gains the line `DB_PASSWORD=<a value>`
- **WHEN** a round runs, and the status, the attention list, `coffer sync status` and `coffer sync status --prompt` are read
- **THEN** the round is `plaintext_found`, the remote's head has not moved and holds no copy of the value, and the other machine never receives the file
- **AND** each surface names the document, line 4 and `DB_PASSWORD`, the prompt asks for the value to be moved with `coffer secret set`, and none carries the value

#### Scenario: a value removed before the push is not published from the history
- **GIVEN** a round stopped as `plaintext_found`, after which the person replaces the value with a `coffer://secret/` reference and makes another edit
- **WHEN** the next round runs
- **THEN** it pushes one folded commit on the remote's head, recording how many commits it folded
- **AND** the remote holds no object containing the value, and the other machine receives both edits

#### Scenario: push anyway allows exactly what was found and is audited
- **GIVEN** a machine whose last round did not find a plaintext secret
- **WHEN** Push anyway is asked for, then a round stops as `plaintext_found` and Push anyway is asked for again
- **THEN** the first is refused with `SYNC_NO_PLAINTEXT_FOUND`, the second pushes the file and records `sync_plaintext_pushed` naming the file and line
- **AND** a new value written into the same file stops the next round again

#### Scenario: an encrypted secret file is not read
- **GIVEN** a remote that carries secret ciphertext, and a `secret/<ref>.enc` file whose bytes look like a token
- **WHEN** a round runs
- **THEN** it pushes the file

#### Scenario: the Sync page names each place and offers the hand-off and push anyway
- **GIVEN** the Sync page with a `plaintext_found` problem
- **WHEN** it is shown
- **THEN** its card lists each file, line and key a file still holds, with Retry and the agent hand-off
- **AND** Push anyway runs only after a confirmation that says it is recorded in the audit log

## MODIFIED Requirements

### Requirement: Cover the sync lifecycle on the command line
The CLI MUST cover the round and the vault's lifecycle:

- `coffer sync now`, `status [--json] [--prompt]`, `history [--limit]` and
  `rollback <round> [--yes]`;
- `join [--yes]`;
- `conflicts [--prompt]`, `resolve <path> --mine|--theirs|--edited`, `resolve --merged`,
  `edit <path>` and `continue`;
- `hold [--confirm|--restore]` and `choose [<path> --mine|--theirs]`;
- `push-anyway [--yes]`.

It MUST cover the administration too:

- `remote set <url> [--branch] [--interval <seconds>] [--with-secret|--without-secret] [--secret-ref] [--username] [--wait]`;
- `remote clear`, `remote pause`, `remote resume` and `remote check`;
- `machine list`, `machine rename <name>` and `machine rm <id>`;
- `key import <file>` and `key fingerprint`.

There is no `key export`: a key backup leaves a machine only through the desktop app. An option
`remote set` is not given keeps the stored remote's value. `remote pause` and `remote resume` switch
the remote's `enabled` switch off and on (see "Pause a configured remote without forgetting it") and
change nothing else. `--prompt` prints the hand-off prompt for the person's agent: on `status` the
current problem's, on `conflicts` the stopped round's merge. It exits `5` when there is none.
`push-anyway` lists the places the last round found and asks before pushing, unless given `--yes`.

`status` MUST report the configured remote and every one of its settings beside this machine, the
last round, what waits to push and anything waiting for the person, in plain and `--json` output.
The settings are the URL, the branch, the interval, whether secret ciphertext travels, the push
secret's ref, the username and whether the remote is on. With no remote configured, `status` says so
and names `remote set`.

#### Scenario: the command line covers every sync operation
- **GIVEN** the `coffer sync` command group
- **WHEN** its commands and options are listed
- **THEN** it offers every command the requirement names, and no `key export`

#### Scenario: pause and resume a remote from the command line
- **GIVEN** a configured, enabled sync remote
- **WHEN** the user runs `coffer sync remote pause`, and then `coffer sync remote resume`
- **THEN** after the first the remote is paused and `coffer sync status` exits zero, and after the second it is enabled again

#### Scenario: the status command reports the remote's settings
- **GIVEN** a joined machine with a change waiting to push
- **WHEN** the user runs `coffer sync status`, and then `coffer sync status --json`
- **THEN** it prints the remote's settings, this machine and what waits to push, and the JSON says the remote is configured

### Requirement: Cover the same operations over HTTP
The HTTP API MUST cover the same operations under `/api/v1/sync`:

- `GET /status`, `POST /run`, `GET /runs` and `GET /runs/{id}`;
- `GET /runs/{id}/rollback-plan` and `POST /runs/{id}/rollback`;
- `GET|PUT|DELETE /remote` and `POST /remote/check`;
- `GET /join/preview`, `POST /join` and `GET|POST /join-choices`;
- `GET /stop`, `POST /stop/files/answer`, `POST /stop/files/editor`, `GET /stop/files/versions`,
  `POST /stop/merged` and `POST /continue`;
- `POST /hold/confirm` and `POST /hold/restore`;
- `POST /plaintext/push-anyway`;
- `GET /machines`, `PATCH /machines/self` and `DELETE /machines/{id}`;
- `GET /key/fingerprint` and `POST /key/import`.

No sync route returns the master key.

#### Scenario: the HTTP API serves every sync operation
- **GIVEN** the daemon's sync routes
- **WHEN** they are listed
- **THEN** every method and path the requirement names is served, and none exports a key

### Requirement: Present a Sync page with Status, Machines and Remote tabs
The web UI MUST present a top-level **Sync** page. The header says in one status whether this machine
is in sync: In sync, N changes to push, N changes pulled, Syncing, Stopped (conflicts or deletions
held), Push failed, Not pushed: plaintext secret, Remote unreachable, Sign-in failed, Paused or Not
set up. Beside the status is the page's one round action (Sync now, or Try again after a failure),
and under it the remote's URL with a copy button, the branch and when rounds run. A "?" beside the
title explains how to add another machine. The page has **three** tabs:

- **Status** is the landing tab. It holds:
  - a banner saying what the status means now;
  - what the vault holds that syncs: knowledge documents, skills, MCP servers and tools
    definitions, and encrypted secrets, synced or not;
  - what waits to push;
  - a card for a round stopped on conflicts or held deletions, and for a join's differing files;
  - the problem a failed round met;
  - every round this machine has run, as a table of when, the round, what it pulled and pushed, the
    commits and Roll back. A round opens in a drawer with its snapshot, the commits it pulled, what
    it changed here and what it pushed.
- **Machines** lists the machine registry. A user renames this machine and retires one that is
  gone. The machine that runs knowledge curation carries a read-only "Runs curation" tag.
- **Remote** holds the remote's settings, each saved as it is changed:
  - the URL, the branch, the push secret, and the user name an HTTPS token is sent with;
  - when a round runs. "Only when I press Sync now" pauses the remote;
  - whether secret ciphertext travels, which asks first when switched on;
  - the vault's folder, with a warning when it sits in a synchronised folder;
  - Stop syncing, which asks first.

Resolving conflicts and reviewing held deletions each have their own view, `/sync/conflicts` and
`/sync/deletions`, reached from the Status card and returning to it. Until this machine has joined
a remote, the page shows setting one up and joining in place of the tabs. The master key is
imported and exported in Settings › Security, not on the Sync page.

#### Scenario: the Sync page opens on Status beside Machines and Remote
- **GIVEN** the web UI with a joined remote
- **WHEN** the user opens the Sync page
- **THEN** it has exactly three tabs, Status, Machines and Remote, and opens on Status
- **AND** a link to a tab that no longer exists lands on Status
