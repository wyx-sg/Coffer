## REMOVED Requirements

### Requirement: Open a new conversation when the active one is archived
**Reason**: Conversations can no longer be archived: Coffer's own archive, unarchive and auto-archive are removed ([chat](../chat/spec.md) "Rename and delete a conversation through its agent"), so no active conversation can be archived under a chat.
**Migration**: None. A conversation the owner deletes — which now also deletes the agent's session — is still replaced by a fresh one on the chat's next message, as "Route the owner's messages into a turn-platform conversation" says.

### Requirement: Persist inbound attachments as references
**Reason**: Coffer no longer persists a user message, so an attachment reference is not recorded on one and is not re-read from history on a later turn. Two of the three other scenarios described that, and the third the message API.
**Migration**: See "Hand inbound attachments to the turn as references" ("an inbound attachment reaches the turn as a reference" replaces "an inbound attachment is persisted as a reference on the user message"; "the media dir prune deletes stale files and keeps fresh ones" is kept; "a later turn re-materialises the attachment from history" and "the message API exposes an attachment block without leaking the path" are dropped).

### Requirement: Ask the owner in the chat and take the answer back to the agent
**Reason**: A question can now only be answered in the chat, so the card is never rewritten to say it was answered in Coffer; the scenario "an answer given in Coffer rewrites the chat card" goes with the web answer.
**Migration**: See "Ask the owner in the chat and take the chat's answer back to the agent"; every other scenario is carried over unchanged.

## MODIFIED Requirements

### Requirement: Route the owner's messages into a turn-platform conversation
Inbound text from the paired peer MUST route to the peer's active conversation,
creating one on first use via the turn platform's standard
conversation-creation path (default agent validated by the agent registry). The
channel layer MUST reach agents only through the turn platform's seams:
conversation service, turn orchestrator (spec `chat`). The conversation is an ordinary one: an index row on the turn platform whose native session holds the history, and no message of it is stored by Coffer. When the active
conversation has been deleted, the peer's next message creates a fresh
conversation with the thread's agent — its sticky agent (chosen with `/new <agent>`, see "Switch the agent with /new") while that
agent is still inside the channel's scope, else the channel's default agent — opened with the thread's other remembered settings (see "Keep a chat's agent, model and directory across its conversations"); when the daemon restarts mid-turn, the orphaned turn is gone and the channel
conversation simply continues on the next message, resuming the agent's own session. A message for a session that is open in a terminal is
refused as [chat](../chat/spec.md) "Run a session in one place at a time" says.

#### Scenario: a paired message gets an agent reply
- **GIVEN** a paired channel whose default agent is available
- **WHEN** the peer sends a text message
- **THEN** a turn runs in the peer's conversation and the reply is delivered
  to the IM chat

#### Scenario: the channel conversation is a normal chat conversation
- **GIVEN** a channel conversation created by first contact
- **WHEN** the user opens the Conversations page
- **THEN** the conversation is listed there like any other, with the channel's badge, and no message text is stored

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
`chat`) and run in order, a burst of them arriving as one
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

### Requirement: List every Coffer-hosted channel on one management surface
Coffer-hosted channels MUST have a unified management surface. A management
view lists every Coffer-hosted channel with its status, paired owner, agent, and
health, mirroring the MCP-server / memory / skill management surfaces; each
channel's secrets (bot tokens, app secrets) are held in the Coffer vault.
The Channels page holds each channel's setup, connection status and settings only: it shows no conversation history, and each channel links to the Conversations page filtered to that channel (spec [chat](../chat/spec.md) "Show channel conversations on the Conversations page"). Externally-hosted channels are out of scope (a non-goal).

#### Scenario: the management surface lists each Coffer-hosted channel with status, owner, agent, and health
- **GIVEN** a registered and running Coffer-hosted channel with a paired owner
  and a routed agent
- **WHEN** the management surface reads the channel
- **THEN** it reports the channel's enabled status, its live health (adapter
  running), the paired owner, and the routed agent — mirroring the MCP-server /
  memory / skill management surfaces

#### Scenario: a channel links to its conversations instead of showing them
- **GIVEN** a SeaTalk channel with three conversations
- **WHEN** the user opens it on the Channels page
- **THEN** it shows its setup, connection status and settings and no conversation list, and its link opens the Conversations page filtered to that channel

### Requirement: Audit the events that grant the right to drive turns
Channel events MUST be audited where an event grants or moves the right to
drive turns: a pairing code issued, and a sender claiming it, each queryable in
the audit log by channel — the claim with the claiming sender's id. Those two are the whole
channel-specific audit surface, alongside the automatic resource-lifecycle audit
the framework records. Traffic MUST NOT be audited — a notification sent and a
turn run are neither irreversible nor invisible afterwards, and the conversation
(listed on the Conversations page, spec `chat`) and the agent's own session are
already their record.

#### Scenario: notifications and turns leave no channel audit entry
- **GIVEN** a paired channel whose pairing code issue and claim are in the audit log
- **WHEN** a notification is sent to the owner and the owner's message drives a turn
- **THEN** the audit log gains no entry for the notification or the turn
- **AND** the two pairing entries are still the only channel-specific entries for that channel

### Requirement: Hand inbound photos and files to the agent
Inbound photos and files MUST drive a turn. The transport downloads each
attachment to a Coffer-managed media dir; the bytes never enter the chat DB (Coffer stores
no message at all; the agent's own session keeps the caption).
For the turn, each attachment is handed to the agent adapter, which materialises
it in its own native shape — a vision agent (Claude Code) inlines an image as a
base64 content block it sees directly and a PDF as a document block; a
path-native agent (Codex) and any non-vision file receive the on-disk path to
open. This works for arbitrary file types, and generalises
to future modalities (a new type is a new mime, not a new schema). A sticker is
a picture the user chose deliberately, so it is downloaded like any other
attachment. Only a message with no text and nothing downloadable at all — a
location, a contact card — gets the reply that the channel needs text, a photo,
or a file. See [Channel Attachments](../../../docs/decisions/channel-attachments.md).

#### Scenario: an inbound photo is downloaded and drives a turn
- **GIVEN** a paired Telegram channel
- **WHEN** the owner sends a photo (with an optional caption)
- **THEN** the largest photo size is downloaded to the media dir and carried on
  the inbound message as an attachment, and the caption becomes the message text

#### Scenario: an inbound image reaches a vision agent as an inline block
- **GIVEN** a turn carrying an image attachment
- **WHEN** the Claude adapter builds the turn's content
- **THEN** the image is a base64 `image` content block (a non-vision file becomes
  a path pointer instead), so the bytes are sent inline for this turn only and
  never stored in the chat database

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
and is folded into the turn's text exactly like thread context, so it stays one
string and the agent's own session records it. It rides on **every** turn, not just a conversation's first: `/new <agent>`
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

### Requirement: Resume an earlier conversation from chat
Every conversation a chat thread opens MUST be remembered for that thread, and
the owner MUST be able to return to one from chat. `/resume` lists the thread's
recent conversations, newest first, each by title, agent and age, with the one
in effect ticked, as a card where the transport has buttons; `/resume <n>` or a
tap makes the n-th the thread's active conversation again, so the next message
continues it. Only conversations this chat thread opened are offered — never one
from another chat, and a tapped value naming any other conversation
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
- **THEN** it asks for the outcome in one first sentence, long content under
  `## Details`, diagrams as PNG files, and a `coffer__ask` call when the agent
  needs the owner's answer

## ADDED Requirements

### Requirement: Hand inbound attachments to the turn as references
An inbound attachment MUST reach the turn that carries it as a **reference** —
path, mime, filename; the bytes stay in the media dir, never the chat DB. The
reference rides the queued message to its turn, and the adapter receives it as an
`Attachment` ([chat](../chat/spec.md) "Let the agent's own session hold the conversation");
Coffer stores no message, so a later turn is not handed it again — the agent's own
session holds what the agent made of it. The path stays inside the daemon: only
the agent adapter, which must read the bytes, ever sees it. The media dir is
bounded by the `attachments` retention policy
([resource-framework](../resource-framework/spec.md) "Retain attachments on an adjustable policy"):
an mtime prune on the retention cadence, 30 days by default and the user's to change (bytes are re-downloadable; no
size cap). See
[Channel Attachments](../../../docs/decisions/channel-attachments.md).

#### Scenario: an inbound attachment reaches the turn as a reference
- **GIVEN** a paired channel driving a turn with an image attachment
- **WHEN** the turn starts
- **THEN** the adapter receives an `Attachment` with the path, mime and filename — never the bytes on the wire
- **AND** no message row records it

#### Scenario: the media dir prune deletes stale files and keeps fresh ones
- **GIVEN** the channel-media dir with one file older than the attachments window (30 days by default) and one recent
- **WHEN** the retention sweep runs
- **THEN** the stale file is deleted and the recent one is kept

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
cannot rewrite it, that line is sent as a reply. A long turn that is waiting on a
question pings "❓ Needs you · <elapsed> — <question>" on a surface that pings.

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

#### Scenario: a long turn that waits on the owner pings
- **GIVEN** a long turn on a persisting surface
- **WHEN** it raises a question
- **THEN** a short message reads "❓ Needs you · <elapsed> — <question>" before the card
