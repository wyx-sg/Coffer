## ADDED Requirements

### Requirement: Undo a retired machine
Retiring another machine MUST run at once and MUST be undoable: `POST
/api/v1/sync/machines/{id}/restore` registers the machine again with the descriptor it had the
moment before it was retired, read from the vault's history, as a commit of this machine's.
Restoring a machine that is registered already changes nothing, restoring this machine is refused,
and restoring a machine the vault never held is `SYNC_MACHINE_NOT_FOUND`. The Machines tab retires
without a confirmation and offers Undo in the toast that says so.

#### Scenario: a retired machine is registered again with its descriptor
- **GIVEN** a machine that retired another one
- **WHEN** it restores the retired machine
- **THEN** the retired machine's descriptor is in the vault again exactly as it was, and the registry lists it
- **AND** restoring it a second time changes nothing, and restoring an unknown machine is `SYNC_MACHINE_NOT_FOUND`

### Requirement: Undo stop syncing
Stopping sync MUST run at once, without a confirmation, and MUST be undoable. `DELETE
/api/v1/sync/remote` forgets the remote as before and keeps, on this machine only, what it
forgot: the remote's settings (the push secret as a name, never its value), whether this machine had
joined, a round waiting for a person and a join's differing files. `POST /api/v1/sync/remote/restore`
puts them back as they were and returns the remote. It is `SYNC_NOTHING_TO_RESTORE` when nothing was
stopped or another remote was set since, and `SYNC_REMOTE_EXISTS` while a remote is set. Setting a
remote drops what was kept.

#### Scenario: stopping sync can be undone
- **GIVEN** a joined machine with a remote, a push secret, a custom interval and a round stopped on a conflict
- **WHEN** sync is stopped and then restored
- **THEN** the remote has the same URL, branch, secret name, user name, interval and secret setting, the machine is still joined, and the stopped round is waiting again
- **AND** restoring a second time, or after setting another remote, is `SYNC_NOTHING_TO_RESTORE`

### Requirement: Move the vault out of a synchronised folder
A vault found inside a folder another tool synchronises (the "Cloud folder" problem) MUST be movable
from the Sync page. `POST /api/v1/sync/vault/move` takes `{to}` and answers `{from, to}`. The vault's
path is fixed (`~/.coffer/vault`), so a vault elsewhere is reached through that path and a move never
changes a path any part of the daemon holds: when `to` is `~/.coffer/vault` itself a real folder
replaces the link, otherwise the folder is placed at `to` and `~/.coffer/vault` becomes a link to it.
No restart is needed. The target MUST be absolute (`~` allowed), absent or empty, outside and not
around the current vault, in a writable parent, and not inside a folder the Cloud folder detector
names: `SYNC_VAULT_TARGET_INVALID` (422), `SYNC_VAULT_TARGET_IN_CLOUD` (422) and
`SYNC_VAULT_TARGET_NOT_EMPTY` (409). While it moves, rounds, the curation pass and agent writes are
held off by the sync lock; the folder is renamed, or copied and then emptied when the target is on
another filesystem; the git repository (HEAD, working-tree status, connectivity) is checked at the
new place against the old; any failure puts the vault back and is `SYNC_VAULT_MOVE_FAILED` (500).
The old folder is left empty for the person to delete. `GET /api/v1/sync/status` carries
`vault_real_path` (where the files really are, the dialog's "From") and `default_vault_path` (the
"To" it offers).

#### Scenario: the vault is moved out of a synchronised folder
- **GIVEN** a git vault in iCloud Drive that `~/.coffer/vault` links to, and the Cloud folder problem showing
- **WHEN** the vault is moved to `~/.coffer/vault`
- **THEN** the response is `{from, to}` with the iCloud folder and the new folder, the vault's files and history are at the new place unchanged, and the old folder exists empty
- **AND** the status no longer reports a synchroniser or a problem, and rounds and writes go on at the same path
- **AND** a target inside iCloud Drive, a cloud drive or a Syncthing folder is `SYNC_VAULT_TARGET_IN_CLOUD`, a relative or overlapping path is `SYNC_VAULT_TARGET_INVALID`, and a folder with files in it is `SYNC_VAULT_TARGET_NOT_EMPTY`, each leaving the vault where it was

### Requirement: Hand conflicting files to an agent
Files both machines edited MUST be offered to the person's agent to merge, beside the two
answers and the editor: a round stopped on conflicts (both sides changed the file, or the merge git
made is not a valid document) and a join's differing files (both sides hold the file with no common
base) are the same question and share one set of routes and one prompt shape. The person hands over
every such file at once or one file; `POST /api/v1/sync/stop/handoff` (a join's:
`POST /api/v1/sync/join-choices/handoff`) takes the optional `paths`, writes each file's marked-up copy
under `derived/sync-conflicts/`, records the hand-off with its time, and returns the prompt. The body
may also carry the `agent` and the Coffer `conversation_id` it was opened in; sending the request
again with them attaches them without a second hand-off. The prompt states the goal and the
constraints only:

- the vault's path, to read for context;
- each file, when each machine changed it and the marked-up copy to write the merge into, which holds
  both versions between conflict markers;
- keep what each side added, and ask the person where the two contradict;
- write only those copies, leaving the vault's own files and its git history alone, because Coffer
  writes the merged file into the vault when the person marks it resolved.

It MUST carry no shell command, no secret's value and no secret file's path or contents.

An agent's merge is never an answer. A file handed over reads `handed_off` while its copy is still
git's marked-up text or holds a conflict marker, and `merged_by_agent` once the copy differs from it
and holds no marker, with `merged_at` the time the copy was saved. `GET /api/v1/sync/stop/files/versions`
then carries the merged text and its unified diff from this machine's version (`merged`,
`merged_diff`). The file stays unresolved: **Mark resolved** is the `edited` answer, read from the
copy (`POST /api/v1/sync/stop/files/answer`, or a join's `POST /api/v1/sync/join-choices`, which commits
the merge as this machine's version for the next round to push), and it is refused while a conflict
marker is left, naming the line. **Back to two choices** (`POST /api/v1/sync/stop/files/discard`, a
join's `.../join-choices/discard`) forgets the copy, the hand-off and any answer for the file. Asking
again for a file already merged starts it over from the marked-up text. Nothing is written into the
vault until the round continues, or, for a join, until the file is answered.

An encrypted secret (`secret/*.enc`) MUST NOT be handed to an agent or hand-merged. It offers only
keep this machine's and take the other's: no editor copy is written, and a hand-off or an edited
answer for it is refused (`SYNC_SECRET_NOT_EDITABLE`). The prompt MAY say how many secret files wait
for the person. A same-name resource with another uid, one uid at two paths, and a file changed on
one side and deleted on the other are decisions, not merges, and are not handed over either.

#### Scenario: an agent's merge is shown to be checked and marked resolved
- **GIVEN** a round stopped because both machines changed the same lines of one document
- **WHEN** the files are handed to an agent, the agent writes its merge into the copy the prompt names, and the person marks it resolved and continues
- **THEN** the prompt names the vault, the file, both machines and the copy, and carries no shell command
- **AND** the file reads `handed_off` until the copy holds a merge, then `merged_by_agent` with the merge and its diff from this machine's version while the round still has an unanswered file
- **AND** marking it resolved is refused while a conflict marker is left, and once it is accepted the merged text is what the vault holds after the round

#### Scenario: going back to two choices discards an agent's merge
- **GIVEN** a conflicting file an agent has merged, even one already marked resolved
- **WHEN** the person goes back to two choices
- **THEN** the copy is gone, the file is unresolved with no agent state, and keeping this machine's or taking the other's answers it
- **AND** handing it over again, or asking again after a merge, starts from the marked-up text

#### Scenario: a join's differing files are handed to an agent too
- **GIVEN** a machine that joined a remote holding a file that differs from this machine's, with no common base
- **WHEN** the join's files are read, handed to an agent, merged in the copy and answered `edited`
- **THEN** the file has the shape a stopped round's conflicting file has, with the same agent states
- **AND** the merge is committed as this machine's version, so the next round pushes it and the other machine takes it

#### Scenario: an encrypted secret in conflict offers only the two choices
- **GIVEN** a round stopped on a `secret/*.enc` file among its conflicts
- **WHEN** the person asks for an editor copy of it, hands it to an agent, or answers it "edited"
- **THEN** each is refused, the file is marked a secret that an agent may not merge, and the prompt carries none of its contents
- **AND** keeping this machine's or taking the other's version answers it

## MODIFIED Requirements

### Requirement: Stop the round on any conflict
A merge that git cannot finish cleanly — both sides changed the same lines, one
side deleted what the other changed, two resources claim one name — or whose
merged tree fails validation MUST stop the round whole: nothing is checked out,
nothing is pushed, this vault's `HEAD` and every file on disk stay as they were,
and the remote is untouched. Coffer MUST NOT resolve a conflict by itself or by a
rule, and an agent's merge counts only once the person marks it resolved (see "Hand conflicting files to an
agent"); the only exception is secret ciphertext (see "Let the
fresher secret ciphertext win"). Asking again while nobody answered and
neither side moved changes nothing.

#### Scenario: a real conflict stops the round without touching the vault
- **GIVEN** two machines that edited the same lines of one document, beside an unrelated change here
- **WHEN** a round runs
- **THEN** it ends `stopped` with one conflict naming the other machine, this vault's `HEAD`, the file on disk and the remote's tip are unchanged
- **AND** a second round before anyone answers is `stopped` again

### Requirement: Cover the sync lifecycle on the command line
The CLI MUST cover the round and the vault's lifecycle:

- `coffer sync now`, `status [--json] [--prompt]`, `history [--limit]` and
  `rollback <round> [--yes]`;
- `join [--yes]`;
- `conflicts [--prompt]`, `resolve <path> --mine|--theirs|--edited`,
  `edit <path> [--join]` and `continue`;
- `hold [--confirm|--restore]` and `choose [<path> --mine|--theirs|--edited]`;
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
current problem's, on `conflicts` the stopped round's merge, which also records the hand-off. It exits `5` when there
is none.
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
- `GET|PUT|DELETE /remote`, `POST /remote/check` and `POST /remote/restore`;
- `GET /join/preview`, `POST /join`, `GET|POST /join-choices`, and `POST /join-choices/editor`,
  `/join-choices/handoff` and `/join-choices/discard`;
- `GET /stop`, `POST /stop/files/answer`, `POST /stop/files/editor`, `GET /stop/files/versions`,
  `POST /stop/handoff`, `POST /stop/files/discard` and `POST /continue`;
- `POST /hold/confirm` and `POST /hold/restore`;
- `POST /plaintext/push-anyway`;
- `GET /machines`, `PATCH /machines/self`, `DELETE /machines/{id}` and `POST /machines/{id}/restore`;
- `GET /key/fingerprint` and `POST /key/import`.

No sync route returns the master key.

#### Scenario: the HTTP API serves every sync operation
- **GIVEN** the daemon's sync routes
- **WHEN** they are listed
- **THEN** every method and path the requirement names is served, and none exports a key

### Requirement: Show a conflict as a banner
A round stopped on conflicts MUST be shown as a card on the Status tab, above the rounds table, not
as a row. The card lists each conflicting file with its area, when each machine changed it and
whether it has an answer, and carries **Resolve conflicts** beside a hand-off that gives every
conflict to an agent at once. That card can be ignored, as the same item on the Overview, and returns
when the set of conflicts changes. The Resolve conflicts view MUST offer, for each file:

- keep this machine's, and take the other's, each saying what it changes here;
- open in the editor and mark resolved, except for an encrypted secret;
- a hand-off that gives that one file to an agent (see "Hand conflicting files to an agent"), after
  which the file reads "Merged by an agent · check it" and shows the merge's diff from this
  machine's version with **Mark resolved**, **Open conversation** and **Back to two choices**.

The view says how many files are answered, lets the person leave the round for later, and offers
Continue round once every file has an answer. A hold is shown the same way, on its own card, leading
to the Review held deletions view with its two answers. So are a join preview and a join's
differing files, each on its own card; a join's differing files are listed and opened in the same
Resolve view as conflicts, titled for the join and ending in **Apply choices**.

#### Scenario: a conflict is shown as a banner above the runs
- **GIVEN** a vault whose last round stopped on a conflict
- **WHEN** the Status tab renders
- **THEN** a card above the rounds table names each conflicting file and leads to its answers

### Requirement: Say a vault needs a human where the user already is
A vault whose round needs a human — stopped on conflicts, held by the breaker,
waiting on an edit, waiting for a join or for a join's differing files, unable
to sign in, paused in a synchronised folder, or refused for its layout — MUST
say so where the user already is, not only on the page built for it.
`coffer sync status` MUST exit non-zero, the web UI MUST mark its **navigation
entry** for the sync page, the attention list MUST carry an item naming what to
do, and the desktop shell MUST raise it as a notification and mark its icon. A
vault that needs a human converges no further, so a question nobody sees is an
outage that looks like silence.

The web UI's mark MUST be cleared by **visiting the page**, not by the situation
changing, and MUST NOT return for the same situation. The rounds are
timer-driven, so a notice that re-raised itself on each would cover every page
hourly with something the user read the first time. A mark keyed on what is
wrong asks once, and asks again only when the answer would be different.

The attention list's sync items MUST be named by their situation, so ignoring one — on the Overview
or from the Sync page, which share the key — hides that situation and no other: the conflicts item
by the commits and files in conflict, a hold's by its commits and files, a join's by its files, a
plaintext secret's by what was found, and a remote's failure by the remote. A situation that
changes is a new item. The list MUST also carry an item while `git` is missing
(`sync_git_missing`) and while the remote is unreachable (`sync_unreachable`), each with its
hand-off, so every problem the Sync page shows can be ignored.

The status MUST also say how far this vault and the remote (as last fetched) have drifted: `ahead`, the commits this vault has that the remote lacks, and `behind`, the commits the remote has that this vault lacks. The Overview's Sync tile words them as "1 behind · 0 ahead".

#### Scenario: the status counts commits ahead of and behind the remote
- **GIVEN** a vault with two commits the remote lacks and a remote with one commit the vault lacks
- **WHEN** the status is read
- **THEN** it reports `ahead` 2 and `behind` 1, and both 0 once the vault and the remote agree

#### Scenario: a held vault says so where the user already is
- **GIVEN** a round held at the deletion guard, so nothing converges and nothing is backed up until someone answers it,
- **WHEN** the user is anywhere other than the sync page — at a terminal, on another page of the web UI, or with only the desktop shell in front of them,
- **THEN** `coffer sync status` exits non-zero, the web UI's navigation entry for sync is marked, and the shell has marked its icon and raised one notification — once for that condition, not once per poll,
- **AND** opening the sync page clears the web UI's mark, which does not return while the same thing is wrong, however many rounds re-raise it.

#### Scenario: a machine that has not joined says so everywhere
- **GIVEN** a machine with a remote configured that it has not joined, so its round ends `join_required` and converges nothing
- **WHEN** the user is anywhere other than the sync page
- **THEN** `coffer sync status` points at `coffer sync join`, the web UI's navigation entry for sync is marked, and the desktop shell marks its icon and raises one notification

#### Scenario: the attention list names what a round waits for
- **GIVEN** a round stopped on a conflict
- **WHEN** the attention list is read
- **THEN** it carries one sync item for the conflicts, pointing at the stopped round

#### Scenario: an ignored item returns when the situation changes
- **GIVEN** a round stopped on one conflicting file and its attention item
- **WHEN** the attention list is read again, and then the round is stopped on another set of files
- **THEN** the item keeps the same key while the situation is the same, and has a different key for the other set of files
- **AND** a machine without `git`, and a remote that cannot be reached, each have their own item

### Requirement: Present a Sync page with Status, Machines and Remote tabs
The web UI MUST present a top-level **Sync** page. The header says in one status whether this machine
is in sync: In sync, N changes to push, N changes pulled, Syncing, Stopped (conflicts or deletions
held), Push failed, Not pushed: plaintext secret, Remote unreachable, Sign-in failed, Paused or Not
set up. Beside the status is the page's one round action, **Sync now** (Syncing… and disabled while a
round runs), which never changes with the state; under the title is the remote's URL with a copy
button, the branch and when rounds run. The title carries the Experimental mark. The page has **three** tabs:

- **Status** is the landing tab. It holds:
  - a banner saying what the status means now, with one grey line under it of what the vault holds
    that syncs: knowledge documents, skills, MCP server and tool definitions, and whether secrets
    are synced;
  - what waits to push, five lines then "Show all";
  - a card for a round stopped on conflicts or held deletions, and for a join's differing files;
  - the problem a failed round met, as a card with its own action and an × that ignores it like
    Ignore on Overview. A card has no Retry; the vault inside a cloud-synced folder is moved with
    "Move the vault…";
  - every round this machine has run, as a table of when, the round, what it pulled and pushed. A
    round opens in a drawer with its snapshot, the commits it pulled, what it changed here and what
    it pushed, and Roll back to before the round is there and nowhere else.
- **Machines** lists the machine registry. A user renames this machine and retires one that is
  gone, at once, with Undo. The machine that runs knowledge curation carries a read-only "Runs curation" tag.
- **Remote** holds the remote's settings, each saved as it is changed:
  - the URL, the branch, the push secret, and the user name an HTTPS token is sent with;
  - when a round runs. "Only when I press Sync now" pauses the remote;
  - whether secret ciphertext travels, which asks first when switched on;
  - the vault's folder, with a warning when it sits in a synchronised folder;
  - Stop syncing, which runs at once and offers Undo.

Resolving conflicts and reviewing held deletions each have their own view, `/sync/conflicts` and
`/sync/deletions`, reached from the Status card and returning to it. Until this machine has joined
a remote, the page shows setting one up and joining in place of the tabs. The master key is
imported and exported in Settings › Security, not on the Sync page.

#### Scenario: the Sync page opens on Status beside Machines and Remote
- **GIVEN** the web UI with a joined remote
- **WHEN** the user opens the Sync page
- **THEN** it has exactly three tabs, Status, Machines and Remote, and opens on Status
- **AND** a link to a tab that no longer exists lands on Status


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
- **THEN** its card lists each file, line and key a file still holds, with "Move into secrets…", which opens the Secrets scan limited to those files, and no Retry
- **AND** Push anyway runs only after a confirmation that says it is recorded in the audit log

## REMOVED Requirements

### Requirement: Hand a conflict's merge to an agent
**Reason**: An agent's merge was recorded with an "I merged it" button that answered every handed-over file at once, unseen. The hand-off now covers a join's differing files too, can be given for one file, and shows the agent's merge for the person to check before it resolves anything.
**Migration**: See "Hand conflicting files to an agent": the hand-off is `POST /api/v1/sync/stop/handoff`, the merge reads `merged_by_agent` on the file, and marking it resolved is the `edited` answer. `POST /api/v1/sync/stop/merged` and `coffer sync resolve --merged` are gone.
