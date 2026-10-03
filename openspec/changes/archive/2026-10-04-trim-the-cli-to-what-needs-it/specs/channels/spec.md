## MODIFIED Requirements

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
secret. A replaced value held for approval changes nothing until it is approved,
and the restart follows the approval. Adapters, failure state and pending
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

### Requirement: Manage channels from the Channels page and the CLI
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
channel may drive (its reach) and the latest conversations it started, with an
Open Conversations link filtered by `?source=<uid>`; it lists no commands — and **Settings**, at `/channels/<uid>/settings` — the
settings below, the machine that runs it (see "Bind each channel to the one
machine that runs it") and its secrets, and the channel's deletion. Choosing a tab
changes the address and nothing else.

Settings are saved as they change, with no save button, and say whether the last
change was saved. They cover the channel's title, its type's plain settings (a
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
channel routes under `/api/v1/channels/{uid}`. Coffer has no `channel` command group. The page
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

#### Scenario: register and list channels from the command line
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
- **THEN** the settings carry every default (group gating, quiet windows, replies, idle period, directories)
- **AND** the Channels page shows them without a default of its own

#### Scenario: rotating a channel secret keeps its refs and pairing
- **GIVEN** a registered telegram channel whose bot token is stored under a
  secret ref
- **WHEN** the owner enters a new bot token in the channel's replace-token dialog
  and confirms
- **THEN** the new token is written under the channel's existing ref first
- **AND** the channel's configuration is then saved to the same channel with
  every ref unchanged, so nothing its pairing and binding hang off moves

#### Scenario: the group-gating switches are edited from the command line
- **GIVEN** a registered channel with `require_mention` on and `ignore_other_mentions` off (the defaults)
- **WHEN** the owner switches `require_mention` off and `ignore_other_mentions` on in the channel's Settings tab
- **THEN** the saved configuration carries both changes and every other setting and ref as it was

#### Scenario: a channel's lifecycle and reach run from its own command group
- **GIVEN** a registered, enabled channel named `tg`
- **WHEN** the user, on the Channels page or over `/api/v1/resources`, sets its title to "Phone bot", scopes it to `codex` only, disables it and then deletes it
- **THEN** the title is saved with every ref unchanged, the channel's scope names only `codex`, and the adapter stops when it is disabled
- **AND** the removal deletes the channel and its peer binding, and each step is audited

#### Scenario: a channel's detail opens on Overview and keeps Settings on its own tab
- **GIVEN** a registered channel
- **WHEN** `/channels/<uid>/settings` is opened, and then the Overview tab is chosen
- **THEN** the first shows the channel's settings, and choosing Overview moves the address to the bare `/channels/<uid>`

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
- A `runs_on` that **cannot be a machine id**, found when an existing vault is
  upgraded, MUST NOT be honoured as a binding. A channel's configuration is a bag
  the system has written other things into before — the retired machine axis put
  ULIDs under this very key — so a value of the wrong shape names no machine that
  has ever existed and is a fossil, not a decision. The upgrade MUST bind such a
  channel to this machine, the answer it would have given had the key been
  absent. This is the one case where an existing value is overwritten, and it is
  the one case where leaving it would silently stop a working bot on upgrade.
  Past the upgrade a value is written only by the surfaces, and they
  refuse an id the machine registry does not hold; whatever else ends up
  there fails closed and is reported as a binding to an unknown machine.
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
model, effort and directory carry over (see "Keep a chat's settings across its
conversations").

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

#### Scenario: the quiet windows are edited from the command line
- **GIVEN** a registered channel
- **WHEN** the owner sets the wait after a text message to 0 and the wait after a forward to 8 in the channel's settings
- **THEN** the channel's config holds those two windows and every other setting is unchanged

#### Scenario: the quiet windows are edited on the Channels page
- **GIVEN** a channel open in the Edit channel dialog
- **WHEN** the owner changes the wait after a text message and saves
- **THEN** the channel's config holds the new window and the other settings are unchanged

### Requirement: Choose the working directory from chat
The owner MUST be able to move a chat's conversation to another working
directory from chat — but only to a directory the channel allows. A channel's
Settings carry its Working directories: a **Default**, the absolute path new
conversations start in (stored as the default agent configuration's `cwd`; set
on the Channels page and cleared there; none means the Coffer workspace `~/.coffer/content/workspace`), and the list **Allowed for
/dir**, `directories`, absolute paths shown as rows with Remove and an Add
directory… folder picker, the default's row marked "default", and edited on the Channels page;
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
- **WHEN** the owner sets its directories in the channel's settings on the Channels page
- **THEN** the channel's configuration carries exactly those absolute paths, and
  removing every row clears them

#### Scenario: the channel's default directory is edited from the Channels page and the CLI
- **GIVEN** a registered channel
- **WHEN** the owner sets its Default working directory in the channel's settings on the Channels page
- **THEN** the channel's default agent configuration carries that absolute path as `cwd`, new conversations start there, and clearing the field removes it
- **AND** a relative path is refused with nothing saved, in the Default working directory and in the allowed list alike

### Requirement: Show a turn's working state as one status line
While a turn runs, its live surface MUST open with one status block the reader
can take in at a glance: a header saying that the turn is working, for how long,
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
tail shows only text written after the last tool call. The final reply keeps
every segment the agent wrote, with a paragraph break between the text either
side of a tool call, so two sentences never run together.

A channel setting `show_steps` (default on) hides the step lines and keeps the
header and narration — useful in a busy group. It is edited on the Channels
page.

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
- **WHEN** the owner switches the channel's step lines off in its settings, then on again
- **THEN** the channel's `show_steps` setting is off, then on again

### Requirement: Ping the asker when a long turn ends
A turn that ran at least the channel's `notify_after_seconds` (default 90, from
0 to 3600; 0 turns it off) MUST end with one short new message wherever its
answer would not notify on its own — that is, where the answer was delivered by
finishing a live surface that persists from the turn's start (see "Grow a reply
in place on one live surface"): a message created minutes ago notifies nobody
when it is finished. The ping reads `✅ Done · 4m 12s — <first line of the
answer>`, the first line read as plain words and clipped to 120 characters; a
turn that failed or was stopped pings `⚠️ Failed · …` or `⏹ Stopped · …` with the tool count and tokens, and
that ping takes the place of its separate summary. It is sent the way the turn's
other replies are — into the same chat and thread — and in a group it opens with
the asker's @mention (see "Mention the asker in a group answer"). A turn whose
answer went out as a new message (a scaffolding surface, or a stream that died
and fell back to the ordinary send) needs no ping: that message already
notified. A turn shorter than the threshold sends none either — the answer
itself is the signal.

Presence is not observable on any platform, so duration is the only signal. The
setting is edited on the Channels page.

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
- **WHEN** the owner sets the ping threshold to 0 in the channel's settings
- **THEN** the channel's threshold is 0, and a value past 3600 is refused

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
