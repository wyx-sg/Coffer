## MODIFIED Requirements

### Requirement: Allow at most one user-owned sync remote
A vault MUST have **at most one** sync remote: a git repository the user owns,
configured with a URL, a branch, a push credential reference, an interval, whether secret ciphertext rides along
(`include_secret`), and whether it is on. The remote is machine-local
configuration, `local/sync/remote.json`. Sync MUST be off until the user
configures it. The interval MUST be at least 60 seconds: a shorter one is
refused before anything is stored. The username git sends with an
HTTPS token is not configured: it follows the host of the remote's URL —
`x-token-auth` for `bitbucket.org`, `oauth2` for a host whose name contains
`gitlab`, and `coffer` for any other host (GitHub and Azure DevOps ignore it
for a token). Bitbucket access tokens work; an App password, which needs the
account's own name, is not supported. The username and the token reach git only
through the credential helper's environment.
#### Scenario: sync stays off until a remote is configured
- **GIVEN** a vault with no sync remote configured
- **WHEN** the worker ticks and a round is requested over REST
- **THEN** the worker runs no round, and the request is refused as `SYNC_NO_REMOTE`

#### Scenario: an interval under a minute is refused
- **GIVEN** a remote being set with an interval of 59 seconds
- **WHEN** the request is validated
- **THEN** it is refused naming the 60-second floor, and 60 seconds is accepted

#### Scenario: a token is sent with the username the remote names
- **GIVEN** remotes on `bitbucket.org`, on a host named `gitlab.example.com`, and on `github.com`
- **WHEN** git is given the push token
- **THEN** they send `x-token-auth`, `oauth2` and `coffer` respectively, each only through the credential helper's environment

### Requirement: Say a vault needs a human where the user already is
A vault whose round needs a human — stopped on conflicts, held by the breaker,
waiting on an edit, waiting for a join or for a join's differing files, unable
to sign in, paused in a synchronised folder, or refused for its layout — MUST
say so where the user already is, not only on the page built for it.
`GET /api/v1/sync/status` MUST report the problem, the attention list MUST carry
an item naming what to do (which Overview lists under Needs you), and the desktop
shell MUST raise it as a notification and mark its icon. A
vault that needs a human converges no further, so a question nobody sees is an
outage that looks like silence.

`GET /api/v1/sync/status` MUST also report the configured remote with every one of its settings
beside this machine, the last round, what waits to push and anything waiting for the person. The
settings are the URL, the branch, the interval, whether secret ciphertext travels, the push
secret's ref and whether the remote is on.

The desktop shell's notification MUST be raised once for a condition, not once per
poll, and MUST NOT return for the same situation. The rounds are timer-driven, so
a notice that re-raised itself on each would interrupt the user hourly with
something they read the first time. A mark keyed on what is wrong asks once, and
asks again only when the answer would be different.

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
- **THEN** the sync status reports the problem, the attention list carries an item for it, and the shell has marked its icon and raised one notification — once for that condition, not once per poll,
- **AND** the notification does not return while the same thing is wrong, however many rounds re-raise it.

#### Scenario: a machine that has not joined says so everywhere
- **GIVEN** a machine with a remote configured that it has not joined, so its round ends `join_required` and converges nothing
- **WHEN** the user is anywhere other than the sync page
- **THEN** the sync status names the join, the attention list carries an item for it, and the desktop shell marks its icon and raises one notification

#### Scenario: the attention list names what a round waits for
- **GIVEN** a round stopped on a conflict
- **WHEN** the attention list is read
- **THEN** it carries one sync item for the conflicts, pointing at the stopped round

#### Scenario: an ignored item returns when the situation changes
- **GIVEN** a round stopped on one conflicting file and its attention item
- **WHEN** the attention list is read again, and then the round is stopped on another set of files
- **THEN** the item keeps the same key while the situation is the same, and has a different key for the other set of files
- **AND** a machine without `git`, and a remote that cannot be reached, each have their own item

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
- **GIVEN** a configured remote with a non-default branch, interval, push credential, carrying secret ciphertext
- **WHEN** the remote is saved again changing only its interval
- **THEN** every other setting is sent exactly as it was
- **AND** saving it with secret sync switched off changes that setting and nothing else

### Requirement: Check a remote before it is saved
A person SHALL be able to ask what a remote holds before saving it — empty, a
Coffer vault (with its layout), some other repository, unreachable or refused
sign-in — through `POST /api/v1/sync/remote/check`
and the set-up form's "Check repository". The check MUST send the token with the username its URL's host implies, as saving does. Checking MUST keep
nothing: no remote is stored and the vault is not touched.

#### Scenario: a remote is checked before it is saved
- **GIVEN** an empty remote, the same remote once a vault has been pushed to it, and a URL that does not exist
- **WHEN** each is checked
- **THEN** they read as empty, as a vault at the current layout, and as unreachable or refused with git's message
- **AND** nothing about the stored remote changed

#### Scenario: a remote check sends the user name it is given
- **GIVEN** a URL on `gitlab.example.com` and another on `bitbucket.org`
- **WHEN** each is checked with a token through `POST /api/v1/sync/remote/check`
- **THEN** the first check sends the username `oauth2` and the second `x-token-auth`, as saving would

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
  - the URL, the branch and the push secret;
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
- **THEN** the remote has the same URL, branch, secret name, interval and secret setting, the machine is still joined, and the stopped round is waiting again
- **AND** restoring a second time, or after setting another remote, is `SYNC_NOTHING_TO_RESTORE`
