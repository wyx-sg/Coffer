## MODIFIED Requirements

### Requirement: Declare the experimental features in one registry
Coffer MUST declare its experimental features in one registry, and every
surface MUST take the list from it. The registry names exactly two features,
in this order:

| Key | What it closes | REST prefixes | Kinds |
| --- | --- | --- | --- |
| `knowledge` | Knowledge | `/api/v1/knowledge` | `knowledge` |
| `memory` | Memory | `/api/v1/memory` | `memory` |

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

## REMOVED Requirements

### Requirement: Close the sync feature's surfaces
**Reason**: Vault sync graduated; it is always on and has no switch.
**Migration**: None. The sync routes are always open and the convergence worker runs whenever a remote is configured; a stored `sync` switch is removed at startup.

### Requirement: Close the models feature's surfaces
**Reason**: Model providers graduated; they are always on and have no switch.
**Migration**: None. The provider, model, proxy and usage routes are always open, the projection into agents and the local model proxy always run; a stored `models` switch is removed at startup.
