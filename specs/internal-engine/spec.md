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
model rewrite that derived digest, lets a model derive the knowledge documents
agents read from the sources a person writes, resolves a sync conflict, and
transcribes a voice message. All five need the same two things — an endpoint to
call and a model to name — and none of them belongs to the agent the user is
chatting with. Four of the five share one endpoint; speech-to-text has its own,
because the gateway that answers a chat completion commonly serves no
transcription endpoint at all.

Before this spec those settings had no owner. Two of the three unattended passes
had no switch at all, the third's could only be changed by hand-editing a synced
document, and all three intervals were constants compiled into the workers. A
timer that rewrites the only copy of the user's writing is not something to
discover. Two further values had the same shape and the same absence of an
owner: how long ONE call to Coffer's own model may take, a constant compiled
into each call site, and the speech-to-text model, an environment variable read
inside a daemon that is spawned detached from any shell and so never saw it.
This spec is that owner: the row, its surfaces, its defaults, and how it travels
between machines. Why each decision went the way it did is in
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
- **A6 — How long one call may take is the OPERATOR's number.** Every call
  Coffer's own model makes is bounded, because an unbounded one is how an
  unattended pass stops being unattended: a wedged endpoint holds the pass until
  the daemon restarts and no surface says so. The bound used to be a constant
  per call site — 60s in distil, 20s in knowledge ingestion, none at all on
  curation's turns. But the right number is a property of the operator's
  endpoint: against a gateway whose typical answer takes 25–30s, a 60s bound
  leaves barely a factor of two, and the passes then fail in their LEAST useful
  mode — gracefully. A timed-out routing chunk defers its entries to the next
  pass, so nothing breaks and nothing is lost; the layer merely converges at a
  fraction of the rate it reports. A knob that needs a rebuild to turn is not a
  knob.
- **A7 — Out of range is refused at a surface and CLAMPED in a pass.** An
  operator asking for a number gets a rejection they can read rather than a
  different number applied silently. A background pass reading a value out of
  range is reading a row written by an older build or a hand-edited synced
  document, and is the wrong place to take itself down over one.
- **A8 — Speech-to-text has its OWN connection and its OWN model, with no
  fallback to the engine's.** They are different models: the gateway a user
  points Coffer's engine at commonly serves chat completions and no
  `/audio/transcriptions` at all, so borrowing it turned every voice message
  into a 404 — where a connection deliberately left unset produces the safe
  behaviour the chat surface already has, which is to hand the agent the audio
  file and leave the recording on this machine. Both halves are required and
  neither falls back, the same rule the engine model already follows; the
  connection is flagged `transcribe_default` (spec provider-switching FR-035)
  and the model is this row's.

### What Coffer does unattended

- **B1 — The same row carries the work.** Three passes run on a timer:
  `aggregate` reads the agents' own memory into the derived tree (spec
  [memory](../memory/spec.md) FR-007), `distil` lets the model rewrite that
  derived digest (spec memory FR-030), and `curate` derives the knowledge
  documents agents read from the sources a person writes (spec
  [knowledge](../knowledge/spec.md) FR-034). Each has a
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
- **B6 — The defaults follow what a pass WRITES.** `aggregate` and `distil`
  write only derived files that deleting and re-running reproduces, so they ship
  ON — including `curate`, which derives `topics/` from sources it may not
  touch and is the only path from a source to something an agent can read, so a
  vault where it never runs has an empty lane forever.

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

- **D1 — Settings → Engine, three cards** — the engine's model with the bound
  its calls run under, the speech-to-text pair, and the upkeep rows. All three
  configure Coffer's own machinery rather than anything served to an agent,
  which is why they sit under Settings and not on a resource page.
- **D2 — Every setting here is reachable from a terminal**, per `.agents/sdd.md`.
  Without it a terminal-only operator cannot stop a timer that rewrites their
  files.

## Scope

### In scope

- The global `internal_engine_config` singleton: the engine model, each
  unattended pass's switch and interval, the bound on one model call, and the
  speech-to-text model; its `internal_engine_model_set` audit event; its
  convergence as the `settings` state area.
- Resolving the engine's connection + model pair, the clean no-op when either is
  missing, building the chat model from the pair, and the drop rule when the
  internal-default connection moves.
- Resolving the speech-to-text connection + model pair the same way, against the
  connection flagged `transcribe_default` instead.
- The schedule the three unattended passes wait on, with its floor and defaults,
  and the bound every internal model call runs under, with its own floor and
  ceiling.
- The surfaces: `GET` / `PUT /api/v1/internal-engine-config`,
  `PUT /api/v1/internal-engine-config/upkeep`,
  `PUT /api/v1/internal-engine-config/timeout`,
  `PUT /api/v1/internal-engine-config/transcribe-model`, `coffer engine …`, and
  Settings → Engine.

### Out of scope (explicit non-goals)

- **The connection itself** — creating, editing, activating or flagging one is
  spec provider-switching, and that holds for both flags: `internal_default` and
  `transcribe_default` are its rows' fields and its routes. This spec reads the
  flagged ones.
- **What each pass DOES** — aggregate, distil and curate are specified by spec
  memory and spec knowledge. This spec owns only whether and how often they run.
- **`GET /api/v1/upkeep/runs`** — what is in flight right now is a cross-kind
  read beside `/resources`, `/audit` and `/retention`, not this spec's schedule.
- **A model registry** — Coffer writes down no model name of its own.
- **Per-collection or per-partition timers** — one switch and interval per pass,
  not one per target.

## Entity — the engine's settings

One row, fixed primary key, a second one unrepresentable. It holds the engine
model, the speech-to-text model, the bound on one model call, and, per pass, a
switch and an optional interval. `NULL` means "the built-in default" for the
interval and for the bound alike — and for a model it means "unchosen", which
makes the work that would have used it a clean no-op. The authoritative field
list is [data-model.md](./data-model.md).

## HTTP API

Hand-written OpenAPI, not contract-test-gated; keep it in sync manually. Full
document in [contracts/api.openapi.yaml](./contracts/api.openapi.yaml).

- `GET /api/v1/internal-engine-config` → the model, the speech-to-text model,
  the chosen call bound beside the default that applies while none is chosen,
  the last write, and every pass's switch, chosen interval and default interval
- `PUT /api/v1/internal-engine-config` → set the model; `null` or empty clears it
- `PUT /api/v1/internal-engine-config/upkeep` → change ONE pass's switch or
  interval; `use_default_interval` returns that pass to its own default, which a
  null interval cannot express
- `PUT /api/v1/internal-engine-config/timeout` → set how long one call to
  Coffer's own model may take; `null` returns to the built-in default. Outside
  the floor–ceiling range is refused, not clamped
- `PUT /api/v1/internal-engine-config/transcribe-model` → set the speech-to-text
  model; `null` or empty clears it, which stops transcription

The connection half of each pair is spec provider-switching's:
`POST /api/v1/providers/{uid}/internal-default` and
`POST /api/v1/providers/{uid}/transcribe-default`.

## CLI

```
coffer engine model show | set <id> | clear
coffer engine timeout show | set <seconds> | default
coffer engine transcribe-model show | set <id> | clear
coffer engine upkeep list [--json]
coffer engine upkeep set <pass> [--on | --off] [--interval <seconds> | --default-interval]
```

`<pass>` is one of `aggregate`, `distil`, `curate`. `upkeep list` prints each
pass's switch, its chosen interval and — when none is chosen — the default that
runs instead, so the terminal shows what the page shows. `timeout show` prints
the same pair for the call bound, and `timeout default` returns to the built-in
one, which a `set` of `null` cannot express. Marking either connection is spec
provider-switching's `coffer provider internal-default <name>` and
`coffer provider transcribe-default <name>`.

## Frontend

**Settings → Engine** is three cards. The model card picks the internal-default
connection and, from that connection's curated `text` models or its probed
catalogue, the engine model, and carries the call bound beside it — a property
of the calls this card configures, named with the default that applies while the
operator has chosen none. The speech-to-text card is the same pair again for the
connection flagged `transcribe_default` and its own model, saying plainly that
with either half unset Coffer transcribes nothing and the agent receives the
audio file. The upkeep card is one row per pass: a switch, an interval select
whose default option names the real number, and — for `curate` alone — a line
saying it is Coffer's own model deriving documents from the user's sources.
Edits auto-save, like every other
settings surface: the switch on toggle, the interval on selection, and a bound
outside the permitted range reported where it was typed rather than saved.

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

- **Given** a fresh vault, where aggregation and distil run on their own
  timers,
- **When** the operator switches one pass on or off, or gives it an interval, or
  returns it to its own default (`PUT /api/v1/internal-engine-config/upkeep`,
  one pass per request),
- **Then** that pass's switch and interval change and no other pass's do, the
  reported default interval says what runs while none is chosen, an interval
  below the floor and an unknown pass name are both refused, and the running
  worker picks the change up without a restart.

### Scenario: bound how long one call to Coffer's own model may take

- **Given** the engine has a connection and a model, and no bound has been
  chosen,
- **When** the operator reads the bound, sets one, and returns it to the default
  (`PUT /api/v1/internal-engine-config/timeout`, or `coffer engine timeout
  show | set | default`),
- **Then** an unchosen bound is reported as unchosen beside the built-in default
  that applies, a chosen one is what every internal model call runs under — the
  distil pass, knowledge ingestion's description step, curation's agentic turns
  and speech-to-text alike — a value outside the permitted range is refused by
  the route and by the CLI with the same error, and a value already stored
  outside that range is clamped by a background pass rather than taking it down.

### Scenario: speech-to-text runs on its own connection and its own model

- **Given** a connection is flagged `transcribe_default` and a speech-to-text
  model is chosen,
- **When** a turn carrying audio asks the engine what to transcribe with, and
  the operator then clears the model, or moves the flag to a connection that
  does not curate that model
  (`PUT /api/v1/internal-engine-config/transcribe-model`,
  `POST /api/v1/providers/{uid}/transcribe-default`),
- **Then** the pair resolves to that connection and that model while both halves
  are set; with either half missing it resolves to `None` and the audio is
  handed to the agent as a file rather than uploaded; the engine's own
  `internal_default` connection is never borrowed for it; and moving the flag
  drops the speech-to-text model unless the newly flagged connection curates it,
  leaving the engine model untouched.

### Scenario: the engine's settings converge and a deletion means the defaults

- **Given** one machine has chosen an engine model and switched `curate` off while
  a second machine still holds the defaults,
- **When** a converge round runs,
- **Then** the second machine takes both decisions from
  `state/settings/internal-engine.yaml`, which carries the call bound and the
  speech-to-text model beside them; a machine holding only the defaults
  publishes no document at all; a document carrying no upkeep block leaves this
  machine's switches alone, and one carrying neither of the two newer keys
  leaves this machine's bound and speech-to-text model alone for the same
  reason; and deleting the document resets this machine to the defaults with the
  write audited as `sync`.

### Scenario: the command line shows and sets the engine model

- **Given** the daemon is running and a connection is the internal default,
- **When** the operator runs `coffer engine model set <id>`, then
  `coffer engine model show`, then `coffer engine model clear`,
- **Then** each has the same effect as the HTTP route — the model is stored,
  reported and cleared — and the audit entry is the same one the route records.

### Scenario: the command line lists and changes each unattended pass

- **Given** the daemon is running,
- **When** the operator runs `coffer engine upkeep list --json`, then
  `coffer engine upkeep set curate --off`, then
  `coffer engine upkeep set distil --interval 900`,
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
  three passes Coffer runs on its own behalf — `aggregate`, `distil` and
  `curate`.
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
- **FR-014**: The passes that write only derived files (`aggregate`, `distil`)
  MUST ship ON, `curate` included: it derives the knowledge documents agents
  read from sources it never rewrites, and a vault where it never runs cannot ship
  OFF.

**Convergence**

- **FR-015**: The settings MUST travel as sync state area `settings`, document
  `state/settings/internal-engine.yaml` (spec
  [vault-sync](../vault-sync/spec.md)), carrying the model, the call bound, the
  speech-to-text model and every pass's switch and interval.
- **FR-016**: A machine still holding the defaults MUST publish NO document: the
  area carries a decision, not a row.
- **FR-017**: An incoming document that carries no upkeep block MUST leave this
  machine's switches and intervals alone rather than resetting them, and the
  same MUST hold key by key for the call bound and the speech-to-text model: a
  key the document does not carry is an older machine, not a decision. A key it
  carries — including an explicit null — is authoritative.
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

**How long one call may take**

- **FR-022**: The row MUST carry the bound on ONE call to Coffer's own model,
  where `NULL` means the built-in default. The default MUST live in one place in
  the code rather than be copied into each vault, exactly as an unchosen
  interval's does (FR-011), so raising it later reaches every vault that never
  chose. `GET /api/v1/internal-engine-config` MUST report the chosen bound and
  that default together.
- **FR-023**: EVERY call the internal engine makes MUST run under that bound —
  the distil pass's routing and writing, knowledge ingestion's description step,
  curation's agentic turns and speech-to-text alike. Curation's bound MUST be
  applied to the model CLIENT rather than around the call, because its loop is
  one `await` from the outside and wrapping it could only bound the whole
  conversation or nothing. The bound MUST be read per call rather than captured
  at wiring time, so a change — made here or converged from another machine —
  takes effect without a daemon restart.
- **FR-024**: A bound outside the permitted range MUST be refused by
  `PUT /api/v1/internal-engine-config/timeout` and by the CLI with the same
  error. A value already STORED outside that range MUST be clamped by the
  background passes rather than raised on: the surfaces refuse it on the way in,
  so a value found out there came from an older build or a hand-edited synced
  document, and a pass that could have run is the wrong place to discover it.

**Speech-to-text**

- **FR-025**: The row MUST carry the speech-to-text model, separate from the
  engine model. The connection it runs on MUST be the one flagged
  `transcribe_default` (spec [provider-switching](../provider-switching/spec.md)
  FR-035), and the pair MUST resolve exactly as the engine's does: both halves
  or `None`. There MUST be NO fallback between the two pairs — an unflagged
  connection or an unchosen speech-to-text model MUST NOT cause the engine's own
  connection or model to be used for transcription, but MUST answer `None`,
  which spec [chat](../chat/spec.md) FR-045 turns into handing the agent the
  audio file with nothing uploaded. The model MUST NOT be read from the
  environment: the daemon is spawned detached from any shell, so an environment
  variable was unreachable in a packaged install.
- **FR-026**: A change of the `transcribe_default` connection MUST DROP the
  speech-to-text model on the same rule as FR-007 — kept only when the newly
  flagged connection's curated `models` already lists that id, nothing probed,
  re-flagging the connection that already carries it changing nothing — and MUST
  leave the engine model untouched. The two flags move independently.

**Surfaces for both**

- **FR-027**: `PUT /api/v1/internal-engine-config/timeout` and
  `PUT /api/v1/internal-engine-config/transcribe-model` MUST each change one
  value and leave the rest of the row alone, audited like any other write to it
  (FR-003). A CLI MUST show, set and return-to-default the bound, and show, set
  and clear the speech-to-text model, with the same effects, refusals and audit
  entries as the routes. Settings → Engine MUST show and change both.

### Key Entities

- **The engine settings row**: the model Coffer's own passes run on, the model
  it transcribes speech with, the bound on one call to either, each pass's
  switch and optional interval, and the timestamp of the last write.
- **`UpkeepSetting`**: one pass's switch and interval, asked for by pass name so
  adding a pass adds an entry rather than a branch in every reader.
- **`ResolvedConnection`**: a connection paired with the model to run on it. The
  value object is spec provider-switching's; the pairing is this spec's.
- **`ModelSelectorPort` / `LlmCompletionPort`**: the two ports every consumer
  depends on — the engine's connection, and one shot of a model.
- **The upkeep schedule**: the sliced wait that re-reads its interval, and the
  per-pass default intervals it falls back to.
- **The call bound**: a reader consulted per call, the built-in default it
  answers with while none is chosen, and the floor and ceiling — refused at a
  surface, clamped in a pass.
- **The `settings` state area**: export, import and delete of
  `state/settings/internal-engine.yaml`, including the is-this-the-default test
  that decides whether to publish at all.

## Success Criteria

- **SC-001**: With an internal-default connection and a model configured,
  Coffer's own passes run on it; with neither, they are a clean no-op.
- **SC-002**: An operator with only a terminal can see which model Coffer thinks
  with, change it, switch off every pass that would rewrite their files, raise
  the bound on a slow endpoint, and choose — or refuse — a model for speech.
- **SC-003**: Every acceptance scenario is covered by at least one test marked
  `acceptance(spec="internal-engine", scenario="…")`, and
  `make verify-acceptance` reports zero uncovered scenarios.
- **SC-004**: `make verify` passes locally and in CI.
- **SC-005**: A switch changed on one machine is in force on the other after a
  converge round, and a vault where nobody has chosen anything carries no
  settings document at all.
- **SC-006**: On a gateway whose typical answer takes 25–30 seconds, raising the
  bound is a settings change rather than a rebuild, and no internal call runs
  unbounded at any setting.
- **SC-007**: A vault that has marked no transcription connection uploads no
  audio, and one that has marked a connection the engine does not use
  transcribes on it without the engine's own connection being touched.

## Assumptions

- Spec provider-switching is in place: connections exist, one may be flagged
  `internal_default` and one `transcribe_default`, and each flag's single-global
  invariant is enforced there.
- Spec vault-sync's state-area mechanism is available, including the rule that
  each area's provider defines what a document's deletion means.
- The four consumers — spec vault-sync's conflict resolver, spec knowledge's
  curate, spec memory's distil and spec chat's voice transcription — supply
  their own prompts and own their own results. This spec supplies the
  connection, the model, the timer and the bound, and absorbs none of their
  requirements. Three of the four run on the engine's connection; transcription
  runs on its own, and that is the only difference between them here.
- `GET /api/v1/upkeep/runs` (what is rewriting right now) is a cross-kind
  surface like `/api/v1/resources` and `/api/v1/audit`, not part of this spec.
- Coffer runs as a single-user personal tool; no multi-user access control is
  needed beyond the existing `X-Coffer-Token` gate.
