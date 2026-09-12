# ADR provider-switching: Provider Switching

**Status**: Proposed
**Date**: 2026-06-21
**Spec**: [specs/provider-switching/spec.md](../../specs/provider-switching/spec.md)

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

See [specs/provider-switching/research.md](../../specs/provider-switching/research.md)
for the full enumeration of alternatives (A1/A2/A3, B1/B2/B3, C1/C2) and the
rationale for rejecting each alternative.

## Amendment 2026-06-22 — connections are optional overrides (introspection: inline secret)

Authoritative design: the [spec provider-switching Amendment 2026-06-22](../../specs/provider-switching/spec.md)
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

Authoritative design: the [spec provider-switching Amendment 2026-09-11](../../specs/provider-switching/spec.md)
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

Authoritative design: the [spec provider-switching Amendment 2026-09-11b](../../specs/provider-switching/spec.md)
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
  with migration 0067. What remains is the honest version: the whole filtered
  catalogue is offered, and a model this account cannot run fails when it is
  picked. Hardcoding the nine stays rejected: Claude Code ships models every few
  weeks, and a user whose new model never appeared would have no way to find out
  why.
- **D13 — An agent answers one question, and nothing narrows the answer.**
  `offered()` / `suggest()` return the whole filtered catalogue (or an active
  connection's curated set), with nothing on the agent and nothing on the channel
  narrowing either — there is no `…/models/selection` route any more, and the
  `…/models` route that served the catalogue over HTTP is gone too, its last
  reader being the channel dialogs that no longer ask. The channel `/model` card
  reads the catalogue in-process, pages through all of it and refuses no id.
  Nothing validates a model NAME against a catalogue — the CLI accepts names
  outside it entirely, so a model name stays raw passthrough everywhere.
