## MODIFIED Requirements

### Requirement: Report what needs a person across every kind
`GET /api/v1/attention` MUST list what needs a person
now, from every source whose experimental feature is on: the reconciler's
drift that a pass could not fix, MCP servers whose last test failed (a server
whose key the upstream refused reads `mcp_key_rejected` and offers
`replace_key`, which opens the server's page where the key is replaced),
whose launcher is missing or whose cited secret is absent, agents whose program is
missing, whose connection is partial or who are not connected, whose Coffer memory hook the agent has not approved or has never run, a sync stopped on
a conflict or holding deletions, channels reconnecting, disconnected or not
running, model provider connections that an agent or Coffer's speech to text
runs on whose endpoint does not answer (`provider_unreachable`, offering
`check` through `POST /api/v1/providers/{uid}/check`, run in place) or refuses
the key (`provider_key_rejected`, offering `replace_key`, which opens the
connection's page) — read from the kept health verdict
([provider-switching](../provider-switching/spec.md) "Know each connection's
health without opening it"), only while `models` is on — and commands a skill
requires that are missing, older than a skill's minimum or not logged in (kind
`cli`, the command as the uid). Each item MUST carry its kind, the resource's uid and title, a stable
reason code with one sentence, a severity (`error`, `warning`, `info`), when
the condition was first seen where that is known, and exactly one action: a
verb and the REST route and body the kind's own page uses — the list has no
write of its own. Every item MUST also carry `handoff` (Principle IV,
AI-Native): the same prompt the kind's own page offers when its fix is a chore
for an agent — and its reason sentence MUST then name no command to run —
otherwise a prompt the daemon writes from the item's title, reason and action,
carrying no secret. Any item MAY be ignored on this machine by its stable key
([web-ui](../web-ui/spec.md) "Let the user ignore any item on Overview").
The route MUST serve each item's prompt as `handoff.prompt`, the text the web UI copies. A source that fails MUST be reported beside the others'
items, and the answer MUST count the items per kind.

#### Scenario: each item carries one action from its kind's own page
- **GIVEN** an MCP server whose last test failed and a partially connected agent
- **WHEN** the user reads the attention list
- **THEN** the server's item offers `test` through `POST /api/v1/resources/mcp_server/{uid}/test`, the agent's offers `connect` through `POST /api/v1/agents/{uid}/coffer-connection`, errors sort before warnings, and the counts name one item for each kind

#### Scenario: a rejected key is its own attention item
- **GIVEN** an enabled HTTP server whose last test failed with `auth_rejected`
- **WHEN** the user reads the attention list
- **THEN** the server's item reads `mcp_key_rejected` with the reason "Every call is rejected with 401 Unauthorized. The API key looks revoked.", offers `replace_key`, and still carries the diagnosis `handoff`

#### Scenario: every item carries a hand-off prompt
- **GIVEN** an attention item whose kind writes its own hand-off, and another whose source gives none
- **WHEN** the attention list is read
- **THEN** the first carries its kind's `handoff.prompt` and the second a prompt written from its title, reason and action, and the web UI copies exactly each text

#### Scenario: a failing source does not hide the others
- **GIVEN** one source that raises and one that has an item
- **WHEN** the attention list is read
- **THEN** the item is listed and the failing source is reported with its error

#### Scenario: a switched-off feature's signals are left out
- **GIVEN** an attention source tagged with a registered experimental feature that is switched off, holding an item it would report
- **WHEN** the attention list is read
- **THEN** that source's item is not listed and the source is not reported as failing

#### Scenario: a required command that needs attention is listed
- **GIVEN** a skill requiring `gh` with minimum `2.40` and `gh 2.30` installed
- **WHEN** the attention list is read
- **THEN** it carries one `cli` item for `gh` with reason `cli_outdated` whose action is `check` through `POST /api/v1/clis/gh/check`
- **AND** once `gh` is current, present and logged in, no `cli` item is listed

#### Scenario: a connection an agent runs on that fails is listed
- **GIVEN** Claude Code runs on connection A, whose verdict is `unreachable`, and connection B, which nothing runs on, whose verdict is `key_rejected`
- **WHEN** the attention list is read
- **THEN** it carries one `provider` item for A with reason `provider_unreachable` whose action is `check` through `POST /api/v1/providers/{uid}/check`, and none for B
- **AND** once A's verdict is `key_rejected`, its item reads `provider_key_rejected` and offers `replace_key`
