## RENAMED Requirements

- FROM: `### Requirement: Show a turn's working state as one status line`
- TO: `### Requirement: Show a turn's working state as one status line (before smooth replies)`

- FROM: `### Requirement: Mention the asker in a group answer`
- TO: `### Requirement: Mention the asker in a group answer (before smooth replies)`

- FROM: `### Requirement: Ask the owner in the chat and take the chat's answer back to the agent`
- TO: `### Requirement: Ask the owner in the chat and take the chat's answer back to the agent (before smooth replies)`

## MODIFIED Requirements

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
- A `## Details` section is the transport's to present: one that collapses it
  does so (see each child spec); on any other it goes out as ordinary text in
  the reply, cut into messages like the rest — never behind a card or a button.
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

#### Scenario: a details section goes out whole where the chat cannot collapse it
- **GIVEN** a transport that does not collapse a details section
- **WHEN** a reply `Deploy is green on live.` ends with a two-line `## Details`
  section
- **THEN** one text message carries the head and the details, and no card or
  button is sent

### Requirement: Tell a channel-driven agent it is on a chat channel
A channel-originated turn MUST tell the agent it is bridged to a chat channel,
not a terminal. The agent receives a short system-prompt note naming **where**
it is — the platform, the chat kind (direct chat, group chat, group thread) and
the channel by its current label — and **what renders there**, in the sentence
or two the running transport declares as its `render_notes` (SeaTalk: bold,
italic, inline code, code fences and lists, but no headings, links or tables;
Telegram: its rich Markdown, tables included). It then asks for a reply shaped
for a phone: do not narrate steps (Coffer already shows that it is working), and
only what it writes after its last tool call is sent, so the whole answer goes
there; the first line is the outcome in one sentence, because it becomes the
notification; at most about 15 lines — and, only where the transport collapses
one (`collapses_details`, Telegram), anything longer under a `## Details`
heading; code blocks
under 30 lines, longer logs attached as files; diagrams and charts as PNG files,
never as source; and, when the agent needs a yes or a choice before it goes on,
to call `coffer__ask` (see "Ask the owner in the chat and take the chat's answer back to the agent").
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
- **THEN** it asks for the outcome in one first sentence, says only the text
  after the last tool call is sent, and asks for diagrams as PNG files and a
  `coffer__ask` call when the agent needs the owner's answer

#### Scenario: only a transport that collapses details is asked for a details section
- **GIVEN** a Telegram direct chat and a SeaTalk group thread
- **WHEN** each turn's note is composed
- **THEN** the Telegram note asks for long content under a `## Details` heading
  Coffer collapses, and the SeaTalk note does not mention one

### Requirement: Summarise a turn that did not end normally
After a turn that did not end normally the chat is told how it ended in one
line, and nothing more: a failure says what happened and ends "Send it again to
retry." (never an error code), an interrupt ends "⏹ Stopped after 12s." — the
turn's real duration, and the tool count when tools ran. After a `/stop` that
line names what was stopped — "⏹ Stopped “<title>” after 12s · 3 tools." — and,
when messages were queued behind the turn, says they are on hold until the next
message; where the platform can edit a message it replaces the "⏹ Stopping
“<title>”…" the `/stop` sent instead of following it, and `/stop` with no turn
in flight answers "Nothing is running.". A turn error
is reported to the IM chat as a short notice and the channel stays up. A clean
success MUST send **no** closing line — the reply itself is the completion
signal, a new message that notifies however long the turn ran, so a fact line
would only be noise (this holds regardless of whether the transport can edit
messages).

#### Scenario: a turn error is reported to the IM chat
- **GIVEN** a scripted agent that fails mid-turn
- **WHEN** the peer sends a message
- **THEN** the IM chat receives a short notice that says what happened and ends "Send it again to retry." — no error code — and the channel stays up

#### Scenario: a turn that does not end normally sends a completion summary
- **GIVEN** a paired channel
- **WHEN** a turn fails or is interrupted
- **THEN** the chat is told the outcome in one line — what failed with "Send it
  again to retry.", or "⏹ Stopped after <duration>." — and no separate fact
  summary follows

#### Scenario: a clean success sends no completion summary
- **GIVEN** a paired channel (whether or not the transport can edit messages)
- **WHEN** a turn completes successfully
- **THEN** no completion summary is sent — the reply itself is the end-of-turn
  signal

### Requirement: Withdraw a bot reply on the owner's command
A reply in a group cannot be unsaid by the platform on its own, and the agent can
read everything the owner keeps in Coffer, so the owner MUST be able to take any bot
reply back. Two owner-only ways do it, and both end the same way. The command
`/del` withdraws the reply it QUOTES (the platform's reply pointer or quote), the
whole reply — every part a long answer was cut into and the files it carried — and `/del` with no quote withdraws the bot's most recent reply in
that chat (in a thread, in that thread; in a group's main chat, anywhere in the
group). It works in groups and in direct chats. And every bot reply in a group
carries a 🗑 button on its last text message, where the transport has buttons and
can withdraw at all.

Both are owner-only: `/del` passes the same owner gate as every command, and a tap on
🗑 by anyone else does nothing and says nothing. What "withdraw" does is the
transport's own fact, declared as capabilities: Telegram deletes the messages
(`withdraw_removes`), SeaTalk — which has no delete — rewrites each card into a
neutral "🗑 Withdrawn" card without buttons. Each platform has a window after which
it refuses (`withdraw_window_hours`: 48 for Telegram, 168 for SeaTalk); a reply past
it is not touched and the owner is told so in their direct chat, never in the group.
The owner's own `/del` message is deleted too where the platform lets the bot remove
it (Telegram, given the right), and left alone otherwise. A direct-chat reply a
transport cannot take back (SeaTalk's direct-chat text, which it can neither
delete nor rewrite) is not recorded, and `/del` says there is nothing to
withdraw.

To make that reliable the channel records, for every reply, which platform messages
it was delivered as — in `runs.db` (`channel_replies`: chat, thread, reply id, the
message ids, the time sent; never the text), so a daemon restart inside the window
loses nothing — and forgets a reply once it is older than the longest window. Each
withdrawal is audited as `channel_reply_withdrawn` with the actor (the owner), the
channel and how many messages went, and no content.

#### Scenario: /del with a quote withdraws that whole reply
- **GIVEN** a paired group where the bot answered the owner in a reply sent as several messages
- **WHEN** the owner sends `/del` quoting one of those messages
- **THEN** every message of that reply is withdrawn through the adapter
- **AND** the reply is no longer on record

#### Scenario: /del without a quote withdraws the latest reply
- **GIVEN** a paired chat where the bot has answered twice
- **WHEN** the owner sends `/del` quoting nothing
- **THEN** only the more recent reply is withdrawn and the earlier one stays

#### Scenario: a long reply is withdrawn in every part
- **GIVEN** a reply cut into several messages and followed by an uploaded file
- **WHEN** the owner withdraws it
- **THEN** each text part, and a file on a transport that can delete one, is withdrawn

#### Scenario: nobody but the owner can withdraw a reply
- **GIVEN** a paired group with a bot reply on record
- **WHEN** someone who is not the owner sends `/del` or taps the reply's 🗑
- **THEN** nothing is withdrawn and nothing is said in the group

#### Scenario: a group reply carries a trash button the owner can tap
- **GIVEN** a paired group on a button-capable transport that can withdraw
- **WHEN** the bot answers and the owner taps 🗑 under the reply
- **THEN** the last message of the reply carries that button, and the tap withdraws the whole reply

#### Scenario: a direct chat reply carries no trash button
- **GIVEN** a paired direct chat
- **WHEN** the bot answers
- **THEN** the reply has no 🗑 button, and `/del` still withdraws it

#### Scenario: a reply past the platform window is reported privately
- **GIVEN** a reply on record that was sent longer ago than the transport's withdraw window
- **WHEN** the owner sends `/del` quoting it, in a group
- **THEN** no message is touched
- **AND** the owner is told in their direct chat that it can no longer be withdrawn, and the group is told nothing

#### Scenario: a withdrawal is audited without content
- **GIVEN** a reply the owner withdraws
- **WHEN** the withdrawal completes
- **THEN** a `channel_reply_withdrawn` audit entry records the owner, the channel and the message count and carries no text

#### Scenario: replies are remembered across a restart
- **GIVEN** a reply recorded before the daemon restarted
- **WHEN** a new ledger opens the same database
- **THEN** the reply and every message id of it are found by any of its messages, and replies past the retention are pruned

#### Scenario: a direct-chat reply the transport cannot take back is not recorded
- **GIVEN** a transport that can rewrite only cards and not delete, in a direct
  chat
- **WHEN** the bot answers in plain text and the owner then sends `/del`
- **THEN** the reply was never put on record, nothing is withdrawn, and the owner
  is told there is no reply to withdraw

### Requirement: Render replies by the adapter's declared capabilities
Replies MUST render per channel capability — each adapter converts the agent's
markdown into its platform's own format and chunks to its own limit, as its
child spec states. A transport with a live surface shows a turn's progress on
ONE surface (see "Show a turn's progress on one live surface"), its lines
describing each call from its input (e.g. `⏳ Bash · list the desktop`,
`✅ Read · wedding.json`). Capabilities are declared by the adapter, not
special-cased in the core: a `ChannelCapabilities` record states what the
adapter can do — a live-updating surface via `supports_live_text`, rewriting a
delivered selection card via `supports_card_update`, interactive
buttons via `supports_buttons`, a typing indicator — and the core picks
rendering strategies from it. When the platform rejects a formatted message the
channel retries the same content as plain text before reporting failure, and
when the platform rate-limits outbound sends, sends back off and retry.

#### Scenario: a long reply is chunked for the platform
- **GIVEN** a scripted agent reply longer than the platform limit
- **WHEN** the turn completes
- **THEN** the reply arrives as multiple messages split on paragraph
  boundaries, in order

#### Scenario: a rate-limited send backs off and retries
- **GIVEN** a platform that answers a send with a rate limit and says how long to wait
- **WHEN** the channel sends a reply
- **THEN** it waits that long and sends again, a bounded number of times, and
  reports the failure only if the platform keeps refusing

#### Scenario: markdown rendering degrades by channel capability
- **GIVEN** the same markdown reply
- **WHEN** delivered through telegram and through a channel without rich text
- **THEN** telegram receives HTML (falling back to plain text if rejected)
  and the other channel receives its declared format

#### Scenario: channel progress lines describe each tool call from its input
- **GIVEN** a paired channel on an adapter that can edit messages
- **WHEN** the agent invokes a tool during a turn
- **THEN** the call's step line in the status block names the tool and a short
  descriptor drawn from its input (e.g. the Bash description, the file basename
  for Read) in a direct chat; a raw command, or an argument of a tool it has no
  rule for, is never used as the descriptor

#### Scenario: a group's progress lines name only the tool
- **GIVEN** a paired group chat on an adapter that can edit messages
- **WHEN** the agent invokes a tool during a turn
- **THEN** the call's step line in the status block names the tool and nothing
  from its input, because everyone in the group reads it

### Requirement: Stream through the platform's own surface where the chat has one
A live reply MUST use the platform's own streaming surface **where there is one
for that chat**. Where the platform can stream a partial message while it is
generated, the live-text handle (see "Show a turn's progress on one live
surface") drives that instead of rewriting a delivered message: no status
message to delete, no rewrite of an already-delivered message, and no edit-rate
ceiling on how often progress may show. A streaming surface the platform offers
only in some chats is used only there; everywhere else the transport keeps the
mechanism it had, rather than spending a refused call per snapshot to show
nothing. A snapshot past whatever the surface may carry is clipped to its tail —
the newest words are the ones being watched — because a refused snapshot would
kill the progress indicator mid-reply.

#### Scenario: a chat without the platform streaming surface keeps its old live mechanism
- **GIVEN** a platform whose streaming surface exists only for direct chats
- **WHEN** one turn runs in a direct chat and another in a group
- **THEN** the direct-chat turn's progress is streamed through the platform surface
- **AND** the group turn's progress uses the transport's previous live mechanism and makes no streaming-surface call

## REMOVED Requirements

### Requirement: Grow a reply in place on one live surface
**Reason**: A live surface no longer becomes the reply on any transport, and SeaTalk has none at all; the requirement is replaced by "Show a turn's progress on one live surface" (see ADDED below), which drops the scenarios about a stream that grows into the reply and a group that cannot stream.
**Migration**: Its dropped scenarios' markers are deleted.

### Requirement: Show a turn's working state as one status line (before smooth replies)
**Reason**: A MODIFIED block cannot drop a scenario, and this requirement loses scenarios that described the SeaTalk stream, the long-turn ping or a reply joining every narration segment; it is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: The dropped scenarios' markers are deleted.

### Requirement: Mention the asker in a group answer (before smooth replies)
**Reason**: A MODIFIED block cannot drop a scenario, and this requirement loses scenarios that described the SeaTalk stream, the long-turn ping or a reply joining every narration segment; it is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: The dropped scenarios' markers are deleted.

### Requirement: Ask the owner in the chat and take the chat's answer back to the agent (before smooth replies)
**Reason**: A MODIFIED block cannot drop a scenario, and this requirement loses scenarios that described the SeaTalk stream, the long-turn ping or a reply joining every narration segment; it is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: The dropped scenarios' markers are deleted.


### Requirement: Ping the asker when a long turn ends
**Reason**: The ping existed because a SeaTalk reply was a stream created when the turn began, so finishing it notified nobody. No transport's reply persists from the turn's start any more — every reply is a new message, which notifies on its own — so the ping, the "❓ Needs you" question ping and the `notify_after_seconds` setting have nothing left to do.
**Migration**: The Channels page loses the "Long-task ping after" field. A stored channel config that still carries `notify_after_seconds` is read without it, and the key disappears on the config's next write.

### Requirement: Offer a reply's details behind a summary card
**Reason**: A summary card with **Details** / **As file** buttons, which then read "Details posted in the thread.", made a reply harder to read than the details themselves. A transport that cannot collapse a `## Details` section now sends it as ordinary text (see "Shape a reply for what the chat can show"), and the agent is asked for one only where the transport collapses it.
**Migration**: Nothing is stored. A `details:` / `detailsfile:` button on a card sent before the change no longer does anything when tapped.

## ADDED Requirements

### Requirement: Show a turn's progress on one live surface
A turn's progress MUST show on a live surface where the transport has one —
chosen from the adapter's declared capabilities, never its type. The capability
the core asks about is `supports_live_text` ("is there a surface I can keep
updating while this turn runs?"), whether the transport gets there through a
message draft or by editing one message (Telegram). The core asks for a
live-text handle and never branches on the mechanism underneath, so no
capability says "can rewrite a delivered text message".

A live surface is **scaffolding**, never the reply: when the turn ends it is
closed (a draft expires, a status message is deleted) and the finished reply is
sent as a new message. A reply created when the turn began would notify nobody
when it ends, and a message that carries the turn's progress and then turns into
the answer redraws itself on every step; the other IM-agent products show a
running turn through typing or a status surface and keep their final message for
the answer. A turn keeps at most ONE live surface, opened only once the turn has
run past the update interval — either tool activity opens it or the reply text
does — so a reply that finishes sooner opens none, avoiding a create → delete →
resend flicker. A turn still thinking in silence opens it on the status line's
first tick.

The cadence of updates belongs to the TRANSPORT, which alone knows its own
limits: the core offers every snapshot and each surface buffers to what it can
sustain. A throttle added by the core on top hides that buffer completely and
makes progress arrive a paragraph at a time. Interim snapshots are plain text
clipped to the platform's per-message limit, keeping their newest words, so a
long or half-written-markdown preview never breaks a platform parser or exceeds
the cap.

A transport with no live surface (SeaTalk) posts no interim traffic: its typing
indication is the progress (see "Acknowledge receipt and completion by
capability") and its final reply is the whole signal. All best-effort — a
failed update, close, or heartbeat never breaks the turn.

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

#### Scenario: a live surface is never the reply
- **GIVEN** a paired channel on an adapter with a live surface
- **WHEN** a turn runs a tool and then answers
- **THEN** the surface shows the progress and is closed when the turn ends, and
  the answer arrives as a new message after it

### Requirement: Show a turn's working state as one status line
While a turn runs on a transport with a live surface (see "Show a turn's
progress on one live surface"), that surface MUST show one status block the
reader can take in at a glance: a header saying that the turn is working, for how long,
and how many steps it has taken (`⏳ Working · 2m 14s · 7 steps`, with the
failed count when there is one); the agent's latest narration as a `💬` line;
and the newest three step lines, older ones collapsed into `+N earlier`. A step
line names the tool, plus a short descriptor from its input in a direct chat
only; a group's step lines carry nothing from the input. The answer written so
far follows under a rule. The header MUST keep ticking while nothing else
happens — a long silent tool still shows time passing — on the cadence the live
surfaces already keep alive at, so the tick costs no extra traffic.

Text the agent writes before a tool call is narration ("Let me check the
logs"): once the tool call arrives it moves up into the `💬` line and the answer
tail shows only text written after the last tool call. The final reply, on every
transport, MUST carry only the answer: the text written after the last tool
call. A turn that wrote nothing after its last tool call replies with the last
text it did write, so an answer is never lost to a trailing tool call.
Narration never reaches the final message.

A channel setting `show_steps` (default on) hides the step lines and keeps the
header and narration — useful in a busy group. It is edited on the Channels
page, which offers it only for a platform that has a live surface (Telegram).

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

#### Scenario: the final reply carries only the answer
- **GIVEN** a turn whose agent wrote text, called a tool, wrote more text, called
  another tool, then wrote its answer
- **WHEN** the reply is delivered
- **THEN** it holds the answer alone, and neither earlier text appears in it

#### Scenario: a turn that ends on a tool call replies with its last text
- **GIVEN** a turn whose agent wrote its answer and then called one more tool,
  writing nothing after it
- **WHEN** the reply is delivered
- **THEN** it holds the last text the agent wrote

#### Scenario: hiding steps keeps only the header
- **GIVEN** a channel with `show_steps` off
- **WHEN** a turn calls a tool
- **THEN** the status block shows the header and narration but no step line

#### Scenario: the step lines are hidden in the channel's settings
- **WHEN** the owner switches the channel's step lines off in its settings, then on again
- **THEN** the channel's `show_steps` setting is off, then on again

### Requirement: Mention the asker in a group answer
A group answer MUST name who it is for, and notify them. In a group, the bot's
reply MUST open by @mentioning the member whose message drove the turn, using the
platform's own mention markup — so the answer notifies the person waiting for it
and a busy room can see at a glance which of them it belongs to. In a direct chat
it MUST NOT: a 1:1 conversation has nobody to disambiguate, and an @ there is
only shouting. Five constraints bound it.

- **The mention MUST be in the content the reply is CREATED with**, not added to
  it later. A platform decides @ notifications at creation; a mention that
  arrives on a later update of the same message renders as a name and notifies
  nobody, which is the worst of both — the room sees an @ the mentioned person
  never got. The reply is always a new message sent when the turn ends (see
  "Show a turn's progress on one live surface"), so it opens with the mention,
  exactly once.
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
- A live surface carries no mention: it is scaffolding, deleted or expired
  before the answer, and a mention there would only render as markup.

#### Scenario: a group reply @mentions whoever asked
- **GIVEN** an addressed message in a group from a member the transport named,
- **WHEN** the turn replies,
- **THEN** the reply opens with the platform's mention markup for that member.

#### Scenario: a direct reply carries no mention
- **GIVEN** the same channel answering in a 1:1 chat,
- **WHEN** the turn replies,
- **THEN** the reply carries no mention — there is nobody to disambiguate.

#### Scenario: a live surface carries no mention and the reply does
- **GIVEN** a group turn on a transport with a live surface and a mention
  spelling
- **WHEN** the turn shows its progress and then replies
- **THEN** no snapshot of the surface carries the mention, and the reply — a new
  message — opens with it exactly once

### Requirement: Ask the owner in the chat and take the chat's answer back to the agent
A question raised in a channel conversation (spec chat "Pause a turn on a question
for the owner") MUST go out in that chat, one card per question in order: the
context (a diff as a code block), "❓ <question>", the options — with their
descriptions listed in the body when any has one — as up to four equal buttons,
and "Or reply with your answer.". A multi-select question's buttons MUST toggle a
✓ in place and a **Submit** button sends the choice. A tap MUST be owner-gated
like every card tap. The owner's next text message in that chat or thread while
the question is pending MUST be taken as the answer and not start or queue a
turn. Nothing MUST be posted in the owner's name. Once the question is answered or
cancelled, every card of it MUST be rewritten in place to
"✓ Answered: <answer> · HH:MM" ("Stopped" when cancelled); where the platform
cannot rewrite it, that line is sent as a reply. The card is itself a new
message, so it notifies the owner however long the turn has run.

#### Scenario: a tap answers the agent without a message from the owner
- **GIVEN** a SeaTalk card "❓ Apply this change to staging?" with Yes and No
- **WHEN** the owner taps Yes
- **THEN** the agent receives "Yes", the card reads "✓ Answered: Yes · 11:42", and no message is sent as the owner

#### Scenario: a text reply answers the pending question
- **GIVEN** a pending question in the owner's Telegram chat
- **WHEN** the owner sends "only the read replica"
- **THEN** the agent receives that text as the answer and no new turn starts

#### Scenario: a multi-select question is answered with Submit in the chat
- **GIVEN** a SeaTalk card for a multi-select question with three options
- **WHEN** the owner taps two options and then Submit
- **THEN** the two buttons showed a ✓ before Submit, and the agent receives both labels

#### Scenario: a question with described options lists them in the card
- **GIVEN** a question whose options "Yes, apply" and "No, keep" each have a description
- **WHEN** its card goes out
- **THEN** the body lists "• Yes, apply — <description>" and "• No, keep — <description>" under the question, with one button per option and "Or reply with your answer."

#### Scenario: several questions go out one card at a time
- **GIVEN** an ask of two questions in a SeaTalk chat
- **WHEN** the owner answers the first
- **THEN** its card reads "✓ Answered: <answer> · HH:MM" and only then does the second question's card go out

#### Scenario: a non-owner's tap is refused
- **GIVEN** a question card in a paired group
- **WHEN** a member who is not the owner taps an option
- **THEN** the group is told only the bot’s owners can use it and the question stays pending

#### Scenario: stopping a turn rewrites the pending card
- **GIVEN** a pending question card in a chat
- **WHEN** the owner stops the turn
- **THEN** the card reads "Stopped" with its buttons gone
