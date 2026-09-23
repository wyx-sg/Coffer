## MODIFIED Requirements

### Requirement: Resolve a key for exactly one connection
`coffer provider key --connection-uid <uid>` / `GET /api/v1/providers/{uid}/key` MUST resolve exactly
that connection's credential ref, decrypt via `EncryptedCredentialStore.get(ref)`, and print it to
stdout or return it without logging the value. Keys resolve per CONNECTION, so routing a connection
to the other wire's agent can never resolve a different connection's key; a disabled connection, or
one scoped to no agent, resolves none — by uid as well as by wire, because the uid form is the one a
helper line already written into Claude Code's `settings.json` keeps calling after the user switches
the connection off. Resolving none is `not_found` (404, `NO_ACTIVE_PROVIDER`) on the route, and a
non-zero exit with a message on `stderr` from the CLI; the secret appears in neither. This is the one CLI command that takes a uid instead of a
name: its caller is the `apiKeyHelper` line Coffer writes into another tool's config file, so it MUST
keep resolving to the same connection after a rename. The wire-keyed form (`--wire <wire>` /
`GET /api/v1/providers/active-key/{wire}`) MUST remain for back-compat with `settings.json` files
written before, resolving through the connection active for that wire's agent.

#### Scenario: resolve the active provider key for the apiKeyHelper
- **GIVEN** a connection is active with a known secret stored in the vault,
- **WHEN** its key is resolved — `coffer provider key --connection-uid <uid>`, or the legacy `--wire anthropic` form,
- **THEN** the raw key is printed to stdout and the vault key is NOT logged.
#### Scenario: per-agent key routing follows the connection's scope
- **GIVEN** two activated connections told apart only by their scope — one scoped to `claude_code`, one to `codex`,
- **WHEN** each agent's key is resolved,
- **THEN** each resolves its own connection's key; disabling a connection, or scoping it to no agent, makes it resolve none.
#### Scenario: an agent bound to a renamed connection still resolves its key
- **GIVEN** a Claude Code agent running on connection `acme`,
- **WHEN** `acme` is renamed,
- **THEN** `GET /api/v1/providers/<uid>/key` returns the same secret, the uid the projected `apiKeyHelper` cites still resolves to it, and the connection is still active and still reaches that agent.
#### Scenario: a disabled or unreached connection's uid helper resolves no key
- **GIVEN** a connection activated for Claude Code, which is then disabled, or re-scoped to no agent,
- **WHEN** its key is resolved by uid — `coffer provider key --connection-uid <uid>` or `GET /api/v1/providers/{uid}/key`,
- **THEN** the route answers 404 `NO_ACTIVE_PROVIDER` and the CLI exits non-zero with a message naming the connection,
- **AND** the secret appears in neither.


### Requirement: Keep at most one internal-engine default
At most one connection globally MUST have `internal_default=true`. `set_internal_default` MUST clear
the flag on all others, then set the target (sequential clear-then-set, serialised by the
single-process daemon); it is the one operation that moves the flag. The flag already held on this
machine keeps it, and a second is refused:

- **Any other write** that would set the flag while a different connection holds it — the generic
  `PATCH /api/v1/resources/{uid}` or `POST /api/v1/resources` — MUST be refused before anything is
  written with 409 `PROVIDER_INTERNAL_DEFAULT_TAKEN`, naming the connection that holds the flag. The
  holder keeps the flag, the refused write changes nothing, and the answer is never a 500. Writing
  the flag back onto the connection that already holds it is not a second one.
- **A converge round** ([vault-sync](../vault-sync/spec.md)) applying a document that sets the flag on
  a connection other than the local holder MUST apply that document with `internal_default` false and
  everything else as written — whether the connection already exists here or is new — and MUST
  report the path among the round's failures, naming the holder. The path is not held for retry,
  because a retry meets the same rows; the round completes and its pointer advances. The exception
  is a move: when the tree the round applies also clears the flag on the local holder, the flag was
  moved on another machine, and the holder MUST be released first so the move lands whatever order
  the two documents apply in.

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
- **GIVEN** connection A is the internal default on this machine and its document in the tree still flags it,
- **WHEN** a converge round applies a document flagging connection B — an existing connection or a new one — with other edits beside the flag,
- **THEN** the round completes and its pointer advances, A keeps the flag, B is applied with every other field as written and `internal_default` false,
- **AND** the round's failures name B's path and A, and the path is not held for retry.

### Requirement: Serve one model list to every surface
What a picker is OFFERED MUST be: the active reaching connection's curated `text` ids when it curates
any, in the user's order and without consulting the agent's catalogue, and otherwise the agent's own
catalogue ([agent-registry](../agent-registry/spec.md)). The catalogue describes the account the
agent logs into itself, and an active connection means the turns do not go there, so mixing the two
could only offer ids the endpoint rejects; `catalogue()` is unchanged and still reports the agent's
own models. An active connection that curates nothing changes nothing, and no active reaching
connection means the agent's own login — a provider row Coffer cannot parse degrades to that case
rather than failing the read.

Codex's own model picker, inside Codex, is the one surface this answer does not reach when the
connection curates models but none of modality `text`: Coffer's surfaces then offer no chat model,
while the projection writes no model catalogue ("Project into Codex config without clobbering it"
writes one only for curated `text` models), so Codex keeps listing its built-in models.

That read MUST NOT touch the network: it happens on every card render and every turn, so
introspection would put a network round trip on the daemon's event loop. Levels MUST survive it — an
id the agent also reports keeps the levels the agent reported, and one the agent has never heard of
reports none, because the turn still runs through the agent's own runtime whatever endpoint it
points at. Every surface that offers a model MUST get this answer from the same place:
`GET /api/v1/agent-providers/{agent_key}/models` serves it, and a channel's `/model` card resolves it
in-process through the same function. No surface may compute its own — a web picker that
introspected the endpoint and offered the union with the agent's catalogue listed ids the endpoint
would reject and disagreed with the same user's `/model` card.

The system context Coffer adds on every turn — Claude Code's system-prompt append and Codex's
`developerInstructions` on `thread/start` and `thread/resume` — MUST state which model Coffer put the
agent on — or that Coffer set no override — and which ids are available, so the agent does not
confidently name a model it is not running on ([chat](../chat/spec.md) "Tell the agent which model it
is on").

#### Scenario: every surface offers the same models
- **GIVEN** an agent with an active connection that curates two model ids, and an agent catalogue of its own that names different ones,
- **WHEN** the model list is read for the web Chat page and for a channel's `/model` card,
- **THEN** both are exactly the connection's curated ids, in the user's order — the agent's own ids are absent, because the turns go to that endpoint,
- **AND** neither read touches the network, so an unreachable endpoint cannot silently shorten either list (see "Serve one model list to every surface").
