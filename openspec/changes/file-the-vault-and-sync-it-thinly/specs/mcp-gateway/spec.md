## MODIFIED Requirements

### Requirement: Preserve capability decisions
The system MUST preserve the user's enable/disable decisions across daemon restarts, upstream upgrades, and
upstream temporary disappearances. A capability is discovered live from the upstream; only the user's
decisions and when each capability was seen are persisted. A capability switched off is listed in its
server's preference document in the vault, `state/mcp-preferences/<server name>.json`, which carries the
server's uid; when this machine first and last saw each capability is a derived record of this machine's,
in `~/.coffer/derived/derived.db`, because it is a fact about what this machine's upstream offered.

#### Scenario: capability preferences survive upstream changes
- **GIVEN** the user has disabled a tool on a server,
- **WHEN** the upstream server is upgraded so that tool's schema changes (or it briefly disappears and returns),
- **THEN** the user's disabled state is preserved without manual re-configuration.

### Requirement: Enable newly discovered capabilities
The system MUST enable a previously unseen capability by default when it is discovered, leaving it to
"Toggle individual capabilities" to curate. There is no per-server auto-enable policy.

#### Scenario: a newly discovered capability is enabled by default
- **GIVEN** a registered server whose capabilities have already been discovered,
- **WHEN** an upgrade adds a new tool to that server,
- **THEN** the new tool is enabled, its first sighting on this machine is recorded as its `first_seen_at`, and the user can disable it through the per-capability toggle ("Toggle individual capabilities").

### Requirement: Re-enable a server when its preference document is deleted
A server's preference document, `state/mcp-preferences/<server name>.json` in the vault, is this spec's, so
this spec defines what deleting it means ([vault-sync](../vault-sync/spec.md) "Converge shared state areas").
The document carries the server's uid and exists only while something on that server is disabled; deleting
it — by hand, or by a sync round that brings another machine's re-enabling — therefore means "nothing is
disabled here", and Coffer MUST re-enable every capability on that server. When each capability was seen
MUST stay: it is this machine's own derived record of what the server offered, not a decision another machine
took back. For the same reason this spec MUST NOT write a document for a server with nothing disabled, or a machine that re-enabled everything and a machine that never
disabled anything would add and delete the same document at each other every round.

#### Scenario: deleting a server's preference document re-enables everything on it
- **GIVEN** two registered servers that each have a disabled capability,
- **WHEN** the preference document of one of them is deleted by a sync commit,
- **THEN** every capability on that server is enabled again, and each is still listed with when it was seen,
- **AND** the other server's disabled capability is untouched, and no preference document is written back for the server with nothing disabled.

### Requirement: Switch off or narrow one custom tool
A custom tool switched off, or whose **reach override** does not admit the
session's agent, MUST be left out of `tools/list` and of
`coffer__search_tools` results, and a call on it MUST be recorded as `denied`
and answered with TOOL_DISABLED. A reach override is a list of agent uids that
narrows the group's reach for that one tool — an agent the group does not
reach is not reached by any of its tools — and, like every reach, it is kept on
this machine only, in `~/.coffer/local/tool-reach.json`, and never travels with sync. Removing a tool or its group
MUST remove its override.

#### Scenario: a switched-off custom tool is hidden and refused
- **GIVEN** a group with two tools, one switched off
- **WHEN** an agent lists the tools and then calls the switched-off one by its name
- **THEN** only the other tool is listed, and the call is refused with TOOL_DISABLED and recorded as `denied`

#### Scenario: a reach override hides one tool from one agent
- **GIVEN** a group reaching Claude Code and Codex, and one tool overridden to Claude Code only
- **WHEN** each agent lists the tools
- **THEN** Codex is offered every tool but that one, and Claude Code is offered all of them
- **AND** the override is absent from what the vault syncs
