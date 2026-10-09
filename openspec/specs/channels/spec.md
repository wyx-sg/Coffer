# Channels

## Purpose
Channels let the owner talk to any agent on Coffer's turn platform from the IM
apps they already use — Telegram and SeaTalk first — and receive notifications
Coffer pushes. A channel is a registered resource of kind `channel` that
connects one IM account to the turn platform (spec `chat`): messages from the
paired owner become turns in an ordinary conversation, and the agent's reply
goes back to the IM chat. The channel layer and the agent layer meet only at the
turn platform's existing seams — conversation creation and the turn event
stream — so the cost of N channels and M agents is N + M, never N × M: a new
channel type is one adapter plus one config schema and touches no agent or
conversation code, and any agent registered on the turn platform is reachable
from any channel with no channel-side change. The turn platform — conversations,
the pending queue, the turn lifecycle and the Conversations page onto them — is spec
`chat`; a channel consumes it and never reimplements it.

This spec owns what every channel type shares. The per-platform mechanics live
in its two children: [`channels/telegram`](telegram/spec.md) (the Bot API
transport) and [`channels/seatalk`](seatalk/spec.md) (the SeaTalk websocket
transport and SeaTalk's own message shapes). Watching and steering the same
conversation from the browser is the Conversations page's, in spec `chat`. Channels
route to **managed** agents (Claude Code, Codex, …) only: Coffer has no chat
persona of its own ([Chat Is a Single-Owner Live Mirror](../../../docs/decisions/chat-single-owner-live-mirror.md)), so
there is no built-in agent to target. There is no tool-approval flow on a channel
([Managed Agents Run With Full Permissions](../../../docs/decisions/managed-agents-run-with-full-permissions.md)); owner
pairing is the gate.

The user is assumed to be able to create a bot on each platform they register —
a Telegram bot via BotFather, a SeaTalk Open Platform app — and to obtain
whatever scopes their organisation's approval flow requires. A fresh install is
meant to go from registering a Telegram channel to an agent reply in under ten
minutes by following the guide.

Deliberately out of scope:

- **Externally-hosted channels.** An agent-native gateway (OpenClaw, Hermes run
  standalone) or an official vendor integration (Claude-in-Slack,
  Codex-in-Slack, Cursor-in-Slack, Claude Code's official
  Telegram/Discord/iMessage plugin) owns its own transport and drives only its
  own agent. Coffer neither proxies nor manages these: stacking Coffer's channel
  in front would collide with their runtime, holding a token that is then
  written into an external process's config defeats the vault, and the official
  cloud integrations have no local secret to hold at all. A native or
  official channel that does not support a platform simply does not run there;
  Coffer does not bridge it. Coffer's channel plane manages only what Coffer
  hosts.
- **A copy-to-clipboard button.** Telegram's inline buttons can carry
  `copy_text`, but a `ChoiceButton` is only ever built by Coffer's own command
  cards, so an agent has no way to ask for one; offering it would need a second
  agent-facing sentinel beside `MEDIA:`, with its own parsing, false-positive
  risk on ordinary prose, and spec.
- **Privately-delivered selection cards**, explained under "Keep non-answer
  chatter private in a group"; the per-platform mechanics are in
  [`channels/telegram`](telegram/spec.md).

Channels are always on: no experimental feature gates their routes or adapters. While `memory` is off, a channel turn carries no memory index or retrieval; channels have no knowledge command — a person asks the agent in the chat to put a file or the conversation into knowledge, and the agent writes it (spec [experimental-features](../experimental-features/spec.md) "Close the memory feature's surfaces", "Close the knowledge feature's surfaces").

## Requirements

### Requirement: Register channels as a secret-referencing resource kind
The system MUST provide a `channel` resource kind with per-type configuration, a
default agent key, and optional default agent configuration. Each child spec
states its own type's fields. Secrets MUST live in the secret store only;
configuration carries references, which are probed at registration time, and a
registration whose reference does not resolve is rejected with nothing
persisted.

A channel is addressed by its immutable `uid`
([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md));
its config is the type, the secret refs, the default agent and its config,
and `runs_on` — the `machine_id` of the one machine whose daemon runs this
channel's adapter (see "Bind each channel to the one machine that runs it").

#### Scenario: register a telegram channel
- **GIVEN** a bot token stored under a secret ref
- **WHEN** the user registers a channel named `tg` with type telegram and that ref
- **THEN** the channel is listed with its config and enabled state
- **AND** the registration is audited

#### Scenario: reject a channel with a missing secret
- **GIVEN** no secret stored under the referenced name
- **WHEN** the user registers a channel pointing at it
- **THEN** registration fails with a secret error and nothing is persisted

### Requirement: Run the channel lifecycle through the resource framework
Channel lifecycle (register, enable, disable, update, delete) MUST ride the
generic resource framework, with audit on every transition. Disabling a channel
stops its adapter (Telegram polling halts, a SeaTalk websocket connection
closes); enabling restarts it;
deleting the channel stops the adapter and removes its peer binding.

#### Scenario: disable stops the adapter and enable restarts it
- **GIVEN** an enabled telegram channel with a running adapter
- **WHEN** the user disables and re-enables the channel
- **THEN** polling stops while disabled and resumes after enabling

#### Scenario: deleting a channel cleans up its runtime and peer
- **GIVEN** an enabled, paired channel
- **WHEN** the user deletes the channel resource
- **THEN** the adapter stops and the peer binding is removed

#### Scenario: renaming a channel keeps its adapter running
- **GIVEN** an enabled channel with a running adapter
- **WHEN** the owner renames the channel
- **THEN** the adapter is not restarted, and it keeps answering under the new name

### Requirement: Restart a channel's adapter on demand
A running adapter reads its secret once, when it is built, and the lifecycle
only rebuilds an adapter when the channel's configuration or routing changes, so
the daemon MUST offer an explicit restart: `POST /api/v1/channels/{uid}/restart`
stops the channel's adapter and its inbound connection (a SeaTalk websocket),
forgets any failure it was waiting out, and starts them afresh at once from the
stored configuration and the secret as it is now. It answers whether the adapter
is running afterwards; a disabled channel, or one bound to another machine, stays
stopped. The Channels page's **Reconnect** action MUST call it.

Replacing a secret under its existing ref MUST restart the adapter that uses it
without anyone asking: the daemon notices that the stored value changed and
rebuilds the adapter and, for SeaTalk, reconnects the websocket with the new
secret. Adapters, failure state and pending
pairing codes are all keyed by the channel's `uid`, so renaming a channel never
restarts it.

#### Scenario: a restart rebuilds the adapter on demand
- **GIVEN** an enabled channel with a running adapter
- **WHEN** the owner presses Reconnect
- **THEN** the old adapter stops and a new one starts and reads its secret again
- **AND** a channel waiting out a failed start is retried at once, and a disabled channel stays stopped

#### Scenario: a replaced secret restarts the adapter
- **GIVEN** a running channel whose bot token or app secret is stored under a ref
- **WHEN** a new value is stored under the same ref
- **THEN** the adapter is rebuilt with the new value, and for SeaTalk the websocket reconnects with it
- **AND** a channel whose secret did not change is left running

### Requirement: Report a channel whose secret waits for approval
A channel's adapter reads its bot token or app secret through the secret
boundary, which holds a secret that no one has approved for this channel (see
[secret](../secret/spec.md)). When that is why an adapter did not
start, the daemon MUST record the cause and report it, rather than a generic
stopped state: the channel status carries `secret_approval` with a `state` of
`pending` (waiting for the owner's approval in the Coffer app) or `refused` (the
owner declined; it stays refused until the channel's destination changes) and the
`secret_ref` it concerns, never a value. The field is absent when the adapter
runs, when the failure has any other cause, and when the channel is disabled or
not bound here. The lifecycle MUST retry on its normal failure interval, so an
approval given meanwhile starts the adapter with no restart; a pairing and the
channel's settings are untouched throughout. The Channels page and the Overview
attention item MUST name the approval (and, for `refused`, that it was refused)
instead of "not running" or a suggestion to replace the key.

#### Scenario: a channel whose secret waits for approval says so and starts once approved
- **GIVEN** an enabled channel whose secret has not been approved for it
- **WHEN** the lifecycle tries to start its adapter
- **THEN** the channel's status reports `secret_approval` with state `pending` and the secret's ref, and the adapter is not running
- **AND** once the owner approves it, the next retry starts the adapter and the field disappears, with no restart

### Requirement: Pair exactly one owner with a single-use code
The daemon MUST issue, per channel, an 8-character single-use pairing code
(unambiguous alphabet, 1-hour TTL, bounded wrong-guess attempts). A message
consisting of the code binds its sender as the channel's sole peer, replacing
any previous peer, and the sender receives a three-line confirmation — "✅
Paired — you own <bot>.", that only the owner can use it and how to use it in a
group, and how to see the commands ("send /help", or on Telegram "tap /") —
where <bot> is the channel's name on SeaTalk and `@username` on Telegram. The
help card (see "Offer the commands as a help card") follows the confirmation
automatically. All other senders
MUST be ignored silently: a stranger messaging the bot produces zero observable
response and zero turns, while the owner's traffic is unaffected, so the bot
never reveals it is alive to strangers. A code that expires or suffers repeated
wrong guesses is invalidated, and a fresh code must be issued. The pairing code
is held in memory only, per channel, and never persisted. Re-issuing a code and
pairing again rebinds the channel to the new sender.

#### Scenario: issue a pairing code
- **GIVEN** a registered channel
- **WHEN** the user requests a pairing code
- **THEN** an 8-character code with an expiry is returned and audited

#### Scenario: pair by sending the code
- **GIVEN** an issued pairing code
- **WHEN** a sender messages the bot with exactly that code
- **THEN** the sender becomes the channel's peer and receives the confirmation "✅ Paired — you own <bot>." followed by the help card
- **AND** the pairing is audited and the code cannot be reused

#### Scenario: an expired or wrong code does not pair
- **GIVEN** an issued pairing code
- **WHEN** a sender submits a wrong guess repeatedly or the code has expired
- **THEN** pairing fails, the sender gets no reply, and the code is invalidated

#### Scenario: pairing from another account replaces the owner
- **GIVEN** a channel paired to one sender, who has also addressed the bot in a group
- **WHEN** a new code is issued and a different sender messages the bot with it
- **THEN** the previous sender's direct and group pairings are removed, and their direct messages get no response
- **AND** a notification that names no chat goes to the new sender's direct chat
- **AND** in a group, an @mention from the new sender is answered while one from the previous sender is refused

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
- **AND** the answer names the conversation it stops ("⏹ Stopping “<title>”…"), and where the platform can edit a message it is edited into "⏹ Stopped “<title>” after 12s." (the turn's real duration) instead of a second message being sent
- **AND** when messages were queued behind the turn, the stopped line adds "⏸ N queued messages are on hold — send anything to continue."

#### Scenario: /stop with no turn in flight says so
- **GIVEN** a paired chat whose conversation has finished its last turn
- **WHEN** the peer sends `/stop`
- **THEN** the chat answers "Nothing is running." and never "⏹ Stopping…"

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
- **THEN** the group's answer lists `/new`, `/stop`, `/del` and `/help` only, with a button for each of those four
- **AND** the direct chat's answer lists all nine commands

#### Scenario: /new answers with a one-line card
- **GIVEN** a paired chat on a button-capable transport with two agents the channel may drive
- **WHEN** the owner sends `/new`, taps Agent, and taps the second agent
- **THEN** the first answer is one line naming the agent, the model and the directory, with Agent, Model and Dir buttons
- **AND** Agent offers the channel's agents with the current one ticked, and the tap starts a fresh conversation on the second agent

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

### Requirement: Notify the paired owner on demand
A notify entry point (`POST /api/v1/channels/{uid}/notify`) MUST deliver arbitrary text to a
channel's paired peer, independent of any conversation and with no inbound message — the call
the Channels page's **Send test** makes. Notify on a channel with no paired peer fails with a clear error and
sends nothing. This is the outbound foundation any feature that alerts the user
reuses.

#### Scenario: notify delivers to the paired owner
- **GIVEN** a paired channel
- **WHEN** notify is called via REST, and again with the Channels page's Send test
- **THEN** the text arrives in the IM chat both times

#### Scenario: notify on an unpaired channel fails cleanly
- **GIVEN** a channel with no paired peer
- **WHEN** notify is called
- **THEN** the call fails with a clear error and nothing is sent

### Requirement: Manage channels from the Channels page
The Channels page MUST be a list beside a detail pane. The **list** shows every
channel as one row — its platform, its name and one line saying what state it is
in — grouped by that state (needs attention, connected, running on another
machine, off), filterable by name, with a way to register a new channel (storing
secrets through the secret store); a row opens the channel. The **detail pane**
MUST show the open channel's status (adapter running, paired peer, and the
inbound state the channel's type reports — for SeaTalk, its websocket
connection) in a header that is the same in every state: the platform mark, the
name, a status pill, a meta line saying where it runs, a secondary **Send test**
(a test notification to its paired owner, see "Notify the paired owner on
demand") and a ⋯ menu holding only **Reconnect** (see "Restart a channel's
adapter on demand"). A control that cannot run in the current state MUST be
disabled rather than hidden, and a disabled **Send test** MUST say why in its
tooltip. The fix for a problem MUST sit in a banner between the header and the
tabs — one banner, one fix button (Reconnect now, Replace token or secret, Take
it back, Retry, Open Secrets, Run it here, Generate pairing code), and for a
missing SeaTalk SDK also the hand-off "Ask an agent" with Copy prompt behind
its chevron. A channel that is off, or run by another Mac, is not a problem: it
MUST show a quiet grey box with one small button (Turn on, Run it here…, the
latter confirming first) instead of a banner. Changing the machine, replacing
the secret and deleting live in the Settings tab. The detail pane MUST split into two tabs, in this order: **Overview**, the
default, at the bare `/channels/<uid>` — a single column of sections — who can use it (the paired owners as a bordered
list, each with Remove, and Add owner below it), the default agent, the agents the
channel may drive (its reach) and one link, **Conversations from this channel →**, to the
Conversations page filtered by `?source=<uid>` — the conversations themselves are listed there
only ([chat](../chat/spec.md) "Show every agent's sessions on the Conversations page"); it lists no commands — and **Settings**, at `/channels/<uid>/settings` — the
settings below, the machine that runs it (see "Bind each channel to the one
machine that runs it") and its secrets, and the channel's deletion. Choosing a tab
changes the address and nothing else.

Settings are saved as they change, with no save button and no saved line; a save
that fails says so in a toast and the field keeps what was typed. The one
exception is the channel's two system prompts (see "Append the owner's system
prompt to a channel turn"): they are prose, so their **System prompts** section
shows them as written and edits them through an **Edit** button and a dialog
with Cancel and Save. They cover the channel's title, its type's plain settings (a
SeaTalk app id), its two group-gating switches, `require_mention` and
`ignore_other_mentions` (see "Configure when the bot answers in a group"), and
the rest of what this requirement and the others in this spec name as a channel
setting. A secret is shown masked and replaced through its own dialog, **in
place**: the new value MUST be written to the secret store under the ref the
channel already cites before the configuration is saved, and that ref MUST stay in
the saved configuration, so a rotation moves no secret and leaves the channel's
machine binding and pairing untouched. A secret left blank rotates nothing.

Registering, editing, enabling, disabling, scoping and deleting a channel are the framework's own
lifecycle operations (see [resource-framework](../resource-framework/spec.md)), done on the
Channels page and over `/api/v1/resources`; pairing, binding, restarting and notifying are the
channel routes under `/api/v1/channels/{uid}`; the `coffer channel` commands call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"). The page
MUST report the channel's configuration together with its status — adapter run state, paired
peer, machine binding and the inbound state its type reports — with the group gating and the
idle period shown as the settings with their defaults filled in, as the daemon reads them. Saving
a setting changes only that setting: every switch, setting and ref it does not touch keeps its
stored value. `coffer secret set <ref>` rotates a secret under a ref the channel's
configuration cites.

The channel's status (`GET /api/v1/channels/{uid}/status`) carries its
**settings**: the typed reading of its stored configuration with every default
filled in (`TelegramChannelConfig` or `SeaTalkChannelConfig` in this capability's
contract). The Channels page starts every settings field from them, so a
default is written in one place, in the daemon, and no surface
keeps a copy. A stored configuration that no longer validates reports no
settings, and the page says so rather than guess.

Changing a channel's default agent or type settings is served by the detail page
and `PATCH /api/v1/resources/{uid}`.

#### Scenario: register a channel from the Add dialog and list it
- **GIVEN** a running daemon and a stored secret
- **WHEN** the user registers a channel in the Channels page's Add dialog and opens the list
- **THEN** the channel is created and appears in the list

#### Scenario: channel status reports runtime, pairing, and callback details
- **GIVEN** channels in various states
- **WHEN** the user queries status via REST and on the Channels page
- **THEN** adapter run state, paired peer, and the channel type's own inbound
  state are reported accurately

#### Scenario: a channel's settings arrive with their defaults filled in
- **GIVEN** a channel whose stored configuration names none of the optional settings
- **WHEN** its status is read
- **THEN** the settings carry every default (group gating, quiet windows, replies, idle period, directories, system prompts)
- **AND** the Channels page shows them without a default of its own

#### Scenario: rotating a channel secret keeps its refs and pairing
- **GIVEN** a registered telegram channel whose bot token is stored under a
  secret ref
- **WHEN** the owner enters a new bot token in the channel's replace-token dialog
  and confirms
- **THEN** the new token is written under the channel's existing ref first
- **AND** the channel's configuration is then saved to the same channel with
  every ref unchanged, so nothing its pairing and binding hang off moves

#### Scenario: the group-gating switches are edited in the Settings tab
- **GIVEN** a registered channel with `require_mention` on and `ignore_other_mentions` off (the defaults)
- **WHEN** the owner switches `require_mention` off and `ignore_other_mentions` on in the channel's Settings tab
- **THEN** the saved configuration carries both changes and every other setting and ref as it was

#### Scenario: a channel's lifecycle and reach run through the resource routes
- **GIVEN** a registered, enabled channel named `tg`
- **WHEN** the user, on the Channels page or over `/api/v1/resources`, sets its title to "Phone bot", scopes it to `codex` only, disables it and then deletes it
- **THEN** the title is saved with every ref unchanged, the channel's scope names only `codex`, and the adapter stops when it is disabled
- **AND** the removal deletes the channel and its peer binding, and each step is audited

#### Scenario: a channel's detail opens on Overview and keeps Settings on its own tab
- **GIVEN** a registered channel
- **WHEN** `/channels/<uid>/settings` is opened, and then the Overview tab is chosen
- **THEN** the first shows the channel's settings, and choosing Overview moves the address to the bare `/channels/<uid>`

#### Scenario: a channel's Overview links to its conversations instead of listing them
- **GIVEN** a channel that has started two conversations
- **WHEN** its Overview renders
- **THEN** it shows no list of conversations and one link, Conversations from this channel, to `/conversations?source=<uid>`

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

### Requirement: Refuse a message with an empty sender id
The owner gate MUST refuse a message whose sender id is empty and MUST NOT
complete or repair a pairing from an inbound message: a pairing records the
sender id when it is made, and no reader of a pairing without one is kept.

#### Scenario: a message with an empty sender id is refused
- **GIVEN** an inbound message whose sender id is empty
- **WHEN** the owner gate evaluates it
- **THEN** no turn runs and no pairing is changed

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
or confirmation dialogs on the user's computer. Where the running transport can
read threads, the note also names `coffer__channel_read_thread` for a thread's
earlier messages, with its arguments taken from the origin block. Web-UI turns
are unaffected — the note rides only on a conversation whose `channel_uid` is
set. A channel that has been deleted, or is not running, still gets the note,
saying less.

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

### Requirement: Append the owner's system prompt to a channel turn
A channel MUST carry two optional system prompts of the owner's own, stored in
its configuration beside its other settings: `direct_system_prompt`, for direct
chats and the threads opened in them, and `group_system_prompt`, for a group's
main chat and its threads. Each is plain multi-line text of at most 4,000
characters, trimmed of surrounding whitespace, and empty by default; a longer
one MUST be refused and leave the stored value as it was.

A channel turn MUST append the prompt for its conversation's chat kind after the
note of "Tell a channel-driven agent it is on a chat channel", under its own
heading line, `Instructions from the channel's owner:`, followed by the text as
written. It never replaces or shortens that note, and an empty prompt appends
nothing. A conversation whose chat cannot be located gets neither prompt.

The prompt MUST be read from the channel's stored configuration each time a
turn's system prompt is composed, so a change applies from the next turn of
every conversation — with no restart, and also when the turn resumes the agent's
existing session: Coffer sends its system context with every turn (Claude Code's
appended system prompt, Codex's `developerInstructions` on `thread/resume` as on
`thread/start`). See [Chat and turns](../../../docs-site/architecture/chat.md).

On the Channels page the prompts are a **System prompts** section of the
channel's Settings tab, after Replies and conversations: a **Direct chats** row
and a **Group chats** row, each showing its prompt as written and blank when
there is none, and an **Edit** button that opens a dialog with one text area for
each, a character count, Cancel and Save. Nothing is saved until Save, the
dialog closes only once the save has landed, and Save is unavailable while a
prompt is over the limit. Over REST they are fields of the channel's config
(`PATCH /api/v1/resources/{uid}`, `coffer channel update`) and are reported in
the channel's status settings.

#### Scenario: the owner's prompt follows Coffer's note under its own heading
- **GIVEN** a channel whose direct-chat prompt is "Answer in Chinese."
- **WHEN** a direct-chat turn's system prompt is composed
- **THEN** it holds Coffer's channel note in full, then the line
  `Instructions from the channel's owner:` and the prompt as written

#### Scenario: each chat kind reads its own system prompt
- **GIVEN** a channel with a direct-chat prompt and a different group-chat prompt
- **WHEN** a turn runs in its direct chat, in a group's main chat and in a group thread
- **THEN** the direct-chat turn carries the direct-chat prompt, and both group
  turns carry the group-chat prompt

#### Scenario: an empty system prompt appends nothing
- **GIVEN** a channel whose group-chat prompt is empty or only whitespace
- **WHEN** a group turn's system prompt is composed
- **THEN** it is Coffer's channel note alone, with no owner heading

#### Scenario: an edited system prompt applies from the next turn
- **GIVEN** a direct-chat conversation that has already run a turn, so its next
  turn resumes the agent's session
- **WHEN** the owner changes the direct-chat prompt and sends another message
- **THEN** that turn's system prompt carries the new text and not the old one,
  with no restart of the channel

#### Scenario: a system prompt longer than 4,000 characters is refused
- **GIVEN** a channel
- **WHEN** a prompt of 4,001 characters is saved, over REST or in the dialog
- **THEN** the REST save is refused with 422 and the stored prompt is unchanged,
  and the dialog states the limit with Save disabled

#### Scenario: the system prompts are edited through a dialog on the Settings tab
- **GIVEN** a channel with a group-chat prompt and no direct-chat prompt
- **WHEN** the owner opens its Settings tab, chooses Edit under System prompts,
  types a direct-chat prompt, clears the group one and saves
- **THEN** the section showed the group prompt as written and the direct row
  blank, nothing was saved before Save, and the saved configuration carries both
  changes with every other setting and ref as it was

#### Scenario: the note names the thread-reading tool where threads can be read
- **GIVEN** a conversation on a running channel whose transport can read threads
- **WHEN** its turn's note is composed
- **THEN** it names `coffer__channel_read_thread` and the origin block its
  arguments come from, while a note for a transport that cannot read threads
  does not

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

### Requirement: Send files back only through an explicit sentinel
The agent MUST send a file back to the user only by an explicit opt-in: a
line-anchored sentinel `MEDIA:/absolute/path` (optionally
`MEDIA:/absolute/path | caption`), told to it by the system note of "Tell a
channel-driven agent it is on a chat channel". On a transport that declares
`supports_media`, the channel uploads that file (an image extension as an inline
photo, otherwise a document) and strips the line from the delivered text;
ordinary prose — including a legitimate markdown image `![alt](path)` written
only to reference a file — is not this syntax and is never uploaded, and a
sentinel whose file is missing, relative, or oversized is left as text. The
unambiguous sentinel keeps outbound file delivery deliberate, not guessed, and
never collides with normal markdown.

#### Scenario: the agent sends a file to the user via a reply marker
- **GIVEN** a media-capable channel and an agent reply containing a
  `MEDIA:/absolute/path` sentinel line (optionally `| caption`) for a file that exists
- **WHEN** the turn's reply is delivered
- **THEN** the file is uploaded (an image as a photo, otherwise a document) and the
  sentinel line is removed from the text; ordinary prose — including a markdown
  image `![alt](path)` — is not this syntax and is not uploaded

### Requirement: Transcribe inbound voice only when the user opted in
An inbound voice message MUST drive a turn as a transcript. The built-in agents
(Claude Code, Codex) cannot hear audio, so the adapter transcribes the audio to
text and folds it into the turn's prompt. Transcription is a per-agent seam
([Channel Attachments](../../../docs/decisions/channel-attachments.md)); a future
audio-native agent's adapter forwards the audio instead of transcribing.

Transcription runs **remotely**, on the connection the user designated
`transcribe_default` ([provider-switching](../provider-switching/spec.md) "Keep an independent speech-to-text default") and the speech-to-text
model chosen beside it ([internal-engine](../internal-engine/spec.md) "Transcribe speech on its own connection and model"). That is a different
connection from the one Coffer's own engine runs on, and there is no fallback
between them: a gateway that serves chat completions commonly serves no
transcription endpoint at all. The endpoint is OpenAI-shaped
(`POST <base_url>/audio/transcriptions`); a connection whose protocol has none
is not used for it.

**This is the one place in Coffer where user content may leave the machine, and
it is off by default.** With no connection designated for transcription, no
model chosen for it, an unsupported protocol, or a secret that will not
resolve, nothing is uploaded: the voice is handed to the agent as an audio file
rather than lost. A failed or slow request degrades the same way — a
transcription problem MUST never fail a turn. The constitution permits this:
Principle I admits cloud services as **LLM and tool providers**, and a
transcription endpoint is a tool provider; the audio is data in transit rather
than vault state, and the transcript lands locally like any other turn text.

#### Scenario: an inbound voice message is transcribed for a text-only agent
- **GIVEN** a voice attachment on a turn for an agent that cannot hear audio
- **WHEN** the adapter prepares the turn
- **THEN** the audio is transcribed to text and folded into the prompt, and the
  audio is not also sent as a file (a future audio-native agent would forward it)

### Requirement: Treat an addressed group chat as its own peer
The system MUST treat a group chat as a first-class peer. When the paired owner
@mentions the bot (or the message is delivered as an addressed group event) the
bot answers there; the group becomes an additional peer in the channel's pairings, the vault document
`state/channel-peers/<channel name>.json`, keyed by the group chat id and inheriting
the owner's `sender_id`.

#### Scenario: the owner @mentions the bot in a group main chat
- **GIVEN** a paired channel and a group chat with no active thread
- **WHEN** the owner @mentions the bot in the group's main chat
- **THEN** a turn runs, no thread history is read, and a peer is recorded for the
  group chat inheriting the owner's `sender_id`
- **AND** where the platform threads group replies (SeaTalk) the reply is delivered
  into a thread rather than the group main chat, while an ordinary Telegram group,
  which has no thread to put it in, is answered in the chat itself

### Requirement: Act in a group only on an addressed message from the owner
The bot MUST act in a group ONLY on an addressed message (an @mention of the
bot). Un-addressed group messages are ignored. An addressed message from a
non-owner — including one whose `sender_id` the transport could not supply — is
refused with the short reply "🚫 Only <bot>’s owners can use it here." and starts no turn. A non-owner
message that is **not** addressed — which reaches the gate only when the channel
is set to answer without a mention — is dropped silently: the refusal is spoken
to someone who spoke to the bot, never to the room's chatter.

#### Scenario: an un-addressed group message is ignored
- **GIVEN** a paired channel and a group chat the bot is a member of
- **WHEN** a group message arrives with no @mention of the bot
- **THEN** no reply is sent and no turn or peer row is created for the group

#### Scenario: a non-owner @mention in a group is refused
- **GIVEN** a paired channel with a known owner
- **WHEN** someone other than the owner @mentions the bot in a group chat
- **THEN** the bot replies "🚫 Only <bot>’s owners can use it here." and no turn is
  started

#### Scenario: a non-owner's un-addressed group message is dropped silently
- **GIVEN** a paired channel set to answer in groups without a mention, and a group chat
- **WHEN** someone other than the owner sends a group message that does not address the bot
- **THEN** no reply is sent, no turn is started and no peer row is created

#### Scenario: an empty sender_id in a group cannot bypass the owner gate
- **GIVEN** a paired channel with a known owner and a group chat
- **WHEN** an addressed group message arrives with no resolvable `sender_id`
  (the transport failed to supply one)
- **THEN** the bot refuses it exactly like a non-owner sender — no turn is
  started and no peer row is created

### Requirement: Flatten forwarded chat records into the turn
Forwarded chat records MUST be flattened into readable text folded into the
turn so the agent sees them. Each entry renders as
`<sender>: <text | [image] url | [file] name>` under a `[Forwarded chat record]`
heading. Where a platform's file links require auth, its child spec states how
the bytes are additionally fetched so a vision agent sees the picture rather
than a dead link.

#### Scenario: a forwarded chat record reaches the agent
- **GIVEN** a paired channel
- **WHEN** the owner forwards a chat record to the bot
- **THEN** the turn's message text carries a `[Forwarded chat record]` block
  listing each forwarded item

### Requirement: Reply in place inside threads
Threads MUST be read and replied-to in place, and a group reply always lands in
a thread — never the group main chat. A DM or group message sent in a thread
also replies into that thread, and so does the reply to a slash command sent
there. A thread is read through every page the platform returns, and a turn
folds a bounded slice of it (see "Ground a thread turn in a bounded slice of the
thread"); the rest is read on demand ("Read a thread's earlier messages on
demand"). Reading *recent group-main* history is intentionally NOT done: the
addressed message is self-contained, and the permission to read a group's
back-chatter is not something this product asks for. How a thread is
identified, and whether its history can be fetched at all, is a platform fact
each child spec states. A quoted/replied message contributes a `> sender: …`
context prefix (see "Ground a turn in the message it quotes").

#### Scenario: the owner @mentions the bot inside a thread
- **GIVEN** a paired channel and a group chat with a thread, on a transport
  that can fetch thread history
- **WHEN** the owner @mentions the bot inside that thread
- **THEN** the thread's own messages are read and folded into the turn, and
  the reply is routed back into the same thread

#### Scenario: a group slash-command reply routes to the group/thread
- **GIVEN** a paired channel and a group chat/thread the owner has messaged in
- **WHEN** the owner sends a slash command (e.g. `/status`) inside that
  group/thread
- **THEN** the command's reply is routed with the same `chat_kind`/`thread_id`
  as the triggering message, not the DM defaults

### Requirement: Keep DM, group-main and thread turns apart
Each `(channel, chat, thread)` MUST map to its own conversation and render its
own turn, so a DM turn, a group-main turn, and a thread turn never share state.
What waits behind a running turn is that conversation's pending queue (spec
`chat`), not a buffer of the channel's own.

#### Scenario: a message behind a running thread turn waits in that thread's conversation queue
- **GIVEN** a paired channel with a turn running in a group thread
- **WHEN** the owner sends another message in that thread and a message in the direct chat
- **THEN** the thread message is queued on the thread conversation's pending queue
- **AND** the direct-chat message runs its own turn in its own conversation without waiting

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

- An unrestricted scope MUST mean every registered agent. A scope is never an
  empty list: `agents: []` is refused on both write paths with `SCOPE_INVALID`,
  as on every kind.
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
  may drive — registered in this vault, and inside its scope. It MUST be enforced on BOTH write paths, so the inconsistent
  state cannot be stored at all: a registration or an edit of the configuration
  is rejected when it names a `default_agent` that is unknown or outside the
  current scope, and an edit to the scope is rejected when the proposed
  scope excludes the current `default_agent`. A scope edit MUST NOT be
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
- A channel that should drive nothing is **switched off**, the same switch every
  toggleable kind has, and there is no second way to say it: a switched-off
  channel does not start its adapter, so no message is ever accepted only to be
  refused, and the management surface reports it as not running. Off keeps the
  scope that was chosen.
- Off MUST NOT also mean frozen: a channel the owner deliberately switched off
  MUST remain editable, so a wrong bot token or app secret can still be
  corrected without reactivating it first.
- A thread's sticky agent choice MUST be dropped in favour of the channel
  default once the scope no longer admits it, so narrowing a scope takes effect
  on the next conversation rather than waiting on whoever set the preference.

Reach and the machine binding answer different questions and MUST never be
merged: reach (`enabled` + `scope`, in this machine's reach record) says **which agents**
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

#### Scenario: an empty agent list is refused for a channel
- **GIVEN** a running channel whose scope names one agent,
- **WHEN** the owner sets its scope to `{"agents": []}`, on the scope route or in
  a registration,
- **THEN** the write is refused with `422` `SCOPE_INVALID`, nothing is persisted
  and the channel keeps running; a channel that should drive nothing is switched
  off, and then its adapter is not started and it reports as not running.

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

#### Scenario: edit a switched-off channel's configuration
- **GIVEN** a channel the owner switched off,
- **WHEN** the owner corrects a field of its configuration, such as its bot
  token ref,
- **THEN** the edit is accepted and the channel stays off — off is not
  frozen.

### Requirement: Bind each channel to the one machine that runs it
A channel MUST name the one machine that runs it. A channel's platform
identity — a polled bot, a held WebSocket — tolerates
exactly ONE consumer, so "which machine answers this bot" must have exactly one
answer, and that answer is written down. Its configuration carries `runs_on`,
the `machine_id` of the machine whose daemon starts this channel's adapter
(spec `vault-sync`, "Derive machine identity from the host"). It is configuration in the channel's
file and not part of its reach, because it MUST travel with that file — every
machine holding the file reads the same name, and every machine but one
finds it is not being named; reach MUST NOT travel and MUST NOT be made to carry
this.

- The binding MUST be authoritative for adapter startup. A runtime MUST start an
  adapter only for a channel whose `runs_on` is this machine's id, and MUST fail
  **closed** otherwise: an unknown machine, a retired one, and no binding at all
  all mean "not this machine", and none of them may be read as permission to
  start. Starting on a guess cannot be walked back — the platform has already
  been answered twice. The three cases are distinguished in what the surfaces
  report rather than in what the runtime does: **bound to another machine** is
  normal and says so, so a channel that is quiet here never looks like a channel
  that crashed here.
- **Unbound MUST run nowhere**, and MUST be reported rather than left to look
  like a stopped adapter, since a document naming no machine means the same
  thing on every machine that holds it. A channel registered through any Coffer
  surface MUST be bound to the registering machine at creation, so unbound is
  reached by import or by hand, not by using the product.
- A binding naming a machine no longer in the registry MUST be reported as a
  fault on the channel, distinctly from a channel that is merely bound
  elsewhere. Both run nowhere here; only one of them is somebody's mistake.
  Starting a channel on the grounds that nobody else claims it would be the
  rival-consumer failure arriving by the back door: every machine that cannot
  resolve the id would reason identically and they would all start.
- A `runs_on` value is written only by the surfaces, and they refuse an id the
  machine registry does not hold; whatever else ends up there (a hand edit, say)
  fails closed and is reported as a binding to an unknown machine.
- Rebinding MUST converge without a restart and without a command that reaches
  another machine: changing `runs_on` is an ordinary configuration edit. The
  losing machine MUST stop its adapter within one reconcile tick of seeing the
  change; the gaining machine MUST start one within one tick of the converge
  round that brings the change to it. So the clean way to hand a channel over is
  to rebind it from the machine that currently holds it. Rebinding TO the
  machine one is sitting at while another machine still holds the channel is
  allowed and is sometimes the only option — the old machine may be the one that
  is broken — but it opens a window, bounded by that machine's sync interval, in
  which both adapters are live; the surface offering the rebind MUST say so.
- A channel's configuration MUST carry secret **references** only, never
  secret material, exactly as it did when it never travelled — the rule is
  unchanged, and travelling is what makes it load-bearing rather than merely
  tidy. Ciphertext for those refs travels only when the user opts the remote in
  to secrets, and a machine holding ciphertext without the master key MUST
  report those refs locked rather than failing decryption silently.
- A channel bound to another machine MUST NOT be refused by this machine's own
  preconditions. Its `default_agent` names an agent on the machine that runs it;
  validating that here would hold a good document out of the registry for a
  fault on nobody's machine.
- A channel's peer pairings MUST travel with the channel as synced state (spec
  `vault-sync`, "Carry channel pairings as platform identity"), because a channel that travels without them makes
  the owner re-pair from their phone every time it moves, and a rebind is meant
  to be one click. What travels is platform identity — chat id, sender id,
  display name. The active conversation pointer and the thread's sticky agent
  do not: both name machine-local things — a conversation the other machine
  does not have, an agent installed on this machine.

Two adapters can still be pointed at one bot identity only the way they always
could — by someone registering the same bot twice, by hand, under two names —
which no field inside Coffer could prevent.

#### Scenario: only the machine a channel names starts its adapter
- **GIVEN** an enabled channel bound to another machine's `machine_id`
- **WHEN** the runtime reconciles
- **THEN** no adapter is started here, and the management surface reports the
  channel as bound elsewhere rather than as stopped

#### Scenario: a channel bound to an unknown machine starts nowhere
- **GIVEN** an enabled channel whose binding names a machine the registry does
  not hold
- **WHEN** the runtime reconciles on any machine
- **THEN** no machine starts an adapter for it, and the channel is reported as
  bound to a machine that no longer exists

#### Scenario: an unbound channel runs nowhere and says so
- **GIVEN** an enabled channel whose configuration carries no binding
- **WHEN** the runtime reconciles
- **THEN** no adapter is started, and the channel's status carries a diagnostic
  naming the missing binding and the fix

#### Scenario: rebinding hands the channel over without a restart
- **GIVEN** an enabled channel running on this machine
- **WHEN** the user binds it to another machine
- **THEN** this machine stops its adapter on the next reconcile, without a
  daemon restart, and the channel's binding is what the next sync round
  pushes

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

### Requirement: List every Coffer-hosted channel on one management surface
Coffer-hosted channels MUST have a unified management surface. A management
view lists every Coffer-hosted channel with its status, paired owner, agent, and
health, mirroring the MCP-server / memory / skill management surfaces; each
channel's secrets (bot tokens, app secrets) are held in the Coffer vault.
The Channels page holds each channel's setup, connection status and settings only: it shows no conversation history, and each channel links to the Conversations page filtered to that channel (spec [chat](../chat/spec.md) "Show every agent's sessions on the Conversations page"). Externally-hosted channels are out of scope (a non-goal).

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

### Requirement: Download the media a thread's messages carry
Thread-history media MUST be downloaded, not flattened to a dead link. When a
turn folds thread messages on a transport that can fetch thread history, the
media those **folded** messages carry is downloaded and attached to the turn,
alongside the flattened text, rather than surfacing only as an auth-gated
`[image] <url>` the agent could not open. Messages the fold leaves out are not
downloaded; a page the read tool returns has its own messages' media downloaded.

#### Scenario: thread-history images reach a vision agent
- **GIVEN** a paired channel and a group thread whose own messages include an
  image (a directly-sent one and one nested in a forwarded record)
- **WHEN** the owner @mentions the bot inside that thread
- **THEN** the thread's images are downloaded and attached to the turn — reaching
  the vision agent as real bytes, not a dead auth-gated file link

#### Scenario: only the folded messages' media is downloaded
- **GIVEN** a thread of more than 20 earlier messages, the oldest and one of the
  newest carrying an image
- **WHEN** the owner @mentions the bot in that thread for the first time
- **THEN** only the newer message's image is downloaded

### Requirement: Give documents to every agent as extracted text
PDFs and office documents MUST reach every agent as extracted text, not as a
vision input. A document attachment is text-extracted into a context block so
path-native agents (Codex) and vision agents alike see its content; images stay
vision-inlined for agents that support it.

#### Scenario: a PDF reaches a path-native agent as extracted text
- **GIVEN** a turn carrying a PDF (or office document) attachment for a
  path-native agent (Codex)
- **WHEN** the adapter prepares the turn
- **THEN** the document is text-extracted and folded into the prompt as a
  labelled `[Document: <name>]` block, and the document is not also sent as a
  binary path note; when no extraction engine is available the document degrades
  to a file path rather than wedging the turn

### Requirement: Return outbound media into the originating thread
Outbound media MUST be thread-aware. On a `supports_media` transport an agent's
`MEDIA:/path` sentinel (see "Send files back only through an explicit
sentinel") sends the file back into the same chat **and thread** the turn came
from — a generated chart returns to the group thread, not the main chat.

#### Scenario: a file the agent returns from a thread turn lands in that thread
- **GIVEN** a paired channel on a `supports_media` transport and a turn driven from a group thread
- **WHEN** the agent's reply carries a `MEDIA:/absolute/path` sentinel for a file that exists
- **THEN** the file is sent to that group chat with that thread's id
- **AND** it is not sent to the group main chat or to the owner's direct chat

### Requirement: Key conversation identity by channel, chat and thread
Each group thread MUST be its own conversation. Conversation identity is keyed
by `(channel, chat_id, thread_id)`, not by the peer alone. A DM (`thread_id=""`)
is one conversation; each thread in a group is independent — its own history and
its own turn lock. Concurrent turns in different threads of one group do not
collide on a single conversation. Pairing/owner identity stays on the peer row.

In a direct chat the key's thread is the thread only when that thread is a
conversation of its own: a parallel thread `/thread` opened, or any thread on a
platform where a direct-chat thread only exists because someone created it
(Telegram's private-chat topics). Any other direct-chat thread keys to the DM's
`""` conversation (see "Open parallel conversations beside a direct chat"). The key
decides which conversation a message joins; the reply still goes to the thread
the message came from.

#### Scenario: each group thread is an independent conversation
- **GIVEN** a paired channel and a group whose threads share one `chat_id`
- **WHEN** the owner drives a turn in thread A and, before it finishes, a turn
  in thread B
- **THEN** the two threads resolve to two different conversations, both turns
  run concurrently, and neither is refused with "a turn is already running"

#### Scenario: a casual direct-chat reply-in-thread keeps the direct chat's conversation
- **GIVEN** a paired SeaTalk direct chat with an active conversation
- **WHEN** the owner replies inside a thread under one of the bot's answers, a thread `/thread` did not open
- **THEN** the turn runs in the direct chat's conversation, with its context
- **AND** the reply is posted inside that thread

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

### Requirement: Open every turn with its message origin
Every turn MUST carry its own origin. The turn text opens with a
`[Message origin]` block naming the platform, the channel (its current name,
which `coffer__channel_read_thread` takes), the chat (kind, the chat title where
the platform supplies one, and always the chat id), the thread, and the sender
(display name **and** the stable platform id, which a platform tool call takes
and which, in a group, appears nowhere else because `chat_id` is the group's) —
so an agent asked "which group is this?" answers from the turn it was given
instead of listing the bot's groups and inferring, and a platform tool call has a
chat id to aim at. The block is folded in after command detection (a prefixed
`/help` would stop being a command) and after the empty-envelope check, and is
folded into the turn's text exactly like thread context, so it stays one string
and the agent's own session records it. It rides on **every** turn, not just a
conversation's first: `/new <agent>` can swap the agent between conversations of
one thread (see "Drive every managed agent from one bot") and a resumed session
would otherwise lose it. Title and sender name are chat-member-settable, so both
are collapsed to one clipped line before they reach the prompt — a rename cannot
forge extra origin lines. Where a platform hands the chat title over for free it
is included; where it does not the chat is named by id alone, which an agent can
resolve to a name through the platform's own tools.

#### Scenario: a group turn names the group it came from
- **GIVEN** a paired channel whose owner @mentions the bot in a group thread
- **WHEN** the turn is driven
- **THEN** the turn text opens with a `[Message origin]` block naming the platform,
  the channel, the chat kind and title, the chat id, the thread id, and the sender

#### Scenario: a DM turn names its own chat
- **GIVEN** a paired channel and a DM from its owner
- **WHEN** the turn is driven
- **THEN** the origin block names the platform, the channel and the direct chat by
  id, omitting the thread line a DM has no value for

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
  tap is refused with the same routed "Only <bot>’s owners can use it here." reply and no switch

### Requirement: Configure when the bot answers in a group
Per-group inbound gating MUST be configurable. A channel may set
require-mention (default on for groups — the bot answers only when @mentioned or
replied-to) and ignore-messages-that-@-someone-else (opt-in — a group message
that @mentions any non-bot user is dropped silently, even when it also mentions
the bot) — so a bot sitting in a busy group answers only when it should. Both
are plain config bools; the channel stays owner-gated regardless, so this is
about *when* to answer, not *who* may drive turns.

#### Scenario: require_mention on drops an un-addressed group message
- **GIVEN** a paired channel with `require_mention` on (the default)
- **WHEN** an un-addressed group message arrives (no @mention/reply-to-bot),
  even from the owner
- **THEN** it is dropped at the mention gate — no reply, no turn, and no peer row

#### Scenario: require_mention off admits an un-addressed owner group message
- **GIVEN** a paired channel with `require_mention` off
- **WHEN** an un-addressed group message arrives from the owner
- **THEN** it passes the mention gate and drives a turn (still owner-gated: a
  non-owner would be refused by the sender checks below the gate)

#### Scenario: ignore_other_mentions drops a message that also @mentions a human
- **GIVEN** a paired channel with `ignore_other_mentions` on
- **WHEN** a group message @mentions the bot but also @mentions another user
- **THEN** it is dropped silently — no reply and no turn — so the bot does not
  butt into human-aimed traffic

#### Scenario: ignore_other_mentions off still answers when @mentioned alongside a human
- **GIVEN** a paired channel with `ignore_other_mentions` off (the default)
- **WHEN** a group message @mentions the bot alongside another user
- **THEN** the turn still runs — the extra human @mention does not suppress it

### Requirement: Acknowledge receipt and completion by capability
Receipt and progress MUST be acknowledged, capability-gated (never by transport
type). On a `supports_reactions` transport the owner's own message carries one
reaction that follows the turn: a **received** mark the moment it arrives (a
message queued behind a running turn keeps it), a **working** mark when its turn
starts, and one of **done** (a clean finish, including one that ends on a
question for the owner), **failed** (an error) or
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

### Requirement: Process each inbound event once
Inbound events MUST be de-duplicated: a redelivered platform event (same message
id) is processed once. When inbound connectivity is lost the adapter backs off
exponentially and resumes, and no inbound message is double-processed after
reconnect.

#### Scenario: a redelivered event is processed once
- **GIVEN** a paired channel that has already handled an inbound event
- **WHEN** the platform redelivers that same event (same id) after a slow ack or
  a network hiccup
- **THEN** the redelivery is dropped and the turn runs exactly once — no double
  reply or duplicate work — while a genuinely new event still drives its own turn

### Requirement: Ground a turn in the message it quotes
A quoted message MUST reach the turn as content, not only as a reference. When
the user replies by quoting a message, the quoted message is folded into the
turn as `> sender: …` lines directly above the user's own text, so "repeat this"
or "as I said above" points at something the agent can read. The images and
files the quoted message carries are attached like a thread message's. A
platform that inlines the quote on the update itself has already folded it into
the message text. A platform that delivers only an id has the transport
resolve it with the bot's own credentials: such an id is scoped to the bot that
received it, so no tool the agent holds could resolve it. The origin block (see
"Open every turn with its message origin") still names the quoted message's
id. A lookup that fails leaves the turn as it was, with the id as the only
trace.

#### Scenario: a quoted message is named in the turn's origin
- **GIVEN** a paired channel whose inbound message quotes an earlier message
- **WHEN** the turn is built
- **THEN** the origin block names the quoted message's id

#### Scenario: a quoted message is folded into the turn
- **GIVEN** a paired group on a transport that resolves quotes, and the owner
  quotes an earlier message in the group main chat and @mentions the bot
- **WHEN** the turn is built
- **THEN** the quoted message's sender and text sit as a `> sender: …` line
  directly above the owner's own text
- **AND** no thread history is read, because the @mention roots a fresh thread

### Requirement: Ground a DM thread's turn in the thread
A thread MUST ground its turn in a DM too, not only in a group. Direct chats with
a bot thread as well, and a transport that can fetch a DM thread does so — the
same bounded fold ("Ground a thread turn in a bounded slice of the thread"), the
same media download, the same degrade-to-nothing on any failure. The asymmetry
this removes was real and invisible: a DM thread was already replied to in place
(see "Reply in place inside threads") yet the turn driving that reply could not
see anything else in the thread. Group-*main* chatter is still never fetched.

#### Scenario: a DM thread grounds its turn in the thread's own messages
- **GIVEN** a paired direct chat on an adapter that supports history fetch, and a
  message arriving inside an existing thread
- **WHEN** the turn is built
- **THEN** the thread's own messages are fetched through the direct-chat thread
  endpoint and folded into the turn, exactly as a group thread's are

### Requirement: Say what a thread read cannot show
A thread's folded context MUST say what it does not show. SeaTalk's thread
endpoints return only replies sent in the last 7 days, and never whisper or
deleted messages; a root message is exempt from the window. A thread whose root
predates the window therefore reads as its root plus recent replies, however long
it looks in the app. A conversation's first fold in such a thread ends with a
note saying so, so the agent reports what it could not see instead of answering
as if the fragment were the whole thread. And whenever the fold leaves older
messages out, it ends with one line saying how many and how to read them: a
`coffer__channel_read_thread` call with the channel, chat id, chat kind, thread
id and `before` set to the oldest message shown.

#### Scenario: a thread older than the platform's 7-day reach says what it cannot show
- **GIVEN** a thread whose root was sent more than 7 days ago
- **WHEN** its context is fetched for a turn
- **THEN** the returned messages are followed by a note that SeaTalk returns only
  the last 7 days of replies and that older messages are not shown

#### Scenario: a fold that leaves out older messages says how to read them
- **GIVEN** a thread of 25 earlier messages
- **WHEN** a conversation's first turn there folds the latest 20
- **THEN** the block ends with a note that 5 earlier messages are not shown,
  naming `coffer__channel_read_thread` with the channel, the thread id and
  `before` set to the oldest message shown

### Requirement: Track the bot's own standing in a group
The bot's own standing in a group MUST be tracked. Platform events that change
what a binding *is* rather than driving a turn arrive on a lifecycle callback
kept separate from messages and card taps, so no consumer of those has to filter
them out. Removal from a group stops every live session for that chat; nothing
is sent back, because the bot is no longer there to send it. A conversion that
lets people from other organisations read a chat the owner paired is a
security-relevant change and so is announced in the group itself rather than
only written to a log — the owner is by definition present, and the group is
the one place the warning is in context. Both are de-duplicated like every other
event (see "Process each inbound event once"): a redelivered removal must not
fire twice. Each child spec names its platform's events and how they normalise
onto this one envelope, so the rule is one rule and not one per platform. Being
*added* is deliberately not an event: anyone can add a bot to a group, and
pairing (see "Pair exactly one owner with a single-use code") is the gate.

#### Scenario: being removed from a group stops that group's sessions
- **GIVEN** a paired group with a live session
- **WHEN** the platform reports the bot was removed from that group
- **THEN** that chat's sessions are stopped and nothing is sent back to the group

#### Scenario: a group turning external is announced in the group
- **GIVEN** a paired group the bot is still a member of
- **WHEN** the platform reports the group was converted to an external group
- **THEN** one warning is sent into that group, and the channel keeps working

### Requirement: Probe platform capabilities and latch off rejected ones
Platform capability MUST be probed, never assumed. Each platform carries a
family of surfaces built for exactly this shape of bot — a message that streams
while an agent generates it, a stop control the platform draws itself,
structured rich text, and a group reply only one member can see. Coffer uses
each one where the platform it reaches offers it, and keeps its own hand-built
equivalent as the fallback beneath it, because the platform version a user
reaches is not guaranteed to be new enough; every such capability is therefore
two mechanisms and a probe, not one mechanism.

On start the transport reads what the platform says about itself and keeps the
fields that change what it may do. A capability introduced after the platform
version the user actually reaches is attempted once and **latched off for the
process** on the platform's own rejection, falling back to the mechanism it
replaced. A Coffer running against an older platform therefore degrades in
formatting and liveness, never in delivery.

#### Scenario: a capability the platform rejects is latched off and the reply still arrives
- **GIVEN** a channel whose platform rejects a newer capability as unsupported
- **WHEN** a reply first tries that capability and a later reply is sent
- **THEN** the first reply is delivered through the fallback mechanism
- **AND** the later reply goes straight to the fallback without attempting the rejected capability again

### Requirement: Diagnose configuration a platform setting defeats
A configuration that a platform-side setting silently defeats MUST be diagnosed,
not silently broken. Where a channel's configuration looks correct in Coffer and
does nothing in the chat because of a setting that lives on the platform, the
channel's health surface (see "List every Coffer-hosted channel on one
management surface") MUST report that state and name the fix.

#### Scenario: a platform setting that defeats the configuration shows on channel health
- **GIVEN** a running channel whose adapter reports a platform-side setting that defeats part of its configuration
- **WHEN** the owner reads the channel's status
- **THEN** the status carries a diagnostic naming the defeated setting and the fix
- **AND** a channel whose configuration the platform honours carries no such diagnostic

### Requirement: Render replies in the platform's rich format
A reply MUST render in the platform's own rich format where it has one. An agent
answers in markdown — headings, lists, tables, block quotes, fenced code — and a
platform whose own rich message carries those natively receives one, rather than
the flattened subset that demotes a heading to bold, a bullet to a glyph, and
passes a table through as raw pipes. The existing renderer stays as the fallback
"Probe platform capabilities and latch off rejected ones" selects.

#### Scenario: a rich reply keeps its markdown structure
- **GIVEN** a transport whose platform renders rich text,
- **WHEN** a turn's reply contains a heading, a list, and a table,
- **THEN** the reply is delivered in the platform's rich format with that
  structure intact, and a platform that rejects it falls back to the plain
  renderer without losing the reply.

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

### Requirement: Stop the turn from the platform's own stop control
The platform's own stop control MUST end the turn. Where a live surface
advertises a stop control the platform draws, Coffer MUST route the press to the
same interrupt path as `/stop` — same turn cancellation, same queue pause, same
user-visible outcome. A stop control the user can see but that does not stop
anything is worse than none, so the button is only advertised on a transport
where the route is wired.

#### Scenario: a stop pressed on the platform's own control ends the turn
- **GIVEN** a running turn whose live surface advertises a stop control,
- **WHEN** the platform reports that the user stopped the generation,
- **THEN** the turn is interrupted and the pending queue is paused, exactly as
  a typed `/stop` would.

### Requirement: Keep non-answer chatter private in a group
Chatter that is not the answer MUST stay private in a group. Command output and
errors are addressed to one member, not to the room, wherever the platform can
deliver a message only that member's client shows; the agent's actual reply is
always an ordinary message the group can see. This is the group-noise half of
"Act in a group only on an addressed message from the owner": that requirement
stops the bot from *acting* on everything, this one stops it from *saying*
everything out loud. Every command declares which side of that line it falls on,
on the same roster "Register the bot's command menu and profile from one roster"
registers the menu from: `/new` and `/stop` change state the whole room shares
and stay visible; the ones that answer only the asker — `/help`, and the
one-line notice a direct-chat command (`/model`, `/dir`, `/status`, `/resume`,
`/thread`) gets in a group — are delivered privately where the transport can. A roster entry that declares
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
in English and Chinese, and whether it works only in a direct chat — which keeps it out of a group's menu and help. A platform with no menu API (SeaTalk) introduces
the commands through the help card instead (see "Offer the commands as a help
card"). Copy the owner already wrote, and the bot's name, are their branding
decision and MUST NOT be overwritten.

#### Scenario: the command menu matches the commands that exist
- **GIVEN** the channel command roster,
- **WHEN** the transport registers its private-chat command menu,
- **THEN** every command the channel handles is registered.

### Requirement: Pair by a one-tap start link
Pairing MUST be one tap where the platform allows it. Where the platform
supports a parameterised start link, the pairing code (see "Pair exactly one
owner with a single-use code") is issued as a link that carries it, so the owner
pairs by opening the link instead of transcribing eight characters on a phone.
The typed code keeps working — the link is an additional way in, and the same
single-use, TTL-bounded, attempt-bounded gate applies to both.

#### Scenario: pairing by link claims the code
- **GIVEN** an issued pairing code delivered as a start link,
- **WHEN** the owner opens the link,
- **THEN** the channel pairs to that sender, and the code is spent exactly as a
  typed one is.

### Requirement: Drive a turn from every inbound media type or say why not
Every inbound media type MUST drive a turn, or say why it cannot. Whatever the
platform can attach to a message is downloaded and becomes an `Attachment` (see
"Hand inbound photos and files to the agent"). Where a platform caps what a bot
may download, a file over that cap MUST be noted in the turn text — exactly
once — so the agent's reply acknowledges it, not a silent no-op: the failure
mode being fixed is a user who sent a file and got an answer that never mentions
it. A file the platform already reports as over the cap is never requested. A
download that fails after the platform handed over a fetchable reference is
noted in the turn text and the turn still runs on whatever text and other
attachments arrived.

#### Scenario: an oversized inbound file tells the user
- **GIVEN** a message carrying a file larger than the platform lets a bot
  download,
- **WHEN** the message drives a turn,
- **THEN** the turn text carries a note naming the file as one that did not
  reach the agent, so the reply acknowledges it rather than the file being
  silently dropped
- **AND** the turn still runs on the message's text

### Requirement: Attach a group reply to the message it answers
A reply MUST be attached to what it answers. In a group, on a platform that
offers a reply primitive, the bot's reply MUST be sent as a platform-level
reply to the message that triggered it, so a busy room can tell which question
each answer belongs to. On a threaded platform whose group replies always land
in a thread (SeaTalk — see "Reply in place inside threads"), the thread rooted
at the triggering message is that attachment: the reply goes into it, and no
separate reply reference is sent.

#### Scenario: a group reply is attached to the message it answers
- **GIVEN** an addressed message in a group, on a platform that offers a reply primitive,
- **WHEN** the turn replies,
- **THEN** the reply is delivered as a platform-level reply to that message.

### Requirement: Use the platform's button vocabulary on cards
Selection cards MUST speak the platform's button vocabulary. Where the platform
offers button semantics beyond a label — a disabled state, an intent colour — the
card uses them, so the option already taken is shown disabled rather than
re-offered.

#### Scenario: the option in effect is shown disabled on a selection card
- **GIVEN** a transport whose buttons support a disabled state
- **WHEN** a selection card is rendered with one option currently in effect
- **THEN** that option's button is disabled and marked as the current choice
- **AND** every other option's button stays an ordinary tappable button

### Requirement: Take a burst of messages as one turn
Messages that arrive in quick succession in one chat and thread MUST become one
turn, not one turn each. A person who forwards a chat record and then types
"look into this" asked one question. The channel waits for a short quiet
window after each message before it starts the turn, and a message arriving
inside the window restarts it. The window is 1.5 seconds after a text message.
It is 5 seconds after a message that is rarely the whole ask: a forwarded chat
record, or files with no text. Both windows are the channel's own settings,
`wait_after_text_seconds` and `wait_after_forward_seconds`, each from 0 to 60
seconds and edited on the Channels page; 0 runs every such message as its own
turn.

The coalesced turn carries:
- every message's text, in arrival order;
- every attachment;
- one origin block, taken from the last message, which is also what the reply
  attaches to and mentions.

Every message is still acknowledged when it arrives (see "Acknowledge receipt
and completion by capability"), never only when the window closes, and every
message of the burst — not only the last — carries the turn's later marks, so none
stays on its receipt mark; a message `/stop` discards from the burst is marked
stopped. Messages
sent while a turn is running are coalesced the same way before they join the
conversation's pending queue.

A slash command is never held. It first releases what its chat and thread are
holding, so the turn it follows still runs first. `/stop` is the exception:
it drops the held messages instead, since they had not started. A tap on a command
button is the command typed, so it settles the held messages the same way.

#### Scenario: a forwarded record and its follow-up become one turn
- **GIVEN** a paired direct chat
- **WHEN** the owner forwards a chat record and, two seconds later, sends "look into this"
- **THEN** one turn runs, and its text holds the forwarded record followed by "look into this"
- **AND** both messages were acknowledged when they arrived, and both carry the turn's done mark when it ends

#### Scenario: messages further apart than the window are separate turns
- **GIVEN** a paired direct chat
- **WHEN** the owner sends a text message and sends another one after the window has closed
- **THEN** each message drives its own turn, in arrival order

#### Scenario: /stop drops messages still being held
- **GIVEN** a message waiting in its quiet window
- **WHEN** the owner sends `/stop` before the window closes
- **THEN** the waiting message never becomes a turn, and it is marked stopped

#### Scenario: a channel's quiet windows come from its settings
- **GIVEN** a channel whose config sets no windows
- **WHEN** its config is read
- **THEN** it waits 1.5 seconds after text and 5 seconds after a forward
- **AND** a config may set either window anywhere from 0 to 60 seconds, and a value outside that range is refused

#### Scenario: the quiet windows are edited in the channel's settings
- **GIVEN** a registered channel
- **WHEN** the owner sets the wait after a text message to 0 and the wait after a forward to 8 in the channel's settings
- **THEN** the channel's config holds those two windows and every other setting is unchanged

#### Scenario: the quiet windows are edited on the Channels page
- **GIVEN** a channel open in the Edit channel dialog
- **WHEN** the owner changes the wait after a text message and saves
- **THEN** the channel's config holds the new window and the other settings are unchanged

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
uses. One rule serves every card — the `/help` command buttons and the `/resume`
list as much as the `/model` list, a numbered list showing on each page only the
lines of its own entries — and a handful of models or directories render
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
  root message or topic name (on SeaTalk, the bot's reply in the thread of the owner's `/thread` message), the conversation's title on the web, and `/status`
  both inside it and in the direct chat.
- `/status` in the direct chat says how many parallel threads the chat has and
  lists each one's mark, agent, and whether a turn is running, waiting, or idle,
  newest first.
- `/thread` works only in a direct chat; in a group it is declined (see
  "Answer the conversation commands from any paired chat"), because every group
  thread is already its own conversation.

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
- **THEN** the channel answers `Unknown command /stpo. Did you mean /stop? Send /help for all commands.` and no turn runs

#### Scenario: a removed command reaches the agent as text
- **GIVEN** a paired channel
- **WHEN** the owner sends `/agent codex`
- **THEN** no agent is switched and the text reaches the agent as a message

### Requirement: Choose the working directory from chat
The owner MUST be able to move a chat's conversation to another working
directory from chat — but only to a directory the channel allows. A channel's
Settings carry its Working directories as one **Directories** list, `directories`:
absolute paths added through an Add directory… folder picker and edited on the
Channels page, each also admitting the directories beneath it, and the ones `/dir`
may switch to. One of them may be the **Default**, the directory new conversations
start in (stored as the default agent configuration's `cwd`): each row offers
**Set as default** (the default's row reads "default" and offers **Unset default**)
and a remove ✕, removing the default's row clears the default, and none means the
Coffer workspace `~/.coffer/content/workspace`, which then heads the list as a row
reading "default · Coffer workspace" with no actions, so where new conversations
start shows before any directory is added. A default stored before it had to be
listed is shown in the list and joins it with the next change. A long list scrolls
inside its box. With no directory, `/dir` is off.
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

#### Scenario: the channel's directories are edited on the Channels page
- **GIVEN** a registered channel
- **WHEN** the owner sets its directories in the channel's settings on the Channels page
- **THEN** the channel's configuration carries exactly those absolute paths, and
  removing every row clears them

#### Scenario: the channel's default directory is edited on the Channels page
- **GIVEN** a registered channel
- **WHEN** the owner chooses Set as default on one of its listed directories on the Channels page
- **THEN** the channel's default agent configuration carries that absolute path as `cwd`, new conversations start there, and Unset default — or removing that row — removes it

### Requirement: Resume an earlier conversation from chat
Every conversation a chat thread opens MUST be remembered for that thread, and
the owner MUST be able to return to one from chat. `/resume` lists the thread's
conversations (up to 100), newest first, each by title, agent and age, with the
one in effect ticked, as a card where the transport has buttons, paged so that
every one is reachable: each page lists its own conversations, and a button
carries the conversation's number in the whole list, so `/resume <n>` means the
same on every page; `/resume <n>` or a
tap makes the n-th the thread's active conversation again, so the next message
continues it. Only conversations this chat thread opened are offered — never one
from another chat, and a tapped value naming any other conversation
is refused. A conversation deleted since is left out.

#### Scenario: /resume lists this chat's earlier conversations
- **GIVEN** a paired chat that has opened two conversations with `/new`
- **WHEN** the owner sends `/resume`
- **THEN** both are listed by title, newest first, with the active one ticked

#### Scenario: /resume pages through every earlier conversation
- **GIVEN** a paired chat that has opened nine conversations
- **WHEN** the owner sends `/resume` and taps Next to the last page
- **THEN** each page lists its own conversations and the last page's button is numbered 9
- **AND** `/resume 9` reopens that same conversation

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

### Requirement: Offer the commands as a help card
`/help` MUST list the commands from the roster on one line, each with its
arguments, then say that anything else is a message to the agent; where the
transport has buttons it is a card titled "Commands" carrying a button for every
command the chat may use — all nine in a direct chat, `/new`, `/stop`, `/del` and
`/help` in a group — paged like any card whose buttons do not fit one page (see
"Offer choices and actions as owner-gated cards"), and a command button runs that
command. The help card is sent automatically right after pairing succeeds (pairing is a direct chat). A
platform with no command menu (SeaTalk) shows what the bot accepts through
`/help`.

#### Scenario: /help is a card with a button for every command, paged
- **GIVEN** a paired direct chat on a button-capable transport
- **WHEN** the owner sends `/help`
- **THEN** a card lists the commands and carries the first page of a button for every one of the nine commands
- **AND** Next rewrites the same card with the following commands, so every command is reachable

#### Scenario: the help card follows pairing
- **GIVEN** an unpaired channel with an issued pairing code
- **WHEN** the owner pairs by sending the code
- **THEN** the pairing is confirmed and the help card listing every command follows it

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
as the title. REST keeps addressing a channel by its `uid`, and the display name is
its `title`.

#### Scenario: a channel is named by any display name
- **GIVEN** the Add channel dialog on the Channels page
- **WHEN** the owner names a new Telegram channel "Team bot!" and connects it
- **THEN** the channel is registered with the title "Team bot!" and the name `team-bot`
- **AND** a second channel named "Team bot!" is registered as `team-bot-2` rather than refused

### Requirement: Check credentials before they are saved
The daemon MUST offer `POST /api/v1/channels/validate-credentials`, which asks a
chat platform whether a set of credentials works without storing, caching or
logging them and without starting a channel. The request names the platform and
the credentials as typed (a Telegram bot token, or a SeaTalk app secret with its
app id) and MAY name an existing channel by `channel_uid`. The answer is `ok`,
the bot it identified (`bot_handle`, `bot_name`; SeaTalk has no handle), and
`same_bot`: whether the credentials are that channel's own bot — a Telegram
token is compared by the bot id both tokens report, a SeaTalk secret by the app
id, which a replacement that omits it takes from the stored channel — and null
when there is nothing to compare, including when the stored secret cannot be
read. A refusal is an ordinary answer, `ok: false` with a `reason` (`missing`,
`rejected`, `unreachable` or `timeout`), never an error response. The platform
call MUST be bounded by a timeout of about eight seconds.

The Add channel and Replace token dialogs MUST call it once the person stops
typing: Add channel for a pasted Telegram token ("Found @bot", "The token works.
It will run on this Mac (name)."), Replace token or secret for the new value
("Works — this is @bot", and for the same bot "Same bot as before, so the
pairing with {owner} still holds."). A failure is stated under the field, and a
rejected value cannot be replaced. Connecting is never disabled for a missing
field: the form reports under each empty field when Connect is pressed.

#### Scenario: check a token as it is pasted
- **GIVEN** a Telegram bot token the platform accepts
- **WHEN** it is sent to `POST /api/v1/channels/validate-credentials`
- **THEN** the answer is `ok` with the bot's handle
- **AND** nothing is stored

#### Scenario: a replacement says whether it is the same bot
- **GIVEN** a Telegram channel whose stored token belongs to bot A
- **WHEN** a replacement token is checked against that channel
- **THEN** `same_bot` is true for a token of bot A and false for a token of bot B
- **AND** it is null when the stored token can no longer be read

#### Scenario: a refused or unreachable platform is reported, not raised
- **GIVEN** a token the platform rejects, and a platform that does not answer in time
- **WHEN** each is checked
- **THEN** the answers are `ok: false` with the reasons `rejected` and `timeout`, as normal responses

### Requirement: Add a channel in three steps and pair from the dialog that shows the code
The Add channel dialog MUST take three steps — Platform, Connect, Pair — under a
stepper that carries no accent colour. **Platform** lists each platform with its
logo, what connecting it needs, a one-line description and its capabilities, with
no filter and no count. **Connect** asks for a name, the default agent and the
platform's credentials, and registers the channel on Connect. **Pair** issues a
pairing code and waits for the owner's message; when someone pairs it turns into a
done state naming the owner, saying that the channel answers only them, and how
to try it with the default agent. "Pair later" leaves the step. A channel's
pairing codes appear only in this step and in the Add an owner dialog, which show
the code with Copy, where to send it, how long it lasts, the platform's one-tap
link where there is one, and a waiting line; an expired code is shown struck
through, says why, and offers a new one in place. With no channel at all the
Channels page keeps its header and offers the platforms as a bordered list that
opens the dialog at Connect.

#### Scenario: add a channel in three steps
- **GIVEN** the Add channel dialog on its Platform step
- **WHEN** a platform is chosen, the name and token are entered and Connect is pressed
- **THEN** a pairing code is shown with a waiting line
- **AND** when the owner sends it, the step names the owner and offers Done

#### Scenario: an expired pairing code is struck through in place
- **GIVEN** an Add an owner dialog whose code has expired
- **WHEN** it is read
- **THEN** the code is struck through and marked Expired with the reason
- **AND** it offers Cancel and Generate a new code

#### Scenario: a first run offers the platforms
- **GIVEN** no channel exists
- **WHEN** the Channels page is opened
- **THEN** it keeps its header and lists the platforms with what each needs
- **AND** choosing one opens Add channel at its Connect step

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

The channel MAY also name a default model for its default agent (Overview ›
Agents › Default model, stored as the default agent configuration's `model`).
It applies only while the default agent is the agent in effect: a thread whose
sticky agent is another one does not inherit it (the directory still applies),
a thread's own sticky model wins over it, and changing the channel's default
agent drops it.

#### Scenario: /new keeps the chat's model and directory
- **GIVEN** a paired chat whose owner set a model and an allowed
  directory from chat
- **WHEN** the owner sends `/new`
- **THEN** the fresh conversation runs on the same agent, model and
  directory

#### Scenario: the channel's default model applies only to its default agent
- **GIVEN** a channel whose default agent has a default model and a default directory
- **WHEN** a thread on the default agent opens a conversation, and another thread whose sticky agent is a different agent opens one
- **THEN** the first conversation opens on the default model
- **AND** the second opens with no model but on the default directory
- **AND** changing the channel's default agent removes the default model

#### Scenario: a group thread inherits the group's defaults
- **GIVEN** a group whose defaults name an agent
- **WHEN** the owner starts a new thread in that group
- **THEN** that thread's conversation opens on the group's agent

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

### Requirement: Report a channel that is starting apart from one that failed to start
The daemon starts an enabled channel on its next reconcile tick, so for a moment
after a channel is switched on (or bound to this machine) its adapter is not
running although nothing has failed. The channel status MUST carry `starting`,
true while the channel is enabled for this machine, not running, and no start
has yet been attempted, found it routes nowhere, or held it on its secret's
approval; it is false in every other case. A channel switched off or bound away
MUST forget its last start failure, so switching it back on starts a new run on
the next tick and does not report the previous run's failure. The Channels page
MUST show a starting channel as connecting — never as stopped or as a rejected
token or secret — including while the status it holds was read before the
switch; the Overview MUST NOT raise a "not running" item for it.

#### Scenario: a channel switched on reports starting until its first start attempt
- **GIVEN** a disabled channel
- **WHEN** the owner switches it on and its status is read before the daemon's next tick
- **THEN** the status reports `running: false` and `starting: true`, and the Channels page shows it connecting
- **AND** after the tick it is running and `starting` is false, while a start that failed leaves `starting` false

### Requirement: Show each paired person's platform picture
The people list on a channel's Overview SHALL show each paired person's picture
on the platform beside their name, and their initials when there is no picture
to show. The line under the name SHALL read "Owner · paired <date>". The picture
MUST be asked of the channel's running adapter on this machine when the page
first asks for it: Telegram's newest profile photo (`getUserProfilePhotos`), and
SeaTalk's employee profile picture (`/contacts/v2/profile`, which needs the app's
Get Employee Profile permission). It MUST be kept in a machine-local cache that
is never synced, served from there for a day, and asked for again after that. A
fetch that fails or is refused, and a person with no picture, MUST read as no
picture, show initials, and not be asked again for an hour; a refused refresh
leaves the cached picture in place. Only bytes that are a JPEG, PNG, GIF or WebP
image of at most 2 MB are served. Removing the person or deleting the channel
MUST drop their cached picture, and a person not paired to the channel has none.

#### Scenario: an owner row shows the person's platform picture or their initials
- **GIVEN** a channel with two paired people, one with a picture on the platform and one without
- **WHEN** the owner opens the channel's Overview
- **THEN** the first person's row shows their picture and the other's shows their initials
- **AND** the line under each name reads "Owner · paired <date>"

#### Scenario: a paired person's picture is fetched once and kept a day
- **GIVEN** a running channel and a paired person with a picture on the platform
- **WHEN** the page asks for the picture twice, and again a day later after the person changed it
- **THEN** the platform is asked once for the first two, and the day-old picture is replaced by the new one

#### Scenario: a person with no reachable picture keeps their initials
- **GIVEN** a SeaTalk app without the Get Employee Profile permission
- **WHEN** the page asks for a paired person's picture
- **THEN** there is no picture and the row keeps the person's initials
- **AND** the platform is not asked again for that person within the hour

#### Scenario: a paired person's picture is served from the running adapter
- **GIVEN** a running channel with two paired people, one with a picture
- **WHEN** a client reads `GET /api/v1/channels/{uid}/people/{sender_id}/avatar` for each, and for a sender who is not paired
- **THEN** the first answers 200 with the image, the others 204
- **AND** after the first person is removed their cached picture is gone

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

### Requirement: Ground a thread turn in a bounded slice of the thread
A thread turn MUST fold a bounded slice of its thread, never the whole thread,
and never what the conversation it runs in already saw. On a transport that can
read thread history, a message that lands in a thread folds in:

- on the **first turn of a conversation in that thread** — a new conversation
  (the thread's first, after `/new`, after an idle rollover or a deleted
  conversation), or a conversation `/resume` switched to that has had no turn
  there — the thread's **20 most recent messages** other than the triggering
  message, the bot's earlier replies included, under `[Thread messages]`;
- on **every later turn of that conversation in that thread**, only the messages
  posted **since that conversation's previous turn there**, leaving out the bot's
  own replies and the triggering message, under
  `[New thread messages since your last turn in this thread]` — at most the 20
  most recent of them — and **nothing at all** when there are none.

Where the conversation is in each thread is a per-conversation cursor (the
message that triggered its latest turn there) kept in `runs.db`, so it survives a
daemon restart. A message that roots a fresh thread at itself reads nothing but
still sets the cursor; a read that fails folds nothing and leaves the cursor
where it was. A quoted message is folded as before ("Ground a turn in the message
it quotes"). See the [chat architecture](../../../docs-site/architecture/chat.md)
page for where the cursor is taken and claimed.

#### Scenario: a conversation's first turn in a thread folds the thread's latest messages
- **GIVEN** a paired group on a transport that can read threads, and a thread of
  25 earlier messages
- **WHEN** the owner @mentions the bot in that thread for the first time
- **THEN** the turn opens with `[Thread messages]` and the 20 most recent of those
  messages, and the triggering message is not among them

#### Scenario: a later turn folds only what was posted since the previous turn
- **GIVEN** a conversation that already had a turn in a thread, after which the
  bot replied and two other members posted
- **WHEN** the owner @mentions the bot in that thread again
- **THEN** the turn folds only the two members' messages, under
  `[New thread messages since your last turn in this thread]`, without the
  earlier messages, the bot's reply or the triggering message

#### Scenario: a later turn with nothing new folds no thread context
- **GIVEN** a conversation that already had a turn in a thread, after which only
  the bot posted
- **WHEN** the owner @mentions the bot in that thread again
- **THEN** the turn carries no thread block, only the owner's message

#### Scenario: a new conversation in the thread is seeded again
- **GIVEN** a thread whose conversation already had a turn there
- **WHEN** the owner sends `/new` in the thread and then @mentions the bot
- **THEN** the new conversation's first turn folds the thread's latest messages
  again under `[Thread messages]`

#### Scenario: the thread cursor survives a daemon restart
- **GIVEN** a conversation that had a turn in a thread
- **WHEN** the daemon's cursor store is opened afresh over the same `runs.db`
- **THEN** it still holds that conversation's place in the thread: the message
  that triggered its turn

### Requirement: Read a thread's earlier messages on demand
Coffer MUST give an agent in a channel turn the built-in tool
`coffer__channel_read_thread`, which reads a thread's messages page by page,
newest page first. It takes the `channel` (name or uid), `chat_id`, `chat_kind`
and `thread_id` the turn's origin block names, an optional `before` (a message
id: return messages older than it) and a `limit` (1–100, default 20). It returns
the page oldest first — each message's id, sender, time, text, whether the bot
sent it, and the local paths of the images and files it carries, downloaded with
the bot's credentials — plus whether older messages remain, the `before` value
that reads them, and the platform's note on what it cannot return. It reads only
through a channel running on this machine, only a thread of a chat that channel
has paired (the owner's direct chat, or a group the owner has addressed the bot
in), and never a chat's main history. On a platform with no history API it
fails saying so. It is turn-scoped like `coffer__ask`: listed to and served for
only an MCP session inside a turn Coffer runs.

#### Scenario: an agent pages back through a thread with the tool
- **GIVEN** a paired group thread of eight messages on a transport that can read
  threads, one of which carries an image
- **WHEN** the agent calls the tool with a limit of 3, then again with the
  returned `before`, then once more
- **THEN** the pages hold the three newest, the three before them (the image as a
  local file path), and the remaining two with no more to read

#### Scenario: the tool reads only threads of paired chats
- **GIVEN** a running channel
- **WHEN** the agent calls the tool for a chat the channel has not paired, without
  a thread id, or for a channel that is not running
- **THEN** each call fails with a message saying why and nothing is read

#### Scenario: the tool says a platform without a history API cannot be read
- **GIVEN** a Telegram channel
- **WHEN** the agent calls the tool for one of its threads
- **THEN** the call fails saying the platform has no history API

#### Scenario: the tool is offered only inside a Coffer turn
- **GIVEN** the daemon is running
- **WHEN** one MCP session inside a live Coffer turn and one outside any turn list
  tools and call `coffer__channel_read_thread`
- **THEN** only the session inside the turn sees and runs it; outside it is an
  unknown tool

### Requirement: Name the model the default resolves to
Every place a channel shows its no-override model choice — `Default model` in the `/model` card and its text fallback, the reply to `/model default`, the settings line of `/status` and `/new`, and Provider default in the channel's Overview › Agents — MUST name the model it resolves to when Coffer can know it, as `Default model (<name>)` (`Provider default (<name>)` on the web), and MUST name none otherwise. The model is the agent's resolved default from [provider-switching](../provider-switching/spec.md) "Name the model a default resolves to", shown by the name its `/model` card button carries.

#### Scenario: the default model names the model it resolves to
- **GIVEN** a channel on an agent whose default resolves to `gpt-5-codex`, labelled `GPT-5 Codex`
- **WHEN** the owner sends `/model default` and then bare `/model`
- **THEN** the reply reads `Model: Default model (GPT-5 Codex) — from your next message` and the model text names `Default model (GPT-5 Codex)`
- **AND** for an agent whose default Coffer cannot know, the same replies read plain `Default model`

### Requirement: Commit a typed channel setting when its field is finished
On a channel's Settings tab, a value typed into a field (the title, a SeaTalk app id,
the two quiet windows, the idle period) MUST be saved when the person finishes the field,
on blur or Enter, never while they are still typing: a value passed on the way to another
("3" on the way to "32") MUST NOT be saved, so it never takes effect on the running channel
and never becomes a version in the vault. A finished value MUST be saved only when it is
valid and differs from the value last saved; leaving the tab saves a pending one.
Switches, choices and list edits keep saving as they change.

#### Scenario: a value half typed into a channel setting never takes effect
- **GIVEN** a channel whose wait after a text message is 1.5 seconds
- **WHEN** the owner types "3", pauses, types "2" and presses Enter
- **THEN** exactly one save is sent, carrying 32 seconds
- **AND** leaving the field afterwards sends nothing more
