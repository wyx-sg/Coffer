## ADDED Requirements

### Requirement: Switch the model from chat
The owner MUST be able to choose the model from chat with one command, `/model`.
The choice applies to the next turn of the same conversation (the model is
re-read each turn, unlike the agent and working directory) and is remembered for
the chat (see "Keep a chat's agent, model and directory across its conversations").

- `/model <name>` sets the model. The name is matched against the agent's model
  catalogue by id or by the name its button shows, case-insensitively; a name
  the catalogue does not list is passed through verbatim, because the model
  namespace belongs to the agent's CLI and not to Coffer — a name that agent
  cannot run surfaces as the CLI's own error on the next turn. Whatever word
  follows `/model` is treated as a model name, `high` or `max` included; Coffer
  reserves no word but `default`, and it has no reasoning-effort setting.
- `/model default` clears the model, returning the conversation and the chat to
  the agent's own default.
- `/model` with no argument reports the model in effect and, on a
  transport that `supports_buttons` (see "Offer choices and actions as
  owner-gated cards"), renders a card that offers the
  agent's catalogue — read back from the installed CLI, the one list Coffer has
  of what that agent can run — in **full**, one page at a time, opening on the
  page holding the model in effect. Each button shows the model's **name**, not
  its raw id, and the tap still carries the id: a model with no name shows its
  id, and a 1M-context variant says "1M", so `fable` and `claude-fable-5-1[1m]`
  read as two different choices. Tapping a model sets it,
  answered "Model: <model> — from your next message". With no catalogue it falls back to the text report.

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



#### Scenario: /model default clears the model
- **GIVEN** a conversation with a model set from chat
- **WHEN** the peer sends `/model default`
- **THEN** the conversation and the chat carry no model, so the agent's own
  default applies from the next turn and in the next conversation

### Requirement: Keep a chat's agent, model and directory across its conversations
A chat thread MUST remember its settings — the agent, the model and the working directory — and a fresh conversation opened there, by
`/new`, by a deleted conversation being replaced, or by `/dir`, MUST open with
them. What the thread has not set falls back, in a group thread, to the group's
defaults (see "Set a group's defaults from its main chat"), and then to the
channel's own default agent and agent configuration. `/model default` and `/dir
default` are the ways back to the defaults.

#### Scenario: /new keeps the chat's model and directory
- **GIVEN** a paired chat whose owner set a model and an allowed
  directory from chat
- **WHEN** the owner sends `/new`
- **THEN** the fresh conversation runs on the same agent, model and
  directory

#### Scenario: a group thread inherits the group's defaults
- **GIVEN** a group whose defaults name an agent
- **WHEN** the owner starts a new thread in that group
- **THEN** that thread's conversation opens on the group's agent

## MODIFIED Requirements

### Requirement: Route the owner's messages into a turn-platform conversation
Inbound text from the paired peer MUST route to the peer's active conversation,
creating one on first use via the turn platform's standard
conversation-creation path (default agent validated by the agent registry). The
channel layer MUST reach agents only through the turn platform's seams:
conversation service, turn orchestrator (spec `chat`). The conversation is an
ordinary one, recorded in the vault with full history. When the active
conversation has been deleted, the peer's next message creates a fresh
conversation with the thread's agent — its sticky agent (chosen with `/new <agent>`, see "Switch the agent with /new") while that
agent is still inside the channel's scope, else the channel's default agent — opened with the thread's other remembered settings (see "Keep a chat's agent, model and directory across its conversations"); when the daemon restarts mid-turn, the turn
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

### Requirement: Answer the conversation commands from any paired chat
Nine words are Coffer's commands in a paired chat, and nothing else: `/new`,
`/stop`, `/model`, `/dir`, `/status`, `/resume`, `/thread`, `/del` and `/help`
(`/start` is a hidden alias of `/help`). They are split by chat type. In a
**direct chat** all nine work. In a **group** only `/new`, `/stop`, `/del` and
`/help` work — they
control the group's own conversation — and `/model`, `/dir`, `/status`,
`/resume` and `/thread` work only in a direct chat: sent in a group by the owner
(see "Act in a group only on an addressed message from the owner"), one of
those five is answered with one line in English and Chinese saying it works in a
private chat with the bot, delivered privately to the sender where the platform
can (see "Keep non-answer chatter private in a group"), and does nothing else —
it is not passed to the agent as a message. A group's `/help` lists only the
four group commands, and a card offered in a group (the `/new` card, the help
card) carries no button for a direct-chat command.
`/new [agent]` starts a fresh conversation with the chat's settings (see "Keep a chat's agent, model and directory across its conversations" and "Switch the agent with /new"),
`/stop` interrupts the running turn, `/status` reports the chat's state (see
"Report the chat's state as a status card") and `/help` lists the commands (see
"Offer the commands as a help card") and `/del` withdraws a bot reply (see
"Withdraw a bot reply on the owner's command"). `/stop` and `/new` take effect even while
a turn is running; other messages join the conversation's pending queue (spec
`chat` — the one the web shows) and run in order, a burst of them arriving as one
turn (see "Take a burst of messages as one turn"). A message that joins the
queue behind a running turn MUST be answered "⏳ Queued — runs when the current
one finishes." Up to 10 may wait; only a message arriving while 10 already wait
is dropped, and the chat MUST be told it was dropped and why (the only place the
limit is mentioned).
`/new` MUST answer with a one-line card — "🆕 New conversation · <agent> ·
<model> · <directory>" — carrying Agent, Model and Dir buttons in a direct chat
and the Agent button alone in a group: Agent opens the agent card (see "Switch
the agent with /new"), Model and Dir run `/model` and `/dir`; a transport
without buttons gets the same line as text. A message arriving exactly
when the previous turn finishes joins the queue rather than racing it: turns for
one conversation never overlap.

The commands that configure the conversation the chat is bound to are specified
in their own requirements — `/model` in "Switch the model from chat", `/dir` in "Choose the working directory from chat", `/resume` in
"Resume an earlier conversation from chat", and `/thread` in "Open parallel conversations beside a direct chat".
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
- **AND** where the platform can edit a message, "⏹ Stopping…" is edited into "⏹ Stopped after 12s." (the turn's real duration) instead of a second message being sent

#### Scenario: messages during a turn are queued in order
- **GIVEN** a turn in progress
- **WHEN** the peer sends two more messages further apart than the quiet window
- **THEN** they run as consecutive turns in arrival order after the first ends

#### Scenario: the queue is bounded and overflow is reported
- **GIVEN** a turn in progress
- **WHEN** the peer sends ten more messages, each after the quiet window of the one before has closed (so none merges into another), and then an eleventh
- **THEN** each of the ten is answered "⏳ Queued — runs when the current one finishes.", and all ten run in order
- **AND** the eleventh is dropped and the peer is told that ten were already waiting

#### Scenario: a direct-chat command in a group is declined with one line
- **GIVEN** a paired group where the owner is addressed
- **WHEN** the owner sends `/model`, `/dir`, `/status`, `/resume` or `/thread`
- **THEN** the sender alone is told, in one line, that the command works in a private chat with the bot
- **AND** no setting changes, no thread opens, and nothing reaches the agent as a message

#### Scenario: a group's help lists only the group commands
- **GIVEN** a paired group and a paired direct chat
- **WHEN** the owner sends `/help` in each
- **THEN** the group's answer lists `/new`, `/stop`, `/del` and `/help` only, with New and Stop as its buttons
- **AND** the direct chat's answer lists all nine commands

#### Scenario: /new answers with a one-line card
- **GIVEN** a paired chat on a button-capable transport with two agents the channel may drive
- **WHEN** the owner sends `/new`, taps Agent, and taps the second agent
- **THEN** the first answer is one line naming the agent, the model and the directory, with Agent, Model and Dir buttons
- **AND** Agent offers the channel's agents with the current one ticked, and the tap starts a fresh conversation on the second agent

### Requirement: Gate inbound traffic on sender identity
The owner gate MUST verify sender identity, not only chat identity. Every
inbound envelope carries a `sender_id`, whose platform meaning each child spec
names; pairing records it on the peer, and an inbound message is accepted only
when its `chat_id` matches and its sender matches the peer's stored
`sender_id`. A message that names no sender is refused, in a direct chat as in a
group: ownership that cannot be proven is not ownership. Pairing refuses the
same way — a code sent in a message that names no sender binds nobody and burns
no attempt.

The peer is a `ChannelPeer`: `(resource, chat_id)`, display name, paired-at and
the paired sender's identity (`sender_id`) — one row per (channel, chat): the
paired owner plus one row per group the owner has addressed the bot in. The
conversation a chat is in the middle of, and its sticky preferences (the chosen
agent, model and directory), are not on the peer: they live in the
thread conversation rows keyed by (channel, chat, thread).

The core never sees platform payloads: every adapter produces and consumes
the normalized `InboundMessage`, `InboundCallback` and `OutboundMessage`
envelopes, and inbound carries the sender's identity for this gate.

#### Scenario: a group member who is not the paired sender is ignored
- **GIVEN** a peer paired with a stored sender identity
- **WHEN** a message arrives with the same chat id but a different sender id
- **THEN** no reply is sent and no turn is started

#### Scenario: a direct message that names no sender is ignored
- **GIVEN** a paired channel
- **WHEN** a message arrives in the owner's chat but the transport supplied no sender id
- **THEN** no reply is sent and no turn is started

#### Scenario: a pairing code sent with no sender binds nobody
- **GIVEN** a channel with a pending pairing code
- **WHEN** the right code arrives in a message that names no sender
- **THEN** nobody is paired and the code is still valid

#### Scenario: ignore messages from strangers
- **GIVEN** a paired channel
- **WHEN** a different account messages the bot
- **THEN** no reply is sent and no turn or conversation is created

### Requirement: Open a new conversation after an idle period
A channel MUST open a new conversation when the owner's next message reaches a
chat whose active conversation has been idle longer than the channel's
`new_conversation_after_idle_hours` (default 24, from 0 to 8760; 0 never does).
Idle time is measured from the conversation's last activity, in hours. It
applies to every conversation a channel keeps, per key: a direct chat's
conversation and each group thread's or parallel thread's own (see "Key
conversation identity by channel, chat and thread"). The old conversation stays
where it was, in the conversation list; the chat is told in one short line,
`🆕 Started a new conversation after 24 h idle.`, before the answer. The new
conversation opens exactly as `/new` opens one, so the chat's sticky agent,
model and directory carry over (see "Keep a chat's agent, model and directory across its conversations").

The setting is edited on the Channels page, on the channel's Settings tab, and
the channel's status reports it.

#### Scenario: a chat idle past the configured hours opens a new conversation
- **GIVEN** a paired chat whose active conversation was last active 25 hours ago, on a channel with the default 24
- **WHEN** the owner sends a message
- **THEN** a new conversation becomes the chat's active one and answers the message
- **AND** the chat is told `Started a new conversation after 24 h idle`
- **AND** the old conversation is still in the conversation list

#### Scenario: a chat active within the idle period keeps its conversation
- **GIVEN** a paired chat whose active conversation was last active 23 hours ago
- **WHEN** the owner sends a message
- **THEN** the message joins that conversation and nothing is announced

#### Scenario: zero idle hours never opens a new conversation
- **GIVEN** a channel whose `new_conversation_after_idle_hours` is 0 and a conversation idle for 90 days
- **WHEN** the owner sends a message
- **THEN** the message joins that conversation

#### Scenario: the idle period applies to each group thread's conversation
- **GIVEN** two threads of one group, each with its own conversation, one idle past the period and one not
- **WHEN** the owner messages both threads
- **THEN** only the idle thread opens a new conversation

#### Scenario: the idle period comes from the channel's settings
- **WHEN** a channel config omits `new_conversation_after_idle_hours`, sets it to 0, or sets it below 0 or above 8760
- **THEN** it is 24, it is 0 (never), and it is refused
- **AND** the owner can set it to 6 on the channel's Settings tab, and a value outside the range is refused

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

Two kinds of button exist. A **choice** carries `model:`, `dir:`,
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
uses. One rule serves every card — a handful of models or directories render
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
A model chosen for the previous agent does not follow it to a different
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
with the agent by its display name, the model by the name its button shows, and the working directory (under the home directory as
`~/…`); then "Running", "Running · n waiting", "n waiting" or "Idle"; in a
direct chat, one "Parallel threads (n):" line naming each with its agent and its state (see "Open
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
- **THEN** a card titled "Status" names the conversation, the agent by display name, the model
  and the directory, carries the New, Model, Resume and Dir buttons —
  and Stop too while a turn runs — and contains no conversation id

### Requirement: Set a group's defaults from its main chat
On a platform where every @mention in a group's main chat roots a fresh thread
(SeaTalk), a command sent in the main chat MUST configure the group rather than
that one-message thread: `/new <agent>` sets the group's default agent, which
every new thread of the group inherits (see "Keep a chat's agent, model and directory across its conversations"), and the answer says so, while bare `/new` says what the
defaults are; and `/stop` interrupts every turn running in that group and lists
what it stopped. A thread's own settings still win inside it. `/model`, `/dir`,
`/status` and `/resume` are direct-chat commands and set nothing here (see
"Answer the conversation commands from any paired chat"). Where a group's main
chat is itself one conversation (a Telegram group without topics) nothing
changes: commands apply to that conversation.

#### Scenario: an agent sent in a SeaTalk group's main chat becomes the default for new threads
- **GIVEN** a paired SeaTalk group
- **WHEN** the owner sends `@bot /new <agent>` in the group's main chat, and
  later @mentions the bot with a question in the main chat
- **THEN** the first answer says the agent is the default for new threads, and
  the question's thread runs on that agent

#### Scenario: /stop in a SeaTalk group's main chat stops every turn in the group
- **GIVEN** a paired SeaTalk group with turns running in two of its threads
- **WHEN** the owner sends `@bot /stop` in the group's main chat
- **THEN** both turns are interrupted and the answer lists both

## REMOVED Requirements

### Requirement: Switch the model and reasoning effort from chat
**Reason**: Renamed: `/model` no longer sets a reasoning effort, and two of its scenarios are gone.
**Migration**: Read "Switch the model from chat"; `/model <word>` now treats the word as a model name.

### Requirement: Keep a chat's settings across its conversations
**Reason**: Renamed: a chat thread no longer remembers a reasoning effort.
**Migration**: Read "Keep a chat's agent, model and directory across its conversations".

