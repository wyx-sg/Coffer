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
which channel". And when a turn ends abnormally, one compact summary is pushed
to the chat: the failure, the stop, or the tool-iteration limit, with tool
count, duration, and tokens. A clean success sends no summary on any channel —
the reply itself is the signal, so the fact line would just be noise.

**Why this priority**: An entrypoint manager's two unclaimed differentiators are
first-class auth/audit and a reliable completion signal; both must be true on
every channel, including the silent ones.

**Independent Test**: Drive a turn from a paired channel and observe a
turn-started audit record with the channel, peer, and agent; observe that a
clean success sends no completion summary while a failed turn does.

**Covering scenarios**:

- a channel-driven turn is audited with channel, peer, and agent
- a clean success sends no completion summary
- a turn that does not end normally sends a completion summary
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
- Inbound photos and files → downloaded and handed to the agent for the turn
  (images inlined for a vision agent; any agent gets the file's path). An empty
  message with nothing downloadable (a sticker, a location) → the channel replies
  that it needs text, a photo, or a file.

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
- **FR-015**: After a turn that did not end normally the channel sends one compact
  completion summary as a fresh message: a failure reports the error, an interrupt
  reports the stop, and the tool-iteration limit reports the limit, each with tool
  count, duration, and token usage. A clean success sends **no** summary on any
  channel — the reply itself is the completion signal, so the fact line would only
  be noise (this holds regardless of whether the transport can edit messages).
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
- **FR-020**: Inbound photos and files drive a turn. The transport downloads each
  attachment to a Coffer-managed media dir; the bytes never enter the chat DB (the
  persisted user message keeps the caption, or a short note when there is none).
  For the turn, each attachment is handed to the agent adapter, which materialises
  it in its own native shape — a vision agent (Claude Code) inlines an image as a
  base64 content block it sees directly and a PDF as a document block; a
  path-native agent (Codex) and any non-vision file receive the on-disk path to
  open. This keeps history small, works for arbitrary file types, and generalises
  to future modalities (a new type is a new mime, not a new schema). See
  [ADR-038](../../docs/decisions/ADR-038-channel-media.md).
- **FR-021**: The agent sends a file back to the user by an explicit opt-in: a
  line-anchored sentinel `MEDIA:/absolute/path` (optionally `MEDIA:/absolute/path |
  caption`), told to it by FR-019's system note. On a transport that declares
  `supports_media`, the channel uploads that file (an image extension as an inline
  photo, otherwise a document) and strips the line from the delivered text; ordinary
  prose — including a legitimate markdown image `![alt](path)` written only to
  reference a file — is not this syntax and is never uploaded, and a sentinel whose
  file is missing, relative, or oversized is left as text. The unambiguous sentinel
  keeps outbound file delivery deliberate, not guessed, and never collides with
  normal markdown.
- **FR-022**: An inbound voice message drives a turn as a transcript. The built-in
  agents (Claude Code, Codex) cannot hear audio, so the adapter transcribes the
  audio to text **locally** and folds it into the turn's prompt. Transcription is a
  per-agent seam (ADR-038): the frozen desktop app uses a bundled, torch-free
  `whisper.cpp` engine (Apple-Silicon Metal) whose small model is downloaded on
  first use; a source run falls back to `mlx-whisper` (the optional `[voice-mlx]`
  extra). See ADR-039. A future audio-native agent's adapter forwards the audio
  instead of transcribing. When no engine is available — or the model has not been
  fetched yet — the voice is handed over as an audio file rather than lost.
- **FR-023**: A group chat is a first-class peer. When the paired owner
  @mentions the bot (or the message is delivered as an addressed group event)
  the bot answers there; the group becomes an additional `channel_peers` row
  keyed by `(channel, group chat id)`, inheriting the owner's `sender_id`. No
  schema migration — the table's `(resource_id, chat_id)` unique key already
  permits multiple peers per channel.
- **FR-024**: The bot acts in a group ONLY on an addressed message (an
  @mention of the bot). Un-addressed group messages are ignored. An addressed
  message from a non-owner is refused with a short "not authorized" reply and
  starts no turn.
- **FR-025**: Forwarded chat records are flattened into readable text folded
  into the turn so the agent sees them — SeaTalk
  `combined_forwarded_chat_history` and Telegram `forward_origin`. Each entry
  renders as `<sender>: <text | [image] url | [file] name>` under a
  `[Forwarded chat record]` heading. Images carried by SeaTalk messages — a
  directly-sent image, or any image nested (recursively) in a forwarded record
  — are additionally downloaded with the app token (SeaTalk file links require
  auth, so the URL alone is useless to the agent) and attached to the turn, so
  a vision agent sees the actual picture, not just a link.
- **FR-026**: Threads are read and replied-to in place, and a group reply
  always lands in a thread — never the group main chat. On SeaTalk a thread's
  id equals its root message's id: an @mention inside a thread already carries
  that id, so the bot reads that thread's messages for context (SeaTalk
  `get_thread_by_thread_id`) and replies into it; an @mention in the group main
  chat carries no thread id, so the bot roots a fresh thread at that @mention
  (replying under the @mention's own message id) and, since the thread holds
  only the @mention itself, reads no history. A DM or group message sent in a
  thread also replies into that thread. Reading *recent group-main* history is
  intentionally NOT done (the SeaTalk group-chat-history permission is not
  granted; the @mention message is self-contained). Telegram cannot fetch any
  history (Bot API limitation), so on Telegram thread context is not read — the
  bot answers on the @mention message and still replies into the forum topic. A
  quoted/replied message contributes a `> sender: …` context prefix where the
  platform inlines it.
- **FR-027**: Each `(channel, chat, thread)` has its own turn queue/session,
  so a DM turn, a group-main turn, and a thread turn never share state.

### Key Entities

- **Channel** — resource `channel:<name>`; config = type, credential refs,
  default agent + config.
- **ChannelPeer** — the paired owner of a channel: `(resource, chat_id)`,
  display name, paired-at, pointer to the active conversation, the paired
  sender's identity (`sender_id`), and sticky preferences (chosen agent).
  One row per (channel, chat): the paired owner plus one row per
  group/thread the owner has addressed the bot in; the `(resource_id, chat_id)`
  unique key already allows this with no migration.
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
  is queryable in the audit log by channel, peer, and agent; a clean success
  sends no completion summary on any channel, while a turn that ends abnormally
  (failed, interrupted, tool-limit) sends one reporting the outcome.

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

### Scenario: a group selection-card tap replies in the group/thread

- **Given** a paired channel with a group peer, on a button-capable transport,
  with a second agent registered
- **When** the owner taps an `/agent` selection-card button in a group thread
- **Then** the switch is applied to that group thread and the "switched"
  confirmation is routed back into the group/thread (never a DM); a non-owner's
  tap is refused with a routed "not authorized" reply and no switch

### Scenario: a channel-driven turn is audited with channel, peer, and agent

- **Given** a paired channel
- **When** the peer sends a message that drives a turn
- **Then** an audit record names the channel, the peer, the agent, and the
  conversation

### Scenario: a turn that does not end normally sends a completion summary

- **Given** a paired channel
- **When** a turn fails, is interrupted, or hits the tool-iteration limit
- **Then** a compact completion summary is sent to the chat reporting the outcome
  (the error / stop / limit) with tool count, duration, and tokens

### Scenario: a clean success sends no completion summary

- **Given** a paired channel (whether or not the transport can edit messages)
- **When** a turn completes successfully
- **Then** no completion summary is sent — the reply itself is the end-of-turn
  signal

### Scenario: channel progress lines describe each tool call from its input

- **Given** a paired channel on an adapter that can edit messages
- **When** the agent invokes a tool during a turn
- **Then** the progress status line names the tool and a short descriptor drawn
  from its input (e.g. the Bash description, the file basename for Read)

### Scenario: reply text streams into the editable status message as it arrives

- **Given** a paired channel on an adapter that can edit messages
- **When** the agent's reply text arrives in deltas during a turn
- **Then** the single status message shows tool-progress lines first, then is
  edited in place with the accumulating reply text (plain, not HTML) so the user
  watches the answer materialize; on finish the status message is deleted and the
  final reply is sent once (HTML-rendered and paragraph-chunked)

### Scenario: the streamed reply preview is clipped to the platform limit

- **Given** a paired channel on an adapter that can edit messages
- **When** the accumulating reply text grows past the platform's per-message limit
- **Then** each interim edit is clipped to that limit (keeping the most recent
  text behind a leading ellipsis) so the edit never fails, while the final reply
  carries the full text

### Scenario: a slow text-only reply streams into a status message

- **Given** a paired channel on an adapter that can edit messages
- **When** a text-only turn (no tool calls) keeps producing reply text past the
  throttle interval
- **Then** a status message is opened with the streaming reply text and edited in
  place as the answer grows, then deleted on finish while the final reply is sent
  once

### Scenario: a fast text-only reply opens no status message

- **Given** a paired channel on an adapter that can edit messages
- **When** a text-only turn completes within the throttle interval
- **Then** no status message is opened (no create → delete → resend flicker) — only
  the single final reply is sent

### Scenario: a supports_typing-only DM keeps the typing indicator alive during a long turn

- **Given** a paired channel on an adapter that can show typing but cannot edit
  (SeaTalk), in a direct chat
- **When** a long turn runs
- **Then** the typing indicator is re-sent periodically for the turn's duration
  (an ephemeral action, no chat clutter), and is stopped when the turn ends

### Scenario: a supports_typing-only group turn posts no interim status message

- **Given** a paired channel on an adapter that can show typing but cannot edit
  or delete (SeaTalk), in a group/thread
- **When** a turn runs
- **Then** no interim signal is posted (no typing heartbeat, no editable status
  message) — only the final chunked reply lands in the originating group/thread

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

### Scenario: an inbound photo is downloaded and drives a turn

- **Given** a paired Telegram channel
- **When** the owner sends a photo (with an optional caption)
- **Then** the largest photo size is downloaded to the media dir and carried on
  the inbound message as an attachment, and the caption becomes the message text

### Scenario: a Telegram album is handled as one turn

- **Given** a paired Telegram channel
- **When** the owner sends a multi-photo album (delivered as separate messages
  that share a `media_group_id`, the caption on the first item only)
- **Then** the items are debounced and combined into a single inbound message
  carrying all their attachments and the album's caption — one turn, not one per
  photo — while a lone photo without a `media_group_id` still drives its turn
  immediately

### Scenario: an inbound image reaches a vision agent as an inline block

- **Given** a turn carrying an image attachment
- **When** the Claude adapter builds the turn's content
- **Then** the image is a base64 `image` content block (a non-vision file becomes
  a path pointer instead), so the bytes are sent inline for this turn only and
  never stored in the chat database

### Scenario: the agent sends a file to the user via a reply marker

- **Given** a media-capable channel and an agent reply containing a
  `MEDIA:/absolute/path` sentinel line (optionally `| caption`) for a file that exists
- **When** the turn's reply is delivered
- **Then** the file is uploaded (an image as a photo, otherwise a document) and the
  sentinel line is removed from the text; ordinary prose — including a markdown
  image `![alt](path)` — is not this syntax and is not uploaded

### Scenario: an inbound voice message is transcribed for a text-only agent

- **Given** a voice attachment on a turn for an agent that cannot hear audio
- **When** the adapter prepares the turn
- **Then** the audio is transcribed to text and folded into the prompt, and the
  audio is not also sent as a file (a future audio-native agent would forward it)

### Scenario: a PDF reaches a path-native agent as extracted text

- **Given** a turn carrying a PDF (or office document) attachment for a
  path-native agent (Codex/Hermes/OpenCode/Cursor)
- **When** the adapter prepares the turn
- **Then** the document is text-extracted and folded into the prompt as a
  labelled `[Document: <name>]` block, and the document is not also sent as a
  binary path note; when no extraction engine is available the document degrades
  to a file path rather than wedging the turn

### Scenario: an un-addressed group message is ignored

- **Given** a paired channel and a group chat the bot is a member of
- **When** a group message arrives with no @mention of the bot
- **Then** no reply is sent and no turn or peer row is created for the group

### Scenario: the owner @mentions the bot in a group main chat

- **Given** a paired channel and a group chat with no active thread
- **When** the owner @mentions the bot in the group's main chat
- **Then** a turn runs and the reply is delivered into a fresh thread rooted at
  that @mention (never the group main chat), no thread history is read, and a
  `channel_peers` row is created for the group chat inheriting the owner's
  `sender_id`

### Scenario: a non-owner @mention in a group is refused

- **Given** a paired channel with a known owner
- **When** someone other than the owner @mentions the bot in a group chat
- **Then** the bot replies that the sender is not authorized and no turn is
  started

### Scenario: an empty sender_id in a group cannot bypass the owner gate

- **Given** a paired channel with a known owner and a group chat
- **When** an addressed group message arrives with no resolvable `sender_id`
  (the transport failed to supply one)
- **Then** the bot refuses it exactly like a non-owner sender — no turn is
  started and no peer row is created

### Scenario: require_mention on drops an un-addressed group message

- **Given** a paired channel with `require_mention` on (the default)
- **When** an un-addressed group message arrives (no @mention/reply-to-bot),
  even from the owner
- **Then** it is dropped at the mention gate — no reply, no turn, and no peer row

### Scenario: require_mention off admits an un-addressed owner group message

- **Given** a paired channel with `require_mention` off
- **When** an un-addressed group message arrives from the owner
- **Then** it passes the mention gate and drives a turn (still owner-gated: a
  non-owner would be refused by the sender checks below the gate)

### Scenario: ignore_other_mentions drops a message that also @mentions a human

- **Given** a paired channel with `ignore_other_mentions` on
- **When** a group message @mentions the bot but also @mentions another user
- **Then** it is dropped silently — no reply and no turn — so the bot does not
  butt into human-aimed traffic

### Scenario: ignore_other_mentions off still answers when @mentioned alongside a human

- **Given** a paired channel with `ignore_other_mentions` off (the default)
- **When** a group message @mentions the bot alongside another user
- **Then** the turn still runs — the extra human @mention does not suppress it

### Scenario: a group slash-command reply routes to the group/thread

- **Given** a paired channel and a group chat/thread the owner has messaged in
- **When** the owner sends a slash command (e.g. `/status`) inside that
  group/thread
- **Then** the command's reply is routed with the same `chat_kind`/`thread_id`
  as the triggering message, not the DM defaults

### Scenario: the owner @mentions the bot inside a thread

- **Given** a paired channel and a group chat with a thread, on a transport
  that can fetch thread history
- **When** the owner @mentions the bot inside that thread
- **Then** the thread's own messages are read and folded into the turn, and
  the reply is routed back into the same thread

### Scenario: a forwarded chat record reaches the agent

- **Given** a paired channel
- **When** the owner forwards a chat record to the bot
- **Then** the turn's message text carries a `[Forwarded chat record]` block
  listing each forwarded item

### Scenario: thread-history images reach a vision agent

- **Given** a paired channel and a group thread whose own messages include an
  image (a directly-sent one and one nested in a forwarded record)
- **When** the owner @mentions the bot inside that thread
- **Then** the thread's images are downloaded and attached to the turn — reaching
  the vision agent as real bytes, not a dead auth-gated file link

### Scenario: each group thread is an independent conversation

- **Given** a paired channel and a group whose threads share one `chat_id`
- **When** the owner drives a turn in thread A and, before it finishes, a turn
  in thread B
- **Then** the two threads resolve to two different conversations, both turns
  run concurrently, and neither is refused with "a turn is already running"

### Scenario: one bot runs different agents in different threads

- **Given** a paired channel and a group
- **When** the owner switches thread A to a different agent and leaves thread B
  on the channel default
- **Then** thread A's conversation drives the switched agent and thread B's
  drives the default — one bot running different agents per thread

### Scenario: SeaTalk outbound media is delivered into the originating thread

- **Given** a paired SeaTalk channel and a group-thread turn whose reply
  contains a `MEDIA:/absolute/path` sentinel line for a file that exists
- **When** the turn's reply is delivered
- **Then** SeaTalk uploads the file (an image as an `image` message, otherwise a
  `file` message) into that same group and thread — not the group main chat —
  because `supports_media` is now true and `send_media` routes on the turn's
  chat_kind + thread_id; any caption follows as a threaded text message

### Scenario: a redelivered event is processed once

- **Given** a paired channel that has already handled an inbound event
- **When** the platform redelivers that same event (same id) after a slow ack or
  a network hiccup
- **Then** the redelivery is dropped and the turn runs exactly once — no double
  reply or duplicate work — while a genuinely new event still drives its own turn

### Scenario: an inbound SeaTalk file drives a turn

- **Given** a paired SeaTalk channel
- **When** the owner sends a file directly (a `file` message whose
  `file.content` is an auth-gated file URL and `file.filename` the original name)
- **Then** the bytes are downloaded with the app token and carried on the inbound
  message as an attachment keeping its real filename and a non-image mime, so the
  file drives a turn like a photo does instead of hitting the "send text, a
  photo, or a file" reply

### Scenario: an inbound attachment is persisted as a reference on the user message

- **Given** a paired channel driving a turn with an image attachment
- **When** the turn starts
- **Then** the persisted user message carries an `AttachmentBlock` reference
  (path, mime, filename — never the bytes) after its text, so the attachment
  survives in history

### Scenario: a later turn re-materialises the attachment from history

- **Given** a persisted user message that carries an attachment reference
- **When** the turn task runs (including after a daemon restart, when nothing is
  threaded down)
- **Then** the adapter receives an `Attachment` with the reference's path/mime,
  re-materialised from the last user message in history — the single source of
  truth

### Scenario: the message API exposes an attachment block without leaking the path

- **Given** a user message with an attachment reference
- **When** the client reads the conversation's messages
- **Then** the content block has `type=attachment` with `filename` and `mime`,
  and no `path` field is present on the wire

### Scenario: the media dir prune deletes stale files and keeps fresh ones

- **Given** the channel-media dir with one file older than 30 days and one recent
- **When** the retention sweep runs
- **Then** the stale file is deleted and the recent one is kept

### Scenario: the management surface lists each Coffer-hosted channel with status, owner, agent, and health

- **Given** a registered and running Coffer-hosted channel with a paired owner
  and a routed agent
- **When** the management surface reads the channel
- **Then** it reports the channel's enabled status, its live health (adapter
  running), the paired owner, and the routed agent — mirroring the MCP-server /
  memory / skill management surfaces

### Scenario: receipt and completion are acked with reactions where supported

- **Given** a paired channel on an adapter that supports reactions (Telegram)
- **When** the owner sends a message that drives a clean turn
- **Then** a 👀 reaction is set on the owner's own message immediately on receipt and
  a ✅ reaction on completion, both targeting that inbound message id

### Scenario: a transport without reaction support attempts no reaction

- **Given** a paired channel on an adapter that does not support reactions (SeaTalk,
  whose receipt-and-progress cue is the typing signal)
- **When** the owner sends a message that drives a turn
- **Then** no reaction is attempted, while the turn still runs and replies normally

### Scenario: a failed reaction never breaks the turn

- **Given** a paired channel on a reaction-supporting adapter whose set_reaction fails
- **When** the owner sends a message that drives a turn
- **Then** the reply is still delivered — the best-effort reaction is suppressed

## Channels as a management plane (north star)

Channels are managed the way Coffer manages MCP servers, memory, and skills:
one place to register, credential, configure, and observe every way a user
reaches their agents over chat. The distinguishing capability — which no
agent-native or official channel can offer — is **one bot controls all agents**:
a single paired SeaTalk/Telegram bot drives *any* managed agent and switches
between them, so a user runs their whole agent fleet from one chat.

Two kinds of channel live under this plane:

- **Coffer-hosted channel (this spec's adapters).** Coffer runs the SeaTalk /
  Telegram adapter, normalizes each message (media download, forward flattening,
  owner-gate, audit, vault), and drives **any** managed agent for one turn —
  switchable per conversation, and (since each thread is its own conversation,
  FR-032) per thread, so one bot can run Claude Code in one thread and Codex in
  another. This is Coffer's moat: agents with no channel of their own (Claude
  Code, Codex, Cursor, OpenCode) reach IM *only* this way; and **SeaTalk is
  Coffer-hosted for every agent, because no external gateway speaks SeaTalk.**
  All of spec 009 — including the enhancements below (FR-028…FR-041) — describes
  this path. The one seam that keeps it agent-agnostic: every inbound message
  becomes text plus on-disk `Attachment(path, mime, filename)`, and each agent
  adapter materializes attachments its own way (Claude inlines images/PDFs;
  Codex/Hermes/OpenCode receive file paths; audio is transcribed upstream). The
  channel layer never branches per agent.
- **Externally-hosted channels are a non-goal.** An agent-native gateway
  (OpenClaw, Hermes run standalone) or an official vendor integration
  (Claude-in-Slack, Codex-in-Slack, Cursor-in-Slack, Claude Code's official
  Telegram/Discord/iMessage plugin) owns its own transport and drives only its
  own agent. Coffer neither proxies these nor manages them: stacking Coffer's
  channel in front would collide with their own runtime; holding a token that is
  then written into an external process's own config defeats the vault (secrets
  must stay encrypted until point of use); and the official cloud integrations
  have no local credential to hold at all. When a user wants one of these, they
  set it up through that tool's own flow — Coffer's docs point the way, nothing
  more. A native/official channel that does not support a platform (e.g. SeaTalk)
  simply does not run there; **Coffer does not bridge it onto SeaTalk.** Coffer's
  channel plane manages only what Coffer hosts.

Because official Telegram/Slack integrations either don't exist for most agents
(Codex/Gemini/OpenCode have no official Telegram; SeaTalk has no official
anything) or are single-agent and often cloud-only, the Coffer-hosted channel
is not redundant with them — it is the only path to unified, local, multi-agent
control, and the enhancements below are exactly the group/thread/voice/media
capabilities the official personal bridges lack.

### E. Unified channel management and one-bot-all-agents

- **FR-040**: One bot controls all agents. A single paired Coffer-hosted bot
  drives any managed agent, switchable via `/agent` and selection cards; agent
  choice is per conversation, and since each thread is its own conversation
  (FR-032) one bot can run different agents in different threads concurrently.
- **FR-041**: Coffer-hosted channels have a unified management surface. A
  management view lists every Coffer-hosted channel with its status, paired
  owner, agent, and health, mirroring the MCP-server / memory / skill management
  surfaces; each channel's credentials (bot tokens, app secrets) are held in the
  Coffer vault. Externally-hosted channels are out of scope (a non-goal).

### A. Media pipeline completeness

- **FR-028**: SeaTalk inbound media covers all types, not just images.
  `handle_event` downloads files/documents, video, and voice/audio with the app
  token — each becoming an `Attachment` — as it already does for images. A
  directly-sent PDF or voice memo drives a turn like a photo does; only a
  message with nothing text-or-downloadable still gets the "send text, a photo,
  or a file" reply.
- **FR-029**: Thread-history media is downloaded, not flattened to a dead link.
  When the owner @mentions the bot inside a thread, `fetch_thread` downloads the
  images/files carried by the thread's own messages (recursing forwarded records
  within them) and attaches them to the turn, alongside the existing flattened
  text. (Previously thread media surfaced only as an auth-gated `[image] <url>`
  the agent could not open.)
- **FR-030**: PDFs and office documents reach every agent as extracted text, not
  as a vision input. A document attachment is text-extracted into a context
  block so path-native agents (Codex/Hermes/OpenCode) and vision agents alike
  see its content; images stay vision-inlined for agents that support it.
- **FR-031**: SeaTalk outbound media is delivered and thread-aware. `send_media`
  is wired to SeaTalk's file-upload API (`supports_media` true); an agent
  `MEDIA:/path` sentinel sends the file back into the same chat **and
  thread** the turn came from — a generated chart returns to the group thread,
  not the main chat (closing the gap where SeaTalk agents could not return
  files at all, and where outbound media ignored the thread).

### B. Conversation model

- **FR-032**: Each group thread is its own conversation. Conversation identity is
  keyed by `(channel, chat_id, thread_id)`, not by the peer alone. A DM
  (`thread_id=""`) is one conversation; each thread in a group is independent —
  its own history and its own turn lock. Concurrent turns in different threads
  of one group no longer collide on a single conversation (the "a turn is
  already running" error). Pairing/owner identity stays on the peer row.
- **FR-033**: Inbound attachments are visible on later turns. The persisted user
  message records an attachment *reference* as an `AttachmentBlock` (path, mime,
  filename; the bytes stay in the media dir, never the chat DB) — the single
  source of truth. The turn task re-materializes the current turn's attachments
  by reading them back from the last user message in history (not a threaded
  param), so materialization survives a daemon restart and stays consistent with
  what the web shows; scope is within the conversation (no cross-session /
  agent-switch full-history replay). The web Chat page renders the reference as a
  compact `📎 filename · mime` chip; the local path is never emitted to the wire.
  The media dir is bounded by a 30-day mtime retention prune on the retention
  cadence (bytes are re-downloadable; no size cap). See ADR-041.

### C. Group UX and gating

- **FR-034**: Group selection-card taps route to the group/thread.
  `InboundCallback` carries `chat_kind`/`thread_id` and is owner-gated by the
  group's peer (`get_by_chat`, not the single-peer `get`); a button tap's reply
  lands in the same group/thread, not a DM.
- **FR-035**: Per-group inbound gating is configurable. A channel may set
  require-mention (default on for groups — the bot answers only when @mentioned
  or replied-to) and ignore-messages-that-@-someone-else (opt-in — a group
  message that @mentions any non-bot user is dropped silently, even when it also
  mentions the bot) — so a bot sitting in a busy group answers only when it
  should. Both are plain config bools; the channel stays owner-gated regardless,
  so this is about *when* to answer, not *who* may drive turns.

### D. Platform polish

- **FR-036**: Receipt and progress are acknowledged, capability-gated (never by
  transport type). On a `supports_reactions` transport (Telegram) an ack reaction
  (👀) marks receipt on the owner's own message immediately, and a ✅ marks
  completion on a clean finish (an errored/interrupted turn keeps just the receipt).
  A transport without reactions (SeaTalk) uses its typing/working signal as the
  receipt-and-progress cue instead. All best-effort — a failed ack never breaks the
  turn.
- **FR-037**: Long replies stream by the platform's best mechanism, chosen from
  the adapter's capabilities (never its type). A `supports_edit` platform
  (Telegram) streams the reply text into ONE throttled editable status message,
  opened once a turn runs long enough to warrant it — either tool activity opens
  it (tool-progress lines show first, then the reply text takes over the same
  message as it arrives) or, on a text-only turn, the reply itself opens it once
  it has run past the throttle interval. A reply that finishes within that
  interval opens no status message at all (no create → delete → resend flicker) —
  its final send is enough. Interim edits are PLAIN and clipped to the
  per-message limit, so a long or partial-markdown preview never breaks the
  platform parser or exceeds the cap; on finish that message is deleted and the
  final reply is sent HTML-rendered and paragraph-chunked to the platform limit. A
  `supports_typing`-only platform (SeaTalk) cannot stream, so on a DM it keeps a
  periodic typing heartbeat alive during the turn (an ephemeral action, zero
  chat clutter) and sends the final chunked reply; a SeaTalk group/thread turn
  gets no interim signal at all (it can neither edit, delete, nor group-type) —
  the final chunked reply is the completion signal. All best-effort — a failed
  edit or heartbeat never breaks the turn.
- **FR-038**: Telegram albums are one turn. Messages sharing a `media_group_id`
  are debounced into a single turn carrying all their attachments, not one turn
  per photo.
- **FR-039**: Inbound events are de-duplicated. A redelivered platform event
  (same message id) is processed once.

## Assumptions

- The user can create a Telegram bot (BotFather) and a SeaTalk Open Platform
  app, and can obtain the SeaTalk scopes (Send Message to Bot User, etc.)
  through their organization's approval flow.
- For SeaTalk, the user runs a tunnel (cloudflared, ngrok, or equivalent)
  from a public URL to the local callback port; Coffer documents this in the
  quickstart but does not manage the tunnel.
- Channels carry text plus inbound photos and files (FR-020): media is
  downloaded and handed to the agent, while an empty message with nothing
  downloadable gets a polite "send text, a photo, or a file" reply. Outbound is
  text plus files the agent chooses to send (FR-021, on a `supports_media`
  transport) and, as a rich exception, **command selection cards**: on a
  transport that `supports_buttons`, `/agent` and `/model` may render their
  choices as interactive buttons (FR-018).
