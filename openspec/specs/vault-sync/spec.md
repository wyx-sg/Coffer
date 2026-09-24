# Vault Sync

## Purpose

Keep one vault across the user's own machines by converging each of them with a
git repository the user owns. A developer works the same project from a laptop
and a desktop, and both produce vault state: knowledge files, skills, MCP
registrations, agent configuration, credentials. Without convergence each
machine is an island, and the fix — export here, carry the directory, import
there — is a chore nobody performs often enough for the two to stay alike. A
background worker commits what this vault holds, lets git three-way-merge it
against what the remote holds, and applies the resulting difference back —
deletions included. Background and alternatives in
[Vault Sync](../../../docs/decisions/vault-sync.md).

**This spec also owns machine identity.** The name says "sync", but
`machine_id` — how it is derived, that it survives a reinstall, what travels in
its place, and the registry that lists it — is specified here and nowhere else.
Other specs key on it: a channel's machine binding in spec
[channels](../channels/spec.md) and the curation owner in spec
[knowledge](../knowledge/spec.md) both name a `machine_id` this spec defines.

Vocabulary. A **vault document** is the serialized form of one piece of vault
state at one path in the working tree: a knowledge file, a skill file, a
resource YAML, a state YAML, a credential blob, a machine descriptor. A
**converge round** is one full cycle of the seven round steps. The **retry set**
is the paths the working tree holds that this vault has not absorbed, stored
locally beside the pointer. A **machine** is one installation of Coffer.

Conversations and the audit log are excluded deliberately: they are records of
what happened *on a machine*, and a merged history of two machines' activity
would be a different feature with a different shape (see `/activity`).

Out of scope:

- **Local export and import.** Deleted with this spec. Writing a bundle to a
  directory and reading one back is a wholesale overwrite with no base — the
  operation that caused the 2026-07-10 incident — and it has no place beside the
  diff-based apply. The needs it served are met without it: a new machine runs
  `coffer sync adopt`, an offline medium is a `file://` remote on a USB drive,
  and handing a copy to someone else is `git clone ~/.coffer/sync`.
- **More than one sync remote.** One rendezvous is what "one vault" means.
- **A hosted sync endpoint.** Would require a further constitutional amendment.
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

## Requirements

### Requirement: Keep the remote a rendezvous, not a system of record
Convergence with a user-owned git remote is a bounded exception to the
constitution's local-first principle (0.6.0): the remote MUST be a
**rendezvous, not a system of record**. Every machine's vault MUST stay
complete and authoritative, so the remote can be deleted and rebuilt from any
single machine without losing anything.

#### Scenario: a remote rebuilt from one machine loses nothing
- **GIVEN** a machine that has converged its vault with a remote
- **WHEN** the remote is replaced by an empty repository and the machine converges with it again
- **THEN** the new remote holds every document the machine's vault holds
- **AND** the machine's vault is unchanged

### Requirement: Converge knowledge files and the skill store
The markdown files under `~/.coffer/knowledge/<collection>/` and the master
skill store under `~/.coffer/skills/` MUST converge, mirrored as regular files —
except a folder in them that is derived output, which is "Withhold derived
output in both halves".

#### Scenario: a local-only document survives a round
- **GIVEN** a knowledge document this vault created and the remote has never
  seen,
- **WHEN** a round runs,
- **THEN** the document is still present locally and is now published to the
  remote.

### Requirement: Skip symlinks and nested repositories
Outbound, a symlink MUST be skipped rather than followed — its target is not
vault content, and a link to a file outside the vault would otherwise be
published — and anything under a nested `.git` directory MUST be skipped as
another repository's internals. What was skipped MUST be logged once per round.
Inbound, a symlink the working tree holds MUST be refused rather than read into
the vault.

#### Scenario: a symlink in the vault is skipped rather than published
- **GIVEN** a knowledge collection holding a symlink to a file outside the
  vault,
- **WHEN** a round serializes the vault,
- **THEN** the working tree holds no copy of that file, the link is not
  followed, and the round logs once what it skipped.

### Requirement: Converge resource definitions as serialized documents
`mcp_server`, `agent`, `skill`, `knowledge`, `provider` and `channel`
definitions MUST converge, serialized to text from SQLite, which stays the
system of record. A resource document is identity, description and config —
what the resource *is*. What it reaches is not in it (see "Keep reach
machine-local").

#### Scenario: a resource document is identity, description and config
- **GIVEN** a registered resource with a description, a config and a reach of its own
- **WHEN** it is serialized into a resource document
- **THEN** the document holds its identity, its description and its config
- **AND** it holds nothing else — no `enabled` flag and no `scope`

### Requirement: Key resource documents by uid
A resource document MUST be stored at a path keyed by the resource's **uid**,
and MUST carry that uid inside it. A machine receiving a document MUST match it
to a local resource by uid, and MUST create a missing one *at that uid* rather
than minting its own — two machines holding one resource hold one identity for
it.

Keying the path by the name made a rename a deletion beside an addition, and
the receiving machine could not tell that from a delete-and-create: it ran the
full deletion, which released the credential nothing else cited and dropped the
kind-owned state the row cascaded to. The name lives inside the document, where
changing it is a modification of one file
([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).

#### Scenario: a rename travels as a rename
- **GIVEN** a resource that both machines hold, whose config cites a credential,
  and which the receiving machine has given a reach of its own,
- **WHEN** the user renames it on one machine and the two converge,
- **THEN** the other machine holds the same resource under the new name — not a
  new resource — with its credential still in the store, its kind-owned state
  intact, and the reach that machine set for itself unchanged,
- **AND** this holds whichever way the new name sorts against the old one,
  because the ordering of the paths a round applies must not decide whether a
  rename is lossless.

### Requirement: Let a kind withhold its own rows
Every kind MUST travel **except one it declares for itself**: a kind sets
`converges=False` when its rows are derived on each machine rather than
authored by the user, and `memory` is the only kind that does
([memory](../memory/spec.md) "Keep the memory tree derived and local"). The rule MUST live on the kind rather than as a list in the
sync layer; the exporter MUST withhold such rows and the applier MUST ignore
such a document, so a machine on an older build cannot deliver one either. A
kind that travels MAY additionally declare that one of its **rows** does not, on
the same terms and for the same reason (see "Withhold derived output in both
halves").

#### Scenario: a kind that declares itself derived never reaches the tree
- **GIVEN** a vault with `memory` partition rows, whose kind declares
  `converges=False`,
- **WHEN** a round exports the vault,
- **THEN** no `resources/memory/*.yaml` document is written, and a document of
  that kind arriving from the remote is ignored rather than applied.

### Requirement: Carry a channel's document but not its adapter
A `channel` document MUST travel while its adapter does not. A channel is an
inbound surface — a polled bot or a held websocket connection, each of which a
platform serves to one consumer at a time — so the document names the one machine that may answer: `runs_on`, the
`machine_id` whose daemon starts the adapter ([channels](../channels/spec.md) "Bind each channel to the one machine that runs it"). The other
machine therefore holds the channel's configuration, its credential references
and its pairings, so taking over a bot is a rebind rather than a
re-registration.

A channel's machine binding is not the retired machine axis of `scope` coming
back. Reach is "which agents, here" — a local answer each machine gives itself.
The binding is "which machine runs the adapter" — one answer the machines
share, so it lives in the channel's config and travels with it. A binding
records a fact no machine can state alone, because it is about which of them
acts.

#### Scenario: a channel document names the machine that runs it
- **GIVEN** a `channel` configured on one machine and bound to it
- **WHEN** a round exports the vault
- **THEN** the working tree holds a document for the channel like any other resource
- **AND** that document names the bound machine's `machine_id` as the one that runs its adapter

### Requirement: Converge shared state areas
Module-owned shared state areas that belong to the vault rather than to one
machine MUST converge: MCP capability preferences, internal engine settings,
the agent plugin inventory, and channel peer pairings.

#### Scenario: each shared state area reaches the working tree
- **GIVEN** a vault holding a non-default choice in a shared state area
- **WHEN** a round exports the vault
- **THEN** the working tree holds that area's document under `state/<area>/`
- **AND** the export counts it under that area

### Requirement: Carry channel pairings as platform identity
Channel peer pairings MUST travel as **platform identity** — chat id, sender
id, display name and pairing time, keyed by the channel's uid — because a channel that moved to
another machine without its pairings would make the owner re-pair from their
phone on every rebind.

#### Scenario: a channel's pairings travel with it
- **GIVEN** a paired `channel` on one machine,
- **WHEN** the two machines converge and the channel is rebound to the other,
- **THEN** the owner's pairing is present on the machine that now runs it and no
  re-pairing is asked for, and the conversation pointer each machine holds is
  its own.

### Requirement: Keep the active conversation pointer local
The active conversation pointer MUST NOT travel, and neither MUST the agent a
chat's thread has stuck to. Conversations are machine-local, and a published
pointer would name a conversation the other machine does not have; the sticky
agent names an agent installed on this machine, which the other machine may not
have either.

#### Scenario: the active conversation pointer is not published
- **GIVEN** a paired chat whose pairing has an active conversation on this machine
- **WHEN** the pairings state area is exported
- **THEN** the exported document carries the chat's platform identity
- **AND** it names no conversation

### Requirement: Record plugins as an inventory, not a replicator
The plugin inventory MUST be an **inventory, not a replicator**: it records
which plugins each agent has on each machine and MUST write nothing into any
agent's configuration.

#### Scenario: an arriving plugin inventory writes nothing into an agent
- **GIVEN** a plugin inventory document another machine published
- **WHEN** this machine applies it
- **THEN** no agent's configuration is written
- **AND** the apply reports nothing to do

### Requirement: Carry credentials as ciphertext only
Credentials MUST travel as Fernet **ciphertext only**, and only when the remote
is configured to carry it.

#### Scenario: a synced channel carries a credential reference, never a secret
- **GIVEN** a `channel` whose configuration cites a credential ref for its bot
  token or its app secret,
- **WHEN** a round exports the vault,
- **THEN** the channel's document in the working tree holds the ref and no
  secret material, and the secrets themselves appear only as Fernet ciphertext
  and only when the remote is configured to carry credentials.

### Requirement: Publish one descriptor per machine
One machine descriptor document per machine MUST travel (see "Write only this
machine's descriptor").

#### Scenario: a round publishes this machine's descriptor and no other
- **GIVEN** a working tree that already holds another machine's descriptor
- **WHEN** this machine exports its vault
- **THEN** the tree holds this machine's descriptor at `machines/<machine_id>.yaml`
- **AND** the other machine's descriptor is left exactly as it was

### Requirement: Keep machine-local state out of the repository
Logs, `coffer.db` itself, `daemon-config.json`, PID files, port allocations,
chat history, conversations, the audit log, MCP invocation records, the whole of
`~/.coffer/memory/` **and the `memory` partition rows derived from it**, and any
runtime artifact MUST stay machine-local. The master key MUST **never** be
written into the repository (see "Never write the master key into the
repository").

#### Scenario: machine-local files never reach the working tree
- **GIVEN** a vault whose `~/.coffer` holds `coffer.db`, `daemon-config.json`, a log file and a memory store beside its knowledge
- **WHEN** a round exports the vault
- **THEN** the working tree holds the knowledge document
- **AND** it holds none of the database, the daemon configuration, the log or the memory store

### Requirement: Keep reach machine-local
**Reach** — a resource's `enabled` flag and its `scope` — is machine-local and
MUST NOT travel in either direction. They read like two fields but they are one
thing, written by one control: whether this resource is live here, and for
which agents. Reach is set on the machine it applies to and each machine sets
its own. Publishing it would let one machine silently re-answer a question
another machine had already answered for itself — the laptop that deliberately
left a server dark would find it live again after the desktop's next round,
with nothing in the history that reads like a decision anyone made.

#### Scenario: reach stays on the machine it was set on
- **GIVEN** an `mcp_server` present on both machines, disabled on one of them and
  restricted to a single agent on the other,
- **WHEN** the two machines converge,
- **THEN** each machine still holds the reach it was given — the disabled one is
  still disabled, the restricted one still restricted — and a later edit to the
  server's configuration on either machine reaches the other without carrying
  its reach along.

### Requirement: Withhold derived output in both halves
**Derived output MUST NOT converge, in either half.** A resource whose bytes
each machine regenerates for itself — from material that already converges
plus that machine's own machine-local state — MUST be withheld from the tree and
MUST be ignored when a document for it arrives. This is the rule of "Let a kind
withhold its own rows" at the granularity of one **row**: a kind that otherwise
converges MUST be able to declare that a particular row does not, and that
row declaration MUST live on the kind rather than as a name the sync layer
recognises. The master-folder half is a set of tree paths held in the sync
layer, because the sync layer may not import the kind; a contract test MUST pin
that set to the kind's own spelling of the name, so the two cannot drift apart
in silence. The exporter and the applier MUST both consult both halves.

Coffer's own generated skill `coffer-guide` is the case this exists for. Its
text is rendered locally from the running build, the knowledge files (which
converge on their own) and **which collections this machine has enabled** — and
`enabled` is reach, which "Keep reach machine-local" keeps machine-local. So two
machines holding identical files still render different bytes, each correct
where it is. Converging it had each round overwrite the other machine's master
folder and its resource row (whose `version_hash` is that folder's digest), the
overwritten machine re-render at its next boot or curation pass, and the
exchange repeat: a commit and an audit event per tick on both machines, forever,
over an artifact neither machine reads from the other. **Both halves MUST be
withheld**: the master folder under `skills/`, which "Converge knowledge files
and the skill store" otherwise mirrors, and the resource document, which
"Converge resource definitions as serialized documents" otherwise publishes.

#### Scenario: a locally generated skill is neither published nor overwritten
- **GIVEN** two machines holding the same knowledge files, one with a
  collection enabled and the other with it disabled, so each has rendered its
  own `coffer-guide` master folder and registered its own `skill:coffer-guide`
  row,
- **WHEN** both converge, and then converge again,
- **THEN** neither machine's `SKILL.md` or row has been changed by the other,
  the remote carries neither `skills/coffer-guide/` nor
  `resources/skill/coffer-guide.yaml`, the second round publishes and applies
  nothing, and the knowledge files and an ordinary imported skill converge as
  usual.

### Requirement: Leave the paths of withheld derived output inert
Withholding derived output MUST NOT publish its **absence**. A bundle written by
an earlier build already carries those paths, and an export that converged them
away would stage a deletion — the one change every machine acts on. A machine
still running that earlier build has no rule to protect it and would take the
deletion as leave to unlink its own live copy, and the resource document's
deletion would reach the row's own delete guard, be refused, and be re-refused
on every tick because a round re-derives its diff (see "Release a hold whose
diff no longer breaches"). So the paths MUST be left exactly where they are: not
published, not applied, not deleted, and never counted by the deletion guard.
They become inert rather than tidy, which is the cheaper of the two mistakes.

This is the opposite treatment from a withheld **kind** (see "Let a kind
withhold its own rows"), whose documents are cleared on purpose — those stand on
nothing at the other end, while a withheld row's document stands on a master
folder that machine wrote itself and still delivers.

#### Scenario: a derived document an older build published is left in place
- **GIVEN** a remote holding the generated `coffer-guide` skill's folder and resource document, published by an earlier build
- **WHEN** a machine on this build converges with it
- **THEN** those paths are neither applied to this vault nor deleted from the tree
- **AND** this machine's own generated skill is untouched and no deletion of it is published

### Requirement: Allow at most one user-owned sync remote
A vault MUST have **at most one** sync remote: a git repository the user owns,
configured with a URL, a branch, a push credential reference, an interval, and
whether credential ciphertext rides along. Sync MUST be disabled until the user
configures it.

#### Scenario: sync stays off until a remote is configured
- **GIVEN** a vault with no sync remote configured
- **WHEN** a round is requested
- **THEN** the round is reported as disabled and nothing is committed or pushed
- **AND** configuring a remote a second time replaces the first rather than adding another

### Requirement: Refuse a URL or branch git would read as an option
The URL and the branch become arguments to `git`, so neither MAY begin with `-`
(git would read it as an option, and `--receive-pack=<cmd>` is a command) and
the branch MUST pass `git check-ref-format --branch`. Both MUST be refused at
the API, at the CLI and again by the domain object. The git adapter MUST fence
every positional argument git lets it fence with `--` and MUST push an explicit
`refs/heads/` refspec.

#### Scenario: a remote URL or branch that git would read as an option is refused
- **GIVEN** a remote URL beginning with `-`, or a branch beginning with `-` or failing `git check-ref-format --branch`
- **WHEN** the remote is configured over REST, from the CLI, or built as the domain object
- **THEN** each is refused and no remote is stored
- **AND** a remote that is accepted is pushed to through an explicit `refs/heads/<branch>` refspec

### Requirement: Keep the working tree outside the vault
The working tree defaults to `~/.coffer/sync`. Every round mirrors the vault
into it and may `reset --hard` it, so it MUST NOT be at, inside or above any
vault directory (knowledge, skills, memory), nor at or above `~/.coffer` itself;
inside `~/.coffer` only the default location is accepted, and a relative path
MUST be refused. The working tree is set over REST (`PUT /api/v1/sync/remote`
`worktree_path`) and on the command line (`coffer sync remote set <url>
--worktree <path>`), and both refuse the same paths with the same reason.

#### Scenario: a working tree pointed inside the vault is refused
- **GIVEN** a request to configure the working tree at a knowledge or skills
  directory, or at `~/.coffer` itself, or at a relative path,
- **WHEN** the remote is configured with that working tree over REST, or with
  `coffer sync remote set <url> --worktree <path>`,
- **THEN** each is refused with the reason named — a 422 over REST, the route's
  message and the invalid-input exit code on the command line — and no remote is
  stored and no repository is created.

### Requirement: Adopt an existing repository only when it is ours
An existing repository at that location MUST be adopted with its history intact
— unless it has commits and an `origin` that is neither the configured remote
nor one Coffer created, in which case it is someone's checkout of something else
and MUST be refused rather than repointed.

#### Scenario: a foreign checkout at the working tree is refused, not repointed
- **GIVEN** a repository at the working tree location with commits and an `origin` pointing at another remote Coffer did not create
- **WHEN** the working tree is prepared for the configured remote
- **THEN** it is refused and its `origin` is left pointing where it did
- **AND** an existing repository whose `origin` is the configured remote is adopted with its history intact

### Requirement: Mark and repoint a working tree Coffer made
A tree Coffer made MUST be marked in its local git config and MAY be repointed
when the remote's URL changes.

#### Scenario: a working tree Coffer made follows a new remote URL
- **GIVEN** a working tree Coffer created for one remote
- **WHEN** the remote's URL is changed and the working tree is prepared again
- **THEN** the tree's `origin` names the new URL

### Requirement: Keep the pointer local
The **pointer** is the commit this vault has provably absorbed, stored locally.
It is the base of every diff and the only machine identity the algorithm needs,
and it MUST NOT travel as an input to the algorithm.

#### Scenario: a round diffs from the pointer stored on this machine
- **GIVEN** a machine that has converged more than once today, so the commit its published descriptor names is older than its stored pointer
- **WHEN** a round runs with one new document in the vault
- **THEN** the round publishes that one document and nothing it published before
- **AND** the stored pointer advances to the round's commit

### Requirement: Keep machine identity across reinstalls
`machine_id` MUST survive reinstalling and uninstalling Coffer. A machine that
comes back under a new identity becomes a ghost: it rejoins as a stranger, its
old descriptor lingers in the registry with nobody to update it, and anything
that named it — the curation owner, its own recovered pointer — silently stops
meaning this machine.

#### Scenario: a machine identity survives reinstalling Coffer
- **GIVEN** a machine whose `~/.coffer` is deleted and Coffer reinstalled, on a
  host that exposes a stable identifier,
- **WHEN** it adopts the remote again,
- **THEN** it returns under the same machine id and its descriptor is updated
  rather than duplicated, so it rejoins as itself rather than as a stranger.

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
deleting `~/.coffer`, and the machine surface MUST say so, because such a
machine reappears under a new id and the old descriptor must be removed by
hand.

#### Scenario: a machine with no host identifier falls back and says so
- **GIVEN** a host that exposes no readable identifier
- **WHEN** the machine identity is resolved twice
- **THEN** a UUID is stored at `~/.coffer/machine-id` with mode `0600`, both resolutions give the same id, and the identity is marked as not derived from the host
- **AND** the machines table warns that deleting `~/.coffer` makes this a new machine

### Requirement: Publish only a hash of the host identifier
The raw host identifier MUST NOT be written into the repository — it is a
hardware identifier. What travels MUST be `sha256("coffer-machine:" + raw)`
truncated to 16 hex characters.

#### Scenario: the raw host identifier never reaches the repository
- **GIVEN** a machine whose id is derived from a host identifier,
- **WHEN** it publishes its descriptor,
- **THEN** the working tree holds only the truncated hash of that identifier and
  the raw value appears nowhere in the repository.

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
Each machine MUST write exactly one document, at `machines/<machine_id>.yaml`,
and MUST write no other machine's. Every machine owning a disjoint path is what
makes these documents unable to conflict.

#### Scenario: the machine registry shows every machine and cannot conflict
- **GIVEN** two machines that have both converged,
- **WHEN** the machines table is read on either,
- **THEN** it lists both with their names, last converged day and whether each
  one's key matches this machine's, marks the local one, and the working tree holds one descriptor
  per machine with no merge conflict between them.

### Requirement: Derive the registry from the descriptors
The registry MUST be whatever `machines/*.yaml` currently holds — a derived
view, never a synced table of its own.

#### Scenario: a retired machine leaves the registry with its descriptor
- **GIVEN** two machines that have both converged
- **WHEN** one retires the other
- **THEN** the other machine's descriptor is gone from the tree and the registry no longer lists it
- **AND** nothing else in the vault changes

### Requirement: Carry the descriptor fields
A descriptor MUST carry `name`, `os`, `hostname`, `coffer_version`,
`last_converged_on`, `last_converged_commit`, `key_fingerprint`, and the names
of the agents registered on that machine.

#### Scenario: a descriptor carries what the machines table shows
- **GIVEN** a machine with agents registered and a master key
- **WHEN** it converges and publishes its descriptor
- **THEN** the descriptor carries its name, operating system, hostname, Coffer version, the day and commit it last converged, its key fingerprint and the names of its agents

### Requirement: Publish this machine's pointer in its descriptor
`last_converged_commit` MUST publish this machine's pointer, so the remote can
hand it back to a machine that lost it (see "Recover a returning machine's base
from its descriptor").

#### Scenario: a descriptor publishes the pointer this machine reached
- **GIVEN** a machine that has converged before and holds a pointer
- **WHEN** a later round publishes its descriptor
- **THEN** the descriptor names the pointer this machine held when it published
- **AND** that commit is in the remote's history, so the remote can hand it back

### Requirement: Publish the key fingerprint in the descriptor
`key_fingerprint` MUST be the same short hash `GET /sync/key/fingerprint`
returns, so the machines table can state directly that another machine's
credentials cannot be decrypted here instead of the user comparing fingerprints
by hand.

#### Scenario: a peer holding another master key is flagged
- **GIVEN** a machine that has converged
- **WHEN** its descriptor is read and `GET /sync/key/fingerprint` is asked on that machine
- **THEN** the descriptor's `key_fingerprint` is the value the route returns
- **AND** the machines table says that a peer whose fingerprint differs from this machine's has credentials that cannot be decrypted here

### Requirement: Restamp the convergence day at most once a day
`last_converged_on` MUST be restamped **at most once per calendar day**, so a
machine that is running but idle does not commit a heartbeat every round. It
therefore means "last day this machine converged", and the UI MUST say so.

#### Scenario: an idle machine restamps its descriptor at most once a day
- **GIVEN** a machine that has already converged today
- **WHEN** further rounds run the same day with nothing else to say
- **THEN** its descriptor is not rewritten and no commit is made
- **AND** the machines table labels the value as the day it last converged

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

### Requirement: Remove the machine axis without widening reach
Removing the axis MUST NOT widen anything. A stored scope that named machines
was, on this machine, either admitted by that list or dormant because of it;
the migration MUST resolve each row against the machine id the daemon was
actually using and write the answer that machine already saw, taking
`agents: []` — dormant — whenever it cannot tell. Narrowing is visible and one
click to undo; widening is a resource silently reaching an agent it was kept
from.

#### Scenario: removing the machine axis narrows rather than widens
- **GIVEN** stored scopes that named machines — one admitting this machine, one excluding it, and one whose machine list the migration cannot interpret
- **WHEN** the migration that removes the machine axis runs
- **THEN** the row that admitted this machine keeps its agents, and the row that excluded it and the uninterpretable row become `agents: []`, dormant
- **AND** on a vault that cannot name the machine it was using, every machine-scoped row becomes `agents: []`

### Requirement: Say where reach is set that it is machine-local
A scope editor MUST state, where the user sets reach, that reach applies to this
machine only and is not synced, and MUST say where a resource is dormant here.

#### Scenario: the reach control says reach is machine-local
- **GIVEN** the reach control open on a resource
- **WHEN** the user reads the panel
- **THEN** it states that reach is set on this machine only and is not synced
- **AND** an empty agent list is named as dormant

### Requirement: Run the seven round steps in order
A round MUST be these seven steps **in this order**:

```
0  Repair    — if the working tree's HEAD is not the pointer, reset to the pointer
1  Serialize — export the vault into the tree (differentially), commit as L
2  Merge     — fetch, then merge origin/<branch> into L with base merge-base(L, R) → M
3  Diff      — D := git diff L..M
4  Guard     — circuit-breaker check on D; tag L as the pre-apply snapshot
5  Apply     — apply D to the vault, path by path
6  Publish   — push M; pointer := M; unapplied paths join the retry set
```

Most concurrent edits are not conflicts: git merges different hunks of one file
without help.

#### Scenario: a changed vault converges and pushes
- **GIVEN** a configured sync remote and a vault with a new knowledge document,
- **WHEN** a converge round runs,
- **THEN** the document is committed to the working tree, the commit is pushed
  to the configured branch, and the pointer advances to it.

#### Scenario: concurrent edits to different parts of one document merge
- **GIVEN** two machines that each appended a different section to one knowledge
  document,
- **WHEN** both converge,
- **THEN** the document holds both sections and no conflict is reported.

### Requirement: Repair the working tree first
Step 0 MUST run first: where the working tree's HEAD is not the pointer, it MUST
be reset to the pointer before anything else happens.

#### Scenario: a drifted working tree is reset to the pointer first
- **GIVEN** a converged machine whose working tree HEAD was left on a commit other than its pointer, one that dropped a document the vault still holds
- **WHEN** a round runs
- **THEN** the tree is reset to the pointer before the vault is serialized
- **AND** the round publishes no deletion of that document

### Requirement: Apply a deletion only when the diff carries one
A deletion MUST be applied only when it appears in `D` as a deletion. A machine
that merely *lacks* a document makes no change relative to its own base, and
that MUST NOT be read as a deletion.

#### Scenario: a stale machine does not resurrect a deletion
- **GIVEN** a machine whose pointer predates a deletion the other machine made
  and pushed,
- **WHEN** that machine runs its first round after being offline,
- **THEN** the deletion is applied rather than reverted, because the machine
  made no change to that path relative to its own base.

### Requirement: Export differentially
Export MUST write **differentially** — writing changed documents and removing
documents the vault no longer holds — and MUST NOT clear and rewrite a
directory.

#### Scenario: a locally deleted resource removes exactly its document
- **GIVEN** an exported vault holding several resources
- **WHEN** one resource is deleted locally and the vault is exported again
- **THEN** exactly that resource's document is removed from the tree
- **AND** every other document is left in place, unrewritten

### Requirement: Never export a retry-set path as a deletion
Export MUST NOT delete a path in the retry set. A document this vault failed to
absorb is pending, not deleted.

#### Scenario: a failed apply holds the path back instead of deleting it
- **GIVEN** a round in which one resource document cannot be applied here,
- **WHEN** the next round exports the vault,
- **THEN** that document is still present in the working tree, it is not
  committed as a deletion, and the round retries it.

### Requirement: Advance the pointer only on absorption
The pointer MAY advance to `M` only when the round completes. Any path whose
application failed MUST join the retry set instead, MUST be re-attempted next
round, and MUST leave the set on success.

#### Scenario: a held path leaves the retry set once it applies
- **GIVEN** a document that failed to apply here and joined the retry set
- **WHEN** a later round runs after the cause of the failure is gone
- **THEN** the document is applied and leaves the retry set
- **AND** it is not re-attempted on the round after that

### Requirement: Record inapplicable paths as not applicable here
A path that fails because it cannot apply on this machine at all — an `agent`
whose `config_dir` does not exist here — MUST be recorded as **not applicable
here** rather than pending: preserved like a retry-set path, not retried, not
reported as an error, and said to be so on the surfaces rather than presented as
a failure the user has to chase.
A round re-checks that precondition, never the apply itself: once the agent's
`config_dir` exists here, the held path is released and applied.

#### Scenario: an agent whose config directory is missing here is not applicable
- **GIVEN** an `agent` document arriving whose `config_dir` does not exist on this machine
- **WHEN** a round applies it
- **THEN** the path is recorded as not applicable here and preserved like a held path
- **AND** it is neither retried nor reported as a failure

### Requirement: Tell a new machine from a returning one
A machine with no pointer is **joining**, and the round MUST tell a new machine
from a returning one — out of the remote's registry, which either holds this
machine's id or does not — before it does anything.

#### Scenario: a joining machine is placed from the remote's registry
- **GIVEN** a machine with no pointer whose id the remote's registry does not hold
- **WHEN** it adopts the remote
- **THEN** the round reports that it joined as a new machine
- **AND** a machine whose id the registry does hold is reported as returning

### Requirement: Join a new machine by taking the union
A **new machine** MUST take the union: its pointer is set to git's empty tree,
so `D` is a diff from nothing and can structurally contain only additions. It
takes everything the remote holds, keeps everything it already had, and the next
round publishes both.

#### Scenario: a new machine takes the union and deletes nothing
- **GIVEN** a machine whose id the remote's registry does not hold, with its own
  vault, and a remote holding a different one,
- **WHEN** the user runs `coffer sync adopt <url>`,
- **THEN** everything the remote holds is added locally, everything the machine
  already held is still present, and the next round publishes both.

### Requirement: Recover a returning machine's base from its descriptor
A **returning machine** MUST recover its base from its own descriptor's
`last_converged_commit` and proceed as an ordinary stale-machine round: the
three-way merge takes the remote's deletions, keeps this machine's edits, and
nothing resurrects.

#### Scenario: a returning machine does not resurrect what was deleted while it was away
- **GIVEN** a machine that converged before, lost its pointer to a reinstall
  while its vault files survived, and a remote from which a skill was deleted in
  the meantime,
- **WHEN** that machine joins the remote again,
- **THEN** its id is recognised in the registry, its base is recovered from its
  own descriptor, the deletion is applied here rather than undone there, and the
  round reports that it joined as a returning machine.

### Requirement: Hold a returning machine's empty vault instead of publishing the loss
A returning machine whose vault is gone MUST NOT publish the loss. A reinstall
that took `~/.coffer` with it leaves an empty vault and a valid pointer, which
the merge would read as "this machine deleted everything"; Coffer cannot tell a
wiped disk from a deliberate purge, so the publish-side guard (see "Guard both
directions") MUST stop the round and ask rather than guess.

#### Scenario: a returning machine with an empty vault does not publish the loss
- **GIVEN** a machine that converged before and whose vault was wiped, rejoining
  a remote holding hundreds of documents,
- **WHEN** a round runs,
- **THEN** nothing is pushed as a deletion, the round is recorded as awaiting
  confirmation naming how many documents it would remove from the remote, and
  the user can instead rebuild this machine from the remote.

### Requirement: Report a join before applying it
Joining MUST be explicit and reported: whichever kind it is, the surfaces MUST
state, before anything is applied, which case it is, when this machine last
converged, how many documents the remote has changed since, and how many this
vault has.
Only an explicit adopt applies a join: `GET /sync/join` states the join and
applies nothing, `coffer sync adopt` prints it and asks before applying
(`--yes` skips the question; with no terminal and no `--yes` it refuses), and
the web Sync page shows it in a dialog and joins only on confirm. An ordinary
round — the background worker, `coffer sync now`, `POST /sync/run` — on a
machine that has not joined MUST apply and push nothing and end as
`awaiting_join`, carrying the same report.

#### Scenario: a join states its case and its counts before applying
- **GIVEN** a returning machine with no pointer and a remote that has changed documents since it last converged
- **WHEN** it joins the remote
- **THEN** the surfaces state that it is returning, the day it last converged, how many documents the remote has changed since and how many this vault holds, before anything is applied

### Requirement: Rebuild a vault from the remote only on request
**Rebuild** MUST replace this vault with the remote's, discarding documents only
this machine holds and pushing nothing. It is destructive on purpose and MUST
NOT be reached without the user asking for it by name. It is the third answer a
damaged machine needs, because confirming spreads the loss and rejecting refuses
the same round forever.

#### Scenario: a damaged machine rebuilds from the remote instead of publishing its loss
- **GIVEN** a machine whose vault was wiped and whose round is held by the
  publish-side guard,
- **WHEN** the user rebuilds it from the remote,
- **THEN** the vault holds what the remote holds, documents only this machine
  had are gone, nothing was pushed, and the held round is cleared.

### Requirement: Refuse a returning machine whose base is gone until the user picks
A returning machine whose recorded base is no longer in the remote's history
MUST be refused until the user picks: joining as new would resurrect what the
others deleted, rebuilding would discard what only this one has, and there is no
safe default.

#### Scenario: a returning machine whose base is gone must choose
- **GIVEN** a machine the remote's registry holds, with no pointer, whose recorded base is no longer in the remote's history
- **WHEN** it adopts the remote without saying how to join
- **THEN** the adopt is refused, naming the choice to make, and nothing is applied or pushed
- **AND** adopting again with `--keep-local` joins it as new

### Requirement: Detect joining on every round without a pointer
The join detection MUST run whenever a round starts with no pointer, not only
under `coffer sync adopt`, so configuring a remote on a machine that has
forgotten its pointer cannot skip it.

#### Scenario: an ordinary round on a machine without a pointer still detects the join
- **GIVEN** a machine the remote's registry holds, which has lost its pointer
- **WHEN** an ordinary round runs rather than `coffer sync adopt`
- **THEN** the round recognises the machine as returning and recovers its base from its descriptor
- **AND** it reports the join and ends as `awaiting_join`, applying nothing until the machine adopts

### Requirement: Apply knowledge and skill file changes
For `knowledge/**` and `skills/**`, an addition or a modification MUST write the
file and a deletion MUST remove it.

#### Scenario: an arriving file is written and a deleted one removed
- **GIVEN** a diff that adds a knowledge file and a skill file and deletes another knowledge file
- **WHEN** it is applied to the vault
- **THEN** the added files are written into the knowledge and skill stores
- **AND** the deleted file is removed from the vault

### Requirement: Apply resource documents through the resource service
For `resources/<kind>/<uid>.yaml`, an addition or a modification MUST upsert
through the kind-agnostic resource service with `${HOME}` expanded and the
kind's import gate run, leaving the local resource's reach untouched (see "Keep
reach machine-local"); a deletion MUST delete the resource. A document whose
name differs from the local resource's MUST be applied as a **rename** of that
resource, never as the arrival of a different one.

#### Scenario: an arriving resource document is upserted through the import gate
- **GIVEN** a resource document for a resource this vault does not hold, and later a modified version of it
- **WHEN** each is applied
- **THEN** the first registers the resource at the document's uid and the second updates that same row
- **AND** a document the kind's import gate refuses writes nothing

### Requirement: Apply state documents through their area's provider
For `state/<area>/**`, the area's provider MUST apply the document and MUST
remove it on deletion (see "Let each state area define its document's
deletion").

#### Scenario: a state document is applied by the provider that claims its area
- **GIVEN** a state document under `state/<area>/` and a provider registered for that area
- **WHEN** it is applied
- **THEN** that area's provider receives it
- **AND** a document for an area no provider claims is skipped

### Requirement: Apply credential blobs
For `credentials/<ref>.enc`, an addition or a modification MUST write the
ciphertext subject to the freshness rule (see "Let the fresher credential
ciphertext win"); a deletion MUST delete the credential.

#### Scenario: a credential blob is written as ciphertext and its deletion deletes the credential
- **GIVEN** a credential blob arriving for a ref, and later its deletion
- **WHEN** each is applied
- **THEN** the ciphertext is written to the credential store, and a blob staler than the one held is refused
- **AND** the deletion removes the credential

### Requirement: Never apply the registry or the manifest
`machines/*.yaml` and `manifest.json` MUST NOT be applied in either direction —
the registry is read from the tree, never projected into anything local, and the
manifest is metadata about the tree.

#### Scenario: the registry and manifest are never applied
- **GIVEN** a diff that changes `machines/<id>.yaml` and `manifest.json` beside a knowledge file
- **WHEN** the changes that reach the vault are taken from it
- **THEN** only the knowledge file is among them
- **AND** neither the descriptor nor the manifest counts towards the deletion guard

### Requirement: Release unreferenced credentials on deletion
Deleting a resource MUST release the credentials no remaining resource cites,
as any other deletion does.

#### Scenario: a remote deletion is applied
- **GIVEN** a skill present on both machines, deleted on the other one and
  pushed,
- **WHEN** a round runs here,
- **THEN** the skill's files and its registry row are removed here, the
  credentials no remaining resource cites are released, and the deletion is
  audited.

### Requirement: Re-run post-import hooks after applying
After the diff is applied, each kind's post-import hook MUST re-apply its
machine-local side effects — native config projections, shims, skill deliveries
— from current state.

#### Scenario: a remote addition lands in the vault
- **GIVEN** a remote holding an `mcp_server` this vault does not have,
- **WHEN** a round runs,
- **THEN** the server is registered locally, its post-import hook has run, and
  the pointer advances past the commit that added it.

### Requirement: Start nothing when a channel arrives
A `channel` is upserted by the same row as every other kind, and its arrival
MUST start nothing: what it carries is a machine binding, and a machine that is
not the one named simply holds the document. The channel kind's own
registration checks MUST be relaxed for exactly that case ([channels](../channels/spec.md) "Bind each channel to the one machine that runs it"),
because a channel bound elsewhere is not judged here against agents this machine
happens to have.

A binding that names no machine any registry claims is a fault on the channel,
not permission for this one to start its adapter: [channels](../channels/spec.md) "Bind each channel to the one machine that runs it" owns that
rule and the fail-closed startup behaviour behind it.

#### Scenario: a channel travels and runs only on the machine it names
- **GIVEN** a `channel` configured on one machine and bound to it,
- **WHEN** the two machines converge,
- **THEN** the channel is registered on the other machine with its binding
  intact, that machine starts no adapter for it, and the machine it names still
  runs it.

### Requirement: Let each state area define its document's deletion
A state document reaches the working tree only while there is a **decision to
carry**, so its deletion is that decision being taken back. Each state area's
provider MUST define what deleting its own document means in that area's terms
and MUST honour it; sync MUST apply the deletion through the provider and MUST
NOT interpret it for any area. The same rule binds the other direction: an area
MUST NOT publish a document for its own defaults, or a machine that took its
choice back and a machine that never made one would add and delete the same
document at each other every round. The areas that exist today state their own
terms in spec [mcp-gateway](../mcp-gateway/spec.md) (capability preferences),
spec [internal-engine](../internal-engine/spec.md) (engine settings) and spec
[agent-registry](../agent-registry/spec.md) (the plugin inventory).

#### Scenario: a state area decides what its own document's deletion means
- **GIVEN** a state document whose area is the MCP capability preferences, and
  the other machine has taken that decision back and pushed the deletion,
- **WHEN** a round applies the diff here,
- **THEN** the area's own provider is what performs the removal, sync applies no
  meaning of its own, and the area publishes no document for its defaults, so
  the next round has nothing to delete again.

### Requirement: Report per-path failures without aborting
Per-path failures MUST be reported and MUST NOT abort the round.

#### Scenario: one path that fails to apply does not stop the round
- **GIVEN** a round whose diff carries one document that cannot be applied here beside others that can
- **WHEN** the round runs
- **THEN** the other documents are applied and the round completes
- **AND** the failing path is reported with its reason

### Requirement: Let the fresher credential ciphertext win
Credential blobs MUST NOT reach a text merge. A Fernet token carries its
encryption time in cleartext, so two ciphertexts for one ref can be ordered
without the key, and the **fresher encryption wins**. This rule applies to
`credentials/*.enc` and to nothing else.

#### Scenario: the fresher credential ciphertext wins
- **GIVEN** one credential ref re-encrypted on both machines, the other machine's
  encryption being the older one,
- **WHEN** the two meet in a round,
- **THEN** the fresher ciphertext is what both machines hold afterwards,
  regardless of which commit is newer.

### Requirement: Resolve remaining conflicts with an agent only in the working tree
Where an internal model is configured, a bounded agent pass MAY resolve the
remaining conflicts **in the working tree only**, and MUST NOT run against the
live vault.

#### Scenario: an agent-resolved conflict is validated and reported
- **GIVEN** a conflicted resource document and an internal model configured,
- **WHEN** a round runs and the agent's resolution parses and validates,
- **THEN** the resolution is applied as an ordinary merge result and the round's
  status names the path as agent-resolved.

### Requirement: Validate an agent's resolution
That pass's output MUST pass a validation gate — the document parses, a resource
document validates, and no conflict marker remains — before it is treated as an
ordinary merge result.

#### Scenario: an agent resolution that fails validation is not applied
- **GIVEN** a conflicted resource document whose agent resolution leaves a
  conflict marker,
- **WHEN** a round runs,
- **THEN** nothing is applied, the round aborts as an unresolved conflict, and
  the vault is unchanged.

### Requirement: Report every resolution with its paths
Resolutions MUST always be reported with their paths, whether or not they
succeeded: a silent machine merge of the user's own notes is precisely what the
user would want to know about.

#### Scenario: a resolution that fails is still reported with its path
- **GIVEN** a conflicted document whose agent resolution fails the validation gate
- **WHEN** a round runs
- **THEN** the round's report names that path among its conflicts

### Requirement: Abort the round on an unresolved conflict
Otherwise the round MUST abort — with no model configured, or when the pass
fails or its output fails the gate. The vault MUST NOT be touched, the pointer
MUST NOT move, and the surfaces MUST name the conflicted paths and the working
tree that holds them.

#### Scenario: a real conflict stops the round without touching the vault
- **GIVEN** two machines that edited the same lines of one document, and no
  internal model configured,
- **WHEN** a round runs,
- **THEN** the round aborts, the vault is unchanged, the pointer has not moved,
  and the status names the conflicted path and the working tree holding it.

### Requirement: Snapshot before applying and roll back from it
Bidirectional convergence writes the vault without a human in the loop, so two
guards are normative.

Step 4 MUST tag `L` as the pre-apply snapshot, whose tree is by construction the
vault's state immediately before the apply. Rollback MUST be the same machinery
run backwards — applying `M..L`. The most recent **ten** snapshots MUST be kept.
A rollback MUST NOT move the pointer: the reverted vault is an ordinary local
change, which the next round publishes to the remote. Moving the pointer back
would make the next round re-derive the diff just undone and apply it again.

#### Scenario: a round can be rolled back
- **GIVEN** a completed round that applied a diff,
- **WHEN** the user rolls it back,
- **THEN** the vault returns to the state the pre-apply snapshot holds and the
  pointer stays where it was, so the next round publishes the undo as an
  ordinary local change rather than re-applying the diff,
- **AND** a round that applied nothing here offers no Undo at all, because the
  snapshot it left is the state the vault is already in.

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
A tripped breaker MUST be recorded as needing confirmation, the surfaces MUST
list what it would remove, and the user accepts or rejects it. What is
outstanding is a question about one diff, which is why a later round re-derives
it rather than repeating it (see "Release a hold whose diff no longer breaches"
and "Record one outstanding confirmation once").

#### Scenario: an oversized deletion is held for confirmation
- **GIVEN** a diff that would delete more documents than the circuit breaker
  allows,
- **WHEN** a round runs,
- **THEN** nothing is applied, the round is recorded as awaiting confirmation
  with the list of documents it would remove, and `coffer sync confirm` applies
  it while rejecting it leaves the vault untouched.

### Requirement: Guard both directions
The guard MUST run in **both directions** — over what the round would apply to
the vault, and equally over what the round's own export would publish as a
deletion. The second direction is what stops a vault that lost its files to a
reinstall, a failed restore or a stray `rm -rf` from publishing that loss and
taking the other machines down with it.

Neither guard replaces the diff-based apply; they bound the damage of a defect
in it. A machine joining as new has no deletions in either direction and is
unaffected.

#### Scenario: a wiped area is held although rename pairings are consulted
- **GIVEN** a vault that has lost every document in an area with nothing added
  in their place — a wiped disk, a failed restore, a stray `rm -rf`,
- **WHEN** a round runs,
- **THEN** there is nothing for a pairing to match, the round is held on the
  publish side, and the loss is not published to the remote.

### Requirement: Guard the retry set with the diff
On the apply side the guard MUST run over everything the round is about to apply
— the incoming diff **and** the retry set, since a held path the tree has since
dropped is absorbed as a deletion.

#### Scenario: the apply-side guard counts held paths the tree dropped
- **GIVEN** a vault whose retry set holds more paths in one area than the guard allows to be lost, all of which the tree has since dropped
- **WHEN** a round runs
- **THEN** the round is held on the apply side rather than absorbing those deletions unasked

### Requirement: Count losses, not deletions
The guard MUST count what a round **loses**, not what it deletes. A deletion
with a destination **in the same area of the same diff** is a **move**: it MUST
NOT count towards either threshold, and it MUST NOT appear in the list a hold
puts in front of the user, because a document that turned up under another name
was not removed. A destination MAY be shown two ways — the same content id
reappearing, or git's own rename detection pairing the two sides — and a
deletion with neither counts. A pairing that crosses an area MUST be discarded,
since the guard's unit is the area. The empty document is never paired on
content, every empty file being identical by construction.

#### Scenario: a re-layout publishes without asking
- **GIVEN** a vault whose knowledge documents have all been moved into a
  subdirectory, so the diff carries a deletion and an addition of identical
  content for nearly every document in the area,
- **WHEN** a round runs,
- **THEN** the guard does not hold it, the round publishes unattended, the other
  machine absorbs the move with no confirmation of its own, and a deletion in
  the same round that no addition received is still held and listed on its own.

### Requirement: Ask git about renames separately from the applied diff
The two tests MUST be asked of git as **separate** questions: the diff a round
applies stays rename-blind, because the vault applies one path at a time, and
the guard's reading of the same diff MUST NOT change what is applied or in what
order.

#### Scenario: a re-layout that rewrites its documents publishes without asking
- **GIVEN** a vault whose documents have all been moved to new addresses **and
  edited on the way**, which is what a layout migration does — so the two sides
  of every change differ and no content id pairs them,
- **WHEN** a round runs,
- **THEN** the guard reads git's own rename detection, does not hold the round,
  and the other machine absorbs the migration with no confirmation of its own.

### Requirement: Say a vault needs a human where the user already is
A vault whose last round needs a human — held for confirmation, conflicted,
failed to push or run, or waiting to join (`awaiting_join`) — MUST say so where
the user already is, not only on the page built for it. `coffer sync status`
MUST exit non-zero, the web UI MUST mark its **navigation entry** for the sync
page, and the desktop shell MUST raise it as a notification and mark its icon. A
held vault converges no further, and neither does a machine that has not joined
its remote, so a hold nobody sees is an outage that looks like silence: the
first one in the field stood for four days.

The web UI's mark MUST be cleared by **visiting the page**, not by the situation
changing, and MUST NOT return for the same situation. The rounds are
timer-driven: one broken remote is a fresh round every hour, and a notice that
re-raised itself on each would cover every page in the app hourly with something
the user read the first time. A mark keyed on what is wrong — the outcome, the
error, the direction and areas a hold was raised over — asks once, and asks
again only when the answer would be different.

#### Scenario: a held vault says so where the user already is
- **GIVEN** a round held at the deletion guard, so nothing converges and
  nothing is backed up until someone answers it,
- **WHEN** the user is anywhere other than the sync page — at a terminal, on
  another page of the web UI, or with only the desktop shell in front of them,
- **THEN** `coffer sync status` exits non-zero, the web UI's navigation entry
  for sync is marked, and the shell has marked its icon and raised one
  notification — once for that condition, not once per poll,
- **AND** opening the sync page clears the web UI's mark, which does not
  return while the same thing is wrong, however many rounds re-raise it.

#### Scenario: a machine that has not joined says so everywhere
- **GIVEN** a machine with a remote configured that it has not joined, so its
  round reports `awaiting_join` and converges nothing
- **WHEN** the user is anywhere other than the sync page
- **THEN** `coffer sync status` exits non-zero and points at `coffer sync adopt`,
  the web UI's navigation entry for sync is marked, and the desktop shell marks
  its icon and raises one notification

### Requirement: Release a hold whose diff no longer breaches
A round MUST re-derive its diff even while a confirmation is outstanding, and
MUST **release** the hold where the direction it was raised for no longer
breaches. A latch is an unanswered question about one diff, not a state a vault
sits in: a vault held on a question that no longer arises MUST converge again
without anyone answering it. A diff that still breaches MUST stay held, and
re-deriving it MUST NOT move the moment the user was asked.

#### Scenario: a hold is released once its diff no longer breaches
- **GIVEN** a vault held at the deletion guard whose documents have since come
  back, so the diff that raised the hold no longer breaches it,
- **WHEN** the next round runs,
- **THEN** the hold is released without anyone answering it, the round converges
  normally, and nothing is left waiting on the user.

### Requirement: Record one outstanding confirmation once
One outstanding confirmation MUST be **one** recorded round and one line in the
daemon log, however many times the timer re-derives it: the round that first
reported it is re-stamped rather than joined by a second, and no further audit
event is written. The surfaces MUST still show the confirmation as outstanding
and still offer its answers, and answering it MUST produce a further round of
its own.

#### Scenario: an unanswered confirmation is reported once, not once a tick
- **GIVEN** a vault held at the deletion guard and a timer that runs a round
  every interval,
- **WHEN** several rounds run with nobody answering,
- **THEN** the history holds **one** round for it rather than one per tick, the
  audit log holds one event, the Sync page still shows the confirmation as
  outstanding with the moment it was raised, and answering it produces a further
  round.

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
A curation pass and a converge round MUST NOT overlap. Both write the vault and an
export taken mid-rewrite is a torn snapshot, so they MUST take the same lock. A
pass MUST additionally be skipped while a conflict or a pending confirmation is
outstanding, so a rewrite is never piled onto an unresolved divergence.

#### Scenario: a curation pass and a converge round do not overlap
- **GIVEN** a curation pass in progress,
- **WHEN** a converge round starts,
- **THEN** the round waits for the pass to finish before it serializes the
  vault, so the exported tree is never a half-rewritten corpus.

#### Scenario: a curation pass is skipped while a round is unresolved
- **GIVEN** a machine whose last round stopped on a conflict, or that holds a pending confirmation,
- **WHEN** the unattended curation pass asks whether it may run,
- **THEN** it is told no, and once a later round converges cleanly with nothing held it is told yes again.

### Requirement: Let an edit beat a curation deletion
Where the owner's curation pass deleted a document another machine edited, the **edit
MUST win**: the document survives with its edit, the deletion is dropped, and
the round MUST NOT report a conflict. A fresh edit is something a person or an
agent just decided; the deletion is a housekeeping judgement the next pass will
simply make again.

#### Scenario: an edit outlives a curation deletion
- **GIVEN** a note the owner's curation pass merged away and deleted, and the same
  note edited on the other machine before it converged,
- **WHEN** the two meet in a round,
- **THEN** the note is still present with its edit, the deletion is dropped, and
  the round does not report a conflict.

### Requirement: Serialize deterministically
Resource and state serialization MUST be deterministic — sorted keys, normalized
timestamps, machine-local fields stripped — so that an unchanged vault produces
an unchanged tree.

#### Scenario: an unchanged vault serializes to an identical tree
- **GIVEN** a vault that has been exported once
- **WHEN** it is exported again with nothing changed
- **THEN** every document in the tree is byte-for-byte what it was
- **AND** nothing is rewritten

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
Paths outside `$HOME` MUST be stored verbatim. They may fail to apply on another
machine, which MUST surface as a per-path failure (see "Report per-path failures
without aborting").

#### Scenario: a path outside the home directory is stored verbatim
- **GIVEN** a config value naming an absolute path outside the home directory
- **WHEN** it is made portable for the tree and expanded again on another machine
- **THEN** the path is carried exactly as written, with no `${HOME}` sentinel

### Requirement: Never write the master key into the repository
The master key MUST never be written into the repository. It is bootstrapped
onto another machine out-of-band with `coffer sync key export` /
`coffer sync key import`.

#### Scenario: the master key never enters the repository
- **GIVEN** a remote configured to carry credential ciphertext,
- **WHEN** a round pushes,
- **THEN** the tree holds Fernet ciphertext and no key material, and a machine
  without the key reports those refs locked rather than failing decryption.

### Requirement: Report refs without a key as locked
A machine holding ciphertext without the key MUST report those refs **locked**
rather than failing decryption silently. Two absences MUST be told apart. A machine
that genuinely holds no master key can open none of its ciphertext, so every
credential ref it holds ciphertext for MUST be reported locked. A key that exists
but cannot be read right now (a locked or unavailable keychain, an unreadable key
file) says nothing about which refs would open, so the round MUST report none
and MUST log that the key was unreadable; the round is still recorded. The key
MUST be resolved at most once per daemon start, whichever of the three answers
it gives, so a key kept in the keychain costs at most one prompt.

#### Scenario: credentials this machine cannot decrypt are reported locked
- **GIVEN** a machine holding credential ciphertext written under a master key it does not hold
- **WHEN** a master key is imported that still does not decrypt them
- **THEN** the import names those refs as still locked rather than reporting success silently

#### Scenario: a machine with no master key reports every ref it holds as locked
- **GIVEN** a machine with no master key file and none in the keychain, holding credential ciphertext that arrived from another machine
- **WHEN** a converge round runs
- **THEN** the round's `locked_refs` names every credential ref this machine holds ciphertext for, and the round is recorded with them

#### Scenario: an unreadable key reports no ref locked
- **GIVEN** a machine holding credential ciphertext whose master key lives in a keychain that is locked
- **WHEN** a converge round runs
- **THEN** the round's `locked_refs` is empty, the unreadable key is logged, the round is recorded, and the keychain is not asked again on later rounds

### Requirement: Hand the push credential to git as a helper
The push credential MUST be resolved from the credential store at push time,
named by reference and never by value. It MUST NOT enter the repository's git
config, MUST NOT appear in a command line, and MUST be redacted from any
recorded error. It MUST reach git as a **credential helper**, which every git
consults before it would prompt, and MUST NOT be handed over through a prompt
mechanism: a prompt path is optional and platform-dependent — macOS's own git
ignores `GIT_ASKPASS` entirely — so a credential delivered that way is not
delivered at all on the platform Coffer ships a desktop app for. That failure is
invisible by construction while a credential helper in the user's own git
configuration happens to answer instead, and this layer pins that configuration
away on purpose, so there is nothing left to fall back on when it stops.

#### Scenario: the push credential never reaches the repository
- **GIVEN** a configured remote with a push credential,
- **WHEN** a round pushes,
- **THEN** the credential is absent from the repository's git config, from the
  git process's arguments, and from any recorded error text or audit payload,
- **AND** it still authenticates, because it reaches git as a credential helper
  reading it from the environment rather than as an answer to a prompt.

### Requirement: Restore to a revision without discarding later work
`coffer sync restore [--at <rev|date>]` MUST move the working tree to a revision
and apply the difference from the current pointer, so a document deleted last
week returns without discarding anything the vault gained since.

#### Scenario: restore brings back a document deleted last week
- **GIVEN** a remote whose history contains a skill later deleted and converged
  away,
- **WHEN** the user runs `coffer sync restore --at <a date before the deletion>`,
- **THEN** the skill is registered again and everything the vault gained since
  that date is untouched.

### Requirement: Restore only on request
Restore MUST always be explicit; a round MUST NOT reach back into history on its
own.

#### Scenario: a round never reaches back into history
- **GIVEN** a document that was deleted and whose deletion has converged, so it survives only in the remote's history
- **WHEN** further rounds run without anyone asking for a restore
- **THEN** the document stays deleted on every machine

### Requirement: Cover the sync lifecycle on the command line
The CLI MUST cover the round and the vault's lifecycle — `coffer sync now`,
`adopt [<url>] [--keep-local] [--yes]`, `status`, `history [--limit]`,
`restore [--at <rev|date>]`, `confirm`, `reject`, `rebuild [--yes]`, `rollback`
— and its administration:
`remote set <url> [--branch] [--interval <seconds>] [--with-credentials|--without-credentials] [--credential-ref] [--worktree <path>]`,
`remote show`, `remote clear`, `machine list`, `machine rename <name>`,
`machine remove <id>`, `key export <file>`, `key import <file>`,
`key fingerprint`. An option `remote set` is not given keeps the stored remote's
value, the working tree included.

#### Scenario: the command line covers every sync operation
- **GIVEN** the `coffer sync` command group
- **WHEN** its commands and options are listed
- **THEN** it offers `now`, `adopt` with `--keep-local` and `--yes`, `status`, `history` with `--limit`, `restore` with `--at`, `confirm`, `reject`, `rebuild` with `--yes` and `rollback`
- **AND** it offers `remote set` with `--branch`, `--interval`, `--with-credentials`, `--without-credentials`, `--credential-ref` and `--worktree`, `remote show`, `remote clear`, `machine list`, `machine rename`, `machine remove`, `key export`, `key import` and `key fingerprint`

### Requirement: Cover the same operations over HTTP
The HTTP API MUST cover the same operations under `/api/v1/sync`:
`GET|PUT|DELETE /sync/remote`, `POST /sync/run`, `GET /sync/join`, `POST /sync/adopt`,
`GET /sync/status`, `GET /sync/runs`, `POST /sync/restore`,
`POST /sync/confirm`, `POST /sync/reject`, `POST /sync/rebuild`,
`POST /sync/rollback`, `GET /sync/machines`, `PATCH /sync/machines/self`,
`DELETE /sync/machines/{id}`, `GET /sync/key/fingerprint`,
`POST /sync/key/export`, `POST /sync/key/import`.

#### Scenario: the HTTP API serves every sync operation
- **GIVEN** the daemon's HTTP application
- **WHEN** its routes under `/api/v1/sync` are listed
- **THEN** every method and path the requirement names is served

### Requirement: Present a Sync page with Runs and Setup tabs
The web UI MUST present a top-level **Sync** page with **two** tabs. **Runs**,
the landing tab: every round this machine has run, as a table — when, outcome,
what it applied here, what it published, the commit. **Setup**: the remote, the
master key and the machine registry, which are one errand rather than three
screens. There MUST be no Status tab — what a vault is *doing* is the newest row
of what it has *been* doing, and a separate tab for it put one situation in two
places and made it actionable in only one.

#### Scenario: the Sync page opens on Runs beside Setup and nothing else
- **GIVEN** the web UI
- **WHEN** the user opens the Sync page
- **THEN** it has exactly two tabs, Runs and Setup, and opens on Runs
- **AND** a link to a tab that no longer exists lands on Runs

### Requirement: Put a held round's answers on its own row
A round waiting on the user MUST carry its answers on **its own row** — confirm
(naming the direction, the breached areas and the paths before it runs), reject,
and, on a `publish` hold, rebuild-from-remote. Only the round the vault is
**currently** waiting on may carry them: `POST /sync/confirm` acts on the
vault's present pending state rather than on a round named in the request. There
is exactly one such row, because one outstanding confirmation is one recorded
round (see "Record one outstanding confirmation once") — the timer re-stamps it
rather than adding another each pass — and answering it produces a further round
rather than rewriting the held one, whose outcome stays `awaiting_confirmation`.

#### Scenario: only the round the vault is waiting on carries its answers
- **GIVEN** a runs history whose newest round is the hold the vault is waiting on, beside an older round that was once held
- **WHEN** the Runs tab renders
- **THEN** the newest round carries confirm, reject and — on a publish hold — rebuild, and the older round carries none of them
- **AND** once the vault is no longer waiting, no round carries them

### Requirement: Show a conflict as a banner
A **conflict** MUST stay a banner above the table, because its paths have to be
resolved with the user's own git in a working tree the table has no column
for.

#### Scenario: a conflict is shown as a banner above the runs
- **GIVEN** a vault whose last round ended in a conflict
- **WHEN** the Runs tab renders
- **THEN** a banner above the table names the conflicted paths and the working tree that holds them

### Requirement: Offer Undo on one round only when it applied something
At most one row — the newest that reached its pre-apply snapshot, which is the
round a rollback would reverse — MAY carry an **Undo** action naming the paths
it would take back, and no other row may, because `POST /sync/rollback` names
no round and an Undo on every row would run the same call from each. That row
MUST carry it only when the round **applied something to this machine**: every
round reaching the apply step tags a snapshot, including one that applies
nothing, so after a single quiet round the newest snapshot is the vault exactly
as it already is, and an Undo there offers to restore the state it is already
in. The action MUST NOT move down to an older round that did apply something —
the quiet round's snapshot is the newest, so the daemon would reverse to that
one and leave the older round standing, which is a button naming one round and
undoing another. Reaching further back is `coffer sync restore` (see "Keep
point-in-time restore on the command line").

#### Scenario: the undo sits on one round and never moves down
- **GIVEN** a runs history in which several rounds applied something here
- **WHEN** the Runs tab renders
- **THEN** only the newest round that reached its snapshot offers Undo, naming the paths it would take back
- **AND** when a quiet round sits on top, no row offers Undo rather than an older one

### Requirement: Keep point-in-time restore on the command line
Restoring at a point in time MUST stay a CLI operation and no page may offer it:
`--at` names a revision in the *remote's* history, which no route exposes, so a
page could only offer a blind date box with no preview of what would come
back.

#### Scenario: no page offers a point-in-time restore
- **GIVEN** the Sync page with a configured remote and a history of rounds
- **WHEN** the user looks through its Runs and Setup tabs
- **THEN** neither offers a restore or a date to restore to

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
fold into one counted row, because an expired credential is ten identical
failures by morning and a held round is re-raised every hour until it is
answered — neither is more true for being printed ten times. A round that
applied or published documents MUST NOT fold, however many like it came before,
and rounds of different outcomes MUST NOT fold together. A lone round MUST stay
a row of its own. The **newest** round MUST never be folded: it is the state the
vault is in now and the only round that may carry Undo or a hold's answers.

#### Scenario: consecutive quiet rounds fold into one counted row
- **GIVEN** a runs history holding a stretch of consecutive rounds that changed nothing
- **WHEN** the Runs tab renders
- **THEN** the stretch is one row that reports its span and how many rounds it stands for
- **AND** every round in it is still reachable from that row

#### Scenario: repeated failures fold into one row and the newest round stands alone
- **GIVEN** a runs history whose newest three rounds failed the same way, preceded by a round that published a document
- **WHEN** the Runs table's rows are built
- **THEN** the newest failure is a row of its own, the two failures before it are one row counting two, and the round that published is a row of its own
- **AND** a stretch of consecutive rounds held for confirmation folds the same way beneath a newer round

### Requirement: Pause a configured remote without forgetting it
A configured remote MUST carry an `enabled` switch, and switching it off MUST
pause sync without forgetting anything. While it is off every round MUST report
`disabled`, record nothing, commit and push nothing, and raise no attention on
any surface — `coffer sync status` exits zero, the web UI does not mark its sync
entry and the desktop shell marks nothing — even over a round the vault was
paused on, because a user who met a hold by switching sync off has answered it
too. The remote, the pointer and the history MUST all be kept, so switching it
back on resumes where the vault left off. Re-running `coffer sync remote set`
MUST keep a paused remote paused — it changes what it names and nothing else:
every option it is not given keeps its stored value, including the branch, the
interval, whether credentials travel, the push credential and the working tree
— and a remote configured for the first time is stored enabled, with the
defaults for every option it is not given.

#### Scenario: a paused remote runs no round and asks for nothing
- **GIVEN** a joined vault whose last round is held at the deletion guard, and
  its remote then switched off
- **WHEN** a note is written and a round is requested
- **THEN** the round reports `disabled`, the history is exactly what it was, the
  note is not on the remote, and the pointer and the remote are kept
- **AND** `coffer sync status` exits zero, the web UI does not mark its sync
  entry and the desktop shell marks nothing

#### Scenario: reconfiguring a paused remote keeps it paused
- **GIVEN** a configured remote that has been switched off
- **WHEN** `coffer sync remote set` is run again with a different interval
- **THEN** the stored remote carries the new interval and is still switched off
- **AND** a remote set for the first time is stored switched on

#### Scenario: reconfiguring a remote changes only what it names
- **GIVEN** a configured remote with a non-default branch, interval, push
  credential and working tree, carrying credentials
- **WHEN** `coffer sync remote set` is run again naming only a new interval
- **THEN** the stored remote carries the new interval and every other setting
  exactly as it was
- **AND** running it with `--without-credentials` switches credential sync off
  and changes nothing else
