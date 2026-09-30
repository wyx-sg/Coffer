## ADDED Requirements
### Requirement: Name a channel by any display name
A channel's name MUST be any display name a person types — spaces, capitals and
any script included, up to 80 characters — and MUST be renamable. Channels are
told apart by their `uid`, so two channels may share a display name. The
display name is the channel's title (resource-framework "Carry an optional
editable title on the kinds that have one"): the Channels page's Add dialog
registers what was typed as the title and derives the resource's name from it —
lowercased, every run of characters the name rules refuse turned into one `-`,
`channel` when nothing is left — stepping to `-2`, `-3`, … past a name another
channel already holds, so adding a channel never fails on a name the person did
not type. The channel's Settings show the display name as its Name and edit it
as the title. The command line keeps addressing a channel by its name and sets
the display name with `--title`.

#### Scenario: a channel is named by any display name
- **GIVEN** the Add channel dialog on the Channels page
- **WHEN** the owner names a new Telegram channel "Team bot!" and connects it
- **THEN** the channel is registered with the title "Team bot!" and the name `team-bot`
- **AND** a second channel named "Team bot!" is registered as `team-bot-2` rather than refused

## MODIFIED Requirements
### Requirement: Answer the conversation commands from any paired chat
Nine words are Coffer's commands in a paired chat, and nothing else: `/new`,
`/stop`, `/model`, `/dir`, `/status`, `/resume`, `/thread`, `/kb` and `/help`
(`/start` is a hidden alias of `/help`). They MUST work from any paired chat.
`/new [agent]` starts a fresh conversation with the chat's settings (see "Keep a
chat's settings across its conversations" and "Switch the agent with /new"),
`/stop` interrupts the running turn, `/status` reports the chat's state (see
"Report the chat's state as a status card") and `/help` lists the commands (see
"Offer the commands as a help card"). `/stop` and `/new` take effect even while
a turn is running; other messages join the conversation's pending queue (spec
`chat` — the one the web shows) and run in order, a burst of them arriving as one
turn (see "Take a burst of messages as one turn"). A message that joins the
queue behind a running turn MUST be answered with a "⏳ Queued (n)" notice, n
being how many now wait. Up to 10 may wait; only a message arriving while 10
already wait is dropped, and the chat MUST be told it was dropped and why.
`/new` MUST answer with a one-line card — "🆕 New conversation · <agent> ·
<model> · <directory>" — carrying Agent, Model and Dir buttons: Agent opens the
agent card (see "Switch the agent with /new"), Model and Dir run `/model` and
`/dir`; a transport without buttons gets the same line as text. A message arriving exactly
when the previous turn finishes joins the queue rather than racing it: turns for
one conversation never overlap.

The commands that configure the conversation the chat is bound to are specified
in their own requirements — `/model` in "Switch the model and reasoning effort
from chat", `/dir` in "Choose the working directory from chat", `/resume` in
"Resume an earlier conversation from chat", `/kb` in "Save a sent document into
a collection", and `/thread` in "Open parallel conversations beside a direct chat".
All of them live on one roster (see "Register the bot's command menu and profile
from one roster"), so none of the lists derived from it can go stale, and every
other text that starts with `/` is a message (see "Pass unreserved slash text to
the agent").

#### Scenario: /new starts a fresh conversation
- **GIVEN** a paired channel with an active conversation
- **WHEN** the peer sends `/new`
- **THEN** a new conversation with the thread's current agent (the default
  agent when none was chosen, or when the chosen one has since left the
  channel's scope) becomes active and the old one remains in history

#### Scenario: /stop interrupts a running turn
- **GIVEN** a turn in progress
- **WHEN** the peer sends `/stop`
- **THEN** the turn ends as interrupted and the chat is responsive again

#### Scenario: messages during a turn are queued in order
- **GIVEN** a turn in progress
- **WHEN** the peer sends two more messages further apart than the quiet window
- **THEN** they run as consecutive turns in arrival order after the first ends

#### Scenario: the queue is bounded and overflow is reported
- **GIVEN** a turn in progress
- **WHEN** the peer sends ten more messages, and then an eleventh
- **THEN** each of the ten is answered "⏳ Queued (n)" with its place, and all ten run in order
- **AND** the eleventh is dropped and the peer is told that ten were already waiting

#### Scenario: /new answers with a one-line card
- **GIVEN** a paired chat on a button-capable transport with two agents the channel may drive
- **WHEN** the owner sends `/new`, taps Agent, and taps the second agent
- **THEN** the first answer is one line naming the agent, the model and the directory, with Agent, Model and Dir buttons
- **AND** Agent offers the channel's agents with the current one ticked, and the tap starts a fresh conversation on the second agent

### Requirement: Switch the agent with /new
The owner MUST be able to switch which agent answers in a chat with `/new
<agent>`: the agent of an existing conversation cannot change, so choosing
another one is starting a fresh conversation with it, and one command says so.
The argument is a name the owner sees — the agent's display name or its
lowercase hyphenated name (`claude-code`, `codex`), matched case-insensitively
with `-`, `_` and spaces treated alike — never an internal key, and no answer
shows one. It is validated against the agents the channel may drive (see "Limit
the agents a channel may drive to its scope"); on success it becomes the chat
thread's sticky agent, so later messages and `/new` use it until switched again.
A model and effort chosen for the previous agent do not follow it to a different
one; the working directory does. An unknown name is refused with the valid names
listed and the active conversation unchanged; no channel-side code is added per
agent. The `/new` card's Agent button offers the same agents as a card, the one
in effect ticked; a tap does exactly what `/new <agent>` does, and a tap naming
an agent the channel may no longer drive is refused with nothing changed.

#### Scenario: /new with an agent name switches and sticks
- **GIVEN** a paired channel with a second scripted agent registered
- **WHEN** the peer sends `/new <second agent's name>` and then a message
- **THEN** a fresh conversation pinned to the second agent becomes active, the
  message is answered by it, and a bare `/new` reuses it until switched again

#### Scenario: /new rejects an unknown agent name
- **GIVEN** a paired channel
- **WHEN** the peer sends `/new nope`
- **THEN** the channel replies that the agent is unknown and lists the valid
  names, and the active conversation is unchanged

### Requirement: Report the chat's state as a status card
`/status` MUST answer what the chat is running in words a person reads, under
the title "Status": the conversation's title (or its parallel mark); one line
with the agent by its display name, the model by the name its button shows, the
effort when one is set, and the working directory (under the home directory as
`~/…`); then "Running", "Running · n waiting", "n waiting" or "Idle"; in a
direct chat, one "Parallel threads:" line naming each with its state (see "Open
parallel conversations beside a direct chat"). It shows no conversation or agent
ids. Where the transport has buttons it is a card whose buttons — Stop while a
turn runs, then New, Model, Resume, Dir — run those commands, so a user who
remembers one word reaches every action by tapping; elsewhere it is text.
In a group where the answer can be delivered to the asker alone (see "Keep
non-answer chatter private in a group") it is sent that way, as text: a card is
always an ordinary message the whole room would see. The same holds for the
help card.

#### Scenario: /status shows names, not ids, with action buttons
- **GIVEN** a paired chat on a button-capable transport with an active
  conversation
- **WHEN** the owner sends `/status`
- **THEN** a card titled "Status" names the conversation, the agent by display name, the model,
  the effort and the directory, carries the New, Model, Resume and Dir buttons —
  and Stop too while a turn runs — and contains no conversation id

### Requirement: Offer the commands as a help card
`/help` MUST list the commands from the roster on one line, each with its
arguments, then say that anything else is a message to the agent; where the
transport has buttons it is a card titled "Coffer" carrying New, Stop, Model,
Status and Resume. The same help follows a successful pairing
once, so a platform with no command menu (SeaTalk) still shows a new owner what
the bot accepts.

#### Scenario: /help is a card with the five actions
- **GIVEN** a paired chat on a button-capable transport
- **WHEN** the owner sends `/help`
- **THEN** a card lists the commands and carries the New, Stop, Model, Status
  and Resume actions as buttons

#### Scenario: the help card follows pairing
- **GIVEN** an unpaired channel with an issued pairing code
- **WHEN** the owner pairs by sending the code
- **THEN** the pairing is confirmed and the help follows it once

### Requirement: Choose the working directory from chat
The owner MUST be able to move a chat's conversation to another working
directory from chat — but only to a directory the channel allows. A channel's
Settings carry its Working directories: a **Default**, the absolute path new
conversations start in (stored as the default agent configuration's `cwd`; set
with `coffer channel add|edit --default-dir PATH`, cleared with `edit
--no-default-dir`; none means the agent's own), and the list **Allowed for
/dir**, `directories`, absolute paths shown as rows with Remove and an Add
directory… folder picker, the default's row marked "default", and edited with
`coffer channel add|edit --dir PATH` (repeatable; `edit --no-dirs` clears it);
each entry also admits the directories beneath it. With no allowed directory,
`/dir` is off.
`/dir <path>` accepts an allowed path or one beneath it, `/dir <name>` the base
name of exactly one allowed path; either must be an existing directory. Because
an agent's session is tied to its directory, setting one opens a fresh
conversation there and remembers the directory for the chat; the previous
conversation stays one `/resume` away. `/dir default` returns to the channel's
default directory. `/dir` with no argument reports the directory in effect and,
where the transport has buttons, offers the allowed ones as a "Working
directory" card naming each by its path (under the home directory as `~/…`),
plus Default when the channel's default is not one of them. A switch answers
"📁 Now in <path> — started a fresh conversation". A channel that allows no
directory says `/dir` is off and where to add one; a directory outside the list
is refused with the allowed ones named.

#### Scenario: /dir switches to an allowed directory in a fresh conversation
- **GIVEN** a paired channel whose allow-list names an existing directory
- **WHEN** the owner sends `/dir <that directory's name>` and then a message
- **THEN** a fresh conversation runs that message in the directory, and the
  previous conversation is still listed by `/resume`

#### Scenario: /dir refuses a directory outside the allow-list
- **GIVEN** a paired channel whose allow-list names one directory
- **WHEN** the owner sends `/dir /etc`
- **THEN** the channel refuses, naming the allowed directory, and the active
  conversation and its directory are unchanged

#### Scenario: the channel's directories are edited from the Channels page and the CLI
- **GIVEN** a registered channel
- **WHEN** the owner sets its directories with `coffer channel edit --dir` or in
  the channel's settings on the Channels page
- **THEN** the channel's configuration carries exactly those absolute paths, and
  `--no-dirs` clears them

#### Scenario: the channel's default directory is edited from the Channels page and the CLI
- **GIVEN** a registered channel
- **WHEN** the owner sets its Default working directory in the channel's settings on the Channels page, or with `coffer channel edit --default-dir`
- **THEN** the channel's default agent configuration carries that absolute path as `cwd`, new conversations start there, and `--no-default-dir` clears it
- **AND** a relative path is refused with nothing saved
