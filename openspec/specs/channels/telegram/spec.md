# Feature Specification: Channels — Telegram

**Status**: Accepted
**Input**: The Telegram half of Coffer's channel plane. Its parent,
[`channels`](../spec.md), owns everything a channel does regardless of
platform — pairing, the owner gate, commands, conversations, media policy,
scope and machine binding. This spec owns what only Telegram's Bot API can
answer: how events arrive, how a reply is rendered and grown in place, what a
card is made of, and which of the Bot API's newer surfaces Coffer reaches for
when the server it talks to offers them.

Requirements here are numbered from FR-001 and are this spec's own. A bare
`FR-00N` below means this spec; the parent's are cited as `channels FR-00N`.

The Bot API carries a family of surfaces built for exactly this shape of bot: a
message that streams while an agent generates it, a stop control the platform
draws itself, structured rich text, and a group reply only one member can see.
Coffer uses each one where the Bot API server it reaches offers it, and keeps
its own hand-built equivalent — an edited message standing in for a stream, a
typed `/stop`, an HTML subset standing in for markdown — as the fallback
beneath it, because the Bot API server a user reaches is not guaranteed to be
new enough. Every capability here is therefore two mechanisms and a probe, not
one mechanism (`channels FR-044`).

## User Scenarios & Testing

### User Story 1 — Reach an agent from Telegram (Priority: P1)

The user creates a bot with BotFather, registers it as a Telegram channel, pairs
their own account, and talks to their agents from the app they already have on
their phone. Replies arrive as Telegram HTML, long ones chunked; while the turn
runs, one status message grows in place and is cleared away before the real
answer lands.

**Why this priority**: Telegram is the channel every user can set up alone, with
no organisation approval in the way, so it is the one that proves the parent's
contract end to end.

**Independent Test**: Against a local fake Bot API, register and pair a channel,
send a message, and observe the polling loop dispatch it, the status message
open and be deleted, and the final HTML reply arrive chunked.

**Covering scenarios**:

- reply text streams into the editable status message as it arrives
- a slow text-only reply streams into a status message
- a fast text-only reply opens no status message

---

### User Story 2 — Send the bot a photo album, a file, or a sticker (Priority: P2)

The owner sends several photos at once, a document, or a sticker. Telegram
delivers an album as separate updates sharing a `media_group_id`, so the adapter
debounces them into one turn carrying every attachment. A file too large for a
bot to download says so rather than disappearing, and nothing about a failed
download ever reaches a log with the bot token in it.

**Why this priority**: Media is how a phone user actually asks a question, and a
silently-dropped attachment produces an answer that never mentions what was sent.

**Covering scenarios**:

- a Telegram album is handled as one turn
- a failed telegram download never puts the bot token in the log

---

### User Story 3 — Be told when a platform setting defeats the configuration (Priority: P2)

The owner switches a channel to answer un-addressed group messages, and nothing
happens — because Telegram bots run with privacy mode on by default and never
receive those messages at all. The channel's health surface names the state and
the fix rather than leaving a correct-looking configuration silently inert.

**Covering scenarios**:

- privacy mode is reported when it contradicts the configuration

## Requirements

### Configuration

- **FR-001**: A Telegram channel's configuration is a **bot token reference**
  and nothing else beyond the fields every channel carries (`channels FR-001`).
  The token itself lives in the credential store; the reference is probed at
  registration.

### Transport

- **FR-002**: Telegram inbound uses **long polling**, with the update offset
  committed only after dispatch, so no inbound message is double-processed
  across a reconnect. The adapter reconnects with exponential backoff and never
  crashes the daemon.
- **FR-003**: On start the transport reads the bot's own identity from `getMe`
  and keeps the two fields that change what it may do: the bot's username, and
  whether privacy mode leaves it able to read group messages. The Bot API
  surfaces introduced later than some servers carry — **rich messages, message
  drafts, ephemeral messages** — are attempted once and latched off for the
  process on the platform's own rejection, per `channels FR-044`.
- **FR-004**: Telegram bots run with **privacy mode ON by default**, which
  withholds ordinary group messages from the bot entirely. A channel configured
  to act on un-addressed group messages (`require_mention = false`,
  `channels FR-037`) but whose bot cannot read them MUST be reported on the
  channel's health surface (`channels FR-045`) naming the fix: disable privacy
  mode in BotFather, then re-add the bot to the group.
- **FR-005**: `from.id` is the sender identity Telegram supplies. It is both the
  id the owner gate matches (`channels FR-011`) and the id a mention is built
  from (`channels FR-055`), so the two coincide on this platform. `chat.title`
  is handed over for free, so the origin block (`channels FR-035`) names the
  chat by title as well as by id.
- **FR-006**: Telegram reports the bot's departure from a group as a change to
  the bot's **own membership** (`my_chat_member`) rather than as a dedicated
  event, and the platform withholds that update unless it is named in the
  subscribed update types. The transport subscribes to it and normalises it onto
  the same lifecycle envelope every platform's removal arrives on
  (`channels FR-043`).

### Rendering

- **FR-007**: A reply is converted from the agent's markdown to **Telegram
  HTML**, with a plain-text retry when the platform rejects the formatted
  message, and chunked at **4000 characters** on paragraph boundaries.
- **FR-008**: Where the Bot API server offers **rich messages**, a reply that
  carries headings, lists, tables or fenced code is sent as one rather than
  being flattened into the HTML subset — which demotes a heading to bold, a
  bullet to a glyph, and passes a table through as raw pipes. The HTML renderer
  of FR-007 stays as the fallback that `channels FR-044` selects.

### Liveness

- **FR-009**: Telegram's live surface is **scaffolding**, not the reply: a status
  message that is edited as the turn runs and **deleted** before the real answer
  is sent. It therefore declares `live_text_persists` false, and opens only once
  the turn has run past the update interval — either tool activity opens it or
  the reply text does — so a reply that finishes sooner opens none and there is
  no create → delete → resend flicker; the 👀 receipt reaction
  (`channels FR-038`) has already said the message was heard. When the turn
  ends, the status message is deleted and the final reply is sent HTML-rendered
  and paragraph-chunked.
- **FR-010**: Where the Bot API offers a **message draft**, the live-text handle
  (`channels FR-047`) drives that instead of rewriting a delivered message. A
  draft addresses a **private chat and has no group form**, so it is used only
  in DMs; a group keeps the status-message mechanism of FR-009 rather than
  spending a refused call per snapshot.
- **FR-011**: A streamed draft MAY advertise the **stop button the platform
  draws**. When the user presses it the platform reports the stopped draft, and
  Coffer routes that to the same interrupt path as `/stop` (`channels FR-048`).
  The button is advertised only where that route is wired.

### Group UX

- **FR-012**: Where the Bot API offers **ephemeral messages** — a message only
  one member's client shows — command output and errors are delivered that way
  in a group, per `channels FR-049`. Their edit address space is different from
  an ordinary message's: Telegram edits an ordinary card by `chat_id` +
  `message_id` and an ephemeral one by `chat_id` + `receiver_user_id` +
  `ephemeral_message_id`, and documents that edit as not guaranteed to reach the
  user. That is why a selection card stays an ordinary message.

### Cards

- **FR-013**: A selection card (`channels FR-015`) is rendered as an **inline
  keyboard**, and a tap arrives as a callback query carrying the button's opaque
  value. The card's title is taken as a **bold first line**, Telegram having no
  title element of its own. Every callback value Coffer emits is fixed-size and
  well inside the **64-byte callback budget** the Bot API allows.

### Media

- **FR-014**: Every type Telegram can attach to a message — **photos, documents,
  voice, audio, video, animations, stickers, round video notes** — is downloaded
  and becomes an `Attachment` (`channels FR-018`, `channels FR-052`). A file over
  the cap the Bot API places on what a bot may download MUST produce a message
  telling the user. A download that fails after `getFile` succeeded — the
  platform answers the file endpoint with an error status, or the connection
  fails — is noted in the turn text as `[attachment '<name>' could not be
  downloaded]` and the turn still runs on whatever text and other attachments
  arrived. **The Telegram file URL embeds the bot token**, so this path MUST log
  only the failure's class, or the method and HTTP status — never the request
  URL, and never a traceback that quotes it.
- **FR-015**: Messages sharing a `media_group_id` are an **album**, delivered as
  separate updates with the caption on the first item only. They are debounced
  into a single inbound message carrying all their attachments and the album's
  caption — one turn, not one per photo — while a lone photo without a
  `media_group_id` still drives its turn immediately.

### Threads

- **FR-016**: The Bot API **cannot fetch chat history at all**, so on Telegram no
  thread context is read: the bot answers on the @mention message itself. It
  still replies into the **forum topic** the message arrived in, so
  `channels FR-024`'s reply-in-place rule holds even though its read-the-thread
  half cannot.

## Success Criteria

- **SC-001**: A user with nothing but BotFather can register, pair and get an
  agent reply, with no public URL, tunnel, or organisation approval anywhere in
  the path.
- **SC-002**: A Coffer running against an older Bot API server degrades in
  formatting and liveness only — every reply is still delivered.
- **SC-003**: No log record produced by any download path contains the bot
  token.
- **SC-004**: Every acceptance scenario below is covered by at least one test.

## Acceptance Scenarios

### Scenario: reply text streams into the editable status message as it arrives

- **Given** a paired channel on an adapter that can edit messages
- **When** the agent's reply text arrives in deltas during a turn
- **Then** the single status message shows tool-progress lines first, then is
  edited in place with the accumulating reply text (plain, not HTML) so the user
  watches the answer materialize; on finish the status message is deleted and the
  final reply is sent once (HTML-rendered and paragraph-chunked)

### Scenario: a slow text-only reply streams into a status message

- **Given** a paired channel on an adapter that can edit messages
- **When** a text-only turn (no tool calls) keeps producing reply text past the
  transport's update interval
- **Then** a status message is opened with the streaming reply text and edited in
  place as the answer grows, then deleted on finish while the final reply is sent
  once

### Scenario: a fast text-only reply opens no status message

- **Given** a paired channel on an adapter that can edit messages
- **When** a text-only turn completes within the transport's update interval
- **Then** no status message is opened (no create → delete → resend flicker) — only
  the single final reply is sent

### Scenario: a Telegram album is handled as one turn

- **Given** a paired Telegram channel
- **When** the owner sends a multi-photo album (delivered as separate messages
  that share a `media_group_id`, the caption on the first item only)
- **Then** the items are debounced and combined into a single inbound message
  carrying all their attachments and the album's caption — one turn, not one per
  photo — while a lone photo without a `media_group_id` still drives its turn
  immediately

### Scenario: privacy mode is reported when it contradicts the configuration

- **Given** a channel configured to act on unaddressed group messages,
- **When** its bot cannot read group messages,
- **Then** the channel's health reports the contradiction and names the fix.

### Scenario: a failed telegram download never puts the bot token in the log

- **Given** a Telegram message with a photo whose file download fails after
  `getFile` succeeds,
- **When** the adapter handles the message,
- **Then** the turn runs with a note that the attachment could not be
  downloaded, and no log record contains the bot token

## Assumptions

- The user can create a bot through BotFather and holds its token. No
  organisation approval, public URL, or vendor SDK is needed anywhere on this
  path.
- Two disclosed Bot API parsing caveats are accepted and documented at their
  call sites rather than specified away: mention entity offsets are matched
  against plain code-point indices even though Telegram's own offsets are UTF-16
  code units, which drifts only when a surrogate-pair character precedes the
  mention in the same message; and only `entities` on a plain text message is
  parsed for a mention, so an @mention inside a media caption is not recognized.
- The Bot API is spoken with `httpx` against the fixed host `api.telegram.org`.
  There is no SDK dependency: the surface used is a handful of methods, and an
  SDK would buy nothing while adding an import-confinement contract.
