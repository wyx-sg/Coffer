## MODIFIED Requirements

### Requirement: Close the models feature's surfaces
While `models` is off, `/api/v1/providers` (including the price list),
`/api/v1/models`, `/api/v1/proxy` and `/api/v1/usage` MUST answer 404
`FEATURE_DISABLED` and the `provider` kind MUST be out of reach of the resource
routes. The local model proxy MUST be given an empty state and serve no agent.
The projection of provider connections into agents' own configuration MUST be
withdrawn: Coffer's keys MUST be removed from each agent's config files while
each agent record keeps its connection choice, and switching `models` on MUST
project them again. Usage ingest and the price-list refresh MUST skip their
rounds. The routes of `/api/v1/agent-providers` and
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
- **WHEN** the usage ingest and the price-list refresh come due
- **THEN** each skips its round

### Requirement: Mark an experimental feature's sidebar entry
While an experimental feature is switched on, its web sidebar entry MUST say the
feature is experimental in the tooltip of the collapsed rail ("Knowledge ·
Experimental"). The expanded row carries no tag beside its label — the
Experimental tag stays on the feature's page title and in Settings › Features —
and an entry no registered feature owns MUST NOT say it at all. The entries owned
by a feature are Knowledge (`knowledge`), Memory (`memory`), Sync (`sync`), and
Model providers (`models`), whose page carries Usage as a tab.

#### Scenario: a collapsed rail's tooltip says a feature's entry is experimental
- **GIVEN** a sidebar entry owned by a registered feature that is switched on
- **WHEN** the sidebar renders expanded, and again collapsed with the entry's tooltip open
- **THEN** the expanded row carries no experimental tag, and the collapsed row's tooltip names the entry followed by "Experimental"
- **AND** an entry no feature owns never says it
