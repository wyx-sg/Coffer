## Context

The plan and its research are in the proposal for the user
(`coffer-rearchitecture/channel-experience-proposal.md`, outside the repo). The
user delegated the open questions; this records what was decided and why.

## Decisions

### The renderer is split along its seams

`turn_render.py` was at the 400-line cap. It is now four modules, each owning
one question: `turn_status` (what the status block says — pure), `turn_surface`
(the one live handle, the mention on snapshots, the typing heartbeat),
`turn_finish` (media, notices, the delivered body, the summary and the ping), and
`turn_render` (the event loop that feeds them). `reply_shape` and `needs_you`
are pure text passes beside them.

### Status block, then the answer, split by a rule

A live snapshot is `status block` + `\n─\n` + `answer tail`. The rule is the one
contract between core and transport: a transport that must shorten a snapshot
(SeaTalk's byte budget, Telegram's draft cap) clips the answer and keeps the
block, and Telegram's rich draft moves the header into `<tg-thinking>`. The
separator is `turn_status.LIVE_SEPARATOR`; nothing else about the block is
parsed downstream.

### The clock ticks from the renderer, at the keep-alive cadence

The surfaces' keep-alive re-sends the last snapshot, which would freeze the
elapsed time. The renderer instead redraws the status every 10 s — the same
cadence as every surface's keep-alive — so a changed snapshot goes out where
the unchanged one would have; the tick also opens a scaffolding surface for a
turn still thinking in silence.

### Narration is kept in the final reply

Text a tool call closes becomes the status line's `💬` line while the turn runs.
The final reply keeps every segment, a paragraph break between each (the
proposal's question 5, answered "keep"): hiding it would make the chat reply
differ from the conversation the web shows.

### Mention on snapshots only where the surface persists

A mention rides on every snapshot of a surface that becomes the reply (SeaTalk:
the platform decides @ notifications at creation). A scaffolding surface
(Telegram's status message) is deleted, so its snapshots stay plain and the
answer — a new message — carries the mention.

### Telegram's mention needs a name

`mention_template` may now carry `{name}` as well as `{user_id}`. Telegram's is
`[{name}](tg://user?id={user_id})` — a rich-markdown inline mention that works
for users without a username; the HTML fallback renders the same link. A name
is escaped of `[`, `]`; an id must be digits.

### Reactions are a transport fact

`ChannelCapabilities.reactions` is a `ReactionSet` (received, working, done,
failed, stopped). Telegram declares 👀 👨‍💻 👌 😢 🤷, each checked against the
73 emoji `ReactionTypeEmoji` lists (Bot API 10.3, read 2026-09-30);
`telegram_reactions` refuses anything else before the round trip. A turn that
ends waiting for the owner counts as done. The tool-iteration limit counts as
failed.

### Who needs a completion ping

A ping is due when the turn ran at least `notify_after_seconds` and its answer
was delivered by closing a surface that **persists** — the answer then lives in
a message created when the turn began, so finishing it notifies nobody. That is
SeaTalk's stream; Telegram's answer is always a new message and needs none. On
an abnormal long turn the ping replaces the separate summary (one message, same
facts). The default is 90 s; 0 turns it off.

### `## Details` becomes a collapsed block — `<details>`, not an expandable quote

The user asked for an expandable blockquote. Telegram's
`RichBlockExpandableBlockQuotation` holds inline text only, so a details section
with a list, a table or a code block would not fit. The rich path therefore uses
`<details><summary>Details</summary>…</details>` (`RichBlockDetails`, which holds
blocks), and the HTML fallback path — where no `<details>` exists — uses
`<blockquote expandable>`. Both collapse by default.

### SeaTalk: tables and long code become files, decided by capability

`ChannelCapabilities.renders_tables` (false on SeaTalk: tables fail in cards and
were never verified in text) and `max_inline_code_lines` (30 on SeaTalk) drive a
pure `shape_reply` pass in the core; the files it produces are written to a
temporary directory and uploaded through the ordinary `send_media` path.

### Continuation numbering is the transport's

Only the transport knows where a reply is cut (SeaTalk: stream budget, then
3500-character chunks; Telegram: 32k rich or 4000 plain), so each transport
numbers its own pieces `(2/3)`. SeaTalk's stream now sends its own remainder,
so its numbering counts the stream as part 1.

### `NEEDS YOU:` is a sentinel beside `MEDIA:`

The agent ends with `NEEDS YOU: <question> (a / b)`. The core strips it from
the body and sends `❓ <question>` as its own message with up to four option
buttons (Yes / No when none are given, none when more than four). A button's
value is `reply:<option>` clipped to Telegram's 64-byte callback budget. A tap
is owner-gated like any card tap and then enters the conversation as the
owner's own message, through the ordinary inbound path — so the agent's
confirmation rule ("the yes comes from the user in this conversation") holds.
The card is rewritten to show the answer, so a second tap cannot resend it.

### SeaTalk's details card stores the details as a file

A card cannot carry a long answer, and a callback value is short. The details
are written to a file under the temp directory, keyed by a random id; the
card's buttons carry `details:<id>` and `detailsfile:<id>`. A tap posts them as
a thread reply (a SeaTalk thread's id is its root message's id) or uploads the
file. A missing file answers that the details are no longer available. No table
and no migration are needed; the next free migration number stays 0109.

### Telegram rich draft

`sendRichMessageDraft` (Bot API 10.1) streams a rich message to a **private**
chat and admits `<tg-thinking>` in drafts only; there is no group form. A direct
chat's draft therefore sends `<tg-thinking>` + the header, the steps, and the
answer as rich markdown; a refusal latches `rich_drafts` off and the draft falls
back to `sendMessageDraft` plain text. Groups keep the silent status message.

## Risks

- Whether a SeaTalk client notifies on the ping (a new message: yes), and how a
  mention tag renders in a card description, cannot be checked without a live
  account; the ping is plain text and carries the mention, the card does not.
- Whether Telegram counts `editMessageText` toward the group limit is
  undocumented; the status message keeps its 1.5 s floor and now ticks at most
  every 10 s.
