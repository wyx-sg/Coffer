## ADDED Requirements

### Requirement: Plan an import of agents' direct MCP entries
The daemon MUST plan an import of direct MCP entries chosen from the agents' own config files without writing anything — no file, no resource, no secret, no audit event — so the person sees what Import will do before it does it. The plan MUST list one server per distinct server: an entry whose transport matches a server Coffer already has is a duplicate (only the entry is removed, and its agent joins that server's reach when the server is scoped); entries sharing one transport across agents merge into one new server reaching the agents that had it; every other entry becomes a new server reaching its agent, under its name normalised to the rule a new server name follows, with a name that cannot be registered flagged. The plan MUST include, per agent config file that changes, the file's path and unified-diff hunks computed against its current text and the text removing the entries would write, with every shown line's secret values redacted — context lines included — and never the whole file. It MUST express the planned writes in the reconciler's change vocabulary and include any difference the reconciler has pending on Coffer's own entry for the agents involved.

#### Scenario: an import plan merges one server two agents share and writes nothing
- **GIVEN** two agents whose config files each hold a direct entry with the same command, one of them with a token in its environment
- **WHEN** the person plans importing both entries
- **THEN** the plan lists one new server reaching both agents, and a diff of each agent's file removing its entry in which the token's value does not appear
- **AND** both files are byte-identical afterwards, and no resource, secret or audit event was created

#### Scenario: an import plan removes only the duplicate of a server Coffer has
- **GIVEN** a registered server scoped to one agent and another agent whose config holds a direct entry with the same command
- **WHEN** the person plans importing that entry
- **THEN** the plan lists the server as already in Coffer, with that agent to be added to its reach, and adds no server

### Requirement: Apply an import of agents' direct MCP entries
Applying an import MUST perform the plan recomputed from the files as they are at that moment, never an entry a file no longer holds: each new server is adopted from its first entry per "Adopt a direct MCP entry into Coffer" (secret values moved into the secret store under `mcp/<agent>/<entry>/<KEY>` first) and its reach set to the agents that had it; every merged or duplicate entry is removed from its file per "Remove a direct MCP entry from its source file" after its agent joins the server's reach when the server is scoped. Each write is audited as its own route audits it. One entry failing MUST NOT stop the rest, and the answer MUST give every chosen entry its outcome — added, merged, duplicate removed, failed with a readable message, or skipped because it could not be imported — so a partial import can be reported.

#### Scenario: applying an import adds, merges and removes duplicates as planned
- **GIVEN** two agents holding the same direct entry, and one of them also holding the duplicate of a registered server
- **WHEN** the person applies importing all three entries
- **THEN** one new server reaching both agents is registered, the duplicate's agent can reach the registered server, and all three entries are gone from the agents' files
- **AND** each entry reports its outcome

#### Scenario: a partial import reports the entry that could not be imported
- **GIVEN** two chosen entries, one of which was removed from its file after the plan was shown
- **WHEN** the person applies the import
- **THEN** the other entry is imported, the removed one is reported as skipped with the reason, and nothing is written for it
