## MODIFIED Requirements

### Requirement: List every Coffer-hosted channel on one management surface
Coffer-hosted channels MUST have a unified management surface. A management
view lists every Coffer-hosted channel with its status, paired owner, agent, and
health, mirroring the MCP-server / memory / skill management surfaces; each
channel's credentials (bot tokens, app secrets) are held in the Coffer vault.
The Channels page holds each channel's setup, connection status and settings only: it shows no conversation history, and each channel links to the Conversations page filtered to that channel (spec [chat](../chat/spec.md) "Show every conversation on the Conversations page"). Externally-hosted channels are out of scope (a non-goal).

#### Scenario: the management surface lists each Coffer-hosted channel with status, owner, agent, and health
- **GIVEN** a registered and running Coffer-hosted channel with a paired owner
  and a routed agent
- **WHEN** the management surface reads the channel
- **THEN** it reports the channel's enabled status, its live health (adapter
  running), the paired owner, and the routed agent — mirroring the MCP-server /
  memory / skill management surfaces

#### Scenario: a channel links to its conversations instead of showing them
- **GIVEN** a SeaTalk channel with three conversations
- **WHEN** the user opens it on the Channels page
- **THEN** it shows its setup, connection status and settings and no conversation list, and its link opens the Conversations page filtered to that channel
