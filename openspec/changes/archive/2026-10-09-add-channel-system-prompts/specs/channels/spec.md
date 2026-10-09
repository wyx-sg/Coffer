## ADDED Requirements

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

## MODIFIED Requirements

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
