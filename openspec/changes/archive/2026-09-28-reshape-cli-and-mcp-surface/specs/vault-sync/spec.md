## MODIFIED Requirements

### Requirement: Converge resource definitions as serialized documents
`mcp_server`, `agent`, `skill`, `knowledge`, `provider` and `channel`
definitions MUST converge, serialized to text from SQLite, which stays the
system of record. A resource document is identity, title, description and
config — what the resource *is*. What it reaches is not in it (see "Keep reach
machine-local").

The `title` is optional in the document. A resource with no title MUST be
serialized without the key, and a document that carries no `title` MUST leave
the receiving machine's title empty, so a machine running an older version,
which writes no `title`, and a newer one converge on the same resource. Setting,
changing or clearing a title on one machine MUST reach every other machine as a
modification of that one document.

#### Scenario: a resource document is identity, description and config
- **GIVEN** a registered resource with a description, a config and a reach of its own
- **WHEN** it is serialized into a resource document
- **THEN** the document holds its identity, its description and its config
- **AND** it holds nothing else — no `enabled` flag and no `scope`

#### Scenario: a resource document carries the title when there is one
- **GIVEN** a registered resource with a title, a description, a config and a reach of its own
- **WHEN** it is serialized into a resource document
- **THEN** the document holds its identity, its title, its description and its config
- **AND** it holds no `enabled` flag and no `scope`

#### Scenario: a title set on one machine converges to the other
- **GIVEN** a resource that two converged machines hold, with no title on either
- **WHEN** the user sets its title on one machine and the two converge
- **THEN** the other machine shows the same title for the same resource
- **AND** clearing the title on either machine and converging again leaves it empty on both

#### Scenario: a document without a title leaves the title empty
- **GIVEN** a resource document that carries no `title` key
- **WHEN** a machine applies it
- **THEN** the resource is registered or updated with an empty title and every other field the document carries

### Requirement: Snapshot before applying and roll back from it
Bidirectional convergence writes the vault without a human in the loop, so two
guards are normative.

Step 4 MUST tag `L` as the pre-apply snapshot, whose tree is by construction the
vault's state immediately before the apply. Rollback MUST be the same machinery
run backwards — applying `M..L`. The most recent **ten** snapshots MUST be kept.
A rollback MUST NOT move the pointer: the reverted vault is an ordinary local
change, which the next round publishes to the remote. Moving the pointer back
would make the next round re-derive the diff just undone and apply it again.

A rollback is reached from the Undo of "Offer Undo on one round only when it
applied something", from `POST /sync/rollback`, and on the command line from
`coffer sync restore` run with no `--at`, which undoes the last round that
applied something here. When no round applied anything since the newest
snapshot, `coffer sync restore` with no `--at` MUST change nothing and say that
there is nothing to undo.

#### Scenario: a round can be rolled back
- **GIVEN** a completed round that applied a diff,
- **WHEN** the user rolls it back,
- **THEN** the vault returns to the state the pre-apply snapshot holds and the
  pointer stays where it was, so the next round publishes the undo as an
  ordinary local change rather than re-applying the diff,
- **AND** a round that applied nothing here offers no Undo at all, because the
  snapshot it left is the state the vault is already in.

#### Scenario: restore with no revision undoes the last applied round
- **GIVEN** a completed round that applied a diff to this machine
- **WHEN** the user runs `coffer sync restore` without `--at`
- **THEN** the vault returns to the state that round's pre-apply snapshot holds
  and the pointer stays where it was
- **AND** running it when the newest round applied nothing changes nothing and
  reports that there is nothing to undo

### Requirement: Restore to a revision without discarding later work
`coffer sync restore --at <rev|date>` MUST move the working tree to a revision
and apply the difference from the current pointer, so a document deleted last
week returns without discarding anything the vault gained since. Without
`--at`, `coffer sync restore` is the rollback of "Snapshot before applying and
roll back from it".

#### Scenario: restore brings back a document deleted last week
- **GIVEN** a remote whose history contains a skill later deleted and converged
  away,
- **WHEN** the user runs `coffer sync restore --at <a date before the deletion>`,
- **THEN** the skill is registered again and everything the vault gained since
  that date is untouched.

### Requirement: Cover the sync lifecycle on the command line
The CLI MUST cover the round and the vault's lifecycle — `coffer sync now`,
`adopt [<url>] [--keep-local] [--yes]`, `status`, `history [--limit]`,
`restore [--at <rev|date>]`, `confirm`, `reject`, `rebuild [--yes]`
— and its administration:
`remote set <url> [--branch] [--interval <seconds>] [--with-credentials|--without-credentials] [--credential-ref] [--worktree <path>]`,
`remote clear`, `remote pause`, `remote resume`, `machine list`,
`machine rename <name>`, `machine rm <id>`, `key export <file>`,
`key import <file>`, `key fingerprint`. An option `remote set` is not given
keeps the stored remote's value, the working tree included. `remote pause` and
`remote resume` switch the remote's `enabled` switch off and on (see "Pause a
configured remote without forgetting it") and change nothing else.

`status` MUST report the configured remote and every one of its settings — URL,
branch, interval, whether credentials travel, the push credential ref, the
working tree and whether the remote is switched on — beside how the last round
went, in plain and `--json` output; with no remote configured it says so and
names `remote set`. `restore` without `--at` undoes the last round that applied
something here (see "Snapshot before applying and roll back from it").

#### Scenario: the command line covers every sync operation
- **GIVEN** the `coffer sync` command group
- **WHEN** its commands and options are listed
- **THEN** it offers `now`, `adopt` with `--keep-local` and `--yes`, `status`, `history` with `--limit`, `restore` with an optional `--at`, `confirm`, `reject` and `rebuild` with `--yes`
- **AND** it offers `remote set` with `--branch`, `--interval`, `--with-credentials`, `--without-credentials`, `--credential-ref` and `--worktree`, `remote clear`, `remote pause`, `remote resume`, `machine list`, `machine rename`, `machine rm`, `key export`, `key import` and `key fingerprint`

#### Scenario: pause and resume a remote from the command line
- **GIVEN** a configured, enabled sync remote
- **WHEN** the user runs `coffer sync remote pause`, and then `coffer sync remote resume`
- **THEN** after the first the stored remote is switched off and a requested round reports `disabled`, and after the second it is switched on again
- **AND** the URL, branch, interval, credential settings and working tree are unchanged throughout

#### Scenario: the status command reports the remote's settings
- **GIVEN** a configured remote with a non-default branch, interval, push credential ref and working tree, carrying credentials
- **WHEN** the user runs `coffer sync status --json`
- **THEN** the output carries the remote's URL, branch, interval, credential setting, push credential ref, working tree and enabled switch as stored
- **AND** with no remote configured `coffer sync status` says none is configured and names `coffer sync remote set`

### Requirement: Offer Undo on one round only when it applied something
At most one row — the newest that reached its pre-apply snapshot, which is the
round a rollback would reverse — MAY carry an **Undo** action naming the paths
it would take back, and no other row may, because `POST /sync/rollback` names
no round and an Undo on every row would run the same call from each. That row
MUST carry it only when the round **applied something to this machine**: every
round reaching the apply step tags a snapshot, including one that applies
nothing, so after a single quiet round the newest snapshot is the vault exactly
as it already is, and an Undo there offers to restore the state it is already
in. The action MUST NOT move down to an older round that did apply something —
the quiet round's snapshot is the newest, so the daemon would reverse to that
one and leave the older round standing, which is a button naming one round and
undoing another. The command-line counterpart of Undo is `coffer sync restore`
with no `--at`. Reaching further back is `coffer sync restore --at` (see "Keep
point-in-time restore on the command line").

#### Scenario: the undo sits on one round and never moves down
- **GIVEN** a runs history in which several rounds applied something here
- **WHEN** the Runs tab renders
- **THEN** only the newest round that reached its snapshot offers Undo, naming the paths it would take back
- **AND** when a quiet round sits on top, no row offers Undo rather than an older one
