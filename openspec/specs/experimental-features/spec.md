# Experimental Features

## Purpose

Let `main` carry every capability while a release exposes only the ready ones.
Every build carries a release channel; a registry names the features that are
not ready yet; each machine decides for itself which of them are switched on;
and a switched-off feature is closed on every surface without losing anything
it holds. The owner tests everything from one line of development, and a
tagged release hands users only what is stable. The choice of feature gates
over a separate release branch is recorded in
[Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md).

## Requirements

### Requirement: Stamp every build with a release channel
Every build MUST carry exactly one release channel: `stable` for a build made by
the release workflow from a tag, `dev` for every other build, including a local
`make desktop` and a source install. `GET /api/v1/daemon/status` MUST report the
channel as `channel`, and `coffer daemon status` MUST print it.

#### Scenario: a source build reports the dev channel
- **GIVEN** a daemon started from a source checkout
- **WHEN** the status is requested
- **THEN** it reports `channel: "dev"`

#### Scenario: the release workflow stamps the stable channel
- **GIVEN** the channel stamp script run with `stable`
- **WHEN** the build channel is read
- **THEN** it is `stable`

### Requirement: Declare the experimental features in one registry
Coffer MUST declare its experimental features in one registry, and every
surface MUST take the list from it. The features are `vault_sync` (spec
[vault-sync](../vault-sync/spec.md)), `knowledge` (spec
[knowledge](../knowledge/spec.md)) and `memory` (spec
[memory](../memory/spec.md)). A capability outside the registry is always on.

#### Scenario: the registry names the three features
- **GIVEN** a running daemon
- **WHEN** `GET /api/v1/daemon/features` is requested
- **THEN** it lists exactly `vault_sync`, `knowledge` and `memory`, each with its state and the layer that decided it

### Requirement: Decide a feature's state per machine
A feature's state MUST be decided in this order: a pin in `COFFER_FEATURES`,
then the machine's own setting in `~/.coffer/daemon-config.json`, then the
channel default — off on `stable`, on on `dev`. The setting MUST be kept on the
machine it was made on and MUST NOT sync. A write to a pinned feature MUST be
refused with 409 `FEATURE_PINNED`.

#### Scenario: a stable build starts with every experimental feature off
- **GIVEN** a `stable` build and no setting and no pin
- **WHEN** the features are listed
- **THEN** every experimental feature is off, decided by the channel

#### Scenario: a machine setting overrides the channel default
- **GIVEN** a `stable` build whose daemon config switches `memory` on
- **WHEN** the features are listed
- **THEN** `memory` is on, decided by the setting, and the other two are off

#### Scenario: a pinned feature cannot be switched
- **GIVEN** `COFFER_FEATURES=knowledge=off`
- **WHEN** a request switches `knowledge` on
- **THEN** it answers 409 `FEATURE_PINNED` and `knowledge` stays off

### Requirement: Switch a feature from the settings page or the command line
A feature MUST be switchable from Settings → General, from
`coffer daemon features list|enable|disable`, and from
`PUT /api/v1/daemon/features/{key}`. The switch MUST take effect at once, with
no daemon restart, and MUST be written to the daemon config before the request
answers.

#### Scenario: switching a feature on opens its surfaces without a restart
- **GIVEN** a running daemon with `vault_sync` off
- **WHEN** `coffer daemon features enable vault_sync` runs
- **THEN** `GET /api/v1/sync/status` answers 200 on the same daemon process
- **AND** the daemon config holds `vault_sync: true`

### Requirement: Close every surface of a switched-off feature
While a feature is off: its REST routes MUST answer 404 with code
`FEATURE_DISABLED` naming the feature; its MCP tools MUST be absent from the
tool list and a call to one MUST answer as a call to an unknown tool; its CLI
commands MUST print one line naming `coffer daemon features enable <key>` and
exit 1; its sidebar entry MUST be absent and its pages MUST show a notice that
links to Settings → General; its background passes MUST skip their rounds.

#### Scenario: a switched-off feature's routes answer feature disabled
- **GIVEN** `knowledge` off
- **WHEN** `GET /api/v1/knowledge/collections` is requested
- **THEN** it answers 404 with code `FEATURE_DISABLED` and the key `knowledge`

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

### Requirement: Keep what a switched-off feature holds
Switching a feature off MUST NOT delete, move or rewrite anything it holds —
resources, files, a configured remote, history. Switching it back on MUST resume
from that state.

#### Scenario: switching knowledge off and on keeps the collections
- **GIVEN** a collection with documents and `knowledge` on
- **WHEN** `knowledge` is switched off and then on
- **THEN** the collection and its documents are listed exactly as before

### Requirement: Withdraw what a switched-off feature put in front of agents
Switching `memory` off MUST remove the memory delivery hook from every agent it
was installed in, and switching it on MUST install it again. Switching
`knowledge` off MUST rewrite the `coffer-guide` skill without its knowledge
catalogue, and a channel `/save` MUST answer that knowledge is switched off
without saving; switching it on MUST restore the catalogue. Switching
`vault_sync` off MUST stop every sync attention mark — the web sidebar's and the
desktop shell's — and remove the tray's Sync item.

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

### Requirement: List and switch the features on the General tab
Settings → General MUST carry an Experimental features card listing every
registered feature with a switch, the current state, and whether a pin or the
channel decided it. A pinned feature's switch MUST be disabled. A switch MUST
move at once and settle on what the daemon answers; a failed write MUST put it
back and show the error beside it.

#### Scenario: the general tab switches a feature
- **GIVEN** the daemon reports `knowledge` off and unpinned
- **WHEN** the user turns its switch on
- **THEN** one request switches `knowledge` on and the Knowledge sidebar entry appears without a reload
