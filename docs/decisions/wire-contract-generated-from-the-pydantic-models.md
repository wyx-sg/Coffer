# The Wire Contract Is Generated From the Pydantic Models, and the Frontend Client From the Contract

> **Superseded in part (2026-10-04).** The change `move-agent-sessions-to-terminal` removed the web chat and Coffer's copy of conversation text. The per-conversation event stream the frontend client once recovered with bounded retries is gone with the page; the decision (contract generated from the Pydantic models, client generated from the contract) is unchanged.

**Status**: Accepted
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](daemon-auth-and-origin-guard.md), [The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do](desktop-shell-over-a-shared-frontend.md), [Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database](one-level-triggered-reconciler-compares-parameters.md), PR #392

## Context

Before this decision the wire contract ran **hand-written YAML → everything
else**: each capability's `contracts/api.openapi.yaml` was written and
PR-reviewed by hand, the backend's Pydantic `BaseModel`s were hand-written to
match it, and the frontend's typed client was generated from it. The stack
notes and the design-principles page both said so.

Measured on `main` at `b7d3e505`, before the change:

- **Two hand-written copies of one fact.** There were 13 contract files under
  `openspec/specs/*/contracts/` and a Pydantic model behind every route.
  FastAPI already derives an OpenAPI document from those models
  (`app.openapi()`), so the YAML was a third description, kept in step by
  tests.
- **The backend gates were good and still leaked.** The contract tests
  checked route sets both ways, property names and, since PR #392, property
  type kinds. The type gate's docstring named four divergences the name-only
  gates had let ship (`SkillOut.scope` served as an object while declared an
  array, among them) and listed deliberate blind spots — constraints,
  nullable spellings, formats — because two hand-written documents
  legitimately disagree there.
- **The frontend was where types were actually hand-written.** Eleven of the
  21 domain modules under `frontend/src/lib/api/` declared 46
  `export interface` wire types by hand, and the modules made 109 hand-written
  `call<T>()` calls (since replaced by the generated typed client) whose `T`
  was chosen by hand. No gate compared any of those types
  with anything: the codegen check only proved `generated/` matched the YAML.
  The `memory` capability was excluded from codegen altogether, because its
  contract's schema names differed from what the hand-written types
  exported. The typed `openapi-fetch` client covered only the mcp-gateway
  paths.
- **Every route declared a shape.** Of 165 route decorators, 143 declared
  `response_model` and 22 `response_class` (204 no-body responses, the MCP
  protocol endpoint and the chat SSE stream), so
  `scripts/check_response_models.py` passed. The gap was not in the backend.
- **There was no daemon-wide change feed.** The only streams were chat's
  per-conversation `GET …/events` and the MCP protocol endpoint. The UI kept
  other data fresh by polling (`refetchInterval` of 5 s to 60 s in several
  hooks). Chat's stream reader (`frontend/src/lib/chat/streamClient.ts`)
  already uses `fetch` with the `X-Coffer-Token` header, because
  `EventSource` cannot send one.
- **Lists paged by `limit`, `since` and `offset`**, which skip or repeat rows
  when new ones arrive mid-read.

## Options Considered

### Option A — Pydantic models → generated OpenAPI → generated client (chosen)

The Pydantic models in `surfaces/http/` are the single hand-written
description of the wire. A generator (`scripts/gen_contracts.py`, `make contracts`) writes the app's
OpenAPI document, split by a route-ownership table into each capability's `contracts/api.openapi.yaml`, so the
contract stays inside the spec folder and every change to it is visible as a
diff in review. The frontend's client and types are generated from those
files for **every** capability, and request functions are thin wrappers over
the generated client.

Gates change accordingly:

- **Freshness, not agreement.** `make lint` runs
  `scripts/gen_contracts.py --check`, which regenerates the contracts and
  fails if the checked-in files differ, and also fails when a served route has
  no owning capability. Backend and YAML cannot disagree, so the
  hand-maintained exclusions of the old name-and-type gates are gone.
- **Types at the consumer.** Wire types in `frontend/src/lib/api/` are aliases
  of generated schemas only; `frontend/scripts/check-wire-types.mjs` (part of
  `codegen:check`) rejects a hand-written `interface` or object-shaped `type`
  there that is not marked UI-only, and `tsc` over the generated client is the
  type check — it compares types, not names.
- **Schema names are stable.** Models carry explicit schema names so a class
  rename is not a wire rename.

Migration happens **per domain on the existing paths**: a domain's models are
brought to what the UI really consumes, its contract becomes generated, its
hand-written types are replaced by generated ones, and the next domain
follows. There is no `/api/v2` beside `/api/v1`.

- **Pros.** One description of the wire instead of three; the class of bug the
  type gate was written for cannot occur; the frontend's hand-written
  interfaces and `memory`'s exclusion disappear.
- **Cons.** The contract is no longer designed ahead of the code in YAML; a
  reviewer designs it in Pydantic and reads the generated diff. Generated
  schema names and nullable spellings are FastAPI's, so a model change can
  produce a noisy contract diff. The migration touches every frontend API
  module.
- **Why it wins.** The YAML was never what the daemon served; the models were.
  Making the thing that runs the source removes the drift instead of
  detecting it.

### Option B — Keep hand-written YAML as the source, and tighten the gates

Keep the direction; extend the type gate to constraints and nullability, and
add a frontend gate that checks hand-written interfaces against generated
types.

- **Pros.** The contract stays a design document written before the code;
  no principle wording changes.
- **Cons.** Three descriptions still have to agree, and every tightening adds
  a new exclusion list for the cases where they legitimately differ — the
  current type gate already carries one. A gate over hand-written TypeScript
  interfaces has to parse TypeScript and match it to OpenAPI, which is the
  generator's job done backwards.
- **Why it loses.** It keeps paying for agreement between copies that need not
  exist.

### Option C — Share types another way (a TypeScript backend, or JSON Schema as the source)

Make one language own the types, or write JSON Schema and generate both
Pydantic and TypeScript from it.

- **Pros.** A single source, arguably more neutral than Pydantic.
- **Cons.** Moving the backend to TypeScript contradicts the Languages
  constraint in [Principles](../../docs-site/architecture/principles.md)
  ("Python 3.12+ for backend, CLI, and any MCP shim"). Generating Pydantic
  from schema loses validators, discriminated unions and defaults the models
  already express, and adds a code generator on the backend.
- **Why it loses.** Pydantic is already the richest description in the tree.

### Option D — Version the API and run v1 and v2 side by side during migration

Generate a fresh `/api/v2` from new models and move the frontend over while
`/api/v1` stays.

- **Pros.** No flag day for any page; the old and new can be compared live.
- **Cons.** Coffer has one first-party client, shipped in the same build as
  the daemon, so no external caller needs `v1` to survive. Two route trees
  double the surface the reconciler, audit and auth guard must cover, and a
  half-migrated tree is exactly the state the project refuses to ship.
- **Why it loses.** Per-domain migration on existing paths gets the same
  safety with one tree.

### Event stream and pagination conventions (part of the same contract)

The contract also fixes how the UI learns that data changed:

- **Option E1 — a daemon-wide change feed of invalidation hints (chosen).**
  One `GET /api/v1/events` stream carries envelopes
  `{seq, kind, id, op}` — a sequence number, the resource kind, its uid (or
  none for the attention list), and `upsert` / `delete`. An envelope says *what* changed,
  never the new state: the client invalidates the matching queries and
  refetches through the normal typed endpoints, so the stream can never become
  a second, untyped copy of the contract. The client resumes with
  `Last-Event-ID`; when the daemon's bounded replay buffer no longer holds that `seq`, it sends
  `resync` and the client refetches everything. The stream is read with
  `fetch` and the token header, as chat's stream already is. Chat's
  per-conversation token stream stays its own endpoint, because it carries
  content, not hints.
- **Option E2 — push full resource state on the stream.** Fewer round trips,
  but the stream then needs its own schema, ordering guarantees and
  redaction, duplicating the REST contract.
- **Option E3 — keep polling.** Simple and already working, but each hook
  picks its own interval, changes show up 5–60 s late, and the overview page
  would need to poll every kind.

Lists that can grow while being read page by an **opaque cursor**, not by
`offset` or `since`.

## Decision

The Pydantic models are the only hand-written description of Coffer's HTTP
wire. Each capability's `contracts/api.openapi.yaml` is **generated** from the
running app and checked in, and the frontend's client and types are generated
from those files for every capability. Gates check that the contracts are
fresh and that frontend wire types are generated, so types are compared by
the compiler rather than names by a script. Migration is per domain on the
existing `/api/v1` paths. UI freshness comes from one change feed whose
envelopes (`seq`, `kind`, `id`, `op`) are invalidation hints only, resumable
by `Last-Event-ID` with a `resync` fallback, read over `fetch` with the token
header; growing lists page by cursor.

The direction is written into [Principles](../../docs-site/architecture/principles.md)
under Spec-as-Truth ("Contract direction"): the behavioural spec is written
first; the wire schema inside the spec folder is generated from the models and
reviewed as a diff; the frontend's client and wire types are generated from
that schema.

## Consequences

- `scripts/gen_contracts.py` and its `--check` mode replace the hand-written
  contracts and the name-and-type agreement tests; the contract tests that
  remain under `backend/tests/contract/` prove each served route has an owning
  capability and check individual behaviours. `scripts/check_response_models.py`
  stays.
- The frontend's `codegen:check` regenerates the types and runs
  `check-wire-types.mjs`, which fails on a hand-written wire type unless it is
  marked UI-only.
- The change feed's replay buffer is bounded and lives in the daemon's event
  broker; a client that falls behind receives one `resync`. The envelope
  carries no revision, because a client refetches rather than reconciles.
- Growing lists (audit, invocations, transcripts) page by an opaque cursor
  bound to the filters it was issued with.
- Built: every frontend call site goes through the generated typed client
  (`unwrap` / `unwrapVoid` / `unwrapOptional`); no hand-written wire type or
  `call<T>()` remains. The chat turn-event stream is part of the contract too
  (`TurnEventMessage`, read by `lib/chat/streamClient.ts`).
- Not built yet: a generated REST reference for the docs site. The docs-site
  generates only its CLI reference; the contracts are the REST reference.
