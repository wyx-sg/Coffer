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

Coffer's default reply style asks for a reply shaped for a phone: do not narrate
steps (Coffer already shows that it is working); the first line is the outcome
in one sentence, because it becomes the notification; at most about 15 lines;
code blocks under 30 lines, longer logs attached as files; diagrams and charts as
PNG files, never as source; and concise never drops evidence — an
investigation's key log lines, error messages and IDs are quoted verbatim.

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
- **THEN** it asks for the outcome in one first sentence, says only the text
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

## REMOVED Requirements

### Requirement: Append the owner's system prompt to a channel turn
**Reason**: The owner asked to see Coffer's built-in prompt and edit it, not only
add text after it. The append is now a read-only channel note plus a reply style
the owner can rewrite (ADR channel-prompt-fixed-note-and-editable-style).
**Migration**: A stored `direct_system_prompt` / `group_system_prompt` is read as
a `*_reply_style` holding Coffer's default style followed by that prompt, so the
agent reads the same instructions; the old keys go on the next write.

## ADDED Requirements

### Requirement: Let the owner rewrite a channel's reply style
A channel MUST carry one reply style per chat kind in its configuration:
`direct_reply_style`, for direct chats and the threads opened in them, and
`group_reply_style`, for a group's main chat and its threads. Each is empty by
default, meaning it follows Coffer's default style, or holds the owner's rewrite:
plain multi-line text of at most 6,000 characters, trimmed of surrounding
whitespace. Text saved equal to Coffer's default MUST be stored empty, so it
keeps following the default. A longer one MUST be refused and leave the stored
value as it was. Beside each, `*_reply_style_base` holds the fingerprint of the
default a rewrite was written against (Coffer stamps today's when none is
given); it is empty while the style follows the default.

A channel turn MUST carry, after the channel note, the line `Reply style:` and
the conversation's chat kind's rewrite, or Coffer's default when there is none
or the chat kind cannot be located. A rewrite replaces only the default style,
never the channel note. The style MUST be read from the channel's stored
configuration each time a turn's system prompt is composed, so a change applies
from the next turn of every conversation — with no restart, and also when the
turn resumes the agent's existing session: Coffer sends its system context with
every turn (Claude Code's appended system prompt, Codex's
`developerInstructions` on `thread/resume` as on `thread/start`). See [Chat and
turns](../../../docs-site/architecture/chat.md).

A channel stored with the earlier `direct_system_prompt` / `group_system_prompt`
MUST be read as a rewrite holding Coffer's default style followed by that
prompt, so its turns carry the same instructions as before; a key the document
already sets for the style wins.

On the Channels page, the channel's Settings tab has a **System prompt** section
after Replies and conversations, with a **Direct chats** row and a **Group
chats** row. Each shows Coffer's channel note for that chat kind on this channel,
marked read-only — for a stopped channel, the note its platform will send — and
the reply style in force, marked **Default** or **Rewritten**. When a rewrite was
written against a default that has since changed, the row says so. An **Edit**
button opens a dialog with one text area per chat kind, each starting from the
style in force, with **Restore default**, a character count, Cancel and Save.
Nothing is saved until Save, a save re-stamps the default each style was written
against, the dialog closes only once the save has landed, and Save is unavailable
while a style is over the limit. The channel's status reports, under `prompts`,
per chat kind the channel note, Coffer's default style and whether it changed
since the rewrite. Over REST the styles are fields of the channel's config
(`PATCH /api/v1/resources/{uid}`, `coffer channel update`) and are reported in
the channel's status settings.

#### Scenario: the owner's reply style follows Coffer's note
- **GIVEN** a channel whose direct-chat reply style is "Answer in Chinese."
- **WHEN** a direct-chat turn's system prompt is composed
- **THEN** it holds Coffer's channel note in full, then the line `Reply style:`
  and the style as written, and not Coffer's default style

#### Scenario: an untouched reply style follows the default
- **GIVEN** a channel whose group-chat reply style is empty or only whitespace
- **WHEN** a group turn's system prompt is composed
- **THEN** it is Coffer's channel note, then `Reply style:` and Coffer's default

#### Scenario: a rewritten style cannot remove how the channel works
- **GIVEN** a channel whose direct-chat reply style is a rewrite
- **WHEN** a direct-chat turn's system prompt is composed
- **THEN** it still says how to call `coffer__ask`, how to send a file with
  `MEDIA:`, that only the text after the last tool call is sent and that it
  cannot click dialogs

#### Scenario: each chat kind reads its own reply style
- **GIVEN** a channel with a direct-chat style and a different group-chat style
- **WHEN** a turn runs in its direct chat, in a group's main chat and in a group thread
- **THEN** the direct-chat turn carries the direct-chat style, and both group
  turns carry the group-chat style

#### Scenario: an edited reply style applies from the next turn
- **GIVEN** a direct-chat conversation that has already run a turn, so its next
  turn resumes the agent's session
- **WHEN** the owner changes the direct-chat style and sends another message
- **THEN** that turn's system prompt carries the new text and not the old one,
  with no restart of the channel

#### Scenario: a reply style longer than 6,000 characters is refused
- **GIVEN** a channel
- **WHEN** a style of 6,001 characters is saved, over REST or in the dialog
- **THEN** the REST save is refused with 422 and the stored style is unchanged,
  and the dialog states the limit with Save disabled

#### Scenario: a reply style equal to the default follows the default
- **WHEN** a style identical to Coffer's default is saved
- **THEN** it is stored empty, with no fingerprint, and keeps following the default

#### Scenario: an owner prompt from before the reply style keeps its effect
- **GIVEN** a channel stored with a direct-chat `direct_system_prompt` and an
  empty group one
- **WHEN** its configuration is read
- **THEN** the direct-chat style is Coffer's default followed by that prompt,
  stamped with today's default, the group style follows the default, and the old
  keys are gone

#### Scenario: the Settings tab shows the note a stopped channel will send
- **GIVEN** a channel that is not running
- **WHEN** its System prompt section is composed
- **THEN** each chat kind's note is written from what its platform's transport
  declares, with the owner's style for that kind

#### Scenario: the Settings tab shows Coffer's channel note and the reply style in force
- **GIVEN** a channel with a group-chat rewrite and no direct-chat one
- **WHEN** the owner opens its Settings tab
- **THEN** each row shows Coffer's channel note marked read-only, the direct row
  shows Coffer's default style marked Default, the group row the rewrite marked
  Rewritten, and nothing in the section is an input

#### Scenario: the Settings tab says when Coffer's default style has changed
- **GIVEN** a direct-chat rewrite written against an older default
- **WHEN** the owner opens the channel's Settings tab
- **THEN** the direct row says the default has changed since, and the group row
  does not

#### Scenario: the reply styles are edited through a dialog on the Settings tab
- **GIVEN** a channel with a group-chat rewrite and no direct-chat one
- **WHEN** the owner chooses Edit, types a direct-chat style, restores the
  group's default and saves
- **THEN** the fields started from the default and the rewrite, nothing was saved
  before Save, and the saved configuration carries the direct style and an empty
  group style with every other setting and ref as it was
