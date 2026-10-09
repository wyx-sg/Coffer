# Experimental Features

## Purpose

Ship one build that carries every capability, and let each person decide which
of the not-yet-proven ones to try. A registry names the two experimental
features; each is off until the person switches it on, and the choice is made
per machine. A switched-off feature looks absent on every surface and loses
nothing it holds. The choice of feature gates over a separate release branch
is recorded in
[Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md).

## Requirements

### Requirement: Declare the experimental features in one registry
Coffer MUST declare its experimental features in one registry, and every
surface MUST take the list from it. The registry names exactly two features,
in this order:

| Key | What it closes | REST prefixes | Kinds |
| --- | --- | --- | --- |
| `knowledge` | Knowledge | `/api/v1/knowledge` | `knowledge` |
| `memory` | Memory | `/api/v1/memory` | — |

Everything else is always on: the shell, the Overview, Agents, the MCP gateway
and its custom tools, Skills, Secrets, Activity, Settings, Conversations,
Channels, vault sync, Model providers (with its Usage tab) and the local model
proxy, the agent list and model catalogue routes (`/api/v1/agent-providers`),
the internal engine's settings, the vault's own routes and an agent's own
transcripts and native memory files. A capability outside the registry is
always on.

A feature MUST join the registry by adding one entry that names its route
prefixes and the kinds it owns, and by tagging its other surfaces — built-in
tools, agent directories, attention sources, sidebar entries and background
passes — with its key. A feature MUST leave the registry by deleting its entry
and every gate and tag that names it, and by adding one entry to the table of
graduated features or the table of retired features (see "Move a graduated
feature's configuration and clean up a retired one's"). A stored setting for a
key the registry does not name and no table lists MUST be ignored by every read
— logged, never listed — and MUST NOT fail anything. A `features` object a
person already holds is kept as it is.

#### Scenario: the registry names the two experimental features
- **GIVEN** a running daemon
- **WHEN** `GET /api/v1/daemon/features` is requested
- **THEN** the route lists exactly `knowledge` and `memory`, in that order, each with its state and what decided it
- **AND** the daemon status `features` map names the same two keys

#### Scenario: a stored setting for a feature the registry does not name is ignored
- **GIVEN** a daemon config whose `features` object holds a key the registry does not name
- **WHEN** the daemon starts and the features and the daemon status are read
- **THEN** the daemon starts, neither the features listing nor the status `features` map names the key, and no request fails because of it

#### Scenario: a gate that still names a feature that left the registry fails loudly
- **GIVEN** a feature whose entry was deleted from the registry, a stored setting for it beside another stored key, and a tool tagged with it
- **WHEN** the features are read, the deleted feature's state is asked for and the tagged tool is registered
- **THEN** its routes and kind are no longer gated, its stored setting is logged and not listed, and the other key is kept
- **AND** asking for the deleted feature's state raises `FeatureUnknown` and registering the tagged tool raises `FeatureUnknown`, so a gate left behind is caught rather than silently open

### Requirement: Move a graduated feature's configuration and clean up a retired one's
A feature that graduates (becomes stable: always on, with no switch) leaves the
registry into a table of graduated features; its entry MAY name a mapping from
old top-level keys of `~/.coffer/daemon-config.json` to new ones. A feature that
is retired (removed) leaves the registry into a table of retired features; its
entry MAY name further top-level keys of that file. The daemon MUST apply both
tables to the daemon config once, at startup, before it reads the feature
settings: a graduated feature's switch is removed from the `features` object and
each mapped setting is moved to its new key, keeping a value already there; a
retired feature's switch and named settings are removed; every other key is
kept. The file MUST be rewritten atomically and only when something changed, and
one log line MUST be written per key moved or removed. A key may be in the
registry or in a table, never both.

`sync` (vault sync) and `models` (Model providers, the local model proxy and
Usage) have graduated: both are in the table of graduated features, neither
moves a setting, and both are always on.

#### Scenario: a graduated feature's switch is removed and its settings carry over at startup
- **GIVEN** a feature in the graduated table that maps old key `a` to `b`, and a daemon config holding its switch, `a` and another feature's switch
- **WHEN** the daemon starts
- **THEN** the config no longer holds the graduated feature's switch or `a`, holds `b` with `a`'s value, and still holds the other feature's switch
- **AND** one log line names the switch and one names the moved setting, and a second start rewrites nothing

#### Scenario: a retired feature's switch and settings are removed at startup
- **GIVEN** a feature in the retired table that names setting `s`, and a daemon config holding its switch, `s` and other keys
- **WHEN** the daemon starts
- **THEN** the config no longer holds the retired feature's switch or `s`, and every other key is kept
- **AND** one log line names each key removed

#### Scenario: the lifecycle tables never name a live feature
- **GIVEN** the registry and both tables
- **WHEN** their keys are compared
- **THEN** no key is in the registry and a table, and no key is in both tables

#### Scenario: sync and models graduated and their switches are removed at startup
- **GIVEN** a daemon config whose `features` object switches `sync` and `models` off and `knowledge` on, and `COFFER_FEATURES=sync=off,models=off`
- **WHEN** the daemon starts
- **THEN** the config no longer holds a `sync` or `models` switch and still holds `knowledge: true`
- **AND** the features listing names neither, the pin's two entries are logged and ignored, and the sync and provider routes answer as usual

### Requirement: Decide a feature's state per machine
A feature's state MUST be decided in this order: a pin in `COFFER_FEATURES`,
then the machine's own setting in `~/.coffer/daemon-config.json`, then the
default, which is off for every feature in every build. The reported source of
the state MUST be `pin`, `setting` or `default`. The setting MUST be kept on the
machine it was made on and MUST NOT sync. A write to a pinned feature MUST be
refused with 409 `FEATURE_PINNED`.

#### Scenario: every experimental feature starts off
- **GIVEN** a registered feature `f`, and no setting and no pin
- **WHEN** the features are listed
- **THEN** `f` is off, with source `default`

#### Scenario: a machine setting overrides the default
- **GIVEN** registered features `f` and `g` whose daemon config switches `f` on
- **WHEN** the features are listed
- **THEN** `f` is on with source `setting`, and `g` is off with source `default`

#### Scenario: a pinned feature cannot be switched
- **GIVEN** a registered feature `f` and `COFFER_FEATURES=f=off`
- **WHEN** a request switches `f` on
- **THEN** it answers 409 `FEATURE_PINNED` and `f` stays off

### Requirement: Switch a feature from the settings page or over REST
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

#### Scenario: a switched-off feature's refusal says how to switch it on
- **GIVEN** a registered feature `f` that owns route prefix `p`, switched off
- **WHEN** a route under `p` is requested
- **THEN** the answer names Settings → Features as where to switch `f` on

### Requirement: Make a switched-off feature look absent in the UI
While a feature is off, the web UI MUST show nothing that belongs to it: its
sidebar entries, and any sidebar group heading left empty, its pages and
objects in the command palette, its Overview tiles and first-run cards, its
kind in object-kind lists, and every section of another page that exists only
for it. A link to one of its pages MUST show the standard not-found page. The UI
MUST NOT show a notice that a feature is switched off or needs another, and MUST
NOT offer a switch-on button outside Settings → Features.

#### Scenario: a switched-off feature's page is not found
- **GIVEN** a registered feature `f` whose sidebar entry opens a page, and `f` off
- **WHEN** the user follows a link to that page
- **THEN** the standard not-found page shows, with no notice that `f` is switched off and no switch-on button

#### Scenario: a switched-off feature is absent from the navigation
- **GIVEN** a registered feature `f` that owns a sidebar entry, a palette page and an Overview tile, and `f` off
- **WHEN** the sidebar, the command palette and the Overview render
- **THEN** none of them shows anything of `f`, and a sidebar group left with no entry shows no heading

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

### Requirement: Close the knowledge feature's surfaces
While `knowledge` is off, `/api/v1/knowledge` MUST answer 404
`FEATURE_DISABLED` and the `knowledge` kind MUST be out of reach of the resource
routes. The `coffer-guide`
skill MUST be rendered without its knowledge catalogue, and switching
`knowledge` on MUST restore it. The knowledge sweep MUST
skip its rounds.

#### Scenario: knowledge off closes the knowledge routes
- **GIVEN** `knowledge` off
- **WHEN** a route under `/api/v1/knowledge` is requested
- **THEN** it answers 404 `FEATURE_DISABLED` naming `knowledge`

#### Scenario: knowledge off leaves coffer__search_tools the only built-in tool
- **GIVEN** `knowledge` off
- **WHEN** an agent opens a gateway session and lists the tools
- **THEN** the `coffer__` tools listed are `coffer__search_tools` alone, a call to any other `coffer__` tool answers as an unknown tool, and the handshake instructions name no knowledge tool

#### Scenario: knowledge off re-renders the coffer-guide skill without its knowledge sections
- **GIVEN** `knowledge` off
- **WHEN** the `coffer-guide` skill is rendered
- **THEN** it carries no knowledge catalogue, and the catalogue returns once `knowledge` is on

#### Scenario: knowledge off skips the knowledge sweep
- **GIVEN** `knowledge` off
- **WHEN** the knowledge sweep comes due
- **THEN** it skips its round

### Requirement: Keep dependencies between features soft
No feature MUST hard-depend on another. Every link from one feature to another
MUST degrade when the other is off and MUST NOT fail: a surface that would
embed data of a switched-off feature MUST leave that section out.

#### Scenario: memory off leaves knowledge and channels working
- **GIVEN** `memory` off and `knowledge` on
- **WHEN** knowledge is used and a channel turn runs
- **THEN** knowledge works as before and the channel turn answers with no memory

#### Scenario: knowledge off leaves memory and channels working
- **GIVEN** `knowledge` off and `memory` on
- **WHEN** memory is used and a channel turn runs
- **THEN** memory works as before and the channel turn answers

### Requirement: Show the Features tab in every build
Settings MUST carry a **Features** tab (`/settings/features`) in every build,
after General, Security, Data and Daemon, and before About. The tab MUST list every
registered feature, in registry order, with its name, an **Experimental** mark,
a one-line description, a switch showing its current state, and what decided
that state — a pin in `COFFER_FEATURES`, this machine's own setting, or the
default. A pinned feature's switch MUST be disabled. A switch MUST move at once
and settle on what the daemon answers; a failed write MUST put it back and show
the error beside it. Settings → General MUST carry no experimental-features
card.

#### Scenario: settings carry the Features tab
- **GIVEN** a running daemon
- **WHEN** the user opens Settings → Features
- **THEN** the tab lists `knowledge` and `memory` with name, Experimental mark, description, state and what decided it
- **AND** the Settings tab list is General, Security, Data, Daemon, Features and About

#### Scenario: the features tab switches a feature
- **GIVEN** the daemon reports a registered feature `f` off and unpinned
- **WHEN** the user turns its switch on
- **THEN** one request switches `f` on and its sidebar entry appears without a reload

#### Scenario: a pinned feature's switch is disabled
- **GIVEN** a registered feature held on or off by `COFFER_FEATURES`
- **WHEN** the user opens Settings → Features
- **THEN** its switch is disabled and the row says the pin decided its state

### Requirement: Mark an experimental feature's sidebar entry
While an experimental feature is switched on, its web sidebar entry MUST say the
feature is experimental in the tooltip of the collapsed rail ("Knowledge ·
Experimental"). The expanded row carries no tag beside its label — the
Experimental tag stays on the feature's page title and in Settings › Features —
and an entry no registered feature owns MUST NOT say it at all. The entries owned
by a feature are Knowledge (`knowledge`) and Memory (`memory`).

#### Scenario: a collapsed rail's tooltip says a feature's entry is experimental
- **GIVEN** a sidebar entry owned by a registered feature that is switched on
- **WHEN** the sidebar renders expanded, and again collapsed with the entry's tooltip open
- **THEN** the expanded row carries no experimental tag, and the collapsed row's tooltip names the entry followed by "Experimental"
- **AND** an entry no feature owns never says it

### Requirement: Close the memory feature's surfaces
While `memory` is off, `/api/v1/memory` MUST answer 404 `FEATURE_DISABLED`,
and the memory sync worker MUST skip its rounds, so nothing is read from an
agent, published to the hub or written into an agent. Switching `memory` off
MUST leave the hub and every copy already written into an agent where they are;
switching it on again MUST resume syncing at the next round, with no daemon
restart. The feature owns no resource kind and puts nothing in front of agents
of its own: there is no memory tool, no memory directory named in the gateway's
instructions or the `coffer-guide` skill, no hook, and no memory in a channel
turn, whether the feature is on or off
([memory](../memory/spec.md) "Deliver no memory into a session").

#### Scenario: memory off closes the memory routes
- **GIVEN** `memory` off
- **WHEN** a route under `/api/v1/memory` is requested
- **THEN** it answers 404 `FEATURE_DISABLED` naming `memory`

#### Scenario: memory off skips the memory sync
- **GIVEN** `memory` off
- **WHEN** the memory sync worker's round comes due
- **THEN** it skips the round and syncs nothing
- **AND** once `memory` is switched on, the next round runs
