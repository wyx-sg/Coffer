## MODIFIED Requirements

### Requirement: Skip symlinks and nested repositories
Outbound, a symlink MUST be skipped rather than followed — its target is not
vault content, and a link to a file outside the vault would otherwise be
published — and anything under a nested `.git` directory MUST be skipped as
another repository's internals. What was skipped MUST be logged once per round.
Inbound, a symlink the working tree holds MUST be refused rather than read into
the vault.

Outbound, Python bytecode — a `__pycache__` directory, or a file ending in
`.pyc` or `.pyo` — MUST NOT be published either. The interpreter writes it
beside a skill's scripts whenever they run, so it changes for reasons that are
not edits. Bytecode already in the working tree MUST be removed by the ordinary
differential deletion. Leaving bytecode out is policy, not a surprise, so it is
not logged.

#### Scenario: a symlink in the vault is skipped rather than published
- **GIVEN** a knowledge collection holding a symlink to a file outside the
  vault,
- **WHEN** a round serializes the vault,
- **THEN** the working tree holds no copy of that file, the link is not
  followed, and the round logs once what it skipped.

#### Scenario: Python bytecode beside a skill's scripts is not published
- **GIVEN** a skill whose `scripts/` holds a `__pycache__/` of `.pyc` files, and
  a working tree that already carries some of them from an older build,
- **WHEN** a round serializes the vault,
- **THEN** the working tree holds the scripts but no bytecode, and nothing is
  logged as skipped.
