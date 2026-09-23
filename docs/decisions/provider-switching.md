# Provider Switching

**Status**: Accepted
**Date**: 2026-06-21
**Deciders**: Yuxing Wu
**Spec**: [openspec/specs/provider-switching/spec.md](../../openspec/specs/provider-switching/spec.md)

The live decision is the one below **as corrected by the amendments** at the end
of this file (D6 onwards). Three clauses of `## Decision` were reversed there and
not rewritten in place: a connection is a credentialed endpoint with `protocol`
*detected*, not a `wire_format` the user picks (D9); model and effort are fields
on the **agent**, not on the connection (D9, D10, D16); and what a connection
projects to is its **per-agent scope**, so one record may legitimately reach both
agents and "at most one active per wire format" is really at most one per agent
type. Read the amendments before relying on a sentence in `## Decision`.

## Context

Claude Code and Codex each require provider settings in separate native config
files (`~/.claude/settings.json`, `~/.codex/config.toml`). Users who want to
switch LLM providers (e.g. from the default Anthropic endpoint to a third-party
OpenAI-compatible endpoint, or vice versa) must today edit multiple files by
hand, store API keys in plaintext, and lose the audit trail. Credentials are
also not synchronised across machines.

## Decision

### A — single-wire profile, per-agent activation

A *provider profile* is a single record carrying `{name, wire_format,
base_url, credential_ref, model, fast_model, wire_api, is_active}`. Its
`wire_format` is either `"anthropic"` or `"openai"` and determines exactly
which native agent it projects to:

- `anthropic` → Claude Code (`~/.claude/settings.json`)
- `openai` → Codex (`~/.codex/config.toml`)

At most one profile per `wire_format` may be active at any time. Claude Code
and Codex share the same profile registry and may share a `credential_ref`, but
they are driven by separate profile records. There is no single record that
drives both agents simultaneously.

### B — credential isolation: key never written as plaintext into native config

The raw API key is stored in the Fernet vault only and materialised on demand
via two mechanisms:

- **Claude Code** (`apiKeyHelper`): `settings.json` is written with
  `apiKeyHelper = "coffer provider key --wire anthropic"`. Claude Code calls
  this command to fetch the key. The raw key is never written to `settings.json`.
  Because Claude Code re-invokes `apiKeyHelper` periodically, this design makes
  a future hot-switch almost free for Claude Code.
- **Codex** (`env_key`): `config.toml` is written with
  `[model_providers.coffer].env_key = "COFFER_PROVIDER_KEY"`. Codex reads the
  key from that env var at runtime. The raw key is never written to
  `config.toml`. The user must export `COFFER_PROVIDER_KEY` before starting
  Codex (documented in the spec quickstart). Auto env-injection into
  Coffer-spawned Codex is deferred with hot-switch.

This decision is consistent with the existing MCP `credential_refs` pattern.
The raw key also never appears in the sync workspace (`resources/provider/*.yaml`).

### C — phased delivery: hot-switch is deferred

This ADR covers: provider registry, projection (native config file write),
switch/activate operation, `PROVIDER_SWITCHED` audit event, and sync wiring.

**Hot-switch** (mid-session reload of a running Claude Code or Codex process)
is explicitly **out of scope** and will be addressed in a separate, later ADR
and PR.

### D — one LLM connection, used by both agents and Coffer's internal engine

A provider profile and Coffer's old `ModelConfig`/`chat_models` registry were the
same shape (key + endpoint + model) wearing two hats. They are unified into a
single **LLM connection** = the provider resource. The standalone `ModelConfig`
registry — the model CRUD REST and the `coffer model` CLI — is **retired** (its
rows migrate to provider resources; the provider model-introspection routes
`list-models` / `test-connection` are kept). To support this:

- `wire_format` gains a third value `ollama`: **internal-only**, projected to NO
  agent (`target_for` returns `None`), and keyless — so `credential_ref` becomes
  optional (required for anthropic/openai, absent for ollama).
- A global `internal_default` flag (≤1 across all connections) marks the
  connection Coffer's internal LLM engine uses (memory organizer, reorg),
  set via `POST /providers/{name}/internal-default`
  (audit event `provider_internal_default_set`) / `coffer provider
  internal-default`. One connection MAY be BOTH `is_active` (projected to its
  wire's agent) AND `internal_default` — one key, two uses.
- `build_chat_model` consumes a connection (`ProviderConfig`) dispatched by
  `wire_format`, replacing its dependency on `ModelConfig`. This fixes a real
  bug: the old anthropic/openai builders dropped the connection's `base_url`, so
  a custom/proxy endpoint was ignored. The internal consumers repoint from
  `ModelService.get_default()` to `ProviderService.resolve_internal_connection()`;
  with no `internal_default` set the internal engine is a clean no-op (as before).

The per-conversation `Conversation.model_id` column is now a vestigial legacy
column (kept, never validated against a registry).

## Consequences

### What projection writes (and never writes)

**anthropic → Claude Code** — Coffer merges these keys into
`~/.claude/settings.json` (JSON, atomic write + `.bak` backup via
`ConfigFileStore.write_text_atomic`, preserving all other keys):

| Managed key | Value |
|---|---|
| `apiKeyHelper` | `"coffer provider key --wire anthropic"` |
| `env.ANTHROPIC_BASE_URL` | `profile.base_url` |
| `env.ANTHROPIC_MODEL` | `profile.model` |
| `env.ANTHROPIC_SMALL_FAST_MODEL` | `profile.fast_model` (omitted when `None`) |

`ANTHROPIC_API_KEY` is **never written**.

**openai → Codex** — Coffer merges these keys into
`~/.codex/config.toml` (TOML, via `tomlkit`, atomic write + `.bak`, preserving
all other keys):

| Managed key | Value |
|---|---|
| `model` | `profile.model` |
| `model_provider` | `"coffer"` |
| `[model_providers.coffer].name` | `"Coffer (<profile name>)"` |
| `[model_providers.coffer].base_url` | `profile.base_url` |
| `[model_providers.coffer].wire_api` | `profile.wire_api` |
| `[model_providers.coffer].env_key` | `"COFFER_PROVIDER_KEY"` |

### Explicit non-goals

- **Proxy / failover / format conversion**: No proxying; no fallback chains; no
  anthropic↔openai protocol translation.
- **Hot-switch / running-process reload**: Deferred to a later PR.
- **Provider drift-verify**: Deferred to spec 4.9.
- **Explicit deactivate / native-config restore**: No "undo a switch" operation.
- **Per-agent provider override beyond wire matching**: A profile not matching
  an agent's wire is not projected to it; no manual per-agent binding.
- **Auto env-injection of `COFFER_PROVIDER_KEY` into Coffer-spawned Codex**:
  Deferred with hot-switch.

### Codex env-var seam — accepted consequence of Decision B

Codex requires `COFFER_PROVIDER_KEY` to be set in the shell before starting.
This is the accepted cost of never writing the raw key to `config.toml`. The
`apiKeyHelper` design does not have this seam for Claude Code. Auto-injection
is deferred.

### Sync

Modeling `provider` as a ResourceService Kind makes sync automatic at zero
engine cost. No new migration or `SCHEMA_VERSION` bump is needed.

### Activation sequencing

Activation clears `is_active` on other same-wire profiles via sequential
`ResourceService.update_config` calls, then sets the target's `is_active=true`.
The single-process daemon serialises requests, so switches never interleave.
Projection (`ProviderService._project`) runs BEFORE the activation flip; a
native-config write failure aborts the switch with the registry unchanged.

### Domain purity

Projection logic consists of pure functions `apply_anthropic_settings` and
`apply_codex_provider` in `backend/coffer/domain/provider/projection.py`; they
return the new native-config TEXT directly (mirroring `domain/agent/mcp_install.py`'s
`apply_install`). There is no `ProjectionPatch` dataclass and no `build_patch()`
function. All I/O (file writes) is performed by `ProviderService._project`.

## Alternatives considered

- **One record driving both agents at once (vs. A).** Rejected: it forces every
  agent's fields onto one record and leaves "active" undefined when one agent's
  write succeeds and the other's fails. The per-agent scope (see the preamble)
  later delivered the useful half — one gateway account reaching both agents —
  without collapsing two agents' activation into one flag.
- **A per-agent provider list with no shared registry (vs. A).** Rejected: it
  loses the unified audit, sync and encryption that are the point of the kind;
  it is the status quo this ADR replaces.
- **Writing the raw key into the native config (vs. B).** Rejected: plaintext
  keys in config files leak into backups, sync and git history, and it breaks
  the `credential_refs` pattern MCP servers already follow.
- **A local proxy that injects the key (vs. B).** Rejected: a new resident
  component, added latency, and clients reconfigured to hit it — and a proxy is
  also what protocol translation and failover would need, both non-goals.
- **Hot-switch in the first delivery (vs. C).** Rejected: detecting and
  signalling running agent processes, with partial failures, is substantially
  more work, while `apiKeyHelper` already gives Claude Code most of the effect.

## Amendment 2026-06-22 — connections are optional overrides (introspection: inline secret)

Authoritative design: the [spec provider-switching Amendment 2026-06-22](../../openspec/specs/provider-switching/spec.md)
(D1–D7). This ADR section records the introspection consequence delivered first
(D6); later D-points extend it.

- **D6 — the connection dialog tests/fetches with a not-yet-saved key.** The kept
  introspection routes (`POST /api/v1/models/test-connection`,
  `POST /api/v1/models/list-models`) now accept an inline `secret_value` in
  addition to `credential_ref`. `ModelIntrospectionService` prefers the inline
  secret and otherwise resolves the ref, so the add/edit dialog can probe a
  provider before the credential exists in the vault. The inline secret is used
  only for the outbound probe — it is never persisted by the introspection path
  (Decision B's store-ref-not-plaintext invariant is unchanged: the secret is
  saved to the Fernet vault only on connection create/update).
- **Deviation from the block plan — the dialog keeps a model field.**
  *(SUPERSEDED by D9 below — model leaves the connection entirely; the dialog's
  model field is removed.)* The model was kept on the connection through PR #206;
  D9 reverses that.
- **D8 — one gateway for two agents = two connections, not a multi-protocol
  connection.** cc-switch (the closest comparable) has no multi-protocol
  connection either — single-protocol providers + a "universal" scope. Dropping
  the planned `protocol`-set + per-protocol projection + migration: one upstream
  serving both Claude Code and Codex is two connections (the vault may store the
  key twice — functionally identical; sharing one `credential_ref` is an internal
  nicety, deliberately not surfaced as a reuse-UI). Proxy / hot-switch /
  conversion stay non-goals — exactly what cc-switch needs a resident proxy for.
- **D9 — a connection is a credentialed endpoint; model & protocol leave it.**
  The connection slims to `{name, base_url, credential_ref, protocol}`. `model`,
  `fast_model`, and the manual `wire_format` selector are REMOVED. `protocol` is
  DETECTED by probing the endpoint (anthropic-wire / openai-wire / unknown) — the
  add dialog shows only name + base_url + key + «测试连接». Model is chosen at the
  point of use: the Agent page's dual slots (`ANTHROPIC_MODEL` +
  `ANTHROPIC_SMALL_FAST_MODEL`), the internal-engine default selector, and the
  chat surface — each from the chosen connection's fetched models. **Projection
  input = connection (endpoint + key + protocol) + the agent binding (model).**
  This REOPENS Decision A (model/wire on the connection). The Agent page filters
  connections by detected protocol; an `unknown` protocol is shown to all agents
  (no silent hiding). Migration is a clean discard: existing connections drop
  `model`/`fast_model`; users re-select models on the Agent page. Why Claude Code
  needs an anthropic-wire endpoint even for non-Anthropic models: it only speaks
  the Anthropic Messages wire, so the endpoint must present it (native or via a
  translating proxy) — verified against Claude Code's published gateway docs.
  See spec provider-switching Amendment 2026-06-22b (E1–E5).

## Amendment 2026-09-11 — the connection curates WHICH models it offers

Authoritative design: the [spec provider-switching Amendment 2026-09-11](../../openspec/specs/provider-switching/spec.md)
(J1–J3).

- **D10 — `models` on the connection: the offered set, not a chosen model.** D9
  stands — no model the connection *runs* is stored on it, and every point of use
  still makes the choice. What the connection now records is which of its
  endpoint's models are on the menu at all: `models: list[str]`, EMPTY meaning no
  restriction (the endpoint's whole catalogue), which is the default and what
  every pre-existing connection gets from migration 0059. It is a middle state
  the design lacked — a gateway account serves dozens of models and its owner
  intends to use two or three, and neither "one model fixed on the connection"
  (too early a choice) nor "everything the endpoint serves" (too many) says so.
  Curated on the connection's detail page from live introspection; applied by
  every downstream picker that offers this connection's models, narrowing the
  connection term of the 2026-09-09 amendment's union while leaving the agent's
  own catalogue untouched. Ids stay opaque — shape validation only, never a check
  against a model name Coffer writes down. Carried by the existing create/patch
  (a patch replaces the whole value; `[]` clears it); no new route, and no audit
  event of its own — it rides `resource_updated`.

## Amendment 2026-09-11b — the agent curates which of its own catalogue it offers

Authoritative design: the [spec provider-switching Amendment 2026-09-11b](../../openspec/specs/provider-switching/spec.md)
(K1–K4).

- **D11 — Two tables in the CLI binary, not one.** The catalog Coffer reads is
  cumulative: it names every model the installed release has heard of. The
  bundle carries a second table naming the ones that are gone — a `remappedTo`
  tier for models the CLI silently reroutes, and per-provider retirement dates
  for the rest — and Coffer now applies the CLI's own predicate over it, using
  the `firstParty` column only (the others describe deployments Coffer does not
  configure). Read the same way as the catalog: located structurally, and a
  landmark that stops matching costs the FILTER, never a model wrongly hidden.
  The clock is injected so the rule is testable without a test that expires.
- **D12 — Beyond that, entitlement is the user's answer, not a derivable one.**
  On a current install the catalog lists nineteen models of which this account
  can run nine, and no field separates them: same price tier, same capabilities,
  same knowledge cutoff on both sides of the line, and no version-number rule
  holds. The CLI's own filter runs over a SERVER-provided account config with no
  local copy. **So nobody ticks (2026-09-12):** the first answer was
  `AgentConfig.models`, and that was the wrong owner — an agent has no audience,
  so curating it narrowed a chat on a phone and a person opening the agent page
  at once. Curation was moved to the surface that HAS an audience, a channel, and
  then removed from there as well: a channel binds an agent and nothing more, and
  a second place to tick turned out to be one more thing to keep in step with a
  catalogue that changes on its own. The agent field, its routes and migration
  0060's backfill are gone, stripped by migration 0063; the channel's pair went
  with migration 0068. What remains is the honest version: the whole filtered
  catalogue is offered, and a model this account cannot run fails when it is
  picked. Hardcoding the nine stays rejected: Claude Code ships models every few
  weeks, and a user whose new model never appeared would have no way to find out
  why.
- **D13 — An agent answers one question, and nothing narrows the answer.**
  `offered()` / `suggest()` return the whole filtered catalogue (or an active
  connection's curated set), with nothing on the agent and nothing on the channel
  narrowing either — there is no `…/models/selection` route any more. The
  `…/models` route that serves the catalogue over HTTP stays, because the one
  question an agent does answer still has to be asked: the web Chat page's model
  picker asks it per conversation and the agent detail page asks it to say what
  the agent can be put on. The channel `/model` card reads the same catalogue
  in-process, pages through all of it and refuses no id. Nothing validates a
  model NAME against a catalogue — the CLI accepts names outside it entirely, so
  a model name stays raw passthrough everywhere.

## Amendment 2026-09-13 — the Claude Code picker offers tier aliases

Authoritative design: the [spec provider-switching Amendment 2026-09-13](../../openspec/specs/provider-switching/spec.md)
(M1–M3).

- **D14 — Offer what the CLI offers, not what its binary remembers.** D12 said
  entitlement is not locally derivable and accepted that a model this account
  cannot run fails when it is picked. That cost turned out to be the whole
  experience: the catalog is cumulative, so the picker filled with names — whole
  internal families among them — that fail on use. Claude Code's own picker never
  asks for a versioned id; it offers four tier aliases and resolves each against
  the account at turn time. Coffer now offers exactly those, read from the
  `aliases` table that sits beside the catalog in the same bundle, each labelled
  with the display name of the model it currently resolves to — so the per-release
  distinction H1 went looking for survives, in the label instead of the id.
- **D15 — One table in the CLI binary, not two.** D11's retirement table is no
  longer read, and its injected clock is gone with it: an alias does not retire,
  and that table's only job was pruning the versioned list nothing offers now. The
  failure mode is unchanged in kind — an anchor that stops matching costs this
  source, never a wrong answer — but it now costs the whole source rather than
  the filter, which is the safe direction when the fallback would be the list this
  amendment exists to stop offering.

## Amendment 2026-09-13b — the effort a Codex turn thinks at is Coffer's to offer

Authoritative design: the [spec provider-switching Amendment 2026-09-13b](../../openspec/specs/provider-switching/spec.md)
(N1–N4).

- **D16 — An effort is a field beside the model, not a name inside it.** D14 made
  the picker offer what the agent's own picker offers; for Codex that is two
  things, not one. `model/list` reports a `supportedReasoningEfforts` list and a
  `defaultReasoningEffort` per model, and Coffer read neither — so on a machine
  whose `model/list` answers with a single model, the picker offered the one
  thing that was already decided and none of the thing that wasn't. The effort now
  rides beside the id the whole way: `AgentModel.efforts` / `.default_effort` out
  of the `…/models` route, `AgentConfig.effort` beside `AgentConfig.model` in the
  conversation's provider-owned blob, `effort` beside `model` on
  `PATCH …/agent-config` (mention one, the other is left alone; empty clears).
  Beside rather than inside because that is how the protocol takes it — a level
  baked into the name would be four entries for one model under ids Coffer made
  up, which J3 (ids stay opaque, never a name Coffer writes down) rules out. And nothing
  validates the level, for the same reason nothing validates a model name: the
  namespace is Codex's, so a fifth level works the day it ships.
- **D17 — Per turn, because the two alternatives are a lie and a dependency.**
  `thread/start` accepts an effort field and ignores it — the response goes on
  echoing the config default — so a thread-level control would have looked like it
  worked while changing nothing. `thread/settings/update` is real but gated behind
  the `experimentalApi` capability, which Coffer will not declare to set a field it
  can set without it. So the effort goes on `turn/start`, and was confirmed there
  by measurement rather than by reading: the same prompt reported 53 reasoning
  output tokens at `low` and 2569 at `xhigh`, ~48x, from Codex's own token-usage
  notification. For a setting whose effect never shows up in the response that
  acknowledges it, a number is the only acceptance test. An agent that reports no
  efforts sends no field and shows no control — the path is inert, not defaulted.

## Amendment 2026-09-17 — speech-to-text gets a flag of its own

Authoritative design: [spec provider-switching](../../openspec/specs/provider-switching/spec.md)
FR-035 and [spec internal-engine](../../openspec/specs/internal-engine/spec.md) FR-025 –
FR-027.

- **D18 — A second global flag, `transcribe_default`, not a second use of the
  first.** D said one connection, two uses: active for an agent AND the internal
  engine, one key. Voice transcription was folded in on that reasoning — it is
  something Coffer does on its own behalf, so it borrowed `internal_default` and
  introduced no new place to configure. It introduced a worse one. The two are
  not one endpoint wearing two hats: the gateway a user points Coffer's engine at
  serves chat completions and commonly serves no `/audio/transcriptions` at all,
  so the borrowed connection answered 404 on every voice message — replacing a
  safe, already-handled state (nothing marked ⇒ hand the agent the audio file,
  the recording never leaves the machine) with a failure. Speech-to-text
  therefore carries its own flag, of the same shape — at most one globally,
  clear-then-set, `provider_transcribe_default_set` audited, the engine notified
  so it can drop a model the new endpoint does not curate — and **nothing falls
  back to the other flag in either direction**. One connection may carry both,
  when one endpoint really does serve both.
- **D19 — And its own model, on the engine's settings row, because an
  environment variable could not be reached.** The speech-to-text model was
  `COFFER_TRANSCRIBE_MODEL`, read inside the daemon. The daemon is spawned
  detached by whichever surface first needs one and inherits that caller's
  environment, so a value exported in a shell profile never reached it: in a
  packaged install the model was unchangeable. It is a setting now, beside the
  engine's own model, and it follows the same both-halves-or-neither rule —
  unset means Coffer transcribes nothing, which is an answer rather than a
  failure.

## Implementation notes

Where the code stands against the clauses above, beyond the amendments:

- **Activation is per agent type.** A first tied a connection to one wire and
  made activation per wire; neither held. The wire was never the thing being
  taken over, so the single-active invariant is per agent type, and which agent
  types a connection covers is its per-agent scope. The projection writer is
  chosen by the agent type, not by the connection's protocol.
- **The helper cites the connection's uid.** Claude Code's `apiKeyHelper` is
  `coffer provider key --connection-uid <uid>`, not `--wire anthropic`, so the
  agent reads exactly the activated connection's key and a rename rewrites
  nothing. The `--wire` form survives for files written before that change.
- **Three non-goals shipped in narrow form.** Reverting an agent to its
  built-in login is `use-builtin/{wire}` (idempotent, ownership-aware). Coffer
  materialises `COFFER_PROVIDER_KEY` for every Codex process it spawns itself
  (`CODEX_ENV_KEY` lives in `domain/connection.py` so the provider kind and the
  chat kind's Codex adapter share it without importing each other); only a
  Codex started from the user's own shell needs the export. And drift-verify
  exists as a boot self-check that clears `is_active` when the projection is no
  longer in the file — it never re-projects.
- **A native config file is shared with its agent.** Atomic writes plus a
  fingerprint of the text read make a concurrent edit a refusal
  (`CONFIG_FILE_STALE`) rather than a silent overwrite, but cannot serialise the
  other program (`application/provider/projector.py`). The Codex merge goes
  through `tomlkit`'s dict API so comments and ordering survive.
- **The Codex model catalogue is a contract with another program.** A malformed
  `model_catalog_json` does not fail loudly — Codex warns and falls back to its
  built-in list — so the document's required fields are pinned by a test
  (`backend/tests/integration/providers/test_codex_model_catalog.py`).
- **Sync costs one post-import hook.** The kind converges through the
  framework's resource serialisation; what it adds is `sync_reconcile.py`, which
  re-derives each agent's projection after a converge round, because writing a
  native config file is a machine-local side effect no document can carry.
  Credentials travel only as Fernet ciphertext.
- **`provider_switched` is its own audit event** carrying `{from, to, protocol,
  agents}`, so the switch history can be read without diffing resource updates.
