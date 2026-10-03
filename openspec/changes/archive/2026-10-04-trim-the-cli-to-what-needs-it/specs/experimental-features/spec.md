## MODIFIED Requirements

### Requirement: Declare the experimental features in one registry
Coffer MUST declare its experimental features in one registry, and every
surface MUST take the list from it. The registry names exactly four features,
in this order:

| Key | What it closes | REST prefixes | Kinds |
| --- | --- | --- | --- |
| `knowledge` | Knowledge | `/api/v1/knowledge` | `knowledge` |
| `memory` | Memory | `/api/v1/memory` | `memory` |
| `sync` | Vault sync | `/api/v1/sync` | none |
| `models` | Model providers (with its Usage tab) and the local model proxy | `/api/v1/providers`, `/api/v1/models`, `/api/v1/proxy`, `/api/v1/usage` | `provider` |

Everything else is always on: the shell, the Overview, Agents, the MCP gateway
and its custom tools, Skills, Secrets, Activity, Settings, Conversations and
Channels, the agent list and model catalogue routes (`/api/v1/agent-providers`),
the internal engine's settings, the vault's own routes and an agent's own
transcripts and native memory files. A capability outside the registry is
always on.

A feature MUST join the registry by adding one entry that names its route
prefixes and the kinds it owns, and by tagging its other surfaces — built-in
tools, agent directories, attention sources, sidebar entries and background
passes — with its key. A feature MUST leave the registry by deleting its entry
and every gate and tag that names it, together with a migration that strips its
stored setting from the `features` object of `~/.coffer/daemon-config.json`,
keeping every other key. A stored setting for a key the registry does not name
MUST be ignored by every read — logged, never listed — and MUST NOT fail
anything. A `features` object a person already holds is kept as it is.

#### Scenario: the registry names the four experimental features
- **GIVEN** a running daemon
- **WHEN** `GET /api/v1/daemon/features` is requested
- **THEN** the route lists exactly `knowledge`, `memory`, `sync` and `models`, in that order, each with its state and what decided it
- **AND** the daemon status `features` map names the same four keys

#### Scenario: a stored setting for a feature the registry does not name is ignored
- **GIVEN** a daemon config whose `features` object holds a key the registry does not name
- **WHEN** the daemon starts and the features and the daemon status are read
- **THEN** the daemon starts, neither the features listing nor the status `features` map names the key, and no request fails because of it

#### Scenario: leaving the registry strips its stored setting
- **GIVEN** a daemon config whose `features` object holds a key of a feature that has left the registry and one other key
- **WHEN** the upgrade's migrations run
- **THEN** the `features` object holds only the other key, and the rest of the file is unchanged
- **AND** a missing or unreadable daemon config is left alone

### Requirement: Switch a feature from the settings page or the command line
A feature MUST be switchable from Settings → Features and from
`PUT /api/v1/daemon/features/{key}`. `DELETE /api/v1/daemon/features/{key}` MUST
remove the machine's own setting, so the feature returns to off.
`GET /api/v1/daemon/features` MUST list every registered feature with its state
and the layer that decided it — a pin, the setting or the default. The switch
MUST take effect at once, with no daemon restart, and MUST be written to the
daemon config before the request answers.

#### Scenario: switching a feature on opens its surfaces without a restart
- **GIVEN** a running daemon with a registered feature `f` that owns route prefix `p`, switched off
- **WHEN** `PUT /api/v1/daemon/features/f` switches it on
- **THEN** a route under `p` answers on the same daemon process instead of 404 `FEATURE_DISABLED`
- **AND** the daemon config holds `f: true`

#### Scenario: unsetting a feature returns it to off
- **GIVEN** a daemon config that switches a registered feature `f` on
- **WHEN** `DELETE /api/v1/daemon/features/f` is requested and then `GET /api/v1/daemon/features`
- **THEN** the daemon config no longer holds a setting for `f`
- **AND** the listing names every registered feature, with `f` off and decided by the default

### Requirement: Close every surface of a switched-off feature
While a feature is off: every REST route under a route prefix it names MUST
answer 404 with code `FEATURE_DISABLED` naming the feature; its MCP tools MUST
be absent from the tool list and a call to one MUST answer as a call to an
unknown tool; its refusals and hints MUST name Settings → Features as where it is
switched on, and no command; its own background passes MUST
skip their rounds. A resource whose kind the feature owns MUST be out of reach
of the kind-agnostic resource routes too: a route naming such a kind, or a uid
whose resource is of it, MUST answer 404 `FEATURE_DISABLED`, and a list MUST
leave those resources out.

#### Scenario: a switched-off feature's routes answer feature disabled
- **GIVEN** a registered feature `f` that owns route prefix `p`, switched off
- **WHEN** a route under `p` is requested
- **THEN** it answers 404 with code `FEATURE_DISABLED` and the key `f`

#### Scenario: a switched-off feature's resources are out of reach of the resource routes
- **GIVEN** a registered feature `f` that owns kind `k`, a resource of kind `k`, and `f` off
- **WHEN** the resource is read, changed or deleted through `/api/v1/resources/{uid}`, or the resources of kind `k` are listed
- **THEN** each answers 404 with code `FEATURE_DISABLED` and the key `f`
- **AND** an unfiltered list leaves the resource out and what it holds on disk stays in place

#### Scenario: a switched-off feature's tool leaves the tool list
- **GIVEN** a built-in tool tagged with a registered feature `f`, and `f` off
- **WHEN** an agent lists the gateway's tools
- **THEN** the tool is absent
- **AND** a call to it answers as an unknown tool

#### Scenario: a switched-off feature's command says how to switch it on
- **GIVEN** a registered feature `f` that owns route prefix `p`, switched off
- **WHEN** a route under `p` is requested
- **THEN** the answer names Settings → Features as where to switch `f` on

### Requirement: Keep dependencies between features soft
No feature MUST hard-depend on another. Every link from one feature to another
MUST degrade when the other is off and MUST NOT fail: a surface that would
embed data of a switched-off feature MUST leave that section out.

#### Scenario: models off leaves knowledge and memory working
- **GIVEN** `models` off and an internal engine connection already chosen
- **WHEN** a knowledge or memory pass runs
- **THEN** it runs on the chosen connection and does not fail
- **AND** agents fall back to their own login

#### Scenario: memory off leaves knowledge and channels working
- **GIVEN** `memory` off and `knowledge` on
- **WHEN** knowledge is used and a channel turn runs
- **THEN** knowledge works as before and the channel turn answers with no memory

#### Scenario: knowledge off leaves memory and channels working
- **GIVEN** `knowledge` off and `memory` on
- **WHEN** memory is used and a channel turn runs
- **THEN** memory works as before and the channel turn answers, with `/kb` answering that Knowledge is switched off

#### Scenario: sync off leaves the vault single-machine
- **GIVEN** `sync` off
- **WHEN** curation runs, the engine's curate-owner is displayed in Settings, and a channel is read
- **THEN** curation and the display treat the vault as single-machine, and the channel stays bound to its machine
