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
surface MUST take the list from it. The registry names no feature today: Sync
(spec [vault-sync](../vault-sync/spec.md)), Knowledge (spec
[knowledge](../knowledge/spec.md)) and Memory (spec [memory](../memory/spec.md))
graduated and are always on. A capability outside the registry is always on.

A feature MUST join the registry by adding one entry that names its route
prefixes and the kinds it owns, and by tagging its other surfaces — built-in
tools, agent directories, attention sources, sidebar entries and background
passes — with its key. A feature MUST leave the registry by deleting its entry
and every gate and tag that names it, together with a migration that strips its
stored setting from the `features` object of `~/.coffer/daemon-config.json`,
keeping every other key. A stored setting for a key the registry does not name
MUST be ignored by every read — logged, never listed — and MUST NOT fail
anything.

#### Scenario: an empty registry lists no features
- **GIVEN** a running daemon whose registry names no feature
- **WHEN** `GET /api/v1/daemon/features` is requested and `coffer config list feature.` runs
- **THEN** the route lists no feature
- **AND** the command prints nothing and exits 0

#### Scenario: a stored setting for a feature the registry does not name is ignored
- **GIVEN** a daemon config whose `features` object holds a key the registry does not name
- **WHEN** the daemon starts and the features and the daemon status are read
- **THEN** the daemon starts, neither the features listing nor the status `features` map names the key, and no request fails because of it

#### Scenario: graduating a feature strips its stored setting
- **GIVEN** a daemon config whose `features` object holds `vault_sync`, `knowledge`, `memory` and one other key
- **WHEN** the upgrade's migrations run
- **THEN** the `features` object holds only the other key, and the rest of the file is unchanged
- **AND** a missing or unreadable daemon config is left alone

### Requirement: Decide a feature's state per machine
A feature's state MUST be decided in this order: a pin in `COFFER_FEATURES`,
then the machine's own setting in `~/.coffer/daemon-config.json`, then the
channel default — off on `stable`, on on `dev`. The setting MUST be kept on the
machine it was made on and MUST NOT sync. A write to a pinned feature MUST be
refused with 409 `FEATURE_PINNED`.

#### Scenario: a stable build starts with every experimental feature off
- **GIVEN** a `stable` build with a registered feature `f`, and no setting and no pin
- **WHEN** the features are listed
- **THEN** `f` is off, decided by the channel

#### Scenario: a machine setting overrides the channel default
- **GIVEN** a `stable` build with registered features `f` and `g` whose daemon config switches `f` on
- **WHEN** the features are listed
- **THEN** `f` is on, decided by the setting, and `g` is off, decided by the channel

#### Scenario: a pinned feature cannot be switched
- **GIVEN** a registered feature `f` and `COFFER_FEATURES=f=off`
- **WHEN** a request switches `f` on
- **THEN** it answers 409 `FEATURE_PINNED` and `f` stays off

### Requirement: Switch a feature from the settings page or the command line
A feature MUST be switchable from Settings → General while the registry names
any feature (see "List and switch the features on the General tab"), from
`coffer config set feature.<key> on|off`, and from
`PUT /api/v1/daemon/features/{key}`. `coffer config unset feature.<key>` MUST
remove the machine's own setting, so the feature returns to its channel
default. `coffer config list feature.` MUST list every registered feature with
its state and the layer that decided it — a pin, the setting or the channel.
The switch MUST take effect at once, with no daemon restart, and MUST be
written to the daemon config before the request answers.

#### Scenario: switching a feature on opens its surfaces without a restart
- **GIVEN** a running daemon with a registered feature `f` that owns route prefix `p`, switched off
- **WHEN** `coffer config set feature.f on` runs
- **THEN** a route under `p` answers on the same daemon process instead of 404 `FEATURE_DISABLED`
- **AND** the daemon config holds `f: true`

#### Scenario: unsetting a feature returns it to the channel default
- **GIVEN** a `dev` build whose daemon config switches a registered feature `f` off
- **WHEN** `coffer config unset feature.f` runs and then `coffer config list feature.`
- **THEN** the daemon config no longer holds a setting for `f`
- **AND** the listing names every registered feature, with `f` on and decided by the channel

### Requirement: Close every surface of a switched-off feature
While a feature is off: every REST route under a route prefix it names MUST
answer 404 with code `FEATURE_DISABLED` naming the feature; its MCP tools MUST
be absent from the tool list and a call to one MUST answer as a call to an
unknown tool; its CLI commands MUST print one line naming
`coffer config set feature.<key> on` and exit 1; its sidebar entry MUST be
absent, its pages and objects MUST be absent from the command palette, and its
pages MUST show a notice that says the feature is switched off; its own
background passes MUST skip their rounds. A resource whose kind the feature
owns MUST be out of reach of the kind-agnostic resource routes too: a route
naming such a kind, or a uid whose resource is of it, MUST answer 404
`FEATURE_DISABLED`, and a list MUST leave those resources out.

Switching a feature on is Coffer's own deterministic work, so a page's notice
MUST NOT name a command to run: it MUST offer a **Switch on** button that makes
the same write as the switch on Settings → General
(`PUT /api/v1/daemon/features/{key}`), after which the page itself renders with
no reload and no restart, and a way to open Settings. A feature that
`COFFER_FEATURES` pins cannot be switched there, so its notice MUST explain the
pin instead and offer no Switch on button.

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
- **WHEN** a `coffer` command that reads a route under `p` runs
- **THEN** it prints a line naming `coffer config set feature.f on` and exits 1

#### Scenario: a switched-off feature's page says it is switched off
- **GIVEN** a registered feature `f` whose sidebar entry opens a page, and `f` off
- **WHEN** the user follows a link to that page
- **THEN** the page shows a notice that `f` is switched off, in place of the page
- **AND** the notice names no command and offers a way to open Settings

#### Scenario: a switched-off feature's page switches it on in place
- **GIVEN** a registered feature `f` whose page shows the switched-off notice, and `f` not pinned
- **WHEN** the user presses Switch on
- **THEN** one `PUT /api/v1/daemon/features/f` switches it on and the page itself renders, with no reload

#### Scenario: a pinned feature's page explains the pin instead of switching
- **GIVEN** a registered feature `f` held off by `COFFER_FEATURES`
- **WHEN** the user opens its page
- **THEN** the notice says `COFFER_FEATURES` holds it off and offers no Switch on button

### Requirement: Keep what a switched-off feature holds
Switching a feature off MUST NOT delete, move or rewrite anything it holds —
resources, files, a configured remote, history. Switching it back on MUST resume
from that state.

#### Scenario: switching a feature off and on keeps what it holds
- **GIVEN** a registered feature `f` that owns kind `k`, a resource of kind `k`, and `f` on
- **WHEN** `f` is switched off and then on
- **THEN** the resource is listed exactly as before, and nothing it held was deleted

### Requirement: Withdraw what a switched-off feature put in front of agents
Anything a feature puts in front of agents or the user outside its own routes —
a hook it installs in an agent, a section of the `coffer-guide` skill, a channel
command, an attention mark on the web sidebar or the desktop shell — MUST leave
while the feature is off and come back when it is switched on. An attention
source tagged with the feature MUST NOT be asked while the feature is off. The
MCP handshake instructions MUST NOT name a built-in tool the tool list does not
carry.

#### Scenario: agents are told only about the tools they have
- **GIVEN** a built-in tool that the session's tool list does not carry
- **WHEN** an agent opens a gateway session
- **THEN** the handshake instructions do not name that tool

#### Scenario: a switched-off feature's attention source is not asked
- **GIVEN** an attention source tagged with a registered feature `f`, and `f` off
- **WHEN** the attention list is read
- **THEN** the source is not asked, none of its items is listed, and it is not reported as a failing source

### Requirement: List and switch the features on the General tab
While the registry names any feature, Settings → General MUST carry an
Experimental features card listing every registered feature with a switch, the
current state, and whether a pin or the channel decided it. A pinned feature's
switch MUST be disabled. A switch MUST move at once and settle on what the
daemon answers; a failed write MUST put it back and show the error beside it.
While no feature is registered the card MUST render nothing at all — no card
and no heading.

#### Scenario: the general tab switches a feature
- **GIVEN** the daemon reports a registered feature `f` off and unpinned
- **WHEN** the user turns its switch on
- **THEN** one request switches `f` on and its sidebar entry appears without a reload

#### Scenario: the general tab shows nothing while no feature is registered
- **GIVEN** a daemon whose registry names no feature
- **WHEN** the user opens Settings → General
- **THEN** the tab carries no Experimental features card and no heading for one

### Requirement: Mark an experimental feature's sidebar entry
While an experimental feature is switched on, its web sidebar entry MUST carry
a marker that says the feature is experimental, beside the label on an expanded
rail and in the tooltip on a collapsed one. An entry no registered feature owns
MUST NOT carry it.

#### Scenario: a switched-on feature's entry says it is experimental
- **GIVEN** a sidebar entry owned by a registered feature that is switched on
- **WHEN** the expanded sidebar renders
- **THEN** that entry carries the experimental marker and no other entry does
- **AND** with a registry that names no feature, no entry carries it
