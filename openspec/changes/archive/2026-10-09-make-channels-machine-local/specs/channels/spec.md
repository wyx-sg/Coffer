## MODIFIED Requirements

### Requirement: Register channels as a secret-referencing resource kind
The system MUST provide a `channel` resource kind with per-type configuration, a
default agent key, and optional default agent configuration. Each child spec
states its own type's fields. Secrets MUST live in the secret store only;
configuration carries references, which are probed at registration time, and a
registration whose reference does not resolve is rejected with nothing
persisted.

A channel is addressed by its immutable `uid`
([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md));
its config is the type, the secret refs, the default agent and its config.
A channel is this machine's (see "Keep each channel on the machine that holds
it").

#### Scenario: register a telegram channel
- **GIVEN** a bot token stored under a secret ref
- **WHEN** the user registers a channel named `tg` with type telegram and that ref
- **THEN** the channel is listed with its config and enabled state
- **AND** the registration is audited

#### Scenario: reject a channel with a missing secret
- **GIVEN** no secret stored under the referenced name
- **WHEN** the user registers a channel pointing at it
- **THEN** registration fails with a secret error and nothing is persisted

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

#### Scenario: renaming a channel keeps its adapter running
- **GIVEN** an enabled channel with a running adapter
- **WHEN** the owner renames the channel
- **THEN** the adapter is not restarted, and it keeps answering under the new name

### Requirement: Restart a channel's adapter on demand
A running adapter reads its secret once, when it is built, and the lifecycle
only rebuilds an adapter when the channel's configuration or routing changes, so
the daemon MUST offer an explicit restart: `POST /api/v1/channels/{uid}/restart`
stops the channel's adapter and its inbound connection (a SeaTalk websocket),
forgets any failure it was waiting out, and starts them afresh at once from the
stored configuration and the secret as it is now. It answers whether the adapter
is running afterwards; a disabled channel stays stopped. The Channels page's **Reconnect** action MUST call it.

Replacing a secret under its existing ref MUST restart the adapter that uses it
without anyone asking: the daemon notices that the stored value changed and
rebuilds the adapter and, for SeaTalk, reconnects the websocket with the new
secret. Adapters, failure state and pending
pairing codes are all keyed by the channel's `uid`, so renaming a channel never
restarts it.

#### Scenario: a restart rebuilds the adapter on demand
- **GIVEN** an enabled channel with a running adapter
- **WHEN** the owner presses Reconnect
- **THEN** the old adapter stops and a new one starts and reads its secret again
- **AND** a channel waiting out a failed start is retried at once, and a disabled channel stays stopped

#### Scenario: a replaced secret restarts the adapter
- **GIVEN** a running channel whose bot token or app secret is stored under a ref
- **WHEN** a new value is stored under the same ref
- **THEN** the adapter is rebuilt with the new value, and for SeaTalk the websocket reconnects with it
- **AND** a channel whose secret did not change is left running

### Requirement: Manage channels from the Channels page
The Channels page MUST be a list beside a detail pane. The **list** shows every
channel as one row — its platform, its name and one line saying what state it is
in — grouped by that state (needs attention, connected, off), filterable by name, with a way to register a new channel (storing
secrets through the secret store); a row opens the channel. The **detail pane**
MUST show the open channel's status (adapter running, paired peer, and the
inbound state the channel's type reports — for SeaTalk, its websocket
connection) in a header that is the same in every state: the platform mark, the
name, a status pill, a meta line saying how it connects, a secondary **Send test**
(a test notification to its paired owner, see "Notify the paired owner on
demand") and a ⋯ menu holding only **Reconnect** (see "Restart a channel's
adapter on demand"). A control that cannot run in the current state MUST be
disabled rather than hidden, and a disabled **Send test** MUST say why in its
tooltip. The fix for a problem MUST sit in a banner between the header and the
tabs — one banner, one fix button (Reconnect now, Replace token or secret, Take
it back, Retry, Open Secrets, Generate pairing code), and for a
missing SeaTalk SDK also the hand-off "Ask an agent" with Copy prompt behind
its chevron. A channel that is off is not a problem: it
MUST show a quiet grey box with one small button, Turn on, instead of a banner.
Replacing the secret and deleting live in the Settings tab. The detail pane MUST split into two tabs, in this order: **Overview**, the
default, at the bare `/channels/<uid>` — a single column of sections — who can use it (the paired owners as a bordered
list, each with Remove, and Add owner below it), the default agent, the agents the
channel may drive (its reach) and one link, **Conversations from this channel →**, to the
Conversations page filtered by `?source=<uid>` — the conversations themselves are listed there
only ([chat](../chat/spec.md) "Show every agent's sessions on the Conversations page"); it lists no commands — and **Settings**, at `/channels/<uid>/settings` — the
settings below, its secrets, and the channel's deletion. Choosing a tab
changes the address and nothing else.

Settings are saved as they change, with no save button and no saved line; a save
that fails says so in a toast and the field keeps what was typed. The one
exception is the channel's two system prompts (see "Append the owner's system
prompt to a channel turn"): they are prose, so their **System prompts** section
shows them as written and edits them through an **Edit** button and a dialog
with Cancel and Save. They cover the channel's title, its type's plain settings (a
SeaTalk app id), its two group-gating switches, `require_mention` and
`ignore_other_mentions` (see "Configure when the bot answers in a group"), and
the rest of what this requirement and the others in this spec name as a channel
setting. A secret is shown masked and replaced through its own dialog, **in
place**: the new value MUST be written to the secret store under the ref the
channel already cites before the configuration is saved, and that ref MUST stay in
the saved configuration, so a rotation moves no secret and leaves the channel's
pairing untouched. A secret left blank rotates nothing.

Registering, editing, enabling, disabling, scoping and deleting a channel are the framework's own
lifecycle operations (see [resource-framework](../resource-framework/spec.md)), done on the
Channels page and over `/api/v1/resources`; pairing, restarting and notifying are the
channel routes under `/api/v1/channels/{uid}`; the `coffer channel` commands call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"). The page
MUST report the channel's configuration together with its status — adapter run state, paired
peer and the inbound state its type reports — with the group gating and the
idle period shown as the settings with their defaults filled in, as the daemon reads them. Saving
a setting changes only that setting: every switch, setting and ref it does not touch keeps its
stored value. `coffer secret set <ref>` rotates a secret under a ref the channel's
configuration cites.

The channel's status (`GET /api/v1/channels/{uid}/status`) carries its
**settings**: the typed reading of its stored configuration with every default
filled in (`TelegramChannelConfig` or `SeaTalkChannelConfig` in this capability's
contract). The Channels page starts every settings field from them, so a
default is written in one place, in the daemon, and no surface
keeps a copy. A stored configuration that no longer validates reports no
settings, and the page says so rather than guess.

Changing a channel's default agent or type settings is served by the detail page
and `PATCH /api/v1/resources/{uid}`.

#### Scenario: register a channel from the Add dialog and list it
- **GIVEN** a running daemon and a stored secret
- **WHEN** the user registers a channel in the Channels page's Add dialog and opens the list
- **THEN** the channel is created and appears in the list

#### Scenario: channel status reports runtime, pairing, and callback details
- **GIVEN** channels in various states
- **WHEN** the user queries status via REST and on the Channels page
- **THEN** adapter run state, paired peer, and the channel type's own inbound
  state are reported accurately

#### Scenario: a channel's settings arrive with their defaults filled in
- **GIVEN** a channel whose stored configuration names none of the optional settings
- **WHEN** its status is read
- **THEN** the settings carry every default (group gating, quiet windows, replies, idle period, directories, system prompts)
- **AND** the Channels page shows them without a default of its own

#### Scenario: rotating a channel secret keeps its refs and pairing
- **GIVEN** a registered telegram channel whose bot token is stored under a
  secret ref
- **WHEN** the owner enters a new bot token in the channel's replace-token dialog
  and confirms
- **THEN** the new token is written under the channel's existing ref first
- **AND** the channel's configuration is then saved to the same channel with
  every ref unchanged, so nothing its pairing hangs off moves

#### Scenario: the group-gating switches are edited in the Settings tab
- **GIVEN** a registered channel with `require_mention` on and `ignore_other_mentions` off (the defaults)
- **WHEN** the owner switches `require_mention` off and `ignore_other_mentions` on in the channel's Settings tab
- **THEN** the saved configuration carries both changes and every other setting and ref as it was

#### Scenario: a channel's lifecycle and reach run through the resource routes
- **GIVEN** a registered, enabled channel named `tg`
- **WHEN** the user, on the Channels page or over `/api/v1/resources`, sets its title to "Phone bot", scopes it to `codex` only, disables it and then deletes it
- **THEN** the title is saved with every ref unchanged, the channel's scope names only `codex`, and the adapter stops when it is disabled
- **AND** the removal deletes the channel and its peer binding, and each step is audited

#### Scenario: a channel's detail opens on Overview and keeps Settings on its own tab
- **GIVEN** a registered channel
- **WHEN** `/channels/<uid>/settings` is opened, and then the Overview tab is chosen
- **THEN** the first shows the channel's settings, and choosing Overview moves the address to the bare `/channels/<uid>`

#### Scenario: a channel's Overview links to its conversations instead of listing them
- **GIVEN** a channel that has started two conversations
- **WHEN** its Overview renders
- **THEN** it shows no list of conversations and one link, Conversations from this channel, to `/conversations?source=<uid>`

### Requirement: Treat an addressed group chat as its own peer
The system MUST treat a group chat as a first-class peer. When the paired owner
@mentions the bot (or the message is delivered as an addressed group event) the
bot answers there; the group becomes an additional peer in the channel's pairings on this
machine, keyed by the group chat id and inheriting
the owner's `sender_id`.

#### Scenario: the owner @mentions the bot in a group main chat
- **GIVEN** a paired channel and a group chat with no active thread
- **WHEN** the owner @mentions the bot in the group's main chat
- **THEN** a turn runs, no thread history is read, and a peer is recorded for the
  group chat inheriting the owner's `sender_id`
- **AND** where the platform threads group replies (SeaTalk) the reply is delivered
  into a thread rather than the group main chat, while an ordinary Telegram group,
  which has no thread to put it in, is answered in the chat itself

### Requirement: Limit the agents a channel may drive to its scope
A channel MUST carry the framework's `scope`
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)),
one allow-list of agents, read as **the agents this channel may drive**. Every
other kind's scope names the agents a resource is *delivered to*; a channel is
consumed by no agent — it is an inbound surface — so the list is inverted rather
than borrowed, and the spec says so explicitly because a reader who assumes the
usual reading gets it backwards. That inverted reading is the whole of what a
channel's scope says. Scope is reach, and reach is machine-local like the
channel itself.

- An unrestricted scope MUST mean every registered agent. A scope is never an
  empty list: `agents: []` is refused on both write paths with `SCOPE_INVALID`,
  as on every kind.
- `agents: [<agent>, …]` MUST narrow `/new <agent>` at every surface that
  names an agent: the list of valid names an unknown one is answered with, and
  the validation of a chosen name. They MUST read one narrowed set — a list that
  offers an agent the next check rejects is the specific failure this requires.
- **One vocabulary above the binding.** A scope and a `default_agent` both name
  agent **uids**, which is also what a reach picker offers, so every comparison
  between them is made directly and no translation exists to get backwards. A
  uid this vault does not hold admits no agent at all.
- **One crossing, below it.** `/new <agent>`, the sticky per-thread choice and the
  turn router all speak the agent **key** the turn platform routes on. That key
  MUST be derived from the uid at exactly ONE place — the runtime gate, where the
  resource row becomes a live binding — and nothing below that point may hold a
  uid. Two agent resources of the same type collapse to one key there. While the
  two vocabularies met in several places at once, each of them compared a scope
  written in one to a default written in the other: the only narrowing a user
  could express was refused, and the value accepted in its place was one the
  reach picker then had to render as an agent registered nowhere.
- **The invariant:** a channel's `default_agent` MUST be an agent the channel
  may drive — registered in this vault, and inside its scope. It MUST be enforced on BOTH write paths, so the inconsistent
  state cannot be stored at all: a registration or an edit of the configuration
  is rejected when it names a `default_agent` that is unknown or outside the
  current scope, and an edit to the scope is rejected when the proposed
  scope excludes the current `default_agent`. A scope edit MUST NOT be
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
- A channel that should drive nothing is **switched off**, the same switch every
  toggleable kind has, and there is no second way to say it: a switched-off
  channel does not start its adapter, so no message is ever accepted only to be
  refused, and the management surface reports it as not running. Off keeps the
  scope that was chosen.
- Off MUST NOT also mean frozen: a channel the owner deliberately switched off
  MUST remain editable, so a wrong bot token or app secret can still be
  corrected without reactivating it first.
- A thread's sticky agent choice MUST be dropped in favour of the channel
  default once the scope no longer admits it, so narrowing a scope takes effect
  on the next conversation rather than waiting on whoever set the preference.


#### Scenario: a channel may only route to the agents in its scope
- **GIVEN** a paired channel whose scope names one of the two registered agents,
- **WHEN** the owner sends `/new nope`, and then `/new <the other one>`,
- **THEN** the list of valid names offers only the scoped agent, and the switch
  to the other one is refused.

#### Scenario: a channel's scope names agent resources, not agent keys
- **GIVEN** a running channel whose default agent is registered as an agent
  resource,
- **WHEN** the owner narrows the channel's scope to that agent resource — its
  uid, which is what the reach control offers,
- **THEN** the edit is accepted, the channel keeps running, and the scope
  reaches `/new <agent>` translated into the agent key that surface speaks.

#### Scenario: an empty agent list is refused for a channel
- **GIVEN** a running channel whose scope names one agent,
- **WHEN** the owner sets its scope to `{"agents": []}`, on the scope route or in
  a registration,
- **THEN** the write is refused with `422` `SCOPE_INVALID`, nothing is persisted
  and the channel keeps running; a channel that should drive nothing is switched
  off, and then its adapter is not started and it reports as not running.

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

#### Scenario: edit a switched-off channel's configuration
- **GIVEN** a channel the owner switched off,
- **WHEN** the owner corrects a field of its configuration, such as its bot
  token ref,
- **THEN** the edit is accepted and the channel stays off — off is not
  frozen.

## ADDED Requirements

### Requirement: Keep each channel on the machine that holds it
A channel MUST be a machine-local resource, like an agent: its file is under
`local/resources/channel/` and its pairings under `local/channel-peers.json`,
keyed by the channel's uid; neither is in the vault, committed or synced
([Channels Are Machine-Local Resources](../../../docs/decisions/channels-are-machine-local-resources.md)).
A bot identity tolerates one consumer, and everything a channel names — its
default agent, its working directories, its paired chats — is this machine's.
A channel that is switched on runs on the machine that holds it; there is no
setting naming another machine. Using the same bot on another machine means
registering the channel there (its secret can be picked from the stored ones)
and pairing again.

#### Scenario: a channel stays on the machine that registered it
- **GIVEN** a vault that converges with a remote
- **WHEN** the owner registers and pairs a channel
- **THEN** the channel's file and its pairings are written under `local/` and nothing about the channel is committed to the vault

#### Scenario: an enabled channel runs on the machine that holds it
- **GIVEN** an enabled channel whose default agent is registered on this machine
- **WHEN** the channel runtime reconciles
- **THEN** its adapter is started here, with no machine to name first

## REMOVED Requirements

### Requirement: Bind each channel to the one machine that runs it
**Reason**: A channel no longer travels, so there is no other machine to tell apart; `runs_on` and every state built on it (bound elsewhere, unbound, unknown machine, Run it here) are gone.
**Migration**: On first start each machine moves the vault channels bound to it, or to no machine, to `local/` without `runs_on`, then deletes every channel file and pairing document from the vault in one commit.
