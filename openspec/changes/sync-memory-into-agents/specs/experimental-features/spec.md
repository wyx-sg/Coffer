## MODIFIED Requirements

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
