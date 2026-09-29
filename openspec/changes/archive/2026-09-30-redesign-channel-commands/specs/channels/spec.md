## ADDED Requirements

### Requirement: Offer choices and actions as owner-gated cards
On a transport that declares the `supports_buttons` capability, the core MAY
render a command's choice list as an **interactive selection card**; outbound
text MAY carry `ChoiceButton`s, which a button-capable transport renders as such
a card. A button tap arrives as a normalized `InboundCallback` carrying an
opaque value instead of text; the core MUST **owner-gate it exactly like a
message** (chat + sender identity, see "Gate inbound traffic on sender
identity") before routing it to the same switch the text command performs. A tap
never pairs, and an unsupported transport silently keeps the text path. This
realizes the interactive-button capability that
[Channel Adapter Framework](../../../docs/decisions/channel-adapter-framework.md)'s
`ChannelCapabilities` anticipated ("show buttons?").

Two kinds of button exist. A **choice** carries `model:`, `effort:`, `dir:`,
`resume:` or `collection:` and applies that choice. A **command button** carries
`cmd:<name>` — the Stop, New, Model, Resume and Dir buttons of the status and
help cards — and a tap runs exactly what typing `/<name>` in that chat or thread
runs.

The card payload MUST follow each platform's published shape, which each child
spec states. A card the platform refuses is not the end of the command: the
handler falls back to the plain-text answer it already has, so a rejected card
degrades to a working message instead of leaving the user with silence. The
rejection is logged so it stays diagnosable. After a choice lands, a transport
that `supports_card_update` MUST **rewrite the card in place** so its tick moves
to the new choice — a card left advertising the option the user just took
invites a second tap that does nothing. The rewrite is best-effort: the choice
is already applied and confirmed in chat, so a transport without the
capability, or a rewrite the platform refuses, changes nothing the user relies
on.

A card carries a **bounded number of buttons** — six, navigation included. A
choice list longer than that bound is **paginated**: the card shows four choices
plus `← Prev` / `Next →`, and a navigation tap **rewrites the same message** at
the next window through the same `supports_card_update` path an applied choice
uses. One rule serves every card — a handful of levels or directories render
with no navigation chrome at all.

A navigation payload lives in its own callback namespace (`page:<kind>:<index>`),
disjoint from the values a choice carries, and fixed-size so it fits the
tightest callback budget any transport declares. The separation is what
guarantees the invariant: **a page turn changes nothing.** The set of kinds that
namespace admits is closed and explicit, so adding a card that ticks a current
choice means adding its kind there too; a `page:` value naming a kind Coffer
does not render is dropped, not applied. It re-reads what is in effect and
re-renders; it can never be mistaken for a choice, and a malformed navigation
value is dropped rather than allowed to fall through to the switch. Because the
page in view may not hold the option in effect, the card's body always names
what is in effect and which page it is on, so a page showing no tick never reads
as a card claiming nothing is selected.

Unlike the cosmetic rewrite after a choice, a page turn is something the user
asked to see, so it degrades rather than dropping: where the message cannot be
rewritten in place — no `supports_card_update`, or an update the platform
refused — the requested page is posted as a fresh card, and as plain text if
that is refused too.

#### Scenario: a command button runs the command it names
- **GIVEN** a paired channel on a button-capable transport showing a `/status`
  card
- **WHEN** the owner taps its New button
- **THEN** a fresh conversation becomes active exactly as if the owner had typed
  `/new` in that chat

#### Scenario: a long selection card is browsed page by page in place
- **GIVEN** a paired channel on a button-capable transport showing a `/model`
  card built from a catalogue far longer than one card can carry
- **WHEN** the owner taps `Next →`
- **THEN** the same card message is rewritten with the following page of models
  — no second card is posted, no model is switched, and the body still names the
  model in effect and the page it is on; the last page offers no `Next →`, and a
  page turn the platform will not apply in place arrives as a fresh card (or as
  plain text) rather than as silence

#### Scenario: a non-owner selection-card tap is ignored
- **GIVEN** a paired channel whose peer has a stored `sender_id`
- **WHEN** a different member of the chat taps a selection-card button
- **THEN** the tap is ignored and the owner's model and conversation are
  unchanged

#### Scenario: a refused selection card falls back to the text reply
- **GIVEN** a button-capable transport that refuses the selection card outright
- **WHEN** the owner sends `/model` or `/status`
- **THEN** the command answers with its plain-text report instead and the
  refusal is logged — silence is the one outcome a command must never produce

#### Scenario: a tapped selection card is rewritten with the new choice
- **GIVEN** a paired channel on a transport that `supports_card_update`, showing
  a selection card
- **WHEN** the owner taps a different choice
- **THEN** the card is rewritten in place with the tick moved to the choice just
  made; on a transport without the capability nothing is rewritten and the
  choice still applies, and a rewrite the platform refuses leaves the choice and
  its confirmation intact

### Requirement: Open parallel conversations beside a direct chat
A direct chat MUST be one conversation, and the owner MUST be able to open
further conversations beside it deliberately:
- `/thread [title]` opens a **parallel thread**. It is a thread in the direct
  chat with a conversation of its own, and the owner talks to it by replying
  inside that thread. How the thread is created is a platform fact each child
  spec states.
- Each parallel thread is numbered per chat, and it MUST carry the mark
  `🧵#N title` (title defaulting to `Task`) wherever it is shown: the thread's
  root message or topic name, the conversation's title on the web, and `/status`
  both inside it and in the direct chat.
- `/status` in the direct chat says how many parallel threads the chat has and
  lists each one's mark, agent, and whether a turn is running, waiting, or idle,
  newest first.
- `/thread` in a group answers that every group thread is already its own
  conversation, and opens nothing.

A thread in a direct chat that `/thread` did not open is, on a platform where
such threads are casual replies, part of the direct chat's conversation. It is
still answered inside that thread.

#### Scenario: /thread opens a marked parallel conversation
- **GIVEN** a paired direct chat whose conversation is mid-task
- **WHEN** the owner sends `/thread deploy check`
- **THEN** a thread marked `🧵#1 deploy check` appears in the chat
- **AND** a message in that thread runs in a new conversation titled `🧵#1 deploy check`, while the direct chat's own conversation is untouched

#### Scenario: /status in a direct chat lists its parallel threads
- **GIVEN** a direct chat with two parallel threads, one of them running a turn
- **WHEN** the owner sends `/status` in the direct chat
- **THEN** the answer says there are two parallel threads and lists both marks, each with its agent and its state

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
agent.

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

### Requirement: Keep a chat's settings across its conversations
A chat thread MUST remember its settings — the agent, the model, the reasoning
effort and the working directory — and a fresh conversation opened there, by
`/new`, by a deleted conversation being replaced, or by `/dir`, MUST open with
them. What the thread has not set falls back, in a group thread, to the group's
defaults (see "Set a group's defaults from its main chat"), and then to the
channel's own default agent and agent configuration. `/model default` and `/dir
default` are the ways back to the defaults.

#### Scenario: /new keeps the chat's model, effort and directory
- **GIVEN** a paired chat whose owner set a model, an effort and an allowed
  directory from chat
- **WHEN** the owner sends `/new`
- **THEN** the fresh conversation runs on the same agent, model, effort and
  directory

#### Scenario: a group thread inherits the group's defaults
- **GIVEN** a group whose defaults name a model
- **WHEN** the owner starts a new thread in that group
- **THEN** that thread's conversation opens on the group's model

### Requirement: Pass unreserved slash text to the agent
Only Coffer's nine commands (see "Answer the conversation commands from any
paired chat") MUST be taken out of the conversation. Any other text starting
with `/` — an agent's own command such as `/compact` or a skill invoked as
`/review`, or a message that opens with a path such as `/Users/me/app crashes` —
is an ordinary message and reaches the agent exactly like any other. A single
slash-word within one edit (for names of four letters or fewer) or two edits
(for longer names) of a Coffer command — a swap of two neighbouring letters
counting as one — is a slip, and is answered with one line, `Did you mean
/stop?`, and runs nothing. The commands this set replaced (`/agent`, `/effort`,
`/threads`, `/save`) are not reserved: `/threads` is a slip of `/thread`, and
the others reach the agent.

#### Scenario: an unreserved slash word reaches the agent
- **GIVEN** a paired channel
- **WHEN** the owner sends `/compact`
- **THEN** a turn runs with `/compact` in its text and no command answers

#### Scenario: a message starting with a path reaches the agent
- **GIVEN** a paired channel
- **WHEN** the owner sends `/Users/me/app crashes on start`
- **THEN** the message is answered by the agent as an ordinary message

#### Scenario: a near miss of a command is corrected, not sent
- **GIVEN** a paired channel
- **WHEN** the owner sends `/stpo`
- **THEN** the channel answers `Did you mean /stop?` and no turn runs

#### Scenario: a removed command reaches the agent as text
- **GIVEN** a paired channel
- **WHEN** the owner sends `/agent codex`
- **THEN** no agent is switched and the text reaches the agent as a message

### Requirement: Choose the working directory from chat
The owner MUST be able to move a chat's conversation to another working
directory from chat — but only to a directory the channel allows. A channel's
configuration carries `directories`, a list of absolute paths edited on the
Channels page and with `coffer channel add|edit --dir PATH` (repeatable; `edit
--no-dirs` clears it); each entry also admits the directories beneath it.
`/dir <path>` accepts an allowed path or one beneath it, `/dir <name>` the base
name of exactly one allowed path; either must be an existing directory. Because
an agent's session is tied to its directory, setting one opens a fresh
conversation there and remembers the directory for the chat; the previous
conversation stays one `/resume` away. `/dir default` returns to the channel's
default directory. `/dir` with no argument reports the directory in effect and,
where the transport has buttons, offers the allowed ones as a card. A channel
that allows no directory says how to add one; a directory outside the list is
refused with the allowed ones named.

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

### Requirement: Resume an earlier conversation from chat
Every conversation a chat thread opens MUST be remembered for that thread, and
the owner MUST be able to return to one from chat. `/resume` lists the thread's
recent conversations, newest first, each by title, agent and age, with the one
in effect ticked, as a card where the transport has buttons; `/resume <n>` or a
tap makes the n-th the thread's active conversation again, so the next message
continues it. Only conversations this chat thread opened are offered — never one
from the web or another chat, and a tapped value naming any other conversation
is refused. A conversation deleted since is left out.

#### Scenario: /resume lists this chat's earlier conversations
- **GIVEN** a paired chat that has opened two conversations with `/new`
- **WHEN** the owner sends `/resume`
- **THEN** both are listed by title, newest first, with the active one ticked

#### Scenario: /resume n reopens that conversation
- **GIVEN** a paired chat with an earlier conversation listed second by `/resume`
- **WHEN** the owner sends `/resume 2` and then a message
- **THEN** the message continues that earlier conversation

#### Scenario: /resume never offers another chat's conversation
- **GIVEN** two paired chats of one channel, each with its own conversations
- **WHEN** the owner sends `/resume` in one of them, or taps a resume value
  naming the other chat's conversation
- **THEN** only that chat's own conversations are offered, and the foreign one is
  refused

### Requirement: Report the chat's state as a status card
`/status` MUST answer what the chat is running in words a person reads: the
conversation's title (or its parallel mark), the agent by its display name, the
model by the name its button shows, the effort, the working directory, and
whether a turn is running or how many messages wait; in a direct chat, the
parallel threads too (see "Open parallel conversations beside a direct chat"). It
shows no conversation or agent ids. Where the transport has buttons it is a card
whose buttons — Stop, New, Model, Resume, Dir — run those commands, so a user
who remembers one word reaches every action by tapping; elsewhere it is text.
In a group where the answer can be delivered to the asker alone (see "Keep
non-answer chatter private in a group") it is sent that way, as text: a card is
always an ordinary message the whole room would see. The same holds for the
help card.

#### Scenario: /status shows names, not ids, with action buttons
- **GIVEN** a paired chat on a button-capable transport with an active
  conversation
- **WHEN** the owner sends `/status`
- **THEN** a card names the conversation, the agent by display name, the model,
  the effort and the directory, carries the Stop, New, Model, Resume and Dir
  buttons, and contains no conversation id

### Requirement: Offer the commands as a help card
`/help` MUST list the commands from the roster, saying that anything else goes
to the agent; where the transport has buttons it is a card carrying the same
five buttons as the status card. The same help follows a successful pairing
once, so a platform with no command menu (SeaTalk) still shows a new owner what
the bot accepts.

#### Scenario: /help is a card with the five actions
- **GIVEN** a paired chat on a button-capable transport
- **WHEN** the owner sends `/help`
- **THEN** a card lists the commands and carries the Status, New, Model, Resume
  and Dir actions as buttons

#### Scenario: the help card follows pairing
- **GIVEN** an unpaired channel with an issued pairing code
- **WHEN** the owner pairs by sending the code
- **THEN** the pairing is confirmed and the help follows it once

### Requirement: Set a group's defaults from its main chat
On a platform where every @mention in a group's main chat roots a fresh thread
(SeaTalk), a command sent in the main chat MUST configure the group rather than
that one-message thread: `/new <agent>`, `/model …` and `/dir …` set the group's
defaults, which every new thread of the group inherits (see "Keep a chat's
settings across its conversations"), and the answer says so; `/status` there
reports the group's defaults and its running threads; `/resume` points to
replying inside a thread; and `/stop` interrupts every turn running in that
group and lists what it stopped. A thread's own settings still win inside it.
Where a group's main chat is itself one conversation (a Telegram group without
topics) nothing changes: commands apply to that conversation.

#### Scenario: a setting sent in a SeaTalk group's main chat becomes the default for new threads
- **GIVEN** a paired SeaTalk group
- **WHEN** the owner sends `@bot /model <name>` in the group's main chat, and
  later @mentions the bot with a question in the main chat
- **THEN** the first answer says the model is the default for new threads, and
  the question's thread runs on that model

#### Scenario: /stop in a SeaTalk group's main chat stops every turn in the group
- **GIVEN** a paired SeaTalk group with turns running in two of its threads
- **WHEN** the owner sends `@bot /stop` in the group's main chat
- **THEN** both turns are interrupted and the answer lists both

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
`chat` — the one the web shows; the channel refuses past 10 waiting and tells
the peer the channel is busy) and run in order, a burst of them arriving as one
turn (see "Take a burst of messages as one turn"). A message arriving exactly
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
- **GIVEN** a full message queue
- **WHEN** the peer sends another message
- **THEN** the message is dropped and the peer is told the channel is busy

### Requirement: Switch the model and reasoning effort from chat
The owner MUST be able to choose the model and its reasoning effort from chat
with one command, `/model`, because both managed agents present the two as one
choice. The choice applies to the next turn of the same conversation (the model
and effort are re-read each turn, unlike the agent and working directory) and is
remembered for the chat (see "Keep a chat's settings across its conversations").

- `/model <name>` sets the model. The name is matched against the agent's model
  catalogue by id or by the name its button shows, case-insensitively; a name
  the catalogue does not list is passed through verbatim, because the model
  namespace belongs to the agent's CLI and not to Coffer — a name that agent
  cannot run surfaces as the CLI's own error on the next turn.
- `/model <level>` — a word of the closed effort vocabulary `minimal`, `low`,
  `medium`, `high`, `xhigh`, `max`, which no model name uses — sets the effort
  alone. `/model <name> <level>` sets both.
- `/model default` clears both, returning the conversation and the chat to the
  agent's own defaults.
- `/model` with no argument reports the model and effort in effect and, on a
  transport that `supports_buttons` (see "Offer choices and actions as
  owner-gated cards"), renders a two-step card. The **model step** offers the
  agent's catalogue — read back from the installed CLI, the one list Coffer has
  of what that agent can run — in **full**, one page at a time, opening on the
  page holding the model in effect. Each button shows the model's **name**, not
  its raw id, and the tap still carries the id: a model with no name shows its
  id, and a 1M-context variant says "1M", so `fable` and `claude-fable-5-1[1m]`
  read as two different choices. Tapping a model sets it; when that model
  reports reasoning levels the same card is rewritten into the **effort step**
  — the levels of the model now in effect plus a button that keeps the current
  effort — and tapping a level sets it. A model with no levels ends the choice
  at the model step. Where the card cannot be rewritten in place the effort step
  arrives as a fresh card. With no catalogue it falls back to the text report.

#### Scenario: /model switches the model for the next turn
- **GIVEN** a paired channel in an active conversation
- **WHEN** the peer sends `/model <name>` and then a message
- **THEN** the next turn runs with the chosen model in the same conversation

#### Scenario: a model card button shows the model's name
- **GIVEN** an agent whose catalogue offers `fable`, named "Fable 5.1", and
  `claude-fable-5-1[1m]`, named "Fable"
- **WHEN** the `/model` card is built
- **THEN** the buttons read "Fable 5.1" and "Fable 1M"
- **AND** tapping either carries its model id

#### Scenario: /model with a level sets the effort only
- **GIVEN** a paired channel whose conversation runs a pinned model
- **WHEN** the peer sends `/model high`
- **THEN** the next turn runs at effort `high` on the same model

#### Scenario: /model default clears the model and effort
- **GIVEN** a conversation with a model and an effort set from chat
- **WHEN** the peer sends `/model default`
- **THEN** the conversation and the chat carry neither, so the agent's own
  defaults apply from the next turn and in the next conversation

#### Scenario: a model tap leads to the effort step
- **GIVEN** a `/model` card on a transport that can rewrite a card, for an agent
  whose models report reasoning levels
- **WHEN** the owner taps a model
- **THEN** the model is set and the same card now offers that model's levels
- **AND** tapping a level sets the effort for the next turn

### Requirement: Save a sent document into a collection
A document sent to a Coffer channel MUST be ingestible into a collection through
the same conversion path the Knowledge page uses, so the phone and that page are
two ends of one entrance (spec `knowledge`). `/kb` is the command that does it.
The channel MUST confirm the collection with the owner before storing, and MUST
NOT store anything from a non-owner. `/kb` is offered — in `/help` and in every
registered menu — only while the knowledge feature is on; while it is off the
word is still Coffer's and answers that knowledge is off.

#### Scenario: a document sent to a channel is saved into a collection
- **GIVEN** a paired owner who has sent a document to the channel,
- **WHEN** the owner follows it with `/kb <collection>` naming a collection
  that exists,
- **THEN** the document is ingested into that collection through the same
  conversion path the Knowledge page uses,
- **AND** a `/kb` from anyone but the paired owner stores nothing.

#### Scenario: a save that names no collection asks which one
- **GIVEN** a paired owner who has sent a document but named no collection,
- **WHEN** they send `/kb`,
- **THEN** the channel offers the collections it may save into and stores
  nothing until one is chosen — on a transport without buttons it lists them as
  text,
- **AND** a `/kb` with no document pending is refused in one line.

#### Scenario: /kb is offered only while knowledge is on
- **GIVEN** a paired channel
- **WHEN** the knowledge feature is switched off and the owner sends `/help`
- **THEN** the help lists every command but `/kb`, and `/kb` answers that
  knowledge is off without saving anything

### Requirement: Keep non-answer chatter private in a group
Chatter that is not the answer MUST stay private in a group. Command output and
errors are addressed to one member, not to the room, wherever the platform can
deliver a message only that member's client shows; the agent's actual reply is
always an ordinary message the group can see. This is the group-noise half of
"Act in a group only on an addressed message from the owner": that requirement
stops the bot from *acting* on everything, this one stops it from *saying*
everything out loud. Every command declares which side of that line it falls on,
on the same roster "Register the bot's command menu and profile from one roster"
registers the menu from: `/new`, `/stop` and `/thread` change or point at state
the whole room shares and stay visible, and so does `/kb`, whose outcome is a
file the room's other members can be expected to want to know about; the ones
that answer only the asker — `/model`, `/dir`, `/status`, `/resume`, `/help` —
are delivered privately where the transport can. A roster entry that declares
nothing is **visible**, so privacy is something a command opts into rather than
something it acquires by omission; a "Did you mean" correction (see "Pass
unreserved slash text to the agent") is answered privately, because a correction
is the least useful thing to broadcast.

**Selection cards are deliberately excluded.** A card is the one surface that
must be *rewritten* after it is used (see "Offer choices and actions as owner-gated cards"), and a privately-delivered message is rewritten through a
different address space whose delivery the platform does not guarantee. A card
that cannot be reliably rewritten keeps offering the option already taken, which
is precisely what the rewrite exists to prevent, so a card stays an ordinary
message until the rewrite is as reliable as the send. Worth revisiting only if a
platform makes that edit as reliable as an ordinary one.

#### Scenario: a group command answer is shown only to the asker
- **GIVEN** a paired group on a transport that can deliver a message only one member sees
- **WHEN** the owner sends `/help` in that group, and then `/new`
- **THEN** the `/help` answer is delivered privately to the owner
- **AND** the `/new` confirmation is an ordinary message the group can see

### Requirement: Register the bot's command menu and profile from one roster
The bot MUST introduce itself. Its command menus are registered with the
platform from Coffer's own command roster, and its prose profile (description,
short description) is **filled in when empty**, so a user opening the bot for
the first time sees what it is and what it accepts instead of an empty chat. The
registered menus MUST list the commands the channel actually handles — a command
the help text offers but the private-chat menu omits is a drift bug, not a
design choice. This is enforced structurally rather than by review: the menus,
the help text, the typo guard (see "Pass unreserved slash text to the agent")
and the per-command privacy flag (see "Keep non-answer chatter private in a
group") are all rendered from one roster, so adding a command is one entry plus
its handler, with no second list to forget. Each entry carries its description
in English and Chinese, whether it belongs in a group's menu, and whether it
needs the knowledge feature. A platform with no menu API (SeaTalk) introduces
the commands through the help card instead (see "Offer the commands as a help
card"). Copy the owner already wrote, and the bot's name, are their branding
decision and MUST NOT be overwritten.

#### Scenario: the command menu matches the commands that exist
- **GIVEN** the channel command roster, with knowledge on,
- **WHEN** the transport registers its private-chat command menu,
- **THEN** every command the channel handles is registered.

### Requirement: Route the owner's messages into a turn-platform conversation
Inbound text from the paired peer MUST route to the peer's active conversation,
creating one on first use via the turn platform's standard
conversation-creation path (default agent validated by the agent registry). The
channel layer MUST reach agents only through the turn platform's seams:
conversation service, turn orchestrator (spec `chat`). The conversation is an
ordinary one, recorded in the vault with full history. When the active
conversation has been deleted, the peer's next message creates a fresh
conversation with the thread's agent — its sticky agent (chosen with `/new <agent>`, see "Switch the agent with /new") while that
agent is still inside the channel's scope, else the channel's default agent — opened with the thread's other remembered settings (see "Keep a chat's settings across its conversations"); when the daemon restarts mid-turn, the turn
platform's startup sweep marks the orphaned turn failed and the channel
conversation simply continues on the next message.

#### Scenario: a paired message gets an agent reply
- **GIVEN** a paired channel whose default agent is available
- **WHEN** the peer sends a text message
- **THEN** a turn runs in the peer's conversation and the reply is delivered
  to the IM chat

#### Scenario: the channel conversation is a normal chat conversation
- **GIVEN** a channel conversation created by first contact
- **WHEN** the user opens the turn platform's conversation APIs
- **THEN** the conversation and its messages are listed like any other

### Requirement: Limit the agents a channel may drive to its scope
A channel MUST carry the framework's `scope`
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)),
one allow-list of agents, read as **the agents this channel may drive**. Every
other kind's scope names the agents a resource is *delivered to*; a channel is
consumed by no agent — it is an inbound surface — so the list is inverted rather
than borrowed, and the spec says so explicitly because a reader who assumes the
usual reading gets it backwards. That inverted reading is the whole of what a
channel's scope says: there is nothing in it about WHICH MACHINE runs the
channel. That question has its own field, `runs_on` (see "Bind each channel to
the one machine that runs it"), for a reason scope cannot satisfy: scope is
reach, reach is machine-local and never travels, and the machine that runs a
channel is one answer the machines must share.

- An unrestricted scope MUST mean every registered agent. That is the pre-scope
  behaviour and what every existing channel carries, so no channel needs a data
  migration.
- `agents: [<agent>, …]` MUST narrow `/new <agent>` at every surface that
  names an agent: the list of valid names an unknown one is answered with, and
  the validation of a chosen name. They MUST read one narrowed set — a list that
  offers an agent the next check rejects is the specific failure this requires.
- **One vocabulary above the binding.** A scope and a `default_agent` both name
  agent **uids**, which is also what a reach picker offers, so every comparison
  between them is made directly and no translation exists to get backwards. A
  uid this vault does not hold admits no agent at all.
- **One crossing, below it.** `/new <agent>`, the sticky per-thread choice and the
  turn router all speak the agent **key** the turn platform routes on. That key
  MUST be derived from the uid at exactly ONE place — the runtime gate, where the
  resource row becomes a live binding — and nothing below that point may hold a
  uid. Two agent resources of the same type collapse to one key there. While the
  two vocabularies met in several places at once, each of them compared a scope
  written in one to a default written in the other: the only narrowing a user
  could express was refused, and the value accepted in its place was one the
  reach picker then had to render as an agent registered nowhere.
- **The invariant:** a channel's `default_agent` MUST be an agent the channel
  may drive — registered in this vault, and inside its scope whenever that scope
  is non-empty. It MUST be enforced on BOTH write paths, so the inconsistent
  state cannot be stored at all: a registration or an edit of the configuration
  is rejected when it names a `default_agent` that is unknown or outside the
  current scope, and an edit to the scope is rejected when the proposed
  non-empty scope excludes the current `default_agent`. A scope edit MUST NOT be
  accepted and then leave the channel unable to run. Each rejection MUST name
  both sides **by label**, not by uid, so the owner sees the two ways forward:
  widen the scope, or change the default agent first.
- **A channel that can route nowhere MUST NOT start.** Three states mean it: it
  names no `default_agent` at all, its scope excludes the one it names, or that
  uid names no agent registered here. In each the runtime declines to start the
  adapter and records why, and the management surface reports the channel as
  not running. There is NO fallback agent: `default_agent` is a reference to an
  agent resource and a uid is minted per vault, so nothing a schema could name
  would stand for "the usual agent". Silence with a reason beats a bot that
  answers as an agent nobody chose.
- `agents: []` (dormant) MUST mean the channel drives nothing, and MUST fail
  early rather than per-turn: the runtime does not start its adapter, so no
  message is ever accepted only to be refused. The management surface reports it
  as not running. Widening the scope is how the owner brings it back.
- `agents: []` MUST be accepted on both write paths. It is the vault-wide
  meaning of dormant — this channel is off — and off MUST NOT also mean frozen:
  a channel the owner deliberately switched off MUST remain editable, so a wrong
  bot token or app secret can still be corrected without reactivating it
  first.
- A thread's sticky agent choice MUST be dropped in favour of the channel
  default once the scope no longer admits it, so narrowing a scope takes effect
  on the next conversation rather than waiting on whoever set the preference.

Reach and the machine binding answer different questions and MUST never be
merged: reach (`enabled` + `scope`, on the resource row) says **which agents**
this channel may drive and whether it is live here, and is set per machine and
stays on it; the binding (`runs_on`, in the channel's config) says **which
machine** runs the adapter, and travels because it is one answer for the whole
vault. Giving the binding a home in `scope` would make "where does this apply"
carry two unrelated answers.

#### Scenario: a channel may only route to the agents in its scope
- **GIVEN** a paired channel whose scope names one of the two registered agents,
- **WHEN** the owner sends `/new nope`, and then `/new <the other one>`,
- **THEN** the list of valid names offers only the scoped agent, and the switch
  to the other one is refused.

#### Scenario: a channel's scope names agent resources, not agent keys
- **GIVEN** a running channel whose default agent is registered as an agent
  resource,
- **WHEN** the owner narrows the channel's scope to that agent resource — its
  uid, which is what the reach control offers,
- **THEN** the edit is accepted, the channel keeps running, and the scope
  reaches `/new <agent>` translated into the agent key that surface speaks.

#### Scenario: a channel scoped to no agent is dormant
- **GIVEN** an enabled channel whose scope is set to the empty list,
- **WHEN** the channel runtime reconciles,
- **THEN** its adapter is never started and the channel reports as not running,
  so it accepts no turn it would have to refuse.

#### Scenario: reject narrowing a channel's scope past its default agent
- **GIVEN** a running channel whose `default_agent` is one registered agent,
- **WHEN** the owner narrows its scope to a non-empty set that excludes that
  agent,
- **THEN** the edit is rejected with a message naming both the default agent and
  the proposed scope — by the labels the owner gave them, not by uid — nothing
  is persisted, and the channel keeps running: the narrowing never silently
  takes the bot offline.

#### Scenario: a channel bound to an agent that does not exist is refused
- **GIVEN** a vault with at least one registered agent,
- **WHEN** a channel is registered, or edited, with a `default_agent` naming no
  agent resource in this vault,
- **THEN** the write is rejected and no row is created or changed, rather than
  the channel being stored and failing at its first turn.

#### Scenario: a channel bound to no agent never starts
- **GIVEN** an enabled channel whose `default_agent` is unset, or names an agent
  this machine does not have,
- **WHEN** the channel runtime reconciles,
- **THEN** its adapter is never started, the reason is recorded, and the channel
  reports as not running — it is never started against a substitute agent.

#### Scenario: edit a dormant channel's configuration
- **GIVEN** a channel the owner switched off by scoping it to no agent,
- **WHEN** the owner corrects a field of its configuration, such as its bot
  token ref,
- **THEN** the edit is accepted and the channel stays dormant — off is not
  frozen.

### Requirement: Drive every managed agent from one bot
One bot MUST control all agents. A single paired Coffer-hosted bot drives any
managed agent, switchable with `/new <agent>`, so from one paired
chat the owner reaches every registered agent with a chosen model; agent choice
is per conversation, and since each thread is its own conversation (see "Key
conversation identity by channel, chat and thread") one bot can run different
agents in different threads concurrently. This is the capability no
agent-native or official channel offers, and the reason the channel plane
exists.

#### Scenario: one bot runs different agents in different threads
- **GIVEN** a paired channel and a group
- **WHEN** the owner switches thread A to a different agent with `/new <agent>` and leaves thread B
  on the channel default
- **THEN** thread A's conversation drives the switched agent and thread B's
  drives the default — one bot running different agents per thread

### Requirement: Open every turn with its message origin
Every turn MUST carry its own origin. The turn text opens with a
`[Message origin]` block naming the platform, the chat (kind, the chat title
where the platform supplies one, and always the chat id), the thread, and the
sender (display name **and** the stable platform id, which a platform tool call
takes and which, in a group, appears nowhere else because `chat_id` is the
group's) — so an agent asked "which group is this?" answers from the turn it was
given instead of listing the bot's groups and inferring, and a platform tool call
has a chat id to aim at. The block is folded in after command detection (a
prefixed `/help` would stop being a command) and after the empty-envelope check,
and is persisted on the user message exactly like thread context — the single
source of truth (see "Persist inbound attachments as references") stays one
string. It rides on **every** turn, not just a conversation's first: `/new <agent>`
can swap the agent between conversations of one thread (see "Drive every managed agent from one
bot") and a resumed session would otherwise lose it. Title and sender name are
chat-member-settable, so both are collapsed to one clipped line before they
reach the prompt — a rename cannot forge extra origin lines. Where a platform
hands the chat title over for free it is included; where it does not the chat is
named by id alone, which an agent can resolve to a name through the platform's
own tools.

#### Scenario: a group turn names the group it came from
- **GIVEN** a paired channel whose owner @mentions the bot in a group thread
- **WHEN** the turn is driven
- **THEN** the turn text opens with a `[Message origin]` block naming the platform,
  the chat kind and title, the chat id, the thread id, and the sender

#### Scenario: a DM turn names its own chat
- **GIVEN** a paired channel and a DM from its owner
- **WHEN** the turn is driven
- **THEN** the origin block names the platform and the direct chat by id, omitting
  the thread line a DM has no value for

#### Scenario: every turn carries its origin
- **GIVEN** a paired channel that has already run one turn
- **WHEN** the owner sends a second message
- **THEN** that turn's text opens with its own origin block too — the provenance is
  not a first-turn-only header

#### Scenario: a slash command keeps its leading slash
- **GIVEN** a paired channel
- **WHEN** the owner sends `/help`
- **THEN** it is handled as a command (no origin block is prefixed, no conversation
  is created)

### Requirement: Route group selection-card taps back to the group
Group selection-card taps MUST route to the group/thread. `InboundCallback`
carries `chat_kind`/`thread_id` and is owner-gated by the group's peer
(`get_by_chat`, not the single-peer `get`); a button tap's reply lands in the
same group/thread, not a DM.

#### Scenario: a group selection-card tap replies in the group/thread
- **GIVEN** a paired channel with a group peer, on a button-capable transport,
  whose agent offers a model catalogue
- **WHEN** the owner taps a `/model` selection-card button in a group thread
- **THEN** the model is applied to that group thread's conversation and the
  confirmation is routed back into the group/thread (never a DM); a non-owner's
  tap is refused with a routed "not authorized" reply and no switch

## REMOVED Requirements

### Requirement: Switch the conversation's agent from chat
**Reason**: `/agent` and `/new` were two commands for one action — choosing another agent always opened a fresh conversation. The switch is now `/new <agent>`.
**Migration**: Type `/new <agent name>`; see "Switch the agent with /new". The agent selection card is gone; the valid names are listed when an unknown one is typed.

### Requirement: Offer command choices as owner-gated selection cards
**Reason**: The cards now carry command buttons (`cmd:<name>`) beside choices, and the agent card they were specified around is gone with `/agent`.
**Migration**: Replaced by "Offer choices and actions as owner-gated cards", which keeps every rule of this one (owner gate, text fallback, in-place rewrite, pagination) and adds command buttons.

### Requirement: Open parallel conversations in a direct chat
**Reason**: `/threads` is removed; its listing moved into `/status`.
**Migration**: Replaced by "Open parallel conversations beside a direct chat"; send `/status` in the direct chat to list the parallel threads.
