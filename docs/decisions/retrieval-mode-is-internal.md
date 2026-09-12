# Retrieval mode is an internal engine detail; external surfaces expose query→answer.

**Status**: Superseded by [Knowledge Is Plain Files](knowledge-is-plain-files.md) (2026-09-12) — with no ranked index there are no retrieval modes left to keep internal, and the `search` tool this ADR shaped is gone. Kept as the record of the design in force until that date.
**Date**: 2026-06-21 (revised 2026-09-10; see Revision history)
**Spec**: [specs/knowledge/spec.md](../../specs/knowledge/spec.md)

## Context

The retrieval substrate (ADR files-as-truth-sqlite-retrieval) supports four modes — `grep`, `keyword`,
`vector`, and `hybrid` (RRF fusion of keyword + vector). The original KB and
memory surfaces exposed this taxonomy outward: REST `search`/`recall` accepted a
`mode` parameter, echoed back the resolved `mode` and a `fallback` field, the
MCP tools took a `mode?` argument, and the human web panel offered a grep box
next to the search box. An invalid external mode was a `400 SEARCH_MODE_INVALID`.

Coffer is a **minimal personal tool**, not an enterprise search product. A
single user choosing between "keyword" and "vector" and "hybrid" per query is
friction, not a feature: the right strategy is a property of the corpus (does it
have embeddings configured?), not of the question. The engine already resolves a
sensible default — `hybrid` when vector is enabled, else `keyword` — from
per-scope config. Exposing the mode knob outward forces every external caller
(REST client, CLI, agent via MCP, the web UI) to understand and re-specify a
decision the engine can make on its own, and it leaks a degradation detail
(`fallback`) into every query response that the metrics surface already reports
(`documents_degraded`). grep is a different shape of capability (exact/regex
file matches, not ranked passages) and belongs to agents/scripts, not to a human
clicking "search".

## Decision

External retrieval surfaces present **one query → one answer**. Specifically:

- **Remove `mode` from all external inputs**: the REST search request, the CLI
  search command, and the MCP retrieval tool
  (`coffer__search(query, scope?, top_k?)`). The caller never chooses a mode.
- **Remove `mode` and `fallback` from search responses**: the response carries
  only its ranked results. There is no per-query echo of the resolved mode and
  no `fallback` flag.
- **Keep modes internal to the engine/service**: the engine and the retrieval
  service still resolve and run a mode (`hybrid` when vector is enabled, else
  `keyword`); the per-scope `retrieval_modes` / `default_mode` remain internal
  config. The `RetrievalMode` enum and the internal domain `SearchResult` type
  are unchanged.
- **grep stays a separate internal/agent tool**: `coffer__grep` and the `/grep`
  endpoint remain for agents and scripts, but the grep affordance is **removed
  from the human web panel**.
- **The only per-scope retrieval knob is the vector on/off toggle** (a scope
  listing the vector mode). Enabling vector flips the resolved default to
  `hybrid`; that is the entire user-facing retrieval choice.

## Consequences

- **Simpler external contract.** One search input (`query`, `top_k?`) and one
  answer (ranked passages / hits). Nothing to mis-configure per query.
- **`SEARCH_MODE_INVALID` is removed.** With no external mode there is no
  invalid-mode request, so the search operation drops its `400` and the
  `SearchModeInvalid` domain error no longer applies. (If the code retains the
  symbol harmlessly, it is unreferenced from any external path.)
- **Degradation is surfaced via metrics, not a response flag.** When the
  resolved strategy needs vectors but no embedding provider is available, the
  engine falls back to keyword internally and still returns results — never an
  error. The "vector unavailable" condition is reported by the
  `documents_degraded` metric, not echoed per query.
- **Engine flexibility is preserved.** Because mode is internal, the resolution
  policy (or a future smarter router) can change without touching any external
  contract or breaking callers.
- **grep is still available where it belongs.** Agents and scripts keep exact
  file/line matching through the dedicated tool/endpoint; only the human panel
  loses the box.

## Alternatives considered

- **Keep `mode` but default it.** Rejected: the parameter still has to be
  documented, validated, and reasoned about on every surface, and it still leaks
  `fallback` into responses — all cost, no benefit for a single user whose
  corpus already determines the right strategy.
- **Keep `fallback` in the response, drop only the input `mode`.** Rejected: the
  degradation is a corpus/config condition, not a per-query outcome; reporting it
  once via `documents_degraded` is enough, and a per-query flag invites callers
  to branch on transient state.
- **Keep grep in the human panel.** Rejected: grep returns file/line matches,
  not ranked passages — a different mental model that confuses the "ask a
  question, get an answer" surface; agents are the right consumer.

## Revision history

- **2026-06-21** — Initial decision: retrieval mode is an internal engine
  detail; external surfaces take a query and return an answer.
- **2026-09-10** — Renamed for the knowledge-layer merge. `memory` and
  `knowledge_base` became one `knowledge` kind, so the two retrieval tools this
  ADR named — `coffer__search_knowledge` and `coffer__recall` — are now one
  `coffer__search`, and `coffer__grep_knowledge` is `coffer__grep`; the two
  per-store retrieval configs are one per-scope `KnowledgeConfig`, which also
  carries no embedding fields any more (embedding resolves through the
  installation-wide config, and a scope opts into vector purely by listing the
  mode). **The decision itself is unchanged** — mode stays internal, and the
  external surface is still one query in, one answer out. If anything the merge
  strengthens it: with one tool over both lanes there is one fewer thing for a
  caller to choose.
