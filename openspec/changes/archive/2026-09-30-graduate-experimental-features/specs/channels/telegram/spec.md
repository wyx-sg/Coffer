## RENAMED Requirements

- FROM: `### Requirement: Register command menus per chat scope and language`
- TO: `### Requirement: Register command menus per chat scope and language (before graduation)`

## REMOVED Requirements

### Requirement: Register command menus per chat scope and language (before graduation)
**Reason**: Knowledge graduated, so `kb` is always registered and the scenario "/kb leaves the menu while knowledge is off" no longer holds. A MODIFIED block cannot drop a scenario, so the requirement is renamed out of the way, removed, and added again under its own title (see ADDED below).
**Migration**: Its marker is deleted.

## ADDED Requirements

### Requirement: Register command menus per chat scope and language
The transport MUST register its command menus with `setMyCommands` per chat
scope: every command for private chats (`all_private_chats`, and the default
scope for clients that predate scopes), and only `new`, `stop`, `model`,
`status`, `resume` and `help` for groups (`all_group_chats`) — a group's menu
offers what is useful to tap in front of other people. Each scope is registered
twice, once with no `language_code` (the English descriptions) and once with
`zh` (the Chinese ones), so a Chinese Telegram client shows Chinese
descriptions. The hidden `/start` is never
listed.

#### Scenario: private chats get every command and groups the group set, in English and Chinese
- **GIVEN** a Telegram channel starting
- **WHEN** it registers its menus
- **THEN** the private-chat scope lists all nine commands and the group scope
  lists new, stop, model, status, resume and help, each once in English and once
  with `language_code` `zh`
