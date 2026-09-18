# Feature Specification: Channels — SeaTalk

**Status**: Accepted
**Input**: The SeaTalk half of Coffer's channel plane. Its parent,
[`channels`](../spec.md), owns everything a channel does regardless of
platform — pairing, the owner gate, commands, conversations, media policy,
scope and machine binding. This spec owns what only SeaTalk can answer: two
inbound transports and the configuration that chooses between them, the
streaming reply contract, the card payload shape, thread identity, and the two
ids a member has.

Requirements here are numbered from FR-001 and are this spec's own. A bare
`FR-00N` below means this spec; the parent's are cited as `channels FR-00N`.

**SeaTalk is Coffer-hosted for every agent**, because no external gateway speaks
SeaTalk at all: there is no official Claude, Codex, Cursor or agent-native
integration for it. Everything a user does with an agent on SeaTalk goes through
this adapter or does not happen.

## User Scenarios & Testing

### User Story 1 — SeaTalk reaches the local daemon (Priority: P1)

SeaTalk delivers events two ways, and a channel picks one of them.

**Webhook.** The platform POSTs each event to a public URL, so Coffer ships a
callback listener: a separate small process that serves only signed callback
paths on a local port. Something has to carry the public internet to that
loopback port — a tunnel the owner runs by hand (cloudflared, ngrok), or one
Coffer supervises itself from a Cloudflare connector token recorded on the
channel — and the resulting public URL is registered on the SeaTalk Open
Platform. The listener answers the platform's verification handshake, verifies
every event's signature, and forwards valid events to the daemon over loopback.
Events with a bad signature are rejected and never reach the daemon.

**WebSocket.** The daemon instead holds one outbound connection to SeaTalk and
the platform pushes events down it. There is no public URL, no listener, no
tunnel, and no signature to check: the connection authenticates itself once with
the app's own credentials, and everything after that arrives on a socket only
this machine opened. For a local-first vault that is the better transport — it
deletes the entire ingress apparatus instead of managing it — and its price is
paid elsewhere: the platform's own client library, which the operator supplies
(FR-007), and one connection per SeaTalk app, so a second machine registering
the same app takes the events away from the first.

Both land on the same seam. An event is the same envelope whichever way it
arrives, ingested at the same entry point, so deduplication, the owner gate,
media download, and the turn itself are identical. The transport is a property of
the channel, not a second path through the product.

**Why this priority**: Without ingress there is no SeaTalk inbound at all.
The separate-process shape is a constitutional requirement for
public-reachable surfaces — which is also why the transport that exposes nothing
needs no process of its own.

**Independent Test**: On webhook, start the listener with a known signing secret,
POST the verification challenge and see it echoed; POST a signed event and see it
forwarded; POST a tampered event and see 401 with nothing forwarded. On
websocket, point a channel at a stand-in client library, push an event down the
connection and watch the same turn start with no listener running and no public
URL configured; take the library away and watch the channel refuse to start with
a message naming what is missing and where it was looked for.

**Covering scenarios**:

- the callback listener answers the verification handshake
- a signed seatalk event reaches the channel
- a tampered seatalk event is rejected
- an oversized callback body is refused before it is read
- the listener runs only while a seatalk channel is enabled
- a websocket channel receives an event with no public url
- a websocket channel runs without the listener or a tunnel
- the websocket connection backs off when another process takes it over
- a websocket channel without the sdk says what is missing
- status reports webhook-only facts as absent rather than as defaults

---

### User Story 2 — A reply that arrives as it is written (Priority: P2)

SeaTalk cannot edit a delivered message at all, but it can **stream** one. The
streamed message IS the reply, so it opens the moment the turn starts —
acknowledging the owner immediately — and grows in place until it carries the
finished answer. A periodic typing heartbeat covers the window before the first
snapshot lands, in a DM or a group thread alike.

**Covering scenarios**:

- each seatalk stream update carries the full reply so far
- a terminated seatalk stream is never reused
- a reply past the stream budget finishes the stream and sends the rest
- seatalk markdown escapes a literal marker character
- a supports_typing-only DM keeps the typing indicator alive during a long turn
- a group turn is acknowledged by typing in the group

---

### User Story 3 — Answer the right person, in the right thread, with their files (Priority: P2)

A SeaTalk group is threads, and a member has two ids: the one the owner gate
matches and the one a mention is addressed to. An answer opens by @mentioning
whoever asked, lands in the thread the question came from, and carries back
whatever file the agent produced — while every file the question carried has
already been downloaded with the app token, because SeaTalk's file links are
auth-gated and a bare URL is useless to an agent.

**Covering scenarios**:

- an inbound SeaTalk file drives a turn
- SeaTalk outbound media is delivered into the originating thread
- a mention target survives the markdown escaper unchanged
- a sender with no id is mentioned by address instead
- a cross-organisation sender is still identified for a mention

## Requirements

### Configuration

- **FR-001**: A SeaTalk channel's configuration carries **`app_id` and
  `app_secret_ref`**, required on both transports, plus whichever fields its
  chosen inbound transport requires (FR-002–FR-004). The secret lives in the
  credential store; the configuration carries the reference, probed at
  registration (`channels FR-001`).
- **FR-002**: A SeaTalk channel declares which inbound transport it uses, and
  that choice decides which of its fields may exist at all. A **`delivery`**
  field carries `webhook` or `websocket`; absent means `webhook`. **The platform
  permits only one delivery method per bot at a time**, so the two are exclusive
  rather than additive: Coffer implements both and each channel chooses, never
  one bot running both. The choice therefore lives in two places that must move
  together — `delivery` here and the bot's event delivery setting on SeaTalk's
  Developer Portal — and switching it **clears the fields the other method
  owns**. That is honest rather than lossy: the switch is never free anyway,
  since the platform-side setting has to change in step, and the portal's
  Re-verify on the websocket side only passes while the connection is actually
  live.
- **FR-003**: A **webhook** channel MUST carry a `signing_secret_ref`, because a
  signature is the only thing between the public internet and the daemon. It MAY
  carry a `public_base_url`, so status can report the URL the platform was
  given, and a `tunnel_token_ref`, which makes the daemon run and keep alive the
  `cloudflared` child that terminates the channel's public URL instead of
  leaving that to the owner.
- **FR-004**: A **websocket** channel reverses the direction: the daemon dials
  out and the platform pushes events down the connection it opened, which the
  register handshake authenticates once from `app_id` and `app_secret_ref`. Such
  a channel MUST NOT carry a `signing_secret_ref`, a `public_base_url`, or a
  `tunnel_token_ref` — there is no request body to sign, no public URL to
  describe, and no tunnel to supervise, and a configuration field that decides
  nothing is a lie about the system. A deployment whose only SeaTalk channels use
  websocket delivery MUST leave the callback listener stopped and spawn no
  tunnel: the point of the transport is that nothing is exposed, and a listener
  nobody can reach is still a port nobody asked for. The kick flag and its reason
  are written on the SDK's listen thread and read by the supervisor on the event
  loop; the two MUST share the connector's state lock, and a kick signalled from
  any thread is observed by the supervisor even when `listen()` then returns
  without raising.
- **FR-005**: **Status MUST stay truthful per transport.** A websocket channel
  reports its connection state and the last error behind it, and reports the
  webhook-only facts (port, path, public URL, listener, tunnel) as **absent**
  rather than as reassuring defaults; the public-URL reachability test stays
  webhook-only and refuses a websocket channel, because there is no URL for it
  to probe.

### Transport

- **FR-006**: The SeaTalk callback listener serves exactly one protocol, and
  this spec owns that protocol: `POST /seatalk/{channel_uid}` answers
  `event_verification` with the echoed challenge, verifies
  `sha256(body + signing_secret)` signatures, forwards valid events to the
  daemon over loopback with the daemon token, and rejects everything else. It
  MUST refuse any request body larger than **1 MiB** with HTTP 413 before it is
  read: a declared `Content-Length` over the limit is rejected without reading a
  byte, and a body without one is read only until its running size passes the
  limit. A SeaTalk event envelope is a few kilobytes; the cap exists because the
  listener sits behind a public tunnel and MUST NOT buffer an arbitrary upload
  in memory before discovering it is unsigned. Which channels demand a listener
  at all is this spec's answer — a channel on **webhook** delivery does, a
  channel on **websocket** delivery MUST NOT bring one up — while the process
  itself, its supervision and its packaging belong to spec `daemon`.
- **FR-007**: The WebSocket client library is an **operator-supplied optional
  dependency**, never a vendored one. The only client for SeaTalk's websocket
  delivery is the platform's own SDK, distributed from an internal corporate
  portal, absent from public PyPI, and published under no public licence — so
  Coffer, which is MIT, MUST NOT vendor it into this repository and MUST NOT
  declare it as a dependency. Reimplementing its wire protocol is not an
  alternative either: none is published. See
  [SeaTalk Inbound Over WebSocket](../../../docs/decisions/seatalk-websocket-inbound.md).
  - Coffer looks for it at runtime in a vendor directory — `$COFFER_SEATALK_SDK_DIR`
    when set, otherwise `~/.coffer/vendor` — prepended to the import path only
    when that directory exists, following the same per-subsystem environment
    override convention the rest of the vault uses. The import is attempted
    lazily, at the moment a websocket channel starts, never at daemon import
    time, so an installation without the SDK starts exactly as it does today.
  - When it cannot be imported, the websocket channel MUST NOT start and MUST say
    precisely why: the directory that was searched and the platform documentation
    that says what to put there. Nothing crashes, the daemon stays up, every
    webhook channel keeps running, and the reason is reported as that channel's
    own state rather than left in a log for someone to find.
  - An installation that never obtains the SDK is fully functional on webhook
    delivery. That is deliberate, because it is what an outside user of this
    project has: websocket delivery is a capability the operator can add, not a
    floor the product is built on.

### Identity

- **FR-008**: A SeaTalk member has **two ids, and they are not interchangeable**.
  The owner gate (`channels FR-011`) matches **`employee_code`**; a mention
  (`channels FR-055`) is addressed to **`seatalk_id`**, and `employee_code`
  arrives empty for a sender outside the bot's organisation, so the transport
  carries both rather than folding them into one field. SeaTalk also documents a
  mention **by email**, which is a FALLBACK for a sender whose `seatalk_id` is
  missing and never the primary. Group events carry only `group_id` and no chat
  title, so the origin block (`channels FR-035`) names a SeaTalk group by id
  alone, which an agent resolves to a name through the platform's own tools.

### Rendering

- **FR-009**: A reply is converted from the agent's markdown to **SeaTalk's own
  markdown** (`format: 1` — bold, italic, inline code, fences, ordered and
  unordered lists), chunked at **4096 bytes**. Headings become bold and links
  become `label (url)`, neither being supported there. A literal marker character
  is escaped with a **SINGLE backslash** — two would be one escape too many,
  SeaTalk consuming the first and rendering the second as literal text. A mention
  tag is lifted out of the escaping pass and put back after it, the way inline
  code already is, because a `seatalk_id` may contain an underscore and the email
  form of the tag contains one routinely — an escaped tag reaches the reader as
  visible source instead of a name.

### Liveness

- **FR-010**: **The SeaTalk streaming constraints are contract, not
  implementation detail.** SeaTalk cannot edit a delivered message at all, yet
  streams one, which is why `supports_live_text` and `supports_edit` are separate
  flags (`channels FR-039`); the streamed message IS the reply, so
  `live_text_persists` is true and the surface opens the moment the turn starts.
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
    nothing is sent twice. Clients older than 3.67 simply see the finished
    message when the stream closes.
- **FR-011**: SeaTalk has **no reaction to ack with**, so it additionally keeps a
  periodic **typing heartbeat** alive (an ephemeral action, zero chat clutter),
  covering the window before the first live update lands. It runs wherever the
  turn is, DM or group thread alike: SeaTalk has a thread-scoped group typing
  endpoint (`group_chat_typing`) beside the direct-chat one, and the heartbeat
  was DM-only purely on the belief that no such endpoint existed. The gate is the
  receipt mechanism, not editing. Best-effort — a failed heartbeat never breaks
  the turn.

### Cards

- **FR-012**: The card payload MUST follow SeaTalk's published shape: **one flat
  `elements` array in which a button is itself an element**
  (`{"element_type": "button", "button": {...}}`) — not a `buttons` array beside
  it. The published per-element limits are a card of at most **3 titles, 5
  descriptions, 5 buttons, 3 button groups and 3 images**, with a title of at
  most 120 characters and a description of at most 1000. Buttons are therefore
  laid out in **button groups** (an element holding up to three buttons on one
  line) rather than one element each: the parent's six-button bound
  (`channels FR-015`) occupies two of the three group slots, is legal by the
  published rules, and reads as two rows rather than a six-high stack. Title and
  description text are clamped to their documented lengths, so a long body
  degrades to a truncated card instead of a refused one.
- **FR-013**: A card rewrite (`channels FR-010`, `channels FR-015`) reaches only
  **interactive cards, only within 7 days, only for the sending bot**. Outside
  that window the platform refuses the update, and the card degrades exactly as
  the parent requires: a cosmetic rewrite after a choice is dropped, while a page
  turn the user asked for is posted as a fresh card, or as plain text if that is
  refused too.

### Media

- **FR-014**: **Inbound media covers all types, not just images.** The event
  handler downloads files and documents, video, and voice/audio with the app
  token — each becoming an `Attachment` — as it already does for images. A
  directly-sent PDF or voice memo drives a turn like a photo does; only a message
  with nothing text-or-downloadable still gets the "send text, a photo, or a
  file" reply.
- **FR-015**: The thread fetch downloads the images and files carried by the
  thread's **own** messages with the app token, recursing forwarded records
  within them, and attaches them to the turn alongside the flattened text
  (`channels FR-030`). SeaTalk file links require auth, so a URL alone is useless
  to the agent.
- **FR-016**: Images carried by SeaTalk messages — a directly-sent image, or any
  image nested **recursively** inside a `combined_forwarded_chat_history` — are
  additionally downloaded with the app token and attached to the turn
  (`channels FR-023`), so a vision agent sees the actual picture and not just a
  link.
- **FR-017**: `send_media` is wired to SeaTalk's **file-upload API** and the
  adapter declares `supports_media` true, so an agent's `MEDIA:` sentinel returns
  a file into the same chat **and thread** the turn came from
  (`channels FR-032`). An image is delivered as an `image` message and anything
  else as a `file` message; any caption follows as a threaded text message.

### Threads

- **FR-018**: **A thread's id is its root message's id.** An @mention inside a
  thread already carries that id, so the bot reads that thread's messages for
  context and replies into it. An @mention in the group **main chat** carries no
  thread id, so the bot roots a fresh thread at that @mention — replying under
  the @mention's own message id — and, since the thread then holds only the
  @mention itself, reads no history.
- **FR-019**: A **DM thread** is fetched from its own endpoint, keyed by employee
  code, alongside the group one; the adapter routes on chat kind and everything
  above it is unchanged (`channels FR-042`). The group-chat **history** endpoint —
  recent group-main messages, as opposed to one thread — is deliberately unused:
  the corresponding SeaTalk permission is not granted to Coffer's app.
- **FR-020**: Both SeaTalk inbound message events carry a **`quoted_message_id`**
  when the user replied by quoting. The envelope keeps it and the origin block
  names it (`channels FR-041`); fetching the quoted body is a single documented
  call the platform's own MCP server already exposes as a tool, so it is a lookup
  the agent performs for itself. The id is scoped to this bot — the platform
  deliberately gives one message different ids to different apps — so it is a
  handle, not a durable identifier.

### Lifecycle

- **FR-021**: Two SeaTalk events change what a binding *is* rather than driving a
  turn, and arrive on the lifecycle callback `channels FR-043` describes:
  **`bot_removed_from_group_chat`** (kicked, or the group was disbanded) and
  **`group_chat_converted_to_external_group`**. The first stops every live
  session for that chat; the second is announced in the group itself, because
  people from other organisations may now read a chat the owner paired.

## Success Criteria

- **SC-001**: A channel on websocket delivery runs with no listener process, no
  tunnel child, and no public URL anywhere in the path, and its status says so
  rather than reporting those facts as zeros.
- **SC-002**: An event drives an identical turn whichever transport delivered it
  — no requirement outside this spec's configuration section distinguishes the
  two.
- **SC-003**: An installation that never obtains the SeaTalk SDK is fully
  functional on webhook delivery, and a websocket channel without it reports
  what is missing instead of crashing anything.
- **SC-004**: Every acceptance scenario below is covered by at least one test.

## Acceptance Scenarios

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

### Scenario: an oversized callback body is refused before it is read

- **Given** a running callback listener,
- **When** a request declares, or streams, a body larger than 1 MiB,
- **Then** the listener responds 413 without buffering the body, and nothing
  reaches the daemon

### Scenario: the listener runs only while a seatalk channel is enabled

- **Given** a daemon with one enabled seatalk channel
- **When** the channel is disabled
- **Then** the listener process stops; enabling it again restarts the listener

### Scenario: a websocket channel receives an event with no public url

- **Given** an enabled seatalk channel on websocket delivery, carrying no signing
  secret, no public base URL and no tunnel token
- **When** the platform pushes a message event down the open connection
- **Then** it is ingested through the same entry point a webhook event takes and
  drives a turn, with no signature to verify and nothing listening for a request

### Scenario: a websocket channel runs without the listener or a tunnel

- **Given** a daemon whose only enabled seatalk channel uses websocket delivery
- **When** the runtime reconciles what should be running
- **Then** the callback listener stays stopped and no tunnel child is spawned
- **And** adding a webhook-delivery channel starts the listener as before

### Scenario: the websocket connection backs off when another process takes it over

- **Given** a connected websocket channel whose SeaTalk app is then registered
  from elsewhere, which kicks this connection — the app allows only one
- **When** the connector observes the kick
- **Then** it reports the kicked state and waits out a long fixed back-off before
  registering again, rather than fighting the other holder for the connection

### Scenario: a websocket channel without the sdk says what is missing

- **Given** a vendor directory that holds no SeaTalk client library
- **When** an enabled websocket-delivery channel tries to connect
- **Then** the channel does not start and its reported state names the missing
  library and the directory searched for it
- **And** the daemon stays up and every webhook channel keeps working

### Scenario: status reports webhook-only facts as absent rather than as defaults

- **Given** a channel delivering over a websocket, which has no callback
  listener and no tunnel to have
- **When** the user queries status on every surface
- **Then** the websocket state is named and the listener port, path and tunnel
  are omitted rather than rendered from their absent values, so a healthy
  channel is never described as broken ingress

### Scenario: a supports_typing-only DM keeps the typing indicator alive during a long turn

- **Given** a paired channel on an adapter that can show typing but cannot edit,
  in a direct chat
- **When** a long turn runs
- **Then** the typing indicator is re-sent periodically for the turn's duration
  (an ephemeral action, no chat clutter), and is stopped when the turn ends

### Scenario: a group turn is acknowledged by typing in the group

- **Given** a paired group on an adapter that can type and has no reactions
- **When** the owner @mentions the bot in a thread of that group
- **Then** the typing indicator is sent to the group typing endpoint carrying
  that group's id and that thread's id — not to the direct-chat endpoint

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

### Scenario: an inbound SeaTalk file drives a turn

- **Given** a paired SeaTalk channel
- **When** the owner sends a file directly (a `file` message whose
  `file.content` is an auth-gated file URL and `file.filename` the original name)
- **Then** the bytes are downloaded with the app token and carried on the inbound
  message as an attachment keeping its real filename and a non-image mime, so the
  file drives a turn like a photo does instead of hitting the "send text, a
  photo, or a file" reply

### Scenario: SeaTalk outbound media is delivered into the originating thread

- **Given** a paired SeaTalk channel and a group-thread turn whose reply
  contains a `MEDIA:/absolute/path` sentinel line for a file that exists
- **When** the turn's reply is delivered
- **Then** SeaTalk uploads the file (an image as an `image` message, otherwise a
  `file` message) into that same group and thread — not the group main chat —
  because `supports_media` is true and `send_media` routes on the turn's
  chat_kind + thread_id; any caption follows as a threaded text message

## Deliberately out of scope

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

**Reading recent group-main history.** SeaTalk delivers neither emoji reactions
nor non-@ group-main messages to a bot, and the permission that would grant the
history endpoint is not granted to a self-built app at Coffer's scope. It is not
merely unimplemented; it is unbuildable here, which is why `channels FR-024`
states the rule as a deliberate choice rather than a gap.

## Assumptions

- The user can create a SeaTalk Open Platform app, enable the Bot capability and
  set it Online, and obtain the scopes their organization's approval flow
  requires (at minimum *Send Message to Bot User*).
- A channel on **webhook** delivery terminates its events at a loopback callback
  listener that the public internet must nonetheless reach, so something has to
  bridge the two: either a tunnel the owner runs by hand (cloudflared, ngrok, or
  equivalent) or one Coffer supervises itself — recording a Cloudflare connector
  token on the channel makes the daemon spawn and keep alive a `cloudflared`
  child for it. On **websocket** delivery none of that exists; what the owner
  supplies there instead is the platform's own client library (FR-007).
- Outbound SeaTalk is spoken with `httpx` against the fixed host
  `openapi.seatalk.io`; the official SDK is used only for websocket inbound,
  where there is no alternative.
- One open question the platform's own documentation does not settle: the
  streaming parameter table marks `thread_id` optional while the group-chat
  request sample is annotated "thread_id required", so whether a group-**main**
  stream is accepted without one is unverified.
