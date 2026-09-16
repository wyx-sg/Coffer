# Research — Internal Engine

Why the decisions in [spec.md](./spec.md) went the way they did. Most of this
prose was previously carried inside spec provider-switching's decision section,
where it described a facet of the connection registry rather than a subject of
its own.

## Why the engine is its own spec

It owns state nobody else does — the settings row, the schedule, the `settings`
state area and the Settings → Engine page — and its consumers are four other
specs (vault-sync's conflict resolver, knowledge's tidy, memory's organise,
chat's voice transcription) rather than the connection registry it borrows an
endpoint from. The coupling to that registry is two callables and a flag.

The counter-argument is that the engine is substrate, and substrate belongs in
the constitution rather than in a spec. It fails on the End-to-End Deliverable
Rule read backwards: substrate has no surfaces of its own, and this has three —
a route family, a page and (once FR-020/FR-021 ship) a CLI — plus defaults a
user can be harmed by. A spec with a page and a timer that rewrites files is a
feature.

## Why the model is not a field on the connection

A connection answers "which gateway account". Which model runs on it is a
property of the USE, and there are several uses: an agent's binding, a
conversation, and Coffer's own passes. Putting the engine's model on the
connection would have meant one of those uses silently owning a field the others
also read.

The cost of separating them is the drop rule: two independent settings can
disagree, and they did — a live vault paired one provider with another's model,
and Coffer's own passes then ran against a model the endpoint had never heard
of. The rule below is the repair.

## Why a change of connection drops the model, and why nothing is probed

Alternatives considered:

1. **Keep the model.** What shipped first. It produced exactly the pairing above.
2. **Probe the new endpoint and keep the model if it is served.** Correct in
   principle, but it makes a settings write depend on an endpoint being
   reachable: a laptop offline at the moment of the change either blocks or
   silently keeps a bad pairing.
3. **Drop unless the new connection CURATES the id** — chosen. A curated model
   list is that connection's own catalogue, written by the user, so an id on it
   is still servable without asking anyone. Everything else is dropped, and the
   dropdown shows its placeholder over the new connection's models.

Re-setting the connection that is already the internal default changes nothing,
so a settings page that submits a whole form never loses a model.

## Why `None` is a no-op rather than an error

Coffer is usable with no connection at all — that is the product's first-run
state and a deliberate one. Every internal pass therefore has to tolerate having
nothing to run on. Raising would turn an ordinary configuration into an error in
the daemon log four times over, and the surfaces that call the engine most often
(voice transcription on every inbound message, the description writer on every
ingest) would be the loudest.

The answer is `None` for BOTH missing halves — no connection flagged, and no
model chosen — because a caller that had to tell them apart would be encoding
this spec's internals.

## Why the unattended passes share the engine's row

They were considered as per-collection and per-partition settings first. Three
reasons against:

- The question they answer is about the ENGINE — what may Coffer's own model do
  while nobody is looking — not about a collection. A user who switches `tidy`
  off means "not on my files", not "not on this folder".
- A per-target setting multiplies: three passes times every collection and
  partition, each needing its own row, its own surface and its own default.
- The thing they gate is shared. There is one engine; the switches say what it
  may do.

## Why one pass per write

The settings page toggles one row at a time. A body carrying all three passes
makes every toggle a read-modify-write over state the operator may also be
changing on another machine, which converges through vault sync — the classic
lost update, on settings whose whole point is that one of them stops a rewriter.

`use_default_interval` exists because JSON cannot distinguish "set this to the
default" from "I did not send this field": `interval_s: null` is both.

## Why the default interval is reported rather than stored

A stored default freezes at the value it had the day the row was written.
Reported, it lives in the worker that owns the pass, so raising it later reaches
every vault that never chose one — which is most of them. The cost is one extra
field on the wire (`default_interval_s`), which the settings page needs anyway:
the alternative is a blank where a number belongs.

## Why the schedule polls instead of subscribing

A worker that went to sleep for six hours does not learn the interval is now
fifteen minutes until the six hours are up, so the setting appears not to work
for most of a day. An event fired by the settings write would fix that for a
local write only — and the write is as often on another machine, arriving
through a converge round, with no event to fire from over there. A sliced wait
that re-reads the interval each slice covers both cases with one mechanism, and
costs one read per slice on an idle daemon.

## Why the state area publishes a decision rather than a row

A singleton has no "absent" state a row can express, so a naive export
republishes whatever the row holds. A fresh machine does not persist a default it
already has, so it would delete that document every round while the other
machine re-added it — a ping-pong with no fixed point.

Publishing only a NON-default choice gives the area a fixed point: the tree holds
the document exactly while somebody has decided something, and its deletion means
"back to the defaults", which every machine can honour by writing the defaults
and then publishing nothing.

## Why `tidy` ships off and the other two ship on

The dividing line is what a pass WRITES, not how expensive or how clever it is.
`aggregate` and `organise` write derived files: delete them, run again, and you
have them back. `tidy` rewrites the user's own knowledge files, which are the
only copy. An unattended rewriter of the only copy is something an operator
switches on deliberately, not something they discover running.

## Alternatives considered but not in this spec

- **A second audit event for a switch change.** The event today is named for the
  model and fires for every write. Correcting it needs a rename or an addition
  to the audit enum, which is a migration — out of scope for the spec that first
  writes the requirement down, and recorded in [data-model.md](./data-model.md).
- **Owning `/api/v1/upkeep/runs`.** What is rewriting right now is a property of
  the daemon, answered in one read across kinds, like `/resources` and `/audit`.
  Folding it in here would make the engine own a cross-kind read it does not
  populate.
- **A per-machine owner for the unattended rewriter.** The column exists and is
  synced; nothing reads it since the machine axis was removed. Either it is
  dropped with a migration or it needs a requirement; this spec writes neither
  rather than specifying state that does nothing.
