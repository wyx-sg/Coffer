## MODIFIED Requirements

### Requirement: Converge shared state areas
Module-owned shared state that belongs to the vault rather than to one machine
MUST converge as vault state documents under `vault/state/<area>/`: MCP
capability switches (`state/mcp-preferences/<server>.json`), channel peer
pairings (`state/channel-peers/<channel>.json`) and Coffer's own settings — the
speech-to-text model and the upkeep switches
(`state/settings/internal-engine.json`). A state document names its owner by
uid; an area with nothing but its defaults has no document. The plugin
inventory is not a state area: it is carried in each machine's descriptor (see
"Record plugins as an inventory, not a replicator").

#### Scenario: each shared state area reaches the working tree
- **GIVEN** a switched-off MCP capability, a channel pairing and a non-default Coffer setting
- **WHEN** each is stored
- **THEN** each is a vault document under its area, named by its owner, and when each capability was first and last seen stays in `derived/`
- **AND** Coffer settings at their defaults have no document
