## MODIFIED Requirements

### Requirement: Never overlap a tidy pass and a round
A curation pass and a converge round MUST NOT overlap. Both write the vault and an
export taken mid-rewrite is a torn snapshot, so they MUST take the same lock. A
pass MUST additionally be skipped while a conflict or a pending confirmation is
outstanding, so a rewrite is never piled onto an unresolved divergence.

#### Scenario: a tidy pass and a converge round do not overlap
- **GIVEN** a curation pass in progress,
- **WHEN** a converge round starts,
- **THEN** the round waits for the pass to finish before it serializes the
  vault, so the exported tree is never a half-rewritten corpus.

#### Scenario: a curation pass is skipped while a round is unresolved
- **GIVEN** a machine whose last round stopped on a conflict, or that holds a pending confirmation,
- **WHEN** the unattended curation pass asks whether it may run,
- **THEN** it is told no, and once a later round converges cleanly with nothing held it is told yes again.
