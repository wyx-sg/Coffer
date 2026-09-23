## MODIFIED Requirements

### Requirement: Route the owner's messages into a turn-platform conversation
Inbound text from the paired peer MUST route to the peer's active conversation,
creating one on first use via the turn platform's standard
conversation-creation path (default agent validated by the agent registry). The
channel layer MUST reach agents only through the turn platform's seams:
conversation service, turn orchestrator (spec `chat`). The conversation is an
ordinary one, recorded in the vault with full history. When the active
conversation has been deleted, the peer's next message creates a fresh
conversation with the thread's agent — its sticky `/agent` choice, else the
channel's default agent; when the daemon restarts mid-turn, the turn
platform's startup sweep marks the orphaned turn failed and the channel
conversation simply continues on the next message.

#### Scenario: a paired message gets an agent reply
- **GIVEN** a paired channel whose default agent is available
- **WHEN** the peer sends a text message
- **THEN** a turn runs in the peer's conversation and the reply is delivered
  to the IM chat

#### Scenario: the channel conversation is a normal chat conversation
- **GIVEN** a channel conversation created by first contact
- **WHEN** the user opens the turn platform's conversation APIs
- **THEN** the conversation and its messages are listed like any other

### Requirement: Answer the conversation commands from any paired chat
Commands `/new`, `/stop`, `/status`, `/help` MUST work from any paired chat.
`/new` starts a fresh conversation with the thread's current agent (its sticky
`/agent` choice, else the channel's default agent), `/stop`
interrupts the running turn, `/status` reports the active conversation, agent,
and turn state, and `/help` lists the commands. `/stop` and `/new` take effect
even while a turn is running; other messages join the conversation's pending
queue (spec `chat` — the one the web shows; the channel refuses past 10 waiting
and tells the peer the channel is busy) and run in order. A message arriving
exactly when the previous turn finishes joins the queue rather than racing it:
turns for one conversation never overlap.

These are the commands that need nothing of the conversation; the ones that
configure the conversation the chat is bound to — `/agent`, `/model`, `/effort`
— are specified in "Switch the conversation's agent from chat" and "Switch the
model and reasoning effort from chat", and `/save` in "Save a sent document into
a collection". All of them live on one roster (see "Register the bot's command
menu and profile from one roster"), so none of the lists derived from it can go
stale.

#### Scenario: /new starts a fresh conversation
- **GIVEN** a paired channel with an active conversation
- **WHEN** the peer sends `/new`
- **THEN** a new conversation with the thread's current agent (the default
  agent when none was chosen) becomes active and the old one remains in history

#### Scenario: /stop interrupts a running turn
- **GIVEN** a turn in progress
- **WHEN** the peer sends `/stop`
- **THEN** the turn ends as interrupted and the chat is responsive again

#### Scenario: messages during a turn are queued in order
- **GIVEN** a turn in progress
- **WHEN** the peer sends two more messages
- **THEN** they run as consecutive turns in arrival order after the first ends

#### Scenario: the queue is bounded and overflow is reported
- **GIVEN** a full message queue
- **WHEN** the peer sends another message
- **THEN** the message is dropped and the peer is told the channel is busy

### Requirement: Manage channels from the Channels page and the CLI
The Channels page MUST list channels, register new ones (storing secrets
through the credential store), show status (adapter running, paired peer,
ingress facts the channel's type has to report), issue pairing codes, toggle
enable/disable, bind each channel to the machine that runs it (see "Bind
each channel to the one machine that runs it"), edit a channel, send a test
notification to its paired owner (see "Notify the paired owner on demand"), and
delete it. Editing changes the channel's default agent and its type's plain
settings (a SeaTalk app id), and rotates a secret **in place**: the new value
MUST be written to the credential store under the ref the channel already cites
before the configuration is saved, and the saved configuration MUST keep every
existing ref, so a rotation moves no secret and leaves the channel's machine
binding and pairing untouched. A secret field left blank rotates nothing. The CLI MUST offer parity:
`coffer channel list / register / bind / pair / status / notify`.

#### Scenario: register and list channels from the command line
- **GIVEN** a running daemon and a stored credential
- **WHEN** the user runs `coffer channel register` and `coffer channel list`
- **THEN** the channel is created and appears in the listing

#### Scenario: channel status reports runtime, pairing, and callback details
- **GIVEN** channels in various states
- **WHEN** the user queries status via REST and CLI
- **THEN** adapter run state, paired peer, and the channel type's own ingress
  facts are reported accurately

#### Scenario: rotating a channel secret keeps its refs and pairing
- **GIVEN** a registered telegram channel whose bot token is stored under a
  credential ref
- **WHEN** the owner enters a new bot token in the Channels page's edit dialog
  and saves
- **THEN** the new token is written under the channel's existing ref first
- **AND** the channel's configuration is then saved to the same channel with
  every ref unchanged, so nothing its pairing and binding hang off moves

### Requirement: Tell a channel-driven agent it is on a chat channel
A channel-originated turn MUST tell the agent it is bridged to a chat channel,
not a terminal: the agent receives a short system-prompt note carrying the
channel name and mobile-chat guidance — keep replies concise, and it cannot
click permission or confirmation dialogs on the user's computer (they may be
away from it). This prevents terminal-sized replies and silent waits on
un-clickable dialogs. Web-UI turns are unaffected — the note rides only on a
conversation whose `channel_uid` is set, and names the channel by its current
label.

#### Scenario: the channel-driven agent is told it is on a chat channel
- **GIVEN** a channel-originated conversation
- **WHEN** a turn is driven from the channel
- **THEN** the agent receives a system-prompt note naming the channel and telling
  it to keep replies concise and that it cannot click the user's OS dialogs,
  while a web-UI conversation gets no such note

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
  bot token or tunnel token can still be corrected without reactivating it
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
identity — a polled bot, a webhook endpoint, a held WebSocket — tolerates
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
