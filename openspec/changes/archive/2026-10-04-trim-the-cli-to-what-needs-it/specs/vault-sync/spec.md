## MODIFIED Requirements

### Requirement: Refuse a URL or branch git would read as an option
The URL and the branch become arguments to `git`, so neither MAY begin with `-`
(git would read it as an option, and `--receive-pack=<cmd>` is a command) and
the branch MUST pass the rules of `git check-ref-format --branch`. Both MUST be
refused at the API and again by the domain object. The git adapter
MUST fence every positional argument git lets it fence with `--` and MUST push
an explicit `refs/heads/` refspec.

#### Scenario: a remote URL or branch that git would read as an option is refused
- **GIVEN** a remote URL beginning with `-`, or a branch beginning with `-` or failing `git check-ref-format --branch`
- **WHEN** the remote is configured over REST or built as the domain object
- **THEN** each is refused and no remote is stored

### Requirement: Report a join before applying it
Joining MUST be explicit and previewed: before anything is applied the surfaces
MUST state which case it is, who pushed the remote's newest commit and when,
what would be pulled and pushed by area, how many files are the same, which
differ, and — for a returning machine — what the merge would delete or stop on;
a remote at the wrong layout is refused in the preview. `GET
/api/v1/sync/join/preview` applies nothing; `POST /api/v1/sync/join` joins as the
preview said; the Sync page shows the preview and joins on the
person's click.

#### Scenario: a join states its case and its counts before applying
- **GIVEN** a machine that has not joined its remote
- **WHEN** the preview is requested (`GET /api/v1/sync/join/preview`) and the person then confirms the join (`POST /api/v1/sync/join`)
- **THEN** the preview states which case the join is and applies nothing, and the confirmed join applies it

### Requirement: Detect joining on every round without a pointer
A round on a machine that has not joined its remote — never joined, or set to
another URL or branch since — MUST apply and push nothing and end
`join_required`, so no timer round or `POST
/api/v1/sync/run` ever joins on its own.

#### Scenario: an ordinary round on a machine without a pointer still detects the join
- **GIVEN** a machine with a remote it has not joined, and a machine whose remote was just set to another URL
- **WHEN** an ordinary round runs on each
- **THEN** each ends `join_required` and nothing is applied or pushed
- **AND** a remote that shares history with the vault (a mirror, a renamed repository) is no different: sharing history is not consent, and the machine joins only through the join

### Requirement: Ask the user to confirm a tripped breaker
A tripped breaker MUST hold the round before anything is checked out or pushed
and record which direction it is — **outgoing** (this machine's own commits
would remove the files from the remote) or **incoming** (the remote's would
remove them here) — and which files, grouped by folder with the share of each
folder they are. The person answers: **delete** them (the round continues and
applies or pushes the deletions) or **restore** them (the round continues and
the files are kept, pushed back if the remote had lost them). Both answers are
on REST (`POST /api/v1/sync/hold/confirm`, `POST /api/v1/sync/hold/restore`) and the Sync page.

#### Scenario: an oversized deletion is held for confirmation
- **GIVEN** a machine that removed 22 documents of one folder, and the machine that receives that deletion
- **WHEN** each runs a round
- **THEN** the first is held outgoing and the second incoming, each listing the files by folder, with nothing applied or pushed
- **AND** confirming pushes the deletion, while restoring keeps the files here and pushes them back

### Requirement: Say a vault needs a human where the user already is
A vault whose round needs a human — stopped on conflicts, held by the breaker,
waiting on an edit, waiting for a join or for a join's differing files, unable
to sign in, paused in a synchronised folder, or refused for its layout — MUST
say so where the user already is, not only on the page built for it.
`GET /api/v1/sync/status` MUST report the problem, the web UI MUST mark its **navigation
entry** for the sync page, the attention list MUST carry an item naming what to
do, and the desktop shell MUST raise it as a notification and mark its icon. A
vault that needs a human converges no further, so a question nobody sees is an
outage that looks like silence.

`GET /api/v1/sync/status` MUST also report the configured remote with every one of its settings
beside this machine, the last round, what waits to push and anything waiting for the person. The
settings are the URL, the branch, the interval, whether secret ciphertext travels, the push
secret's ref, the username and whether the remote is on.

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
- **WHEN** the user is anywhere other than the sync page — on another page of the web UI, or with only the desktop shell in front of them,
- **THEN** the sync status reports the problem, the web UI's navigation entry for sync is marked, and the shell has marked its icon and raised one notification — once for that condition, not once per poll,
- **AND** opening the sync page clears the web UI's mark, which does not return while the same thing is wrong, however many rounds re-raise it.

#### Scenario: a machine that has not joined says so everywhere
- **GIVEN** a machine with a remote configured that it has not joined, so its round ends `join_required` and converges nothing
- **WHEN** the user is anywhere other than the sync page
- **THEN** the sync status names the join, the web UI's navigation entry for sync is marked, and the desktop shell marks its icon and raises one notification

#### Scenario: the attention list names what a round waits for
- **GIVEN** a round stopped on a conflict
- **WHEN** the attention list is read
- **THEN** it carries one sync item for the conflicts, pointing at the stopped round

#### Scenario: an ignored item returns when the situation changes
- **GIVEN** a round stopped on one conflicting file and its attention item
- **WHEN** the attention list is read again, and then the round is stopped on another set of files
- **THEN** the item keeps the same key while the situation is the same, and has a different key for the other set of files
- **AND** a machine without `git`, and a remote that cannot be reached, each have their own item

### Requirement: Never write the master key into the repository
The master key MUST never be written into the vault: it stays in the OS
credential store or `~/.coffer/master.key`, outside the repository. It is
bootstrapped onto another machine out-of-band: a backup is written only by the
desktop app, behind a presence check ([secret](../secret/spec.md)
"Release plaintext only to a present human in the desktop app"), and installed
on the other machine from Settings › Security (see "Import a master key after showing whose key it is").

#### Scenario: the master key never enters the repository
- **GIVEN** a remote configured to carry secret ciphertext, and a key file beside the vault
- **WHEN** a round pushes
- **THEN** the remote holds the ciphertext files and no key material

### Requirement: Restore to a revision without discarding later work
Going back to an earlier version of a vault file or folder MUST NOT discard
anything the vault gained since: restoring writes that version back as a new
commit through the vault's one write path (`POST
/api/v1/vault/restore`, the Skills History tab — [vault-storage](../vault-storage/spec.md)
"Show, compare and restore any version of a vault file"), touching only the
paths restored, and the next round publishes it like any other change.
Undoing what one round did is its rollback (see "Snapshot before checking out
and roll a round back from it").

#### Scenario: restore brings back a document deleted last week
- **GIVEN** a file with two versions in the vault's history
- **WHEN** the person restores the first
- **THEN** the file holds the first version's bytes as a new commit, and no earlier commit is rewritten

### Requirement: Pause a configured remote without forgetting it
A configured remote MUST carry an `enabled` switch, and switching it off MUST
pause sync without forgetting anything: the worker runs no timer round, and no
surface raises attention for it — the sync status reports no problem, the web UI
does not mark its sync entry and the desktop shell marks nothing — even over a
round the vault was waiting on, because a user who met a question by switching
sync off has answered it too. A round the person asks for by name ("Sync now")
still runs. The remote and the history MUST be kept, so switching it back on
resumes where the vault left off. Saving the remote again from the Sync page's
form (`PUT /api/v1/sync/remote`) MUST keep a paused remote paused — the form starts from the
stored remote and changes what the person edited and nothing else: every setting the
person did not touch keeps its stored value — and a remote configured for the first
time is stored enabled, with the defaults for every setting it is not given.

#### Scenario: a paused remote runs no round and asks for nothing
- **GIVEN** a joined vault whose remote is then switched off
- **WHEN** the worker ticks
- **THEN** no round is recorded and no next round is scheduled
- **AND** the sync status reports no problem, the web UI does not mark its sync entry and the desktop shell marks nothing

#### Scenario: reconfiguring a paused remote keeps it paused
- **GIVEN** a configured remote that has been switched off
- **WHEN** the remote is saved again from the form with a different interval
- **THEN** the remote it sends carries the new interval and is still switched off
- **AND** a remote set for the first time is sent switched on with the defaults

#### Scenario: reconfiguring a remote changes only what it names
- **GIVEN** a configured remote with a non-default branch, interval, push credential and username, carrying secret ciphertext
- **WHEN** the remote is saved again changing only its interval
- **THEN** every other setting is sent exactly as it was
- **AND** saving it with secret sync switched off changes that setting and nothing else

### Requirement: Hold a push token pointed at a new URL until approved
Setting the remote MUST resolve its push token for the remote's URL through the
secret boundary ([secret](../secret/spec.md) "Hold a secret for a new
destination until a person approves it"). An existing token pointed at a URL it
was not approved for MUST NOT be sent: the remote is saved without the
reachability probe, so the approval has a destination to name; the answer is
`SECRET_BINDING_PENDING` naming the approval, and the remote is set (and probed) once the approval
is applied. A round
MUST send the token only to the URL it is approved for, and fails with the same
refusal until then.

#### Scenario: a push token pointed at a new URL waits for approval
- **GIVEN** a push token already approved for one remote URL
- **WHEN** the remote is set to another URL citing the same token
- **THEN** the token is not sent and the answer names a pending approval for the new URL
- **AND** after the approval is applied, setting the remote again succeeds

### Requirement: Import a master key after showing whose key it is
Importing a master key MUST show, before anything is replaced, whose key the
file holds beside this machine's: `POST /api/v1/sync/key/import/preview` takes
the file's text and answers the key's fingerprint, this machine's fingerprint
(or none), whether they are the same key, and whether the file is a
passphrase-protected backup, and MUST change nothing. A protected backup's
fingerprint is read from the file without its passphrase and MUST be checked
against the key when the file is opened; a file whose fingerprint is not its
key's MUST be refused with `MASTER_KEY_FILE_INVALID`. `POST
/api/v1/sync/key/import` takes the file's text and, for a protected backup,
its passphrase; a missing or wrong passphrase MUST be refused with
`MASTER_KEY_PASSPHRASE_WRONG` and replace nothing. A bare Fernet key needs no
passphrase. On success it MUST answer the fingerprint of the key now in use,
whether a different key was replaced (the replaced key is kept as a backup,
never overwritten), how many stored secrets the key decrypts, and the refs it
still cannot decrypt; it is audited as `master_key_imported` with the
fingerprints and never the key or the passphrase. The running daemon MUST use
the imported key from then on, so a secret stored after the import is sealed
under it. Key material coming in needs no presence check: a caller that
supplies a key already has it.

Settings › Security MUST offer the import as one dialog: choose the key file,
see "Current key" beside "Key in the file" marked same or different, type the
passphrase when the file needs one, and confirm with Replace key; afterwards it
says how many secrets are readable now and names those still locked, with a
way to the Secrets page.

#### Scenario: an import shows whose key the file holds before replacing
- **GIVEN** a machine with its own master key, and a passphrase-protected backup of another machine's key
- **WHEN** the backup, and then a copy of this machine's own key, are previewed
- **THEN** the first answers the other key's fingerprint beside this machine's, not the same, and protected
- **AND** the second answers the same key and not protected, and this machine's key is unchanged after both

#### Scenario: a protected key file opens only with its passphrase
- **GIVEN** a passphrase-protected backup of another machine's key
- **WHEN** it is imported with a wrong passphrase, with none, and then with the right one
- **THEN** the first two are refused with `MASTER_KEY_PASSPHRASE_WRONG`, echo no passphrase and leave this machine's key in place
- **AND** the third installs the other key and answers its fingerprint with `replaced` true

#### Scenario: the security tab replaces a key and names what stays locked
- **GIVEN** Settings › Security, and a backup holding a key different from this machine's
- **WHEN** the person chooses the file, types the passphrase and replaces the key
- **THEN** the dialog showed both fingerprints and "different" before anything was sent to import
- **AND** afterwards it names the key now in use, how many secrets are readable, and the names of those still locked, with Open Secrets

### Requirement: Record every round
Every round — timer, `POST /api/v1/sync/run` (Sync now), a join, a
continue, an answered hold, a rollback — SHALL be recorded in `runs.db` with its
status, its trigger, when it started and finished, the commit range it moved the
vault across, the snapshot it took, the commits it pulled (with the machine that
wrote each), the files it applied here and pushed, the machines it met and, when
it stopped or failed, why in words a person can act on. A round that ends in a
problem — the remote unreachable, sign-in failed, a token waiting for approval —
MUST be recorded as a round of that status, never raised as an error the caller
has to catch. The history SHALL be readable newest first, paged, on REST
(`GET /api/v1/sync/runs`, `GET /api/v1/sync/runs/{id}`) and on the Sync page's Status tab.

#### Scenario: every round is recorded with what it moved
- **GIVEN** a joined machine with one new knowledge document waiting to push
- **WHEN** a round runs
- **THEN** the history's newest round is `pushed`, names the file it pushed and the commit range it moved across
- **AND** `GET /api/v1/sync/runs/{id}` returns that round, and an unknown id is `SYNC_ROUND_NOT_FOUND`

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
`GET /api/v1/sync/stop/files/versions`, `POST /api/v1/sync/continue`) and on the Sync page.

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

### Requirement: Check a remote before it is saved
A person SHALL be able to ask what a remote holds before saving it — empty, a
Coffer vault (with its layout), some other repository, unreachable or refused
sign-in — through `POST /api/v1/sync/remote/check`
and the set-up form's "Check repository". The check MUST send the user name the token
goes with, as saving does: the form's User name field, else the stored remote's,
else the default. Checking MUST keep
nothing: no remote is stored and the vault is not touched.

#### Scenario: a remote is checked before it is saved
- **GIVEN** an empty remote, the same remote once a vault has been pushed to it, and a URL that does not exist
- **WHEN** each is checked
- **THEN** they read as empty, as a vault at the current layout, and as unreachable or refused with git's message
- **AND** nothing about the stored remote changed

#### Scenario: the command line checks a remote with the user name it is given
- **GIVEN** a stored remote
- **WHEN** `POST /api/v1/sync/remote/check` is called with the user name `oauth2`, and then with none
- **THEN** the first check sends the user name `oauth2` with the token, and the second sends the stored remote's

### Requirement: Snapshot before checking out and roll a round back from it
Bidirectional convergence writes the vault without a human in the loop, so two
guards are normative. Before a round checks anything out it MUST tag this
vault's `HEAD` as the pre-apply snapshot, `refs/tags/coffer/pre-apply/<time>`;
the ten newest are kept. Rolling a round back MUST put back, as one new commit
naming the snapshot it restored from, what that round changed here — and only
that: a file edited after the round keeps the edit. The next round publishes the
rollback like any other local change. A round that applied nothing, or that was
itself a rollback, MUST be refused with nothing to roll back. A rollback shows
what it will reverse and what it keeps before it runs (`GET
/api/v1/sync/runs/{id}/rollback-plan`), and runs through `POST /api/v1/sync/runs/{id}/rollback`
and the Status tab's rounds.

#### Scenario: a round can be rolled back
- **GIVEN** a round that applied two files here, one of which was edited afterwards
- **WHEN** the person rolls the round back
- **THEN** the untouched file returns to its state before the round, the edited one keeps the edit, the newest commit names the snapshot it restored from, and the other machine takes the rollback on its next round

#### Scenario: a round that applied nothing has nothing to roll back
- **GIVEN** a round that only pushed, and a round that was a rollback
- **WHEN** a rollback of either is asked for
- **THEN** it is refused with nothing to roll back

#### Scenario: a rollback shows its plan first
- **GIVEN** a round that pulled a change
- **WHEN** the rollback plan is requested (`GET /api/v1/sync/runs/{id}/rollback-plan`) and the person does not confirm
- **THEN** it has shown what it would reverse and changed nothing, and confirming rolls the round back

### Requirement: Hand a remote's failure to an agent
A round the remote refused, whether a rejected push (`push_failed`), a refused sign-in
(`auth_failed`) or a remote that cannot be reached (`unreachable`), MUST carry a hand-off. The fix is
on the remote's side or on this machine's network, not in Coffer. The hand-off is served as
`problem.handoff` on `GET /api/v1/sync/status` and on the attention list's item. A rejected push is
the `sync_push_failed` item.

The prompt MUST carry the remote URL without any user name or password in it, the branch, the name
of the secret Coffer signs in with, git's message with URL credentials and token-shaped strings
scrubbed, and what to check for that kind of failure. It MUST NOT carry or ask for a token or a
secret's value. It ends by leaving the retry to the person, and **Retry** stays Coffer's own button.

A machine with no `git` on the daemon's PATH MUST report the problem `git_missing`, carrying the
shared install hand-off, which names the machine and no installer. The `GIT_MISSING` error carries
the same hand-off in `details.handoff`.

#### Scenario: a refused push carries a hand-off without a secret
- **GIVEN** a remote reached with an HTTPS URL that has a user and token in it, whose push a branch rule declines
- **WHEN** a round runs and the status and the attention list are read
- **THEN** each carries the same prompt, naming the URL without its credentials, the branch, the secret's name and git's message
- **AND** the prompt contains no part of the token

#### Scenario: a machine without git is handed the install chore
- **GIVEN** a configured remote on a machine where no `git` is found
- **WHEN** the status is read
- **THEN** its problem is `git_missing`, carrying a hand-off that asks for git to be installed and names no install command

### Requirement: Refuse to push a plaintext secret
Before a round pushes — a round that merged, a push with nothing to pull, or a join — it MUST read
every file version the push would publish: each blob reachable from the commit being pushed and
not from the remote's head, from every commit in between. It reads them with the detection
the Secrets scan uses (an assignment whose name says secret, and the well-known token shapes).
An encrypted `secret/<ref>.enc` file is ciphertext and MUST NOT be read; a binary file or one over
1 MB is not read either.

When a file still holds a value at the commit being pushed, the round MUST push nothing and record
the status `plaintext_found`. The record's `plaintext` names each place: the file, the line, and
the name the value is assigned to (`token` for a value recognised by its shape alone). Nothing the
round records, reports or hands off carries the value. The status's `problem` is
`plaintext_found`, with the places and an agent hand-off. The hand-off asks for each value to be
moved into a Coffer secret and the file pointed at it, without printing the value, and it leaves
Retry to the person. The attention list carries the `sync_plaintext_found` item with the same
hand-off.

When only an earlier, unpushed commit holds a value, because the file was fixed since, the round
MUST NOT publish that commit. It folds the unpushed commits into one commit on the remote's head,
with the same files, checks it out in their place, and pushes that. It records how many commits it
folded as `folded`. No file on disk changes.

"Push anyway" (`POST /api/v1/sync/plaintext/push-anyway`) MUST allow
exactly the file versions the last round found, record the audit event `sync_plaintext_pushed`
with the files and lines, and run a round. A file changed since is a new version and is read
again. When the last round is not `plaintext_found`, it MUST be refused with
`SYNC_NO_PLAINTEXT_FOUND` (409).

#### Scenario: a plaintext secret stops the round before anything is pushed
- **GIVEN** a joined machine whose knowledge document gains the line `DB_PASSWORD=<a value>`
- **WHEN** a round runs, and the status and the attention list are read
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

### Requirement: Cover the sync lifecycle on the command line
**Reason**: The requirement only defines the `coffer sync` command group, which is removed: every operation it listed is done on the Sync page and over REST, and the program-and-offline command list keeps no sync command.
**Migration**: Use the Sync page, or the REST routes the other requirements of this capability name (`/api/v1/sync/...`).
