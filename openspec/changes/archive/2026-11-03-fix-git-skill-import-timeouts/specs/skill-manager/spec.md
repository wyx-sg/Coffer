## ADDED Requirements

### Requirement: Fetch a Git skill's folder in one request, within one deadline
Reading a skill's Git repository MUST keep the history Coffer compares commits
by without downloading every version of every file: the repository is cloned
without file contents (`--filter=blob:none`; a server that does not support it
sends everything), and before the files a subpath holds at a commit are
written out, every one of them the clone lacks MUST be fetched in one request,
never one request per file. The temporary clones run no automatic gc,
maintenance or commit-graph write. When the checkout still reports an object
the clone could not get from its remote, the repository MUST be cloned once
more without the filter and the files taken from that clone; this happens at
most once, is logged, and a failure of that clone is reported with git's own
message. A path the commit does not hold is reported as before, with no second
clone.

One operation on a skill's Git source — staging an import, checking for an
update, previewing a change of source, preparing the update hand-off, recording
a merge — MUST finish within 300 s, all its git commands together. Past that,
every git process it started is killed, its staging is removed, and the
operation is refused `SKILL_SOURCE_UNREACHABLE` saying it did not finish
within 300 s; an update check records that as the source's error, keeping the
last success.

#### Scenario: a partial clone fetches the skill's files in one request
- **GIVEN** a repository served with the `blob:none` filter whose `skills/review` folder holds thirteen files
- **WHEN** the skill is staged from that subpath
- **THEN** the thirteen files arrive in one fetch after the clone, the files outside the subpath stay on the server, and no second clone is made
- **AND** when that fetch reports a missing object instead, the files are written from one clone without the filter

#### Scenario: a Git source operation past its deadline is refused
- **GIVEN** a git that never finishes
- **WHEN** a skill is staged from it
- **THEN** after the deadline the git process is gone, the staging is removed, and the stage is refused `SKILL_SOURCE_UNREACHABLE` saying it did not finish in time
