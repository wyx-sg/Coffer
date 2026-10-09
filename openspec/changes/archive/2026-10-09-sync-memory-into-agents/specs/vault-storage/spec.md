## MODIFIED Requirements

### Requirement: Store state in five classes by nature
Coffer SHALL store its state under `~/.coffer/` in five class directories
chosen by what the state is, not by which code writes it: `vault/` (the user's
configuration and content), `local/` (true of this machine only), `content/`
(media and the chat workspace), `runs.db` (history) and `derived/` (rebuilt
from other state). Only `vault/` MUST ever be committed or pushed; nothing
machine-local MUST be written under `vault/`, and nothing that is the only
copy of a fact MUST be written under `derived/`. Everything under `derived/` MUST be
rebuilt by the daemon when it is missing: removing the directory while the daemon is stopped
MUST NOT stop the next start, and that start MUST write it again. The reasoning is
[Storage Is Five Classes by Nature](../../../docs/decisions/storage-is-five-classes-by-nature.md).

#### Scenario: each class has its own directory
- **GIVEN** a running daemon
- **WHEN** a person lists `~/.coffer/`
- **THEN** it holds `vault/`, `local/`, `content/`, `derived/` and `runs.db`
- **AND** reach, the sync remote and retention settings are under `local/`, never under `vault/`

#### Scenario: deleting derived state loses nothing
- **GIVEN** a running vault with MCP health and skill delivery bindings under `derived/`
- **WHEN** `derived/` is deleted and the daemon restarts
- **THEN** every resource, secret, knowledge document and skill is still present
- **AND** the derived state is rebuilt

#### Scenario: clearing derived state rebuilds it
- **GIVEN** a stopped daemon whose `derived/` holds the health database and Coffer's own skill, delivered to an agent
- **WHEN** `derived/` is removed and the daemon starts again
- **THEN** the start succeeds, `derived/derived.db` and the skill's master folder exist again, and the agent's link into it works
- **AND** the person's own knowledge collections are unchanged
