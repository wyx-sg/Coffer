# Feature Specification: Channels

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/channels`
**Created**: 2026-06-12
**Status**: Accepted
**Input**: User description: "Coffer needs messaging channels — Telegram and
SeaTalk first — so the owner can talk to any agent on the chat platform from
the IM apps they already use, approve tool calls without leaving the chat, and
receive notifications pushed by Coffer. The architecture must stay uniform:
more channels and more agents will be added, so a new channel never touches
agent code and a new agent never touches channel code."

A channel is a registered resource (`channel:<name>`) that connects one IM
account to Coffer's chat platform (spec 008). Messages from the paired owner
become turns in an ordinary conversation; the agent's reply goes back to the
IM chat. The channel layer and the agent layer meet only at the chat
platform's existing seams — conversation creation, the turn event stream, the
approval gate — so the cost of N channels and M agents is N + M, never N × M.

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

### User Story 5 — Approve a tool call from the IM app (Priority: P2)

When an agent pauses a turn for human approval, the channel delivers the
request as an interactive prompt — inline Approve/Deny buttons on Telegram,
an interactive card on SeaTalk. The owner's tap resolves the platform's
approval gate exactly as a click in the web UI would, and the prompt message
is updated to show the decision. Taps from anyone but the owner are ignored.

**Why this priority**: The chat platform carries an approval capability;
a channel that cannot answer it would silently hang any agent that uses it.

**Independent Test**: With a scripted agent that requests approval, run a
turn, click the fake IM's Approve button, observe the decision delivered to
the agent and the prompt updated; repeat with Deny.

**Covering scenarios**:
- an approval prompt is answered from the IM chat
- a denied approval is delivered to the agent

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
  conversation service, turn orchestrator, approval gate.
- **FR-005**: Replies render per channel capability: Telegram converts
  markdown to Telegram HTML with a plain-text fallback and 4000-character
  paragraph-boundary chunking, and streams tool progress into one throttled
  editable status message; SeaTalk sends markdown with 4096-byte chunking and
  signals progress with a typing indicator. Capabilities are declared by the
  adapter, not special-cased in the core.
- **FR-006**: Commands `/new`, `/stop`, `/status`, `/help` work from any
  paired chat. `/stop` and `/new` take effect even while a turn is running;
  other messages queue (FIFO, bounded at 10) and run in order.
- **FR-007**: An `approval_request` event in the turn stream becomes an
  interactive prompt (Telegram inline buttons, SeaTalk interactive card); the
  owner's response resolves the platform approval gate; the prompt is updated
  with the outcome; non-owner clicks are ignored.
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

### Key Entities

- **Channel** — resource `channel:<name>`; config = type, credential refs,
  default agent + config.
- **ChannelPeer** — the paired owner of a channel: `(resource, chat_id)`,
  display name, paired-at, pointer to the active conversation. One per
  channel today; keyed by chat so group chats can become peers later without
  a schema change.
- **InboundMessage / OutboundMessage** — the normalized envelopes every
  adapter produces and consumes; the core never sees platform payloads.
- **ChannelCapabilities** — what an adapter declares it can do
  (edit messages, interactive buttons, typing indicator); the core picks
  rendering and approval strategies from it.
- **PairingCode** — in-memory, single-use, per-channel; never persisted.

## Success Criteria

### Measurable Outcomes

- **SC-001**: From a fresh install, a user can register a Telegram channel,
  pair, and get an agent reply in under 10 minutes following the quickstart.
- **SC-002**: A stranger messaging the bot produces zero observable response
  and zero turns, while the owner's traffic is unaffected.
- **SC-003**: Adding a hypothetical third channel type requires implementing
  one adapter + one config schema and touching no agent, conversation, or
  approval code (demonstrated by the test-only fake channel the suite uses).
- **SC-004**: Any agent registered on the chat platform is reachable from any
  channel with no channel-side code change (demonstrated by driving a channel
  against a scripted second provider in tests).
- **SC-005**: Every acceptance scenario below is covered by at least one
  test; `make verify` passes.

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

### Scenario: an approval prompt is answered from the IM chat

- **Given** a scripted agent that requests tool approval
- **When** the peer taps Approve on the delivered prompt
- **Then** the approval gate resolves allow, the turn continues, and the
  prompt shows the decision

### Scenario: a denied approval is delivered to the agent

- **Given** a pending approval prompt
- **When** the peer taps Deny
- **Then** the agent receives the deny decision and the prompt shows it

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

## Assumptions

- The user can create a Telegram bot (BotFather) and a SeaTalk Open Platform
  app, and can obtain the SeaTalk scopes (Send Message to Bot User, etc.)
  through their organization's approval flow.
- For SeaTalk, the user runs a tunnel (cloudflared, ngrok, or equivalent)
  from a public URL to the local callback port; Coffer documents this in the
  quickstart but does not manage the tunnel.
- Channels carry text conversations; rich media arrives as a polite
  "text only" reply.
- The built-in agent gates tool calls through the MCP gateway today, so live
  approval prompts appear only for agents that use the platform's approval
  gate; the channel-side capability is proven with a scripted provider, the
  same way spec 008 proved the platform seam.
