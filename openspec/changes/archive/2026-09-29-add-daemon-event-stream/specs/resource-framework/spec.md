## ADDED Requirements

### Requirement: Announce every change on one daemon-wide event stream
`GET /api/v1/events` MUST be one Server-Sent Events stream for the whole
daemon, gated by the token header like every other management call, so a
client reads it with `fetch` rather than `EventSource`. Each `change` event
MUST carry an envelope `{seq, kind, id, rev, op}` and an SSE id that names both
the daemon run and the `seq`, because `seq` starts again at 1 on every run:
`seq` grows by one per event across the daemon run, `kind` is the resource
kind or `attention`, `id` is the resource's uid (none for `attention`), `rev`
is the revision the write produced (none for `attention`), and `op` is
`upsert` or `delete`. Every resource write through the framework MUST produce
one envelope, and so MUST every change in what the attention list reports. An
envelope is an invalidation hint only: it MUST NOT carry the resource's state,
and a client refetches through the typed endpoints. The daemon MUST keep a
bounded buffer of recent envelopes: a client that reconnects with
`Last-Event-ID` MUST receive every envelope after that `seq` still in the
buffer, in order, and then live ones; when the buffer cannot cover the gap —
the `seq` is older than the buffer's oldest, or is not one this daemon run has
issued — the stream MUST send one `resync` event before going live, telling the
client to refetch everything. While nothing changes the stream MUST send a
`heartbeat` event carrying the current head `seq` at a fixed interval.

#### Scenario: a resource write is announced as an invalidation hint
- **GIVEN** a client reading the event stream
- **WHEN** a resource is disabled and then deleted
- **THEN** the client receives two `change` events for that uid, an `upsert` carrying the revision the disable produced and then a `delete`, with consecutive `seq` values
- **AND** neither envelope carries any field of the resource beyond its kind, uid and revision

#### Scenario: a reconnecting client resumes after the last event it saw
- **GIVEN** a client that saw `change` events up to `seq` n and disconnected, after which two more resources were written
- **WHEN** it reconnects with the SSE id of event n as `Last-Event-ID`
- **THEN** it receives exactly the two missed envelopes, `seq` n+1 and n+2, before any live event, and no `resync`

#### Scenario: a client the buffer cannot cover is told to resync
- **GIVEN** more writes since a client's last `seq` than the buffer holds, or a `Last-Event-ID` this daemon run never issued — an earlier run's included, even when its `seq` is one this run has reached
- **WHEN** the client reconnects with that `Last-Event-ID`
- **THEN** the first event it receives is `resync`, and live `change` events follow it

#### Scenario: an attention change is announced on the event stream
- **GIVEN** a client reading the event stream and an attention list with no items
- **WHEN** something starts needing a person, so the attention list gains an item
- **THEN** the client receives a `change` event of kind `attention` with no id, and no attention item in it

#### Scenario: an idle event stream carries heartbeats
- **GIVEN** a client reading the event stream while nothing changes
- **WHEN** the heartbeat interval passes
- **THEN** the client receives a `heartbeat` event carrying the current head `seq`

#### Scenario: the event stream requires the token
- **GIVEN** a running daemon
- **WHEN** a client opens `GET /api/v1/events` without the `X-Coffer-Token` header
- **THEN** the request is refused `401 UNAUTHENTICATED` and no stream is opened
