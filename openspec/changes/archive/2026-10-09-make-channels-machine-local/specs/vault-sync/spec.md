## MODIFIED Requirements

### Requirement: Converge shared state areas
Module-owned shared state that belongs to the vault rather than to one machine
MUST converge as vault state documents under `vault/state/<area>/`: MCP
capability switches (`state/mcp-preferences/<server>.json`) and Coffer's own
settings — the
speech-to-text model and the upkeep switches
(`state/settings/internal-engine.json`). A state document names its owner by
uid; an area with nothing but its defaults has no document. The plugin
inventory is not a state area: it is carried in each machine's descriptor (see
"Record plugins as an inventory, not a replicator").

#### Scenario: each shared state area reaches the working tree
- **GIVEN** a switched-off MCP capability and a non-default Coffer setting
- **WHEN** each is stored
- **THEN** each is a vault document under its area, named by its owner, and when each capability was first and last seen stays in `derived/`
- **AND** Coffer settings at their defaults have no document

### Requirement: Keep machine identity across reinstalls
`machine_id` MUST survive reinstalling and uninstalling Coffer. A machine that
comes back under a new identity becomes a ghost: it rejoins as a stranger, its
old descriptor lingers in the registry with nobody to update it, and anything
that named it silently stops meaning this machine.

#### Scenario: a machine identity survives reinstalling Coffer
- **GIVEN** a machine whose cached identity is lost, on a host that exposes a stable identifier
- **WHEN** its identity is resolved again and it joins the remote
- **THEN** it has the same machine id, the remote's registry holds it, and it joins as a returning machine rather than as a stranger

### Requirement: Converge resources as their own files
`mcp_server`, `skill`, `provider` and `knowledge` resources MUST
converge as their files, `vault/resources/<kind>/<name>.json` — the file is the
resource, not a serialization of a row kept elsewhere ([vault-storage](../vault-storage/spec.md)
"Identify a resource by the uid inside its file"). A resource file is identity,
title, description and config — what the resource *is*; what it reaches is not
in it (see "Keep reach machine-local"). Agents and channels are machine-local
and never converge: a channel's file, like an agent's, is under `local/`
([channels](../channels/spec.md) "Keep each channel on the machine that holds it"). The `title` is optional: a resource with no title has no `title` key.

#### Scenario: a resource document is identity, description and config
- **GIVEN** a registered resource with a description, a config and a reach of its own
- **WHEN** its file is read from the vault
- **THEN** the file holds its uid, kind, name, description and config
- **AND** it holds no `enabled` flag and no `scope`, and the vault's history never carries them

## REMOVED Requirements

### Requirement: Carry channel pairings as platform identity
**Reason**: A channel and its pairings are machine-local now and never travel.
**Migration**: On first start each machine moves its own channels' pairings from `state/channel-peers/` to `local/channel-peers.json`, and the vault's copies are deleted.

### Requirement: Carry a channel's file but not its adapter
**Reason**: A channel file no longer travels; it is under `local/` like an agent's, so there is nothing to carry and no machine binding.
**Migration**: On first start each machine moves the channels bound to it (or to no machine) to `local/resources/channel/`, without `runs_on`, and the vault's channel files are deleted.
