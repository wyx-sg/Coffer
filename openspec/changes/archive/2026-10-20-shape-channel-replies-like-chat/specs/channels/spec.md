## MODIFIED Requirements

### Requirement: Tell a channel-driven agent it is on a chat channel
A channel-originated turn MUST tell the agent it is bridged to a chat channel,
not a terminal. Its system-prompt append is the **channel note** followed by the
line `Reply style:` and the reply style in force for the conversation's chat
kind (see "Let the owner rewrite a channel's reply style").

The channel note says how the channel works, and Coffer alone writes it. It
names **where** the agent is — the platform, the chat kind (direct chat, group
chat, group thread) and the channel by its current label — and **what renders
there**, in the sentence or two the running transport declares as its
`render_notes` (SeaTalk: bold, italic, inline code, code fences and lists, but no
headings, links or tables; Telegram: its rich Markdown, tables included). It
says only what the agent writes after its last tool call is sent, so the whole
answer goes there; only where the transport collapses one
(`collapses_details`, Telegram), to put anything long under a `## Details`
heading; to call `coffer__ask` when it needs a yes or a choice before it goes on
(see "Ask the owner in the chat and take the chat's answer back to the agent");
that it cannot click permission or confirmation dialogs on the user's computer;
and how to send a file (`MEDIA:/absolute/path` on its own line). Where the
running transport can read threads, it also names `coffer__channel_read_thread`
for a thread's earlier messages, with its arguments taken from the origin block.

Coffer's default reply style asks for a reply that reads like a person texting
a colleague: the answer first, in one or two plain sentences, because the first
line becomes the notification; no process — no narrated steps (Coffer already
shows that it is working), no list of what was checked, no spelled-out
assumptions or caveats, and something the agent could not do is mentioned only
when it changes what the reader does next; about 8 lines at most, with a list
only for three or more parallel items; a full report only as a file, offered
first ("do you want the full report?") and sent as Markdown when the reader says
yes or asked for it up front; logs over 30 lines as files, diagrams as PNG
files, never as source; and short never drops evidence — the key log line,
error or ID is quoted verbatim.

Web-UI turns are unaffected — the append rides only on a conversation whose
`channel_uid` is set. A channel that has been deleted, or is not running, still
gets it, saying less. See [A Channel's System Prompt Is a Fixed Channel Note Plus
a Reply Style the Owner Can Rewrite](../../../docs/decisions/channel-prompt-fixed-note-and-editable-style.md).

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
- **WHEN** a channel turn's note is composed with Coffer's default reply style
- **THEN** it asks for the answer in one or two plain sentences first, a full
  report only as a file the reader is asked about first, says only the text
  after the last tool call is sent, and asks for diagrams as PNG files and a
  `coffer__ask` call when the agent needs the owner's answer

#### Scenario: only a transport that collapses details is asked for a details section
- **GIVEN** a Telegram direct chat and a SeaTalk group thread
- **WHEN** each turn's note is composed
- **THEN** the Telegram note asks for long content under a `## Details` heading
  Coffer collapses, and the SeaTalk note does not mention one

#### Scenario: the note names the thread-reading tool where threads can be read
- **GIVEN** a conversation on a running channel whose transport can read threads
- **WHEN** its turn's note is composed
- **THEN** it names `coffer__channel_read_thread` and the origin block its
  arguments come from, while a note for a transport that cannot read threads
  does not

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
Narration never reaches the final message. An agent that marks its own messages
as narration (Codex's `commentary` phase, carried as `MessageEnd.commentary`)
has those messages moved into the `💬` line and left out of the reply wherever
they stand, even after the last tool call; messages the agent wrote between two
tool events join the reply as paragraphs. A turn that wrote nothing but
narration replies with its last words.

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

#### Scenario: narration the agent marked never reaches the reply
- **GIVEN** a turn whose agent marks a message as narration, calls a tool, marks
  another message after it as narration, then writes its answer
- **WHEN** the reply is delivered
- **THEN** it holds the answer alone

## ADDED Requirements

### Requirement: Ask for the short version of a reply too long for a chat
A reply that finished cleanly but is too long to read as a chat message — more
than 20 lines with text, or more than 1,500 characters, not counting `MEDIA:`
lines or a `## Details` section the transport collapses — MUST NOT be sent.
Instead Coffer asks the same conversation, in a follow-up turn of its own, to say
it again short: only the conclusion and what the reader needs to act on, in at
most 5 lines and the same language, ending by asking whether they want the full
report as a file. The follow-up's text opens with `[Coffer]`, never names the
conversation, and runs through the conversation's ordinary queue; its reply is
rendered into the same chat and thread, and is never held back again however
long it is. Cutting the long reply would leave half a message, and Coffer keeps
no reply text to send later; the agent still holds the full answer in its
session.

The follow-up's reply carries a **📄 Full report** button where the transport
has buttons. A tap by the owner is the owner asking, in a message of its own,
"Send me the full report as a Markdown file." — through every gate a typed
message passes — and the agent answers it with the file. A tap by anyone else
asks nothing.

A failed or stopped turn's reply goes out as it always did, with its notice. When
a message is already waiting in the conversation's queue, the long reply goes
out as it is: the waiting message would run first and make "your last reply"
mean something else. See [A Long Channel Reply Is Rewritten Short by the
Agent](../../../docs/decisions/long-channel-reply-is-rewritten-short.md).

#### Scenario: a reply too long for a chat is said again short
- **GIVEN** a channel whose agent answers in 40 lines
- **WHEN** the turn ends cleanly
- **THEN** the 40 lines are not sent, the conversation is asked in a turn opening
  with `[Coffer] Your last reply (40 lines)` for the short version, and that
  reply arrives carrying the **📄 Full report** button

#### Scenario: the full-report button asks the agent for the file
- **GIVEN** a shortened reply carrying the **📄 Full report** button
- **WHEN** the owner taps it
- **THEN** the conversation runs a turn asking "Send me the full report as a
  Markdown file." and its answer is delivered

#### Scenario: the short version is never shortened again
- **GIVEN** an agent whose short version is still 40 lines
- **WHEN** the follow-up turn ends
- **THEN** its reply is delivered as it is and no further turn is asked for
