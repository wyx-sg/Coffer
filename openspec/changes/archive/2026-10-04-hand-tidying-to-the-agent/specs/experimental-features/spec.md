## MODIFIED Requirements

### Requirement: Make a switched-off feature look absent in the UI
While a feature is off, the web UI MUST show nothing that belongs to it: its
sidebar entries, and any sidebar group heading left empty, its pages and
objects in the command palette, its Overview tiles and first-run cards, its
kind in object-kind lists, and every section of another page that exists only
for it. A link to one of its pages MUST show the standard not-found page. The UI
MUST NOT show a notice that a feature is switched off or needs another, and MUST
NOT offer a switch-on button outside Settings → Features. An agent's
Overview › Model section and the Speech-to-text section of Settings › General MUST omit what depends on `models`:
the Model section is read-only, with no Provider row and no Change…, and Speech-to-text offers no connection choice.

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
- **WHEN** the user opens an agent's Overview and Settings › General
- **THEN** the Model section shows the agent's own model read-only, with no Provider row and no Change…, and Speech-to-text shows no connection choice
- **AND** neither shows a notice about it, and `?change-model=1` opens no dialog

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

#### Scenario: knowledge off skips the curation pass
- **GIVEN** `knowledge` off
- **WHEN** the knowledge sweep comes due
- **THEN** it skips its round

### Requirement: Close the memory feature's surfaces
While `memory` is off, `/api/v1/memory` MUST answer 404 `FEATURE_DISABLED` and
the `memory` kind MUST be out of reach of the resource routes. The memory root
directory MUST be tagged `memory`, so the handshake does not name it, and the
`coffer-guide` skill MUST be rendered without its memory root section. The
memory delivery hook MUST be withdrawn from agents, and the agent connection
status MUST carry no `memory_hook` part. Switching `memory` on MUST install the
hook again into the connected agents and restore the section. The aggregate and
distil passes MUST skip their rounds, and a note's retirement marker is not acted on while they are skipped. A channel turn MUST carry no memory
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
- **WHEN** the aggregate and distil passes come due
- **THEN** each skips its round

#### Scenario: memory off leaves channel turns without memory
- **GIVEN** `memory` off and a channel conversation
- **WHEN** a turn runs
- **THEN** the turn carries no memory index or retrieval

### Requirement: Close the sync feature's surfaces
While `sync` is off, `/api/v1/sync` MUST answer 404 `FEATURE_DISABLED`, the
convergence worker MUST skip its rounds, and the sync attention source MUST be
tagged `sync` and not asked. The configured remote and the
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
- **GIVEN** `sync` off
- **WHEN** the knowledge sweep comes due
- **THEN** the sweep runs as on a single-machine vault

### Requirement: Keep dependencies between features soft
No feature MUST hard-depend on another. Every link from one feature to another
MUST degrade when the other is off and MUST NOT fail: a surface that would
embed data of a switched-off feature MUST leave that section out.

#### Scenario: models off leaves knowledge and memory working
- **GIVEN** `models` off
- **WHEN** the knowledge sweep and the aggregate and distil passes run
- **THEN** they run and do not fail, because none of them calls a model
- **AND** agents fall back to their own login

#### Scenario: memory off leaves knowledge and channels working
- **GIVEN** `memory` off and `knowledge` on
- **WHEN** knowledge is used and a channel turn runs
- **THEN** knowledge works as before and the channel turn answers with no memory

#### Scenario: knowledge off leaves memory and channels working
- **GIVEN** `knowledge` off and `memory` on
- **WHEN** memory is used and a channel turn runs
- **THEN** memory works as before and the channel turn answers

#### Scenario: sync off leaves the vault single-machine
- **GIVEN** `sync` off
- **WHEN** the knowledge sweep runs and a channel is read
- **THEN** the sweep commits as on a single-machine vault, and the channel stays bound to its machine
