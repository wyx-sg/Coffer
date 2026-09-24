## MODIFIED Requirements

### Requirement: Keep at most one internal-engine default
At most one connection globally MUST have `internal_default=true`. `set_internal_default` MUST clear
the flag on all others, then set the target (sequential clear-then-set, serialised by the
single-process daemon); it is the one operation that moves the flag on this machine. A direct write
never makes a second one, and a synced one is settled the same way on every machine:

- **Any other write** that would set the flag while a different connection holds it — the generic
  `PATCH /api/v1/resources/{uid}` or `POST /api/v1/resources` — MUST be refused before anything is
  written with 409 `PROVIDER_INTERNAL_DEFAULT_TAKEN`, naming the connection that holds the flag. The
  holder keeps the flag, the refused write changes nothing, and the answer is never a 500. Writing
  the flag back onto the connection that already holds it is not a second one.
- **A converge round** ([vault-sync](../vault-sync/spec.md)) applying a document that sets the flag on
  a connection other than the local holder MUST NOT fail the round and MUST NOT hold the path for
  retry. When the tree the round applies also clears the flag on the local holder, the flag was
  moved on another machine, and the holder MUST be released first so the move lands whatever order
  the two documents apply in. Otherwise two machines each flagged a different connection, and the
  connection whose uid sorts first (lexicographically) MUST keep the flag — a tie-break every machine
  computes the same way, so the fleet converges on one default instead of each machine keeping its
  own and then receiving a clear for it. If that is the incoming connection, the local holder MUST
  be released and the document applied as written; if it is the local holder, the document MUST be
  applied with `internal_default` false and everything else as written — whether the connection
  already exists here or is new — and the path MUST be reported among the round's failures, naming
  the holder. A release runs only once the incoming document has passed its gate, just before its
  write, and is reverted if that write fails, so a document that cannot land leaves this machine its
  internal default.

The invariant MUST be enforced by the database as well. `internal_default` is an ordinary config
field, and a live vault was found holding two flagged connections, which makes "which connection
does the internal engine use?" a question with no defined answer. A partial unique index restricted
to flagged provider rows makes a second one unrepresentable, whatever writes it; the refusal and the
normalisation above keep every write from reaching it.

#### Scenario: setting a new internal default clears the previous one
- **GIVEN** connection A is the internal default,
- **WHEN** the user sets connection B as the internal default,
- **THEN** B's `internal_default` becomes true and A's becomes false (one internal default globally, enforced by the database as well as by the operation).
#### Scenario: a second internal default outside the dedicated route is refused
- **GIVEN** connection A is the internal default,
- **WHEN** `PATCH /api/v1/resources/{B}` sets B's `internal_default` true, or `POST /api/v1/resources` creates a provider with it true,
- **THEN** the answer is 409 `PROVIDER_INTERNAL_DEFAULT_TAKEN` naming A, A keeps the flag, B stays unflagged and no connection is created,
- **AND** `POST /api/v1/providers/{B}/internal-default` still moves the flag to B.
#### Scenario: a synced second internal default is dropped, not fatal
- **GIVEN** connection A is the internal default on this machine, its document in the tree still flags it, and A's uid sorts before B's,
- **WHEN** a converge round applies a document flagging connection B — an existing connection or a new one — with other edits beside the flag,
- **THEN** the round completes and its pointer advances, A keeps the flag, B is applied with every other field as written and `internal_default` false,
- **AND** the round's failures name B's path and A, and the path is not held for retry.
#### Scenario: a synced internal default whose uid sorts first takes the flag
- **GIVEN** connection A is the internal default on this machine, its document in the tree still flags it, and B's uid sorts before A's,
- **WHEN** a converge round applies a document flagging connection B,
- **THEN** B holds the flag, A's is cleared, and the round reports no failure for it.
#### Scenario: two machines that each set a different internal default converge on one
- **GIVEN** two machines in sync, and within one sync interval machine 1 sets connection X as the internal default and machine 2 sets connection Y,
- **WHEN** both machines run converge rounds until they settle,
- **THEN** both machines hold exactly one internal default, the same one on each, and it is whichever of X and Y has the smaller uid.
