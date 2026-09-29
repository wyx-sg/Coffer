## Context

Hints already exist in-process: every write through `ResourceService` passes
the hinting resource repository, which announces `Changed(kind, uid, rev)` to
the reconciler. The attention list is computed on demand from each kind's
source; nothing records when it changes.

## Decisions

- **One broker, fed from the existing seam.** The hint sink fans out: the
  reconciler still gets every hint, and the event broker turns each into an
  envelope. No kind announces its own writes.
- **Attention is watched, not pushed.** The attention list has no write of its
  own, so a watcher recomputes its fingerprint after each reconcile pass, after
  resource writes (settled), and on a slow period, and publishes one
  `attention` envelope when the fingerprint moves. The envelope carries no
  item: clients refetch `GET /api/v1/attention`.
- **Sequence numbers are per daemon run, and the id says which run.** `seq`
  starts at 1 each time the daemon starts and increases by one per envelope,
  so a bare `seq` cannot tell an earlier run's event 5 from this run's. The SSE
  id is therefore `<run>.<seq>`, with a random run name chosen at start. A
  `Last-Event-ID` naming another run, ahead of the head, or older than the
  buffer's oldest entry gets `resync`, because in each case the client may have
  missed something.
- **Bounded memory.** The buffer is a ring of the latest envelopes; each
  subscriber has a bounded queue, and a subscriber that falls behind its queue
  is sent `resync` and dropped back to live, never allowed to grow memory.
- **Heartbeat is an event, not a comment.** A `heartbeat` event carrying the
  head `seq` is readable by the same parser as every other event and tells a
  reconnecting client whether it is behind.

## Risks

- A burst of writes (a sync import) produces a burst of envelopes; the client
  coalesces invalidations per query key, so this costs refetches, not
  correctness.
