# Feature Specification: Channels

**Status**: Accepted
**Input**: User description: "Coffer needs messaging channels — Telegram and
SeaTalk first — so the owner can talk to any agent on the chat platform from
the IM apps they already use and
receive notifications pushed by Coffer. The architecture must stay uniform:
more channels and more agents will be added, so a new channel never touches
agent code and a new agent never touches channel code."

A channel is a registered resource of kind `channel` that connects one IM
account to Coffer's turn platform (spec `chat`). Messages from the paired owner
become turns in an ordinary conversation; the agent's reply goes back to the IM
chat. The channel layer and the agent layer meet only at the turn platform's
existing seams — conversation creation and the turn event stream — so the cost
of N channels and M agents is N + M, never N × M.

This spec owns what every channel type shares. The per-platform mechanics live
in its two children, which number their own requirements from FR-001:

- [`channels/telegram`](telegram/spec.md) — the Bot API transport.
- [`channels/seatalk`](seatalk/spec.md) — both SeaTalk inbound transports.

> **Note ([Built-in Agent Is Internal](../../../docs/decisions/builtin-agent-is-internal-capability.md)).**
> Mentions of the `builtin` agent below as a routable channel target reflect the
> behaviour shipped when this spec landed. That ADR retires the built-in agent as a
> chat persona, so channels route to **managed** agents (Claude Code, Codex, …)
> only; the built-in model is now an internal `coffer__*` capability, not a chat
> target.

## User Scenarios & Testing

### User Story 1 — Register a channel (Priority: P1)

The user creates a bot on the platform's own developer surface, stores its
secret in Coffer's credential store, and registers a channel resource
referencing it. The channel appears in the Channels page and CLI with its
enabled state, and validation rejects a channel whose credential reference does
not resolve.

**Why this priority**: Nothing else works until a channel exists. Registration
also proves the resource-framework integration (lifecycle, audit, credential
probing) end to end.

**Independent Test**: Store a bot token under a credential ref, register
a `channel` resource named `my-telegram` pointing at it, see it listed via REST, CLI, and the
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
the IM chat, rendered for that platform and chunked when long. The bot shows
progress while the turn runs by growing ONE message in place, so the answer
never arrives as a run of fragments. The same conversation is recorded in the
vault with full history.

**Why this priority**: This is the product: the vault's agents reachable from
the IM apps the user already lives in.

**Independent Test**: With a paired channel whose agent is scripted, send
"hello", observe a reply in the fake IM within the turn, and the same
exchange visible through the turn platform's REST API.

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

### User Story 8 — Operate channels day to day (Priority: P3)

Disabling a channel stops its adapter (polling halts, events are refused);
enabling restarts it; deleting the channel stops the adapter and removes its
peer binding. The Channels page and `coffer channel status` show whether the
adapter is running, who is paired, and whatever ingress facts the channel's
type has to report.

**Why this priority**: Lifecycle honesty (status that tells the truth,
disable that actually stops traffic) is what makes the feature operable.

**Covering scenarios**:

- disable stops the adapter and enable restarts it
- deleting a channel cleans up its runtime and peer
- channel status reports runtime, pairing, and callback details

---

### User Story 9 — Switch agent, model and effort from chat (Priority: P2)

The owner steers the entrypoint without leaving the IM app. `/agent codex`
switches the conversation to Codex; `/model opus` changes the model; `/effort
high` changes how hard that model thinks. Switching
the agent starts a fresh conversation pinned to the new choice (the agent is
fixed for a conversation's life) and the choice sticks for later messages and
`/new`; switching the model or the effort takes effect on the next turn in the
same conversation. Each command with no argument reports the current value and
the available choices, as a selection card where the transport has buttons.

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

### User Story 10 — Know who may drive, and when a turn is done (Priority: P2)

Because the entrypoint is remote-reachable, the act that grants a stranger the
right to drive turns at all is recorded in the audit log: a pairing code issued,
and a sender claiming it. A turn itself is not — the conversation and its
messages are already the durable record of what was asked and what answered, and
they are readable from the web Chat page (spec `chat`) and the REST API. And
when a turn ends abnormally, one compact summary is pushed
to the chat: the failure, the stop, or the tool-iteration limit, with tool
count, duration, and tokens. A clean success sends no summary on any channel —
the reply itself is the signal, so the fact line would just be noise.

**Why this priority**: An entrypoint manager's two unclaimed differentiators are
a fail-closed authorization boundary that leaves a record, and a reliable
completion signal; both must be true on every channel, including the silent ones.

**Independent Test**: Issue a pairing code and claim it, and observe both events
in the audit log with the channel and the sender; then observe that a clean
success sends no completion summary while a failed turn does.

**Covering scenarios**:

- a clean success sends no completion summary
- a turn that does not end normally sends a completion summary
- a group member who is not the paired sender is ignored

---

> **There is no User Story 5.** It was the tool-approval story, and
> [Remove Tool Approval](../../../docs/decisions/remove-tool-approval.md) removed it
> together with its requirements, success criteria and scenarios — owner pairing
> is the gate instead. The gap stands rather than being closed by renumbering:
> that ADR names the removed story by its number, so compacting the list would
> re-point its reference at whichever story inherited the five.
>
> **There is no User Story 7 here.** "SeaTalk reaches the local daemon" is one
> platform's ingress story, so it lives in
> [`channels/seatalk`](seatalk/spec.md) with the requirements that answer it.
>
> **There is no User Story 11 here.** "Watch and steer the same conversation
> from the browser" is the web Chat page's story and lives in spec `chat`.

### Edge Cases

- A message arriving exactly when the previous turn finishes joins the queue,
  not a race: turns for one conversation never overlap (platform guarantee).
- The IM platform rejects a formatted message → the channel retries the same
  content as plain text before reporting failure.
- The daemon restarts mid-turn → the turn platform's startup sweep marks the
  orphaned turn failed; the channel conversation simply continues on the next
  message.
- A pairing code expires (1 hour) or suffers repeated wrong guesses → the
  code is invalidated; a fresh code must be issued.
- The active conversation is deleted → the peer's next
  message creates a fresh conversation with the default agent.
- Inbound connectivity is lost → the adapter backs off exponentially and
  resumes, and no inbound message is double-processed after reconnect.
- The platform rate-limits outbound sends → sends back off and retry.
- Inbound photos and files → downloaded and handed to the agent for the turn
  (images inlined for a vision agent; any agent gets the file's path). A sticker
  is a picture the user chose deliberately, so it is downloaded like any other
  attachment (FR-051). Only a message with no text and nothing downloadable at
  all — a location, a contact card — gets the reply that the channel needs text,
  a photo, or a file.

## Requirements

### Functional Requirements

- **FR-001**: A `channel` resource kind exists with per-type configuration, a
  default agent key, and optional default agent configuration. Each child spec
  states its own type's fields. Secrets live in the credential store only;
  configuration carries references, which are probed at registration time.
- **FR-002**: Channel lifecycle (register, enable, disable, update, delete)
  rides the generic resource framework, with audit on every transition.
- **FR-003**: Pairing: the daemon issues an 8-character single-use code
  (unambiguous alphabet, 1-hour TTL, bounded wrong-guess attempts) per
  channel; a message consisting of the code binds its sender as the channel's
  sole peer, replacing any previous peer; all other senders are ignored
  silently.
- **FR-004**: Inbound text from the paired peer routes to the peer's active
  conversation, creating one on first use via the turn platform's standard
  conversation-creation path (default agent validated by the agent registry).
  The channel layer reaches agents only through the turn platform's seams:
  conversation service, turn orchestrator (spec `chat`).
- **FR-005**: Replies render per channel capability — each adapter converts the
  agent's markdown into its platform's own format and chunks to its own limit,
  as its child spec states. Both stream a turn's progress into ONE surface that
  grows in place (FR-038), its lines describing each call from its input (e.g.
  `⏳ Bash · list the desktop`, `✅ Read · wedding.json`). Capabilities are
  declared by the adapter, not special-cased in the core.
- **FR-006**: Commands `/new`, `/stop`, `/status`, `/help` work from any
  paired chat. `/stop` and `/new` take effect even while a turn is running;
  other messages join the conversation's pending queue (spec `chat` — the one
  the web shows; the channel refuses past 10 waiting) and run in order. These
  are the commands that need nothing of the conversation; the ones that
  configure the conversation the chat is bound to — `/agent`, `/model`,
  `/effort` — are specified in FR-010 and FR-013, and `/save` in FR-014. All of
  them live on one roster (FR-049), so none of the lists derived from it can go
  stale.
- **FR-007**: A notify entry point (REST + CLI) delivers arbitrary text to a
  channel's paired peer, independent of any conversation.
- **FR-008**: The Channels page lists channels, registers new ones (storing
  secrets through the credential store), shows status (adapter running,
  paired peer, ingress facts), issues pairing codes, and toggles
  enable/disable, and binds each channel to the machine that runs it (FR-026).
  CLI parity: `coffer channel list / register / bind / pair / status / notify`.
- **FR-009**: Channel events are audited where an event grants or moves the
  right to drive turns: a pairing code issued, and a sender claiming it. Those
  two are the whole channel-specific audit surface, alongside the automatic
  resource-lifecycle audit the framework records. Traffic is deliberately not
  audited — a notification sent and a turn run are neither irreversible nor
  invisible afterwards, and the conversation and its messages are already their
  record.
- **FR-010**: The owner switches the conversation's agent from chat. `/agent`
  with no argument reports the current agent and the registry's available agent
  keys; `/agent <key>` validates the key against the agent registry and, on
  success, records it as the peer's sticky preference and opens a fresh
  conversation pinned to it (an existing conversation's agent cannot change), so
  subsequent messages and `/new` use the chosen agent until it is switched
  again. An unknown key is rejected with the valid keys listed; no channel-side
  code is added per agent. On a transport that `supports_buttons` (FR-015),
  `/agent` with no argument renders the choices as an interactive selection card
  instead of a text list; tapping a button performs the same switch. The card
  carries a **title element** where the transport has one, so its subject is
  scannable without crowding the body. After a tap lands, a transport that
  `supports_card_update` MUST **rewrite the card in place** so its tick moves to
  the new choice — a card left advertising the option the user just took invites
  a second tap that does nothing. The rewrite is best-effort: the switch is
  already done and confirmed in chat, so a transport without the capability, or
  a rewrite the platform refuses, changes nothing the user relies on.
- **FR-011**: The owner gate verifies sender identity, not only chat identity.
  Every inbound envelope carries a `sender_id`, whose platform meaning each
  child spec names; pairing records it on the peer, and an inbound message is
  accepted only when its `chat_id` matches and — when the peer has a stored
  `sender_id` — its sender matches. A peer paired before this requirement (no
  stored `sender_id`) degrades to the chat-id-only gate.
- **FR-012**: After a turn that did not end normally the channel sends one compact
  completion summary as a fresh message: a failure reports the error, an interrupt
  reports the stop, and the tool-iteration limit reports the limit, each with tool
  count, duration, and token usage. A clean success sends **no** summary on any
  channel — the reply itself is the completion signal, so the fact line would only
  be noise (this holds regardless of whether the transport can edit messages).
- **FR-013**: The owner switches the model from chat. `/model` with no argument
  reports the current model; `/model <name>` stores the raw upstream model
  string, passed through to the bound agent's CLI verbatim. A channel curates no
  models, so nothing is validated here: the model namespace belongs to the CLI,
  not to Coffer, and a name that agent cannot run surfaces as the CLI's own error
  relayed to the chat on the next turn. A model switch takes effect on the next
  turn in the same conversation (the model is re-read each turn, unlike the agent
  and working directory). On a transport that `supports_buttons` (FR-015),
  `/model` with no argument renders the choices as a selection card. They come
  from the agent's model catalogue — read back from the installed CLI, the one
  list Coffer has of what that agent can run — in **full**, because nothing
  curates it. It is shown one **page** at a time (FR-015), opening on the page
  holding the model currently in effect, so a freshly rendered card always has
  its tick in view. Free-text `/model <name>` still reaches a model the user can
  already name — including one the catalogue does not list — and the card's body
  says so. No surface refuses an id: a channel binds an agent and nothing more.
  With no suggestions it falls back to the text report.

  **`/effort` is the other half of that choice.** For an agent whose models take
  a reasoning level, the model id is not the whole decision, and the level is not
  part of the model NAME, so it is its own command rather than an argument to
  `/model`. It behaves exactly as `/model` does: no argument reports the level in
  effect and renders the choices as a selection card where the transport
  `supports_buttons`, an argument applies it to the next turn of the SAME
  conversation, a tap takes the same path as the text, and Coffer validates
  nothing — the level reaches the agent verbatim. The levels offered are those of
  the model the conversation is actually ON, read from the same catalogue
  `/model` offers, so a level menu never describes a model the conversation is
  not running. An agent whose model reports no levels has nothing to choose
  between: `/effort` says so in one line rather than rendering an empty card.
  Like `/model` there is no clearing form, and `/new` is the way back to the
  agent's own default, since a fresh conversation carries no overrides at all.
- **FR-014**: A document sent to a Coffer channel MUST be ingestible into a
  collection through the same conversion path the Knowledge page uses, so the
  phone and that page are two ends of one entrance (spec `knowledge`). `/save`
  is the command that does it. The channel MUST confirm the collection with the
  owner before storing, and MUST NOT store anything from a non-owner.
- **FR-015**: On a transport that declares the `supports_buttons` capability,
  the core MAY render a command's choice list as an **interactive selection
  card**. A button tap arrives as a normalized callback carrying an opaque
  value; the core **owner-gates it exactly like a message** (chat + sender
  identity, FR-011) before routing it to the same switch the text command
  performs. A tap never pairs, and an unsupported transport silently keeps the
  text path. This realizes the interactive-button capability that
  [Channel Adapter Framework](../../../docs/decisions/channel-adapter-framework.md)'s
  `ChannelCapabilities` anticipated ("show buttons?").

  The card payload MUST follow each platform's published shape, which each child
  spec states. A card the platform refuses is not the end of the command: the
  handler falls back to the plain-text answer it already has, so a rejected card
  degrades to a working message instead of leaving the user with silence. The
  rejection is logged so it stays diagnosable.

  A card carries a **bounded number of buttons** — six, navigation included. A
  choice list longer than that bound is **paginated**: the card shows four
  choices plus `← Prev` / `Next →`, and a navigation tap **rewrites the same
  message** at the next window through the same `supports_card_update` path an
  applied choice uses. One rule serves both cards — `/agent`'s two choices are
  under the bound and render with no navigation chrome at all, and `/effort`'s
  handful of levels likewise.

  A navigation payload lives in its own callback namespace (`page:<kind>:<index>`),
  disjoint from the `agent:` / `model:` / `effort:` values a choice carries, and
  fixed-size so it fits the tightest callback budget any transport declares. The
  separation is what guarantees the invariant: **a page turn changes nothing.**
  The set of kinds that namespace admits is closed and explicit, so adding a card
  that ticks a current choice means adding its kind there too; a `page:` value
  naming a kind Coffer does not render is dropped, not applied. It re-reads what
  is in effect and re-renders; it can never be mistaken for a choice, and a
  malformed navigation value is dropped rather than allowed to fall through to
  the switch. Because the page in view may not hold the option in effect, the
  card's body always names what is in effect and which page it is on, so a page
  showing no tick never reads as a card claiming nothing is selected.

  Unlike the cosmetic rewrite after a choice, a page turn is something the user
  asked to see, so it degrades rather than dropping: where the message cannot be
  rewritten in place — no `supports_card_update`, or an update the platform
  refused — the requested page is posted as a fresh card, and as plain text if
  that is refused too.
- **FR-016**: A channel-originated turn tells the agent it is bridged to a chat
  channel, not a terminal: the agent receives a short system-prompt note carrying
  the channel name and mobile-chat guidance — keep replies concise, and it cannot
  click permission or confirmation dialogs on the user's computer (they may be
  away from it). This prevents terminal-sized replies and silent waits on
  un-clickable dialogs. Web-UI turns are unaffected — the note rides only on a
  conversation whose `channel_name` is set.

- **FR-017**: Inbound photos and files drive a turn. The transport downloads each
  attachment to a Coffer-managed media dir; the bytes never enter the chat DB (the
  persisted user message keeps the caption, or a short note when there is none).
  For the turn, each attachment is handed to the agent adapter, which materialises
  it in its own native shape — a vision agent (Claude Code) inlines an image as a
  base64 content block it sees directly and a PDF as a document block; a
  path-native agent (Codex) and any non-vision file receive the on-disk path to
  open. This keeps history small, works for arbitrary file types, and generalises
  to future modalities (a new type is a new mime, not a new schema). See
  [Channel Media](../../../docs/decisions/channel-media.md).
- **FR-018**: The agent sends a file back to the user by an explicit opt-in: a
  line-anchored sentinel `MEDIA:/absolute/path` (optionally `MEDIA:/absolute/path |
  caption`), told to it by FR-016's system note. On a transport that declares
  `supports_media`, the channel uploads that file (an image extension as an inline
  photo, otherwise a document) and strips the line from the delivered text; ordinary
  prose — including a legitimate markdown image `![alt](path)` written only to
  reference a file — is not this syntax and is never uploaded, and a sentinel whose
  file is missing, relative, or oversized is left as text. The unambiguous sentinel
  keeps outbound file delivery deliberate, not guessed, and never collides with
  normal markdown.
- **FR-019**: An inbound voice message drives a turn as a transcript. The built-in
  agents (Claude Code, Codex) cannot hear audio, so the adapter transcribes the
  audio to text and folds it into the turn's prompt. Transcription is a per-agent
  seam ([Channel Media](../../../docs/decisions/channel-media.md)); a future
  audio-native agent's adapter forwards the audio instead of transcribing.

  Transcription runs **remotely**, on the connection the user designated
  `transcribe_default` (spec `provider-switching` FR-035) and the speech-to-text
  model chosen beside it (spec `internal-engine` FR-025). That is a different
  connection from the one Coffer's own engine runs on, and there is no fallback
  between them: a gateway that serves chat completions commonly serves no
  transcription endpoint at all. The endpoint is OpenAI-shaped
  (`POST <base_url>/audio/transcriptions`); a connection whose protocol has none
  is not used for it.

  **This is the one place in Coffer where user content may leave the machine, and
  it is off by default.** With no connection designated for transcription, no
  model chosen for it, an unsupported protocol, or a credential that will not
  resolve, nothing is uploaded: the voice is handed to the agent as an audio file
  rather than lost. A failed or slow
  request degrades the same way — a transcription problem must never fail a turn.
  The constitution permits this: Principle I admits cloud services as **LLM and
  tool providers**, and a transcription endpoint is a tool provider; the audio is
  data in transit rather than vault state, and the transcript lands locally like
  any other turn text.
- **FR-020**: A group chat is a first-class peer. When the paired owner
  @mentions the bot (or the message is delivered as an addressed group event)
  the bot answers there; the group becomes an additional `channel_peers` row
  keyed by `(channel, group chat id)`, inheriting the owner's `sender_id`.
- **FR-021**: The bot acts in a group ONLY on an addressed message (an
  @mention of the bot). Un-addressed group messages are ignored. An addressed
  message from a non-owner is refused with a short "not authorized" reply and
  starts no turn.
- **FR-022**: Forwarded chat records are flattened into readable text folded
  into the turn so the agent sees them. Each entry renders as
  `<sender>: <text | [image] url | [file] name>` under a
  `[Forwarded chat record]` heading. Where a platform's file links require auth,
  its child spec states how the bytes are additionally fetched so a vision agent
  sees the picture rather than a dead link.
- **FR-023**: Threads are read and replied-to in place, and a group reply
  always lands in a thread — never the group main chat. A DM or group message
  sent in a thread also replies into that thread. Reading *recent group-main*
  history is intentionally NOT done: the addressed message is self-contained,
  and the permission to read a group's back-chatter is not something this
  product asks for. How a thread is identified, and whether its history can be
  fetched at all, is a platform fact each child spec states. A quoted/replied
  message contributes a `> sender: …` context prefix where the platform inlines
  it.
- **FR-024**: Each `(channel, chat, thread)` maps to its own conversation and
  renders its own turn, so a DM turn, a group-main turn, and a thread turn never
  share state. What waits behind a running turn is that conversation's pending
  queue (spec `chat`), not a buffer of the channel's own.
- **FR-025**: A channel MUST carry the framework's `scope`
  ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)),
  one allow-list of agents, read as **the agents this channel may drive**. Every
  other kind's scope names the agents a resource is *delivered to*; a channel is
  consumed by no agent — it is an inbound surface — so the list is inverted
  rather than borrowed, and the spec says so explicitly because a reader who
  assumes the usual reading gets it backwards. That inverted reading is the
  whole of what a channel's scope says: there is nothing in it about WHICH
  MACHINE runs the channel. That question has its own field, `runs_on`
  (FR-026), for a reason scope cannot satisfy: scope is reach, reach is
  machine-local and never travels, and the machine that runs a channel is one
  answer the machines must share.

  - An unrestricted scope MUST mean every registered agent. That is the
    pre-scope behaviour and what every existing channel carries, so no channel
    needs a data migration.
  - `agents: [<agent>, …]` MUST narrow `/agent` at all three of its surfaces:
    the listing, the selection card, and the validation of a chosen key
    (typed or tapped). They MUST read one narrowed set — a card that offers an
    agent the next check rejects is the specific failure this requires.
  - **One vocabulary above the binding.** A scope and a `default_agent` both
    name agent **uids**, which is also what a reach picker offers, so every
    comparison between them is made directly and no translation exists to get
    backwards. A uid this vault does not hold admits no agent at all.
  - **One crossing, below it.** `/agent`, the sticky per-thread choice and the
    turn router all speak the agent **key** the turn platform routes on. That
    key MUST be derived from the uid at exactly ONE place — the runtime gate,
    where the resource row becomes a live binding — and nothing below that point
    may hold a uid. Two agent resources of the same type collapse to one key
    there. While the two vocabularies met in several places at once, each of
    them compared a scope written in one to a default written in the other:
    the only narrowing a user could express was refused, and the value accepted
    in its place was one the reach picker then had to render as an agent
    registered nowhere.
  - **The invariant:** a channel's `default_agent` MUST be an agent the channel
    may drive — registered in this vault, and inside its scope whenever that
    scope is non-empty. It MUST be enforced on BOTH write paths, so the
    inconsistent state cannot be stored at all: a registration or an edit of the
    configuration is rejected when it names a `default_agent` that is unknown or
    outside the current scope, and an edit to the scope is rejected when the
    proposed non-empty scope excludes the current `default_agent`. A scope edit
    MUST NOT be accepted and then leave the channel unable to run. Each
    rejection MUST name both sides **by label**, not by uid, so the owner sees
    the two ways forward: widen the scope, or change the default agent first.
  - **A channel that can route nowhere MUST NOT start.** Three states mean it:
    it names no `default_agent` at all, its scope excludes the one it names, or
    that uid names no agent registered here. In each the runtime declines to
    start the adapter and records why, and the management surface reports the
    channel as not running. There is NO fallback agent: `default_agent` is a
    reference to an agent resource and a uid is minted per vault, so nothing a
    schema could name would stand for "the usual agent". Silence with a reason
    beats a bot that answers as an agent nobody chose.
  - `agents: []` (dormant) MUST mean the channel drives nothing, and MUST fail
    early rather than per-turn: the runtime does not start its adapter, so no
    message is ever accepted only to be refused. The management surface reports
    it as not running. Widening the scope is how the owner brings it back.
  - `agents: []` MUST be accepted on both write paths. It is the vault-wide
    meaning of dormant — this channel is off — and off MUST NOT also mean
    frozen: a channel the owner deliberately switched off MUST remain editable,
    so a wrong bot token or tunnel token can still be corrected without
    reactivating it first.
  - A thread's sticky `/agent` choice MUST be dropped in favour of the channel
    default once the scope no longer admits it, so narrowing a scope takes
    effect on the next conversation rather than waiting on whoever set the
    preference.
- **FR-026**: A channel MUST name the one machine that runs it. Its
  configuration carries `runs_on`, the `machine_id` of the machine whose daemon
  starts this channel's adapter (spec `vault-sync`, "Identity is derived"). It is
  configuration and not a property of the row, because it MUST travel with the
  channel document; reach MUST NOT travel and MUST NOT be made to carry this
  (see "Where a channel runs").

  - The binding MUST be authoritative for adapter startup. A runtime MUST start
    an adapter only for a channel whose `runs_on` is this machine's id, and MUST
    fail **closed** otherwise: an unknown machine, a retired one, and no binding
    at all all mean "not this machine", and none of them may be read as
    permission to start. Starting on a guess cannot be walked back — the
    platform has already been answered twice.
  - **Unbound MUST run nowhere**, and MUST be reported rather than left to look
    like a stopped adapter. A channel registered through any Coffer surface MUST
    be bound to the registering machine at creation, so unbound is reached by
    import or by hand, not by using the product.
  - A binding naming a machine no longer in the registry MUST be reported as a
    fault on the channel, distinctly from a channel that is merely bound
    elsewhere. Both run nowhere here; only one of them is somebody's mistake.
  - A `runs_on` that **cannot be a machine id** MUST NOT be honoured as a
    binding. A channel's configuration is a bag the system has written other
    things into before — the retired machine axis put ULIDs under this very
    key — so a value of the wrong shape names no machine that has ever existed
    and is a fossil, not a decision. Coffer MUST bind such a channel to this
    machine, the answer it would have given had the key been absent. This is
    the one case where an existing value is overwritten, and it is the one case
    where leaving it would silently stop a working bot on upgrade.
  - Rebinding MUST converge without a restart and without a command that reaches
    another machine. The losing machine MUST stop its adapter within one
    reconcile tick of seeing the change; the gaining machine MUST start one
    within one tick of the converge round that brings the change to it. The
    surface offering the rebind MUST say that binding a channel to the machine
    the user is sitting at, while another machine still holds it, leaves both
    live until that machine's next round.
  - A channel's configuration MUST carry credential **references** only, never
    secret material, exactly as it did when it never travelled — the rule is
    unchanged, and travelling is what makes it load-bearing rather than merely
    tidy. Ciphertext for those refs travels only when the user opts the remote
    in to credentials, and a machine holding ciphertext without the master key
    MUST report those refs locked rather than failing decryption silently.
  - A channel bound to another machine MUST NOT be refused by this machine's
    own preconditions. Its `default_agent` names an agent on the machine that
    runs it; validating that here would hold a good document out of the registry
    for a fault on nobody's machine.

### One bot, all agents, one management surface

- **FR-027**: One bot controls all agents. A single paired Coffer-hosted bot
  drives any managed agent, switchable via `/agent` and selection cards; agent
  choice is per conversation, and since each thread is its own conversation
  (FR-032) one bot can run different agents in different threads concurrently.
  This is the capability no agent-native or official channel offers, and the
  reason the channel plane exists.
- **FR-028**: Coffer-hosted channels have a unified management surface. A
  management view lists every Coffer-hosted channel with its status, paired
  owner, agent, and health, mirroring the MCP-server / memory / skill management
  surfaces; each channel's credentials (bot tokens, app secrets) are held in the
  Coffer vault. Externally-hosted channels are out of scope (a non-goal).

### A. Media pipeline completeness

- **FR-029**: Thread-history media is downloaded, not flattened to a dead link.
  When the owner @mentions the bot inside a thread on a transport that can fetch
  thread history, the media carried by the thread's own messages is downloaded
  and attached to the turn, alongside the flattened text. (Previously thread
  media surfaced only as an auth-gated `[image] <url>` the agent could not open.)
- **FR-030**: PDFs and office documents reach every agent as extracted text, not
  as a vision input. A document attachment is text-extracted into a context
  block so path-native agents (Codex) and vision agents alike
  see its content; images stay vision-inlined for agents that support it.
- **FR-031**: Outbound media is thread-aware. On a `supports_media` transport an
  agent's `MEDIA:/path` sentinel (FR-018) sends the file back into the same chat
  **and thread** the turn came from — a generated chart returns to the group
  thread, not the main chat.

### B. Conversation model

- **FR-032**: Each group thread is its own conversation. Conversation identity is
  keyed by `(channel, chat_id, thread_id)`, not by the peer alone. A DM
  (`thread_id=""`) is one conversation; each thread in a group is independent —
  its own history and its own turn lock. Concurrent turns in different threads
  of one group no longer collide on a single conversation. Pairing/owner
  identity stays on the peer row.
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
  [Persisted Attachment Reference](../../../docs/decisions/persisted-attachment-reference.md).
- **FR-034**: Every turn carries its own origin. The turn text opens with a
  `[Message origin]` block naming the platform, the chat (kind, the chat title
  where the platform supplies one, and always the chat id), the thread, and the
  sender (display name **and** the stable platform id, which a platform tool
  call takes and which, in a group, appears nowhere else because `chat_id` is
  the group's) — so an agent asked "which group is this?" answers from the turn
  it was given instead of listing the bot's groups and inferring, and a platform
  tool call has a chat id to aim at. The block is folded in after command
  detection (a prefixed `/help` would stop being a command) and after the
  empty-envelope check, and is persisted on the user message exactly like thread
  context — the single source of truth (FR-033) stays one string. It rides on
  **every** turn, not just a conversation's first: `/agent` can swap the agent
  mid-conversation (FR-027) and a resumed session would otherwise lose it. Title
  and sender name are chat-member-settable, so both are collapsed to one clipped
  line before they reach the prompt — a rename cannot forge extra origin lines.
  Where a platform hands the chat title over for free it is included; where it
  does not the chat is named by id alone, which an agent can resolve to a name
  through the platform's own tools.

### C. Group UX and gating

- **FR-035**: Group selection-card taps route to the group/thread.
  `InboundCallback` carries `chat_kind`/`thread_id` and is owner-gated by the
  group's peer (`get_by_chat`, not the single-peer `get`); a button tap's reply
  lands in the same group/thread, not a DM.
- **FR-036**: Per-group inbound gating is configurable. A channel may set
  require-mention (default on for groups — the bot answers only when @mentioned
  or replied-to) and ignore-messages-that-@-someone-else (opt-in — a group
  message that @mentions any non-bot user is dropped silently, even when it also
  mentions the bot) — so a bot sitting in a busy group answers only when it
  should. Both are plain config bools; the channel stays owner-gated regardless,
  so this is about *when* to answer, not *who* may drive turns.

### D. Platform polish

- **FR-037**: Receipt and progress are acknowledged, capability-gated (never by
  transport type). On a `supports_reactions` transport an ack reaction (👀) marks
  receipt on the owner's own message immediately, and a ✅ marks completion on a
  clean finish (an errored/interrupted turn keeps just the receipt). A transport
  without reactions uses its typing/working signal as the receipt-and-progress
  cue instead. All best-effort — a failed ack never breaks the turn.
- **FR-038**: A reply grows in place, by whatever live-text mechanism the
  platform has — chosen from the adapter's declared capabilities, never its
  type. The capability the core asks about is `supports_live_text` ("is there a
  surface I can keep updating while this turn runs?"), NOT `supports_edit`
  ("can a delivered message be rewritten?"). The two flags are set
  independently, because a transport can have a live surface while being unable
  to rewrite a delivered message at all; keying the strategy on `supports_edit`
  silently denied such a transport the live experience it does support, and its
  replies arrived as several chunked messages at the end of the turn.

  A turn keeps exactly ONE live surface. WHEN it opens depends on whether that
  surface becomes the reply or is scaffolding thrown away at the end, which the
  adapter declares as `live_text_persists`. Where it persists, the surface opens
  the moment the turn starts and says so — an acknowledgement the user can see,
  because the wait between a message and an answer is otherwise the whole of
  what they get, and on a long turn it reads as the bot having missed them. That
  acknowledgement costs no extra message: the reply is the same one, rewritten
  in place. Where the surface is scaffolding, it opens only once the turn has
  run past the update interval — either tool activity opens it or the reply text
  does — so a reply that finishes sooner opens none, avoiding a create → delete
  → resend flicker.

  The cadence of updates belongs to the TRANSPORT, which alone knows its own
  limits: the core offers every snapshot and each surface buffers to what it can
  sustain. A throttle added by the core on top hides that buffer completely and
  makes a stream arrive a paragraph at a time. Interim snapshots are clipped to
  the platform's per-message limit and their formatting characters are ESCAPED,
  so a long or half-written-markdown preview never breaks a platform parser or
  exceeds the cap. They are escaped rather than sent as plain text because the
  message has to be able to carry an @mention from the moment it is created
  (FR-054), and a mention is only a name in rich text.

  How a surface *ends* is the transport's business, and each child spec states
  its own. A transport with no live surface at all posts no interim traffic; its
  final reply is the whole signal. All best-effort — a failed update, close, or
  heartbeat never breaks the turn.
- **FR-039**: Inbound events are de-duplicated. A redelivered platform event
  (same message id) is processed once.
- **FR-040**: A quoted message is surfaced, not resolved. Where the platform
  tells the transport that the user replied by quoting, the envelope keeps the
  quoted message's id and the origin block (FR-034) names it, so an agent
  reading "as I said above" can tell that *above* refers to something specific
  instead of guessing from the visible text. The transport deliberately stops at
  the id: fetching the quoted body is an on-demand lookup the agent performs for
  itself through the platform's own tools, not transport work that must happen
  on every turn whether or not anyone needs it. The id is a handle scoped to
  this bot, not a durable identifier.
- **FR-041**: A thread grounds its turn in a DM too, not only in a group.
  FR-029's thread-context fetch was written when only group chats threaded;
  direct chats with a bot thread as well, and a transport that can fetch a DM
  thread does so — same flatten, same media download, same degrade-to-empty on
  any failure. The asymmetry this removes was real and invisible: a DM thread
  was already replied to in place (FR-023) yet the turn driving that reply could
  not see anything else in the thread. Group-*main* chatter is still never
  fetched.
- **FR-042**: The bot's own standing in a group is tracked. Platform events that
  change what a binding *is* rather than driving a turn arrive on a lifecycle
  callback kept separate from messages and card taps, so no consumer of those
  has to filter them out. Removal from a group stops every live session for that
  chat; nothing is sent back, because the bot is no longer there to send it. A
  conversion that lets people from other organisations read a chat the owner
  paired is a security-relevant change and so is announced in the group itself
  rather than only written to a log — the owner is by definition present, and
  the group is the one place the warning is in context. Both are de-duplicated
  like every other event (FR-039): a redelivered removal must not fire twice.
  Each child spec names its platform's events and how they normalise onto this
  one envelope, so the rule is one rule and not one per platform. Being *added*
  is deliberately not an event: anyone can add a bot to a group, and pairing
  (FR-003) is the gate.

### E. Platform parity

Each platform carries a family of surfaces built for exactly this shape of bot:
a message that streams while an agent generates it, a stop control the platform
draws itself, structured rich text, and a group reply only one member can see.
Coffer uses each one where the platform it reaches offers it, and keeps its own
hand-built equivalent as the fallback beneath it, because the platform version a
user reaches is not guaranteed to be new enough. Every requirement here is
therefore two mechanisms and a probe, not one mechanism.

- **FR-043**: Platform capability is probed, never assumed. On start the
  transport reads what the platform says about itself and keeps the fields that
  change what it may do. A capability introduced after the platform version the
  user actually reaches is attempted once and **latched off for the process** on
  the platform's own rejection, falling back to the mechanism it replaced. A
  Coffer running against an older platform therefore degrades in formatting and
  liveness, never in delivery.
- **FR-044**: A configuration that a platform-side setting silently defeats is
  diagnosed, not silently broken. Where a channel's configuration looks correct
  in Coffer and does nothing in the chat because of a setting that lives on the
  platform, the channel's health surface (FR-028) MUST report that state and
  name the fix.
- **FR-045**: A reply renders in the platform's own rich format where it has
  one. An agent answers in markdown — headings, lists, tables, block quotes,
  fenced code — and a platform whose own rich message carries those natively
  receives one, rather than the flattened subset that demotes a heading to bold,
  a bullet to a glyph, and passes a table through as raw pipes. The existing
  renderer stays as the fallback FR-043 selects.
- **FR-046**: A live reply uses the platform's own streaming surface **where
  there is one for that chat**. Where the platform can stream a partial message
  while it is generated, the live-text handle (FR-038) drives that instead of
  rewriting a delivered message: no status message to delete, no rewrite of an
  already-delivered message, and no edit-rate ceiling on how often progress may
  show. A streaming surface the platform offers only in some chats is used only
  there; everywhere else the transport keeps the mechanism it had, rather than
  spending a refused call per snapshot to show nothing. A snapshot past whatever
  the surface may carry is clipped to its tail — the newest words are the ones
  being watched — because a refused snapshot would kill the progress indicator
  mid-reply.
- **FR-047**: The platform's own stop control ends the turn. Where a live
  surface advertises a stop control the platform draws, Coffer MUST route the
  press to the same interrupt path as `/stop` — same turn cancellation, same
  queue pause, same user-visible outcome. A stop control the user can see but
  that does not stop anything is worse than none, so the button is only
  advertised on a transport where the route is wired.
- **FR-048**: Chatter that is not the answer stays private in a group. Command
  output and errors are addressed to one member, not to the room, wherever the
  platform can deliver a message only that member's client shows; the agent's
  actual reply is always an ordinary message the group can see. This is the
  group-noise half of FR-021: that requirement stops the bot from *acting* on
  everything, this one stops it from *saying* everything out loud. Every command
  declares which side of that line it falls on, on the same roster FR-049
  registers the menu from: `/new` and `/stop` change state the whole room shares
  and stay visible, and so does `/save`, whose outcome is a file the room's
  other members can be expected to want to know about; the ones that answer only
  the asker — `/agent`, `/model`, `/effort`, `/status`, `/help` — are delivered
  privately where the transport can. A roster entry that declares nothing is
  **visible**, so privacy is something a command opts into rather than something
  it acquires by omission; a command that is not on the roster at all is
  answered privately, because an "unknown command" scolding is the least useful
  thing to broadcast. The two defaults differ because they answer different
  questions — what a command Coffer ships decided, versus what to do with a
  string nobody declared.

  **Selection cards are deliberately excluded.** A card is the one surface that
  must be *rewritten* after it is used (FR-015), and a privately-delivered
  message is rewritten through a different address space whose delivery the
  platform does not guarantee. A card that cannot be reliably rewritten keeps
  offering the option already taken, which is precisely what FR-015 exists to
  prevent, so a card stays an ordinary message until the rewrite is as reliable
  as the send.
- **FR-049**: The bot introduces itself. Its command menu is registered with
  the platform from Coffer's own command roster, and its prose profile
  (description, short description) is **filled in when empty**, so a user
  opening the bot for the first time sees what it is and what it accepts
  instead of an empty chat. The registered menu MUST list every command the
  channel actually handles — a command the help text offers but the menu omits
  is a drift bug, not a design choice. This is enforced structurally rather than
  by review: the menu, the help text and the per-command privacy flag (FR-048)
  are all rendered from one roster, so adding a command is one entry plus its
  handler, with no second list to forget. Copy the owner already wrote, and the
  bot's name, are their branding decision and MUST NOT be overwritten.
- **FR-050**: Pairing is one tap. Where the platform supports a parameterised
  start link, the pairing code (FR-003) is issued as a link that carries it, so
  the owner pairs by opening the link instead of transcribing eight characters
  on a phone. The typed code keeps working — the link is an additional way in,
  and the same single-use, TTL-bounded, attempt-bounded gate applies to both.
- **FR-051**: Every inbound media type drives a turn, or says why it cannot.
  Whatever the platform can attach to a message is downloaded and becomes an
  `Attachment` (FR-017). Where a platform caps what a bot may download, a file
  over that cap MUST produce a message telling the user, not a silent no-op: the
  failure mode being fixed is a user who sent a file and got an answer that
  never mentions it. A download that fails after the platform handed over a
  fetchable reference is noted in the turn text and the turn still runs on
  whatever text and other attachments arrived.
- **FR-052**: A reply is attached to what it answers. In a group, the bot's
  reply MUST be sent as a platform-level reply to the message that triggered it,
  so a busy room can tell which question each answer belongs to.
- **FR-053**: Selection cards speak the platform's button vocabulary. Where the
  platform offers button semantics beyond a label — a disabled state, an intent
  colour — the card uses them, so the option already taken is shown disabled
  rather than re-offered.
- **FR-054**: A group answer names who it is for, and notifies them. In a group,
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
    not always the id the owner gate matches — so the transport carries both.
    Where the platform documents a second way to address a member, it is a
    FALLBACK for a sender whose id is missing, never the primary: the id is the
    identifier that is always present.
  - It degrades silently: no id and no usable fallback, or a transport that
    cannot mention from an id alone, yields an ordinary unmentioned reply — never
    a broken tag.

### Key Entities

- **Channel** — a resource of kind `channel`, addressed by its immutable `uid`
  ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md));
  config = type, credential refs,
  default agent + config, and `runs_on` — the `machine_id` of the one machine
  whose daemon runs this channel's adapter (see "Where a channel runs").
- **ChannelPeer** — the paired owner of a channel: `(resource, chat_id)`,
  display name, paired-at, pointer to the active conversation, the paired
  sender's identity (`sender_id`), and sticky preferences (chosen agent).
  One row per (channel, chat): the paired owner plus one row per
  group/thread the owner has addressed the bot in.
- **InboundMessage / InboundCallback / OutboundMessage** — the normalized
  envelopes every adapter produces and consumes; the core never sees platform
  payloads. Inbound carries the sender's identity (`sender_id`) for the owner
  gate. An `InboundCallback` is a selection-card button tap (an opaque `data`
  value instead of text, FR-015); outbound text MAY carry `ChoiceButton`s, which
  a button-capable transport renders as a selection card.
- **ChannelCapabilities** — what an adapter declares it can do (a live-updating
  surface via `supports_live_text`, rewriting a delivered message via
  `supports_edit` — the two are independent, see FR-038 — interactive buttons
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
- **SC-004**: Any agent registered on the turn platform is reachable from any
  channel with no channel-side code change (demonstrated by driving a channel
  against a scripted second provider in tests).
- **SC-005**: Every acceptance scenario below is covered by at least one
  test; `make verify` passes.
- **SC-006**: From one paired chat the owner reaches every registered agent
  with a chosen model (demonstrated by driving two scripted providers in tests).
- **SC-007**: Every pairing — the code issued and the sender who claimed it — is
  queryable in the audit log by channel; and a clean success
  sends no completion summary on any channel, while a turn that ends abnormally
  (failed, interrupted, tool-limit) sends one reporting the outcome.

## Where a channel runs

A channel's platform identity — a polled bot, a webhook endpoint, a held
WebSocket — tolerates exactly ONE consumer. So "which machine answers this bot"
must have exactly one answer, and that answer is written down: **a channel is
bound to one machine**, and only the bound machine's daemon starts an adapter
for it.

The binding is `runs_on`, a `machine_id` (spec `vault-sync`, "Identity is
derived") in the channel's own configuration. It is configuration, not a
property of the row, and that is the load-bearing choice: configuration is what
a resource document carries between machines, so the binding travels with the
channel it binds. Every machine holding the document reads the same name, and
every machine but one finds it is not being named.

### Reach and the binding answer different questions

They are easy to confuse and must never be merged.

| | Reach (`enabled` + `scope`) | Binding (`runs_on`) |
| --- | --- | --- |
| Question | **which agents** may this channel drive, and is it live here | **which machine** runs the adapter |
| Travels? | no — set per machine, stays on it | **yes** — it is one answer for the whole vault |
| Where | the resource row | the channel's config |

A channel's `scope` still says exactly one thing and it is still not about
machines (FR-025): it names the agents the channel may DRIVE. Giving the
binding a home in `scope` would have made "where does this apply" carry two
unrelated answers. The binding is the opposite kind of fact: it is one decision
the machines share, which is why it travels and reach does not.

### What the runtime does with it

The runtime starts an adapter only for a channel bound to the machine it is
running on. Everything else fails **closed** — nothing is started — and the
three cases are distinguished in what the surfaces report rather than in what
the runtime does. **Bound to another machine** is normal and says so, so a
channel that is quiet here never looks like a channel that crashed here.
**Bound to a machine the registry does not know** is reported as a fault,
because starting a channel on the grounds that nobody else claims it is the
rival-consumer failure arriving by the back door: every machine that cannot
resolve the id would reason identically and they would all start. **Unbound**
also runs nowhere and is also reported, since a document naming no machine means
the same thing on every machine that holds it.

Two adapters can still be pointed at one bot identity, but only the way they
always could — by someone registering the same bot twice, by hand, under two
names — and no field inside Coffer could have prevented that one.

### Rebinding

Changing `runs_on` from machine A to machine B is an ordinary configuration
edit, and it converges the ordinary way — no restart, and no command that
reaches across to another machine. The machine that loses the channel stops its
adapter on its next reconcile tick after it sees the change; the machine that
gains it starts one on its next tick after the converge round lands the document
there. So the clean way to hand a channel over is to rebind it from the machine
that currently holds it. Rebinding TO the machine one is sitting at while
another machine still holds the channel is allowed and is sometimes the only
option — the old machine may be the one that is broken — but it opens a window,
bounded by that machine's sync interval, in which both adapters are live. The
surface that offers the rebind says so.

### Pairings travel with the channel

A channel's peer pairings are synced state (spec `vault-sync`, `## What syncs`),
because a channel that travels without them makes the owner re-pair from their
phone every time it moves, and a rebind is meant to be one click. What travels
is platform identity — chat id, sender id, display name, the chat's sticky
agent. The active conversation pointer does not: conversations are machine-local
and a published pointer would name a conversation the other machine does not
have.

## Acceptance Scenarios

### Scenario: register a telegram channel

- **Given** a bot token stored under a credential ref
- **When** the user registers a channel named `tg` with type telegram and that ref
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
- **When** the user opens the turn platform's conversation APIs
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
- **Then** the text arrives in the IM chat both times

### Scenario: notify on an unpaired channel fails cleanly

- **Given** a channel with no paired peer
- **When** notify is called
- **Then** the call fails with a clear error and nothing is sent

### Scenario: disable stops the adapter and enable restarts it

- **Given** an enabled telegram channel with a running adapter
- **When** the user disables and re-enables the channel
- **Then** polling stops while disabled and resumes after enabling

### Scenario: only the machine a channel names starts its adapter

- **Given** an enabled channel bound to another machine's `machine_id`
- **When** the runtime reconciles
- **Then** no adapter is started here, and the management surface reports the
  channel as bound elsewhere rather than as stopped

### Scenario: a channel bound to an unknown machine starts nowhere

- **Given** an enabled channel whose binding names a machine the registry does
  not hold
- **When** the runtime reconciles on any machine
- **Then** no machine starts an adapter for it, and the channel is reported as
  bound to a machine that no longer exists

### Scenario: an unbound channel runs nowhere and says so

- **Given** an enabled channel whose configuration carries no binding
- **When** the runtime reconciles
- **Then** no adapter is started, and the channel's status carries a diagnostic
  naming the missing binding and the fix

### Scenario: rebinding hands the channel over without a restart

- **Given** an enabled channel running on this machine
- **When** the user binds it to another machine
- **Then** this machine stops its adapter on the next reconcile, without a
  daemon restart, and the channel's binding is what the next converge round
  publishes

### Scenario: deleting a channel cleans up its runtime and peer

- **Given** an enabled, paired channel
- **When** the user deletes the channel resource
- **Then** the adapter stops and the peer binding is removed

### Scenario: channel status reports runtime, pairing, and callback details

- **Given** channels in various states
- **When** the user queries status via REST and CLI
- **Then** adapter run state, paired peer, and the channel type's own ingress
  facts are reported accurately

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

### Scenario: the streamed reply preview is clipped to the platform limit

- **Given** a paired channel on an adapter that can edit messages
- **When** the accumulating reply text grows past the platform's per-message limit
- **Then** each interim edit is clipped to that limit (keeping the most recent
  text behind a leading ellipsis) so the edit never fails, while the final reply
  carries the full text

### Scenario: a transport with no live-text surface posts no interim status message

- **Given** a paired channel on an adapter that can neither edit nor stream and
  declares no typing signal either, in a group/thread
- **When** a turn runs
- **Then** no interim signal is posted at all — only the final chunked reply
  lands in the originating group/thread

### Scenario: a reply grows in place on a transport that streams but cannot edit

- **Given** a paired channel on an adapter that cannot edit or delete a message
  but can stream one, in a group/thread
- **When** a turn runs tools and then writes its reply
- **Then** exactly ONE message reaches the chat and grows in place — tool
  progress first, then the accumulating reply — and it finishes carrying the
  final reply, so nothing is sent twice and the answer never arrives as
  fragments

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
- **Then** a turn runs and the reply is delivered into a thread rather than the
  group main chat, no thread history is read, and a `channel_peers` row is
  created for the group chat inheriting the owner's `sender_id`

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

### Scenario: a redelivered event is processed once

- **Given** a paired channel that has already handled an inbound event
- **When** the platform redelivers that same event (same id) after a slow ack or
  a network hiccup
- **Then** the redelivery is dropped and the turn runs exactly once — no double
  reply or duplicate work — while a genuinely new event still drives its own turn

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

- **Given** a paired channel on an adapter that supports reactions
- **When** the owner sends a message that drives a clean turn
- **Then** a 👀 reaction is set on the owner's own message immediately on receipt and
  a ✅ reaction on completion, both targeting that inbound message id

### Scenario: a transport without reaction support attempts no reaction

- **Given** a paired channel on an adapter that does not support reactions,
  whose receipt-and-progress cue is the typing signal
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

### Scenario: a channel may only route to the agents in its scope

- **Given** a paired channel whose scope names one of the two registered agents,
- **When** the owner sends `/agent`, and then `/agent <the other one>`,
- **Then** the listing and the selection card offer only the scoped agent, and
  the switch to the other one is refused — whether it is typed or tapped from a
  card rendered before the scope was narrowed.

### Scenario: a channel's scope names agent resources, not agent keys

- **Given** a running channel whose default agent is registered as a resource
  under its own name,
- **When** the owner narrows the channel's scope to that resource name — the
  only name the reach control offers,
- **Then** the edit is accepted, the channel keeps running, and the scope
  reaches `/agent` translated into the agent key that surface speaks.

### Scenario: a channel scoped to no agent is dormant

- **Given** an enabled channel whose scope is set to the empty list,
- **When** the channel runtime reconciles,
- **Then** its adapter is never started and the channel reports as not running,
  so it accepts no turn it would have to refuse.

### Scenario: reject narrowing a channel's scope past its default agent

- **Given** a running channel whose `default_agent` is one registered agent,
- **When** the owner narrows its scope to a non-empty set that excludes that
  agent,
- **Then** the edit is rejected with a message naming both the default agent and
  the proposed scope — by the labels the owner gave them, not by uid — nothing
  is persisted, and the channel keeps running: the narrowing never silently
  takes the bot offline.

### Scenario: a channel bound to an agent that does not exist is refused

- **Given** a vault with at least one registered agent,
- **When** a channel is registered, or edited, with a `default_agent` naming no
  agent resource in this vault,
- **Then** the write is rejected and no row is created or changed, rather than
  the channel being stored and failing at its first turn.

### Scenario: a channel bound to no agent never starts

- **Given** an enabled channel whose `default_agent` is unset, or names an agent
  this machine does not have,
- **When** the channel runtime reconciles,
- **Then** its adapter is never started, the reason is recorded, and the channel
  reports as not running — it is never started against a substitute agent.

### Scenario: edit a dormant channel's configuration

- **Given** a channel the owner switched off by scoping it to no agent,
- **When** the owner corrects a field of its configuration, such as its bot
  token ref,
- **Then** the edit is accepted and the channel stays dormant — off is not
  frozen.

### Scenario: a document sent to a channel is saved into a collection

- **Given** a paired owner who has sent a document to the channel,
- **When** the owner follows it with `/save <collection>` naming a collection
  that exists,
- **Then** the document is ingested into that collection through the same
  conversion path the Knowledge page uses,
- **And** a `/save` from anyone but the paired owner stores nothing.

### Scenario: a save that names no collection asks which one

- **Given** a paired owner who has sent a document but named no collection,
- **When** they send `/save`,
- **Then** the channel offers the collections it may save into and stores
  nothing until one is chosen — on a transport without buttons it lists them as
  text,
- **And** a `/save` with no document pending is refused in one line.

## Deliberately out of scope

**Externally-hosted channels.** An agent-native gateway (OpenClaw, Hermes run
standalone) or an official vendor integration (Claude-in-Slack, Codex-in-Slack,
Cursor-in-Slack, Claude Code's official Telegram/Discord/iMessage plugin) owns
its own transport and drives only its own agent. Coffer neither proxies these
nor manages them: stacking Coffer's channel in front would collide with their
own runtime; holding a token that is then written into an external process's own
config defeats the vault; and the official cloud integrations have no local
credential to hold at all. When a user wants one of these, they set it up
through that tool's own flow — Coffer's docs point the way, nothing more. A
native/official channel that does not support a platform simply does not run
there; **Coffer does not bridge it.** Coffer's channel plane manages only what
Coffer hosts. The survey this rests on is in `research.md`.

**A copy-to-clipboard button.** Telegram's inline buttons can carry `copy_text`,
which would let an agent hand over a command as something tappable rather than
as text to select by hand. It is not adopted, because the button is the easy
half: a `ChoiceButton` is only ever built by the agent and model cards, so an
agent has no way to *ask* for one. Giving it that way means a second
agent-facing sentinel beside `MEDIA:` — a feature with its own parsing, its own
false-positive risk on ordinary prose, and its own spec — not a field on an
existing button. Recorded here so the button is not mistaken for an oversight.

**Privately-delivered selection cards.** See FR-048: the card is the one surface
that must be rewritten after use, and a privately-delivered message is rewritten
through a different address space with delivery the platform does not guarantee.
Worth revisiting only if a platform makes that edit as reliable as an ordinary
one; the per-platform mechanics are in
[`channels/telegram`](telegram/spec.md).

**Two SeaTalk card capabilities Coffer does not use.** Recorded in
[`channels/seatalk`](seatalk/spec.md).

## Assumptions

- The user can create a bot on each platform they register — a Telegram bot via
  BotFather, a SeaTalk Open Platform app — and can obtain whatever scopes their
  organization's approval flow requires.
- Channels carry text plus inbound photos and files (FR-017): media is
  downloaded and handed to the agent, while an empty message with nothing
  downloadable gets a polite "send text, a photo, or a file" reply. Outbound is
  text plus files the agent chooses to send (FR-018, on a `supports_media`
  transport) and, as a rich exception, **command selection cards**: on a
  transport that `supports_buttons`, `/agent` and `/model` may render their
  choices as interactive buttons (FR-015).
- The turn platform this spec drives — conversations, the pending queue, the
  turn lifecycle and the web Chat page onto them — is spec `chat`. A channel
  consumes it and never reimplements it.
