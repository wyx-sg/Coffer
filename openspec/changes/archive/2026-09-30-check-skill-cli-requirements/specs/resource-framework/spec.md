## MODIFIED Requirements

### Requirement: Report what needs a person across every kind
`GET /api/v1/attention` and `coffer attention` MUST list what needs a person
now, from every source whose experimental feature is on: the reconciler's
drift that a pass could not fix, MCP servers whose last test failed, whose
launcher is missing or whose cited secret is absent, agents whose program is
missing, whose connection is partial or who are not connected, a sync stopped on
a conflict or holding deletions, channels reconnecting, disconnected or not
running, and commands a skill requires that are missing, older than a skill's
minimum or not logged in (kind `cli`, the command as the uid). Each item MUST carry its kind, the resource's uid and title, a stable
reason code with one sentence, a severity (`error`, `warning`, `info`), when
the condition was first seen where that is known, and exactly one action: a
verb and the REST route and body the kind's own page uses — the list has no
write of its own. A source that fails MUST be reported beside the others'
items, and the answer MUST count the items per kind.

#### Scenario: each item carries one action from its kind's own page
- **GIVEN** an MCP server whose last test failed and a partially connected agent
- **WHEN** the user reads the attention list
- **THEN** the server's item offers `test` through `POST /api/v1/resources/mcp_server/{uid}/test`, the agent's offers `connect` through `POST /api/v1/agents/{uid}/coffer-connection`, errors sort before warnings, and the counts name one item for each kind

#### Scenario: a failing source does not hide the others
- **GIVEN** one source that raises and one that has an item
- **WHEN** the attention list is read
- **THEN** the item is listed and the failing source is reported with its error

#### Scenario: a switched-off feature's signals are left out
- **GIVEN** a sync stopped on a conflict and the `vault_sync` feature switched off
- **WHEN** the attention list is read
- **THEN** no sync item is listed

#### Scenario: a required command that needs attention is listed
- **GIVEN** a skill requiring `gh` with minimum `2.40` and `gh 2.30` installed
- **WHEN** the attention list is read
- **THEN** it carries one `cli` item for `gh` with reason `cli_outdated` whose action is `check` through `POST /api/v1/clis/gh/check`
- **AND** once `gh` is current, present and logged in, no `cli` item is listed
