# The Wire Contract Is Generated From the Pydantic Models, and the Frontend Client From the Contract

**Status**: Proposed
**Date**: 2026-09-29
**Deciders**: Yuxing Wu
**Related**: [A Per-Start Token, Handed to the Page by Whoever Hosts It, Behind a Loopback Host Guard](daemon-auth-and-origin-guard.md), [The Desktop Shell Hosts the Shared Frontend and Owns Only What a Browser Cannot Do](desktop-shell-over-a-shared-frontend.md), [Chat Is a Single-Owner Live Mirror](chat-single-owner-live-mirror.md), [One Level-Triggered Reconciler Converges What Coffer Writes Outside Its Database](one-level-triggered-reconciler-compares-parameters.md), spec chat "Recover a dropped event stream with bounded retries", spec chat "Send fire-and-return and stream output over one subscription", PR #392

## Context

The wire contract today runs **hand-written YAML → everything else**.
`.agents/stack.md` line 80 states it:

> The authoritative wire contract for any feature is `openspec/specs/<short-name>/contracts/api.openapi.yaml` (hand-written, PR-reviewed …). Backend Pydantic `BaseModel`s are HAND-WRITTEN to match the yaml.

and `docs-site/architecture/design-principles.md` line 58, under "Spec as
truth", repeats it: "backend models are hand-written to match it, `make
verify-contract` fails on structural drift, and the frontend's typed client
is generated from it."

Measured on `main` at `b7d3e505`:

- **Two hand-written copies of one fact.** There are 13 contract files under
  `openspec/specs/*/contracts/` and a Pydantic model behind every route. FastAPI
  already derives an OpenAPI document from those models (`app.openapi()`),
  and the docs-site REST reference is generated from that runtime document
  (`docs-site/scripts/gen_rest_reference.py`), not from the YAML. The YAML is a
  third description, kept in step by tests.
- **The backend gates are good and still leak.**
  `backend/tests/contract/` checks route sets both ways
  (`test_contract_coverage.py`), property names
  (`test_schemas_match_openapi.py`) and, since PR #392, property type kinds
  (`test_schema_types_match_openapi.py`). That last module's docstring names
  four divergences the name-only gates had let ship (`SkillOut.scope` served
  as an object while declared an array, among them) and lists deliberate
  blind spots — constraints, nullable spellings, formats — because two
  hand-written documents legitimately disagree there.
- **The frontend is where types are actually hand-written.**
  `frontend/src/lib/api/` holds 21 domain modules beside the four shared ones
  (`call`, `client`, `errors`, `queryKeys`). Eleven of them declare 46
  `export interface` wire types by hand, and the modules make 109
  `call<T>()` calls whose `T` is chosen by hand. No gate compares any of those
  types with anything: `codegen:check` only proves `generated/` matches the
  YAML. `memory` is excluded from codegen altogether (`frontend/scripts/codegen.mjs`,
  because its contract's schema names differ from what `memoryTypes.ts`
  exports). The typed `openapi-fetch` client covers only the mcp-gateway
  paths.
- **Every route declares a shape.** Of 165 route decorators, 143 declare
  `response_model` and 22 declare `response_class` — 204 no-body responses,
  the MCP protocol endpoint and the chat SSE stream — so
  `scripts/check_response_models.py` passes. The gap is not in the backend.
- **There is no daemon-wide change feed.** The only streams are chat's
  per-conversation `GET …/events` and the MCP protocol endpoint. The UI keeps
  other data fresh by polling: `refetchInterval` in `useSync`, `useUpkeep`,
  `useChannels`, `useDaemon` and `useMcpInvocations` (5 s to 60 s). Chat's
  stream reader (`frontend/src/lib/chat/streamClient.ts`) already uses `fetch`
  with the `X-Coffer-Token` header, because `EventSource` cannot send one.
- **Lists page by `limit`, `since` and `offset`** (`mcp/invocation_routes.py`,
  `agent_transcript_routes.py`), which skip or repeat rows when new ones
  arrive mid-read.

## Options Considered

### Option A — Pydantic models → generated OpenAPI → generated client (chosen)

The Pydantic models in `surfaces/http/` are the single hand-written
description of the wire. A generator writes the app's OpenAPI document, split
by path ownership into each capability's `contracts/api.openapi.yaml`, so the
contract stays inside the spec folder and every change to it is visible as a
diff in review. The frontend's client and types are generated from those
files for **every** capability, and request functions are thin wrappers over
the generated client.

Gates change accordingly:

- **Freshness, not agreement.** CI regenerates the contracts and fails if the
  checked-in files differ. Backend ↔ YAML cannot disagree, so the
  hand-maintained exclusions in `test_schema_types_match_openapi.py` go away
  with it.
- **Types at the consumer.** Wire types in `frontend/src/lib/api/` are aliases
  of generated schemas only; a lint rule rejects a hand-written `interface` or
  `type` there that is not marked UI-only, and `tsc` over the generated
  client is the type check — it compares types, not names.
- **Schema names are stable.** Models carry explicit schema names so a class
  rename is not a wire rename.

Migration happens **per domain on the existing paths**: a domain's models are
brought to what the UI really consumes, its contract becomes generated, its
hand-written module is deleted, and the next domain follows. There is no
`/api/v2` beside `/api/v1`.

- **Pros.** One description of the wire instead of three; the class of bug the
  type gate was written for cannot occur; the frontend's 46 hand-written
  interfaces and `memory`'s exclusion disappear; the docs-site reference and
  the contract finally come from the same document.
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
  `{seq, kind, id, rev, op}` — a sequence number, the resource kind, its uid,
  its revision, and `upsert` / `delete`. An envelope says *what* changed,
  never the new state: the client invalidates the matching queries and
  refetches through the normal typed endpoints, so the stream can never become
  a second, untyped copy of the contract. The client resumes with
  `Last-Event-ID`; when the daemon no longer holds that `seq`, it sends
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
existing `/api/v1` paths, deleting each hand-written module as its domain
moves. UI freshness comes from one change feed whose envelopes
(`seq`, `kind`, `id`, `rev`, `op`) are invalidation hints only, resumable by
`Last-Event-ID` with a `resync` fallback, read over `fetch` with the token
header; growing lists page by cursor.

**This reverses a stated rule, so it needs an amendment in a separate PR,
which is not part of this ADR's change.** [Principles](../../docs-site/architecture/principles.md)
states Spec-as-Truth at line 54 — "Specifications under `openspec/specs/` …
are the canonical product contract" — but has **no clause on which way the
wire contract is derived**; the hand-written direction is stated in
`docs-site/architecture/design-principles.md` line 58 and `.agents/stack.md`
line 80, quoted above. The amending PR adds that direction explicitly under
Spec-as-Truth (the behavioural spec is written first; the wire schema inside
the spec folder is generated from the models and reviewed as a diff) and
rewrites those two passages, following the Amendments procedure in
Principles. No domain migrates before that PR merges.

## Consequences

- **Supersedes** the hand-written direction recorded in `.agents/stack.md`,
  `.agents/frontend.md` ("hand-written — with a comment saying why — only where
  the contract is narrower") and `.agents/openspec.md`, once the amendment
  lands.
- `test_schema_types_match_openapi.py`, `test_schemas_match_openapi.py` and
  the per-capability `test_*_openapi.py` shape tests are replaced by the
  freshness check; `test_contract_coverage.py` keeps its role of proving each
  served route has an owning capability. `check_response_models.py` stays.
  `codegen:check` is rewritten to check that no hand-written wire type
  remains.
- The docs-site REST reference and the contracts now come from the same
  document.
- The change feed needs a monotonic `rev` per resource, shared with the
  reconciler's `Changed` hint, and a bounded replay buffer in the daemon.
- **Follow-up work:** the generator and freshness gate, run once beside the
  current gates before any domain moves; per-domain migration in the order the
  v0.2 pages ship (MCP, Skills, Agents, Settings, Activity), each deleting its
  hand-written module; the events endpoint and a query-invalidation client;
  cursor pagination for invocations, audit and transcripts; the principles
  amendment PR.
