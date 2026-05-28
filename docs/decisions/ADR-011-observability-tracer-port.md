# ADR-011: Observability — Tracer Port with LangFuse Adapter

**Status**: Accepted
**Date**: 2026-05-29
**Deciders**: Yuxing Wu
**Related**: spec `006-knowledge-base` (FR-016, research.md §7), [ADR-002](ADR-002-code-layout-layer-first.md)

## Context

Spec `006-knowledge-base` introduced trace-worthy operations: `ingest` and
`search` are long, multi-step, and the kind of thing a developer is going
to want to inspect when debugging slow retrieval or pinning down "why did
my last query return nothing." LangFuse is the dominant local-friendly
LLM-app tracing tool in the 2025 ecosystem (self-hosted, MIT-licensed,
purpose-built for LLM+RAG instrumentation), so it is the obvious default
backend if we ship tracing at all.

The constitutional question is _where the tracer interface lives_. There
are two options that match the rest of the codebase's layering:

1. **Kind-local**: a `Tracer` port lives inside
   `application/knowledge_base/`, the adapter inside
   `infrastructure/knowledge_base/`. Strictly follows the
   "extract cross-cutting after the second feature needs it" rule.
2. **Cross-cutting up-front**: extract `application/observability/` and
   `infrastructure/observability/` immediately in this PR, expecting
   spec 007 (memory) to be the second consumer.

Either choice is defensible. The trade-off:

- (1) honours the constitution literally — no premature abstraction; the
  same shape was used for credentials, audit, and retention. The
  refactor when spec 007 lands is small (move two files, rewrite two
  imports).
- (2) anticipates a known second consumer. Spec 007's draft already
  reasons about memory traces; the refactor cost in (1) is ≈ one PR of
  pure mechanical move. Doing it now also forces us to design the port
  kind-agnostic from day one rather than retrofit later.

The other dimension is **how tracing is enabled**. LangFuse requires a
public/secret key and a host URL. We cannot have the adapter dragging
LangFuse into the import graph at daemon-start time if the user has not
opted in; that would break the local-first invariant for users who never
set the env vars.

## Decision

**Extract the `Tracer` port into `application/observability/` in this PR,
one step ahead of the strict "second consumer" rule.** Concrete shape:

- Port: `application/observability/tracer.py` defines `Tracer` as a
  `typing.Protocol` with `start_span(name, attrs) -> SpanHandle` /
  `record_attrs(handle, attrs)` / `end_span(handle, status)`. The port
  speaks only stdlib + a small `SpanHandle` value type; nothing
  LangFuse-shaped leaks through.
- Default implementation: `NoopTracer` in the same module. Returns a
  static handle, ignores attrs, never imports LangFuse. The composition
  root wires this by default.
- LangFuse adapter: `infrastructure/observability/langfuse_tracer.py`.
  The adapter `import langfuse` happens **inside the constructor**, not
  at module top-level — so the daemon never imports LangFuse unless the
  composition root explicitly selects this adapter. Activation is gated
  on `LANGFUSE_PUBLIC_KEY` being set in the environment at daemon start;
  if not set, the noop wins and `langfuse` is never imported.
- Span name discipline: spans follow the convention `<kind>.<operation>`
  — `kb.ingest_document`, `kb.search`, `kb.delete_document`, `kb.delete`.
  Future consumers (spec 007 memory) will use `memory.<operation>`. This
  is the port's only kind-aware concession and is documented in
  `application/observability/__init__.py`.
- Privacy: payloads sent to LangFuse contain sizes, counts, and durations
  only — never document text, never query strings, never passage
  content. This rule is enforced by code review (no automated check yet;
  the LangFuse adapter is the single chokepoint).

The package layout intentionally mirrors `credentials/`: a `domain/`-
adjacent port surface lives under `application/observability/`, the
side-effectful adapter lives under `infrastructure/observability/`, and
importlinter prevents the application layer from reaching directly into
the LangFuse SDK.

## Consequences

**Positive**

- Spec 007 (memory) will plug `memory.<op>` spans into the same port
  without any refactor — saving one PR of mechanical move.
- Default is no-op, so users who never set LangFuse env vars pay zero
  bytes of LangFuse code, zero outbound network calls, and zero log
  noise. Local-first invariant holds.
- The lazy import means a misconfigured LangFuse install (e.g. wrong
  version pin in the user's environment) cannot break daemon start
  unless the user explicitly opted in.
- Tracing surface is _kind-agnostic_. The port does not assume RAG;
  any future kind that wants to trace operations just uses the same
  `Tracer` injection.

**Negative**

- One step ahead of the strict "second consumer" rule. If spec 007 is
  delayed indefinitely, the cross-cutting module sits with a single
  consumer for longer than constitutionally ideal. Mitigated by the
  port surface being tiny (3 methods) and the noop default being a
  ~20-line implementation; the carrying cost is small.
- Span-name discipline (`<kind>.<op>`) is enforced by convention, not
  by the port's type system. A future contributor could emit
  `kb.something` from a non-KB module. Mitigated by the small set of
  call sites and code review; no automated check yet.
- LangFuse is one library among several (Phoenix, Logfire, OpenTelemetry +
  Tempo). We bet on LangFuse because it is the local-friendly RAG-aware
  default in 2025; if that bet ages poorly, the adapter is one file to
  swap and the port stays stable.

## Alternatives Considered

**Leave the tracer inside `application/knowledge_base/` until spec 007
lands.** Strictly correct per the constitution. Rejected because the
refactor cost when 007 ships is purely mechanical (rename a module,
update two imports) and doing it up-front lets us design the port shape
without a known second consumer's needs constraining it later. The
benefit of the "wait for second consumer" rule — preventing speculative
abstractions — is undermined when the second consumer is known and
imminent.

**OpenTelemetry as the in-process tracing API.** Rejected for v1.
OpenTelemetry is the right answer at scale but its Python SDK adds
non-trivial deps and the developer-facing UI options are weak compared to
LangFuse for RAG/LLM workflows. If a future Coffer wants APM-style
distributed traces, the port can grow an OTLP adapter without touching
the call sites.

**Make the tracer mandatory, not optional.** Rejected. The
constitution's "local-first, no surprise outbound network calls"
principle means tracing has to be opt-in, gated on an explicit env
var. Defaulting to a no-op is the only way to honour that.

**Eager-import LangFuse at module load.** Rejected. Eager import would
make a `pip install langfuse` failure or a version conflict break the
daemon for users who never wanted tracing. The lazy import is a hard
constraint, not a stylistic choice.
