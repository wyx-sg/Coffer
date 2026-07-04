# Feature Specification: Channels

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/channels`
**Created**: 2026-06-12
**Status**: Accepted
**Input**: User description: "Coffer needs messaging channels — Telegram and
SeaTalk first — so the owner can talk to any agent on the chat platform from
the IM apps they already use and
receive notifications pushed by Coffer. The architecture must stay uniform:
more channels and more agents will be added, so a new channel never touches
agent code and a new agent never touches channel code."

A channel is a registered resource (`channel:<name>`) that connects one IM
account to Coffer's chat platform (spec 008). Messages from the paired owner
become turns in an ordinary conversation; the agent's reply goes back to the
IM chat. The channel layer and the agent layer meet only at the chat
platform's existing seams — conversation creation and the turn event stream
— so the cost of N channels and M agents is N + M, never N × M.

> **Note ([ADR-024](../../docs/decisions/ADR-024-builtin-agent-is-internal-capability.md)).**
> Mentions of the `builtin` agent below as a routable channel target reflect the
> behaviour shipped when this spec landed. ADR-024 retires the built-in agent as a
> chat persona, so channels route to **managed** agents (Claude Code, Codex, …)
> only; the built-in model is now an internal `coffer__*` capability, not a chat
> target. The channel observe mechanics over the shared seams are
> unchanged.

## User Scenarios & Testing

### User Story 1 — Register a channel (Priority: P1)

The user creates a Telegram bot with BotFather (or a SeaTalk app on the
SeaTalk Open Platform), stores its secret in Coffer's credential store, and
registers a channel resource referencing it. The channel appears in the
Channels page and CLI with its enabled state, and validation rejects a
channel whose credential reference does not resolve.

**Why this priority**: Nothing else works until a channel exists. Registration
also proves the resource-framework integration (lifecycle, audit, credential
probing) end to end.

**Independent Test**: Store a bot token under a credential ref, register
`channel:my-telegram` pointing at it, see it listed via REST, CLI, and the
Channels page; attempt a registration with a dangling ref and see it rejected
with no row persisted.

**Covering scenarios**:

- register a telegram channel
- reject a channel with a missing credential
- register and list channels from the command line

---

### User Story 2 — Pair the owner (Priority: P1)

Coffer is a single-user vault, so each channel obeys exactly one person. The
user asks Coffer for a pairing code (UI button or CLI), sends that code to the
bot from their own IM account, and the account becomes the channel's owner.
Messages from anyone else are ignored silently — the bot never reveals it is
alive to strangers. Re-issuing a code and pairing again rebinds the channel to
the new sender.

**Why this priority**: Pairing is the security boundary. A reachable bot wired
to a personal vault must fail closed before any message flows.

**Independent Test**: Issue a pairing code, send it from a fake IM account,
observe the confirmation reply and the peer recorded; send messages from a
second account and observe no reply and no turn started.

**Covering scenarios**:

- issue a pairing code
- pair by sending the code
- ignore messages from strangers
- an expired or wrong code does not pair

---

### User Story 3 — Chat with an agent from the IM app (Priority: P1)

The paired owner sends a text message to the bot. The channel routes it into
the peer's long-lived conversation — created on first contact with the
channel's configured default agent — and the agent's reply arrives back in
the IM chat, rendered for that platform (Telegram HTML, SeaTalk Markdown) and
chunked when long. On Telegram the bot shows progress while the turn runs and
streams tool activity into one editable status message; on SeaTalk, which
cannot edit messages, the bot acknowledges with a typing indicator and sends
the finished reply. The same conversation is visible in the Chat page with
full history.

**Why this priority**: This is the product: the vault's agents reachable from
the IM apps the user already lives in.

**Independent Test**: With a paired channel whose agent is scripted, send
"hello", observe a reply in the fake IM within the turn, and the same
exchange visible through the chat platform's REST API.

**Covering scenarios**:

- a paired message gets an agent reply
- the channel conversation is a normal chat conversation
- a long reply is chunked for the platform
- markdown rendering degrades by channel capability
- a turn error is reported to the IM chat

---

### User Story 4 — Control the conversation with commands (Priority: P2)

The owner manages the conversation without leaving the IM app: `/new` starts
a fresh conversation with the channel's default agent, `/stop` interrupts the
running turn, `/status` reports the active conversation, agent, and turn
state, `/help` lists the commands. Messages sent while a turn is running are
queued and answered in order; the queue is bounded and overflow is reported.

**Why this priority**: Without `/new` and `/stop` the single long-lived
conversation becomes a trap; queueing makes concurrent typing predictable.

**Independent Test**: Start a slow scripted turn, send `/stop`, observe the
turn end as interrupted; send `/new`, observe a fresh conversation recorded
for the peer; flood messages during a turn and observe queued execution and
an overflow notice.

**Covering scenarios**:

- /new starts a fresh conversation
- /stop interrupts a running turn
- messages during a turn are queued in order
- the queue is bounded and overflow is reported

---

### User Story 6 — Receive notifications (Priority: P2)

Coffer can push a message to a channel's paired owner without any inbound
message: `coffer channel notify my-telegram "build finished"` or the matching
REST call delivers the text to the IM chat. This is the outbound foundation —
any future feature that wants to alert the user reuses it.

**Why this priority**: Notification is half the reason channels exist, and the
seam (a notify entry point on the channel service) must be proven now.

**Independent Test**: With a paired channel, call notify via CLI and REST,
observe the message in the fake IM; call it on an unpaired channel and
observe a clean error.

**Covering scenarios**:

- notify delivers to the paired owner
- notify on an unpaired channel fails cleanly

---

### User Story 7 — SeaTalk reaches the local daemon (Priority: P2)

SeaTalk delivers events only by webhook, so Coffer ships a callback listener:
a separate small process, spawned by the daemon while any SeaTalk channel is
enabled, that serves only signed callback paths on a local port. The user
points a tunnel (cloudflared, ngrok) at that port and registers the public
URL on the SeaTalk Open Platform. The listener answers the platform's
verification handshake, verifies every event's signature, and forwards valid
events to the daemon over loopback. Events with a bad signature are rejected
and never reach the daemon.

**Why this priority**: Without ingress there is no SeaTalk inbound at all.
The separate-process shape is a constitutional requirement for
public-reachable surfaces.

**Independent Test**: Start the listener with a known signing secret, POST the
verification challenge and see it echoed; POST a signed event and see it
forwarded; POST a tampered event and see 401 with nothing forwarded.

**Covering scenarios**:

- the callback listener answers the verification handshake
- a signed seatalk event reaches the channel
- a tampered seatalk event is rejected
- the listener runs only while a seatalk channel is enabled

---

### User Story 8 — Operate channels day to day (Priority: P3)

Disabling a channel stops its adapter (polling halts, events are refused);
enabling restarts it; deleting the channel stops the adapter and removes its
peer binding. The Channels page and `coffer channel status` show whether the
adapter is running, who is paired, and — for SeaTalk — the callback port and
path to point the tunnel at.

**Why this priority**: Lifecycle honesty (status that tells the truth,
disable that actually stops traffic) is what makes the feature operable.

**Covering scenarios**:

- disable stops the adapter and enable restarts it
- deleting a channel cleans up its runtime and peer
- channel status reports runtime, pairing, and callback details

---

### User Story 9 — Switch agent and model from chat (Priority: P2)

The owner steers the entrypoint without leaving the IM app. `/agent codex`
switches the conversation to Codex; `/model opus` changes the model. Switching
the agent starts a fresh conversation pinned to the new choice (the agent is
fixed for a conversation's life) and the choice sticks for later messages and
`/new`; switching the model takes effect on the next turn in the same
conversation. Each command with no argument reports the current value and the
available choices.

**Why this priority**: A channel is an entrypoint _manager_, not a single fixed
wire. Routing to a chosen agent with a chosen model is what makes one paired
chat a switchboard for every agent the vault exposes.

**Independent Test**: With a paired channel and two scripted providers, send
`/agent <second>` and observe a fresh conversation pinned to it and the next
message answered by it; send `/model <name>` and observe the next turn use it.

**Covering scenarios**:

- /agent switches the agent and sticks
- /agent rejects an unknown agent
- /model switches the model for the next turn

---

### User Story 10 — Know who drove what, and when a turn is done (Priority: P2)

Because the entrypoint is remote-reachable, every turn a channel message drives
is recorded in the audit log
with the channel, peer, and agent — answering "who drove which agent through
which channel". And because some platforms cannot
edit messages and show nothing while a long bridged turn runs, a turn that
needs an end-of-turn signal pushes one compact summary to the chat: the
failure, the stop, the tool-iteration limit, or — on a channel that cannot edit
— a done marker with tool count, duration, and tokens. A clean success on an
edit-capable channel needs none: the live progress and the reply already
signalled it.

**Why this priority**: An entrypoint manager's two unclaimed differentiators are
first-class auth/audit and a reliable completion signal; both must be true on
every channel, including the silent ones.

**Independent Test**: Drive a turn from a paired channel and observe a
turn-started audit record with the channel, peer, and agent; observe a completion
summary message after the turn on a channel that cannot edit messages.

**Covering scenarios**:

- a channel-driven turn is audited with channel, peer, and agent
- a completion summary is sent on a channel that cannot edit messages
- a clean success on an edit-capable channel sends no completion summary
- a group member who is not the paired sender is ignored

---

### Edge Cases

- A message arriving exactly when the previous turn finishes joins the queue,
  not a race: turns for one conversation never overlap (platform guarantee).
- The IM platform rejects a formatted message → the channel retries the same
  content as plain text before reporting failure.
- The daemon restarts mid-turn → the platform's startup sweep marks the
  orphaned turn failed; the channel conversation simply continues on the next
  message.
- A pairing code expires (1 hour) or suffers repeated wrong guesses → the
  code is invalidated; a fresh code must be issued.
- The active conversation is deleted from the Chat page → the peer's next
  message creates a fresh conversation with the default agent.
- Telegram long polling loses connectivity → the adapter backs off
  exponentially and resumes; no inbound message is double-processed after
  reconnect (update offset is committed only after dispatch).
- SeaTalk sender rate limits (HTTP 429) → outbound sends back off and retry.
- Non-text inbound content (images, files, voice) → the channel replies that
  only text is supported in this version.

## Requirements

### Functional Requirements

- **FR-001**: A `channel` resource kind exists with per-type configuration
  (Telegram: bot token reference; SeaTalk: app id, app secret reference,
  signing secret reference), a default agent key, and optional default agent
  configuration. Secrets live in the credential store only; configuration
  carries references, which are probed at registration time.
- **FR-002**: Channel lifecycle (register, enable, disable, update, delete)
  rides the generic resource framework, with audit on every transition.
- **FR-003**: Pairing: the daemon issues an 8-character single-use code
  (unambiguous alphabet, 1-hour TTL, bounded wrong-guess attempts) per
  channel; a message consisting of the code binds its sender as the channel's
  sole peer, replacing any previous peer; all other senders are ignored
  silently.
- **FR-004**: Inbound text from the paired peer routes to the peer's active
  conversation, creating one on first use via the chat platform's standard
  conversation-creation path (default agent validated by the agent registry).
  The channel layer reaches agents only through the chat platform's seams:
  conversation service, turn orchestrator.
- **FR-005**: Replies render per channel capability: Telegram converts
  markdown to Telegram HTML with a plain-text fallback and 4000-character
  paragraph-boundary chunking, and streams tool progress into one throttled
  editable status message whose lines describe each call from its input (e.g.
  `⏳ Bash · list the desktop`, `✅ Read · wedding.json`); SeaTalk sends markdown
  with 4096-byte chunking and
  signals progress with a typing indicator. Capabilities are declared by the
  adapter, not special-cased in the core.
- **FR-006**: Commands `/new`, `/stop`, `/status`, `/help` work from any
  paired chat. `/stop` and `/new` take effect even while a turn is running;
  other messages queue (FIFO, bounded at 10) and run in order.
- **FR-008**: A notify entry point (REST + CLI) delivers arbitrary text to a
  channel's paired peer, independent of any conversation.
- **FR-009**: The SeaTalk callback listener is a separate process serving only
  `POST /seatalk/{channel}`: it answers `event_verification` with the echoed
  challenge, verifies `sha256(body + signing_secret)` signatures, forwards
  valid events to the daemon over loopback with the daemon token, and rejects
  everything else. The daemon spawns it while at least one SeaTalk channel is
  enabled and stops it otherwise.
- **FR-010**: Telegram inbound uses long polling with the update offset
  committed only after dispatch; adapters reconnect with exponential backoff
  and never crash the daemon.
- **FR-011**: The Channels page lists channels, registers new ones (storing
  secrets through the credential store), shows status (adapter running,
  paired peer, callback endpoint), issues pairing codes, and toggles
  enable/disable. CLI parity: `coffer channel list / register / pair /
status / notify`.
- **FR-012**: Channel events are audited: pairing issued, paired,
  notification sent — alongside the automatic resource-lifecycle audit.
- **FR-013**: The owner switches the conversation's agent from chat. `/agent`
  with no argument reports the current agent and the registry's available agent
  keys; `/agent <key>` validates the key against the agent registry and, on
  success, records it as the peer's sticky preference and opens a fresh
  conversation pinned to it (an existing conversation's agent cannot change), so
  subsequent messages and `/new` use the chosen agent until it is switched
  again. An unknown key is rejected with the valid keys listed; no channel-side
  code is added per agent. On a transport that `supports_buttons` (FR-018),
  `/agent` with no argument renders the choices as an interactive selection card
  instead of a text list; tapping a button performs the same switch.
- **FR-014**: The owner gate verifies sender identity, not only chat identity.
  Every inbound envelope carries a `sender_id` (Telegram `from.id`, SeaTalk
  `employee_code`); pairing records it on the peer, and an inbound message is
  accepted only when its `chat_id` matches and — when the peer has a stored
  `sender_id` — its sender matches. A peer paired before this requirement (no
  stored `sender_id`) degrades to the chat-id-only gate. One channel-driven
  event is audited beyond FR-012: a turn started by an inbound message
  (channel, peer, agent, conversation).
- **FR-015**: After a turn the channel sends one compact completion summary as a
  fresh message when the turn needs an end-of-turn signal: a failure reports the
  error, an interrupt reports the stop, the tool-iteration limit reports the
  limit, and — on a channel that cannot edit messages — a success reports a done
  marker with tool count, duration, and token usage. A clean success on an
  edit-capable channel sends no summary: the live progress status and the reply
  itself already signalled completion, so the summary would be noise. This is the
  end-of-turn signal on platforms that cannot edit messages and show nothing
  while a long bridged turn runs.
- **FR-017**: The owner switches the model from chat. `/model` with no argument
  reports the current model; `/model <name>` for the builtin agent resolves the
  name against the model registry and sets the conversation's model override,
  and for a bridged agent stores the raw upstream model string passed through to
  the CLI. A model switch takes effect on the next turn in the same conversation
  (the model is re-read each turn, unlike the agent and working directory). An
  invalid builtin model is rejected against the registry; a bad bridged model
  string surfaces as the CLI's own error relayed to the chat. On a transport
  that `supports_buttons` (FR-018), `/model` with no argument renders best-effort
  quick-picks — the managed agent's active provider profile model/fast_model
  (ADR-032) — as a selection card (free-text `/model <name>` still works); with
  no suggestions it falls back to the text report.
- **FR-018**: On a transport that declares the `supports_buttons` capability,
  the core MAY render a command's choice list as an **interactive selection
  card** (Telegram inline keyboard, SeaTalk interactive message). A button tap
  arrives as a normalized callback carrying an opaque value; the core
  **owner-gates it exactly like a message** (chat + sender identity, FR-014)
  before routing it to the same switch the text command performs. A tap never
  pairs, and an unsupported transport silently keeps the text path. This
  realizes the interactive-button capability that
  [ADR-014](../../docs/decisions/ADR-014-channel-adapter-framework.md)'s
  `ChannelCapabilities` anticipated ("show buttons?").
- **FR-019**: A channel-originated turn tells the agent it is bridged to a chat
  channel, not a terminal: the agent receives a short system-prompt note carrying
  the channel name and mobile-chat guidance — keep replies concise, and it cannot
  click permission or confirmation dialogs on the user's computer (they may be
  away from it). This prevents terminal-sized replies and silent waits on
  un-clickable dialogs. Web-UI turns are unaffected — the note rides only on a
  conversation whose `channel_name` is set.

### Key Entities

- **Channel** — resource `channel:<name>`; config = type, credential refs,
  default agent + config.
- **ChannelPeer** — the paired owner of a channel: `(resource, chat_id)`,
  display name, paired-at, pointer to the active conversation, the paired
  sender's identity (`sender_id`), and sticky preferences (chosen agent).
  One per channel today; keyed by chat so group chats can become
  peers later without a schema change.
- **InboundMessage / InboundCallback / OutboundMessage** — the normalized
  envelopes every adapter produces and consumes; the core never sees platform
  payloads. Inbound carries the sender's identity (`sender_id`) for the owner
  gate. An `InboundCallback` is a selection-card button tap (an opaque `data`
  value instead of text, FR-018); outbound text MAY carry `ChoiceButton`s, which
  a button-capable transport renders as a selection card.
- **ChannelCapabilities** — what an adapter declares it can do
  (edit messages, interactive buttons via `supports_buttons`, typing indicator);
  the core picks rendering strategies from it.
- **PairingCode** — in-memory, single-use, per-channel; never persisted.

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user can register a Telegram channel,
  pair, and get an agent reply in under 10 minutes following the quickstart.
- **SC-002**: A stranger messaging the bot produces zero observable response
  and zero turns, while the owner's traffic is unaffected.
- **SC-003**: Adding a hypothetical third channel type requires implementing
  one adapter + one config schema and touching no agent or conversation
  code (demonstrated by the test-only fake channel the suite uses).
- **SC-004**: Any agent registered on the chat platform is reachable from any
  channel with no channel-side code change (demonstrated by driving a channel
  against a scripted second provider in tests).
- **SC-005**: Every acceptance scenario below is covered by at least one
  test; `make verify` passes.
- **SC-006**: From one paired chat the owner reaches every registered agent
  with a chosen model (demonstrated by driving two scripted providers in tests).
- **SC-007**: Every channel-driven turn
  is queryable in the audit log by channel, peer, and agent; and on a channel
  that cannot edit messages every turn ends with a completion summary in the
  chat (demonstrated against the edit-incapable fake adapter), while a clean
  success on an edit-capable channel sends none.

## Acceptance Scenarios

### Scenario: register a telegram channel

- **Given** a bot token stored under a credential ref
- **When** the user registers `channel:tg` with type telegram and that ref
- **Then** the channel is listed with its config and enabled state
- **And** the registration is audited

### Scenario: reject a channel with a missing credential

- **Given** no credential stored under the referenced name
- **When** the user registers a channel pointing at it
- **Then** registration fails with a credential error and nothing is persisted

### Scenario: register and list channels from the command line

- **Given** a running daemon and a stored credential
- **When** the user runs `coffer channel register` and `coffer channel list`
- **Then** the channel is created and appears in the listing

### Scenario: issue a pairing code

- **Given** a registered channel
- **When** the user requests a pairing code
- **Then** an 8-character code with an expiry is returned and audited

### Scenario: pair by sending the code

- **Given** an issued pairing code
- **When** a sender messages the bot with exactly that code
- **Then** the sender becomes the channel's peer and receives a confirmation
- **And** the pairing is audited and the code cannot be reused

### Scenario: ignore messages from strangers

- **Given** a paired channel
- **When** a different account messages the bot
- **Then** no reply is sent and no turn or conversation is created

### Scenario: an expired or wrong code does not pair

- **Given** an issued pairing code
- **When** a sender submits a wrong guess repeatedly or the code has expired
- **Then** pairing fails, the sender gets no reply, and the code is invalidated

### Scenario: a paired message gets an agent reply

- **Given** a paired channel whose default agent is available
- **When** the peer sends a text message
- **Then** a turn runs in the peer's conversation and the reply is delivered
  to the IM chat

### Scenario: the channel conversation is a normal chat conversation

- **Given** a channel conversation created by first contact
- **When** the user opens the chat platform's conversation APIs
- **Then** the conversation and its messages are listed like any other

### Scenario: a long reply is chunked for the platform

- **Given** a scripted agent reply longer than the platform limit
- **When** the turn completes
- **Then** the reply arrives as multiple messages split on paragraph
  boundaries, in order

### Scenario: markdown rendering degrades by channel capability

- **Given** the same markdown reply
- **When** delivered through telegram and through a channel without rich text
- **Then** telegram receives HTML (falling back to plain text if rejected)
  and the other channel receives its declared format

### Scenario: a turn error is reported to the IM chat

- **Given** a scripted agent that fails mid-turn
- **When** the peer sends a message
- **Then** the IM chat receives a short error notice and the channel stays up

### Scenario: /new starts a fresh conversation

- **Given** a paired channel with an active conversation
- **When** the peer sends `/new`
- **Then** a new conversation with the default agent becomes active and the
  old one remains in history

### Scenario: /stop interrupts a running turn

- **Given** a turn in progress
- **When** the peer sends `/stop`
- **Then** the turn ends as interrupted and the chat is responsive again

### Scenario: messages during a turn are queued in order

- **Given** a turn in progress
- **When** the peer sends two more messages
- **Then** they run as consecutive turns in arrival order after the first ends

### Scenario: the queue is bounded and overflow is reported

- **Given** a full message queue
- **When** the peer sends another message
- **Then** the message is dropped and the peer is told the channel is busy

### Scenario: notify delivers to the paired owner

- **Given** a paired channel
- **When** notify is called via REST and via CLI
- **Then** the text arrives in the IM chat both times and is audited

### Scenario: notify on an unpaired channel fails cleanly

- **Given** a channel with no paired peer
- **When** notify is called
- **Then** the call fails with a clear error and nothing is sent

### Scenario: the callback listener answers the verification handshake

- **Given** a running callback listener configured for a channel
- **When** SeaTalk posts an `event_verification` callback
- **Then** the listener echoes the challenge with HTTP 200

### Scenario: a signed seatalk event reaches the channel

- **Given** a listener configured with a channel's signing secret
- **When** a correctly signed message event is posted
- **Then** it is forwarded to the daemon and processed as inbound

### Scenario: a tampered seatalk event is rejected

- **Given** a running callback listener
- **When** an event with an invalid signature is posted
- **Then** the listener responds 401 and nothing reaches the daemon

### Scenario: the listener runs only while a seatalk channel is enabled

- **Given** a daemon with one enabled seatalk channel
- **When** the channel is disabled
- **Then** the listener process stops; enabling it again restarts the listener

### Scenario: disable stops the adapter and enable restarts it

- **Given** an enabled telegram channel with a running adapter
- **When** the user disables and re-enables the channel
- **Then** polling stops while disabled and resumes after enabling

### Scenario: deleting a channel cleans up its runtime and peer

- **Given** an enabled, paired channel
- **When** the user deletes the channel resource
- **Then** the adapter stops and the peer binding is removed

### Scenario: channel status reports runtime, pairing, and callback details

- **Given** channels in various states
- **When** the user queries status via REST and CLI
- **Then** adapter run state, paired peer, and (for seatalk) the callback
  port and path are reported accurately

### Scenario: /agent switches the agent and sticks

- **Given** a paired channel with a second scripted agent registered
- **When** the peer sends `/agent <second>` and then a message
- **Then** a fresh conversation pinned to the second agent becomes active, the
  message is answered by it, and `/new` reuses it until switched again

### Scenario: /agent rejects an unknown agent

- **Given** a paired channel
- **When** the peer sends `/agent nope`
- **Then** the channel replies that the agent is unknown and lists the valid
  keys, and the active conversation is unchanged

### Scenario: /model switches the model for the next turn

- **Given** a paired channel in an active conversation
- **When** the peer sends `/model <name>` and then a message
- **Then** the next turn runs with the chosen model in the same conversation

### Scenario: a selection-card tap switches the agent

- **Given** a paired channel on a button-capable transport, with a second agent
  registered
- **When** the owner sends `/agent` (rendered as a selection card) and taps the
  second agent's button
- **Then** a fresh conversation pinned to the second agent becomes active, as if
  the owner had typed `/agent <second>`

### Scenario: a non-owner selection-card tap is ignored

- **Given** a paired channel whose peer has a stored `sender_id`
- **When** a different member of the chat taps a selection-card button
- **Then** the tap is ignored and the owner's agent/model is unchanged

### Scenario: a channel-driven turn is audited with channel, peer, and agent

- **Given** a paired channel
- **When** the peer sends a message that drives a turn
- **Then** an audit record names the channel, the peer, the agent, and the
  conversation

### Scenario: a completion summary is sent on a channel that cannot edit messages

- **Given** a paired channel on an adapter that cannot edit messages
- **When** a turn completes
- **Then** a compact completion summary is sent to the chat reporting the
  outcome, and a failed turn reports the error

### Scenario: a clean success on an edit-capable channel sends no completion summary

- **Given** a paired channel on an adapter that can edit messages
- **When** a turn completes successfully
- **Then** no trailing completion summary is sent — the live progress and the
  reply itself are the end-of-turn signal

### Scenario: channel progress lines describe each tool call from its input

- **Given** a paired channel on an adapter that can edit messages
- **When** the agent invokes a tool during a turn
- **Then** the progress status line names the tool and a short descriptor drawn
  from its input (e.g. the Bash description, the file basename for Read)

### Scenario: a group member who is not the paired sender is ignored

- **Given** a peer paired with a stored sender identity
- **When** a message arrives with the same chat id but a different sender id
- **Then** no reply is sent and no turn is started

### Scenario: the channel-driven agent is told it is on a chat channel

- **Given** a channel-originated conversation
- **When** a turn is driven from the channel
- **Then** the agent receives a system-prompt note naming the channel and telling
  it to keep replies concise and that it cannot click the user's OS dialogs,
  while a web-UI conversation gets no such note

## Assumptions

- The user can create a Telegram bot (BotFather) and a SeaTalk Open Platform
  app, and can obtain the SeaTalk scopes (Send Message to Bot User, etc.)
  through their organization's approval flow.
- For SeaTalk, the user runs a tunnel (cloudflared, ngrok, or equivalent)
  from a public URL to the local callback port; Coffer documents this in the
  quickstart but does not manage the tunnel.
- Channels carry text conversations; rich media arrives as a polite
  "text only" reply. The one exception is **command selection cards**: on a
  transport that `supports_buttons`, `/agent` and `/model` may render their
  choices as interactive buttons (FR-018).
