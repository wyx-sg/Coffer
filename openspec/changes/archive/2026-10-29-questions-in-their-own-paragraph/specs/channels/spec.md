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
heading; when it needs something from the person to go on, to ask in its reply,
every question in that one message, in its own paragraph after what was done and
numbered 1, 2, 3 when there are several, and end its turn, since the answer comes as
the next message ([chat](../chat/spec.md) "Ask the owner in the reply, not in a
dialog"); that it cannot click permission or confirmation dialogs on the user's computer;
and how to send a file (`MEDIA:/absolute/path` on its own line). Where the
running transport can read threads, it also names `coffer__channel_read_thread`
for a thread's earlier messages, with its arguments taken from the origin block.

Coffer's default reply style asks for a reply that reads like a person texting
a colleague: the answer first, in one or two plain sentences, because the first
line becomes the notification; nothing repeated back — no "Got it" and no
restating what the person just said; no process — no narrated steps (Coffer
already shows that it is working), no list of what was checked, no spelled-out
assumptions or caveats, and something the agent could not do is mentioned only
when it changes what the reader does next; when it needs something from the
person, everything asked at once; about 8 lines at most, with a list
only for three or more parallel items; a full report only as a Markdown file,
and only when the reader asks for it — the reply never ends by offering one;
logs over 30 lines as files, diagrams as PNG
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
  report only as a file and only when asked for, never offered at the end of a
  reply, says only the text
  after the last tool call is sent, and asks for diagrams as PNG files and for
  every question to the person in one message of the reply, in its own
  paragraph after what was done, several questions numbered 1, 2, 3

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
