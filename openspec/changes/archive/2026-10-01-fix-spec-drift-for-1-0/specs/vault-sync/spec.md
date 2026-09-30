## MODIFIED Requirements

### Requirement: Keep the remote a rendezvous, not a system of record
Convergence with a user-owned git remote is a bounded exception to the
principles' Local-First rule: the remote MUST be a
**rendezvous, not a system of record**. Every machine's vault is a complete git
repository of its own, so the remote can be deleted and rebuilt from any single
machine without losing anything.

#### Scenario: a remote rebuilt from one machine loses nothing
- **GIVEN** a machine's vault and an empty remote
- **WHEN** the machine joins the remote
- **THEN** the remote's branch is the vault's own `HEAD`, holding every committed file
- **AND** the machine's vault is unchanged

### Requirement: Withhold derived output in both halves
**Derived output MUST NOT converge, in either half**, and it cannot, because it
is stored under `derived/`, outside the vault. Coffer's own generated skill
`coffer-guide` is the case this exists for: its text is rendered locally from
the running build, the knowledge files and this machine's absolute paths, so
two machines holding identical files render different bytes, each correct where
it is. **Both halves** are
derived: its master folder (`derived/skills/coffer-guide/`) and its resource
file (`derived/resources/skill/coffer-guide.json`). Every other skill is in the
vault. Memory partitions are derived the same way.

#### Scenario: a locally generated skill is neither published nor overwritten
- **GIVEN** Coffer's own skill and a person's imported skill
- **WHEN** each is filed
- **THEN** Coffer's own is stored under `derived/` and the person's under the vault, so only the person's can converge

### Requirement: Keep the pointer local
There is no pointer apart from the vault's own history. A round's base MUST be
the merge base of this vault's `HEAD` and the remote's tip, so what this machine
has absorbed is exactly what its history shares with the remote; nothing about
it travels as an input to the algorithm except the `last_converged_commit` a
returning machine reads back from its own descriptor.

#### Scenario: a round diffs from the shared history
- **GIVEN** two machines that converged, after which one deleted a document the other never touched
- **WHEN** the other machine, holding a new document of its own, runs a round
- **THEN** the merge from the shared history applies the deletion and publishes the new document

### Requirement: Stop the round on any conflict
A merge that git cannot finish cleanly — both sides changed the same lines, one
side deleted what the other changed, two resources claim one name — or whose
merged tree fails validation MUST stop the round whole: nothing is checked out,
nothing is pushed, this vault's `HEAD` and every file on disk stay as they were,
and the remote is untouched. Coffer MUST NOT resolve a conflict by itself, by a
rule or by an agent; the only exception is secret ciphertext (see "Let the
fresher secret ciphertext win"). Asking again while nobody answered and
neither side moved changes nothing.

#### Scenario: a real conflict stops the round without touching the vault
- **GIVEN** two machines that edited the same lines of one document, beside an unrelated change here
- **WHEN** a round runs
- **THEN** it ends `stopped` with one conflict naming the other machine, this vault's `HEAD`, the file on disk and the remote's tip are unchanged
- **AND** a second round before anyone answers is `stopped` again

### Requirement: Check a remote before it is saved
A person SHALL be able to ask what a remote holds before saving it — empty, a
Coffer vault (with its layout), some other repository, unreachable or refused
sign-in — through `POST /api/v1/sync/remote/check`, `coffer sync remote check`
and the set-up form's "Check repository". Each MUST send the user name the token
goes with, as saving does: the form's User name field, and on the command line
`--username`, else the stored remote's, else the default. Checking MUST keep
nothing: no remote is stored and the vault is not touched.

#### Scenario: a remote is checked before it is saved
- **GIVEN** an empty remote, the same remote once a vault has been pushed to it, and a URL that does not exist
- **WHEN** each is checked
- **THEN** they read as empty, as a vault at the current layout, and as unreachable or refused with git's message
- **AND** nothing about the stored remote changed

#### Scenario: the command line checks a remote with the user name it is given
- **GIVEN** a stored remote
- **WHEN** `coffer sync remote check --username oauth2` runs, and then `coffer sync remote check`
- **THEN** the first check sends the user name `oauth2` with the token, and the second sends the stored remote's
