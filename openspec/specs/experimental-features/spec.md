# Experimental Features

## Purpose

Ship one build that carries every capability, and let each person decide which
of the not-yet-proven ones to try. A registry names the four experimental
features; each is off until the person switches it on, and the choice is made
per machine. A switched-off feature looks absent on every surface and loses
nothing it holds. The choice of feature gates over a separate release branch
is recorded in
[Experimental Features Instead of a Release Branch](../../../docs/decisions/experimental-features-instead-of-a-release-branch.md).

## Requirements

### Requirement: Declare the experimental features in one registry
Coffer MUST declare its experimental features in one registry, and every
surface MUST take the list from it. The registry names exactly four features,
in this order:

| Key | What it closes | REST prefixes | Kinds |
| --- | --- | --- | --- |
| `knowledge` | Knowledge | `/api/v1/knowledge` | `knowledge` |
| `memory` | Memory | `/api/v1/memory` | `memory` |
| `sync` | Vault sync | `/api/v1/sync` | none |
| `models` | Model providers, the local model proxy and Usage | `/api/v1/providers`, `/api/v1/models`, `/api/v1/proxy`, `/api/v1/usage` | `provider` |

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
- **WHEN** `GET /api/v1/daemon/features` is requested and `coffer config list feature.` runs
- **THEN** the route and the command list exactly `knowledge`, `memory`, `sync` and `models`, in that order, each with its state and what decided it
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

### Requirement: Switch a feature from the settings page or the command line
A feature MUST be switchable from Settings → Features, from
`coffer config set feature.<key> on|off`, and from
`PUT /api/v1/daemon/features/{key}`. `coffer config unset feature.<key>` MUST
remove the machine's own setting, so the feature returns to off.
`coffer config list feature.` MUST list every registered feature with its state
and the layer that decided it — a pin, the setting or the default. The switch
MUST take effect at once, with no daemon restart, and MUST be written to the
daemon config before the request answers.

#### Scenario: switching a feature on opens its surfaces without a restart
- **GIVEN** a running daemon with a registered feature `f` that owns route prefix `p`, switched off
- **WHEN** `coffer config set feature.f on` runs
- **THEN** a route under `p` answers on the same daemon process instead of 404 `FEATURE_DISABLED`
- **AND** the daemon config holds `f: true`

#### Scenario: unsetting a feature returns it to off
- **GIVEN** a daemon config that switches a registered feature `f` on
- **WHEN** `coffer config unset feature.f` runs and then `coffer config list feature.`
- **THEN** the daemon config no longer holds a setting for `f`
- **AND** the listing names every registered feature, with `f` off and decided by the default

### Requirement: Close every surface of a switched-off feature
While a feature is off: every REST route under a route prefix it names MUST
answer 404 with code `FEATURE_DISABLED` naming the feature; its MCP tools MUST
be absent from the tool list and a call to one MUST answer as a call to an
unknown tool; its CLI commands MUST print one line naming
`coffer config set feature.<key> on` and exit 1; its own background passes MUST
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
- **WHEN** a `coffer` command that reads a route under `p` runs
- **THEN** it prints a line naming `coffer config set feature.f on` and exits 1

### Requirement: Make a switched-off feature look absent in the UI
While a feature is off, the web UI MUST show nothing that belongs to it: its
sidebar entries, and any sidebar group heading left empty, its pages and
objects in the command palette, its Overview tiles and first-run cards, its
kind in object-kind lists, and every section of another page that exists only
for it. A link to one of its pages MUST show the standard not-found page. The UI
MUST NOT show a notice that a feature is switched off or needs another, and MUST
NOT offer a switch-on button outside Settings → Features. The Agents page's
Model tab and Settings → Coffer's model MUST omit what depends on `models`.

#### Scenario: a switched-off feature's page is not found
- **GIVEN** a registered feature `f` whose sidebar entry opens a page, and `f` off
- **WHEN** the user follows a link to that page
- **THEN** the standard not-found page shows, with no notice that `f` is switched off and no switch-on button

#### Scenario: a switched-off feature is absent from the navigation
- **GIVEN** a registered feature `f` that owns a sidebar entry, a palette page and an Overview tile, and `f` off
- **WHEN** the sidebar, the command palette and the Overview render
- **THEN** none of them shows anything of `f`, and a sidebar group left with no entry shows no heading

#### Scenario: a page omits the section that belongs to a switched-off feature
- **GIVEN** `models` off
- **WHEN** the user opens an agent's Model tab and Settings → Coffer's model
- **THEN** neither shows what depends on `models`, and neither shows a notice about it

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
routes. The `coffer__write` tool, which writes a knowledge document, MUST be
absent from the tool list and answer as an unknown tool. The `coffer-guide`
skill MUST be rendered without its knowledge catalogue and `coffer__write`
sections, and switching `knowledge` on MUST restore them. The curation pass MUST
skip its rounds. The channel `/kb` command MUST be out of `/help` and the menus
and answer that Knowledge is switched off, keeping any pending document.

#### Scenario: knowledge off closes the knowledge routes
- **GIVEN** `knowledge` off
- **WHEN** a route under `/api/v1/knowledge` is requested
- **THEN** it answers 404 `FEATURE_DISABLED` naming `knowledge`

#### Scenario: knowledge off hides the write tool
- **GIVEN** `knowledge` off
- **WHEN** an agent opens a gateway session and lists the tools
- **THEN** `coffer__write` is absent, a call to it answers as an unknown tool, and the handshake instructions do not name it

#### Scenario: knowledge off re-renders the coffer-guide skill without its knowledge sections
- **GIVEN** `knowledge` off
- **WHEN** the `coffer-guide` skill is rendered
- **THEN** it carries no knowledge catalogue or `coffer__write` section, and the sections return once `knowledge` is on

#### Scenario: knowledge off skips the curation pass
- **GIVEN** `knowledge` off
- **WHEN** the curation pass comes due
- **THEN** it skips its round

#### Scenario: knowledge off answers /kb as switched off
- **GIVEN** `knowledge` off and a channel conversation with a pending document
- **WHEN** the user sends `/kb`
- **THEN** `/kb` is absent from `/help` and the menus and answers that Knowledge is switched off, and the pending document is kept

### Requirement: Close the memory feature's surfaces
While `memory` is off, `/api/v1/memory` MUST answer 404 `FEATURE_DISABLED` and
the `memory` kind MUST be out of reach of the resource routes. The memory root
directory MUST be tagged `memory`, so the handshake does not name it, and the
`coffer-guide` skill MUST be rendered without its memory root section. The
memory delivery hook MUST be withdrawn from agents, and the agent connection
status MUST carry no `memory_hook` part. Switching `memory` on MUST install the
hook again into the connected agents and restore the section. The distil and
aggregate passes MUST skip their rounds. A channel turn MUST carry no memory
index or retrieval.

#### Scenario: memory off closes the memory routes
- **GIVEN** `memory` off
- **WHEN** a route under `/api/v1/memory` is requested
- **THEN** it answers 404 `FEATURE_DISABLED` naming `memory`

#### Scenario: memory off hides the memory root
- **GIVEN** `memory` off
- **WHEN** an agent opens a gateway session
- **THEN** the handshake instructions do not name the memory root, and the `coffer-guide` skill carries no memory root section

#### Scenario: memory off withdraws the memory delivery hook
- **GIVEN** `memory` on and a connected agent with the memory delivery hook installed
- **WHEN** `memory` is switched off
- **THEN** the hook is removed from the agent and its connection status carries no `memory_hook` part
- **AND** connecting an agent while `memory` is off leaves the hook out

#### Scenario: switching memory on installs the memory hook again
- **GIVEN** `memory` off and a connected agent without the hook
- **WHEN** `memory` is switched on
- **THEN** the hook is installed into the agent again, with no daemon restart

#### Scenario: memory off skips the distil and aggregate passes
- **GIVEN** `memory` off
- **WHEN** the distil and aggregate passes come due
- **THEN** each skips its round

#### Scenario: memory off leaves channel turns without memory
- **GIVEN** `memory` off and a channel conversation
- **WHEN** a turn runs
- **THEN** the turn carries no memory index or retrieval

### Requirement: Close the sync feature's surfaces
While `sync` is off, `/api/v1/sync` MUST answer 404 `FEATURE_DISABLED`, the
convergence worker MUST skip its rounds, and the sync attention source MUST be
tagged `sync` and not asked. Curation MUST treat the vault as single-machine:
the engine's curate-owner setting is ignored. The configured remote and the
history stay untouched.

#### Scenario: sync off closes the sync routes
- **GIVEN** `sync` off
- **WHEN** a route under `/api/v1/sync` is requested
- **THEN** it answers 404 `FEATURE_DISABLED` naming `sync`

#### Scenario: sync off skips convergence rounds and keeps the remote
- **GIVEN** `sync` on with a configured remote
- **WHEN** `sync` is switched off and the convergence worker comes due
- **THEN** it skips the round, the remote and the history are unchanged, and the sync attention source is not asked

#### Scenario: sync off treats the vault as single-machine for curation
- **GIVEN** `sync` off and an engine curate-owner setting naming another machine
- **WHEN** a curation pass comes due
- **THEN** the pass runs as on a single-machine vault, ignoring the curate-owner setting

### Requirement: Close the models feature's surfaces
While `models` is off, `/api/v1/providers` (including the price list),
`/api/v1/models`, `/api/v1/proxy` and `/api/v1/usage` MUST answer 404
`FEATURE_DISABLED` and the `provider` kind MUST be out of reach of the resource
routes. The local model proxy MUST be given an empty state and serve no agent.
The projection of provider connections into agents' own configuration MUST be
withdrawn: Coffer's keys MUST be removed from each agent's config files while
each agent record keeps its connection choice, and switching `models` on MUST
project them again. Usage ingest, the Codex quota loops and the price-list
refresh MUST skip their rounds. The routes of `/api/v1/agent-providers` and
`/api/v1/internal-engine-config` stay available.

#### Scenario: models off closes the provider, model, proxy and usage routes
- **GIVEN** `models` off
- **WHEN** a route under `/api/v1/providers`, `/api/v1/models`, `/api/v1/proxy` or `/api/v1/usage` is requested
- **THEN** each answers 404 `FEATURE_DISABLED` naming `models`
- **AND** `/api/v1/agent-providers` still answers

#### Scenario: models off serves no agent through the model proxy
- **GIVEN** `models` on with a connection the model proxy serves to an agent
- **WHEN** `models` is switched off
- **THEN** the proxy holds an empty state and a request through it is refused as for an agent with no connection

#### Scenario: models off withdraws the provider projection from agents
- **GIVEN** `models` on and an agent whose config files carry Coffer's projection of its chosen connection
- **WHEN** `models` is switched off
- **THEN** Coffer's keys are gone from the agent's config files and the agent falls back to its own login
- **AND** the agent record still names its connection choice

#### Scenario: switching models on projects the connection again
- **GIVEN** `models` off and an agent record that names a connection
- **WHEN** `models` is switched on
- **THEN** the connection is projected into the agent's config files again, with no daemon restart

#### Scenario: models off skips usage ingest and the price-list refresh
- **GIVEN** `models` off
- **WHEN** the usage ingest, the Codex quota loops and the price-list refresh come due
- **THEN** each skips its round

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
- **WHEN** curation runs, the engine's curate-owner is displayed with `coffer config`, and a channel is read
- **THEN** curation and the display treat the vault as single-machine, and the channel stays bound to its machine

### Requirement: Show the Features tab in every build
Settings MUST carry a **Features** tab (`/settings/features`) in every build,
after General, Security, Data, Daemon and About. The tab MUST list every
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
- **THEN** the tab lists `knowledge`, `memory`, `sync` and `models` with name, Experimental mark, description, state and what decided it
- **AND** the Settings tab list is General, Security, Data, Daemon, About and Features

#### Scenario: the features tab switches a feature
- **GIVEN** the daemon reports a registered feature `f` off and unpinned
- **WHEN** the user turns its switch on
- **THEN** one request switches `f` on and its sidebar entry appears without a reload

#### Scenario: a pinned feature's switch is disabled
- **GIVEN** a registered feature held on or off by `COFFER_FEATURES`
- **WHEN** the user opens Settings → Features
- **THEN** its switch is disabled and the row says the pin decided its state

### Requirement: Mark an experimental feature's sidebar entry
While an experimental feature is switched on, its web sidebar entry MUST carry
a marker that says the feature is experimental, beside the label on an expanded
rail and in the tooltip on a collapsed one. An entry no registered feature owns
MUST NOT carry it. The entries owned by a feature are Knowledge (`knowledge`),
Memory (`memory`), Sync (`sync`), and Model providers and Usage (`models`).

#### Scenario: a switched-on feature's entry says it is experimental
- **GIVEN** a sidebar entry owned by a registered feature that is switched on
- **WHEN** the expanded sidebar renders
- **THEN** that entry carries the experimental marker and no entry of a switched-off or unowned feature does
- **AND** Overview, Agents, MCP servers, Custom tools, Skills, CLIs, Secrets, Conversations, Channels and Activity never carry it
