## ADDED Requirements

### Requirement: Treat a command addressed to this bot by name as the command
A command a Telegram client sends from a group's menu arrives as
`/<command>@<bot username>`. When the username is this bot's own
(case-insensitively) the transport MUST hand the core `/<command>` with the
suffix removed and MUST count the message as addressed to the bot, so a group
that requires a mention still answers it. A command naming another bot is not
addressed to this one: in a group it is dropped like any un-addressed message.

#### Scenario: /cmd@thisbot runs the command
- **GIVEN** a paired Telegram group that requires a mention, and a bot named `CofferBot`
- **WHEN** the owner sends `/status@CofferBot`
- **THEN** the core receives an addressed `/status` and answers it

#### Scenario: /cmd@otherbot is not for this bot
- **GIVEN** a paired Telegram group and a bot named `CofferBot`
- **WHEN** the owner sends `/status@SomeOtherBot`
- **THEN** the message is not addressed to this bot and nothing answers it

### Requirement: Register command menus per chat scope and language
The transport MUST register its command menus with `setMyCommands` per chat
scope: every command for private chats (`all_private_chats`, and the default
scope for clients that predate scopes), and only `new`, `stop`, `model`,
`status`, `resume` and `help` for groups (`all_group_chats`) — a group's menu
offers what is useful to tap in front of other people. Each scope is registered
twice, once with no `language_code` (the English descriptions) and once with
`zh` (the Chinese ones), so a Chinese Telegram client shows Chinese
descriptions. `kb` is registered only while the knowledge feature is on, and
switching the feature re-registers the menus. The hidden `/start` is never
listed.

#### Scenario: private chats get every command and groups the group set, in English and Chinese
- **GIVEN** a Telegram channel starting with knowledge on
- **WHEN** it registers its menus
- **THEN** the private-chat scope lists all nine commands and the group scope
  lists new, stop, model, status, resume and help, each once in English and once
  with `language_code` `zh`

#### Scenario: /kb leaves the menu while knowledge is off
- **GIVEN** a Telegram channel starting with knowledge off
- **WHEN** it registers its menus
- **THEN** no scope lists `kb`
