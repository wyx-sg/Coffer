## MODIFIED Requirements

### Requirement: Manage channels from the Channels page and the CLI
The Channels page MUST list channels, register new ones (storing secrets
through the credential store), show each row's paired peer and health, set each
channel's reach (enable/disable and scope), bind each channel to the machine
that runs it (see "Bind each channel to the one machine that runs it"), and
delete a channel from its row. A channel's detail page MUST show its status
(adapter running, paired peer, and the inbound state the channel's type
reports — for SeaTalk, its websocket connection),
issue pairing codes, edit the channel, send a test notification to its paired
owner (see "Notify the paired owner on demand"), and delete it.

Editing changes the channel's default agent, its type's plain settings (a
SeaTalk app id) and its two group-gating switches, `require_mention` and
`ignore_other_mentions` (see "Configure when the bot answers in a group"). Rotating an existing
secret happens **in place**: the new value MUST be written to the credential
store under the ref the channel already cites before the configuration is
saved, and that ref MUST stay in the saved configuration, so a rotation moves
no secret and leaves the channel's machine binding and pairing untouched. A
secret field left blank rotates nothing.

The CLI MUST offer these operations across three command groups:
`coffer channel list / register / bind / pair / status / notify / set` for the
channel-specific ones — `register` and `set` take the group-gating switches as
`--require-mention/--no-require-mention` and
`--ignore-other-mentions/--no-ignore-other-mentions`, and `set` changes only
the switches it is given; the kind-agnostic `coffer resource show / enable /
disable / rename / delete channel <name>` and `coffer scope show / set channel
<name>` for its lifecycle and reach; and `coffer credentials set <ref>` for
rotating a secret under a ref that `coffer resource show` reports. Editing a
channel's default agent or type settings is served by the detail page and
`PATCH /api/v1/resources/{uid}`.

#### Scenario: register and list channels from the command line
- **GIVEN** a running daemon and a stored credential
- **WHEN** the user runs `coffer channel register` and `coffer channel list`
- **THEN** the channel is created and appears in the listing

#### Scenario: channel status reports runtime, pairing, and callback details
- **GIVEN** channels in various states
- **WHEN** the user queries status via REST and CLI
- **THEN** adapter run state, paired peer, and the channel type's own inbound
  state are reported accurately

#### Scenario: rotating a channel secret keeps its refs and pairing
- **GIVEN** a registered telegram channel whose bot token is stored under a
  credential ref
- **WHEN** the owner enters a new bot token in the channel detail page's edit
  dialog and saves
- **THEN** the new token is written under the channel's existing ref first
- **AND** the channel's configuration is then saved to the same channel with
  every ref unchanged, so nothing its pairing and binding hang off moves

#### Scenario: the group-gating switches are edited from the command line
- **GIVEN** a registered channel with `require_mention` on and `ignore_other_mentions` off (the defaults)
- **WHEN** the owner switches `require_mention` off and `ignore_other_mentions` on through `coffer channel set`
- **THEN** the saved configuration carries both changes and every other setting and ref as it was

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
