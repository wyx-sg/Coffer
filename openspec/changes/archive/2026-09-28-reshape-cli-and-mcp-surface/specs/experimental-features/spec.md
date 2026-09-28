## MODIFIED Requirements

### Requirement: Switch a feature from the settings page or the command line
A feature MUST be switchable from Settings → General, from
`coffer config set feature.<key> on|off`, and from
`PUT /api/v1/daemon/features/{key}`. `coffer config unset feature.<key>` MUST
remove the machine's own setting, so the feature returns to its channel
default. `coffer config list feature.` MUST list every registered feature with
its state and the layer that decided it — a pin, the setting or the channel.
The switch MUST take effect at once, with no daemon restart, and MUST be
written to the daemon config before the request answers.

#### Scenario: switching a feature on opens its surfaces without a restart
- **GIVEN** a running daemon with `vault_sync` off
- **WHEN** `coffer config set feature.vault_sync on` runs
- **THEN** `GET /api/v1/sync/status` answers 200 on the same daemon process
- **AND** the daemon config holds `vault_sync: true`

#### Scenario: unsetting a feature returns it to the channel default
- **GIVEN** a `dev` build whose daemon config switches `memory` off
- **WHEN** `coffer config unset feature.memory` runs and then `coffer config list feature.`
- **THEN** the daemon config no longer holds a setting for `memory`
- **AND** the listing names every registered feature, with `memory` on and decided by the channel

### Requirement: Close every surface of a switched-off feature
While a feature is off: its REST routes MUST answer 404 with code
`FEATURE_DISABLED` naming the feature; its MCP tools MUST be absent from the
tool list and a call to one MUST answer as a call to an unknown tool; its CLI
commands, including `coffer path knowledge` for `knowledge` and
`coffer path memory` for `memory`, MUST print one line naming
`coffer config set feature.<key> on` and exit 1; its sidebar entry MUST be
absent and its pages MUST show a notice that links to Settings → General; its
background passes MUST skip their rounds. A resource whose kind the feature
owns — `knowledge` owns the `knowledge` kind, `memory` the `memory` kind — MUST
be out of reach of the kind-agnostic resource routes too: a route naming such a
kind, or a uid whose resource is of it, MUST answer 404 `FEATURE_DISABLED`, and
a list MUST leave those resources out. While `vault_sync` is off the vault MUST
be treated as a single-machine one: the curation pass MUST NOT wait on a
curation owner machine or on a held or conflicted sync round.

#### Scenario: a switched-off feature's routes answer feature disabled
- **GIVEN** `knowledge` off
- **WHEN** `GET /api/v1/knowledge/collections` is requested
- **THEN** it answers 404 with code `FEATURE_DISABLED` and the key `knowledge`

#### Scenario: a switched-off feature's resources are out of reach of the resource routes
- **GIVEN** a knowledge collection and `knowledge` off
- **WHEN** the collection is read, changed or deleted through `/api/v1/resources/{uid}`, or the resources of kind `knowledge` are listed
- **THEN** each answers 404 with code `FEATURE_DISABLED` and the key `knowledge`
- **AND** an unfiltered list leaves the collection out and its folder stays in place

#### Scenario: a switched-off feature's tool leaves the tool list
- **GIVEN** `knowledge` off
- **WHEN** an agent lists the gateway's tools
- **THEN** `coffer__write` is absent
- **AND** a call to `coffer__write` answers as an unknown tool

#### Scenario: a switched-off feature's command says how to switch it on
- **GIVEN** `vault_sync` off
- **WHEN** `coffer sync status` runs
- **THEN** it prints a line naming `coffer config set feature.vault_sync on` and exits 1

#### Scenario: a switched-off feature's pass skips its round
- **GIVEN** `memory` off
- **WHEN** the aggregation worker reaches its interval
- **THEN** no aggregation pass runs

#### Scenario: curation does not wait on sync while vault sync is off
- **GIVEN** curation switched on, a curation owner naming another machine or an unresolved sync round, and `vault_sync` off
- **WHEN** the curation worker asks whether it may run
- **THEN** it may

### Requirement: Withdraw what a switched-off feature put in front of agents
Switching `memory` off MUST remove the memory delivery hook from every agent it
was installed in, and switching it on MUST install it again. Switching
`knowledge` off MUST rewrite the `coffer-guide` skill without its knowledge
catalogue, and a channel `/save` MUST answer that knowledge is switched off
without saving; switching it on MUST restore the catalogue. Switching
`vault_sync` off MUST stop every sync attention mark — the web sidebar's and the
desktop shell's — and remove the tray's Sync item. The MCP handshake
instructions and the `coffer-guide` skill MUST name only the tools the tool
list carries and only the directories a switched-on feature serves: while
`knowledge` is off neither names `coffer__write` nor the knowledge root, and
while `memory` is off neither names the memory root.

#### Scenario: switching memory off removes the delivery hook
- **GIVEN** an agent with the memory delivery hook installed
- **WHEN** `memory` is switched off
- **THEN** the hook is no longer in the agent's configuration
- **AND** switching `memory` on installs it again

#### Scenario: switching knowledge off drops the catalogue from the guide
- **GIVEN** an enabled collection catalogued in `coffer-guide`
- **WHEN** `knowledge` is switched off
- **THEN** the delivered `coffer-guide` carries no knowledge catalogue

#### Scenario: a channel save while knowledge is off saves nothing
- **GIVEN** a paired channel and `knowledge` off
- **WHEN** the owner sends `/save` with text
- **THEN** the reply says knowledge is switched off and nothing reaches any inbox

#### Scenario: agents are told only about the tools they have
- **GIVEN** `knowledge` and `memory` off
- **WHEN** an agent opens a gateway session and reads the delivered `coffer-guide`
- **THEN** neither the handshake instructions nor the guide name `coffer__write`, the knowledge root or the memory root
- **AND** switching `memory` on puts the memory root back in the guide, and switching `knowledge` on puts `coffer__write` back in both
