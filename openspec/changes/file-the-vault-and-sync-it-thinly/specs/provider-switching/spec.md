## ADDED Requirements

### Requirement: Keep at most one internal default connection
At most one connection globally MUST have `internal_default=true`. `set_internal_default` MUST clear
the flag on all others, then set the target (sequential clear-then-set, serialised by the
single-process daemon); it is the one operation that moves the flag on this machine. Nothing else
makes a second one:

- **Any other write** that would set the flag while a different connection holds it — the generic
  `PATCH /api/v1/resources/{uid}` or `POST /api/v1/resources` — MUST be refused before anything is
  written with 409 `PROVIDER_INTERNAL_DEFAULT_TAKEN`, naming the connection that holds the flag. The
  holder keeps the flag, the refused write changes nothing, and the answer is never a 500. Writing
  the flag back onto the connection that already holds it is not a second one.
- **A sync round** whose merged tree would flag a connection other than the one flagged here MUST
  NOT check that tree out: the vault's validation refuses a tree holding two flagged connections,
  so the round stops on the file and the person answers it like any other
  ([vault-sync](../vault-sync/spec.md) "Stop the round on any conflict") — keeping this machine's
  version or taking the other machine's. A tree that moves the flag, clearing it on one connection
  and setting it on another, holds one and is checked out like any change. No tie-break picks one
  silently: which connection Coffer's own model borrows is the person's decision.

The invariant MUST be enforced by the vault's validation as well. `internal_default` is an ordinary
config field, and a live vault was found holding two flagged connections, which makes "which
connection does the internal engine use?" a question with no defined answer. The rule over the
provider files ([vault-storage](../vault-storage/spec.md) "Admit every vault write through one compare-and-swap path")
makes a second one unrepresentable in the vault, whatever writes it — a surface, a hand edit or a
round; the refusal above keeps every surface write from reaching it.

#### Scenario: setting a new internal default clears the previous one
- **GIVEN** connection A is the internal default,
- **WHEN** the user sets connection B as the internal default,
- **THEN** B's `internal_default` becomes true and A's becomes false (one internal default globally, enforced by the vault's validation as well as by the operation).

#### Scenario: a second internal default outside the dedicated route is refused
- **GIVEN** connection A is the internal default,
- **WHEN** `PATCH /api/v1/resources/{B}` sets B's `internal_default` true, or `POST /api/v1/resources` creates a provider with it true,
- **THEN** the answer is 409 `PROVIDER_INTERNAL_DEFAULT_TAKEN` naming A, A keeps the flag, B stays unflagged and no connection is created,
- **AND** `POST /api/v1/providers/{B}/internal-default` still moves the flag to B.

#### Scenario: a file flagging a second internal default is refused by the vault
- **GIVEN** a connection file that flags `internal_default` in the vault
- **WHEN** a second connection file flagging it is written, and separately a change clears the first file's flag while setting the second's
- **THEN** the second file alone is refused as an invalid config naming the file that already holds the flag
- **AND** the change that moves the flag is accepted

#### Scenario: two machines that each set a different internal default stop the round
- **GIVEN** two machines in sync, and within one sync interval machine 1 sets connection X as the internal default and machine 2 sets connection Y
- **WHEN** machine 1's round pushes and machine 2's round then merges
- **THEN** machine 2's round stops on the connection files instead of checking out a tree with two internal defaults
- **AND** machine 2's vault is left as it was, holding only its own flag, until the person answers

## MODIFIED Requirements

### Requirement: Converge connections across machines
The `provider` kind MUST be registered into the composition root's kind table like every kind, so each
connection is one vault file, `resources/provider/<name>.json`, that a sync round merges and checks out
like every resource file ([vault-sync](../vault-sync/spec.md) "Converge resources as their own files"). A connection's reach
(`enabled` / `scope`) MUST NOT travel: it is this machine's reach record, one decision the user makes
per machine, so a connection that already exists keeps the reach it has, and one that has just arrived
takes the kind's own default. Secrets travel as Fernet ciphertext at `secret/<ref>.enc`, only when the
remote is configured to carry them; the master key never enters the repository, and no raw key MUST
appear in the vault's plaintext.

Projection is a machine-local side effect, so after a round that applied changes, the reconcile pass it
runs with the import's warrant ([vault-sync](../vault-sync/spec.md) "Run the reconciler once after a round that applied changes")
MUST re-derive every agent's projection from the connections as they now are: for each
agent type with a registered agent, the active connection whose scope reaches it is projected, and a
type with no active connection is de-projected — the import carries the user's switch either way.

#### Scenario: a provider profile round-trips through sync export and import
- **GIVEN** a connection with a secret ref exists on one machine,
- **WHEN** a second machine joins a remote that carries secrets, and the first machine later edits the connection and both run a round,
- **THEN** the connection's file arrives on the second machine byte for byte, the secret ciphertext is present at `secret/<ref>.enc`, and no secret appears in the file's plaintext; the edit arrives the same way, so the second machine ends up with the edited config.

#### Scenario: an import projects a switch made on another machine
- **GIVEN** a connection activated on another machine, whose file arrives here with `is_active` set while this machine's agent carries none of Coffer's keys
- **WHEN** the round's reconcile pass runs
- **THEN** the connection is projected into the agent rather than its flag being cleared

## REMOVED Requirements

### Requirement: Keep at most one internal-engine default
**Reason**: A sync round no longer applies a document path by path, so there is no applier to drop a second flag or break a tie by uid: the vault's validation refuses a merged tree holding two flagged connections, and the round stops for the person to answer.
**Migration**: "Keep at most one internal default connection".
