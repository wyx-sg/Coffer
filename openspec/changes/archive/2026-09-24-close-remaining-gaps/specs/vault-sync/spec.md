## MODIFIED Requirements

### Requirement: Keep the working tree outside the vault
The working tree defaults to `~/.coffer/sync`. Every round mirrors the vault
into it and may `reset --hard` it, so it MUST NOT be at, inside or above any
vault directory (knowledge, skills, memory), nor at or above `~/.coffer` itself;
inside `~/.coffer` only the default location is accepted, and a relative path
MUST be refused. The working tree is set over REST (`PUT /api/v1/sync/remote`
`worktree_path`) and on the command line (`coffer sync remote set <url>
--worktree <path>`), and both refuse the same paths with the same reason.

#### Scenario: a working tree pointed inside the vault is refused
- **GIVEN** a request to configure the working tree at a knowledge or skills
  directory, or at `~/.coffer` itself, or at a relative path,
- **WHEN** the remote is configured with that working tree over REST, or with
  `coffer sync remote set <url> --worktree <path>`,
- **THEN** each is refused with the reason named — a 422 over REST, the route's
  message and the invalid-input exit code on the command line — and no remote is
  stored and no repository is created.

### Requirement: Cover the sync lifecycle on the command line
The CLI MUST cover the round and the vault's lifecycle — `coffer sync now`,
`adopt [<url>] [--keep-local] [--yes]`, `status`, `history [--limit]`,
`restore [--at <rev|date>]`, `confirm`, `reject`, `rebuild [--yes]`, `rollback`
— and its administration:
`remote set <url> [--branch] [--interval <seconds>] [--with-credentials|--without-credentials] [--credential-ref] [--worktree <path>]`,
`remote show`, `remote clear`, `machine list`, `machine rename <name>`,
`machine remove <id>`, `key export <file>`, `key import <file>`,
`key fingerprint`. An option `remote set` is not given keeps the stored remote's
value, the working tree included.

#### Scenario: the command line covers every sync operation
- **GIVEN** the `coffer sync` command group
- **WHEN** its commands and options are listed
- **THEN** it offers `now`, `adopt` with `--keep-local` and `--yes`, `status`, `history` with `--limit`, `restore` with `--at`, `confirm`, `reject`, `rebuild` with `--yes` and `rollback`
- **AND** it offers `remote set` with `--branch`, `--interval`, `--with-credentials`, `--without-credentials`, `--credential-ref` and `--worktree`, `remote show`, `remote clear`, `machine list`, `machine rename`, `machine remove`, `key export`, `key import` and `key fingerprint`

### Requirement: Report refs without a key as locked
A machine holding ciphertext without the key MUST report those refs **locked**
rather than failing decryption silently. Two absences MUST be told apart. A machine
that genuinely holds no master key can open none of its ciphertext, so every
credential ref it holds ciphertext for MUST be reported locked. A key that exists
but cannot be read right now (a locked or unavailable keychain, an unreadable key
file) says nothing about which refs would open, so the round MUST report none
and MUST log that the key was unreadable; the round is still recorded. The key
MUST be resolved at most once per daemon start, whichever of the three answers
it gives, so a key kept in the keychain costs at most one prompt.

#### Scenario: credentials this machine cannot decrypt are reported locked
- **GIVEN** a machine holding credential ciphertext written under a master key it does not hold
- **WHEN** a master key is imported that still does not decrypt them
- **THEN** the import names those refs as still locked rather than reporting success silently

#### Scenario: a machine with no master key reports every ref it holds as locked
- **GIVEN** a machine with no master key file and none in the keychain, holding credential ciphertext that arrived from another machine
- **WHEN** a converge round runs
- **THEN** the round's `locked_refs` names every credential ref this machine holds ciphertext for, and the round is recorded with them

#### Scenario: an unreadable key reports no ref locked
- **GIVEN** a machine holding credential ciphertext whose master key lives in a keychain that is locked
- **WHEN** a converge round runs
- **THEN** the round's `locked_refs` is empty, the unreadable key is logged, the round is recorded, and the keychain is not asked again on later rounds
