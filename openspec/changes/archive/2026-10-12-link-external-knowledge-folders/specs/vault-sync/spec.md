## MODIFIED Requirements

### Requirement: Keep machine-local state out of the repository
Only `~/.coffer/vault/` is a repository. Everything true of one machine only
MUST be stored outside it: `local/` (agents, reach, the rows of linked
knowledge folders, the sync remote, retention, the secret boundary's files,
machine-local ciphertext, and what memory sync wrote into this machine's
agents), `content/` (media and
the chat workspace), `runs.db` (conversations, the audit log, MCP invocation
records, rounds, usage), `derived/` (everything rebuilt),
and `daemon-config.json`, `daemon.json`, the master key and logs directly under
`~/.coffer` ([vault-storage](../vault-storage/spec.md) "Store state in five
classes by nature"). The master key MUST **never** be written into the vault
(see "Never write the master key into the repository").

#### Scenario: machine-local files never reach the working tree
- **GIVEN** an agent, a machine-local resource and a derived one registered on a machine, and a migrated home's reach, retention and remote settings
- **WHEN** the vault's history and tree are read
- **THEN** none of them is in the vault: each is a file under `local/` or `derived/`
