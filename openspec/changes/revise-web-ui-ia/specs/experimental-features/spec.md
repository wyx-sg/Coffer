## RENAMED Requirements

- FROM: `### Requirement: Switch a feature from the settings page or the command line`
- TO: `### Requirement: Switch a feature from the command line`

## REMOVED Requirements

### Requirement: List and switch the features on the General tab
**Reason**: At 1.0 every experimental feature graduates and its switch is deleted, so Settings
carries no Experimental features card: the General tab holds display preferences only, and no
Settings tab lists features.
**Migration**: None in the web UI. The acceptance marker for "the general tab switches a feature"
is deleted with this requirement.

## MODIFIED Requirements

### Requirement: Switch a feature from the command line
A feature MUST be switchable from
`coffer config set feature.<key> on|off` and from
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
absent, its pages and objects MUST be absent from the command palette, and its
pages MUST show a notice that says the feature is switched off; its
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

#### Scenario: a switched-off feature's page says it is switched off
- **GIVEN** `memory` off
- **WHEN** the user follows a link to `/memory`
- **THEN** the page shows a notice that memory is switched off, in place of the page
