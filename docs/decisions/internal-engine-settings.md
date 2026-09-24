# The Engine Owns Its Model; Its Endpoint Is Borrowed From a Flagged Connection

**Status**: Accepted
**Date**: 2026-09-17
**Deciders**: Yuxing Wu
**Related**: [Coffer's Own Model Is an Internal Engine](coffer-model-is-an-internal-engine.md), [Provider Connections Projected Into Agent Config](provider-connections-projected-into-agent-config.md), [Single Owner Machine for Unattended Rewrites](single-owner-machine-for-unattended-rewrites.md), [Sync Withholds Derived Output](sync-withholds-derived-output.md), [Kind Plugin Contract](kind-plugin-contract.md), spec internal-engine "Keep the engine's settings in one global row", spec internal-engine "Resolve the engine's connection and model together", spec internal-engine "Drop the engine model when its connection moves", spec internal-engine "Transcribe speech on its own connection and model", spec internal-engine "Publish no document while the defaults hold", spec provider-switching "Keep at most one internal-engine default", spec provider-switching "Keep an independent speech-to-text default"

## Context

[Coffer's own model](coffer-model-is-an-internal-engine.md) runs unattended
passes — memory distil, knowledge curation and ingest, sync conflict
resolution — and transcribes voice messages. Each needs three things: an
endpoint with a key, a model id, and a policy (whether the pass may run, how
often, how long one call may take).

The endpoints and keys already exist. They are the user's LLM connections
(`kind='provider'`, [Provider Connections Projected Into Agent Config](provider-connections-projected-into-agent-config.md)),
stored once, encrypted, synced, and shown on one page. A gateway account there
typically serves dozens of models.

Forces on the shape:

- **First run has nothing.** A fresh install has no connection and no model.
  The most frequent consumer — transcription, on every inbound voice message —
  would be the loudest error in the log if "not configured" were an error.
- **Settings converge across machines.** The engine settings travel through
  [vault sync](vault-sync.md) as the `settings` state area, so a change arrives
  from another machine as often as from a local write, and there is no local
  event to fire when it does.
- **Chat and speech are different endpoints.** The gateway a user points the
  engine at usually serves chat completions and often serves no
  `/audio/transcriptions` at all. When transcription borrowed the engine's
  connection, it got a 404 on every voice message.
- **The daemon cannot read the user's shell.** It is spawned detached by
  whichever client needs it first ([Detect-or-Spawn](daemon-detect-or-spawn.md)),
  so an environment variable exported in a shell profile does not reach it. In a
  packaged install, `COFFER_TRANSCRIBE_MODEL` could not be changed at all.
- **Layering.** The engine is kind-agnostic substrate: `application/engine/` is
  in the "Kind-agnostic core does not import kind-specific code" import-linter
  contract (`backend/pyproject.toml`), so it cannot import the provider kind
  that holds the flags.

## Options Considered

### Option A — One global settings row owns the model; a flag on one connection lends the endpoint (chosen)

`internal_engine_config` is a singleton row (`domain/internal_engine_config.py`)
holding the engine `model`, the speech-to-text `transcribe_model`, each
unattended pass's switch and interval (`aggregate`, `distil`, `curate`), the
bound on one model call (`model_timeout_s`) and the curation owner machine. The
endpoint and key come from the connection flagged `internal_default`; speech
comes from the connection flagged `transcribe_default`. Each flag is held by at
most one connection, set by clear-then-set
(`POST /api/v1/providers/{uid}/internal-default`, `…/transcribe-default`), and
audited (`provider_internal_default_set`, `provider_transcribe_default_set`).
One connection may carry both flags, and may also be active for an agent: one
key, several uses.

`application/engine/resolve.py` pairs the two halves. With no model chosen or
no connection flagged it answers `None`, and every pass treats `None` as "do
nothing". There is no fallback between the two flags in either direction:
nothing flagged for speech means Coffer transcribes nothing and hands the agent
the audio file, which keeps the recording on the machine.

When a flag moves, the provider kind notifies the engine through
`EngineNotifyPort`, a protocol the provider kind declares
(`application/provider/ports.py`). The engine's `InternalDefaultModelGuard`
(`application/engine/internal_default.py`) keeps the model only if the new
connection's curated `models` list names it, and otherwise clears it. Nothing is
probed, because a settings write must not depend on an endpoint being
reachable. Re-flagging the connection that already holds the flag changes
nothing. The composition root is the only place that sees both packages.

Pros: a connection keeps meaning one thing — which gateway account — and the
choice of model stays with the use, the same way an agent's model lives on the
agent ([Model Catalogue Read From the Agent](model-catalogue-read-from-the-agent.md));
the no-op default makes first run silent and correct; speech and chat can point
at different gateways; the engine stays out of the provider kind's import graph.
Cons: two independent settings can disagree. A live vault once paired one
provider with another provider's model, and Coffer's passes ran against a model
the endpoint had never heard of. The drop rule is the repair. It wins because
the disagreement has a mechanical fix, while the alternatives either tie the
model to the wrong owner or cannot be reached from a packaged daemon.

### Option B — The model is a field on the connection

The connection carries `{base_url, key, model}` and the engine uses the flagged
connection's model. This was the shape when models and providers were first
unified into one connection (PR #187), before model choice moved to each point
of use.

Pros: one record, no pairing, no way to disagree. Cons: a connection serves
agents, the engine and the chat picker at once, and each wants a different
model. A model on the connection forces one choice onto every use, or forces the
user to duplicate the connection per model. It lost when model choice moved to
the point of use for agents; the engine followed so that "connection" means the
same thing everywhere.

### Option C — The engine owns its own endpoint and key

The settings row holds a base URL, a credential ref and a model, independent of
the provider connections.

Pros: fully self-contained; no cross-kind notification. Cons: the same gateway
account is entered twice, the key is stored twice, and the two copies drift when
the user rotates it. The connections page stops being the one place endpoints
live. It loses on duplication.

### Option D — Environment variables

`COFFER_ENGINE_MODEL`, `COFFER_TRANSCRIBE_MODEL` and similar, read at daemon start.

Pros: zero UI, trivially scriptable. Cons: the daemon is spawned detached and
does not inherit a shell profile, so in a packaged install the variable never
arrives. Nothing converges across machines, and nothing is audited. This is
how the speech-to-text model worked until it was found to be unchangeable in a
packaged install. It remains only for operator knobs that are not user settings,
such as tool tiering ([Tool Overload](tool-overload-tier-the-list-search-the-rest.md)).

### Option E — Transcription borrows `internal_default`

A single flag for everything Coffer does on its own behalf.

Pros: one fewer thing to configure. Cons: this was shipped, and it broke voice.
A chat gateway commonly has no transcription endpoint, so a safe state — "no
transcription, the agent gets the audio file" — became a 404 on every voice
message. It lost on that incident.

## Decision

The engine's settings are one global row that owns the engine model, the
speech-to-text model, each unattended pass's switch and interval, the call
bound and the curation owner. Endpoints and keys are borrowed from the
connections flagged `internal_default` and `transcribe_default`, which are
separate flags with no fallback between them. The shape carries these rules:

- **A missing half resolves to `None`, not an error.** Both halves return the
  same `None`, so no consumer has to know which half was missing.
- **A moved flag drops a model the new connection does not curate.** Nothing is
  probed to decide.
- **Switches are per pass, not per collection or partition.** The question is
  what Coffer's one engine may do unattended. A per-target setting would
  multiply rows, surfaces and defaults.
- **One value per write.** `PUT /api/v1/internal-engine-config/upkeep`, `…/timeout`
  and `…/transcribe-model` each change one pass or one value, so a toggle is
  never a read-modify-write over state another machine may be changing through
  sync. `use_default_interval` exists because JSON cannot tell "use the default"
  from "not sent".
- **Defaults are reported, not stored.** An unchosen interval or bound is
  `NULL` in the row and reported beside the default that applies
  (`application/upkeep_schedule.py`, `application/engine_timeout.py`), so raising
  a default later reaches every vault that never chose one.
- **The schedule polls in slices.** Workers wait in 30-second slices and
  re-read the interval each slice (`SLICE_S`). A change that arrives through a
  converge round has no local event to subscribe to, so re-reading is the only
  wait that covers both local and remote writes.
- **Sync publishes a decision, not the row.** The `settings` area writes
  `internal-engine.yaml` only while some machine holds a non-default choice.
  Deleting it means "back to the defaults" everywhere
  (`application/engine_settings_sync.py`). A singleton has no absent state, so
  exporting the row itself would make a fresh machine and a configured one
  delete and re-add the document on every round.
- **The engine never imports the provider kind.** The provider kind answers
  "which connection" through `InternalDefaultConnectionPort` and
  `TranscribeConnectionPort` and is told about flag moves through
  `EngineNotifyPort`. Consumers reach the engine only through
  `ModelSelectorPort` and `LlmCompletionPort`.

## Consequences

- Surfaces: `/api/v1/internal-engine-config` (plus `/upkeep`, `/timeout`,
  `/transcribe-model`, `/curation-owner`), `coffer engine model|upkeep|timeout|transcribe-model|curate-owner`,
  and Settings → Coffer's model (`/settings/engine`). The connection flags are
  set on the provider kind's own routes and CLI.
- Every write to the row records `internal_engine_model_set` with the values
  after the write (spec internal-engine "Audit every write to the engine
  settings"). The event name is narrower than what it records, and renaming it
  would need a migration of the audit enum.
- A settings change takes effect within one 30-second slice, never instantly.
  That is the cost of covering remote writes.
- Pairing a model with a connection is the operator's job. The drop rule
  prevents the stale pairing a flag move would leave, but it cannot stop a user
  from choosing a model the endpoint does not serve. That failure shows up as
  failed passes in the upkeep run log, not as a settings error.
