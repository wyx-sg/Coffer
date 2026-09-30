## MODIFIED Requirements

### Requirement: Manage channels from the Channels page and the CLI
The Channels page MUST list channels, register new ones (storing secrets
through the secret store), show each row's paired peer and health, set each
channel's reach (enable/disable and scope), bind each channel to the machine
that runs it (see "Bind each channel to the one machine that runs it"), and
delete a channel from its row. A channel's detail page MUST show its status
(adapter running, paired peer, and the inbound state the channel's type
reports — for SeaTalk, its websocket connection),
issue pairing codes, edit the channel, send a test notification to its paired
owner (see "Notify the paired owner on demand"), and delete it. The detail page
MUST split into two tabs, in this order: **Overview**, the default, at the bare
`/channels/<uid>` — the paired owner and re-pairing, the default agent, the
agents the channel may drive, and a link to the conversations it started — and
**Settings**, at `/channels/<uid>/settings` — the settings below, the machine
that runs it and its secrets. Choosing a tab changes the address and nothing
else.

Editing changes the channel's default agent, its type's plain settings (a
SeaTalk app id), its title and its two group-gating switches, `require_mention` and
`ignore_other_mentions` (see "Configure when the bot answers in a group"). Rotating an existing
secret happens **in place**: the new value MUST be written to the secret
store under the ref the channel already cites before the configuration is
saved, and that ref MUST stay in the saved configuration, so a rotation moves
no secret and leaves the channel's machine binding and pairing untouched. A
secret field left blank rotates nothing.

The CLI MUST offer these operations in the `coffer channel` group. Its uniform
lifecycle verbs are `list`, `show`, `add`, `edit`, `rm`, `enable`, `disable` and
`scope <name> [--agents a,b | --all | --none]` (see
[resource-framework](../resource-framework/spec.md), the requirement that
generates each kind's lifecycle verbs), and its channel-specific commands are
`pair`, `bind` and `notify`:

- `coffer channel show <name>` MUST report the channel's configuration together
  with its status — adapter run state, paired peer, machine binding and the
  inbound state its type reports — in plain and `--json` output.
- `coffer channel add` and `coffer channel edit` MUST take the group-gating
  switches as `--require-mention/--no-require-mention` and
  `--ignore-other-mentions/--no-ignore-other-mentions`. `edit` also takes
  `--name`, `--title` and `--description`, and it changes only what it is
  given: every switch, setting and ref it is not given keeps its stored value.
- `coffer secret set <ref>` rotates a secret under a ref that
  `coffer channel show` reports.

Editing a channel's default agent or type settings is served by the detail page
and `PATCH /api/v1/resources/{uid}`.

#### Scenario: register and list channels from the command line
- **GIVEN** a running daemon and a stored secret
- **WHEN** the user runs `coffer channel add` and `coffer channel list`
- **THEN** the channel is created and appears in the listing

#### Scenario: channel status reports runtime, pairing, and callback details
- **GIVEN** channels in various states
- **WHEN** the user queries status via REST and with `coffer channel show`
- **THEN** adapter run state, paired peer, and the channel type's own inbound
  state are reported accurately

#### Scenario: rotating a channel secret keeps its refs and pairing
- **GIVEN** a registered telegram channel whose bot token is stored under a
  secret ref
- **WHEN** the owner enters a new bot token in the channel detail page's edit
  dialog and saves
- **THEN** the new token is written under the channel's existing ref first
- **AND** the channel's configuration is then saved to the same channel with
  every ref unchanged, so nothing its pairing and binding hang off moves

#### Scenario: the group-gating switches are edited from the command line
- **GIVEN** a registered channel with `require_mention` on and `ignore_other_mentions` off (the defaults)
- **WHEN** the owner switches `require_mention` off and `ignore_other_mentions` on through `coffer channel edit`
- **THEN** the saved configuration carries both changes and every other setting and ref as it was

#### Scenario: a channel's lifecycle and reach run from its own command group
- **GIVEN** a registered, enabled channel named `tg`
- **WHEN** the user runs `coffer channel edit tg --title "Phone bot"`, `coffer channel scope tg --agents codex`, `coffer channel disable tg` and then `coffer channel rm tg`
- **THEN** the title is saved with every ref unchanged, the channel's scope names only `codex`, and the adapter stops when it is disabled
- **AND** the removal deletes the channel and its peer binding, and each step is audited

#### Scenario: a channel's detail opens on Overview and keeps Settings on its own tab
- **GIVEN** a registered channel
- **WHEN** `/channels/<uid>/settings` is opened, and then the Overview tab is chosen
- **THEN** the first shows the channel's settings, and choosing Overview moves the address to the bare `/channels/<uid>`
