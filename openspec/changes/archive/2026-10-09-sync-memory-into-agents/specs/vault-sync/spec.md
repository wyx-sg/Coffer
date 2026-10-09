## MODIFIED Requirements

### Requirement: Keep machine-local state out of the repository
Only `~/.coffer/vault/` is a repository. Everything true of one machine only
MUST be stored outside it: `local/` (agents, reach, the sync remote, retention,
the secret boundary's files, machine-local ciphertext, and what memory sync
wrote into this machine's agents), `content/` (media and
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

### Requirement: Withhold derived output in both halves
**Derived output MUST NOT converge, in either half**, and it cannot, because it
is stored under `derived/`, outside the vault. Coffer's own generated skill
`coffer-guide` is the case this exists for: its text is rendered locally from
the running build, the knowledge files and this machine's absolute paths, so
two machines holding identical files render different bytes, each correct where
it is. **Both halves** are
derived: its master folder (`derived/skills/coffer-guide/`) and its resource
file (`derived/resources/skill/coffer-guide.json`). Every other skill is in the
vault. Memory is not derived: the memory hub, `vault/memory/`, is vault content
and converges like any other vault file
([memory](../memory/spec.md) "Keep every agent's memories in a hub in the vault").

#### Scenario: a locally generated skill is neither published nor overwritten
- **GIVEN** Coffer's own skill and a person's imported skill
- **WHEN** each is filed
- **THEN** Coffer's own is stored under `derived/` and the person's under the vault, so only the person's can converge

### Requirement: Apply knowledge and skill file changes
What a round applies MUST be a checkout of the merged tree: an added or modified file
under `knowledge/`, `skills/`, `memory/`, `resources/`, `state/`,
`secret/` or `machines/` is written, and a deleted one removed, in the one
compare-and-swap step that refuses to overwrite a person's unsettled edit (see
"Never overwrite a person's unsettled edit"). Stores that read the vault reload
from the new `HEAD`, so an arriving resource file is a resource and an arriving
state document is in effect without any per-kind import step.

#### Scenario: an arriving file is written and a deleted one removed
- **GIVEN** two machines that each wrote a knowledge document
- **WHEN** both run rounds
- **THEN** each machine holds the other's document with the same bytes
