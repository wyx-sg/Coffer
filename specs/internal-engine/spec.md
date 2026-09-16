# Feature Specification: Internal Engine

**Status**: Accepted

## One-line

Coffer thinks with a model of its own. The **internal engine** is the settings
that say which one — the connection it borrows and the model it runs — plus the
switch and timer of every pass Coffer runs when nobody asked it to. It owns one
global settings row, the surfaces that show and change it, and the rule that a
pass with nothing configured is a clean no-op rather than an error.

## Why

Coffer does work on its own behalf: it aggregates the agents' memory, lets a
model rewrite that derived digest, lets a model tidy the user's own knowledge
files, resolves a sync conflict, and transcribes a voice message. All five need
the same two things — an endpoint to call and a model to name — and none of them
belongs to the agent the user is chatting with.

Before this spec those settings had no owner. Two of the three unattended passes
had no switch at all, the third's could only be changed by hand-editing a synced
document, and all three intervals were constants compiled into the workers. A
timer that rewrites the only copy of the user's writing is not something to
discover. This spec is that owner: the row, its surfaces, its defaults, and how
it travels between machines. Why each decision went the way it did is in
[research.md](./research.md).

## Decisions

### The engine borrows a connection and owns a model

- **A1 — Two halves, two owners.** The ENDPOINT and key come from the connection
  flagged `internal_default`, owned by spec
  [provider-switching](../provider-switching/spec.md) FR-024/FR-025. The MODEL is
  this spec's, on its own global row. The connection carries no model to fall
  back to, so the two resolve together or not at all.
- **A2 — Nothing configured is a no-op, never an error.** Coffer is usable with
  no connection at all, so a pass with nothing to run on simply does not run.
- **A3 — A change of connection drops a model the new one does not serve**,
  unless that connection CURATES the id — a curated list is its own catalogue,
  so an id on it is still servable. Nothing is probed: a settings write MUST NOT
  depend on an endpoint being reachable.
- **A4 — No second model registry.** The chat model is built from the resolved
  pair, dispatched by protocol; Coffer writes down no model name of its own.
- **A5 — Consumers reach the engine through ports**, never through the provider
  kind. That is what makes the engine kind-agnostic substrate rather than a
  facet of the connection registry.

### What Coffer does unattended

- **B1 — The same row carries the work.** Three passes run on a timer:
  `aggregate` reads the agents' own memory into the derived tree (spec
  [memory](../memory/spec.md) FR-007), `organise` lets the model rewrite that
  derived digest (spec memory FR-030), and `tidy` lets it rewrite the user's own
  knowledge files (spec [knowledge](../knowledge/spec.md) FR-051). Each has a
  switch and an interval, because they share one question — what may Coffer's
  own model do while nobody is looking.
- **B2 — One pass per write.** A settings page toggles one row at a time, and a
  body carrying all three makes every toggle a chance to write back a stale copy
  of the other two — on settings another machine may be changing too.
- **B3 — An unchosen interval is reported as unchosen, beside the default that
  runs.** The default stays in the worker that owns the pass, so raising it
  later reaches every vault that never chose one.
- **B4 — A floor, and no unknown passes.** An interval below the floor would
  busy-loop a model over the user's files; both it and an unknown pass name are
  refused.
- **B5 — A change reaches a running worker** without a restart, because the wait
  is taken in slices and the interval re-read each slice.
- **B6 — The defaults follow what a pass WRITES.** `aggregate` and `organise`
  write only derived files that deleting and re-running reproduces, so they ship
  ON. `tidy` rewrites the only copy of the user's own writing, so it ships OFF.

### Convergence

- **C1 — The settings travel as their own state area**, `settings`, document
  `state/settings/internal-engine.yaml` (spec
  [vault-sync](../vault-sync/spec.md)): Coffer's passes behave the same
  everywhere only when they run on the same model, and switching a rewriter off
  is exactly the decision a second machine must not be left out of.
- **C2 — The area publishes a DECISION, not a row.** A machine still holding the
  defaults writes no document, so the tree holds one exactly while some machine
  holds a non-default choice and its deletion means "back to the defaults".
- **C3 — An older machine is not a decision.** A document missing the upkeep
  block leaves this machine's switches and timers alone.

### Surfaces

- **D1 — Settings → Engine, two cards** — the model, and the upkeep rows. Both
  configure Coffer's own machinery rather than anything served to an agent,
  which is why they sit under Settings and not on a resource page.
- **D2 — Every setting here is reachable from a terminal**, per `.agents/sdd.md`.
  Without it a terminal-only operator cannot stop a timer that rewrites their
  files.

## Scope

### In scope

- The global `internal_engine_config` singleton: the engine model, and each
  unattended pass's switch and interval; its `internal_engine_model_set` audit
  event; its convergence as the `settings` state area.
- Resolving the engine's connection + model pair, the clean no-op when either is
  missing, building the chat model from the pair, and the drop rule when the
  internal-default connection moves.
- The schedule the three unattended passes wait on, with its floor and defaults.
- The surfaces: `GET` / `PUT /api/v1/internal-engine-config`,
  `PUT /api/v1/internal-engine-config/upkeep`, `coffer engine …`, and
  Settings → Engine.

### Out of scope (explicit non-goals)

- **The connection itself** — creating, editing, activating or flagging one is
  spec provider-switching. This spec reads the flagged one.
- **What each pass DOES** — aggregate, organise and tidy are specified by spec
  memory and spec knowledge. This spec owns only whether and how often they run.
- **`GET /api/v1/upkeep/runs`** — what is in flight right now is a cross-kind
  read beside `/resources`, `/audit` and `/retention`, not this spec's schedule.
- **A model registry** — Coffer writes down no model name of its own.
- **Per-collection or per-partition timers** — one switch and interval per pass,
  not one per target.

## Entity — the engine's settings

One row, fixed primary key, a second one unrepresentable. It holds the engine
model and, per pass, a switch and an optional interval, where `NULL` means "this
pass's own default". The authoritative field list is
[data-model.md](./data-model.md).

## HTTP API

Hand-written OpenAPI, not contract-test-gated; keep it in sync manually. Full
document in [contracts/api.openapi.yaml](./contracts/api.openapi.yaml).

- `GET /api/v1/internal-engine-config` → the model, its last write, and every
  pass's switch, chosen interval and default interval
- `PUT /api/v1/internal-engine-config` → set the model; `null` or empty clears it
- `PUT /api/v1/internal-engine-config/upkeep` → change ONE pass's switch or
  interval; `use_default_interval` returns that pass to its own default, which a
  null interval cannot express

## CLI

```
coffer engine model show | set <id> | clear
coffer engine upkeep list [--json]
coffer engine upkeep set <pass> [--on | --off] [--interval <seconds> | --default-interval]
```

`<pass>` is one of `aggregate`, `organise`, `tidy`. `upkeep list` prints each
pass's switch, its chosen interval and — when none is chosen — the default that
runs instead, so the terminal shows what the page shows.

## Frontend

**Settings → Engine** is two cards. The model card picks the internal-default
connection and, from that connection's curated `text` models or its probed
catalogue, the engine model. The upkeep card is one row per pass: a switch, an
interval select whose default option names the real number, and — for `tidy`
alone — a line saying it rewrites the user's own files. Edits auto-save, like
every other settings surface: the switch on toggle, the interval on selection.

## Acceptance Scenarios

Per `.agents/sdd.md`, every scenario in this section is referenced by at least
one test marked `@pytest.mark.acceptance(spec="internal-engine", scenario="…")`
(Python) or `acceptance("internal-engine", "…", …)` (TypeScript).

### Scenario: choose the model the internal engine runs on

- **Given** a connection is the internal default,
- **When** the operator sets a model on the global internal-engine config
  (`PUT /api/v1/internal-engine-config`),
- **Then** `GET /api/v1/internal-engine-config` returns that model, an
  `internal_engine_model_set` audit entry is recorded, and
  `resolve_internal_connection()` pairs the chosen model with the resolved
  internal-default connection.

### Scenario: a second engine settings row is unrepresentable

- **Given** the internal-engine settings row exists,
- **When** a second row is inserted directly into the table,
- **Then** the database refuses it, so "which settings does the engine use?"
  cannot become a question with two answers.

### Scenario: nothing configured makes every internal pass a clean no-op

- **Given** no connection is flagged `internal_default`, or no engine model is
  chosen,
- **When** a consumer asks the engine for its connection,
- **Then** it is answered `None`, the pass that asked does not run, and no error
  is raised or logged as a failure — the same answer for both missing halves.

### Scenario: switching the internal engine's connection drops a model it does not serve

- **Given** connection A is the internal default and the engine model is one of
  A's models,
- **When** the operator makes connection B the internal default,
- **Then** the engine model is cleared — so `resolve_internal_connection()` is
  `None` until a model is picked again — unless B's curated `models` already
  lists that id, in which case it is kept; nothing is probed over the network,
  and re-setting A, which is already the internal default, changes nothing.

### Scenario: switch off and re-time the passes Coffer runs unattended

- **Given** a fresh vault, where aggregation and organise run on their own
  timers and tidy does not,
- **When** the operator switches one pass on or off, or gives it an interval, or
  returns it to its own default (`PUT /api/v1/internal-engine-config/upkeep`,
  one pass per request),
- **Then** that pass's switch and interval change and no other pass's do, the
  reported default interval says what runs while none is chosen, an interval
  below the floor and an unknown pass name are both refused, and the running
  worker picks the change up without a restart.

### Scenario: the engine's settings converge and a deletion means the defaults

- **Given** one machine has chosen an engine model and switched `tidy` on while
  a second machine still holds the defaults,
- **When** a converge round runs,
- **Then** the second machine takes both decisions from
  `state/settings/internal-engine.yaml`, a machine holding only the defaults
  publishes no document at all, a document carrying no upkeep block leaves this
  machine's switches alone, and deleting the document resets this machine to the
  defaults with the write audited as `sync`.

### Scenario: the command line shows and sets the engine model

- **Given** the daemon is running and a connection is the internal default,
- **When** the operator runs `coffer engine model set <id>`, then
  `coffer engine model show`, then `coffer engine model clear`,
- **Then** each has the same effect as the HTTP route — the model is stored,
  reported and cleared — and the audit entry is the same one the route records.

### Scenario: the command line lists and changes each unattended pass

- **Given** the daemon is running,
- **When** the operator runs `coffer engine upkeep list --json`, then
  `coffer engine upkeep set tidy --off`, then
  `coffer engine upkeep set organise --interval 900`,
- **Then** the listing is machine-readable and names each pass's switch, its
  chosen interval and the default that runs while none is chosen; each `set`
  changes one pass only; and an interval below the floor or an unknown pass name
  is refused with the same error the route gives.

### Scenario: Settings → Engine shows and changes both halves

- **Given** the Settings → Engine page is rendered with an internal-default
  connection and the three passes,
- **When** the page renders and the operator toggles one pass and picks an
  interval,
- **Then** the model card shows the chosen connection and model, the upkeep card
  shows one row per pass with the default named rather than blank, each edit
  saves on its own without a Save button, and only the toggled pass is written
  (TypeScript acceptance test).

## Requirements

### Functional Requirements

**The engine's own settings row**

- **FR-001**: Coffer's own operating settings MUST live in one global row whose
  primary key is fixed, with a database constraint making a second row
  unrepresentable whatever writes it.
- **FR-002**: `GET /api/v1/internal-engine-config` MUST report the engine model,
  when it was last written, and every pass's switch, chosen interval and default
  interval. `PUT /api/v1/internal-engine-config` MUST set the model, treating a
  blank or null value as clearing it.
- **FR-003**: Every write to the row MUST record an audit entry naming the actor
  and carrying the values after the write, so a change made on another machine
  and converged here is as visible as one made on this one.

**Resolving what the engine runs on**

- **FR-004**: `resolve_internal_connection()` MUST return the connection flagged
  `internal_default` (spec [provider-switching](../provider-switching/spec.md)
  FR-024) paired with the engine model, or `None` when no connection is flagged
  or no model is chosen.
- **FR-005**: When that answer is `None`, every internal pass MUST be a clean
  no-op rather than an error, on every consumer.
- **FR-006**: Coffer MUST keep no second model registry: the engine builds its
  chat model from the resolved pair via `build_chat_model(resolved, …)`,
  dispatched by protocol.
- **FR-007**: A change of the internal-default connection MUST DROP the engine
  model, unless the newly chosen connection's curated `models` already lists
  that id. Nothing MUST be probed to decide. Setting the connection that is
  already the internal default MUST change nothing. The trigger is spec
  provider-switching FR-025, which notifies the engine through a port; the rule
  and its exception are this spec's.
- **FR-008**: Consumers MUST reach the engine only through `ModelSelectorPort`
  and `LlmCompletionPort`, satisfied by the composition root. No consumer MUST
  import the provider kind to get at the engine.

**What Coffer does unattended**

- **FR-009**: The same row MUST carry a switch and an interval for each of the
  three passes Coffer runs on its own behalf — `aggregate`, `organise` and
  `tidy`.
- **FR-010**: `PUT /api/v1/internal-engine-config/upkeep` MUST change exactly one
  named pass. An omitted half MUST leave that half alone, and every other pass
  MUST be left exactly as it stands.
- **FR-011**: An interval the operator has not chosen MUST be reported as
  unchosen ALONGSIDE the default that runs in its place. The default MUST live
  in the worker that owns the pass, not copied into each vault.
- **FR-012**: An interval below the floor MUST be refused, and so MUST a pass
  name Coffer does not run.
- **FR-013**: A running worker MUST pick a switch or interval change up without
  a daemon restart.
- **FR-014**: The passes that write only derived files (`aggregate`, `organise`)
  MUST ship ON; `tidy`, which rewrites the user's own knowledge files, MUST ship
  OFF.

**Convergence**

- **FR-015**: The settings MUST travel as sync state area `settings`, document
  `state/settings/internal-engine.yaml` (spec
  [vault-sync](../vault-sync/spec.md)), carrying the model and every pass's
  switch and interval.
- **FR-016**: A machine still holding the defaults MUST publish NO document: the
  area carries a decision, not a row.
- **FR-017**: An incoming document that carries no upkeep block MUST leave this
  machine's switches and intervals alone rather than resetting them.
- **FR-018**: Deleting the document MUST reset this machine to the defaults,
  written through the same service as any other change and audited as `sync`.

**Surfaces**

- **FR-019**: Settings → Engine MUST show and change both halves: the connection
  and model the engine runs on, and each pass's switch and interval with its
  default named rather than left blank. Edits MUST save on their own.
- **FR-020**: A CLI MUST show, set and clear the engine model, with the same
  effect and the same audit entry as the HTTP route.
- **FR-021**: A CLI MUST list every pass's switch, chosen interval and default
  interval — with `--json` — and change one pass per invocation, including
  returning that pass to its default interval. It MUST refuse an interval below
  the floor and an unknown pass name with the same errors the route gives.

### Key Entities

- **The engine settings row**: the model Coffer's own passes run on, each pass's
  switch and optional interval, and the timestamp of the last write.
- **`UpkeepSetting`**: one pass's switch and interval, asked for by pass name so
  adding a pass adds an entry rather than a branch in every reader.
- **`ResolvedConnection`**: a connection paired with the model to run on it. The
  value object is spec provider-switching's; the pairing is this spec's.
- **`ModelSelectorPort` / `LlmCompletionPort`**: the two ports every consumer
  depends on — the engine's connection, and one shot of a model.
- **The upkeep schedule**: the sliced wait that re-reads its interval, and the
  per-pass default intervals it falls back to.
- **The `settings` state area**: export, import and delete of
  `state/settings/internal-engine.yaml`, including the is-this-the-default test
  that decides whether to publish at all.

## Success Criteria

- **SC-001**: With an internal-default connection and a model configured,
  Coffer's own passes run on it; with neither, they are a clean no-op.
- **SC-002**: An operator with only a terminal can see which model Coffer thinks
  with, change it, and switch off every pass that would rewrite their files.
- **SC-003**: Every acceptance scenario is covered by at least one test marked
  `acceptance(spec="internal-engine", scenario="…")`, and
  `make verify-acceptance` reports zero uncovered scenarios.
- **SC-004**: `make verify` passes locally and in CI.
- **SC-005**: A switch changed on one machine is in force on the other after a
  converge round, and a vault where nobody has chosen anything carries no
  settings document at all.

## Assumptions

- Spec provider-switching is in place: connections exist, one may be flagged
  `internal_default`, and that flag's single-global invariant is enforced there.
- Spec vault-sync's state-area mechanism is available, including the rule that
  each area's provider defines what a document's deletion means.
- The four consumers — spec vault-sync's conflict resolver, spec knowledge's
  tidy, spec memory's organise and spec chat's voice transcription — supply
  their own prompts and own their own results. This spec supplies the
  connection, the model and the timer, and absorbs none of their requirements.
- `GET /api/v1/upkeep/runs` (what is rewriting right now) is a cross-kind
  surface like `/api/v1/resources` and `/api/v1/audit`, not part of this spec.
- Coffer runs as a single-user personal tool; no multi-user access control is
  needed beyond the existing `X-Coffer-Token` gate.
