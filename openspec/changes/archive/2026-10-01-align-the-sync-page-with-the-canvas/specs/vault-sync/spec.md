## ADDED Requirements

### Requirement: Hand a conflict's merge to an agent
A round stopped on files both machines edited (both sides changed it, or the merge git made is not
a valid document) MUST offer, beside the two answers and the editor, a hand-off that asks the
person's agent to merge them. The prompt MUST name:

- the vault's path;
- each file, with the commit that last changed it on each side, when each side changed it, and the
  marked-up copy under `derived/sync-conflicts/` to edit, which Coffer writes before it builds the
  prompt;
- how to see what each side changed (`git -C <vault> diff <base> <commit> -- <path>`);
- the rule that the agent edits only those copies and runs no git command that changes the vault,
  because Coffer commits the result;
- how the person finishes: **I merged it**, then **Continue round**.

The prompt is served as `handoff` on `GET /api/v1/sync/stop` and on the attention list's conflicts
item. `coffer sync conflicts --prompt` prints it.

**I merged it** (`POST /api/v1/sync/stop/merged`, `coffer sync resolve --merged`) MUST record, as the
edited answer, the saved copy of every unanswered file the prompt handed over. It MUST check every
copy first and refuse the whole request, naming the file and line, while any copy still holds a
conflict marker. Nothing is written into the vault until the round continues.

An encrypted secret (`secret/*.enc`) MUST NOT be handed to an agent or hand-merged. It offers only
keep this machine's and take the other's: no editor copy is written, and an edited answer is refused
(`SYNC_SECRET_NOT_EDITABLE`). The prompt MAY say how many secret files wait for the person, and MUST
NOT carry a secret file's path, contents or any secret value. A same-name resource with another uid,
one uid at two paths, and a file changed on one side and deleted on the other are decisions, not
merges, and are not handed over either.

#### Scenario: a conflict's merge is handed to an agent and recorded with I merged it
- **GIVEN** a round stopped because both machines changed the same lines of one document
- **WHEN** the stopped round is read, the agent edits the marked-up copy the prompt names, and the person presses I merged it and continues
- **THEN** the prompt names the vault, the file, both sides' commits, a `git -C <vault> diff` command and `coffer sync resolve --merged`
- **AND** I merged it is refused while a conflict marker is left in the copy, and once it is gone the merged text is what the vault holds after the round

#### Scenario: an encrypted secret in conflict offers only the two choices
- **GIVEN** a round stopped on a `secret/*.enc` file among its conflicts
- **WHEN** the person asks for an editor copy of it, answers it "edited", or presses I merged it with nothing else to merge
- **THEN** each is refused, the file is marked a secret that is not handed to the agent, and the prompt carries none of its contents
- **AND** keeping this machine's or taking the other's version answers it

### Requirement: Hand a remote's failure to an agent
A round the remote refused, whether a rejected push (`push_failed`), a refused sign-in
(`auth_failed`) or a remote that cannot be reached (`unreachable`), MUST carry a hand-off. The fix is
on the remote's side or on this machine's network, not in Coffer. The hand-off is served as
`problem.handoff` on `GET /api/v1/sync/status` and on the attention list's item. A rejected push is
the `sync_push_failed` item. `coffer sync status --prompt` prints the hand-off.

The prompt MUST carry the remote URL without any user name or password in it, the branch, the name
of the secret Coffer signs in with, git's message with URL credentials and token-shaped strings
scrubbed, and what to check for that kind of failure. It MUST NOT carry or ask for a token or a
secret's value. It ends by leaving the retry to the person, and **Retry** stays Coffer's own button.

A machine with no `git` on the daemon's PATH MUST report the problem `git_missing`, carrying the
shared install hand-off, which names the machine and no installer. The `GIT_MISSING` error carries
the same hand-off in `details.handoff`.

#### Scenario: a refused push carries a hand-off without a secret
- **GIVEN** a remote reached with an HTTPS URL that has a user and token in it, whose push a branch rule declines
- **WHEN** a round runs and the status, the attention list and `coffer sync status --prompt` are read
- **THEN** each carries the same prompt, naming the URL without its credentials, the branch, the secret's name and git's message
- **AND** the prompt contains no part of the token

#### Scenario: a machine without git is handed the install chore
- **GIVEN** a configured remote on a machine where no `git` is found
- **WHEN** the status is read
- **THEN** its problem is `git_missing`, carrying a hand-off that asks for git to be installed and names no install command

### Requirement: Present a Sync page with Status, Machines and Remote tabs
The web UI MUST present a top-level **Sync** page. The header says in one status whether this machine
is in sync: In sync, N changes to push, N changes pulled, Syncing, Stopped (conflicts or deletions
held), Push failed, Remote unreachable, Sign-in failed, Paused or Not set up. Beside the status is
the page's one round action (Sync now, or Try again after a failure), and under it the remote's URL
with a copy button, the branch and when rounds run. A "?" beside the title explains how to add
another machine. The page has **three** tabs:

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

## MODIFIED Requirements

### Requirement: Show a conflict as a banner
A round stopped on conflicts MUST be shown as a card on the Status tab, above the rounds table, not
as a row. The card lists each conflicting file with its area, when each machine changed it and
whether it has an answer, and leads to the Resolve conflicts view. That view MUST offer, for each
file:

- keep this machine's, and take the other's, each saying what it changes here;
- open in the editor and mark resolved, except for an encrypted secret;
- merging with an agent (see "Hand a conflict's merge to an agent").

The view says how many files are answered, lets the person leave the round for later, and offers
Continue round once every file has an answer. A hold is shown the same way, on its own card, leading
to the Review held deletions view with its two answers. So are a join preview and a join's
differing files, each on its own card with its own answers.

#### Scenario: a conflict is shown as a banner above the runs
- **GIVEN** a vault whose last round stopped on a conflict
- **WHEN** the Status tab renders
- **THEN** a card above the rounds table names each conflicting file and leads to its answers

### Requirement: Cover the sync lifecycle on the command line
The CLI MUST cover the round and the vault's lifecycle:

- `coffer sync now`, `status [--json] [--prompt]`, `history [--limit]` and
  `rollback <round> [--yes]`;
- `join [--yes]`;
- `conflicts [--prompt]`, `resolve <path> --mine|--theirs|--edited`, `resolve --merged`,
  `edit <path>` and `continue`;
- `hold [--confirm|--restore]` and `choose [<path> --mine|--theirs]`.

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
- `GET /machines`, `PATCH /machines/self` and `DELETE /machines/{id}`;
- `GET /key/fingerprint` and `POST /key/import`.

No sync route returns the master key.

#### Scenario: the HTTP API serves every sync operation
- **GIVEN** the daemon's sync routes
- **WHEN** they are listed
- **THEN** every method and path the requirement names is served, and none exports a key

## REMOVED Requirements

### Requirement: Present a Sync page with Runs, Setup and Machines tabs
**Reason**: The final design splits the page into Status, Machines and Remote. What a person opens
Sync to find out, and every round, are on Status. The remote's settings are on Remote. The master key
moved to Settings › Security.
**Migration**: See "Present a Sync page with Status, Machines and Remote tabs". The acceptance marker
for "the Sync page opens on Runs beside Setup and Machines" moves to "the Sync page opens on Status
beside Machines and Remote".
