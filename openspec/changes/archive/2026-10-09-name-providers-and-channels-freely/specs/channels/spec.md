## MODIFIED Requirements

### Requirement: Name a channel by any display name
A channel's name MUST be any display name a person types — spaces, capitals and
any script included — under the free-text rule of [resource-framework](../resource-framework/spec.md)
"Name a provider or a channel with free text": trimmed and NFC-normalised, 1 to 80 characters, no line
break or other control character, not starting with `-`, and unique among channels ignoring case. A
channel is registered under exactly the name typed, with no name derived from it, and carries no
separate title. A name that breaks the rule is refused as a validation error and one another channel
holds is refused with `RESOURCE_ALREADY_EXISTS` (409), in both cases with nothing registered or changed.
The name is renamable through the ordinary update (`PATCH /api/v1/resources/{uid}` with `name`): the
channel's Settings tab edits it as its Name, and every surface shows it. REST keeps addressing a
channel by its `uid`.

#### Scenario: a channel is named by any display name
- **GIVEN** the Add channel dialog on the Channels page
- **WHEN** the owner names a new Telegram channel "Team bot!" and connects it
- **THEN** the channel is registered with the name "Team bot!" exactly as typed, and its file is `local/resources/channel/<uid>.json`

#### Scenario: a second channel cannot take a name ignoring case
- **GIVEN** a channel named "Team bot!"
- **WHEN** the owner adds another channel named "team BOT!"
- **THEN** the registration is refused with `RESOURCE_ALREADY_EXISTS` (409) and no second channel exists

#### Scenario: a channel is renamed from its Settings tab
- **GIVEN** a channel named "Team bot!" with a paired owner
- **WHEN** the owner changes its Name to "Office bot" on the Settings tab
- **THEN** the channel is named "Office bot" everywhere, keeps its uid, pairing and file, and the rename is audited

### Requirement: Manage channels from the Channels page
The Channels page MUST be a list beside a detail pane. The **list** shows every
channel as one row — its platform, its name and one line saying what state it is
in — grouped by that state (needs attention, connected, off), filterable by name, with a way to register a new channel (storing
secrets through the secret store); a row opens the channel. The **detail pane**
MUST show the open channel's status (adapter running, paired peer, and the
inbound state the channel's type reports — for SeaTalk, its websocket
connection) in a header that is the same in every state: the platform mark, the
name, a status pill, a meta line saying how it connects, a secondary **Send test**
(a test notification to its paired owner, see "Notify the paired owner on
demand") and a ⋯ menu holding only **Reconnect** (see "Restart a channel's
adapter on demand"). A control that cannot run in the current state MUST be
disabled rather than hidden, and a disabled **Send test** MUST say why in its
tooltip. The fix for a problem MUST sit in a banner between the header and the
tabs — one banner, one fix button (Reconnect now, Replace token or secret, Take
it back, Retry, Open Secrets, Generate pairing code), and for a
missing SeaTalk SDK also the hand-off "Ask an agent" with Copy prompt behind
its chevron. A channel that is off is not a problem: it
MUST show a quiet grey box with one small button, Turn on, instead of a banner.
Replacing the secret and deleting live in the Settings tab. The detail pane MUST split into two tabs, in this order: **Overview**, the
default, at the bare `/channels/<uid>` — a single column of sections — who can use it (the paired owners as a bordered
list, each with Remove, and Add owner below it), the default agent, the agents the
channel may drive (its reach) and one link, **Conversations from this channel →**, to the
Conversations page filtered by `?source=<uid>` — the conversations themselves are listed there
only ([chat](../chat/spec.md) "Show every agent's sessions on the Conversations page"); it lists no commands — and **Settings**, at `/channels/<uid>/settings` — the
settings below, its secrets, and the channel's deletion. Choosing a tab
changes the address and nothing else.

Settings are saved as they change, with no save button and no saved line; a save
that fails says so in a toast and the field keeps what was typed. The one
exception is the channel's two system prompts (see "Append the owner's system
prompt to a channel turn"): they are prose, so their **System prompts** section
shows them as written and edits them through an **Edit** button and a dialog
with Cancel and Save. They cover the channel's name, its type's plain settings (a
SeaTalk app id), its two group-gating switches, `require_mention` and
`ignore_other_mentions` (see "Configure when the bot answers in a group"), and
the rest of what this requirement and the others in this spec name as a channel
setting. A secret is shown masked and replaced through its own dialog, **in
place**: the new value MUST be written to the secret store under the ref the
channel already cites before the configuration is saved, and that ref MUST stay in
the saved configuration, so a rotation moves no secret and leaves the channel's
pairing untouched. A secret left blank rotates nothing.

Registering, editing, enabling, disabling, scoping and deleting a channel are the framework's own
lifecycle operations (see [resource-framework](../resource-framework/spec.md)), done on the
Channels page and over `/api/v1/resources`; pairing, restarting and notifying are the
channel routes under `/api/v1/channels/{uid}`; the `coffer channel` commands call the same routes ([resource-framework](../resource-framework/spec.md) "Offer every management operation on the command line"). The page
MUST report the channel's configuration together with its status — adapter run state, paired
peer and the inbound state its type reports — with the group gating and the
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
  every ref unchanged, so nothing its pairing hangs off moves

#### Scenario: the group-gating switches are edited in the Settings tab
- **GIVEN** a registered channel with `require_mention` on and `ignore_other_mentions` off (the defaults)
- **WHEN** the owner switches `require_mention` off and `ignore_other_mentions` on in the channel's Settings tab
- **THEN** the saved configuration carries both changes and every other setting and ref as it was

#### Scenario: a channel's lifecycle and reach run through the resource routes
- **GIVEN** a registered, enabled channel named `tg`
- **WHEN** the user, on the Channels page or over `/api/v1/resources`, renames it to "Phone bot", scopes it to `codex` only, disables it and then deletes it
- **THEN** the name is saved with every ref unchanged, the channel's scope names only `codex`, and the adapter stops when it is disabled
- **AND** the removal deletes the channel and its peer binding, and each step is audited

#### Scenario: a channel's detail opens on Overview and keeps Settings on its own tab
- **GIVEN** a registered channel
- **WHEN** `/channels/<uid>/settings` is opened, and then the Overview tab is chosen
- **THEN** the first shows the channel's settings, and choosing Overview moves the address to the bare `/channels/<uid>`

#### Scenario: a channel's Overview links to its conversations instead of listing them
- **GIVEN** a channel that has started two conversations
- **WHEN** its Overview renders
- **THEN** it shows no list of conversations and one link, Conversations from this channel, to `/conversations?source=<uid>`

### Requirement: Commit a typed channel setting when its field is finished
On a channel's Settings tab, a value typed into a field (the name, a SeaTalk app id,
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

### Requirement: Open every turn with its message origin
Every turn MUST carry its own origin. The turn text opens with a
`[Message origin]` block naming the platform, the channel (as
`channel: "<name>" (id: <uid>)`: its current name, and the id that
`coffer__channel_read_thread` takes), the chat (kind, the chat title where
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
  the channel's name and id, the chat kind and title, the chat id, the thread id, and the sender

#### Scenario: a DM turn names its own chat
- **GIVEN** a paired channel and a DM from its owner
- **WHEN** the turn is driven
- **THEN** the origin block names the platform, the channel and the direct chat by
  id, omitting the thread line a DM has no value for

#### Scenario: the origin block carries the channel's id and the tool takes it
- **GIVEN** a channel named "Team bot!" with uid `U`
- **WHEN** a turn is driven and the agent calls `coffer__channel_read_thread` with `channel` set to `U`
- **THEN** the origin block's channel line reads `channel: "Team bot!" (id: U)` and the call reads that channel's thread
- **AND** the same call with `channel` set to "Team bot!" reads it too, and a rename of the channel never breaks a call that names its id

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

### Requirement: Read a thread's earlier messages on demand
Coffer MUST give an agent in a channel turn the built-in tool
`coffer__channel_read_thread`, which reads a thread's messages page by page,
newest page first. It takes the `channel` — the channel's id (the `id:` of the origin block's channel line; its name is accepted too) — `chat_id`, `chat_kind`
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
