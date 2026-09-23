# Channels — Telegram

## Purpose
The Telegram half of Coffer's channel plane. Its parent,
[`channels`](../spec.md), owns everything a channel does regardless of platform
— pairing, the owner gate, commands, conversations, media policy, scope and
machine binding. This spec owns what only Telegram's Bot API can answer: how
events arrive, how a reply is rendered and grown in place, what a card is made
of, and which of the Bot API's newer surfaces Coffer reaches for when the server
it talks to offers them.

Telegram is the channel every user can set up alone: a user with nothing but
BotFather can register a bot, pair their own account and get an agent reply,
with no public URL, tunnel, vendor SDK or organisation approval anywhere in the
path, which is why it is the channel that proves the parent's contract end to
end. The Bot API is spoken with `httpx` against the fixed host
`api.telegram.org`; there is no SDK dependency, because the surface used is a
handful of methods and an SDK would buy nothing while adding an
import-confinement contract.

The Bot API carries a family of surfaces built for exactly this shape of bot: a
message that streams while an agent generates it, a stop control the platform
draws itself, structured rich text, and a group reply only one member can see.
Coffer uses each one where the Bot API server it reaches offers it, and keeps its
own hand-built equivalent — an edited message standing in for a stream, a typed
`/stop`, an HTML subset standing in for markdown — as the fallback beneath it,
because the Bot API server a user reaches is not guaranteed to be new enough.
Every capability here is therefore two mechanisms and a probe, not one mechanism
([channels](../spec.md) "Probe platform capabilities and latch off rejected ones"); a Coffer running against an older Bot API server degrades
in formatting and liveness only, and every reply is still delivered.

One disclosed Bot API parsing caveat is accepted and documented at its call
site rather than specified away: only `entities` on a plain text message is
parsed for a mention, so an @mention inside a media caption is not recognized.

## Requirements

### Requirement: Configure a Telegram channel by a bot token reference
A Telegram channel's configuration MUST be a **bot token reference** and nothing
else beyond the fields every channel carries ([channels](../spec.md) "Register channels as a credential-referencing resource kind"). The token
itself lives in the credential store; the reference is probed at registration.

#### Scenario: register a telegram channel whose token reference resolves
- **GIVEN** a bot token stored in the credential store under a reference
- **WHEN** a telegram channel is registered with that reference and no other type-specific field
- **THEN** the channel is stored carrying the reference, not the token itself
- **AND** a telegram registration naming a reference with no stored credential is rejected

### Requirement: Receive updates by long polling
Telegram inbound MUST use **long polling**, with the update offset committed only
after dispatch, so no inbound message is double-processed across a reconnect.
The adapter reconnects with exponential backoff and never crashes the daemon.

#### Scenario: the polling offset advances only past dispatched updates
- **GIVEN** a running telegram adapter polling a Bot API that returns a batch of updates
- **WHEN** the updates are dispatched and the next poll is made
- **THEN** the next `getUpdates` asks for the offset after the last dispatched update
- **AND** a failed poll is retried after a back-off without stopping the adapter

### Requirement: Read the bot's identity from getMe and latch off unsupported surfaces
On start the transport MUST read the bot's own identity from `getMe` and keep the
two fields that change what it may do: the bot's username, and whether privacy
mode leaves it able to read group messages. The Bot API surfaces introduced
later than some servers carry — **rich messages, message drafts, ephemeral
messages** — are attempted once and latched off for the process on the
platform's own rejection, per [channels](../spec.md) "Probe platform capabilities and latch off rejected ones".

#### Scenario: getMe identity is kept and a rejected newer surface is latched off
- **GIVEN** a Bot API whose `getMe` names the bot and reports that it cannot read all group messages
- **WHEN** the transport starts and a newer Bot API surface is then refused as unsupported
- **THEN** the transport keeps the bot's username and its privacy-mode state
- **AND** that surface is not attempted again for the life of the process, while an ordinary refusal leaves it available

### Requirement: Report privacy mode that defeats the group configuration
Telegram bots run with **privacy mode ON by default**, which withholds ordinary
group messages from the bot entirely. A channel configured to act on un-addressed
group messages (`require_mention = false`, [channels](../spec.md) "Configure when the bot answers in a group") but whose bot
cannot read them MUST be reported on the channel's health surface
([channels](../spec.md) "Diagnose configuration a platform setting defeats") naming the fix: disable privacy mode in BotFather, then
re-add the bot to the group.

#### Scenario: privacy mode is reported when it contradicts the configuration
- **GIVEN** a channel configured to act on unaddressed group messages,
- **WHEN** its bot cannot read group messages,
- **THEN** the channel's health reports the contradiction and names the fix.

### Requirement: Use from.id as the gate identity
`from.id` MUST be the sender identity Telegram supplies, and it is the id the
owner gate matches ([channels](../spec.md) "Gate inbound traffic on sender identity"). Telegram spells a mention with a
display name as well as an id, so a Telegram group reply carries no @mention and
degrades as [channels](../spec.md) "Mention the asker in a group answer" allows. `chat.title` is
handed over for free, so the origin block ([channels](../spec.md) "Open every turn with its message origin") names the chat
by title as well as by id.

#### Scenario: a telegram group message carries from.id and the chat title
- **GIVEN** a telegram group message whose `from.id` and `chat.title` are set
- **WHEN** the transport normalizes it
- **THEN** the envelope's sender id is that `from.id` and it carries no mention id
- **AND** the envelope carries the chat title for the origin block

### Requirement: Subscribe to the bot's own membership changes
Telegram reports the bot's departure from a group as a change to the bot's
**own membership** (`my_chat_member`) rather than as a dedicated event, and the
platform withholds that update unless it is named in the subscribed update
types. The transport MUST subscribe to it and normalise it onto the same
lifecycle envelope every platform's removal arrives on ([channels](../spec.md) "Track the bot's own standing in a group").

#### Scenario: the bot leaving a group arrives as a removal event
- **GIVEN** a telegram adapter whose polling subscription names `my_chat_member`
- **WHEN** an update reports the bot's own status in a group changed to left or kicked
- **THEN** it is normalized into a removal lifecycle event for that chat
- **AND** a membership update about another user, or one where the bot is still a member, produces no event

### Requirement: Render replies as Telegram HTML chunked at 4000 characters
A reply MUST be converted from the agent's markdown to **Telegram HTML**, with a
plain-text retry when the platform rejects the formatted message, and chunked at
**4000 characters** on paragraph boundaries.

#### Scenario: a reply is sent as telegram HTML and retried as plain text when refused
- **GIVEN** a telegram channel and an agent reply longer than 4000 characters containing markdown emphasis
- **WHEN** the reply is delivered
- **THEN** it is sent as HTML-formatted messages of at most 4000 characters, split on paragraph boundaries
- **AND** a chunk whose HTML the platform rejects is re-sent as plain text

### Requirement: Send rich messages where the Bot API offers them
Where the Bot API server offers **rich messages**, a reply that carries
headings, lists, tables or fenced code MUST be sent as one rather than being
flattened into the HTML subset — which demotes a heading to bold, a bullet to a
glyph, and passes a table through as raw pipes. The HTML renderer of "Render
replies as Telegram HTML chunked at 4000 characters" stays as the fallback that
[channels](../spec.md) "Probe platform capabilities and latch off rejected ones" selects.

#### Scenario: a structured reply is sent as a telegram rich message
- **GIVEN** a Bot API server that accepts rich messages
- **WHEN** a reply containing a heading and a table is delivered
- **THEN** it is sent as a rich message carrying the markdown structure
- **AND** on a server that refuses rich messages the same reply is delivered as HTML

### Requirement: Use a deleted status message as the live scaffolding
Telegram's live surface MUST be **scaffolding**, not the reply: a status message
that is edited as the turn runs and **deleted** before the real answer is sent.
It therefore declares `live_text_persists` false, and opens only once the turn
has run past the update interval — either tool activity opens it or the reply
text does — so a reply that finishes sooner opens none and there is no create →
delete → resend flicker; the 👀 receipt reaction ([channels](../spec.md) "Acknowledge receipt and completion by capability") has
already said the message was heard. When the turn ends, the status message is
deleted and the final reply is sent HTML-rendered and paragraph-chunked.

#### Scenario: reply text streams into the editable status message as it arrives
- **GIVEN** a paired channel on an adapter that can edit messages
- **WHEN** the agent's reply text arrives in deltas during a turn
- **THEN** the single status message shows tool-progress lines first, then is
  edited in place with the accumulating reply text (plain, not HTML) so the user
  watches the answer materialize; on finish the status message is deleted and the
  final reply is sent once (HTML-rendered and paragraph-chunked)

#### Scenario: a slow text-only reply streams into a status message
- **GIVEN** a paired channel on an adapter that can edit messages
- **WHEN** a text-only turn (no tool calls) keeps producing reply text past the
  transport's update interval
- **THEN** a status message is opened with the streaming reply text and edited in
  place as the answer grows, then deleted on finish while the final reply is sent
  once

#### Scenario: a fast text-only reply opens no status message
- **GIVEN** a paired channel on an adapter that can edit messages
- **WHEN** a text-only turn completes within the transport's update interval
- **THEN** no status message is opened (no create → delete → resend flicker) — only
  the single final reply is sent

### Requirement: Stream through a message draft in direct chats only
Where the Bot API offers a **message draft**, the live-text handle
([channels](../spec.md) "Stream through the platform's own surface where the chat has one") MUST drive that instead of rewriting a delivered message. A
draft addresses a **private chat and has no group form**, so it is used only in
DMs; a group keeps the status-message mechanism of "Use a deleted status message
as the live scaffolding" rather than spending a refused call per snapshot.

#### Scenario: a direct-chat turn streams into a message draft while a group turn edits a status message
- **GIVEN** a Bot API server that offers message drafts
- **WHEN** a turn's reply streams in a direct chat and another in a group
- **THEN** the direct-chat progress is sent as message-draft updates with no status message to delete
- **AND** the group progress uses an edited status message and makes no draft call

### Requirement: Route the draft's stop button to the interrupt path
A streamed draft MAY advertise the **stop button the platform draws**. When the
user presses it the platform reports the stopped draft, and Coffer MUST route
that to the same interrupt path as `/stop` ([channels](../spec.md) "Stop the turn from the platform's own stop control"). The button is
advertised only where that route is wired.

#### Scenario: pressing the draft's stop button interrupts the turn
- **GIVEN** a direct-chat turn streaming into a draft that advertises the platform's stop button
- **WHEN** the platform reports that the user stopped that draft
- **THEN** the turn is interrupted through the same path as a typed `/stop`

### Requirement: Deliver group command output as ephemeral messages
Where the Bot API offers **ephemeral messages** — a message only one member's
client shows — command output and errors MUST be delivered that way in a group,
per [channels](../spec.md) "Keep non-answer chatter private in a group". Their edit address space is different from an ordinary
message's: Telegram edits an ordinary card by `chat_id` + `message_id` and an
ephemeral one by `chat_id` + `receiver_user_id` + `ephemeral_message_id`, and
documents that edit as not guaranteed to reach the user. That is why a selection
card stays an ordinary message.

#### Scenario: a group command answer is sent as an ephemeral message to the asker
- **GIVEN** a telegram group on a Bot API server that offers ephemeral messages
- **WHEN** the owner's `/status` answer is delivered in that group
- **THEN** it is sent as an ephemeral message addressed to the owner's user id
- **AND** a selection card in the same group is sent as an ordinary message

### Requirement: Render selection cards as inline keyboards
A selection card ([channels](../spec.md) "Offer command choices as owner-gated selection cards") MUST be rendered as an **inline
keyboard**, and a tap arrives as a callback query carrying the button's opaque
value. Telegram has no title element of its own, so the card's title MUST be
carried in the text: as a **heading** of the rich message when the Bot API
server offers rich messages, and as a **bold first line** on the HTML path
beneath it. Every callback value Coffer emits fits the **64-byte callback
budget** the Bot API allows; a choice whose value would not fit is left off the
card.

#### Scenario: a selection card becomes an inline keyboard with a bold title line
- **GIVEN** a selection card with a title and several choices
- **WHEN** it is rendered for telegram on the HTML path
- **THEN** the message opens with the title as a bold first line and carries an inline keyboard of the choices
- **AND** every button's callback data is at most 64 bytes

#### Scenario: a selection card on a rich-message server takes its title as a heading
- **GIVEN** a Bot API server that offers rich messages
- **WHEN** a selection card with a title is sent
- **THEN** it is sent as one rich message whose markdown opens with the title as a heading
- **AND** it carries the inline keyboard of the choices

### Requirement: Download every Telegram media type without leaking the token
Every type Telegram can attach to a message — **photos, documents, voice, audio,
video, animations, stickers, round video notes** — MUST be downloaded and become
an `Attachment` ([channels](../spec.md) "Hand inbound photos and files to the agent", [channels](../spec.md) "Drive a turn from every inbound media type or say why not"). A file over the cap
the Bot API places on what a bot may download MUST produce a message telling the
user. A download that fails after `getFile` succeeded — the platform answers the
file endpoint with an error status, or the connection fails — is noted in the
turn text as `[attachment '<name>' could not be downloaded]` and the turn still
runs on whatever text and other attachments arrived. **The Telegram file URL
embeds the bot token**, so this path MUST log only the failure's class, or the
method and HTTP status — never the request URL, and never a traceback that
quotes it; no log record produced by any download path contains the bot token.

#### Scenario: a failed telegram download never puts the bot token in the log
- **GIVEN** a Telegram message with a photo whose file download fails after
  `getFile` succeeds,
- **WHEN** the adapter handles the message,
- **THEN** the turn runs with a note that the attachment could not be
  downloaded, and no log record contains the bot token

### Requirement: Debounce an album into one turn
Messages sharing a `media_group_id` are an **album**, delivered as separate
updates with the caption on the first item only. They MUST be debounced into a
single inbound message carrying all their attachments and the album's caption —
one turn, not one per photo — while a lone photo without a `media_group_id` still
drives its turn immediately.

#### Scenario: a Telegram album is handled as one turn
- **GIVEN** a paired Telegram channel
- **WHEN** the owner sends a multi-photo album (delivered as separate messages
  that share a `media_group_id`, the caption on the first item only)
- **THEN** the items are debounced and combined into a single inbound message
  carrying all their attachments and the album's caption — one turn, not one per
  photo — while a lone photo without a `media_group_id` still drives its turn
  immediately

### Requirement: Answer on the mention and reply into the forum topic
The Bot API **cannot fetch chat history at all**, so on Telegram no thread
context is read: the bot MUST answer on the @mention message itself. It still
replies into the **forum topic** the message arrived in, so [channels](../spec.md) "Reply in place inside threads"'s
reply-in-place rule holds even though its read-the-thread half cannot.

#### Scenario: a mention in a forum topic is answered in that topic without reading history
- **GIVEN** a telegram supergroup message that @mentions the bot inside a forum topic
- **WHEN** the turn replies
- **THEN** the reply is sent with that topic's `message_thread_id`
- **AND** no call is made to read the topic's earlier messages
