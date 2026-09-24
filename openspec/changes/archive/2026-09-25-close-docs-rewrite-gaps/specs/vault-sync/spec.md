## MODIFIED Requirements

### Requirement: Allow at most one user-owned sync remote
A vault MUST have **at most one** sync remote: a git repository the user owns,
configured with a URL, a branch, a push credential reference, an interval, and
whether credential ciphertext rides along. Sync MUST be disabled until the user
configures it. The interval MUST be at least 60 seconds: a shorter one is
refused on every surface that sets it — the route, `coffer sync remote set
--interval` and the web form — before anything is stored.

#### Scenario: sync stays off until a remote is configured
- **GIVEN** a vault with no sync remote configured
- **WHEN** a round is requested
- **THEN** the round is reported as disabled and nothing is committed or pushed
- **AND** configuring a remote a second time replaces the first rather than adding another

#### Scenario: an interval under a minute is refused
- **GIVEN** a configured sync remote with a 300-second interval
- **WHEN** the remote is set again with an interval of 59 seconds, through the route and through `coffer sync remote set --interval 59`
- **THEN** both are refused with a validation error naming the 60-second floor
- **AND** the stored remote still carries the 300-second interval

### Requirement: Run the seven round steps in order
A round MUST be these seven steps **in this order**:

```
0  Repair    — if the working tree's HEAD is not the pointer, reset to the pointer
1  Serialize — export the vault into the tree (differentially), commit as L;
               deletion guard on the publish side (pointer..L)
2  Merge     — fetch, then merge origin/<branch> into L with base merge-base(L, R) → M
3  Diff      — D := git diff L..M
4  Guard     — deletion guard on the apply side (D plus the retry set);
               tag L as the pre-apply snapshot
5  Apply     — apply D to the vault, path by path
6  Publish   — push M; pointer := M; unapplied paths join the retry set
```

The deletion guard runs in both directions, each at the first step that knows
its diff: what this vault is about to publish is checked right after it is
committed, before any merge, and what the round is about to apply to this
vault is checked once the merge has produced it. A breach in either direction
holds the round before the vault or the remote is touched.

Most concurrent edits are not conflicts: git merges different hunks of one file
without help.

#### Scenario: a changed vault converges and pushes
- **GIVEN** a configured sync remote and a vault with a new knowledge document,
- **WHEN** a converge round runs,
- **THEN** the document is committed to the working tree, the commit is pushed
  to the configured branch, and the pointer advances to it.

#### Scenario: concurrent edits to different parts of one document merge
- **GIVEN** two machines that each appended a different section to one knowledge
  document,
- **WHEN** both converge,
- **THEN** the document holds both sections and no conflict is reported.

### Requirement: Cover the sync lifecycle on the command line
The CLI MUST cover the round and the vault's lifecycle — `coffer sync now`,
`adopt [<url>] [--keep-local] [--yes]`, `status`, `history [--limit]`,
`restore [--at <rev|date>]`, `confirm`, `reject`, `rebuild [--yes]`, `rollback`
— and its administration:
`remote set <url> [--branch] [--interval <seconds>] [--with-credentials|--without-credentials] [--credential-ref] [--worktree <path>]`,
`remote show`, `remote clear`, `remote pause`, `remote resume`, `machine list`,
`machine rename <name>`, `machine remove <id>`, `key export <file>`,
`key import <file>`, `key fingerprint`. An option `remote set` is not given
keeps the stored remote's value, the working tree included. `remote pause` and
`remote resume` switch the remote's `enabled` switch off and on (see "Pause a
configured remote without forgetting it") and change nothing else.

#### Scenario: the command line covers every sync operation
- **GIVEN** the `coffer sync` command group
- **WHEN** its commands and options are listed
- **THEN** it offers `now`, `adopt` with `--keep-local` and `--yes`, `status`, `history` with `--limit`, `restore` with `--at`, `confirm`, `reject`, `rebuild` with `--yes` and `rollback`
- **AND** it offers `remote set` with `--branch`, `--interval`, `--with-credentials`, `--without-credentials`, `--credential-ref` and `--worktree`, `remote show`, `remote clear`, `remote pause`, `remote resume`, `machine list`, `machine rename`, `machine remove`, `key export`, `key import` and `key fingerprint`

#### Scenario: pause and resume a remote from the command line
- **GIVEN** a configured, enabled sync remote
- **WHEN** the user runs `coffer sync remote pause`, and then `coffer sync remote resume`
- **THEN** after the first the stored remote is switched off and a requested round reports `disabled`, and after the second it is switched on again
- **AND** the URL, branch, interval, credential settings and working tree are unchanged throughout
