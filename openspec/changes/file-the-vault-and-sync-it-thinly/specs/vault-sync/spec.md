## ADDED Requirements

### Requirement: Record every round
Every round — timer, `coffer sync now`, `POST /api/v1/sync/run`, a join, a
continue, an answered hold, a rollback — SHALL be recorded in `runs.db` with its
status, its trigger, when it started and finished, the commit range it moved the
vault across, the snapshot it took, the commits it pulled (with the machine that
wrote each), the files it applied here and pushed, the machines it met and, when
it stopped or failed, why in words a person can act on. A round that ends in a
problem — the remote unreachable, sign-in failed, a token waiting for approval —
MUST be recorded as a round of that status, never raised as an error the caller
has to catch. The history SHALL be readable newest first, paged, on REST
(`GET /api/v1/sync/runs`, `GET /api/v1/sync/runs/{id}`) and on the command line
(`coffer sync history`).

#### Scenario: every round is recorded with what it moved
- **GIVEN** a joined machine with one new knowledge document waiting to push
- **WHEN** a round runs
- **THEN** the history's newest round is `pushed`, names the file it pushed and the commit range it moved across
- **AND** `GET /api/v1/sync/runs/{id}` returns that round, and an unknown id is `SYNC_ROUND_NOT_FOUND`

### Requirement: Stop the round on any conflict
A merge that git cannot finish cleanly — both sides changed the same lines, one
side deleted what the other changed, two resources claim one name — or whose
merged tree fails validation MUST stop the round whole: nothing is checked out,
nothing is pushed, this vault's `HEAD` and every file on disk stay as they were,
and the remote is untouched. Coffer MUST NOT resolve a conflict by itself, by a
rule or by an agent; the only exception is secret ciphertext (see "Let the
fresher credential ciphertext win"). Asking again while nobody answered and
neither side moved changes nothing.

#### Scenario: a real conflict stops the round without touching the vault
- **GIVEN** two machines that edited the same lines of one document, beside an unrelated change here
- **WHEN** a round runs
- **THEN** it ends `stopped` with one conflict naming the other machine, this vault's `HEAD`, the file on disk and the remote's tip are unchanged
- **AND** a second round before anyone answers is `stopped` again

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
`GET /api/v1/sync/stop/files/versions`, `POST /api/v1/sync/continue`), on the
command line (`coffer sync conflicts`, `resolve <path> --mine|--theirs|--edited`,
`edit <path>`, `continue`) and on the Sync page.

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

### Requirement: Treat the same name with a different uid as a conflict
Two resource files of one kind that carry the same `name` and different `uid`s
are two resources claiming one name. A merge or a join that would bring them
together SHALL stop on them as a conflict the person answers — keep one, or
rename one — and MUST NOT pick one by itself or check both out.

#### Scenario: the same name with a different uid stops the round
- **GIVEN** one machine with an MCP server named `linear` and another with a different MCP server also named `linear`, each with its own uid
- **WHEN** the second machine's round (or its join) merges with the first's
- **THEN** the round stops and the conflict's reason is the same name with a different uid

### Requirement: Never overwrite a person's unsettled edit
A round SHALL check out its merged tree only where the working tree still holds
what `HEAD` holds. A path the round would change that a person has edited and
that is not yet committed — an edit still settling, or one validation refused —
MUST stop the round as waiting on that edit, naming the path; the file on disk
and `HEAD` MUST stay as they were.

#### Scenario: an invalid hand edit on a path the round changes is never overwritten
- **GIVEN** a resource file the other machine changed, and on this machine an uncommitted hand edit to the same file that does not parse
- **WHEN** a round runs here
- **THEN** the round ends `waiting_on_edit` naming the file, the hand edit is still on disk, and `HEAD` still holds the last valid version

### Requirement: Pause a vault that sits inside a file synchroniser
A vault inside a folder another tool synchronises — Dropbox, Syncthing, iCloud
Drive, or a cloud drive under `~/Library/CloudStorage` — would have two
replicators writing one git repository. A round SHALL detect this and end
`paused_cloud_folder`, touching nothing, and the status SHALL name the tool so
the person can move the vault or exclude it.

#### Scenario: a vault in a synchronised folder pauses
- **GIVEN** a vault whose parent folder carries Syncthing's or Dropbox's marker, or that sits under iCloud Drive or `~/Library/CloudStorage`
- **WHEN** a round runs
- **THEN** it ends `paused_cloud_folder` and the status names the synchroniser as a `cloud_folder` problem

### Requirement: Report a remote's failure by what a person can do
A round that cannot fetch or push SHALL classify git's failure by what a person
can do about it: `unreachable` (the network or the host), `auth_failed`
(sign-in failed, or the push token is missing or waiting for approval — the
status names the token's ref) and `push_failed` (the remote rejected the push,
for example a protected branch). git's message SHALL be kept, with any
credential redacted. A failed fetch MUST leave the vault exactly as it was.

#### Scenario: remote failures are reported by what a person can do
- **GIVEN** git failing with an unreachable host, a refused sign-in, and a rejected push
- **WHEN** each failure is classified
- **THEN** they are `unreachable`, `auth_failed` and `push_failed` respectively
- **AND** a round against a remote that does not exist changes nothing in the vault

#### Scenario: a token waiting for approval is a sign-in problem
- **GIVEN** a remote whose push token waits for the person's approval
- **WHEN** a round runs
- **THEN** it is recorded `auth_failed` naming the token's ref, and the attention list carries a sign-in item

### Requirement: Refuse a remote at another layout
The remote's `manifest.json` carries the vault layout's `schema_version`. A
round or a join SHALL refuse a remote at a newer layout (`remote_too_new`) and
at an older one (`remote_too_old`), leaving this vault untouched. A remote in
the layout builds before the vault files wrote is never converted: it is
rebuilt from the first machine that ran the one-time upgrade — pointed at an
empty branch or remote, which that machine then fills — and every other machine
upgrades and joins it as a new machine.

#### Scenario: a remote at another layout is refused
- **GIVEN** a remote whose manifest names a newer layout, and another whose manifest names an older one
- **WHEN** a round runs against each
- **THEN** the first ends `remote_too_new` and the second `remote_too_old` with a message saying to rebuild it from a migrated machine
- **AND** in both cases this vault's `HEAD` is unchanged

#### Scenario: an old remote is rebuilt from the first upgraded machine
- **GIVEN** two machines that synced through a remote before the upgrade, and the first of them upgraded
- **WHEN** its round meets the old remote, and it is then pointed at an empty remote and joins, and the second machine upgrades and joins that remote
- **THEN** the old remote is refused, the first machine fills the empty one, and the second machine joins as new with nothing lost on either

### Requirement: Check a remote before it is saved
A person SHALL be able to ask what a remote holds before saving it — empty, a
Coffer vault (with its layout), some other repository, unreachable or refused
sign-in — through `POST /api/v1/sync/remote/check`, `coffer sync remote check`
and the Setup tab's "Check repository". Checking MUST keep nothing: no remote is
stored and the vault is not touched.

#### Scenario: a remote is checked before it is saved
- **GIVEN** an empty remote, the same remote once a vault has been pushed to it, and a URL that does not exist
- **WHEN** each is checked
- **THEN** they read as empty, as a vault at the current layout, and as unreachable or refused with git's message
- **AND** nothing about the stored remote changed

### Requirement: Run the reconciler once after a round that applied changes
What another machine changed is this machine's warrant to bring its own side
effects in step — an agent's native configuration, Coffer's MCP entries, skill
deliveries. After a round that applied files here, one reconcile pass SHALL run
with the import's warrant (see [resource-framework](../resource-framework/spec.md)
"Converge what Coffer writes outside its database with one reconciler"); a round
that applied nothing MUST NOT run one. A failed pass is logged and the round
stands.

#### Scenario: a round that applied changes runs one reconcile pass
- **GIVEN** a joined machine and another machine that pushed a knowledge document
- **WHEN** this machine's round pulls it, and a further round has nothing to do
- **THEN** exactly one reconcile pass ran, after the first round

### Requirement: Converge resources as their own files
`mcp_server`, `skill`, `channel`, `provider` and `knowledge` resources MUST
converge as their files, `vault/resources/<kind>/<name>.json` — the file is the
resource, not a serialization of a row kept elsewhere ([vault-storage](../vault-storage/spec.md)
"Identify a resource by the uid inside its file"). A resource file is identity,
title, description and config — what the resource *is*; what it reaches is not
in it (see "Keep reach machine-local"). Agents are machine-local and never
converge. The `title` is optional: a resource with no title has no `title` key.

#### Scenario: a resource document is identity, description and config
- **GIVEN** a registered resource with a description, a config and a reach of its own
- **WHEN** its file is read from the vault
- **THEN** the file holds its uid, kind, name, description and config
- **AND** it holds no `enabled` flag and no `scope`, and the vault's history never carries them


### Requirement: Carry a channel's file but not its adapter
A `channel` file MUST travel while its adapter does not. A channel is an inbound
surface — a polled bot or a held websocket connection, each of which a platform
serves to one consumer at a time — so its config names the one machine that may
answer: `runs_on`, the `machine_id` whose daemon starts the adapter ([channels](../channels/spec.md)
"Bind each channel to the one machine that runs it"). Every other machine holds
the channel's configuration, its credential references and its pairings, starts
nothing for it, and does not judge it against agents it happens to have, so
taking over a bot is a rebind rather than a re-registration.

A channel's machine binding is not the retired machine axis of `scope` coming
back. Reach is "which agents, here" — a local answer each machine gives itself.
The binding is "which machine runs the adapter" — one answer the machines share,
so it lives in the channel's file and travels with it.

#### Scenario: a channel travels and runs only on the machine it names
- **GIVEN** a `channel` bound to one machine, held by two
- **WHEN** both daemons start their channels
- **THEN** only the machine it names starts an adapter for it, and the other holds the channel and runs nothing


### Requirement: Carry secrets as ciphertext only
Stored secrets MUST travel as Fernet **ciphertext only** — the files
`vault/secret/<ref>.enc` — and only when the remote is configured to carry them
(`include_secret`). Until then `secret/` is in the vault repository's exclude
file and is in no commit. A resource's config names a secret by reference and
never holds its value.

#### Scenario: ciphertext travels only when the remote carries it
- **GIVEN** a stored secret on a machine whose remote does not carry secrets
- **WHEN** it runs a round and the other machine runs one
- **THEN** the ciphertext is in no commit and the other machine has no copy
- **AND** once both remotes carry secrets, the ciphertext reaches the other machine byte for byte


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
/api/v1/sync/runs/{id}/rollback-plan`, `coffer sync rollback <round>` without
`--yes`), and runs through `POST /api/v1/sync/runs/{id}/rollback`, `coffer sync
rollback <round> --yes` and the Runs tab.

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
- **WHEN** `coffer sync rollback <round>` runs and the person declines
- **THEN** it has printed what it would reverse and changed nothing, and `--yes` rolls the round back


### Requirement: Report the refs a key cannot open as locked
A machine holding ciphertext its master key cannot open MUST report those refs
**locked** rather than failing decryption silently: importing a key MUST answer
which refs it still cannot open, and the Sync page shows the refs this machine
cannot decrypt. A key file that is blank or not a key MUST be refused.

#### Scenario: credentials this machine cannot decrypt are reported locked
- **GIVEN** a machine holding ciphertext written under a master key it does not hold
- **WHEN** a master key is imported that still does not open it
- **THEN** the import names those refs as still locked, and a blank or malformed key is refused


## MODIFIED Requirements

### Requirement: Run a round as pull, merge, guard, check out, push
A round MUST be these steps **in this order**:

```
1  Pull      — fetch the remote's branch (tip R); this vault's HEAD is L
2  Merge     — git merge-tree --write-tree L R, outside the working tree,
               from their merge base
3  Stop?     — any conflict or a merged file validation refuses: stop, whole
4  Guard     — the deletion breaker, incoming (L -> merged) and outgoing
               (base -> L)
5  Snapshot  — tag L as refs/tags/coffer/pre-apply/<time>
6  Check out — move the vault to the merged tree in one compare-and-swap step
7  Push      — push the merged commit; this machine's descriptor rides along
```

Nothing is written to the vault before step 6, so a round that stops, holds or
fails leaves the vault exactly as it was. Most concurrent edits are not
conflicts: git merges different hunks of one file without help. A round with
nothing to pull and nothing to push makes no commit.

#### Scenario: a changed vault converges and pushes
- **GIVEN** two joined machines that each wrote a different knowledge document
- **WHEN** the first runs a round and then the second
- **THEN** the first pushes, the second pulls the first's document behind a pre-apply snapshot and pushes its own, and the first then pulls it

#### Scenario: concurrent edits to different parts of one document merge
- **GIVEN** two machines that each edited a different line of one knowledge document
- **WHEN** both run rounds
- **THEN** the document holds both edits and no conflict is reported

### Requirement: Keep the remote a rendezvous, not a system of record
Convergence with a user-owned git remote is a bounded exception to the
constitution's local-first principle (0.6.0): the remote MUST be a
**rendezvous, not a system of record**. Every machine's vault is a complete git
repository of its own, so the remote can be deleted and rebuilt from any single
machine without losing anything.

#### Scenario: a remote rebuilt from one machine loses nothing
- **GIVEN** a machine's vault and an empty remote
- **WHEN** the machine joins the remote
- **THEN** the remote's branch is the vault's own `HEAD`, holding every committed file
- **AND** the machine's vault is unchanged

### Requirement: Converge knowledge files and the skill store
The knowledge collections under `vault/knowledge/` and the skill master
folders under `vault/skills/` are files of the vault repository and MUST
converge as files, merged by git. Coffer's own generated skill is not among
them: it lives under `derived/` (see "Withhold derived output in both halves").

#### Scenario: a local-only document survives a round
- **GIVEN** a knowledge document each of two machines created and the other has never seen
- **WHEN** both run a round
- **THEN** each document is still present where it was written and is now on the other machine too

### Requirement: Skip symlinks and nested repositories
The vault repository MUST NOT record a symlink (its target is not vault content,
and a link to a file outside the vault would otherwise be published) or anything
inside a nested git repository, so neither is ever pushed; Python bytecode
(`__pycache__/`, `*.pyc`, `*.pyo`), which the interpreter writes beside a skill's
scripts whenever they run, and editor and system litter are kept out by the
repository's own exclude file.

#### Scenario: a symlink in the vault is skipped rather than published
- **GIVEN** a skill folder holding a symlink to a file outside the vault, and a nested git repository beside it
- **WHEN** the vault settles what is on disk
- **THEN** only the skill's own file is committed, and nothing is left pending

#### Scenario: Python bytecode beside a skill's scripts is not published
- **GIVEN** a skill whose `scripts/` holds a `__pycache__/` of `.pyc` files beside its scripts
- **WHEN** the vault settles what is on disk
- **THEN** the scripts are committed and the bytecode is not, and nothing is left pending

### Requirement: Converge shared state areas
Module-owned shared state that belongs to the vault rather than to one machine
MUST converge as vault state documents under `vault/state/<area>/`: MCP
capability switches (`state/mcp-preferences/<server>.json`), channel peer
pairings (`state/channel-peers/<channel>.json`) and Coffer's own engine settings
(`state/settings/internal-engine.json`). A state document names its owner by
uid; an area with nothing but its defaults has no document. The plugin
inventory is not a state area: it is carried in each machine's descriptor (see
"Record plugins as an inventory, not a replicator").

#### Scenario: each shared state area reaches the working tree
- **GIVEN** a switched-off MCP capability, a channel pairing and a non-default engine setting
- **WHEN** each is stored
- **THEN** each is a vault document under its area, named by its owner, and when each capability was first and last seen stays in `derived/`
- **AND** engine settings at their defaults have no document

### Requirement: Carry channel pairings as platform identity
Channel peer pairings MUST travel as **platform identity** — chat id, sender id,
display name and pairing time — in the channel's state document, keyed by the
channel's uid, because a channel that moved to another machine without its
pairings would make the owner re-pair from their phone on every rebind. Renaming
the channel MUST move its pairings document in the same commit.

#### Scenario: a channel's pairings travel with it
- **GIVEN** a paired `channel`
- **WHEN** the channel is renamed
- **THEN** one commit moves both the channel's file and its pairings document, and the pairings and the owner's identity are unchanged

### Requirement: Record plugins as an inventory, not a replicator
The plugin inventory MUST be an **inventory, not a replicator**: each machine's
descriptor lists the agents registered there and the plugins each has, and
nothing MUST write any of it into any agent's configuration — a descriptor is
never applied. An agent whose plugins cannot be read is listed with none.

#### Scenario: an arriving plugin inventory writes nothing into an agent
- **GIVEN** a machine with an agent that has a plugin
- **WHEN** it runs a round
- **THEN** its descriptor lists the agent's type and the plugin
- **AND** no machine applies that list to an agent's configuration

### Requirement: Let the fresher credential ciphertext win
Secret ciphertext MUST NOT reach a text merge or a question. A Fernet token
carries its encryption time in cleartext, so two ciphertexts for one ref can be
ordered without the key, and the **fresher encryption wins**. This rule applies
to `secret/**.enc` and to nothing else.

#### Scenario: the fresher credential ciphertext wins
- **GIVEN** one secret ref re-encrypted on both machines, the other machine's encryption being the fresher one
- **WHEN** the two meet in a round
- **THEN** both machines hold the fresher ciphertext, the round pulls it, and there is nothing to ask

### Requirement: Publish one descriptor per machine
One machine descriptor, `vault/machines/<machine_id>.json`, per machine MUST
travel (see "Write only this machine's descriptor").

#### Scenario: a round publishes this machine's descriptor and no other
- **GIVEN** three machines joined to one remote
- **WHEN** each runs rounds
- **THEN** the remote holds one descriptor per machine at `machines/<machine_id>.json`, each written only by its own machine

### Requirement: Write only this machine's descriptor
Each machine MUST write exactly one descriptor, at `machines/<machine_id>.json`,
and MUST write no other machine's — except that retiring another machine
deletes its descriptor (see "Derive the registry from the descriptors"). Every
machine owning a disjoint path is what makes these documents unable to
conflict.

#### Scenario: the machine registry shows every machine and cannot conflict
- **GIVEN** two machines that have both run rounds
- **WHEN** the machines table is read on either
- **THEN** it lists both with their names, when each last ran a round and whether each one's key matches this machine's, marks the local one, and the vault holds one descriptor per machine with no conflict between them

### Requirement: Derive the registry from the descriptors
The registry MUST be whatever `machines/*.json` currently holds — a derived
view, never a table of its own. Retiring another machine removes its descriptor
in a commit of this machine's; retiring this machine is refused. A retirement
MUST survive a remote that moved on meanwhile.

#### Scenario: a retired machine leaves the registry with its descriptor
- **GIVEN** three machines joined to one remote
- **WHEN** one retires another while the remote has moved on
- **THEN** the retired machine's descriptor is gone from the vault and the remote, the registry no longer lists it, and the remaining descriptors are untouched
- **AND** retiring this machine, or a machine the registry does not hold, is refused

### Requirement: Carry the descriptor fields
A descriptor MUST carry its `format_version`, `machine_id`, `name`, `os`,
`hostname`, `coffer_version`, `last_round_at`, `last_converged_commit`,
`key_fingerprint`, and the agents registered on that machine with their plugins.
A descriptor from a newer build MUST still be read for the fields this build
knows.

#### Scenario: a descriptor carries what the machines table shows
- **GIVEN** a machine with an agent registered and a master key
- **WHEN** it runs a round
- **THEN** its descriptor carries its format version, name, operating system, hostname, Coffer version, when it last ran a round, the commit it last converged at, its key fingerprint and its agents
- **AND** the descriptor reads back to the same fields

### Requirement: Publish this machine's pointer in its descriptor
`last_converged_commit` MUST publish the commit this machine last converged at,
so the remote can hand it back to a machine that lost its vault's history (see
"Recover a returning machine's base from its descriptor").

#### Scenario: a descriptor publishes the pointer this machine reached
- **GIVEN** a machine that has converged with the remote
- **WHEN** its descriptor is read from the remote
- **THEN** it names the commit the machine last converged at, a commit in the remote's history

### Requirement: Keep machine identity across reinstalls
`machine_id` MUST survive reinstalling and uninstalling Coffer. A machine that
comes back under a new identity becomes a ghost: it rejoins as a stranger, its
old descriptor lingers in the registry with nobody to update it, and anything
that named it — the curation owner, a channel's binding — silently stops meaning
this machine.

#### Scenario: a machine identity survives reinstalling Coffer
- **GIVEN** a machine whose cached identity is lost, on a host that exposes a stable identifier
- **WHEN** its identity is resolved again and it joins the remote
- **THEN** it has the same machine id, the remote's registry holds it, and it joins as a returning machine rather than as a stranger

### Requirement: Fall back to a stored identifier and say so
Where neither host identifier is readable, a UUID MUST be generated once and
stored at `~/.coffer/machine-id` (mode `0600`). This one does **not** survive
deleting `~/.coffer`, and the identity MUST say that it was not derived from the
host, so such a machine is known to reappear under a new id if `~/.coffer` is
deleted.

#### Scenario: a machine with no host identifier falls back and says so
- **GIVEN** a host that exposes no readable identifier
- **WHEN** the machine identity is resolved twice
- **THEN** a UUID is stored at `~/.coffer/machine-id` with mode `0600`, both resolutions give the same id, and the identity is marked as not derived from the host

### Requirement: Publish only a hash of the host identifier
The raw host identifier MUST NOT be written into the vault — it is a hardware
identifier. What travels MUST be `sha256("coffer-machine:" + raw)` truncated to
16 hex characters, which also names the machine's one descriptor path.

#### Scenario: the raw host identifier never reaches the repository
- **GIVEN** a host identifier
- **WHEN** the machine id is derived from it
- **THEN** the id is 16 hex characters that do not contain the raw value, and it names exactly one descriptor path

### Requirement: Keep machine-local state out of the repository
Only `~/.coffer/vault/` is a repository. Everything true of one machine only
MUST be stored outside it: `local/` (agents, reach, the sync remote, retention,
the secret boundary's files, machine-local ciphertext), `content/` (media and
the chat workspace), `runs.db` (conversations, the audit log, MCP invocation
records, rounds, usage), `derived/` (the memory tree and everything rebuilt),
and `daemon-config.json`, `daemon.json`, the master key and logs directly under
`~/.coffer` ([vault-storage](../vault-storage/spec.md) "Store state in five
classes by nature"). The master key MUST **never** be written into the vault
(see "Never write the master key into the repository").

#### Scenario: machine-local files never reach the working tree
- **GIVEN** an agent, a machine-local resource and a derived one registered on a machine, and a migrated home's reach, retention and remote settings
- **WHEN** the vault's history and tree are read
- **THEN** none of them is in the vault: each is a file under `local/` or `derived/`

### Requirement: Keep reach machine-local
**Reach** — a resource's `enabled` flag and its `scope` — is machine-local and
MUST NOT travel in either direction: it is `local/reach.json`, keyed by resource
uid. They read like two fields but they are one thing, written by one control:
whether this resource is live here, and for which agents. Publishing it would
let one machine silently re-answer a question another machine had already
answered for itself.

#### Scenario: reach stays on the machine it was set on
- **GIVEN** a resource disabled on this machine and restricted to one agent
- **WHEN** its reach is stored and the resource's file is committed
- **THEN** the reach is in `local/reach.json` under the resource's uid and in no commit of the vault

### Requirement: Withhold derived output in both halves
**Derived output MUST NOT converge, in either half**, and it cannot, because it
is stored under `derived/`, outside the vault. Coffer's own generated skill
`coffer-guide` is the case this exists for: its text is rendered locally from
the running build, the knowledge files and which collections this machine has
enabled — which is reach, and machine-local — so two machines holding identical
files render different bytes, each correct where it is. **Both halves** are
derived: its master folder (`derived/skills/coffer-guide/`) and its resource
file (`derived/resources/skill/coffer-guide.json`). Every other skill is in the
vault. Memory partitions are derived the same way.

#### Scenario: a locally generated skill is neither published nor overwritten
- **GIVEN** Coffer's own skill and a person's imported skill
- **WHEN** each is filed
- **THEN** Coffer's own is stored under `derived/` and the person's under the vault, so only the person's can converge

### Requirement: Allow at most one user-owned sync remote
A vault MUST have **at most one** sync remote: a git repository the user owns,
configured with a URL, a branch, a push credential reference, the username an
HTTPS token is sent with, an interval, whether secret ciphertext rides along
(`include_secret`), and whether it is on. The remote is machine-local
configuration, `local/sync/remote.json`. Sync MUST be off until the user
configures it. The interval MUST be at least 60 seconds: a shorter one is
refused before anything is stored. The username defaults to `coffer`; GitHub and
GitLab ignore it for a token, while Bitbucket (for example `x-token-auth`) and
Azure DevOps need a real one, and a username git cannot send — blank, or
holding a space, `:`, `@` or `/` — MUST be refused. The username and the token
reach git only through the credential helper's environment.

#### Scenario: sync stays off until a remote is configured
- **GIVEN** a vault with no sync remote configured
- **WHEN** the worker ticks and a round is requested over REST
- **THEN** the worker runs no round, and the request is refused as `SYNC_NO_REMOTE`

#### Scenario: an interval under a minute is refused
- **GIVEN** a remote being set with an interval of 59 seconds
- **WHEN** the request is validated
- **THEN** it is refused naming the 60-second floor, and 60 seconds is accepted

#### Scenario: a token is sent with the username the remote names
- **GIVEN** a remote with no username and another with `x-token-auth`
- **WHEN** git is given the push token
- **THEN** the first sends `coffer` and the second `x-token-auth`, both only through the credential helper's environment
- **AND** a username with a space, `:`, `@` or `/` is refused

### Requirement: Refuse a URL or branch git would read as an option
The URL and the branch become arguments to `git`, so neither MAY begin with `-`
(git would read it as an option, and `--receive-pack=<cmd>` is a command) and
the branch MUST pass the rules of `git check-ref-format --branch`. Both MUST be
refused at the API, at the CLI and again by the domain object. The git adapter
MUST fence every positional argument git lets it fence with `--` and MUST push
an explicit `refs/heads/` refspec.

#### Scenario: a remote URL or branch that git would read as an option is refused
- **GIVEN** a remote URL beginning with `-`, or a branch beginning with `-` or failing `git check-ref-format --branch`
- **WHEN** the remote is configured over REST or built as the domain object
- **THEN** each is refused and no remote is stored

### Requirement: Keep the pointer local
There is no pointer apart from the vault's own history. A round's base MUST be
the merge base of this vault's `HEAD` and the remote's tip, so what this machine
has absorbed is exactly what its history shares with the remote; nothing about
it travels as an input to the algorithm except the `last_converged_commit` a
returning machine reads back from its own descriptor.

#### Scenario: a round diffs from the pointer stored on this machine
- **GIVEN** two machines that converged, after which one deleted a document the other never touched
- **WHEN** the other machine, holding a new document of its own, runs a round
- **THEN** the merge from the shared history applies the deletion and publishes the new document

### Requirement: Apply a deletion only when the diff carries one
A deletion MUST be applied only when one side of the three-way merge deleted the
file relative to the shared base. A machine that merely *lacks* a document it
never had makes no change relative to that base, and that MUST NOT be read as a
deletion; a machine that did not touch a file another machine deleted takes the
deletion rather than resurrecting it.

#### Scenario: a stale machine does not resurrect a deletion
- **GIVEN** a machine behind the remote, which never touched a document the other machine deleted and pushed
- **WHEN** that machine runs its next round
- **THEN** the deletion is applied here, and the document does not come back on the remote

### Requirement: Tell a new machine from a returning one
A machine that has never converged with the remote is **joining**, and the join
MUST tell which case it is before it does anything: **empty** (the remote holds
nothing: this machine becomes the first and pushes its whole vault), **new**
(the remote's history shares nothing with this vault and holds no usable base
for this machine) or **returning** (the remote carries this machine's
descriptor, whose `last_converged_commit` is still in the remote's history).

#### Scenario: a joining machine is placed from the remote's registry
- **GIVEN** an empty remote, a remote another machine filled, and a remote holding this machine's own descriptor from before a reinstall
- **WHEN** each join is previewed
- **THEN** they are `empty`, `new` and `returning` respectively

### Requirement: Join a new machine by taking the union
A **new machine** MUST take the union: files only the remote has are pulled,
files only this machine has are pushed, identical files need nothing, and a file
both hold with different content is left exactly as it is here — not pushed, not
committed over — until the person chooses, per file or for all, to keep this
machine's (pushed by the next round) or take the remote's. Joining MUST NOT
delete a file on either side. A machine the registry knows whose recorded base
is no longer in the remote's history joins the same way. A resource of the same
name and a different uid stops the join as a conflict (see "Treat the same name
with a different uid as a conflict").

#### Scenario: a new machine takes the union and deletes nothing
- **GIVEN** a remote holding one machine's vault, and a new machine with files of its own, one of which the remote holds with different content
- **WHEN** the new machine joins
- **THEN** everything the remote holds is added here, everything this machine held is still present, the differing file keeps this machine's content and is not pushed, and nothing is deleted on either side

#### Scenario: a differing file waits until the person chooses
- **GIVEN** a join that left a differing file
- **WHEN** the person keeps this machine's version, or instead takes the remote's
- **THEN** keeping it pushes it on the next round, and taking the remote's replaces it here, and either way nothing is left pending

### Requirement: Recover a returning machine's base from its descriptor
A **returning machine** MUST recover its base from its own descriptor's
`last_converged_commit` and join with an ordinary three-way merge from it: the
remote's deletions are taken, this machine's own edits and deletions since are
kept and guarded by the breaker, and nothing resurrects.

#### Scenario: a returning machine does not resurrect what was deleted while it was away
- **GIVEN** a machine that converged before, lost its vault's history to a reinstall while its files survived, and deleted one file while offline
- **WHEN** it joins the remote again
- **THEN** the preview says it is returning with its base and lists the deletion, and after the join the file is gone from the other machine too while its kept files are unchanged

### Requirement: Hold a returning machine's empty vault instead of publishing the loss
A vault that lost its files — a reinstall that took them, a failed restore, a
stray `rm -rf` — MUST NOT publish the loss. Coffer cannot tell a wiped disk from
a deliberate purge, so the outgoing deletion breaker (see "Guard both
directions") MUST hold the round before anything is pushed and ask.

#### Scenario: a returning machine with an empty vault does not publish the loss
- **GIVEN** a machine that converged 25 documents and then lost all of them
- **WHEN** a round runs
- **THEN** nothing is pushed, the round is `held` on the outgoing side naming the 25 files, and the remote is unchanged until the person confirms

### Requirement: Report a join before applying it
Joining MUST be explicit and previewed: before anything is applied the surfaces
MUST state which case it is, who pushed the remote's newest commit and when,
what would be pulled and pushed by area, how many files are the same, which
differ, and — for a returning machine — what the merge would delete or stop on;
a remote at the wrong layout is refused in the preview. `GET
/api/v1/sync/join/preview` applies nothing; `POST /api/v1/sync/join` joins as the
preview said; `coffer sync join` prints the preview and asks before joining
(`--yes` skips the question); the Sync page shows the preview and joins on the
person's click.

#### Scenario: a join states its case and its counts before applying
- **GIVEN** a machine that has not joined its remote
- **WHEN** `coffer sync join` runs and the person declines, then runs it again with `--yes`
- **THEN** the first prints which case the join is and applies nothing, and the second joins

### Requirement: Detect joining on every round without a pointer
A round on a machine that has not joined its remote — never joined, or set to
another URL or branch since — MUST apply and push nothing and end
`join_required`, so no timer round, `coffer sync now` or `POST
/api/v1/sync/run` ever joins on its own.

#### Scenario: an ordinary round on a machine without a pointer still detects the join
- **GIVEN** a machine with a remote it has not joined, and a machine whose remote was just set to another URL
- **WHEN** an ordinary round runs on each
- **THEN** each ends `join_required` and nothing is applied or pushed

### Requirement: Apply knowledge, skill and memory-trigger file changes
What a round applies MUST be a checkout of the merged tree: an added or modified file
under `knowledge/`, `skills/`, `memory-triggers/`, `resources/`, `state/`,
`secret/` or `machines/` is written, and a deleted one removed, in the one
compare-and-swap step that refuses to overwrite a person's unsettled edit (see
"Never overwrite a person's unsettled edit"). Stores that read the vault reload
from the new `HEAD`, so an arriving resource file is a resource and an arriving
state document is in effect without any per-kind import step.

#### Scenario: an arriving file is written and a deleted one removed
- **GIVEN** two machines that each wrote a knowledge document
- **WHEN** both run rounds
- **THEN** each machine holds the other's document with the same bytes

#### Scenario: an arriving memory trigger is written into the vault
- **GIVEN** a memory trigger written on one machine
- **WHEN** it runs a round and the other machine runs one
- **THEN** the other machine's vault holds the trigger's file under `memory-triggers/` with the same bytes

### Requirement: Re-run post-import hooks after applying
After a round applied files here, each kind's machine-local side effects MUST be
brought in step from the new state by one reconcile pass (see "Run the
reconciler once after a round that applied changes"); a round that applied
nothing runs none.

#### Scenario: a remote addition lands in the vault
- **GIVEN** another machine that pushed a knowledge document
- **WHEN** this machine's round pulls it
- **THEN** the document is in this vault and one reconcile pass has run

### Requirement: Never apply the registry or the manifest
`machines/*.json` and `manifest.json` MUST NOT be projected into anything local —
the registry is read from the vault, and the manifest is metadata about the
layout — and MUST NOT count towards the deletion breaker.

#### Scenario: the registry and manifest are never applied
- **GIVEN** a diff that deletes thirty descriptors and the manifest
- **WHEN** the breaker counts its losses
- **THEN** it counts none

### Requirement: Ask the user to confirm a tripped breaker
A tripped breaker MUST hold the round before anything is checked out or pushed
and record which direction it is — **outgoing** (this machine's own commits
would remove the files from the remote) or **incoming** (the remote's would
remove them here) — and which files, grouped by folder with the share of each
folder they are. The person answers: **delete** them (the round continues and
applies or pushes the deletions) or **restore** them (the round continues and
the files are kept, pushed back if the remote had lost them). Both answers are
on REST (`POST /api/v1/sync/hold/confirm`, `POST /api/v1/sync/hold/restore`), the
command line (`coffer sync hold --confirm|--restore`) and the Sync page.

#### Scenario: an oversized deletion is held for confirmation
- **GIVEN** a machine that removed 22 documents of one folder, and the machine that receives that deletion
- **WHEN** each runs a round
- **THEN** the first is held outgoing and the second incoming, each listing the files by folder, with nothing applied or pushed
- **AND** confirming pushes the deletion, while restoring keeps the files here and pushes them back

### Requirement: Guard both directions
The breaker MUST run in **both directions** — over what the round would remove
from this vault, and equally over what this machine's own commits since the
shared base would remove from the remote. The second is what stops a vault that
lost its files to a reinstall, a failed restore or a stray `rm -rf` from
publishing that loss and taking the other machines down with it. A join as a
new machine deletes nothing in either direction and is unaffected.

#### Scenario: a wiped area is held although rename pairings are consulted
- **GIVEN** a vault that lost every document in an area with nothing added in their place
- **WHEN** a round runs
- **THEN** there is nothing for a pairing to match, the round is held on the outgoing side, and the loss is not pushed

### Requirement: Count losses, not deletions
The breaker MUST count what a round **loses**, not what it deletes. A resource
file is lost only when its **uid** is gone from the other side: a file that
disappears while its uid reappears under another name is a move by
construction. Any other file is a move when its exact bytes land elsewhere in
the same area, or git's own rename detection pairs it with a file in the same
area. A move MUST NOT count towards either threshold or appear in the list a
hold shows. A pairing that crosses an area MUST be discarded, since the
breaker's unit is the area, and the empty file never pairs on content.

#### Scenario: a re-layout publishes without asking
- **GIVEN** a diff that moves thirty documents into a subfolder of their area with their bytes unchanged, and deletes one more
- **WHEN** the breaker counts its losses
- **THEN** only the one deletion is a loss, while the same bytes landing in another area, or two empty files, are not paired

#### Scenario: moving resource files is not a loss
- **GIVEN** 25 resource files renamed, each keeping its uid
- **WHEN** the machine that renamed them and the other machine run rounds
- **THEN** neither round is held

### Requirement: Ask git about renames separately from the applied diff
The breaker MUST ask git's rename detection as a question of its own, only to
tell a move from a loss; it MUST NOT change what the merge produces or what is
checked out.

#### Scenario: a re-layout that rewrites its documents publishes without asking
- **GIVEN** a document moved to a new folder of its area **and edited on the way**, so no content id pairs the two sides
- **WHEN** git's rename detection pairs them
- **THEN** it is a move, while a pairing git finds across areas is still a loss

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

### Requirement: Release a hold whose diff no longer breaches
A hold is a question about one pair of commits. It MUST stand while neither this
vault nor the remote moves, and a round in that time answers the same hold
again; once either side has a new commit the round MUST re-derive its merge and
breaker, and a hold whose diff no longer breaches MUST be released without
anyone answering it.

#### Scenario: a hold is released once its diff no longer breaches
- **GIVEN** a vault held on the outgoing side after 22 documents were removed
- **WHEN** the documents are written back and a round runs
- **THEN** the round is not held and nothing is left waiting on the person

### Requirement: Never overlap a curation pass and a round
A curation pass and a round MUST NOT overlap. Both write the vault, so they MUST
take the same lock, and the worker MUST wait for a pass to finish rather than run
a round under it. A pass MUST additionally be skipped while a round waits for a
person — a stop on conflicts, a hold, or a join's differing files — so a rewrite
is never piled onto the very files the person is deciding between.

#### Scenario: a curation pass and a converge round do not overlap
- **GIVEN** a curation pass holding the vault lock
- **WHEN** the sync worker ticks
- **THEN** no round is recorded until the pass releases the lock, and then one is

#### Scenario: a curation pass is skipped while a round is unresolved
- **GIVEN** a machine whose last round stopped on a conflict
- **WHEN** the unattended curation pass asks whether it may run
- **THEN** it is told no, and once the conflict is answered and the round continued it is told yes again

### Requirement: Serialize deterministically
Every vault document MUST be written with one deterministic encoding ([vault-storage](../vault-storage/spec.md)
"Keep every vault document a JSON object that preserves what it does not
know"), so an unchanged vault is an unchanged tree and a write that changes
nothing makes no commit.

#### Scenario: an unchanged vault serializes to an identical tree
- **GIVEN** a document written by Coffer
- **WHEN** it is read and written again with nothing changed
- **THEN** its bytes are identical and no commit is made

### Requirement: Store paths outside home verbatim
Paths outside `$HOME` MUST be stored verbatim. Such a path may not exist on
another machine; that is the resource's business on that machine, not the
round's.

#### Scenario: a path outside the home directory is stored verbatim
- **GIVEN** a config value naming an absolute path outside the home directory
- **WHEN** it is made portable for the vault and expanded again on another machine
- **THEN** the path is carried exactly as written, with no `${HOME}` sentinel

### Requirement: Never write the master key into the repository
The master key MUST never be written into the vault: it stays in the OS
credential store or `~/.coffer/master.key`, outside the repository. It is
bootstrapped onto another machine out-of-band: a backup is written only by the
desktop app, behind a presence check ([secret](../secret/spec.md)
"Release plaintext only to a present human in the desktop app"), and installed
on the other machine with `coffer sync key import`.

#### Scenario: the master key never enters the repository
- **GIVEN** a remote configured to carry secret ciphertext, and a key file beside the vault
- **WHEN** a round pushes
- **THEN** the remote holds the ciphertext files and no key material

### Requirement: Restore to a revision without discarding later work
Going back to an earlier version of a vault file or folder MUST NOT discard
anything the vault gained since: restoring writes that version back as a new
commit through the vault's one write path (`coffer vault restore`, `POST
/api/v1/vault/restore`, the Skills History tab — [vault-storage](../vault-storage/spec.md)
"Show, compare and restore any version of a vault file"), touching only the
paths restored, and the next round publishes it like any other change.
Undoing what one round did is its rollback (see "Snapshot before checking out
and roll a round back from it").

#### Scenario: restore brings back a document deleted last week
- **GIVEN** a file with two versions in the vault's history
- **WHEN** the person restores the first
- **THEN** the file holds the first version's bytes as a new commit, and no earlier commit is rewritten

### Requirement: Cover the sync lifecycle on the command line
The CLI MUST cover the round and the vault's lifecycle — `coffer sync now`,
`status [--json]`, `history [--limit]`, `rollback <round> [--yes]`,
`join [--yes]`, `conflicts`, `resolve <path> --mine|--theirs|--edited`,
`edit <path>`, `continue`, `hold [--confirm|--restore]`,
`choose [<path> --mine|--theirs]` — and its administration:
`remote set <url> [--branch] [--interval <seconds>] [--with-secret|--without-secret] [--secret-ref] [--username] [--wait]`,
`remote clear`, `remote pause`, `remote resume`, `remote check`,
`machine list`, `machine rename <name>`, `machine rm <id>`,
`key import <file>`, `key fingerprint`. There is no `key export`: a key backup
leaves a machine only through the desktop app. An option `remote set` is not
given keeps the stored remote's value. `remote pause` and `remote resume` switch
the remote's `enabled` switch off and on (see "Pause a configured remote without
forgetting it") and change nothing else.

`status` MUST report the configured remote and every one of its settings — URL,
branch, interval, whether secret ciphertext travels, the push credential ref,
the username and whether the remote is on — beside this machine, the last round,
what waits to push and anything waiting for the person, in plain and `--json`
output; with no remote configured it says so and names `remote set`.

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
`GET /status`, `POST /run`, `GET /runs`, `GET /runs/{id}`,
`GET /runs/{id}/rollback-plan`, `POST /runs/{id}/rollback`,
`GET|PUT|DELETE /remote`, `POST /remote/check`, `GET /join/preview`,
`POST /join`, `GET|POST /join-choices`, `GET /stop`,
`POST /stop/files/answer`, `POST /stop/files/editor`,
`GET /stop/files/versions`, `POST /continue`, `POST /hold/confirm`,
`POST /hold/restore`, `GET /machines`, `PATCH /machines/self`,
`DELETE /machines/{id}`, `GET /key/fingerprint`, `POST /key/import`. No sync
route returns the master key.

#### Scenario: the HTTP API serves every sync operation
- **GIVEN** the daemon's sync routes
- **WHEN** they are listed
- **THEN** every method and path the requirement names is served, and none exports a key

### Requirement: Show a conflict as a banner
A round stopped on conflicts MUST be shown as a card above the runs table, not as
a row: it lists each conflicting file with the machine whose version it met, the
three answers (keep this machine's, take the other's, open in the editor and mark
resolved), how many are answered, and Continue once all are. A hold, a join
preview and a join's differing files are shown the same way, each on its own
card with its own answers.

#### Scenario: a conflict is shown as a banner above the runs
- **GIVEN** a vault whose last round stopped on a conflict
- **WHEN** the Runs tab renders
- **THEN** a card above the table names each conflicting file with its answers

### Requirement: Pause a configured remote without forgetting it
A configured remote MUST carry an `enabled` switch, and switching it off MUST
pause sync without forgetting anything: the worker runs no timer round, and no
surface raises attention for it — `coffer sync status` exits zero, the web UI
does not mark its sync entry and the desktop shell marks nothing — even over a
round the vault was waiting on, because a user who met a question by switching
sync off has answered it too. A round the person asks for by name ("Sync now")
still runs. The remote and the history MUST be kept, so switching it back on
resumes where the vault left off. Re-running `coffer sync remote set` MUST keep
a paused remote paused — it changes what it names and nothing else: every option
it is not given keeps its stored value — and a remote configured for the first
time is stored enabled, with the defaults for every option it is not given.

#### Scenario: a paused remote runs no round and asks for nothing
- **GIVEN** a joined vault whose remote is then switched off
- **WHEN** the worker ticks
- **THEN** no round is recorded and no next round is scheduled
- **AND** `coffer sync status` exits zero, the web UI does not mark its sync entry and the desktop shell marks nothing

#### Scenario: reconfiguring a paused remote keeps it paused
- **GIVEN** a configured remote that has been switched off
- **WHEN** `coffer sync remote set` is run again with a different interval
- **THEN** the remote it sends carries the new interval and is still switched off
- **AND** a remote set for the first time is sent switched on with the defaults

#### Scenario: reconfiguring a remote changes only what it names
- **GIVEN** a configured remote with a non-default branch, interval, push credential and username, carrying secret ciphertext
- **WHEN** `coffer sync remote set` is run again naming only a new interval
- **THEN** every other setting is sent exactly as it was
- **AND** running it with `--without-secret` switches secret sync off and changes nothing else

### Requirement: Present a Sync page with Runs, Setup and Machines tabs
The web UI MUST present a top-level **Sync** page with **three** tabs. **Runs**,
the landing tab: the status of sync now (last round, what moved, the next round,
the machines, what the vault holds, Sync now), the cards for anything waiting on
the person (conflicts, a hold, a join and its differing files, a problem), what
waits to push, and every round this machine has run as a table — when, status,
what it pulled and pushed, the commits, and roll back. **Setup**: the remote
(with Check repository, whether secret ciphertext travels, pause and resume, and
Stop syncing), the vault's path with a warning when it sits in a synchronised
folder, and the master key. **Machines**: the machine registry, where a user
renames this machine or retires one that is gone.

#### Scenario: the Sync page opens on Runs beside Setup and Machines
- **GIVEN** the web UI
- **WHEN** the user opens the Sync page
- **THEN** it has exactly three tabs, Runs, Setup and Machines, and opens on Runs
- **AND** a link to a tab that no longer exists lands on Runs

## REMOVED Requirements

### Requirement: Converge resource definitions as serialized documents
**Reason**: A resource is no longer serialized from a database row: its file in the vault is the resource, and its title travels as a key of that file like any other.
**Migration**: "Converge resources as their own files".

### Requirement: Carry a channel's document but not its adapter
**Reason**: Restated for the channel's file in the vault, with "Start nothing when a channel arrives" folded in.
**Migration**: "Carry a channel's file but not its adapter".

### Requirement: Carry credentials as ciphertext only
**Reason**: Restated for the secret files, `vault/secret/<ref>.enc`, and the remote's `include_secret` flag.
**Migration**: "Carry secrets as ciphertext only".

### Requirement: Snapshot before applying and roll back from it
**Reason**: A round no longer applies a diff path by path and there is no `coffer sync restore`: a round is rolled back by naming it, as a new commit that keeps later edits.
**Migration**: "Snapshot before checking out and roll a round back from it".

### Requirement: Report refs without a key as locked
**Reason**: A round no longer resolves the key or reports locked refs; the key's import and the Sync page do.
**Migration**: "Report the refs a key cannot open as locked".

### Requirement: Key resource documents by uid
**Reason**: A resource is its own file, `resources/<kind>/<name>.json`, carrying its uid; nothing keys on the path, so a rename is a move of one file and there is no separate document to key.
**Migration**: The rule lives in [vault-storage](../vault-storage/spec.md) "Identify a resource by the uid inside its file"; the breaker counts resource files by uid ("Count losses, not deletions").

### Requirement: Let a kind withhold its own rows
**Reason**: What travels is decided by where a thing is stored, not by a flag the sync layer consults: a kind declares its storage class, and only the vault class is a repository.
**Migration**: [vault-storage](../vault-storage/spec.md) "Store state in five classes by nature"; memory partitions are derived.

### Requirement: Leave the paths of withheld derived output inert
**Reason**: Derived output is no longer in the vault at all, and a remote written by the old layout is refused and rebuilt rather than read, so there are no inherited paths to leave in place.
**Migration**: "Withhold derived output in both halves" and "Refuse a remote at another layout".

### Requirement: Keep the working tree outside the vault
**Reason**: There is no separate working tree: the vault is the repository.
**Migration**: None. The previous build's `~/.coffer/sync` is left in place by the one-time upgrade and named in its report.

### Requirement: Adopt an existing repository only when it is ours
**Reason**: There is no working tree to adopt; a remote is checked before it is saved.
**Migration**: "Check a remote before it is saved".

### Requirement: Mark and repoint a working tree Coffer made
**Reason**: There is no working tree; setting the remote points the vault's own `origin`.
**Migration**: "Allow at most one user-owned sync remote".

### Requirement: Repair the working tree first
**Reason**: There is no working tree that could drift from a pointer.
**Migration**: None.

### Requirement: Export differentially
**Reason**: Nothing is exported: every write is already a commit of the vault.
**Migration**: [vault-storage](../vault-storage/spec.md) "Admit every vault write through one compare-and-swap path".

### Requirement: Never export a retry-set path as a deletion
**Reason**: There is no export and no retry set: a round checks out a merged tree whole or stops.
**Migration**: "Never overwrite a person's unsettled edit".

### Requirement: Advance the pointer only on absorption
**Reason**: There is no pointer apart from the vault's history, and no per-path apply that could half-succeed.
**Migration**: "Keep the pointer local".

### Requirement: Record inapplicable paths as not applicable here
**Reason**: Agents, the one kind whose document could not apply on a machine without its config directory, are machine-local and never travel.
**Migration**: None.

### Requirement: Rebuild a vault from the remote only on request
**Reason**: A damaged machine answers the outgoing hold by restoring the files from the remote, or clears the remote and joins it again; there is no separate rebuild.
**Migration**: `coffer sync hold --restore`, or `coffer sync remote clear` then `coffer sync remote set` and `coffer sync join`.

### Requirement: Apply resource documents through the resource service
**Reason**: An arriving resource file is checked out like any file, validated first; the resource store reads it from `HEAD`.
**Migration**: "Apply knowledge, skill and memory-trigger file changes".

### Requirement: Apply state documents through their area's provider
**Reason**: State documents are checked out like any file; each area's store reads its document from `HEAD`.
**Migration**: "Apply knowledge, skill and memory-trigger file changes".

### Requirement: Apply credential blobs
**Reason**: Ciphertext files are checked out like any file; the secret store reads them where they are.
**Migration**: "Carry secrets as ciphertext only" and "Let the fresher credential ciphertext win".

### Requirement: Release unreferenced credentials on deletion
**Reason**: A round no longer deletes resources through the resource service; a deletion arrives as the file's removal, and the secret files travel as files of their own.
**Migration**: None.

### Requirement: Start nothing when a channel arrives
**Reason**: Folded into the requirement that already carries the channel's binding.
**Migration**: "Carry a channel's file but not its adapter".

### Requirement: Let each state area define its document's deletion
**Reason**: A state document's absence means its area's defaults, which each area's own spec states; sync applies no deletion of its own.
**Migration**: The areas' specs (mcp-gateway, channels, internal-engine).

### Requirement: Report per-path failures without aborting
**Reason**: A round no longer applies path by path: the merged tree is validated first and checked out whole, and anything that would fail stops the round as a conflict the person answers.
**Migration**: "Answer each conflicting file and continue the round".

### Requirement: Resolve remaining conflicts with an agent only in the working tree
**Reason**: The agent resolver is removed: any conflict stops the round and the person answers each file.
**Migration**: "Answer each conflicting file and continue the round".

### Requirement: Validate an agent's resolution
**Reason**: The agent resolver is removed.
**Migration**: A merged tree is validated like any write; a file that fails is a conflict the person answers.

### Requirement: Report every resolution with its paths
**Reason**: The agent resolver is removed; every conflict is answered by the person, per file.
**Migration**: "Answer each conflicting file and continue the round".

### Requirement: Abort the round on an unresolved conflict
**Reason**: Replaced by stopping on any conflict and answering each file; there is no resolver left for a conflict to be unresolved by.
**Migration**: "Stop the round on any conflict" and "Answer each conflicting file and continue the round".

### Requirement: Guard the retry set with the diff
**Reason**: There is no retry set.
**Migration**: "Guard both directions".

### Requirement: Let an edit beat a curation deletion
**Reason**: The automatic arbiter is removed: a curation deletion meeting an edit is a conflict like any other, and curation does not run while a round waits.
**Migration**: "Answer each conflicting file and continue the round" and "Never overlap a curation pass and a round".

### Requirement: Keep point-in-time restore on the command line
**Reason**: Going back in time is the vault's history restore, on the CLI, REST and the Skills History tab.
**Migration**: "Restore to a revision without discarding later work".

### Requirement: Restamp the convergence day at most once a day
**Reason**: The descriptor carries `last_round_at` and is rewritten only by rounds that move something, so there is no daily heartbeat to limit.
**Migration**: "Carry the descriptor fields".

### Requirement: Keep the active conversation pointer local
**Reason**: Conversations and their pointers live in `runs.db`, which never syncs; the pairings document carries platform identity only.
**Migration**: "Keep machine-local state out of the repository" and "Carry channel pairings as platform identity".

### Requirement: Refuse a returning machine whose base is gone until the user picks
**Reason**: A join never deletes a file on either side, so a machine whose base is gone joins by the union and asks about each differing file; there is nothing unsafe left to refuse.
**Migration**: "Join a new machine by taking the union".

### Requirement: Record one outstanding confirmation once
**Reason**: Every round is recorded; the Runs table folds consecutive held rounds into one counted row.
**Migration**: "Record every round" and "Fold consecutive quiet rounds into one row".

### Requirement: Put a held round's answers on its own row
**Reason**: A hold's answers are on the hold's card above the runs, not on a row.
**Migration**: "Show a conflict as a banner" and "Ask the user to confirm a tripped breaker".

### Requirement: Offer Undo on one round only when it applied something
**Reason**: Rollback names its round, so any round that applied something and still has its snapshot can be rolled back.
**Migration**: "Snapshot before checking out and roll a round back from it".

### Requirement: Restore only on request
**Reason**: A round only merges forward; going back is always an explicit vault restore or a round's rollback.
**Migration**: "Restore to a revision without discarding later work".

## RENAMED Requirements

- FROM: `### Requirement: Run the seven round steps in order`
- TO: `### Requirement: Run a round as pull, merge, guard, check out, push`
