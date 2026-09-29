## ADDED Requirements

### Requirement: Show a turn's working state as one status line
While a turn runs, its live surface MUST open with one status block the reader
can take in at a glance: a header saying that the turn is working, for how long,
and how many steps it has taken (`⏳ Working · 2m 14s · 7 steps`, with the
failed count when there is one); the agent's latest narration as a `💬` line;
and the newest three step lines, older ones collapsed into `+N earlier`. The
answer written so far follows under a rule. The header MUST keep ticking while
nothing else happens — a long silent tool still shows time passing — on the
cadence the live surfaces already keep alive at, so the tick costs no extra
traffic.

Text the agent writes before a tool call is narration ("Let me check the
logs"): once the tool call arrives it moves up into the `💬` line and the answer
tail shows only text written after the last tool call. The final reply keeps
every segment the agent wrote, with a paragraph break between the text either
side of a tool call, so two sentences never run together.

A channel setting `show_steps` (default on) hides the step lines and keeps the
header and narration — useful in a busy group. It is edited on the Channels
page and with `coffer channel add|edit --show-steps/--hide-steps`.

A transport that must shorten a snapshot to its own limit clips the answer's
oldest words and keeps the status block whole; only a limit too small for the
block drops the step lines, then the header.

#### Scenario: a long turn shows elapsed time and step count in one status line
- **GIVEN** a turn that has run for 2 minutes 14 seconds and called eight tools,
  one of which failed
- **WHEN** its status block is drawn
- **THEN** the header reads `⏳ Working · 2m 14s · 8 steps (1 failed)`, followed by
  `+5 earlier` and the newest three step lines

#### Scenario: narration between tool calls moves to the status line
- **GIVEN** a turn whose agent writes a sentence and then calls a tool
- **WHEN** the tool call arrives and the agent then writes its answer
- **THEN** the sentence appears as the status block's `💬` line and the answer
  alone grows under the rule

#### Scenario: the status line keeps ticking during a silent tool
- **GIVEN** a turn whose tool runs for minutes without producing an event
- **WHEN** the live surface is next redrawn on its cadence
- **THEN** the header shows the new elapsed time

#### Scenario: the final reply keeps every paragraph the agent wrote
- **GIVEN** a turn whose agent wrote text, called a tool, then wrote more text
- **WHEN** the reply is delivered
- **THEN** it holds both texts with a paragraph break between them

#### Scenario: hiding steps keeps only the header
- **GIVEN** a channel with `show_steps` off
- **WHEN** a turn calls a tool
- **THEN** the status block shows the header and narration but no step line

#### Scenario: the step lines are hidden from the command line
- **WHEN** the owner runs `coffer channel edit <name> --hide-steps`, then `--show-steps`
- **THEN** the channel's `show_steps` setting is off, then on again

### Requirement: Ping the asker when a long turn ends
A turn that ran at least the channel's `notify_after_seconds` (default 90, from
0 to 3600; 0 turns it off) MUST end with one short new message wherever its
answer would not notify on its own — that is, where the answer was delivered by
finishing a live surface that persists from the turn's start (see "Grow a reply
in place on one live surface"): a message created minutes ago notifies nobody
when it is finished. The ping reads `✅ Done · 4m 12s — <first line of the
answer>`, the first line read as plain words and clipped to 120 characters; a
turn that failed, was stopped or hit the tool-iteration limit pings `⚠️ Failed ·
…`, `⏹ Stopped · …` or `⚠️ Tool limit · …` with the tool count and tokens, and
that ping takes the place of its separate summary. It is sent the way the turn's
other replies are — into the same chat and thread — and in a group it opens with
the asker's @mention (see "Mention the asker in a group answer"). A turn whose
answer went out as a new message (a scaffolding surface, or a stream that died
and fell back to the ordinary send) needs no ping: that message already
notified. A turn shorter than the threshold sends none either — the answer
itself is the signal.

Presence is not observable on any platform, so duration is the only signal. The
setting is edited on the Channels page and with `coffer channel add|edit
--notify-after <seconds>`.

#### Scenario: a long turn whose answer does not notify ends with a ping
- **GIVEN** a transport whose streamed answer persists from the turn's start, and
  a turn that ran 4 minutes 12 seconds against the default threshold
- **WHEN** the turn ends cleanly
- **THEN** after the streamed answer one new message reads `✅ Done · 4m 12s —`
  followed by the answer's first line in plain words

#### Scenario: a short turn or a zero threshold sends no ping
- **GIVEN** a turn shorter than the threshold, and a long turn on a channel whose
  threshold is 0
- **WHEN** each ends
- **THEN** neither sends a ping

#### Scenario: an answer sent as a new message needs no ping
- **GIVEN** a transport whose live surface is scaffolding deleted before the answer
- **WHEN** a long turn ends
- **THEN** no ping is sent — the answer's own new message notified

#### Scenario: a long failed turn pings instead of summarising
- **GIVEN** a long turn on a persisting surface that errors after one tool
- **WHEN** it ends
- **THEN** exactly one message follows the answer: `⚠️ Failed · <elapsed> · 1 tool
  — <error>`

#### Scenario: the ping threshold comes from the channel's settings
- **WHEN** a channel config omits `notify_after_seconds`, sets it to 0, or sets it
  past 3600
- **THEN** it is 90, it is 0 (off), and it is refused

#### Scenario: the ping threshold is edited from the command line
- **WHEN** the owner runs `coffer channel edit <name> --notify-after 0`
- **THEN** the channel's threshold is 0, and a value past 3600 is refused

### Requirement: Shape a reply for what the chat can show
A finished reply MUST pass one structure pass before the platform renderer,
driven by the transport's declared capabilities, never its type:

- A transport that does not render tables (`renders_tables` false) receives each
  table as one bullet per row, `- **checkout** · failed · 3DS timeout`; a table
  of more than 12 rows or 4 columns keeps its first five rows as bullets and
  goes out whole as an attached `.csv`.
- A transport with `max_inline_code_lines` set receives a longer fenced block as
  its first three lines plus a note, and the whole block as an attached file
  (`.log`, `.diff`, `.txt` by the fence's language).
- The files follow the answer, through the transport's ordinary file upload,
  under their own names. A transport that cannot send files keeps everything in
  the body instead.
- A `## Details` section — where the agent is asked to put long content — is the
  transport's to present: one that collapses it does so (see each child spec).
- A reply cut into several messages is never cut inside a fenced code block (a
  fence longer than one message is closed and reopened, its language kept), and
  every message after the first opens with its place, `(2/3)`, so a busy group
  can follow it.

#### Scenario: a table becomes bullet rows where the chat cannot show tables
- **GIVEN** a transport that does not render tables
- **WHEN** a reply holds a three-column table of two rows
- **THEN** it is delivered as two bullet rows, the first cell of each in bold, and
  no file is attached

#### Scenario: a long log is attached as a file
- **GIVEN** a transport that keeps at most 30 lines of code inline
- **WHEN** a reply holds a 40-line `log` block
- **THEN** the reply keeps its first three lines and names `log-1.log`, which holds
  all 40 lines

#### Scenario: a table's CSV and a long log follow the answer as files
- **GIVEN** a transport that renders no tables and keeps 30 lines of code inline
- **WHEN** a reply holds a 20-row table and a 50-line log
- **THEN** the answer is delivered first, then `table-1.csv` and `log-2.log` are
  uploaded as documents

#### Scenario: a code block is never split across messages
- **GIVEN** a reply longer than one message whose fenced block holds a blank line
- **WHEN** it is cut into messages
- **THEN** no message holds half a fence, and an oversized fence is closed and
  reopened with its language

## RENAMED Requirements

- FROM: `### Requirement: Summarise only a turn that did not end normally`
- TO: `### Requirement: Summarise a turn that did not end normally`

## MODIFIED Requirements

### Requirement: Grow a reply in place on one live surface
A reply MUST grow in place, by whatever live-text mechanism the platform has —
chosen from the adapter's declared capabilities, never its type — so the answer
never arrives as a run of fragments. The capability the core asks about is
`supports_live_text` ("is there a surface I can keep updating while this turn
runs?"), NOT `supports_edit` ("can a delivered message be rewritten?"). The two
flags are set independently, because a transport can have a live surface while
being unable to rewrite a delivered message at all; keying the strategy on
`supports_edit` silently denied such a transport the live experience it does
support, and its replies arrived as several chunked messages at the end of the
turn.

A turn keeps exactly ONE live surface. WHEN it opens depends on whether that
surface becomes the reply or is scaffolding thrown away at the end, which the
adapter declares as `live_text_persists`. Where it persists, the surface opens
the moment the turn starts and says so — its status line (see "Show a turn's
working state as one status line") is an acknowledgement the user can see,
because the wait between a message and an answer is otherwise the whole of what
they get, and on a long turn it reads as the bot having missed them. That
acknowledgement costs no extra message: the reply is the same one, rewritten in
place. Where the surface is scaffolding, it opens only once the turn has run
past the update interval — either tool activity opens it or the reply text does
— so a reply that finishes sooner opens none, avoiding a create → delete →
resend flicker. A turn still thinking in silence opens it on the status line's
first tick.

The cadence of updates belongs to the TRANSPORT, which alone knows its own
limits: the core offers every snapshot and each surface buffers to what it can
sustain. A throttle added by the core on top hides that buffer completely and
makes a stream arrive a paragraph at a time. Interim snapshots are clipped to
the platform's per-message limit and their formatting characters are ESCAPED, so
a long or half-written-markdown preview never breaks a platform parser or
exceeds the cap. They are escaped rather than sent as plain text because the
message has to be able to carry an @mention from the moment it is created (see
"Mention the asker in a group answer"), and a mention is only a name in rich
text.

How a surface *ends* is the transport's business, and each child spec states its
own. A transport with no live surface at all posts no interim traffic; its final
reply is the whole signal. All best-effort — a failed update, close, or
heartbeat never breaks the turn.

#### Scenario: the streamed reply preview is clipped to the platform limit
- **GIVEN** a paired channel on an adapter that can edit messages
- **WHEN** the accumulating reply text grows past the platform's per-message limit
- **THEN** each interim edit is clipped to that limit (keeping the most recent
  text behind a leading ellipsis) so the edit never fails, while the final reply
  carries the full text

#### Scenario: a transport with no live-text surface posts no interim status message
- **GIVEN** a paired channel on an adapter that can neither edit nor stream and
  declares no typing signal either, in a group/thread
- **WHEN** a turn runs
- **THEN** no interim signal is posted at all — only the final chunked reply
  lands in the originating group/thread

#### Scenario: a reply grows in place on a transport that streams but cannot edit
- **GIVEN** a paired channel on an adapter that cannot edit or delete a message
  but can stream one, in a group/thread
- **WHEN** a turn runs tools and then writes its reply
- **THEN** exactly ONE message reaches the chat and grows in place — tool
  progress first, then the accumulating reply — and it finishes carrying the
  final reply, so nothing is sent twice and the answer never arrives as
  fragments

### Requirement: Acknowledge receipt and completion by capability
Receipt and progress MUST be acknowledged, capability-gated (never by transport
type). On a `supports_reactions` transport the owner's own message carries one
reaction that follows the turn: a **received** mark the moment it arrives (a
message queued behind a running turn keeps it), a **working** mark when its turn
starts, and one of **done** (a clean finish, including one that ends on a
question for the owner), **failed** (an error or the tool-iteration limit) or
**stopped** (interrupted) when it ends. Which emoji each stage uses is the
transport's declared `reactions` set, because a platform may accept only a fixed
list — each child spec names its own. A reaction replaces the previous one, so
the message shows where the turn is now. A transport without reactions uses its
typing/working signal as the receipt-and-progress cue instead. All best-effort —
a failed mark never breaks the turn.

#### Scenario: receipt and completion are acked with reactions where supported
- **GIVEN** a paired channel on an adapter that supports reactions
- **WHEN** the owner sends a message that drives a clean turn
- **THEN** the received mark is set on the owner's own message immediately on
  receipt, the working mark when the turn starts, and the done mark on
  completion, all targeting that inbound message id

#### Scenario: a transport without reaction support attempts no reaction
- **GIVEN** a paired channel on an adapter that does not support reactions,
  whose receipt-and-progress cue is the typing signal
- **WHEN** the owner sends a message that drives a turn
- **THEN** no reaction is attempted, while the turn still runs and replies normally

#### Scenario: a failed reaction never breaks the turn
- **GIVEN** a paired channel on a reaction-supporting adapter whose set_reaction fails
- **WHEN** the owner sends a message that drives a turn
- **THEN** the reply is still delivered — the best-effort reaction is suppressed

#### Scenario: a failed turn ends on the failed mark
- **GIVEN** a paired channel on an adapter that supports reactions
- **WHEN** the owner's message drives a turn that errors
- **THEN** the message's marks are received, working, then failed — never done

#### Scenario: a turn's marks follow it from receipt to its end
- **GIVEN** a paired channel on an adapter that supports reactions
- **WHEN** the owner's message drives a turn that is interrupted
- **THEN** the message's marks are received, working, then stopped

### Requirement: Summarise a turn that did not end normally
After a turn that did not end normally the channel MUST send one compact
completion summary as a fresh message: a failure reports the error, an
interrupt reports the stop, and the tool-iteration limit reports the limit, each
with tool count, duration, and token usage. A turn error is reported to the IM
chat as a short notice and the channel stays up. Where a long turn pings (see
"Ping the asker when a long turn ends"), the ping carries these facts and takes
the summary's place. A clean success MUST send **no** summary — the reply itself
is the completion signal, so the fact line would only be noise (this holds
regardless of whether the transport can edit messages); the one line a clean
*long* turn may end with is its ping.

#### Scenario: a turn error is reported to the IM chat
- **GIVEN** a scripted agent that fails mid-turn
- **WHEN** the peer sends a message
- **THEN** the IM chat receives a short error notice and the channel stays up

#### Scenario: a turn that does not end normally sends a completion summary
- **GIVEN** a paired channel
- **WHEN** a turn fails, is interrupted, or hits the tool-iteration limit
- **THEN** a compact completion summary is sent to the chat reporting the outcome
  (the error / stop / limit) with tool count, duration, and tokens

#### Scenario: a clean success sends no completion summary
- **GIVEN** a paired channel (whether or not the transport can edit messages)
- **WHEN** a turn shorter than the ping threshold completes successfully
- **THEN** no completion summary is sent — the reply itself is the end-of-turn
  signal

### Requirement: Mention the asker in a group answer
A group answer MUST name who it is for, and notify them. In a group, the bot's
reply MUST open by @mentioning the member whose message drove the turn, using the
platform's own mention markup — so the answer notifies the person waiting for it
and a busy room can see at a glance which of them it belongs to. In a direct chat
it MUST NOT: a 1:1 conversation has nobody to disambiguate, and an @ there is
only shouting. Four constraints bound it.

- **The mention MUST be in the content the reply is CREATED with**, not added to
  it later. A platform decides @ notifications at creation; a mention that
  arrives on a later update of the same message renders as a name and notifies
  nobody, which is the worst of both — the room sees an @ the mentioned person
  never got. For a streamed reply that means the opening post carries it, and
  therefore so does every snapshot in between: a mention that appeared at
  creation, vanished for the length of the stream and returned at the end would
  be a visible glitch.
- Because every snapshot then carries markup, every snapshot MUST be sent in the
  platform's rich format. The protection that the plain format used to give a
  reply clipped mid-word — an unclosed emphasis run the client would render as
  noise — MUST instead come from ESCAPING the agent's partial text, leaving the
  mention markup itself untouched.
- The mention is built from the id the PLATFORM addresses a member by, which is
  not always the id the owner gate matches — so the transport carries both.
  Where the platform documents a second way to address a member, it is a
  FALLBACK for a sender whose id is missing, never the primary: the id is the
  identifier that is always present.
- A platform whose mention is a link that shows a name (Telegram) spells it
  with the asker's display name as well as the id; the name is stripped of
  anything that could end the link text.
- It degrades silently: no id and no usable fallback, or a transport that cannot
  mention at all, yields an ordinary unmentioned reply — never a broken tag.
- Only a surface that persists as the reply carries the mention while it grows;
  scaffolding that is deleted before the answer carries none, and the answer —
  a new message — opens with it.

#### Scenario: a group reply @mentions whoever asked
- **GIVEN** an addressed message in a group from a member the transport named,
- **WHEN** the turn replies,
- **THEN** the reply opens with the platform's mention markup for that member.

#### Scenario: a direct reply carries no mention
- **GIVEN** the same channel answering in a 1:1 chat,
- **WHEN** the turn replies,
- **THEN** the reply carries no mention — there is nobody to disambiguate.

#### Scenario: a streamed group reply is created already mentioning the asker
- **GIVEN** a group turn that opens a live surface before it has anything to say,
- **WHEN** the first snapshot is posted and the reply then grows in place,
- **THEN** the mention markup is in the content the message is created with, and
  in every snapshot after it, exactly once.

#### Scenario: an @ notification needs the mention in the message that creates it
- **GIVEN** the transport that creates its reply as a stream and grows it,
- **WHEN** the reply is delivered,
- **THEN** the mention travels in the creating call, because the platform decides
  @ notifications then and not on any later update of the same message.

#### Scenario: an interim snapshot reaches the chat as written, not as markup
- **GIVEN** an in-flight snapshot of a reply, clipped mid-word so it can end
  inside an unclosed emphasis run,
- **WHEN** it is sent in the platform's rich format, as carrying a mention
  requires,
- **THEN** its formatting characters are escaped — one escape each — so the
  reader sees the text the agent has written so far.

### Requirement: Tell a channel-driven agent it is on a chat channel
A channel-originated turn MUST tell the agent it is bridged to a chat channel,
not a terminal. The agent receives a short system-prompt note naming **where**
it is — the platform, the chat kind (direct chat, group chat, group thread) and
the channel by its current label — and **what renders there**, in the sentence
or two the running transport declares as its `render_notes` (SeaTalk: bold,
italic, inline code, code fences and lists, but no headings, links or tables;
Telegram: its rich Markdown, tables included). It then asks for a reply shaped
for a phone: do not narrate steps (Coffer already shows the working state); the
first line is the outcome in one sentence, because it becomes the notification;
at most about 15 lines, anything longer under a `## Details` heading; code blocks
under 30 lines, longer logs attached as files; diagrams and charts as PNG files,
never as source; and, when the agent needs a yes or a choice before it goes on,
a final `NEEDS YOU:` line (see "Turn a question for the owner into buttons").
Concise never drops evidence — an investigation's key log lines, error messages
and IDs are quoted verbatim — and the agent is told it cannot click permission
or confirmation dialogs on the user's computer. Web-UI turns are unaffected —
the note rides only on a conversation whose `channel_uid` is set. A channel that
has been deleted, or is not running, still gets the note, saying less.

#### Scenario: the channel-driven agent is told it is on a chat channel
- **GIVEN** a channel-originated conversation
- **WHEN** a turn is driven from the channel
- **THEN** the agent receives a system-prompt note naming the platform, the chat
  kind and the channel, telling it not to narrate its steps, to quote an
  investigation's key evidence verbatim, and that it cannot click the user's OS
  dialogs, while a web-UI conversation gets no such note

#### Scenario: the note lists what renders on the platform the turn is on
- **GIVEN** a SeaTalk group-thread conversation on a running channel
- **WHEN** its turn's note is composed
- **THEN** it says the turn is in a SeaTalk group thread and that headings, links
  and tables do not render there (write one bullet per row)

#### Scenario: the note asks for the answer's shape
- **WHEN** a channel turn's note is composed
- **THEN** it asks for the outcome in one first sentence, long content under
  `## Details`, diagrams as PNG files, and a final `NEEDS YOU:` line with at most
  four options when the agent needs the owner's answer
