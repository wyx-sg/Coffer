# Vault Sync

## Purpose

Keep one vault across the user's own machines by converging each of them with a
git repository the user owns. A developer works the same project from a laptop
and a desktop, and both produce vault state: knowledge files, skills, MCP
registrations, agent configuration, secrets. Without convergence each
machine is an island, and the fix — export here, carry the directory, import
there — is a chore nobody performs often enough for the two to stay alike. A
background worker commits what this vault holds, lets git three-way-merge it
against what the remote holds, and applies the resulting difference back —
deletions included. Background and alternatives in
[Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](../../../docs/decisions/sync-applies-clean-merges-and-stops-on-any-conflict.md).

**This spec also owns machine identity.** The name says "sync", but
`machine_id` — how it is derived, that it survives a reinstall, what travels in
its place, and the registry that lists it — is specified here and nowhere else.
Other specs key on it: a channel's machine binding in spec
[channels](../channels/spec.md) and the curation owner in spec
[knowledge](../knowledge/spec.md) both name a `machine_id` this spec defines.

Vocabulary. A **vault document** is the serialized form of one piece of vault
state at one path in the working tree: a knowledge file, a skill file, a
resource JSON file, a state JSON file, a secret blob, a machine descriptor. A
**converge round** is one full cycle of the round steps. A **machine** is one
installation of Coffer.

Conversations and the audit log are excluded deliberately: they are records of
what happened *on a machine*, and a merged history of two machines' activity
would be a different feature with a different shape (see `/activity`).

Out of scope:

- **Local export and import.** Deleted with this spec. Writing a bundle to a
  directory and reading one back is a wholesale overwrite with no base — the
  operation that caused the 2026-07-10 incident — and it has no place beside the
  diff-based apply. The needs it served are met without it: a new machine joins from the Sync page, an offline medium is a `file://` remote on a USB drive,
  and handing a copy to someone else is `git clone ~/.coffer/vault`.
- **More than one sync remote.** One rendezvous is what "one vault" means.
- **A hosted sync endpoint.** Would need a further exception to the principles'
  Local-First rule.
- **Syncing conversations, the audit log, or MCP invocation records.** They
  describe what happened on a machine; merging them is a different feature.
- **Merging two unrelated vaults into one.** First contact takes the union of
  documents; it does not reconcile two histories that never shared a base.
- **A machine × agent pair matrix.** `scope` has one list, `agents`, and no
  machine axis to pair it with (see "Scope names agents only"). Expressing
  "these agents on the desktop, those on the laptop" inside one travelling field
  is not supported and is not wanted: reach is machine-local (see "Keep reach
  machine-local"), so each machine already answers that question for itself by
  holding its own scope.

While the `sync` feature is switched off (spec [experimental-features](../experimental-features/spec.md) "Close the sync feature's surfaces"), the sync routes are closed and the convergence worker skips its rounds; the configured remote and the history stay untouched, and curation treats the vault as single-machine. Requirements below describe the feature while it is on.

## Requirements

### Requirement: Keep the remote a rendezvous, not a system of record
Convergence with a user-owned git remote is a bounded exception to the
principles' Local-First rule: the remote MUST be a
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
inside a nested git repository, so neither is ever pushed; what a skill's
scripts generate whenever they run — Python bytecode (`__pycache__/`, `*.pyc`,
`*.pyo`), log files (`*.log`), installed dependencies (`node_modules/`, `.venv/`)
and tool caches (`.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`) — and editor
and system litter are kept out by the repository's own exclude file.

#### Scenario: a symlink in the vault is skipped rather than published
- **GIVEN** a skill folder holding a symlink to a file outside the vault, and a nested git repository beside it
- **WHEN** the vault settles what is on disk
- **THEN** only the skill's own file is committed, and nothing is left pending

#### Scenario: Python bytecode beside a skill's scripts is not published
- **GIVEN** a skill whose `scripts/` holds a `__pycache__/` of `.pyc` files beside its scripts
- **WHEN** the vault settles what is on disk
- **THEN** the scripts are committed and the bytecode is not, and nothing is left pending

#### Scenario: logs and caches a skill's scripts write are not published
- **GIVEN** a skill whose folder holds a `run.log`, a `node_modules/` and a `.pytest_cache/` its scripts wrote
- **WHEN** the vault settles what is on disk
- **THEN** the skill's own files are committed and none of the generated ones are, and nothing is left pending

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

#### Scenario: a synced channel carries a secret reference, never a secret
- **GIVEN** a `channel` whose configuration cites a secret ref for its bot token or its app secret
- **WHEN** the channel's resource file is committed and pushed
- **THEN** the file holds the ref and no secret material, and the secret itself travels only as ciphertext under `secret/` when the remote carries secrets

### Requirement: Publish one descriptor per machine
One machine descriptor, `vault/machines/<machine_id>.json`, per machine MUST
travel (see "Write only this machine's descriptor").

#### Scenario: a round publishes this machine's descriptor and no other
- **GIVEN** three machines joined to one remote
- **WHEN** each runs rounds
- **THEN** the remote holds one descriptor per machine at `machines/<machine_id>.json`, each written only by its own machine

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
the running build, the knowledge files and this machine's absolute paths, so
two machines holding identical files render different bytes, each correct where
it is. **Both halves** are
derived: its master folder (`derived/skills/coffer-guide/`) and its resource
file (`derived/resources/skill/coffer-guide.json`). Every other skill is in the
vault. Memory partitions are derived the same way.

#### Scenario: a locally generated skill is neither published nor overwritten
- **GIVEN** Coffer's own skill and a person's imported skill
- **WHEN** each is filed
- **THEN** Coffer's own is stored under `derived/` and the person's under the vault, so only the person's can converge

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

### Requirement: Keep the pointer local
There is no pointer apart from the vault's own history. A round's base MUST be
the merge base of this vault's `HEAD` and the remote's tip, so what this machine
has absorbed is exactly what its history shares with the remote; nothing about
it travels as an input to the algorithm except the `last_converged_commit` a
returning machine reads back from its own descriptor.

#### Scenario: a round diffs from the shared history
- **GIVEN** two machines that converged, after which one deleted a document the other never touched
- **WHEN** the other machine, holding a new document of its own, runs a round
- **THEN** the merge from the shared history applies the deletion and publishes the new document

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

### Requirement: Derive machine identity from the host
`machine_id` MUST therefore be derived from the host, not generated by Coffer:
on macOS, `IOPlatformUUID` from `IOPlatformExpertDevice`; on Linux,
`/etc/machine-id` falling back to `/var/lib/dbus/machine-id`. It MUST be cached
in `daemon-config.json` and recomputed if that cache is lost.

#### Scenario: a machine id is derived from the host and cached
- **GIVEN** a Linux host whose `/etc/machine-id` is unreadable and whose `/var/lib/dbus/machine-id` holds an identifier
- **WHEN** the machine identity is resolved, and resolved again after `daemon-config.json` has lost its cached value
- **THEN** both times it is the id derived from the dbus identifier and it is marked as derived from the host
- **AND** the id is cached in `daemon-config.json`

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

### Requirement: Treat the machine name as a label
`machine_name` MUST be a label, not a key: chosen by the user, defaulting from
the hostname, changeable at any time at no cost, and stored inside the machine's
own descriptor so it syncs.

#### Scenario: renaming a machine costs nothing
- **GIVEN** a machine that has converged and appears in the registry,
- **WHEN** the user renames it,
- **THEN** nothing else in the vault is rewritten, and the new name reaches the
  other machines inside that machine's own descriptor on the next round.

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

### Requirement: Publish the key fingerprint in the descriptor
`key_fingerprint` MUST be the same short hash `GET /sync/key/fingerprint`
returns, so the machines table can state directly that another machine's
secrets cannot be decrypted here instead of the user comparing fingerprints
by hand.

#### Scenario: a peer holding another master key is flagged
- **GIVEN** a machine that has converged
- **WHEN** its descriptor is read and `GET /sync/key/fingerprint` is asked on that machine
- **THEN** the descriptor's `key_fingerprint` is the value the route returns
- **AND** the machines table says that a peer whose fingerprint differs from this machine's has secrets that cannot be decrypted here

### Requirement: Scope names agents only
`scope` MUST name agents, by uid, and nothing else — `{ agents: [...] }`.
`null` means every agent, a list restricts to it, `[]` matches nothing and is
dormant, and an unknown agent uid is legal and simply never matches. There MUST
be no machine axis: reach is machine-local (see "Keep reach machine-local"), so a
machine already names the resources it activates by *holding* that scope, and
machine ids inside the scope would record the same fact a second time with two
ways to disagree.

#### Scenario: a scope names agents and nothing else
- **GIVEN** scopes of `null`, a list of agent uids, an empty list, and a list naming an agent that does not exist
- **WHEN** each is matched against the registered agents
- **THEN** `null` matches every agent, the list matches exactly its agents, the empty list matches none, and the unknown uid matches nothing without being refused
- **AND** a scope that carries a machine axis is refused

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

### Requirement: Never apply the registry or the manifest
`machines/*.json` and `manifest.json` MUST NOT be projected into anything local —
the registry is read from the vault, and the manifest is metadata about the
layout — and MUST NOT count towards the deletion breaker.

#### Scenario: the registry and manifest are never applied
- **GIVEN** a diff that deletes thirty descriptors and the manifest
- **WHEN** the breaker counts its losses
- **THEN** it counts none

### Requirement: Re-run post-import hooks after applying
After a round applied files here, each kind's machine-local side effects MUST be
brought in step from the new state by one reconcile pass (see "Run the
reconciler once after a round that applied changes"); a round that applied
nothing runs none.

#### Scenario: a remote addition lands in the vault
- **GIVEN** another machine that pushed a knowledge document
- **WHEN** this machine's round pulls it
- **THEN** the document is in this vault and one reconcile pass has run

### Requirement: Let the fresher secret ciphertext win
Secret ciphertext MUST NOT reach a text merge or a question. A Fernet token
carries its encryption time in cleartext, so two ciphertexts for one ref can be
ordered without the key, and the **fresher encryption wins**. This rule applies
to `secret/**.enc` and to nothing else.

#### Scenario: the fresher secret ciphertext wins
- **GIVEN** one secret ref re-encrypted on both machines, the other machine's encryption being the fresher one
- **WHEN** the two meet in a round
- **THEN** both machines hold the fresher ciphertext, the round pulls it, and there is nothing to ask

### Requirement: Hold a round that would lose too much
A round that would **lose** more than **20%** of the documents in an area, or
**20 or more** documents in one area, MUST NOT proceed. Both thresholds are
fixed and MUST NOT be configurable, and nothing — no caller, no migration, no
relocation of the layout — may skip the guard rather than satisfy it. What
counts as a loss is "Count losses, not deletions".

#### Scenario: the guard trips above a fifth of an area or at twenty documents
- **GIVEN** the deletion guard at its fixed thresholds
- **WHEN** it scores a diff losing exactly 20% of an area, one losing more than 20%, and one losing 20 documents from a large area
- **THEN** the first does not breach and the other two do
- **AND** the thresholds the guard runs with are the published constants of 20% and 20

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
changes is a new item. The list MUST also carry an item while the remote is unreachable
(`sync_unreachable`), with its hand-off, so that problem the Sync page shows can be ignored. A
missing `git` MUST raise no sync item: it is reported by the CLIs item for `git`
([skill-manager](../skill-manager/spec.md) "List the commands Coffer itself runs"), which names the
vault's history as well as sync, and the Sync page's own `git_missing` problem has no ignore.
While `git` is missing the last round's problem MUST NOT be raised either.

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

### Requirement: Run an unattended rewriter on one owner machine
A worker that rewrites vault content with no human approving the diff is safe on
one machine and unsafe on several. Two machines rewriting one corpus each merge
the same pair of documents into a *different* result, and git merges that
cleanly — both agree the originals are deleted, the two results are additions at
different paths — so the vault holds the same content twice with nothing
reported as a conflict.

An unattended rewriter of synced vault content MUST name **one owner machine**,
MUST run only on the machine that setting names, and MUST be a clean no-op on
every other. The owner MUST be **synced state**, so every machine agrees who it
is; the knowledge **curation** pass is the case that exists today and its owner
travels in the `internal-engine` state document that already carries its switch.
If the owner machine is off, no pass happens, which is the accepted trade for a
background nicety. The retention worker is exempt: it prunes the audit log, MCP
invocation records and conversations, none of which sync.

#### Scenario: curation runs only on its owner machine
- **GIVEN** two converged machines with curation enabled and one of them named
  as the owner,
- **WHEN** the curation interval elapses on both,
- **THEN** a pass runs on the owner and is a no-op on the other, and the vault
  holds one rewritten document rather than two.

### Requirement: Report and change the rewriter's owner
The owner MUST be **reportable and changeable**, on the same terms as a
channel's machine binding ([channels](../channels/spec.md) "Bind each channel to the one machine that runs it"), because it is the same fact in
the same shape: one machine named in a document every machine holds.

- A surface MUST be able to say which machine owns the pass, and MUST
  distinguish **four** states — no owner named, this machine, another machine in
  the registry, and a machine **the registry does not hold**. Only the last is a
  fault, and it MUST be reported as one rather than folded into "runs
  elsewhere": the pass then runs on no machine at all, and no other part of the
  product says so.
- An **empty** registry MUST NOT produce that fault. A vault that has never
  converged has no registry to be absent from, and every single-machine install
  has an owner naming its own machine.
- A user MUST be able to take the pass over on this machine, and to clear the
  owner. Clearing returns the vault to running the pass wherever the setting is
  read, which is right for a vault down to one machine and wrong for one that
  still spans several, so it MUST be an explicit choice and never a repair
  anything performs on its own.
- The four states MUST be **derived from the setting and the registry**, not
  stored: the owner is one field, and a second field recording what that field
  means is a second thing to keep true.

This exists because the pass failed silently in exactly the way the requirement
above accepts and the one below does not. "If the owner machine is off, no pass
happens" ("Run an unattended rewriter on one owner machine") is the accepted
trade for a machine that will come back; an owner naming a machine that is
**gone** is not that trade, it is curation stopped everywhere with nothing to
say why and — until this requirement — no way to take it back short of editing
the database.

#### Scenario: an owner naming a machine that is gone is reported, not silent
- **GIVEN** an unattended rewriter whose owner setting names a machine the
  registry does not hold — a machine retired, reinstalled under a new identity,
  or never converged with,
- **WHEN** a surface reports where the pass runs,
- **THEN** it names that as a fault distinct from "runs on another machine",
  because the pass is running on none, and the user can take it over here.

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

### Requirement: Make no commit for a round with nothing to say
A round with nothing to say MUST produce **no commit**, and MUST still be
recorded as successful.

#### Scenario: an unchanged vault makes no commit
- **GIVEN** a configured remote whose last round is already pushed,
- **WHEN** a round runs and nothing in the vault or the remote has changed,
- **THEN** no commit is created and the round is recorded as successful.

### Requirement: Store home paths against a sentinel
Absolute paths under `$HOME` MUST be stored against a `${HOME}` sentinel and
expanded against each machine's home — in resource documents and in state
documents alike.

#### Scenario: a path under the home directory applies on a machine with a different home
- **GIVEN** a resource whose config names a path under this machine's home,
- **WHEN** the document reaches a machine whose home directory has a different
  name,
- **THEN** the stored document carries the `${HOME}` sentinel rather than either
  literal path, and the applied resource names the second machine's own home.

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
on the other machine from Settings › Security (see "Import a master key after showing whose key it is").

#### Scenario: the master key never enters the repository
- **GIVEN** a remote configured to carry secret ciphertext, and a key file beside the vault
- **WHEN** a round pushes
- **THEN** the remote holds the ciphertext files and no key material

### Requirement: Hand the push secret to git as a helper
The push secret MUST be resolved from the secret store at push time,
named by reference and never by value. It MUST NOT enter the repository's git
config, MUST NOT appear in a command line, and MUST be redacted from any
recorded error. It MUST reach git as a **credential helper**, which every git
consults before it would prompt, and MUST NOT be handed over through a prompt
mechanism: a prompt path is optional and platform-dependent — macOS's own git
ignores `GIT_ASKPASS` entirely — so a secret delivered that way is not
delivered at all on the platform Coffer ships a desktop app for. That failure is
invisible by construction while a credential helper in the user's own git
configuration happens to answer instead, and this layer pins that configuration
away on purpose, so there is nothing left to fall back on when it stops.

#### Scenario: the push secret never reaches the repository
- **GIVEN** a configured remote with a push secret,
- **WHEN** a round pushes,
- **THEN** the secret is absent from the repository's git config, from the
  git process's arguments, and from any recorded error text or audit payload,
- **AND** it still authenticates, because it reaches git as a credential helper
  reading it from the environment rather than as an answer to a prompt.

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

### Requirement: Fold consecutive quiet rounds into one row
Consecutive rounds that changed **nothing** — no documents either way, no join,
no failure, no locked ref — MUST be folded into one row reporting the span and
the count. They are the majority, and one row each buries everything that
matters; they MUST NOT be dropped, because they are the only evidence that a
vault which stopped converging on Tuesday is not simply a vault with nothing to
do. A round that failed once is noise; a round that has failed every hour since
Tuesday is the answer.

Repeats that are not quiet MUST fold the same way, by outcome: consecutive
rounds that **failed**, and consecutive rounds **held** for confirmation, each
fold into one counted row, because an expired secret is ten identical
failures by morning and a held round is re-raised every hour until it is
answered — neither is more true for being printed ten times. A round that
applied or published documents MUST NOT fold, however many like it came before,
and rounds of different outcomes MUST NOT fold together. A lone round MUST stay
a row of its own. The **newest** round MUST never be folded: it is the state the
vault is in now and the only round that may carry Undo or a hold's answers.

#### Scenario: consecutive quiet rounds fold into one counted row
- **GIVEN** a runs history holding a stretch of consecutive rounds that changed nothing
- **WHEN** the Status tab renders
- **THEN** the stretch is one row that reports its span and how many rounds it stands for
- **AND** every round in it is still reachable from that row

#### Scenario: repeated failures fold into one row and the newest round stands alone
- **GIVEN** a runs history whose newest three rounds failed the same way, preceded by a round that published a document
- **WHEN** the rounds table's rows are built
- **THEN** the newest failure is a row of its own, the two failures before it are one row counting two, and the round that published is a row of its own
- **AND** a stretch of consecutive rounds held for confirmation folds the same way beneath a newer round

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

### Requirement: Refuse a newer-layout remote and replace an older one
The remote's `manifest.json` carries the vault layout's `schema_version`. A
round or a join SHALL refuse a remote at a newer layout (`remote_too_new`),
leaving this vault untouched: the person upgrades this machine. A round or a
join that meets a remote at an older layout SHALL replace it with this vault,
joined or not — never convert it. The push is a fast-forward of one commit
whose tree is exactly this machine's content, with this machine's commit and
the old tip as parents, so the old history stays reachable in git. The files
only the old remote had go away on purpose, so the outgoing deletion breaker
does not apply; the plaintext check still does, and a plaintext finding refuses
with the remote keeping its old tip. The machine is marked joined and the round
records `join: "replace"`. The join preview of such a remote (kind `REPLACE`)
SHALL list what goes up by area, the files that go away (the first 100, with the
exact total), who pushed the old tip and when, and that machines still on the
older layout must upgrade.

#### Scenario: a remote at a newer layout is refused
- **GIVEN** a remote whose manifest names a newer layout
- **WHEN** a round runs against it
- **THEN** the round ends `remote_too_new`
- **AND** this vault's `HEAD` is unchanged

#### Scenario: a remote at an older layout is replaced by this vault
- **GIVEN** a remote at an older layout holding a file this vault does not have, and an upgraded machine that has not joined
- **WHEN** its round runs
- **THEN** the round ends `pushed` with `join: "replace"`, and the new remote tip has the old tip as an ancestor
- **AND** the file only the old remote had is gone from the new tip and listed as removed, this vault's files are on it, and the machine is joined
- **AND** the next round has nothing to do

#### Scenario: the join preview of an older remote lists what goes away
- **GIVEN** a remote at an older layout and a machine that has not joined
- **WHEN** the join is previewed, and then confirmed
- **THEN** the preview is of kind `REPLACE` with nothing pulled, the old tip, what goes up and the files that go away with their exact total
- **AND** confirming replaces the remote, which is then at this vault's layout

#### Scenario: code that assigns a secret-named variable is not a plaintext secret
- **GIVEN** a script with `token = m.group(0)`, `user, _, password = creds.partition(":")` and `password=password,`
- **WHEN** it is read for plaintext secrets
- **THEN** nothing is reported
- **AND** a quoted literal assigned to `password`, or a `.env`-style `API_KEY=` value, still is

#### Scenario: replacing an older remote still refuses a plaintext secret
- **GIVEN** a remote at an older layout and a vault holding a plaintext credential
- **WHEN** a round runs
- **THEN** the round ends `plaintext_found`
- **AND** the remote keeps its old tip

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

### Requirement: Run the reconciler once after a round that applied changes
What another machine changed is this machine's warrant to bring its own side
effects in step — an agent's native configuration, Coffer's MCP entries, skill
deliveries. After a round that applied files here, one reconcile pass SHALL run
with the import's warrant (see [resource-framework](../resource-framework/spec.md)
"Converge what Coffer writes outside its database with one reconciler"); a round
that applied nothing MUST NOT run one. A failed pass is logged and the round
stands. The round MUST hold the reconciler from its first git call to the end of
that pass, so a pass its own checkout hinted cannot judge the vault before the
import pass and undo what another machine changed (a provider switch).

#### Scenario: a round that applied changes runs one reconcile pass
- **GIVEN** a joined machine and another machine that pushed a knowledge document
- **WHEN** this machine's round pulls it, and a further round has nothing to do
- **THEN** exactly one reconcile pass ran, after the first round
- **AND** with the real reconciler running, no hinted pass ran before the import pass

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

### Requirement: Report the refs a key cannot open as locked
A machine holding ciphertext its master key cannot open MUST report those refs
**locked** rather than failing decryption silently: importing a key MUST answer
which refs it still cannot open, and the Sync page shows the refs this machine
cannot decrypt. A key file that is blank or not a key MUST be refused.

#### Scenario: credentials this machine cannot decrypt are reported locked
- **GIVEN** a machine holding ciphertext written under a master key it does not hold
- **WHEN** a master key is imported that still does not open it
- **THEN** the import names those refs as still locked, and a blank or malformed key is refused

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

### Requirement: Refuse to push a plaintext secret
Before a round pushes — a round that merged, a push with nothing to pull, or a join — it MUST read
every file version the push would publish: each blob reachable from the commit being pushed and
not from the remote's head, from every commit in between. It reads them for an assignment whose name says secret and for the well-known token shapes.
An unquoted value holding call, index or list punctuation (`(`, `)`, `[`, `]`, `,`, `;`) is code,
not a secret, so `token = m.group(0)` or `password=password,` is not reported.
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
- **THEN** its card lists each file, line and key a file still holds, with the agent hand-off that moves each value into a secret, and no Retry
- **AND** Push anyway runs only after a confirmation that says it is recorded in the audit log

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
- **THEN** the remote has the same URL, branch, secret name, interval and secret setting, the machine is still joined, and the stopped round is waiting again
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

### Requirement: Apply knowledge and skill file changes
What a round applies MUST be a checkout of the merged tree: an added or modified file
under `knowledge/`, `skills/`, `resources/`, `state/`,
`secret/` or `machines/` is written, and a deleted one removed, in the one
compare-and-swap step that refuses to overwrite a person's unsettled edit (see
"Never overwrite a person's unsettled edit"). Stores that read the vault reload
from the new `HEAD`, so an arriving resource file is a resource and an arriving
state document is in effect without any per-kind import step.

#### Scenario: an arriving file is written and a deleted one removed
- **GIVEN** two machines that each wrote a knowledge document
- **WHEN** both run rounds
- **THEN** each machine holds the other's document with the same bytes

### Requirement: Show what a round changed in each file
The round drawer MUST let a person open any file the round **applied** here or
**pushed** and read what changed in it, line by line, without storing anything
new: `GET /api/v1/sync/runs/{id}/diff?path=<file>&side=applied|pushed` MUST
compute a unified diff from the vault's git history. For `applied` it compares
this machine's version before the round with its version after; for `pushed` it
compares the remote tip the push went on top of with the pushed commit. The
response MUST carry a `kind`: `text` with the diff and its added and removed line
counts; `secret` for a file under `secret/`, with no content at all, not even
ciphertext; `binary` for a file that is not text; `too_large` for a file or diff
over the size cap. A `path` the round did not list on that side MUST be refused
(`SYNC_ROUND_FILE_NOT_LISTED`, 404), so the endpoint never reads an arbitrary
file; a round whose commits are no longer in the vault MUST answer
`SYNC_ROUND_DIFF_UNAVAILABLE` (409). The drawer MUST show each file as a row
that expands to the diff (old and new line numbers, added and removed lines
tinted) with the counts beside the file once loaded, and a plain message for
each non-text kind. Pulled commits MUST NOT carry a diff.

#### Scenario: an applied file shows its line-by-line diff
- **GIVEN** a round that applied another machine's edit to a knowledge document
- **WHEN** the file is asked for with `side=applied`
- **THEN** the diff holds the removed and the added lines of that edit and their counts

#### Scenario: a pushed file shows its line-by-line diff
- **GIVEN** a round that pushed this machine's edit to a knowledge document
- **WHEN** the file is asked for with `side=pushed`
- **THEN** the diff is against the version the remote held before the push

#### Scenario: a secret file shows no content
- **GIVEN** a round that pushed an encrypted file under `secret/`
- **WHEN** the file is asked for
- **THEN** the answer is `kind: "secret"` with no diff, and the drawer says the contents are not shown

#### Scenario: a path the round did not touch is refused
- **GIVEN** a round and a vault file it neither applied nor pushed
- **WHEN** that file is asked for on either side
- **THEN** the answer is `SYNC_ROUND_FILE_NOT_LISTED`

#### Scenario: expanding a file in the drawer shows its diff
- **GIVEN** the drawer of a round that applied a file
- **WHEN** the file's row is expanded
- **THEN** its diff rows and its added and removed counts appear

### Requirement: Show a plaintext finding in its file
The Sync page MUST let a person read each place a `plaintext_found` round
listed in its file, so they can judge whether it is a secret, without Coffer
ever returning the value. `GET /api/v1/sync/plaintext/context?path=<file>&line=<n>`
MUST compute, from the file version the last round found the value in and
without storing anything: the flagged line with up to three lines either side,
each with every plaintext value on it masked; whether the remote already holds
the file (`added` or `modified`) and the flagged line; and for a `modified`
file within the size cap, its unified diff against the remote's copy with
every line masked the same way, and its added and removed counts.

Masking MUST replace every character of a value with `•`, keeping the line's
length, except a well-known token format's public prefix (`ghp_`,
`github_pat_`, `sk-`, `xoxb-` and its siblings, `AKIA`) or a URL's scheme.
Each masked value MUST carry its place on the line, the name it is assigned
to, and its shape: its length, which kinds of character it holds (lower,
upper, digit, symbol), that prefix, and a hint — `reference` for names joined
by dots, `placeholder` with the placeholder word it holds, `repeated` for one
or two characters over and over. No other character of a value MAY appear in
the response, and the response MUST NOT be stored, logged or audited.

When the last round is not `plaintext_found` the request MUST be refused with
`SYNC_NO_PLAINTEXT_FOUND` (409); a place the round did not find in a current
file MUST be refused with `SYNC_PLAINTEXT_NOT_LISTED` (404), so the route never
reads an arbitrary file. The plaintext card MUST show each place as a row that
expands to the masked lines — line numbers, the flagged line tinted, each
masked value highlighted — with whether the file is new or changed, whether the
line is already on the remote, the value's shape in words, and for a changed
file the masked diff behind "Show changes".

#### Scenario: a finding is shown in its file with the value masked
- **GIVEN** a round stopped as `plaintext_found` on line 4 of a new knowledge document, with another value on line 5
- **WHEN** the place's context is asked for, before and after the round, and for a line the round did not find
- **THEN** before the round it is `SYNC_NO_PLAINTEXT_FOUND`, and after it lines 1 to 7 come back with both values masked to `•` of the same length, the file `added`, and line 4's value keyed `DB_PASSWORD` with its length and kinds of character
- **AND** neither value appears in the response, and a line the round did not find is `SYNC_PLAINTEXT_NOT_LISTED`

#### Scenario: a finding in a file the remote holds shows its masked change
- **GIVEN** a document the remote already holds with the line `const token = process.env.ORDERS_TOKEN`, to which this machine adds a line with a GitHub token
- **WHEN** a round stops as `plaintext_found` and each place's context is asked for
- **THEN** the old line is `modified`, already on the remote, and hinted as a code reference, and the token keeps only `ghp_` visible
- **AND** the masked diff adds one line and carries no value

#### Scenario: the Sync page opens each place to its masked lines
- **GIVEN** the Sync page with a `plaintext_found` problem
- **WHEN** a place is opened
- **THEN** it shows the masked lines with the flagged one marked, whether the file is new or changed, and the value's shape in words
- **AND** for a changed file "Show changes" shows the masked diff
