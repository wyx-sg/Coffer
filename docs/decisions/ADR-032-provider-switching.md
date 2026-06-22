# ADR-032: Provider Switching

**Status**: Proposed
**Date**: 2026-06-21
**Spec**: [specs/011-provider-switching/spec.md](../../specs/011-provider-switching/spec.md)

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
  connection Coffer's internal LLM engine uses (memory organizer, reorg,
  distill, `coffer__ask`), set via `POST /providers/{name}/internal-default`
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

See [specs/011-provider-switching/research.md](../../specs/011-provider-switching/research.md)
for the full enumeration of alternatives (A1/A2/A3, B1/B2/B3, C1/C2) and the
rationale for rejecting each alternative.

## Amendment 2026-06-22 — connections are optional overrides (introspection: inline secret)

Authoritative design: the [spec 011 Amendment 2026-06-22](../../specs/011-provider-switching/spec.md)
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
- **Deviation from the block plan — the dialog keeps a model field.** The model
  remains a required field on the connection entity (projected to
  `ANTHROPIC_MODEL` / Codex `model`, per Decision D), so the dialog retains model
  selection — upgraded to the `ProviderModelField` combobox (test/fetch +
  dropdown + free text). Moving model selection onto the Agent page is the
  separate two-slot concern tracked under D3.
