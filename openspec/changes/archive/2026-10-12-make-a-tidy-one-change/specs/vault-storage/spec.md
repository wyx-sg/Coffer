## MODIFIED Requirements

### Requirement: Keep the last valid version when a hand edit is invalid
A person's edits SHALL be found, not intercepted: a file-system watcher is a
hint, and a scan asking git which files differ from `HEAD` is the truth —
at boot, on every hint once the changed paths have been quiet for a second,
and periodically. A valid change SHALL be committed as a `disk` write, except
under a path prefix the writer has **paused** for the component that owns it —
a knowledge collection an agent is tidying ([knowledge](../knowledge/spec.md)
"Record a tidy as one change") — whose changes stay in the working tree, left
alone by every settle, until that component commits them as one write of its
own; a sync round treats them as it treats any uncommitted edit. A change
that fails validation MUST stay in the working tree uncommitted, MUST be
reported on the attention list with its reason, and the version at `HEAD`
MUST stay in effect until the file is fixed.

#### Scenario: an edit is committed once it is quiet
- **GIVEN** a person saving a vault file twice within a second
- **WHEN** the scanner looks
- **THEN** nothing is committed until the content has stopped changing, and then one `disk` commit holds the last content

#### Scenario: an invalid hand edit stays out of HEAD and is flagged
- **GIVEN** a person saves a resource file that does not parse
- **WHEN** the vault settles it
- **THEN** the file is not committed, the resource keeps its last valid configuration, and the attention list names the file and the reason
