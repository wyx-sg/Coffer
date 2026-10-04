# The Speech-to-Text Model Is a Setting; Its Endpoint Is Borrowed From a Flagged Connection

**Status**: Accepted
**Date**: 2026-10-04
**Deciders**: Yuxing Wu
**Related**: [Tidying Knowledge and Memory Is the Agent's Job](tidying-knowledge-and-memory-is-the-agents-job.md), [Provider Connections Projected Into Agent Config](provider-connections-projected-into-agent-config.md), [Sync Withholds Derived Output](sync-withholds-derived-output.md), [Kind Plugin Contract](kind-plugin-contract.md), spec internal-engine "Keep the engine's settings in one vault document", spec internal-engine "Transcribe speech on its own connection and model", spec internal-engine "Drop the speech-to-text model when its connection moves", spec internal-engine "Publish no document while the defaults hold", spec provider-switching "Keep an independent speech-to-text default"

## Context

Transcribing a voice message is the one model call Coffer makes on its own
behalf ([Tidying Knowledge and Memory Is the Agent's Job](tidying-knowledge-and-memory-is-the-agents-job.md)
puts every other judgement in the person's agent). The call needs two
things: an endpoint with a key and a model id. Coffer also runs two mechanical passes on timers (aggregate and
distil), each with a switch and an interval.

The endpoints and keys already exist. They are the user's LLM connections
(`kind='provider'`, [Provider Connections Projected Into Agent Config](provider-connections-projected-into-agent-config.md)),
stored once as vault files whose key is a secret reference, synced with the
vault, and shown on one page. A gateway account there typically serves dozens
of models.

Forces on the shape:

- **First run has nothing.** A fresh install has no connection and no model.
  Transcription runs on every inbound voice message, so "not configured" must
  not be an error; it hands the agent the audio file.
- **Settings converge across machines.** The settings are a vault document, so
  they travel through
  [Sync Only Pulls and Pushes the Vault Repository; a Clean Merge Is Applied, Any Conflict Stops for the Person](sync-applies-clean-merges-and-stops-on-any-conflict.md),
  and a change arrives from another machine as often as from a local write,
  with no event to fire when it does.
- **Chat and speech are different endpoints.** The gateway a user points
  agents at usually serves chat completions and often serves no
  `/audio/transcriptions` at all. When transcription borrowed a chat
  connection, it got a 404 on every voice message.
- **The daemon cannot read the user's shell.** It is spawned detached by
  whichever client needs it first ([Detect-or-Spawn](daemon-detect-or-spawn.md)),
  so an environment variable exported in a shell profile does not reach it. In a
  packaged install, `COFFER_TRANSCRIBE_MODEL` could not be changed at all.
- **Layering.** The settings are kind-agnostic substrate: `application/engine/`
  is in the "Kind-agnostic core does not import kind-specific code"
  import-linter contract (`backend/pyproject.toml`), so it cannot import the
  provider kind that holds the flag.

## Options Considered

### Option A — One global settings document owns the model; a flag on one connection lends the endpoint (chosen)

The settings are one vault state document, `state/settings/internal-engine.json`
(read and written by `infrastructure/persistence/internal_engine_repo.py`, typed
by `domain/internal_engine_config.py`), holding the speech-to-text
`transcribe_model`, each mechanical pass's switch and interval (`aggregate`,
`distil`). A key the
document does not carry reads as that key's default, and the time of the last
write is not in it (two machines stamping it would conflict on every edit): it
is this machine's own record, `local/engine.json`. The endpoint and key come
from the connection flagged `transcribe_default`. The flag is held by at most
one connection, set by clear-then-set
(`POST /api/v1/providers/{uid}/transcribe-default`) and audited
(`provider_transcribe_default_set`). That connection may also be active for an
agent: one key, several uses.

`application/engine/resolve.py` pairs the two halves. With no model chosen or
no connection flagged it answers `None`, and the chat layer hands the agent the
audio file, which keeps the recording on the machine.

When the flag moves, the provider kind notifies the settings through
`EngineNotifyPort`, a protocol the provider kind declares
(`application/provider/ports.py`). The settings keep the model only if the new
connection's curated `models` list names it, and otherwise clear it. Nothing is
probed, because a settings write must not depend on an endpoint being
reachable. Re-flagging the connection that already holds the flag changes
nothing. The composition root is the only place that sees both packages.

Pros: a connection keeps meaning one thing — which gateway account — and the
choice of model stays with the use, the same way an agent's model lives on the
agent ([Model Catalogue Read From the Agent](model-catalogue-read-from-the-agent.md));
the no-op default makes first run silent and correct; speech and chat can point
at different gateways; the settings stay out of the provider kind's import
graph. Cons: two independent settings can disagree. A live vault once paired one
provider with another provider's model. The drop rule is the repair. It wins
because the disagreement has a mechanical fix, while the alternatives either tie
the model to the wrong owner or cannot be reached from a packaged daemon.

### Option B — The model is a field on the connection

The connection carries `{base_url, key, model}` and speech uses the flagged
connection's model. This was the shape when models and providers were first
unified into one connection (PR #187), before model choice moved to each point
of use.

Pros: one record, no pairing, no way to disagree. Cons: a connection serves
agents, speech and the chat picker at once, and each wants a different model.
A model on the connection forces one choice onto every use, or forces the user
to duplicate the connection per model. It lost when model choice moved to the
point of use for agents; speech followed so that "connection" means the same
thing everywhere.

### Option C — Speech owns its own endpoint and key

The settings document holds a base URL, a secret reference and a model,
independent of the provider connections.

Pros: fully self-contained; no cross-kind notification. Cons: the same gateway
account is entered twice, the key is stored twice, and the two copies drift when
the user rotates it. The connections page stops being the one place endpoints
live. It loses on duplication.

### Option D — Environment variables

`COFFER_TRANSCRIBE_MODEL` and similar, read at daemon start.

Pros: zero UI, trivially scriptable. Cons: the daemon is spawned detached and
does not inherit a shell profile, so in a packaged install the variable never
arrives. Nothing converges across machines, and nothing is audited. This is
how the speech-to-text model worked until it was found to be unchangeable in a
packaged install. It remains only for operator knobs that are not user settings,
such as tool tiering ([Tool Overload](tool-overload-tier-the-list-search-the-rest.md)).

### Option E — Speech borrows the chat connection

A single flag for every model call Coffer makes on its own behalf. This is the
shape of the design this replaced, when Coffer also ran chat-model passes over
knowledge and memory through an internal default connection.

Pros: one fewer thing to configure. Cons: it broke voice. A chat gateway
commonly has no transcription endpoint, so a safe state — "no transcription,
the agent gets the audio file" — became a 404 on every voice message. It lost on
that incident, and the flag it needed no longer has any other use.

### Option F — A singleton row in the database

The same fields as one row of a settings table, the way every other piece of
configuration once lived.

- **Pros.** A transaction around the write; no file format to version; one
  place for configuration.
- **Cons.** The row was not meant to travel, so sync needed its own translator,
  a row has no absent state (a fresh machine and a configured one disagreed
  about whether the "document" existed), and the settings could not be read or
  edited as a file.
- **Why it loses.** Configuration is now files in the vault, which is what sync
  already merges; the settings gain the same history, writer and convergence as
  every other state document for no extra mechanism.

## Decision

Coffer's own operating settings are one global vault document that owns the
speech-to-text model, each mechanical pass's switch and interval. The endpoint and key are borrowed from the connection flagged
`transcribe_default`. The shape carries these rules:

- **A missing half resolves to `None`, not an error.** Both halves return the
  same `None`, so no consumer has to know which half was missing.
- **A moved flag drops a model the new connection does not curate.** Nothing is
  probed to decide.
- **Switches are per pass, not per collection or partition.** The question is
  what Coffer may do on a timer. A per-target setting would multiply rows,
  surfaces and defaults.
- **One value per write.** `PUT /api/v1/internal-engine-config/upkeep`
  and `…/transcribe-model` each change one pass or one value, so a toggle is
  never a read-modify-write over state another machine may be changing through
  sync. `use_default_interval` exists because JSON cannot tell "use the default"
  from "not sent".
- **Defaults are reported, not stored.** An unchosen interval is
  absent or `null` in the document and reported beside the default that applies
  (`application/upkeep_schedule.py`), so raising
  a default later reaches every vault that never chose one.
- **The schedule polls in slices.** Workers wait in 30-second slices and
  re-read the interval each slice (`SLICE_S`). A change that arrives through a
  converge round has no local event to subscribe to, so re-reading is the only
  wait that covers both local and remote writes.
- **The document is a decision, not a row.** A machine that holds every default
  writes no document, and a change back to all defaults removes it, so "the
  defaults" is always the absence of one. Deleting the document anywhere means
  "back to the defaults" everywhere. A document that always existed would have a
  fresh machine and a configured one write and delete it against each other on
  every round.
- **The settings never import the provider kind.** The provider kind answers
  "which connection" through `TranscribeConnectionPort` and is told about flag
  moves through `EngineNotifyPort`.

The document and its route family keep the name `internal-engine`; renaming
them would need a migration of stored files and audit rows for no change in
behaviour.

## Consequences

- Surfaces: `/api/v1/internal-engine-config` (plus `/upkeep` and
  `/transcribe-model`) and Settings › General → Speech-to-text. The Memory page
  carries the aggregate and distil switches. The connection flag is set on the
  provider kind's own route.
- Every write to the settings records `internal_engine_model_set` with the values
  after the write (spec internal-engine "Audit every write to the engine
  settings"). The event name is narrower than what it records, and renaming it
  would need a migration of the audit enum.
- A settings change takes effect within one 30-second slice, never instantly.
  That is the cost of covering remote writes.
- Pairing a model with a connection is the operator's job. The drop rule
  prevents the stale pairing a flag move would leave, but it cannot stop a user
  from choosing a model the endpoint does not serve. That failure shows up as a
  failed transcription, which falls back to handing the agent the audio file.
- A settings document written by an older build may still carry keys for model
  passes Coffer no longer runs, and for a per-call time limit that is now a
  fixed 60 seconds. They are ignored on read and dropped on the
  next write, while a key a newer build wrote survives.
