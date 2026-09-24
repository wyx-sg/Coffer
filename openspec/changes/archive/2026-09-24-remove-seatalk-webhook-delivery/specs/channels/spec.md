## MODIFIED Requirements

### Requirement: Run the channel lifecycle through the resource framework
Channel lifecycle (register, enable, disable, update, delete) MUST ride the
generic resource framework, with audit on every transition. Disabling a channel
stops its adapter (Telegram polling halts, a SeaTalk websocket connection
closes); enabling restarts it;
deleting the channel stops the adapter and removes its peer binding.

#### Scenario: disable stops the adapter and enable restarts it
- **GIVEN** an enabled telegram channel with a running adapter
- **WHEN** the user disables and re-enables the channel
- **THEN** polling stops while disabled and resumes after enabling

#### Scenario: deleting a channel cleans up its runtime and peer
- **GIVEN** an enabled, paired channel
- **WHEN** the user deletes the channel resource
- **THEN** the adapter stops and the peer binding is removed

### Requirement: Manage channels from the Channels page and the CLI
The Channels page MUST list channels, register new ones (storing secrets
through the credential store), show each row's paired peer and health, set each
channel's reach (enable/disable and scope), bind each channel to the machine
that runs it (see "Bind each channel to the one machine that runs it"), and
delete a channel from its row. A channel's detail page MUST show its status
(adapter running, paired peer, and the inbound state the channel's type
reports — for SeaTalk, its websocket connection),
issue pairing codes, edit the channel, send a test notification to its paired
owner (see "Notify the paired owner on demand"), and delete it.

Editing changes the channel's default agent and its type's plain settings (a
SeaTalk app id). Rotating an existing
secret happens **in place**: the new value MUST be written to the credential
store under the ref the channel already cites before the configuration is
saved, and that ref MUST stay in the saved configuration, so a rotation moves
no secret and leaves the channel's machine binding and pairing untouched. A
secret field left blank rotates nothing.

The CLI MUST offer these operations across three command groups:
`coffer channel list / register / bind / pair / status / notify` for the
channel-specific ones; the kind-agnostic `coffer resource show / enable /
disable / rename / delete channel <name>` and `coffer scope show / set channel
<name>` for its lifecycle and reach; and `coffer credentials set <ref>` for
rotating a secret under a ref that `coffer resource show` reports. Editing a
channel's default agent or type settings is served by the detail page and
`PATCH /api/v1/resources/{uid}`.

#### Scenario: register and list channels from the command line
- **GIVEN** a running daemon and a stored credential
- **WHEN** the user runs `coffer channel register` and `coffer channel list`
- **THEN** the channel is created and appears in the listing

#### Scenario: channel status reports runtime, pairing, and callback details
- **GIVEN** channels in various states
- **WHEN** the user queries status via REST and CLI
- **THEN** adapter run state, paired peer, and the channel type's own inbound
  state are reported accurately

#### Scenario: rotating a channel secret keeps its refs and pairing
- **GIVEN** a registered telegram channel whose bot token is stored under a
  credential ref
- **WHEN** the owner enters a new bot token in the channel detail page's edit
  dialog and saves
- **THEN** the new token is written under the channel's existing ref first
- **AND** the channel's configuration is then saved to the same channel with
  every ref unchanged, so nothing its pairing and binding hang off moves

### Requirement: Limit the agents a channel may drive to its scope
A channel MUST carry the framework's `scope`
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)),
one allow-list of agents, read as **the agents this channel may drive**. Every
other kind's scope names the agents a resource is *delivered to*; a channel is
consumed by no agent — it is an inbound surface — so the list is inverted rather
than borrowed, and the spec says so explicitly because a reader who assumes the
usual reading gets it backwards. That inverted reading is the whole of what a
channel's scope says: there is nothing in it about WHICH MACHINE runs the
channel. That question has its own field, `runs_on` (see "Bind each channel to
the one machine that runs it"), for a reason scope cannot satisfy: scope is
reach, reach is machine-local and never travels, and the machine that runs a
channel is one answer the machines must share.

- An unrestricted scope MUST mean every registered agent. That is the pre-scope
  behaviour and what every existing channel carries, so no channel needs a data
  migration.
- `agents: [<agent>, …]` MUST narrow `/agent` at all three of its surfaces: the
  listing, the selection card, and the validation of a chosen key (typed or
  tapped). They MUST read one narrowed set — a card that offers an agent the
  next check rejects is the specific failure this requires.
- **One vocabulary above the binding.** A scope and a `default_agent` both name
  agent **uids**, which is also what a reach picker offers, so every comparison
  between them is made directly and no translation exists to get backwards. A
  uid this vault does not hold admits no agent at all.
- **One crossing, below it.** `/agent`, the sticky per-thread choice and the
  turn router all speak the agent **key** the turn platform routes on. That key
  MUST be derived from the uid at exactly ONE place — the runtime gate, where the
  resource row becomes a live binding — and nothing below that point may hold a
  uid. Two agent resources of the same type collapse to one key there. While the
  two vocabularies met in several places at once, each of them compared a scope
  written in one to a default written in the other: the only narrowing a user
  could express was refused, and the value accepted in its place was one the
  reach picker then had to render as an agent registered nowhere.
- **The invariant:** a channel's `default_agent` MUST be an agent the channel
  may drive — registered in this vault, and inside its scope whenever that scope
  is non-empty. It MUST be enforced on BOTH write paths, so the inconsistent
  state cannot be stored at all: a registration or an edit of the configuration
  is rejected when it names a `default_agent` that is unknown or outside the
  current scope, and an edit to the scope is rejected when the proposed
  non-empty scope excludes the current `default_agent`. A scope edit MUST NOT be
  accepted and then leave the channel unable to run. Each rejection MUST name
  both sides **by label**, not by uid, so the owner sees the two ways forward:
  widen the scope, or change the default agent first.
- **A channel that can route nowhere MUST NOT start.** Three states mean it: it
  names no `default_agent` at all, its scope excludes the one it names, or that
  uid names no agent registered here. In each the runtime declines to start the
  adapter and records why, and the management surface reports the channel as
  not running. There is NO fallback agent: `default_agent` is a reference to an
  agent resource and a uid is minted per vault, so nothing a schema could name
  would stand for "the usual agent". Silence with a reason beats a bot that
  answers as an agent nobody chose.
- `agents: []` (dormant) MUST mean the channel drives nothing, and MUST fail
  early rather than per-turn: the runtime does not start its adapter, so no
  message is ever accepted only to be refused. The management surface reports it
  as not running. Widening the scope is how the owner brings it back.
- `agents: []` MUST be accepted on both write paths. It is the vault-wide
  meaning of dormant — this channel is off — and off MUST NOT also mean frozen:
  a channel the owner deliberately switched off MUST remain editable, so a wrong
  bot token or app secret can still be corrected without reactivating it
  first.
- A thread's sticky `/agent` choice MUST be dropped in favour of the channel
  default once the scope no longer admits it, so narrowing a scope takes effect
  on the next conversation rather than waiting on whoever set the preference.

Reach and the machine binding answer different questions and MUST never be
merged: reach (`enabled` + `scope`, on the resource row) says **which agents**
this channel may drive and whether it is live here, and is set per machine and
stays on it; the binding (`runs_on`, in the channel's config) says **which
machine** runs the adapter, and travels because it is one answer for the whole
vault. Giving the binding a home in `scope` would make "where does this apply"
carry two unrelated answers.

#### Scenario: a channel may only route to the agents in its scope
- **GIVEN** a paired channel whose scope names one of the two registered agents,
- **WHEN** the owner sends `/agent`, and then `/agent <the other one>`,
- **THEN** the listing and the selection card offer only the scoped agent, and
  the switch to the other one is refused — whether it is typed or tapped from a
  card rendered before the scope was narrowed.

#### Scenario: a channel's scope names agent resources, not agent keys
- **GIVEN** a running channel whose default agent is registered as an agent
  resource,
- **WHEN** the owner narrows the channel's scope to that agent resource — its
  uid, which is what the reach control offers,
- **THEN** the edit is accepted, the channel keeps running, and the scope
  reaches `/agent` translated into the agent key that surface speaks.

#### Scenario: a channel scoped to no agent is dormant
- **GIVEN** an enabled channel whose scope is set to the empty list,
- **WHEN** the channel runtime reconciles,
- **THEN** its adapter is never started and the channel reports as not running,
  so it accepts no turn it would have to refuse.

#### Scenario: reject narrowing a channel's scope past its default agent
- **GIVEN** a running channel whose `default_agent` is one registered agent,
- **WHEN** the owner narrows its scope to a non-empty set that excludes that
  agent,
- **THEN** the edit is rejected with a message naming both the default agent and
  the proposed scope — by the labels the owner gave them, not by uid — nothing
  is persisted, and the channel keeps running: the narrowing never silently
  takes the bot offline.

#### Scenario: a channel bound to an agent that does not exist is refused
- **GIVEN** a vault with at least one registered agent,
- **WHEN** a channel is registered, or edited, with a `default_agent` naming no
  agent resource in this vault,
- **THEN** the write is rejected and no row is created or changed, rather than
  the channel being stored and failing at its first turn.

#### Scenario: a channel bound to no agent never starts
- **GIVEN** an enabled channel whose `default_agent` is unset, or names an agent
  this machine does not have,
- **WHEN** the channel runtime reconciles,
- **THEN** its adapter is never started, the reason is recorded, and the channel
  reports as not running — it is never started against a substitute agent.

#### Scenario: edit a dormant channel's configuration
- **GIVEN** a channel the owner switched off by scoping it to no agent,
- **WHEN** the owner corrects a field of its configuration, such as its bot
  token ref,
- **THEN** the edit is accepted and the channel stays dormant — off is not
  frozen.

### Requirement: Bind each channel to the one machine that runs it
A channel MUST name the one machine that runs it. A channel's platform
identity — a polled bot, a held WebSocket — tolerates
exactly ONE consumer, so "which machine answers this bot" must have exactly one
answer, and that answer is written down. Its configuration carries `runs_on`,
the `machine_id` of the machine whose daemon starts this channel's adapter
(spec `vault-sync`, "Derive machine identity from the host"). It is configuration and not a
property of the row, because it MUST travel with the channel document — every
machine holding the document reads the same name, and every machine but one
finds it is not being named; reach MUST NOT travel and MUST NOT be made to carry
this.

- The binding MUST be authoritative for adapter startup. A runtime MUST start an
  adapter only for a channel whose `runs_on` is this machine's id, and MUST fail
  **closed** otherwise: an unknown machine, a retired one, and no binding at all
  all mean "not this machine", and none of them may be read as permission to
  start. Starting on a guess cannot be walked back — the platform has already
  been answered twice. The three cases are distinguished in what the surfaces
  report rather than in what the runtime does: **bound to another machine** is
  normal and says so, so a channel that is quiet here never looks like a channel
  that crashed here.
- **Unbound MUST run nowhere**, and MUST be reported rather than left to look
  like a stopped adapter, since a document naming no machine means the same
  thing on every machine that holds it. A channel registered through any Coffer
  surface MUST be bound to the registering machine at creation, so unbound is
  reached by import or by hand, not by using the product.
- A binding naming a machine no longer in the registry MUST be reported as a
  fault on the channel, distinctly from a channel that is merely bound
  elsewhere. Both run nowhere here; only one of them is somebody's mistake.
  Starting a channel on the grounds that nobody else claims it would be the
  rival-consumer failure arriving by the back door: every machine that cannot
  resolve the id would reason identically and they would all start.
- A `runs_on` that **cannot be a machine id** MUST NOT be honoured as a binding.
  A channel's configuration is a bag the system has written other things into
  before — the retired machine axis put ULIDs under this very key — so a value of
  the wrong shape names no machine that has ever existed and is a fossil, not a
  decision. Coffer MUST bind such a channel to this machine, the answer it would
  have given had the key been absent. This is the one case where an existing
  value is overwritten, and it is the one case where leaving it would silently
  stop a working bot on upgrade.
- Rebinding MUST converge without a restart and without a command that reaches
  another machine: changing `runs_on` is an ordinary configuration edit. The
  losing machine MUST stop its adapter within one reconcile tick of seeing the
  change; the gaining machine MUST start one within one tick of the converge
  round that brings the change to it. So the clean way to hand a channel over is
  to rebind it from the machine that currently holds it. Rebinding TO the
  machine one is sitting at while another machine still holds the channel is
  allowed and is sometimes the only option — the old machine may be the one that
  is broken — but it opens a window, bounded by that machine's sync interval, in
  which both adapters are live; the surface offering the rebind MUST say so.
- A channel's configuration MUST carry credential **references** only, never
  secret material, exactly as it did when it never travelled — the rule is
  unchanged, and travelling is what makes it load-bearing rather than merely
  tidy. Ciphertext for those refs travels only when the user opts the remote in
  to credentials, and a machine holding ciphertext without the master key MUST
  report those refs locked rather than failing decryption silently.
- A channel bound to another machine MUST NOT be refused by this machine's own
  preconditions. Its `default_agent` names an agent on the machine that runs it;
  validating that here would hold a good document out of the registry for a
  fault on nobody's machine.
- A channel's peer pairings MUST travel with the channel as synced state (spec
  `vault-sync`, "Carry channel pairings as platform identity"), because a channel that travels without them makes
  the owner re-pair from their phone every time it moves, and a rebind is meant
  to be one click. What travels is platform identity — chat id, sender id,
  display name. The active conversation pointer and the thread's sticky agent
  do not: both name machine-local things — a conversation the other machine
  does not have, an agent installed on this machine.

Two adapters can still be pointed at one bot identity only the way they always
could — by someone registering the same bot twice, by hand, under two names —
which no field inside Coffer could prevent.

#### Scenario: only the machine a channel names starts its adapter
- **GIVEN** an enabled channel bound to another machine's `machine_id`
- **WHEN** the runtime reconciles
- **THEN** no adapter is started here, and the management surface reports the
  channel as bound elsewhere rather than as stopped

#### Scenario: a channel bound to an unknown machine starts nowhere
- **GIVEN** an enabled channel whose binding names a machine the registry does
  not hold
- **WHEN** the runtime reconciles on any machine
- **THEN** no machine starts an adapter for it, and the channel is reported as
  bound to a machine that no longer exists

#### Scenario: an unbound channel runs nowhere and says so
- **GIVEN** an enabled channel whose configuration carries no binding
- **WHEN** the runtime reconciles
- **THEN** no adapter is started, and the channel's status carries a diagnostic
  naming the missing binding and the fix

#### Scenario: rebinding hands the channel over without a restart
- **GIVEN** an enabled channel running on this machine
- **WHEN** the user binds it to another machine
- **THEN** this machine stops its adapter on the next reconcile, without a
  daemon restart, and the channel's binding is what the next converge round
  publishes
