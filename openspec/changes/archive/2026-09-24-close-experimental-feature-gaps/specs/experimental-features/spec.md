## MODIFIED Requirements

### Requirement: Close every surface of a switched-off feature
While a feature is off: its REST routes MUST answer 404 with code
`FEATURE_DISABLED` naming the feature; its MCP tools MUST be absent from the
tool list and a call to one MUST answer as a call to an unknown tool; its CLI
commands MUST print one line naming `coffer daemon features enable <key>` and
exit 1; its sidebar entry MUST be absent and its pages MUST show a notice that
links to Settings → General; its background passes MUST skip their rounds.
A resource whose kind the feature owns — `knowledge` owns the `knowledge`
kind, `memory` the `memory` kind — MUST be out of reach of the kind-agnostic
resource routes too: a route naming such a kind, or a uid whose resource is of
it, MUST answer 404 `FEATURE_DISABLED`, and a list MUST leave those resources
out. While `vault_sync` is off the vault MUST be treated as a single-machine
one: the curation pass MUST NOT wait on a curation owner machine or on a held
or conflicted sync round.

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
- **GIVEN** `memory` off
- **WHEN** an agent lists the gateway's tools
- **THEN** `coffer__recall` is absent
- **AND** a call to `coffer__recall` answers as an unknown tool

#### Scenario: a switched-off feature's command says how to switch it on
- **GIVEN** `vault_sync` off
- **WHEN** `coffer sync status` runs
- **THEN** it prints a line naming `coffer daemon features enable vault_sync` and exits 1

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
list carries: while `knowledge` is off neither names `coffer__write` nor the
knowledge root, and while `memory` is off neither names `coffer__recall`.

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
- **THEN** neither the handshake instructions nor the guide name `coffer__write` or `coffer__recall`
- **AND** switching `memory` on puts `coffer__recall` back in the guide
