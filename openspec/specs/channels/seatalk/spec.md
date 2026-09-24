# Channels — SeaTalk

## Purpose
The SeaTalk half of Coffer's channel plane. Its parent,
[`channels`](../spec.md), owns everything a channel does regardless of platform
— pairing, the owner gate, commands, conversations, media policy, scope and
machine binding. This spec owns what only SeaTalk can answer: its inbound
websocket transport and the configuration it needs, the streaming reply
contract, the card payload shape, thread identity, and the two ids a member has.

**SeaTalk is Coffer-hosted for every agent**, because no external gateway speaks
SeaTalk at all: there is no official Claude, Codex, Cursor or agent-native
integration for it. Everything a user does with an agent on SeaTalk goes through
this adapter or does not happen.

SeaTalk inbound has one transport: the daemon holds one outbound websocket
connection per channel and the platform pushes events down it. Nothing is
exposed — no public URL, no listener, no tunnel, no signature to check — which
is what a local-first vault that binds to loopback needs. Its price is paid
elsewhere: the platform's own client library, which the operator supplies, and
one connection per SeaTalk app, so a second machine registering the same app
takes the events away from the first. There is no webhook transport, so an
installation without the SDK has no SeaTalk inbound; see
[SeaTalk Inbound Over WebSocket](../../../../docs/decisions/seatalk-websocket-inbound.md).

The user is assumed to be able to create a SeaTalk Open Platform app, enable the
Bot capability and set it Online, and obtain the scopes their organisation's
approval flow requires (at minimum *Send Message to Bot User*). Outbound SeaTalk
is spoken with `httpx` against the fixed host `openapi.seatalk.io`; the official
SDK is used only for websocket inbound, where there is no alternative. One open
question the platform's own documentation does not settle: the streaming
parameter table marks `thread_id` optional while the group-chat request sample is
annotated "thread_id required", so whether a group-**main** stream is accepted
without one is unverified.

Deliberately out of scope:

- **Two SeaTalk card capabilities.** The platform's card format also offers
  `redirect` buttons (with `mobile_link` / `desktop_link`) and per-language card
  bodies (`{"default": …, "zh-Hans": …}`). A redirect button needs somewhere to
  send the user, and Coffer's web UI binds to loopback — a link from the owner's
  phone reaches nothing. Per-language cards need Coffer's channel copy to exist
  in more than one language; it is English-only in the backend, and the card
  would be the only translated surface in a conversation whose every other line
  comes from the agent in whatever language the owner wrote in.
- **Reading recent group-main history.** SeaTalk delivers neither emoji
  reactions nor non-@ group-main messages to a bot, and the permission that
  would grant the history endpoint is not granted to a self-built app at
  Coffer's scope. It is unbuildable here, which is why [channels](../spec.md) "Reply in place inside threads"
  states the rule as a deliberate choice rather than a gap.

## Requirements

### Requirement: Configure a SeaTalk channel by app id and secret reference
A SeaTalk channel's configuration MUST carry **`app_id` and `app_secret_ref`**
and no inbound-transport field: SeaTalk inbound has one transport (see "Receive
every event over one outbound websocket connection"), and the register handshake
authenticates it from those two values alone. The secret lives in the credential
store; the configuration carries the reference, probed at registration ([channels](../spec.md) "Register channels as a credential-referencing resource kind").

A channel stored while webhook delivery existed MUST be rewritten once, by a
migration, so that it carries none of `delivery`, `signing_secret_ref`,
`public_base_url` or `tunnel_token_ref`: a stored key that configures nothing
misdescribes the running system. The credential values those refs cited MUST be
left in the credential store rather than deleted, because a migration that
destroys secrets cannot be undone by its downgrade.

#### Scenario: a seatalk channel without an app id or secret reference is refused
- **GIVEN** a stored SeaTalk app secret under a credential reference
- **WHEN** a seatalk channel is registered missing `app_id`, or missing `app_secret_ref`
- **THEN** the registration is rejected and nothing is persisted
- **AND** the same registration carrying both is accepted with the secret held only as a reference

#### Scenario: a webhook-era seatalk channel keeps only its app credentials
- **GIVEN** a stored seatalk channel carrying `delivery: webhook`, a signing secret ref, a public base URL and a tunnel token ref
- **WHEN** the daemon's startup migrations run
- **THEN** the channel's configuration carries its `app_id`, its `app_secret_ref` and its common fields, and none of the four webhook-era keys
- **AND** the credential values the removed refs cited are still in the credential store

### Requirement: Load the websocket client library from an operator-supplied directory
The WebSocket client library MUST be an **operator-supplied optional
dependency**, never a vendored one. The only client for SeaTalk's websocket
delivery is the platform's own SDK, distributed from an internal corporate
portal, absent from public PyPI, and published under no public licence — so
Coffer, which is MIT, MUST NOT vendor it into this repository and MUST NOT
declare it as a dependency. Reimplementing its wire protocol is not an
alternative either: none is published. See
[SeaTalk Inbound Over WebSocket](../../../../docs/decisions/seatalk-websocket-inbound.md).

- Coffer looks for it at runtime in a vendor directory —
  `$COFFER_SEATALK_SDK_DIR` when set, otherwise `~/.coffer/vendor` — prepended to
  the import path only when that directory exists, following the same
  per-subsystem environment override convention the rest of the vault uses. The
  import is attempted lazily, at the moment a websocket channel starts, never at
  daemon import time, so an installation without the SDK starts exactly as it
  does today.
- When it cannot be imported, the websocket channel's connection MUST NOT come
  up and the channel MUST say precisely why: its websocket state is
  `sdk_missing`, with a detail naming the directory that was searched and the
  platform documentation that says what to put there. The connection keeps
  retrying on its back-off ladder, so dropping the SDK in needs no daemon
  restart. Nothing crashes, the daemon stays up, every other channel keeps
  running, the channel's outbound sends — replies and notifications, which
  never touch the SDK — are unaffected, and the reason is reported as that
  channel's own state rather than left in a log for someone to find.
- An installation without the SDK has **no SeaTalk inbound**. The websocket
  connection is the only inbound transport, so an outside user of this project
  who cannot obtain the SDK can register a SeaTalk channel and send to its
  paired owner, but the channel receives nothing and reports `sdk_missing` for
  as long as the SDK is absent. The SDK is still never vendored and never
  declared; Telegram, whose transport needs no vendor library, is unaffected.

#### Scenario: a websocket channel without the sdk says what is missing
- **GIVEN** a vendor directory that holds no SeaTalk client library
- **WHEN** an enabled websocket-delivery channel tries to connect
- **THEN** its websocket connection never comes up and its reported state is
  `sdk_missing`, naming the missing library and the directory searched for it
- **AND** the connection keeps retrying, so the library can be dropped in without
  a daemon restart
- **AND** the daemon stays up and every other channel keeps working

### Requirement: Carry both of a member's ids
A SeaTalk member has **two ids, and they are not interchangeable**, so the
transport MUST carry both rather than folding them into one field. The owner
gate ([channels](../spec.md) "Gate inbound traffic on sender identity") matches **`employee_code`**; a mention
([channels](../spec.md) "Mention the asker in a group answer") is addressed to **`seatalk_id`**, and `employee_code`
arrives empty for a sender outside the bot's organisation. SeaTalk also documents
a mention **by email**, which is a FALLBACK for a sender whose `seatalk_id` is
missing and never the primary. Group events carry only `group_id` and no chat
title, so the origin block ([channels](../spec.md) "Open every turn with its message origin") names a SeaTalk group by id
alone, which an agent resolves to a name through the platform's own tools.

#### Scenario: a sender with no id is mentioned by address instead
- **GIVEN** a group message from a member the transport named only by email, on a
  platform that documents an address-keyed mention,
- **WHEN** the turn replies,
- **THEN** the reply mentions them by address; when both are known, the id is used.

#### Scenario: a cross-organisation sender is still identified for a mention
- **GIVEN** a group @mention from a sender outside the bot's organisation, whose
  organisation-scoped identifiers arrive empty,
- **WHEN** the transport normalizes the message,
- **THEN** the platform id the mention needs is kept, not discarded with them.

### Requirement: Render replies as SeaTalk markdown
A reply MUST be converted from the agent's markdown to **SeaTalk's own markdown**
(`format: 1` — bold, italic, inline code, fences, ordered and unordered lists),
chunked to stay under the platform's **4096-byte** message cap in two steps:
the agent's markdown is first split into chunks of at most 3500 characters,
each chunk is then rendered and escaped, and a rendered chunk longer than 3900
UTF-8 bytes is split again at character boundaries until every piece fits, so
neither escaping nor multi-byte text can push a message past the cap.
Headings become bold and links become `label (url)`,
neither being supported there. A literal marker character is escaped with a
**SINGLE backslash** — two would be one escape too many, SeaTalk consuming the
first and rendering the second as literal text. A mention tag is lifted out of
the escaping pass and put back after it, the way inline code already is, because
a `seatalk_id` may contain an underscore and the email form of the tag contains
one routinely — an escaped tag reaches the reader as visible source instead of a
name.

#### Scenario: seatalk markdown escapes a literal marker character
- **GIVEN** a reply whose prose contains a SeaTalk formatting character that is
  not markup (e.g. an underscore inside `snake_case`)
- **WHEN** it is rendered for SeaTalk
- **THEN** that character is escaped with a SINGLE backslash so it survives as
  typed, while genuine bold/italic/code/list markup is left as SeaTalk markdown

#### Scenario: a mention target survives the markdown escaper unchanged
- **GIVEN** a mention whose target holds a character the platform's markdown
  escaper would otherwise escape (an id containing an underscore, or an email
  address),
- **WHEN** the reply is rendered for that platform,
- **THEN** the mention markup is delivered byte for byte, while the text around
  it is escaped as usual.

### Requirement: Stream the reply under SeaTalk's streaming contract
**The SeaTalk streaming constraints are contract, not implementation detail.**
SeaTalk cannot edit a delivered message at all, yet streams one, which is why
`supports_live_text` and `supports_edit` are separate flags
([channels](../spec.md) "Grow a reply in place on one live surface"); the streamed message IS the reply, so
`live_text_persists` MUST be true and the surface opens the moment the turn
starts, acknowledging the owner immediately.

- Every update carries the **FULL accumulated text**, never a delta: the client
  renders the latest snapshot it received.
- Updates must be **less than 30 s apart** or the platform terminates the
  stream, so the last snapshot is re-sent on a keep-alive well inside that
  window.
- One stream carries at most **4096 characters**; a reply that outgrows the
  budget finishes the stream at the limit and the remainder is sent as ordinary
  chunked messages. A reply's length is unknown until it ends, so refusing to
  stream anything that *might* overrun would withhold the live reply from every
  turn to serve the rare one.
- A stream that has **ended** — finished, timed out, or errored — is never
  reused, because the platform rejects any later request naming its id: the
  surface latches dead, no replacement stream is opened, and the ordinary send
  path delivers the reply in full. The partial message the platform kept stays
  where it is — visibly stale, but the user still gets the whole answer.
- The stream finishes carrying the final text rendered as SeaTalk markdown, so
  nothing is sent twice. Clients older than 3.67 simply see the finished message
  when the stream closes.

#### Scenario: each seatalk stream update carries the full reply so far
- **GIVEN** a SeaTalk channel streaming a reply
- **WHEN** the reply text arrives in deltas
- **THEN** the stream is opened once, every update carries the FULL accumulated
  text (never a delta) under a monotonically increasing sequence number, and
  only the last update finishes the stream

#### Scenario: a terminated seatalk stream is never reused
- **GIVEN** a SeaTalk stream the platform has terminated (an error, or a gap
  past its 30-second limit)
- **WHEN** the turn produces more text and then ends
- **THEN** no further request names that stream id, no replacement stream is
  opened, and the reply is delivered through the ordinary send path instead

#### Scenario: a reply past the stream budget finishes the stream and sends the rest
- **GIVEN** a SeaTalk reply longer than one stream may carry (4096 characters)
- **WHEN** the turn ends
- **THEN** the stream finishes at the budget on a paragraph boundary and the
  remainder is delivered as ordinary chunked messages

### Requirement: Keep a typing heartbeat alive in DMs and group threads
SeaTalk has **no reaction to ack with**, so it MUST additionally keep a periodic
**typing heartbeat** alive (an ephemeral action, zero chat clutter), covering the
window before the first live update lands. It runs wherever the turn is, DM or
group thread alike: SeaTalk has a thread-scoped group typing endpoint
(`group_chat_typing`) beside the direct-chat one, and the heartbeat was DM-only
purely on the belief that no such endpoint existed. The gate is the receipt
mechanism, not editing. Best-effort — a failed heartbeat never breaks the turn.

#### Scenario: a supports_typing-only DM keeps the typing indicator alive during a long turn
- **GIVEN** a paired channel on an adapter that can show typing but cannot edit,
  in a direct chat
- **WHEN** a long turn runs
- **THEN** the typing indicator is re-sent periodically for the turn's duration
  (an ephemeral action, no chat clutter), and is stopped when the turn ends

#### Scenario: a group turn is acknowledged by typing in the group
- **GIVEN** a paired group on an adapter that can type and has no reactions
- **WHEN** the owner @mentions the bot in a thread of that group
- **THEN** the typing indicator is sent to the group typing endpoint carrying
  that group's id and that thread's id — not to the direct-chat endpoint

### Requirement: Build cards in SeaTalk's published element shape
The card payload MUST follow SeaTalk's published shape: **one flat `elements`
array in which a button is itself an element**
(`{"element_type": "button", "button": {...}}`) — not a `buttons` array beside
it. The published per-element limits are a card of at most **3 titles, 5
descriptions, 5 buttons, 3 button groups and 3 images**, with a title of at most
120 characters and a description of at most 1000. Buttons are therefore laid out
in **button groups** (an element holding up to three buttons on one line) rather
than one element each: the parent's six-button bound ([channels](../spec.md) "Offer command choices as owner-gated selection cards")
always fits in the three group slots and reads as rows rather than a six-high
stack. A row splits the card's width evenly, so how many buttons share a row
depends on their labels: a row takes the next button only while every label in
it fits the width a row of that size leaves, and a long label gets a row of its
own. When that would need more than three rows, the buttons are spread evenly
over three. Title and description text are clamped to their documented lengths,
so a long body degrades to a truncated card instead of a refused one.

#### Scenario: a six-button card is laid out as two button groups with clamped text
- **GIVEN** a selection card with six short-labelled buttons, a title over 120 characters and a body over 1000 characters
- **WHEN** it is built as a SeaTalk interactive card
- **THEN** the payload is one flat `elements` array whose buttons sit in two button-group elements of three
- **AND** the title is truncated to 120 characters and the description to 1000

#### Scenario: a long button label gets a row of its own
- **GIVEN** a selection card whose buttons include a label too wide to share a row, such as "Claude Code" beside "Codex"
- **WHEN** it is built as a SeaTalk interactive card
- **THEN** that button sits alone in its button group, while short labels still share one

### Requirement: Degrade card rewrites outside SeaTalk's update window
A card rewrite ([channels](../spec.md) "Switch the conversation's agent from chat", [channels](../spec.md) "Offer command choices as owner-gated selection cards") reaches only
**interactive cards, only within 7 days, only for the sending bot**. Outside that
window the platform refuses the update, and the card MUST degrade exactly as the
parent requires: a cosmetic rewrite after a choice is dropped, while a page turn
the user asked for is posted as a fresh card, or as plain text if that is refused
too.

#### Scenario: a refused card update drops a choice rewrite but reposts a page turn
- **GIVEN** a SeaTalk card whose in-place update the platform refuses
- **WHEN** the owner applies a choice on it, and separately asks for its next page
- **THEN** the choice is applied with no replacement card posted
- **AND** the requested page arrives as a fresh card

### Requirement: Download every inbound SeaTalk media type
**Inbound media MUST cover all types, not just images.** The event handler
downloads files and documents, video, and voice/audio with the app token — each
becoming an `Attachment` — as it already does for images. A directly-sent PDF or
voice memo drives a turn like a photo does; only a message with nothing
text-or-downloadable still gets the "send text, a photo, or a file" reply.

#### Scenario: an inbound SeaTalk file drives a turn
- **GIVEN** a paired SeaTalk channel
- **WHEN** the owner sends a file directly (a `file` message whose
  `file.content` is an auth-gated file URL and `file.filename` the original name)
- **THEN** the bytes are downloaded with the app token and carried on the inbound
  message as an attachment keeping its real filename and a non-image mime, so the
  file drives a turn like a photo does instead of hitting the "send text, a
  photo, or a file" reply

### Requirement: Download the files a fetched thread carries
The thread fetch MUST download the images and files carried by the thread's
**own** messages with the app token, recursing forwarded records within them, and
attach them to the turn alongside the flattened text ([channels](../spec.md) "Download the media a thread's messages carry").
SeaTalk file links require auth, so a URL alone is useless to the agent.

#### Scenario: a file posted earlier in a seatalk thread is attached to the turn
- **GIVEN** a SeaTalk thread whose earlier messages include a file and a forwarded record holding an image
- **WHEN** the owner @mentions the bot inside that thread
- **THEN** both are downloaded with the app token and attached to the turn
- **AND** the flattened thread text is still folded into the turn

### Requirement: Download images nested in forwarded chat history
Images carried by SeaTalk messages — a directly-sent image, or any image nested
**recursively** inside a `combined_forwarded_chat_history` — MUST additionally be
downloaded with the app token and attached to the turn ([channels](../spec.md) "Flatten forwarded chat records into the turn"), so
a vision agent sees the actual picture and not just a link.

#### Scenario: an image nested two forwards deep is downloaded
- **GIVEN** a SeaTalk message whose forwarded chat history contains another forwarded record holding an image
- **WHEN** the transport handles the message
- **THEN** that image is downloaded with the app token and carried on the inbound message as an attachment
- **AND** the forwarded record is still flattened into the turn text

### Requirement: Upload outbound media into the originating chat and thread
`send_media` MUST be wired to SeaTalk's **send-message endpoints** — the ones
`send_text` uses — with the file's bytes carried base64-inline in the message,
and the adapter declares `supports_media` true, so an agent's `MEDIA:` sentinel
returns a file into the same chat **and thread** the turn came from
([channels](../spec.md) "Return outbound media into the originating thread"). An
image is delivered as an `image` message and anything else as a `file` message;
any caption follows as a threaded text message.

#### Scenario: SeaTalk outbound media is delivered into the originating thread
- **GIVEN** a paired SeaTalk channel and a group-thread turn whose reply
  contains a `MEDIA:/absolute/path` sentinel line for a file that exists
- **WHEN** the turn's reply is delivered
- **THEN** SeaTalk receives the file's bytes inline (an image as an `image`
  message, otherwise a `file` message) in that same group and thread — not the
  group main chat — because `supports_media` is true and `send_media` routes on
  the turn's chat_kind + thread_id; any caption follows as a threaded text
  message

### Requirement: Identify a thread by its root message
**A thread's id MUST be its root message's id.** An @mention inside a thread
already carries that id, so the bot reads that thread's messages for context and
replies into it. An @mention in the group **main chat** carries no thread id, so
the bot roots a fresh thread at that @mention — replying under the @mention's own
message id — and, since the thread then holds only the @mention itself, reads no
history.

#### Scenario: a main-chat mention roots a new thread at itself
- **GIVEN** a SeaTalk group @mention sent in the group main chat, carrying no thread id
- **WHEN** the transport normalizes it and the turn replies
- **THEN** the reply is sent into a thread whose id is the @mention's own message id
- **AND** no thread history is fetched for it

### Requirement: Fetch a DM thread from its own endpoint
A **DM thread** MUST be fetched from its own endpoint, keyed by employee code,
alongside the group one; the adapter routes on chat kind and everything above it
is unchanged ([channels](../spec.md) "Ground a DM thread's turn in the thread"). The group-chat **history** endpoint — recent
group-main messages, as opposed to one thread — is deliberately unused: the
corresponding SeaTalk permission is not granted to Coffer's app.

#### Scenario: a DM thread is read from the direct-chat thread endpoint
- **GIVEN** a SeaTalk direct-chat message inside a thread from the owner
- **WHEN** the adapter fetches the thread's context
- **THEN** it calls the direct-chat thread endpoint keyed by the owner's employee code
- **AND** it calls neither the group-thread endpoint nor the group-chat history endpoint

### Requirement: Resolve a quoted message with the bot's own token
Both SeaTalk inbound message events carry a **`quoted_message_id`** when the user
replied by quoting. The envelope MUST keep it, and the transport MUST resolve it
through `GET /messaging/v2/get_message_by_message_id` with the app's own token
([channels](../spec.md) "Ground a turn in the message it quotes"). SeaTalk gives
one message a different id per app, so only the app that received the event
can resolve this one. The response has a thread message's shape, so it is
flattened, and its images and files downloaded, the same way. Any error or
non-zero `code` resolves to nothing, and the turn runs on the message alone.

#### Scenario: a quoting seatalk message keeps the quoted id on the envelope
- **GIVEN** a SeaTalk direct message and a SeaTalk group message that each quote an earlier message
- **WHEN** the transport normalizes them
- **THEN** each envelope carries the event's `quoted_message_id`

#### Scenario: a quoted seatalk message is resolved by its id
- **GIVEN** a quoted message id this app received
- **WHEN** the transport resolves it
- **THEN** it calls `get_message_by_message_id` with that id and returns the
  message's sender and text
- **AND** a failed or refused lookup returns nothing rather than failing the turn

### Requirement: Normalise SeaTalk's two lifecycle events
Two SeaTalk events change what a binding *is* rather than driving a turn, and
MUST arrive on the lifecycle callback [channels](../spec.md) "Track the bot's own standing in a group" describes:
**`bot_removed_from_group_chat`** (kicked, or the group was disbanded) and
**`group_chat_converted_to_external_group`**. The first stops every live session
for that chat; the second is announced in the group itself, because people from
other organisations may now read a chat the owner paired.

#### Scenario: seatalk removal and external-conversion events become lifecycle events
- **GIVEN** a SeaTalk channel
- **WHEN** it receives a `bot_removed_from_group_chat` event and a `group_chat_converted_to_external_group` event
- **THEN** each is delivered on the lifecycle callback as a removal and an external conversion for that group
- **AND** neither is delivered as an inbound message

### Requirement: Read every page of a thread
A thread read MUST follow `next_cursor` until SeaTalk returns none. The thread
endpoints page oldest-first at no more than 100 messages a page, so reading one
page would drop the messages written just before the @mention. The read stops
after a fixed number of pages so a runaway cursor cannot stall the turn. A
later page that fails keeps the pages already read.

#### Scenario: a thread longer than one page is read to its last message
- **GIVEN** a SeaTalk thread whose first page carries a `next_cursor`
- **WHEN** the adapter fetches the thread
- **THEN** it requests the next page with that cursor and returns the messages
  of both pages in order

### Requirement: Receive every event over one outbound websocket connection
SeaTalk inbound MUST arrive over **one outbound websocket connection per
channel**: the daemon dials out, the register handshake authenticates the
connection once from `app_id` and `app_secret_ref`, and the platform pushes
events down the connection the daemon opened. It is the only inbound transport.
Coffer MUST expose nothing to the network for a SeaTalk channel — no public URL,
no listening port, no tunnel, no signature to verify — so the daemon's loopback
socket stays the only one the vault listens on. Every event MUST be ingested at
the channel's one ingest entry point, so deduplication, the owner gate, media
download and the turn itself are the same for every event. The platform permits
one delivery method per bot, so the bot's event delivery setting on SeaTalk's
Developer Portal is WebSocket; the portal's Re-verify passes only while the
connection is live, so the order is to enable the channel in Coffer first and
verify there second. The kick flag and its reason are written on the SDK's
listen thread and read by the supervisor on the event loop; the two MUST share
the connector's state lock, and a kick signalled from any thread is observed by
the supervisor even when `listen()` then returns without raising.

#### Scenario: a websocket channel receives an event with no public url
- **GIVEN** an enabled seatalk channel carrying only its app id and app secret
  reference among its SeaTalk fields
- **WHEN** the platform pushes a message event down the open connection
- **THEN** it is ingested through the channel's ingest entry point and drives a
  turn, with no signature to verify and nothing listening for a request

#### Scenario: the websocket connection backs off when another process takes it over
- **GIVEN** a connected websocket channel whose SeaTalk app is then registered
  from elsewhere, which kicks this connection — the app allows only one
- **WHEN** the connector observes the kick
- **THEN** it reports the kicked state and waits out a long fixed back-off before
  registering again, rather than fighting the other holder for the connection

### Requirement: Report the websocket connection as the channel's inbound state
**Status MUST report a SeaTalk channel's websocket connection as its inbound
state**, on every surface: the connection state — `connecting`, `connected`,
`kicked`, `sdk_missing` or `error`, or none before the first attempt — and the
last error behind it, verbatim, so the owner can act on it. Status MUST NOT
report a listener, a port, a path, a public URL or a tunnel, because none
exists, and there is no reachability probe: the connection state is the health
answer.

#### Scenario: status names the websocket connection state
- **GIVEN** an enabled seatalk channel whose websocket connection is up, and one
  whose last connection attempt failed
- **WHEN** the user queries status via REST and the CLI
- **THEN** each reports the connection state as the channel's inbound state, and
  the failed one carries its last error verbatim
- **AND** neither surface reports a listener, port, path, public URL or tunnel
  for either channel
