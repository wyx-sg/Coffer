## MODIFIED Requirements

### Requirement: Restore to a revision without discarding later work
Going back to an earlier version of a vault file or folder MUST NOT discard
anything the vault gained since: restoring writes that version back as a new
commit — made from a document's or a skill's History tab ([vault-storage](../vault-storage/spec.md)
"Show and restore any version of a vault file or folder"), or by the person with git —
touching only the paths restored and never rewriting history, and the next round publishes it like
any other change.
Undoing what one round did is its rollback (see "Snapshot before checking out
and roll a round back from it").

#### Scenario: restore brings back a document deleted last week
- **GIVEN** a file with two versions in the vault's history
- **WHEN** the first version's bytes are written back and committed as a restore
- **THEN** the file holds the first version's bytes as a new commit, and no earlier commit is rewritten
