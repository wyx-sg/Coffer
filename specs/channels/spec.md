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
account to Coffer's chat platform (described in section E below). Messages
from the paired owner become turns in an ordinary conversation; the agent's
reply goes back to the IM chat. The channel layer and the agent layer meet
only at the chat platform's existing seams — conversation creation and the
turn event stream — so the cost of N channels and M agents is N + M, never
N × M.

> **Note ([Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.md)).**
> Mentions of the `builtin` agent below as a routable channel target reflect the
> behaviour shipped when this spec landed. That ADR retires the built-in agent as a
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
chunked when long. The bot shows progress while the turn runs by growing ONE
message in place — Telegram edits its status message, SeaTalk streams one that
re-renders — so the answer never arrives as a run of fragments. The same
conversation is recorded in the vault with full history.

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
- The active conversation is deleted → the peer's next
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
  paragraph-boundary chunking; SeaTalk converts the same markdown to SeaTalk's
  own markdown (`format: 1` — bold, italic, inline code, fences, ordered and
  unordered lists; headings become bold and links become `label (url)`, neither
  being supported there, and a literal marker character is escaped with a
  SINGLE backslash — two would be one escape too many, SeaTalk consuming the
  first and rendering the second as literal text) with 4096-byte chunking. Both stream a turn's progress into
  ONE surface that grows in place (FR-037), its lines describing each call from
  its input (e.g. `⏳ Bash · list the desktop`, `✅ Read · wedding.json`).
  Capabilities are declared by the adapter, not special-cased in the core.
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
  instead of a text list; tapping a button performs the same switch. The card
  carries a **title element** where the transport has one (SeaTalk; Telegram
  takes it as a bold first line) so its subject is scannable without crowding
  the body. After a tap lands, a transport that `supports_card_update` MUST
  **rewrite the card in place** so its tick moves to the new choice — a card
  left advertising the option the user just took invites a second tap that does
  nothing. The rewrite is best-effort: the switch is already done and confirmed
  in chat, so a transport without the capability, or a rewrite the platform
  refuses (SeaTalk updates only interactive cards, only within 7 days, only for
  the sending bot), changes nothing the user relies on.
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
  that `supports_buttons` (FR-018), `/model` with no argument renders the choices
  as a selection card. They come from the agent's model catalogue — the same list
  the web picker offers — narrowed by the channel's own allowed range where it
  has one (FR-071), and otherwise the **whole** catalogue, one **page** at
  a time (FR-018): that catalogue runs to 29 models for `claude_code`, and a card
  that long is unreadable on a phone and refused outright by SeaTalk, so the card
  is a window onto the list rather than the list. It opens on the page holding the
  model currently in effect, so a freshly rendered card always has its tick in
  view. Free-text `/model <name>` still reaches a model the user can already
  name — including one the catalogue does not list — and the card's body says so;
  within a channel that curates an allowed range, it reaches only what that range
  allows (FR-071). With no suggestions it falls back to the text report.
- **FR-018**: On a transport that declares the `supports_buttons` capability,
  the core MAY render a command's choice list as an **interactive selection
  card** (Telegram inline keyboard, SeaTalk interactive message). A button tap
  arrives as a normalized callback carrying an opaque value; the core
  **owner-gates it exactly like a message** (chat + sender identity, FR-014)
  before routing it to the same switch the text command performs. A tap never
  pairs, and an unsupported transport silently keeps the text path. This
  realizes the interactive-button capability that
  [Channel Adapter Framework](../../docs/decisions/channel-adapter-framework.md)'s
  `ChannelCapabilities` anticipated ("show buttons?").

  The card payload MUST follow each platform's published shape. SeaTalk's is
  one flat `elements` array in which **a button is itself an element**
  (`{"element_type": "button", "button": {...}}`) — not a `buttons` array
  beside it. Coffer emitted the latter until 2026-09-10, a shape guessed while
  the API docs were login-gated, so a SeaTalk selection card would have
  rendered without its buttons or been refused outright.

  The per-element ceilings were likewise unknown while the docs were gated, and
  were approximated from probing: two buttons were known to be accepted and
  twenty-nine to be refused, with nothing established in between, so the card
  was capped at six buttons on the strength of that gap. The published limits
  are a card of at most **3 titles, 5 descriptions, 5 buttons, 3 button groups
  and 3 images**, with a title of at most 120 characters and a description of at
  most 1000 — which makes the six-button card one over the bare-button ceiling.
  Buttons are therefore laid out in **button groups** (an element holding up to
  three buttons on one line) instead of one element each: six buttons occupy two
  of the three group slots, are legal by the published rules, and read as two
  rows rather than a six-high stack. Title and description text are clamped to
  their documented lengths, so a long body degrades to a truncated card instead
  of a refused one.

  A card the platform refuses is not the end of the command: the handler falls
  back to the plain-text answer it already has, so a rejected card degrades to a
  working message instead of leaving the user with silence. The rejection is
  logged so it stays diagnosable.

  A card carries a **bounded number of buttons** — six, navigation included.
  SeaTalk's true ceiling is undocumented (two are accepted, twenty-nine are
  refused), so the bound is the largest count Coffer has shipped rather than a
  guess at the limit. A choice list longer than that bound is **paginated**: the
  card shows four choices plus `← Prev` / `Next →`, and a navigation tap
  **rewrites the same message** at the next window through the same
  `supports_card_update` path an applied choice uses. One rule serves both
  cards — `/agent`'s two choices are under the bound and render with no
  navigation chrome at all.

  A navigation payload lives in its own callback namespace (`page:<kind>:<index>`),
  disjoint from the `agent:` / `model:` values a choice carries and fixed-size
  well inside the 64-byte callback budget. The separation is what guarantees the
  invariant: **a page turn changes nothing.** It re-reads what is in effect and
  re-renders; it can never be mistaken for a choice, and a malformed navigation
  value is dropped rather than allowed to fall through to the switch. Because the
  page in view may not hold the option in effect, the card's body always names
  what is in effect and which page it is on, so a page showing no tick never
  reads as a card claiming nothing is selected.

  Unlike the cosmetic rewrite after a choice, a page turn is something the user
  asked to see, so it degrades rather than dropping: where the message cannot be
  rewritten in place — no `supports_card_update`, or an update the platform
  refused because the card aged past SeaTalk's 7-day window or we were
  rate-limited — the requested page is posted as a fresh card, and as plain text
  if that is refused too.
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
  [Channel Media](../../docs/decisions/channel-media.md).
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
  audio to text and folds it into the turn's prompt. Transcription is a per-agent
  seam (ADR channel-media); a future audio-native agent's adapter forwards the audio instead
  of transcribing.

  Transcription runs **remotely**, on the connection the user designated as
  Coffer's `internal_default` — the same one that runs knowledge merge, organize
  and reorg (spec provider-switching). Voice therefore adds no new concept and no second place
  to configure. The endpoint is OpenAI-shaped
  (`POST <base_url>/audio/transcriptions`); a connection whose protocol has none
  (`anthropic`, `ollama`) is not used for it.

  **This is the one place in Coffer where user content may leave the machine, and
  it is off by default.** With no internal connection designated, an unsupported
  protocol, or a credential that will not resolve, nothing is uploaded: the voice
  is handed to the agent as an audio file rather than lost, exactly as when the
  local engine was absent. A failed or slow request degrades the same way — a
  transcription problem must never fail a turn.

  The constitution permits this. Principle I admits cloud services as **LLM and
  tool providers**, and a transcription endpoint is a tool provider; the audio is
  data in transit rather than vault state, and the transcript lands locally like
  any other turn text.

  _Was local until 2026-09-10:_ the frozen build bundled a `whisper.cpp` sidecar
  compiled from source in CI, plus an `mlx-whisper` fallback for source runs.
  That was the project's heaviest build dependency — a `git clone` and a cmake
  compile on every release — carried for a feature a remote endpoint does at
  least as well. It is removed along with the bundled-sidecar decision, the `whisper-cli` binary, and
  the `[voice]` / `[voice-mlx]` extras.

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
- **ChannelCapabilities** — what an adapter declares it can do (a live-updating
  surface via `supports_live_text`, rewriting a delivered message via
  `supports_edit` — the two are independent, see FR-037 — interactive buttons
  via `supports_buttons`, typing indicator); the core picks rendering strategies
  from it.
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

## Where a channel runs

A channel's platform identity (a polled bot, a webhook endpoint) tolerates
only ONE consumer. Coffer keeps one vault per machine and never replicates a
running one ([Vault Export and Import](../../docs/decisions/vault-export-import.md)),
so there is nothing to arbitrate: an **enabled channel runs its adapter here**,
on the machine whose daemon holds it, and a disabled channel runs nowhere.
There is no machine binding, no affinity field, and no per-machine override.

The `channel` kind declares no `scope`
([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)): a
non-null value is rejected at validation (422). Enabling is the only control
over whether the adapter starts.

If the user carries a bundle to a second machine (spec vault-export-import) the channel is
registered there too — pairing state rides along in the bundle's
`channel-peers` state area, so it needs no re-pairing — and enabling it on
both machines would point two adapters at one bot identity. That is a deliberate act by the user, not a state Coffer
arbitrates — the export/import model has no background replication that could
produce it on its own.

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

### Scenario: a tapped selection card is rewritten with the new choice

- **Given** a paired channel on a transport that `supports_card_update`, showing
  an `/agent` selection card
- **When** the owner taps a different agent's button
- **Then** the card is rewritten in place with the tick moved to the agent just
  chosen; on a transport without the capability nothing is rewritten and the
  switch still succeeds, and a rewrite the platform refuses leaves the switch
  and its confirmation intact

### Scenario: a long selection card is browsed page by page in place

- **Given** a paired channel on a button-capable transport showing a `/model`
  card built from a catalogue far longer than one card can carry
- **When** the owner taps `Next →`
- **Then** the same card message is rewritten with the following page of models
  — no second card is posted, no model is switched, and the body still names the
  model in effect and the page it is on; the last page offers no `Next →`, and a
  page turn the platform will not apply in place arrives as a fresh card (or as
  plain text) rather than as silence

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

### Scenario: a transport with no live-text surface posts no interim status message

- **Given** a paired channel on an adapter that can neither edit nor stream, in
  a group/thread (where the DM-only typing signal does not apply either)
- **When** a turn runs
- **Then** no interim signal is posted at all — only the final chunked reply
  lands in the originating group/thread

### Scenario: a reply grows in place on a transport that streams but cannot edit

- **Given** a paired channel on an adapter that cannot edit or delete a message
  but can stream one (SeaTalk), in a group/thread
- **When** a turn runs tools and then writes its reply
- **Then** exactly ONE message reaches the chat and grows in place — tool
  progress first, then the accumulating reply — and it finishes carrying the
  final reply, so nothing is sent twice and the answer never arrives as
  fragments

### Scenario: each seatalk stream update carries the full reply so far

- **Given** a SeaTalk channel streaming a reply
- **When** the reply text arrives in deltas
- **Then** the stream is opened once, every update carries the FULL accumulated
  text (never a delta) under a monotonically increasing sequence number, and
  only the last update finishes the stream

### Scenario: a terminated seatalk stream is never reused

- **Given** a SeaTalk stream the platform has terminated (an error, or a gap
  past its 30-second limit)
- **When** the turn produces more text and then ends
- **Then** no further request names that stream id, no replacement stream is
  opened, and the reply is delivered through the ordinary send path instead

### Scenario: a reply past the stream budget finishes the stream and sends the rest

- **Given** a SeaTalk reply longer than one stream may carry (4096 characters)
- **When** the turn ends
- **Then** the stream finishes at the budget on a paragraph boundary and the
  remainder is delivered as ordinary chunked messages

### Scenario: seatalk markdown escapes a literal marker character

- **Given** a reply whose prose contains a SeaTalk formatting character that is
  not markup (e.g. an underscore inside `snake_case`)
- **When** it is rendered for SeaTalk
- **Then** that character is escaped with a SINGLE backslash so it survives as
  typed, while genuine bold/italic/code/list markup is left as SeaTalk markdown

### Scenario: a refused selection card falls back to the text reply

- **Given** a button-capable transport that refuses the selection card outright
- **When** the owner sends `/agent` or `/model`
- **Then** the command answers with its plain-text report instead and the
  refusal is logged — silence is the one outcome a command must never produce

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
  path-native agent (Codex)
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

### Scenario: a group turn names the group it came from

- **Given** a paired channel whose owner @mentions the bot in a group thread
- **When** the turn is driven
- **Then** the turn text opens with a `[Message origin]` block naming the platform,
  the chat kind and title, the chat id, the thread id, and the sender

### Scenario: a DM turn names its own chat

- **Given** a paired channel and a DM from its owner
- **When** the turn is driven
- **Then** the origin block names the platform and the direct chat by id, omitting
  the thread line a DM has no value for

### Scenario: every turn carries its origin

- **Given** a paired channel that has already run one turn
- **When** the owner sends a second message
- **Then** that turn's text opens with its own origin block too — the provenance is
  not a first-turn-only header

### Scenario: a slash command keeps its leading slash

- **Given** a paired channel
- **When** the owner sends `/help`
- **Then** it is handled as a command (no origin block is prefixed, no conversation
  is created)

### Scenario: list available agents

- **Given** a running daemon,
- **When** the platform is asked which agents it offers,
- **Then** the managed agents (`claude_code`, `codex`) are listed, each with a
  display name and an availability flag, the `builtin` agent is **not** among
  them ([Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.md)),
  and the list is reachable from the REST API.

### Scenario: choose an agent when starting a conversation

- **Given** a running daemon,
- **When** a conversation is created for a named managed agent with a working
  directory,
- **Then** the conversation records that agent and its configuration.

### Scenario: reject an unknown agent or invalid agent configuration

- **Given** a running daemon,
- **When** a conversation is created for an `agent_key` no agent provides, or
  with a working directory that is not an existing directory,
- **Then** each is rejected as a domain error and nothing is persisted. An
  *absent* working directory is not invalid — it defaults to the Coffer-managed
  workspace.

### Scenario: send a message and receive a streamed reply

- **Given** a conversation on a registered agent,
- **When** a turn is started,
- **Then** the turn's events stream in order — start, text deltas, completion —
  and the assistant reply is persisted.

### Scenario: observe a turn started from another surface

- **Given** a turn already running on a conversation,
- **When** a second subscriber attaches to that conversation's event bus,
- **Then** it receives the current turn's events from the beginning and then
  follows live, so a subscriber that arrives mid-turn misses nothing.

### Scenario: second message queues during a streaming turn

- **Given** a turn is streaming,
- **When** another message is sent on the same conversation,
- **Then** it is accepted and enqueued rather than rejected, and runs as its own
  turn after the current one ends.

### Scenario: editing a queued message re-queues it at the tail

- **Given** one or more messages queued behind a streaming turn, shown one per
  row,
- **When** a queued message is edited,
- **Then** it leaves the queue and returns to the draft surface to be amended,
  and re-sending it enqueues it at the tail of the pending queue.

### Scenario: a queued message runs after the current turn

- **Given** a message queued behind a running turn,
- **When** that turn completes,
- **Then** the queued message is committed as the next user message and its turn
  runs, one turn per queued message.

### Scenario: interrupting a turn pauses the pending queue

- **Given** a running turn with messages queued behind it,
- **When** the turn is interrupted,
- **Then** the current turn stops, and the queued messages are held rather than
  auto-run until they are resumed or dropped.

### Scenario: stop a running turn

- **Given** a turn that has streamed partial text and is still running,
- **When** it is interrupted,
- **Then** the stream ends with a terminal turn-done carrying stop reason
  `interrupted`, and the partial assistant message is persisted as complete.

### Scenario: reply survives a restart

- **Given** a completed turn,
- **When** the daemon is restarted and the conversation is read back,
- **Then** the assistant reply is there — the message store, not the live
  stream, is the system of record.

### Scenario: manage conversations

- **Given** a running daemon,
- **When** conversations are created, renamed, and deleted,
- **Then** each operation persists and the listing reflects it; a deleted
  conversation and its messages are removed.

### Scenario: archive and restore a conversation

- **Given** a conversation in the active listing,
- **When** it is archived,
- **Then** it leaves the default (active) listing, appears in the archived
  listing, and is not destroyed; unarchiving returns it to the active listing.
  Archiving a conversation that does not exist is rejected.

### Scenario: skills are reachable as tools

- **Given** a vault holding skills,
- **When** an agent runs a turn,
- **Then** the vault's skills are offered to it as gateway tools.

### Scenario: model selection is recorded

- **Given** a conversation whose model has been set,
- **When** a turn completes,
- **Then** the assistant message records the model that produced it.

### Scenario: chat runs on the built-in model when no connection

- **Given** a running daemon with no Coffer LLM connection configured for the
  agent,
- **When** the Chat page is opened,
- **Then** the draft surface is available with no blocking empty state, and a
  sent turn runs on the agent's own built-in model and login — a Coffer
  connection is an optional override, not a prerequisite.

### Scenario: token usage is recorded on the assistant message

- **Given** a turn that completes,
- **When** the turn ends,
- **Then** the assistant message records the turn's token usage.

### Scenario: a group turn is acknowledged by typing in the group

- **Given** a paired group on an adapter that can type and has no reactions
  (SeaTalk)
- **When** the owner @mentions the bot in a thread of that group
- **Then** the typing indicator is sent to the group typing endpoint carrying
  that group's id and that thread's id — not to the direct-chat endpoint

### Scenario: a quoted message is named in the turn's origin

- **Given** a paired channel whose inbound message quotes an earlier message
- **When** the turn is built
- **Then** the origin block names the quoted message's id, and the transport
  makes no call to fetch the quoted message's content

### Scenario: a DM thread grounds its turn in the thread's own messages

- **Given** a paired direct chat on an adapter that supports history fetch, and a
  message arriving inside an existing thread
- **When** the turn is built
- **Then** the thread's own messages are fetched through the direct-chat thread
  endpoint and folded into the turn, exactly as a group thread's are

### Scenario: being removed from a group stops that group's sessions

- **Given** a paired group with a live session
- **When** the platform reports the bot was removed from that group
- **Then** that chat's sessions are stopped and nothing is sent back to the group

### Scenario: a group turning external is announced in the group

- **Given** a paired group the bot is still a member of
- **When** the platform reports the group was converted to an external group
- **Then** one warning is sent into that group, and the channel keeps working

### Scenario: a rich reply keeps its markdown structure

- **Given** a transport whose platform renders rich text,
- **When** a turn's reply contains a heading, a list, and a table,
- **Then** the reply is delivered in the platform's rich format with that
  structure intact, and a platform that rejects it falls back to the plain
  renderer without losing the reply.

### Scenario: a stop pressed on the platform's own control ends the turn

- **Given** a running turn whose live surface advertises a stop control,
- **When** the platform reports that the user stopped the generation,
- **Then** the turn is interrupted and the pending queue is paused, exactly as
  a typed `/stop` would.

### Scenario: privacy mode is reported when it contradicts the configuration

- **Given** a channel configured to act on unaddressed group messages,
- **When** its bot cannot read group messages,
- **Then** the channel's health reports the contradiction and names the fix.

### Scenario: an oversized inbound file tells the user

- **Given** a message carrying a file larger than the platform lets a bot
  download,
- **When** the message drives a turn,
- **Then** the user is told the file could not be fetched, rather than the file
  being silently dropped.

### Scenario: the command menu matches the commands that exist

- **Given** the channel command roster,
- **When** the transport registers its command menu,
- **Then** every command the channel handles is registered.

### Scenario: pairing by link claims the code

- **Given** an issued pairing code delivered as a start link,
- **When** the owner opens the link,
- **Then** the channel pairs to that sender, and the code is spent exactly as a
  typed one is.

### Scenario: a group reply is attached to the message it answers

- **Given** an addressed message in a group,
- **When** the turn replies,
- **Then** the reply is delivered as a platform-level reply to that message.

### Scenario: a group reply @mentions whoever asked

- **Given** an addressed message in a group from a member the transport named,
- **When** the turn replies,
- **Then** the reply opens with the platform's mention markup for that member.

### Scenario: a direct reply carries no mention

- **Given** the same channel answering in a 1:1 chat,
- **When** the turn replies,
- **Then** the reply carries no mention — there is nobody to disambiguate.

### Scenario: a streamed group reply is created already mentioning the asker

- **Given** a group turn that opens a live surface before it has anything to say,
- **When** the first snapshot is posted and the reply then grows in place,
- **Then** the mention markup is in the content the message is created with, and
  in every snapshot after it, exactly once.

### Scenario: an @ notification needs the mention in the message that creates it

- **Given** the transport that creates its reply as a stream and grows it,
- **When** the reply is delivered,
- **Then** the mention travels in the creating call, because the platform decides
  @ notifications then and not on any later update of the same message.

### Scenario: an interim snapshot reaches the chat as written, not as markup

- **Given** an in-flight snapshot of a reply, clipped mid-word so it can end
  inside an unclosed emphasis run,
- **When** it is sent in the platform's rich format, as carrying a mention
  requires,
- **Then** its formatting characters are escaped — one escape each — so the
  reader sees the text the agent has written so far.

### Scenario: a mention target survives the markdown escaper unchanged

- **Given** a mention whose target holds a character the platform's markdown
  escaper would otherwise escape (an id containing an underscore, or an email
  address),
- **When** the reply is rendered for that platform,
- **Then** the mention markup is delivered byte for byte, while the text around
  it is escaped as usual.

### Scenario: a sender with no id is mentioned by address instead

- **Given** a group message from a member the transport named only by email, on a
  platform that documents an address-keyed mention,
- **When** the turn replies,
- **Then** the reply mentions them by address; when both are known, the id is used.

### Scenario: a cross-organisation sender is still identified for a mention

- **Given** a group @mention from a sender outside the bot's organisation, whose
  organisation-scoped identifiers arrive empty,
- **When** the transport normalizes the message,
- **Then** the platform id the mention needs is kept, not discarded with them.


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
  Code, Codex) reach IM *only* this way; and **SeaTalk is
  Coffer-hosted for every agent, because no external gateway speaks SeaTalk.**
  All of spec channels — including the enhancements below (FR-028…FR-042) — describes
  this path. The one seam that keeps it agent-agnostic: every inbound message
  becomes text plus on-disk `Attachment(path, mime, filename)`, and each agent
  adapter materializes attachments its own way (Claude inlines images/PDFs;
  Codex receives file paths; audio is transcribed upstream). The
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
  block so path-native agents (Codex) and vision agents alike
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
  agent-switch full-history replay). The path stays inside the daemon: only the
  agent adapter, which must read the bytes, ever sees it.
  The media dir is bounded by a 30-day mtime retention prune on the retention
  cadence (bytes are re-downloadable; no size cap). See
  [Persisted Attachment Reference](../../docs/decisions/persisted-attachment-reference.md).
- **FR-042**: Every turn carries its own origin. The turn text opens with a
  `[Message origin]` block naming the platform, the chat (kind, the chat title
  where the platform supplies one, and always the chat id), the thread, and the
  sender (display name **and** the stable platform id — SeaTalk `employee_code`,
  Telegram `from.id` — which a platform tool call takes and which, in a group,
  appears nowhere else because `chat_id` is the group's) — so an agent asked "which group is this?" answers from the turn it was
  given instead of listing the bot's groups and inferring, and a platform tool
  call (send-to-group, fetch-group-info) has a chat id to aim at. The block is
  folded in after command detection (a prefixed `/help` would stop being a
  command) and after the empty-envelope check, and is persisted on the user
  message exactly like thread context (FR-029) — the single source of truth
  (FR-033) stays one string. It rides on **every** turn, not just a
  conversation's first: `/agent` can swap the agent mid-conversation (FR-040)
  and a resumed session would otherwise lose it. Title and sender name are
  chat-member-settable, so both are collapsed to one clipped line before they
  reach the prompt — a rename cannot forge extra origin lines. Where a platform
  hands the chat title over for free it is included (Telegram `chat.title`);
  where it does not (SeaTalk group events carry only `group_id`) the chat is
  named by id alone, which an agent can resolve to a name through the platform's
  own tools.

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
- **FR-037**: A reply grows in place, by whatever live-text mechanism the
  platform has — chosen from the adapter's declared capabilities, never its
  type. The capability the core asks about is `supports_live_text` ("is there a
  surface I can keep updating while this turn runs?"), NOT `supports_edit`
  ("can a delivered message be rewritten?"). Telegram answers yes by editing
  one status message; SeaTalk answers yes through its message-**streaming**
  API (`init_stream` / `update_stream`) while still being unable to edit
  anything at all. The flag's meaning changed because keying the strategy on
  `supports_edit` silently denied SeaTalk the live experience it does support:
  its replies arrived as several chunked messages at the end of the turn, one
  fragment at a time. `supports_edit` now means only what it literally says —
  `edit_text` still raises on SeaTalk — and the two flags are set
  independently.
  A turn keeps exactly ONE live surface. WHEN it opens depends on whether that
  surface becomes the reply or is scaffolding thrown away at the end, which the
  adapter declares as `live_text_persists`. Where it persists (SeaTalk: the
  streamed message IS the answer), the surface opens the moment the turn starts
  and says so — an acknowledgement the user can see, because the wait between a
  message and an answer is otherwise the whole of what they get, and on a long
  turn it reads as the bot having missed them. That acknowledgement costs no
  extra message: the reply is the same one, rewritten in place. Where the
  surface is scaffolding (Telegram: a status message deleted before the real
  reply is sent), it opens only once the turn has run past the update interval —
  either tool activity opens it or the reply text does — so a reply that
  finishes sooner opens none, avoiding a create → delete → resend flicker, and
  its 👀 receipt reaction already says the message was heard.
  The cadence of updates belongs to the TRANSPORT, which alone knows its own
  limits: the core offers every snapshot and each surface buffers to what it can
  sustain (SeaTalk ~200 ms, the interval its own guidance gives for a typewriter
  effect; Telegram far slower, since it edits a real message). The core adding a
  throttle of its own on top hid that buffer completely and made a stream arrive
  a paragraph at a time. Interim
  snapshots are clipped to the platform's per-message limit and their formatting
  characters are ESCAPED, so a long or half-written-markdown preview never breaks
  a platform parser or exceeds the cap. They are escaped rather than sent as plain
  text because the message has to be able to carry an @mention from the moment it
  is created (FR-070), and a mention is only a name in rich text.
  How a surface *ends* is the transport's business: Telegram's status message
  is scaffolding — it is deleted and the final reply is sent HTML-rendered and
  paragraph-chunked — whereas SeaTalk's stream IS the reply, so it finishes
  carrying the final text rendered as SeaTalk markdown and nothing is sent
  twice. A transport with no live surface at all posts no interim traffic; its
  final reply is the whole signal.
  The SeaTalk streaming constraints are contract, not implementation detail:
  every update carries the FULL accumulated text, never a delta (the client
  renders the latest snapshot); updates must be less than 30 s apart or the
  platform terminates the stream, so the last snapshot is re-sent on a keep-alive
  well inside that window; one stream carries at most 4096 characters, and a
  reply that outgrows the budget finishes the stream at the limit with the
  remainder sent as ordinary chunked messages (a reply's length is unknown
  until it ends, so refusing to stream anything that *might* overrun would
  withhold the live reply from every turn to serve the rare one); and a stream
  that has ended — finished, timed out, or errored — is never reused, because
  the platform rejects any later request naming its id: the surface latches
  dead, no replacement stream is opened, and the ordinary send path delivers the
  reply in full (the partial message the platform kept stays where it is —
  visibly stale, but the user still gets the whole answer). Clients older than
  3.67 simply see the finished message when the stream closes.
  A transport that can show typing but has **no reaction** to ack with
  (SeaTalk) additionally keeps a periodic typing heartbeat alive (an ephemeral
  action, zero chat clutter), covering the window before the first live update
  lands. It runs wherever the turn is, DM or group thread alike: SeaTalk turned
  out to have a second typing endpoint (`group_chat_typing`, thread-scoped)
  beside the direct-chat one, and the heartbeat was DM-only purely on the belief
  that no such endpoint existed. The gate is the receipt mechanism, not editing:
  a
  reaction-capable transport (Telegram) already acked receipt with 👀 (FR-036),
  so `supports_edit` selects nothing at all any more. All best-effort — a
  failed update, close, or heartbeat never breaks the turn.
- **FR-038**: Telegram albums are one turn. Messages sharing a `media_group_id`
  are debounced into a single turn carrying all their attachments, not one turn
  per photo.
- **FR-039**: Inbound events are de-duplicated. A redelivered platform event
  (same message id) is processed once.
- **FR-056**: A quoted message is surfaced, not resolved. Both SeaTalk inbound
  message events carry a `quoted_message_id` when the user replied by quoting;
  the envelope keeps it and the origin block (FR-042) names it, so an agent
  reading "as I said above" can tell that *above* refers to something specific
  instead of guessing from the visible text. The transport deliberately stops
  at the id. Fetching the quoted body is a single documented call
  (`get_message_by_message_id`) that the platform's own MCP server already
  exposes as a tool, which makes it an on-demand lookup the agent performs for
  itself — not transport work that must happen on every turn whether or not
  anyone needs it. The id is scoped to this bot: the platform deliberately
  gives one message different ids to different apps, so it is a handle, not a
  durable identifier.
- **FR-057**: A thread grounds its turn in a DM too, not only in a group.
  FR-029's thread-context fetch was written when SeaTalk threaded group chats
  alone; direct chats with a bot now thread as well, and the platform exposes
  the DM thread under its own endpoint (`single_chat/get_thread_by_thread_id`,
  keyed by employee code) alongside the group one. The adapter routes on chat
  kind and everything above it is unchanged — same flatten, same media
  download, same degrade-to-empty on any failure. The asymmetry this removes
  was real and invisible: a DM thread was already replied to in place (FR-026)
  yet the turn driving that reply could not see anything else in the thread.
  Group-*main* chatter is still never fetched — that stays undesirable, and the
  permission is still not granted.
- **FR-058**: The bot's own standing in a group is tracked. Two platform events
  change what a binding *is* rather than driving a turn —
  `bot_removed_from_group_chat` (kicked, or the group was disbanded) and
  `group_chat_converted_to_external_group` — and they arrive on a lifecycle
  callback kept separate from messages and card taps, so no consumer of those
  has to filter them out. Removal stops every live session for that chat;
  nothing is sent back, because the bot is no longer there to send it.
  Conversion to an external group means people from other organisations may now
  read a chat the owner paired, which is a security-relevant change and so is
  announced in the group itself rather than only written to a log — the owner
  is by definition present, and the group is the one place the warning is in
  context. Both are de-duplicated like every other event (FR-039): a redelivered
  removal must not fire twice. Telegram reports the same departure as a change
  to the bot's own membership (`my_chat_member`, which the platform withholds
  unless it is named in the subscribed update types) rather than as a dedicated
  event; it normalises to the same lifecycle envelope, so the rule is one rule
  and not one per platform. Being *added* is deliberately not an event: anyone
  can add a bot to a group, and pairing (FR-005) is the gate.

### E. The turn platform

Folded in from the retired Agent Chat spec. These requirements describe the machinery
*underneath* every channel turn — the registry, the adapters, the conversation
store, and the turn lifecycle. They lived in their own spec while a web Chat
page was their other client. That page is a live surface again (section G
below), but the description stays here: one platform, one document, so the
whole path — IM message → turn → reply, and that same turn watched from the
browser — reads in one place instead of two.

- **FR-043**: A turn MUST reach an agent only through an **agent-provider
  registry**: a turn is run, a conversation is initialised, and a conversation's
  agent state is torn down by asking the registry for the agent named on the
  conversation. Adding another agent MUST be a new registry entry only — no
  change to the conversation/message schema, the turn orchestrator, or the
  channel layer. The channel layer never branches per agent.
- **FR-044**: Each conversation MUST record which agent it belongs to via an
  `agent_key`, plus an opaque, agent-specific configuration that the named agent
  validates and persists. An `agent_key` no agent provides MUST be rejected, and
  an invalid configuration MUST be rejected as a domain error — both before
  anything is written. This is what a channel binding resolves against on the
  peer's first message.
- **FR-045**: The platform MUST expose its registered agents — each with a
  stable key, a display name, and a current availability flag — over the REST
  API, so the channel editor offers only agents that exist, and marks the ones
  whose CLI is absent on this host. It MUST likewise expose, per agent, the
  models that agent can be put on.
- **FR-046**: An agent is addressed for a turn through an **agent adapter** that
  is self-contained: given only the conversation history, it yields a stream of
  typed turn events. The adapter carries its own model, tools, and
  configuration; the orchestrator MUST NOT inject them.
- **FR-047**: System MUST ship subprocess-backed agent providers for Claude Code
  and Codex. Each runs in a working directory (its `agent_config.cwd`); when a
  turn supplies none, the provider MUST default to the Coffer-managed workspace
  `~/.coffer/workspace` (created on first use) rather than reject the turn — so
  a channel with no configured workspace works out of the box. An
  explicitly-supplied cwd MUST be an existing directory or the configuration is
  rejected. Availability MUST reflect whether the agent's binary is resolvable
  on the daemon's PATH; an unavailable agent is listed but not selectable. A
  turn MUST stream the tool's line-delimited JSON output mapped onto the
  platform's turn events, and persist the upstream session id so the next turn
  continues the same session. Claude Code is driven through the Claude Agent SDK
  and Codex through `codex app-server` (JSON-RPC 2.0 over stdio, NDJSON-framed);
  both run with full permissions — owner pairing (FR-005) is the security gate.
  Both MUST emit the reply as text increments *as it is written*, not as one
  block at the end of the turn — otherwise the live surface of FR-037 has
  nothing to grow and a channel reply lands all at once after a long silence.
  The Claude Agent SDK does this only when asked (`include_partial_messages`),
  and it then delivers BOTH the increments and the finished assistant message,
  so the adapter MUST subtract what it already emitted and send the reply
  exactly once.
- **FR-048**: System MUST persist conversations and their messages in SQLite as
  the system of record; they are not Resources of the kind-agnostic Resource
  framework. A message MUST store its role and an ordered list of content blocks
  of types `text`, `tool_use`, `tool_result`, and `attachment` (FR-033);
  assistant messages MUST also store token usage and the model that produced
  them when the agent reports one.
- **FR-049**: Conversations MUST follow a two-stage, retention-managed
  lifecycle, both windows configurable under Settings → Data: the retention
  worker auto-archives a conversation with no new message for the auto-archive
  window (default 7 days), then deletes archived conversations and their
  messages the configured number of days after archiving (default 30 days).
  Either window may be set to keep-forever to disable that stage. Auto-archiving
  is reversible; only deletion is destructive.
- **FR-050**: System MUST process at most one in-flight turn per conversation
  without rejecting a message sent while a turn is running: such a message is
  enqueued on a per-conversation **pending queue**. When the in-flight turn
  ends, System MUST dequeue the head, commit it as the next user message, and
  run its turn — sequential FIFO, one turn per queued message, never coalesced.
  A pending message is not committed to the message sequence until its turn
  starts. The queue is in-memory, so a daemon restart drops what has not yet
  been committed. (A message arriving from a channel while a turn is in flight
  is held by that channel's own inbound buffering, FR-027, rather than this
  queue.)
- **FR-051**: Interrupting a turn MUST also **pause** the pending queue: the
  current turn stops with its partial output kept, and queued messages are held
  rather than auto-run until the owner resumes them. This is what `/stop`
  (FR-011) reaches.
- **FR-052**: System MUST express a turn as a sequence of typed events covering,
  at minimum, turn start, text deltas, tool calls, tool results, turn
  completion, turn error, and pending-queue change.
- **FR-053**: System MUST publish those events on a per-conversation in-process
  bus that any number of subscribers may attach to. On attach, if a turn is in
  flight the bus MUST replay the current turn's events so a late subscriber
  catches up, then stream live. A turn runs as a detached task, so it survives
  the subscriber that started it going away — which is why a reply completes and
  is persisted even when the peer's connection drops mid-turn.
- **FR-054**: An interrupted turn — user interrupt, adapter failure, or daemon
  restart — MUST leave the partial assistant message persisted and marked
  complete rather than discarded. Stopping a turn is distinct from discarding
  the conversation, which throws the turn away.
- **FR-055**: Every completed turn MUST be recorded in the audit log with the
  actor, the agent, the conversation, and the turn's token usage, so "which
  agent did what, driven by whom" is answerable after the fact (see FR-030 for
  the channel-specific fields).


### F. Telegram platform parity (Bot API 10.x)

Telegram's Bot API 10.1–10.3 (June–August 2026) added a family of surfaces
built for exactly this shape of bot: a message that streams while an agent
generates it, a stop control the platform draws itself, structured rich text,
and a group reply only one member can see. Coffer had hand-built approximations
of the first three — an edited message standing in for a stream, a typed
`/stop`, a five-tag HTML subset standing in for markdown — and had no answer at
all for the fourth. These requirements move each one onto the platform's own
mechanism while keeping the hand-built path as the fallback, because the Bot
API server a user reaches is not guaranteed to be new enough.

- **FR-059**: Platform capability is probed, never assumed. On start the
  transport reads what the platform says about itself (`getMe`) and keeps the
  fields that change what it may do — the bot's identity, and whether privacy
  mode leaves it able to read group messages. A capability introduced after the
  Bot API server the user actually reaches (rich messages, message drafts,
  ephemeral messages) is attempted once and **latched off for the process** on
  the platform's own rejection, falling back to the mechanism it replaced. A
  Coffer running against an older Bot API server therefore degrades in
  formatting and liveness, never in delivery.
- **FR-060**: Group readability is diagnosed, not silently broken. Telegram bots
  run with privacy mode ON by default, which withholds ordinary group messages
  from the bot entirely. A channel configured to act on unaddressed group
  messages (`require_mention = false`, FR-035) but whose bot cannot read them is
  a configuration that looks correct in Coffer and does nothing in the chat.
  The channel's health surface (FR-041) MUST report this state and name the fix
  (disable privacy mode in BotFather, then re-add the bot to the group).
- **FR-061**: A reply renders in the platform's own rich format where it has
  one. An agent answers in markdown — headings, lists, tables, block quotes,
  fenced code. Telegram rich messages carry all of those natively, so the
  reply is sent as one rather than being flattened into the HTML subset (which
  demotes a heading to bold, a bullet to a glyph, and passes a table through as
  raw pipes). The existing renderer stays as the fallback FR-059 selects.
- **FR-062**: A live reply uses the platform's own streaming surface **where
  there is one for that chat**. Where the platform can stream a partial message
  while it is generated, the live-text handle (FR-037) drives that instead of
  rewriting a delivered message: no status message to delete, no rewrite of an
  already-delivered message, and no edit-rate ceiling on how often progress may
  show. A streaming surface that the platform offers only in some chats (a
  Telegram message draft addresses a private chat and has no group form) is
  used only there; everywhere else the transport keeps the mechanism it had,
  rather than spending a refused call per snapshot to show nothing. A snapshot
  past whatever the surface may carry is clipped to its tail — the newest words
  are the ones being watched — because a refused snapshot would kill the
  progress indicator mid-reply.
- **FR-063**: The platform's own stop control ends the turn. A streamed draft
  may advertise a stop button the platform draws; when the user presses it the
  platform reports the stopped draft, and Coffer MUST route that to the same
  interrupt path as `/stop` — same turn cancellation, same queue pause
  (FR-051), same user-visible outcome. A stop control the user can see but that
  does not stop anything is worse than none, so the button is only advertised
  on a transport where the route is wired.
- **FR-064**: Chatter that is not the answer stays private in a group. Command
  output and errors are addressed to one member, not to the room. Where the
  platform can deliver a message only that member's client shows (Telegram
  ephemeral messages), Coffer uses it for those; the agent's actual reply is
  always an ordinary message the group can see. This is the group-noise half of
  FR-024: that requirement stops the bot from *acting* on everything, this one
  stops it from *saying* everything out loud.
  **Selection cards are deliberately excluded.** A card is the one surface that
  must be *rewritten* after it is used (FR-018), and a privately-delivered
  message is rewritten through a different address space — Telegram edits an
  ordinary card by `chat_id` + `message_id` and an ephemeral one by `chat_id` +
  `receiver_user_id` + `ephemeral_message_id`, and documents that edit as not
  guaranteed to reach the user. A card that cannot be reliably rewritten keeps
  offering the option already taken, which is precisely what FR-018 exists to
  prevent, so a card stays an ordinary message until the rewrite is as reliable
  as the send.
- **FR-065**: The bot introduces itself. Its command menu is registered with
  the platform from Coffer's own command roster, and its prose profile
  (description, short description) is **filled in when empty**, so a user
  opening the bot for the first time sees what it is and what it accepts
  instead of an empty chat. The registered menu MUST list every command the
  channel actually handles — a command the help text offers but the menu omits
  is a drift bug, not a design choice. Copy the owner already wrote, and the
  bot's name, are their branding decision and MUST NOT be overwritten.
- **FR-066**: Pairing is one tap. Where the platform supports a parameterised
  start link, the pairing code (FR-005) is issued as a link that carries it, so
  the owner pairs by opening the link instead of transcribing eight characters
  on a phone. The typed code keeps working — the link is an additional way in,
  and the same single-use, TTL-bounded, attempt-bounded gate applies to both.
- **FR-067**: Every inbound media type drives a turn, or says why it cannot.
  Whatever the platform can attach to a message — photos, documents, voice,
  audio, video, animations, stickers, round video notes — is downloaded and
  becomes an `Attachment` (FR-020). Where a platform caps what a bot may
  download, a file over that cap MUST produce a message telling the user, not a
  silent no-op: the failure mode being fixed is a user who sent a file and got
  an answer that never mentions it.
- **FR-068**: A reply is attached to what it answers. In a group, the bot's
  reply MUST be sent as a platform-level reply to the message that triggered it,
  so a busy room can tell which question each answer belongs to.
- **FR-069**: Selection cards speak the platform's button vocabulary. Where the
  platform offers button semantics beyond a label — a disabled state, an intent
  colour — the card uses them, so the option already taken is shown disabled
  rather than re-offered.
- **FR-070**: A group answer names who it is for, and notifies them. In a group,
  the bot's reply MUST open by @mentioning the member whose message drove the
  turn, using the platform's own mention markup — so the answer notifies the
  person waiting for it and a busy room can see at a glance which of them it
  belongs to. In a direct chat it MUST NOT: a 1:1 conversation has nobody to
  disambiguate, and an @ there is only shouting. Four constraints bound it.
  - **The mention MUST be in the content the reply is CREATED with**, not added
    to it later. A platform decides @ notifications at creation; a mention that
    arrives on a later update of the same message renders as a name and notifies
    nobody, which is the worst of both — the room sees an @ the mentioned person
    never got. For a streamed reply that means the opening post carries it, and
    therefore so does every snapshot in between: a mention that appeared at
    creation, vanished for the length of the stream and returned at the end would
    be a visible glitch.
  - Because every snapshot then carries markup, every snapshot MUST be sent in
    the platform's rich format. The protection that the plain format used to give
    a reply clipped mid-word — an unclosed emphasis run the client would render
    as noise — MUST instead come from ESCAPING the agent's partial text, leaving
    the mention markup itself untouched.
  - The mention is built from the id the PLATFORM addresses a member by, which is
    not always the id the owner gate matches (SeaTalk gates on `employee_code`
    and mentions `seatalk_id`, and `employee_code` arrives empty for a sender
    outside the bot's organisation) — so the transport carries both. Where the
    platform documents a second way to address a member (SeaTalk also mentions by
    email), it is a FALLBACK for a sender whose id is missing, never the primary:
    the id is the identifier that is always present.
  - It degrades silently: no id and no usable fallback, or a transport that
    cannot mention from an id alone, yields an ordinary unmentioned reply — never
    a broken tag.
- **FR-071**: The channel owns its models, not the agent. A channel MUST carry
  its own `default_model` (the model a NEW conversation opened on this channel
  starts on) and its own `models` allowed range, and these MUST be the only
  curation applied to it: the agent resource governs what a person gets when
  they open that agent directly, and a channel is a different place with a
  different audience. Three consequences. A new conversation on the channel
  opens on `default_model` when one is set, reaching the agent's config the same
  way `default_agent` / `default_agent_config` do; `None` pins nothing and the
  agent's CLI default applies. The `/model` card offers exactly the allowed
  range when it is non-empty, in the order the user arranged it, so the card can
  never show a pick the next requirement refuses. And `/model <id>` outside a
  non-empty range MUST be refused with a message naming the allowed ids, rather
  than silently taking the chat somewhere the card never offered. An EMPTY range
  means NOT CURATED — every model the bound agent offers is allowed — never "no
  models", so a channel nobody has configured behaves exactly as it did before
  this requirement existed. Ids stay opaque: they are handed to the CLI verbatim
  and are never validated against the agent's catalogue, which moves with every
  CLI upgrade. **On the web surface** both fields belong to the channel's
  add/edit dialogs, beside the bound agent: a **Default model** select
  that always offers an explicit "not pinned" choice and draws its options from
  the bound agent's model catalogue — narrowed to the allowed range once there
  is one, so the form cannot assemble a pair the backend refuses — and an
  **Allowed models** tick list over that same catalogue, which states
  that nothing is restricted while it is empty rather than reading as "no
  models". The form MUST mirror this requirement's own rule (a default outside a
  non-empty range is refused before the round trip, and un-ticking the pinned
  model unpins it) and MUST clear both when `default_agent` is re-bound, since
  the ids named the previous agent.

### G. The web Chat page

The turn platform has a second surface: a **Chat page** in the web UI, onto
exactly the conversations the channels drive. It shipped with the Agent Chat
spec, was removed on 2026-09-10 as unused, and is restored on 2026-09-12,
because the thing it does that no channel can is let the owner watch, steer and
continue from a desktop a conversation they are driving from their phone. The
decision it rests on is recorded in
[Chat Is a Single-Owner Live Mirror](../../docs/decisions/chat-single-owner-live-mirror.md).

- **FR-072**: The web UI MUST carry a **Chat page**: two columns, the
  conversation list on the left and the selected conversation's message thread
  with its draft surface on the right. The list MUST show every conversation in
  the vault whatever opened it — a conversation an IM channel created is listed,
  readable, watchable, and continuable from the page, and carries a badge naming
  the channel it is also reachable on. There is no web-only conversation kind:
  the page and the channel are two windows onto one timeline, driven by one
  owner, and an agent cannot tell which window a turn arrived through.
- **FR-073**: The conversation list MUST support create, rename, archive,
  unarchive, and delete. Archiving takes a conversation out of the default
  (active) listing and into the archived listing **without destroying it**;
  unarchiving returns it to the active listing. Deleting removes the
  conversation and its messages and cancels any turn in flight on it — deletion
  is the destructive one, archiving is not. An operation naming a conversation
  that does not exist MUST be rejected.
- **FR-074**: Sending from the page MUST be **fire-and-return**:
  `POST .../messages` accepts the message, starts or enqueues its turn, and
  returns immediately (202) carrying none of the turn's output. Turn output is
  consumed from exactly one place — `GET .../events`, an SSE subscription — so
  "the turn I started" and "the turn my phone started" travel the same code and
  the sender is never a special case. On attach the subscription MUST replay the
  in-flight turn's events from that turn's beginning and then follow live
  (FR-053), so a client that arrives mid-turn misses nothing; with no turn in
  flight it MUST hold open and deliver the next turn whenever it begins, from
  whichever surface begins it.
- **FR-075**: The draft surface MUST NOT lock while a turn runs. A message sent
  during a turn joins the pending queue (FR-050) and is shown as its own row,
  one row per queued message, in queue order. A queued row MUST be removable,
  and MUST be editable by pulling it back out of the queue into the draft
  surface to amend — re-sending it then enqueues it at the **tail**, because it
  is a new send and whatever was queued behind it was queued first. `PUT
  .../pending` replaces the queue wholesale, and the resulting queue MUST ride
  the event stream (FR-052) so a second tab, and the phone, render the same rows.
- **FR-076**: The page MUST be able to interrupt the turn it is watching —
  whichever surface started it — via `POST .../interrupt`, with the semantics of
  FR-051: the turn stops with its partial output kept and persisted, and the
  pending queue is **paused** rather than auto-advanced into the turn that was
  just stopped.
- **FR-077**: The message thread MUST render a turn's tool calls as their own
  cards rather than as prose: each card names the tool, shows what it was called
  with, and shows the result once one arrives, so a reader can see what the agent
  *did* and not only what it said. Text and tool-call blocks appear in the order
  the turn emitted them, and a card whose result has not arrived yet reads as
  still running.
- **FR-078**: The page MUST let the owner read and set the conversation's agent
  configuration — which agent it runs on and which model that agent is put on —
  over `GET|PATCH .../agent-config`, persisting the model while preserving the
  conversation's working directory and upstream session id, and reverting to the
  agent's own default when it is cleared. A missing Coffer LLM connection MUST
  NOT block the page: with none configured the draft surface still accepts a
  message and the turn runs on the agent's own built-in model and login, because
  a Coffer connection is an optional override, not a prerequisite (see the
  2026-06-22 amendment of
  [Provider Switching](../../docs/decisions/provider-switching.md)).

## Deliberately out of scope

**A copy-to-clipboard button.** Telegram's inline buttons can carry `copy_text`,
which would let an agent hand over a command as something tappable rather than
as text to select by hand. It is not adopted, because the button is the easy
half: a `ChoiceButton` is only ever built by the agent and model cards, so an
agent has no way to *ask* for one. Giving it that way means a second
agent-facing sentinel beside `MEDIA:` — a feature with its own parsing, its own
false-positive risk on ordinary prose, and its own spec — not a field on an
existing button. Recorded here so the button is not mistaken for an oversight.

**Privately-delivered selection cards.** See FR-064: the card is the one surface
that must be rewritten after use, and an ephemeral message is rewritten through
a different address space with delivery the platform does not guarantee. The
work this would need is the ephemeral edit family
(`editEphemeralMessageText` / `editEphemeralMessageReplyMarkup`) plus a way to
carry an `ephemeral_message_id` on a delivered card, and it would still leave
the rewrite less reliable than the send. Worth revisiting only if the platform
makes that edit as reliable as an ordinary one.

**Two SeaTalk card capabilities Coffer does not use.** The platform's card format
also offers `redirect` buttons (with `mobile_link` / `desktop_link`) and
per-language card bodies (`{"default": …, "zh-Hans": …}`). Neither is adopted.
A redirect button needs somewhere to send the user, and Coffer's web UI binds to
loopback — a link from the owner's phone reaches nothing. Per-language cards
need Coffer's channel copy to exist in more than one language; it is
English-only in the backend, and the card would be the only translated surface
in a conversation whose every other line comes from the agent in whatever
language the owner wrote in. Both are recorded here rather than silently
skipped, because the research that found them is what made the card work
possible at all.

**SeaTalk's WebSocket event delivery.** The platform now offers a second way to
receive events: instead of verifying a public callback URL, a bot holds a
persistent WebSocket to SeaTalk and needs outbound connectivity only. For a
local-first vault that is the obviously right transport — it would delete the
tunnel (cloudflared/ngrok) the owner must stand up today, the listener process
that terminates it, and the signature verification that exists only because the
callback is reachable from the internet. It is not adopted, for two reasons that
are both outside this project's control. The wire protocol is not documented at
all — the published material covers only how to call a vendor SDK — and that SDK
(Go and Python) is distributed from an internal corporate GitLab, absent from
public PyPI. Coffer is MIT and OSS-bound, so it can neither depend on the SDK
nor reimplement a protocol nobody has published. Recorded here rather than left
as a silent omission: if the protocol is published or the SDK reaches PyPI, this
becomes the preferred inbound path and the tunnel becomes optional.


**An agent registry under the chat prefix.** The agent-registry listing and the
per-agent model catalogue once answered at `/api/v1/chat/agents` and
`/chat/agents/{key}/models`, and they moved to `GET /api/v1/agent-providers` and
`/agent-providers/{key}/models` when the page came down. They stay there now the
page is back. Neither was ever about a conversation — the channel editor calls
the first to list bindable agents, the agent detail page calls the second to
offer a model — and a page that happens to need them does not make them chat
routes. The Chat page reads them from where they live.

**Chat as "the Vault Console".** An earlier positioning made this page a seat
for talking to the vault itself, and for approving an agent's tool calls one by
one. Neither returns with it. The built-in model is an internal `coffer__*`
capability rather than a chat persona
([Built-in Agent Is Internal](../../docs/decisions/builtin-agent-is-internal-capability.md)),
and tool approval is gone outright, owner pairing being the gate
([Remove Tool Approval](../../docs/decisions/remove-tool-approval.md)). Section
G restores the live mirror and only the live mirror.

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
