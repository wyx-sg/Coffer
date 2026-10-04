## Why

The web UI keeps its data fresh by polling: each hook picks its own interval,
between 5 and 60 seconds, so a change made in the terminal or by a reconcile
pass shows up late, and a page that shows every kind would have to poll every
kind. The ADR
[The Wire Contract Is Generated From the Pydantic Models](../../../docs/decisions/wire-contract-generated-from-the-pydantic-models.md)
chooses one daemon-wide change feed of invalidation hints instead (option E1).

## What Changes

- `GET /api/v1/events` is one Server-Sent Events stream for the whole daemon,
  gated by the token header and read with `fetch`, whose envelopes
  `{seq, kind, id, rev, op}` say *what* changed — never the new state.
- Every resource write through the framework (the same seam that feeds the
  reconciler's `Changed(kind, uid, rev)` hint) and every change in the
  attention list produces one envelope.
- The daemon holds a bounded replay buffer. A client reconnects with
  `Last-Event-ID` and receives what it missed; when the buffer no longer
  covers the gap it receives one `resync` event and refetches everything.
- An idle stream carries a `heartbeat` event so a client can tell a quiet
  daemon from a dead connection.
- The envelope, resync and heartbeat events are Pydantic models, so they are
  documented in the generated contract like every other wire shape.

## Impact

- resource-framework: one new requirement and its route.
- The frontend's query-invalidation client over this stream is follow-up work
  for the rebuilt pages.
