# Data Model — Provider Switching

Entities, fields, and reuse anchors for the provider registry.
Depends on the agent kind and its config-file store from spec
[agent-registry](../agent-registry/spec.md), on the Fernet vault from spec
credentials, and on the kind-agnostic Resource framework.

## Domain entities (`backend/coffer/domain/provider/`)

### `ProviderConfig` (`domain/provider/config.py`)

Pydantic v2 `BaseModel`, `extra="forbid"`. This is the synced `config` dict
stored on the resource row. It MUST NOT hold the raw secret, and it holds no
model the connection runs: a connection is a credentialed endpoint, and the
model is chosen at the point of use.

| Field | Type | Constraints / Notes |
|---|---|---|
| `protocol` | `Protocol` | Required. `"anthropic"`, `"openai"`, `"ollama"` or `"unknown"`. The wire the endpoint speaks: it drives model introspection and whether a key is required, and supplies the scope a new connection STARTS with. It is not a projection gate — that is the resource's scope. Mutable (the probe that guessed it can be wrong). |
| `base_url` | `str` | Required, non-blank (trimmed); the upstream endpoint. |
| `credential_ref` | `str \| None` | Fernet vault ref matching `^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$`, minted opaquely as `provider/<uuid4>/key`; several connections MAY share one. Required for `anthropic` / `openai` / `unknown`; MUST be absent for `ollama`, which has no key. Immutable once set. |
| `models` | `list[CuratedModel]` | The curated set of models this connection OFFERS downstream. Default `[]` = no restriction (the endpoint's whole catalogue). Shape-validated only: non-blank ids, deduplicated by id preserving order, at most 200 ids of at most 200 characters. Ids are opaque and passed verbatim to the vendor — never checked against a list Coffer holds. Not a chosen model. |
| `models[].modality` | `Modality` | `"text"` (the default), `"embedding"`, `"image"`, `"video"` or `"audio"` — which KIND of model the id is. STORED, never re-derived at read time. |
| `is_active` | `bool` | At most one `True` per AGENT TYPE at any time, enforced by the switch op. It records that this connection is the one currently written INTO the agents it reaches — a claim about a file Coffer does not own, which is why the boot self-check exists. Always `False` for `ollama`, which projects into nothing. |
| `internal_default` | `bool` | At most one `True` globally: the connection Coffer's own engine runs on. Its MODEL is a separate singleton, not stored here. Backed by a partial unique index, so a second flagged row is unrepresentable whatever writes it. |
| `transcribe_default` | `bool` | At most one `True` globally: the connection Coffer transcribes speech on. Its MODEL is a separate singleton too, and neither half falls back to the engine's — a gateway serving chat completions commonly serves no `/audio/transcriptions` at all, so with this unset Coffer uploads nothing and the agent receives the audio file. Upheld by `set_transcribe_default`'s clear-then-set; no partial unique index backs it yet. |

Reach — which agents the connection projects into — is deliberately NOT a field
here. It is the resource row's framework-level per-agent `scope`
([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)),
shared by every scoped kind. The agent names stay plain strings outside this
module, so the provider domain never imports the agent kind; the application
layer hydrates them at the projection seam
(`application/provider/targets.py`).

The scope a new connection starts with comes from the kind's `default_scope`
hook (`make_provider_kind().default_scope`, `application/provider/kind.py`),
which reads the wire through `starts_dormant(protocol)`
(`domain/provider/config.py`): an `ollama` connection starts `scope = []`,
dormant, because the framework's unscoped default would advertise a reach a
keyless connection can never have; every other wire, `unknown` included, starts
unscoped, which reaches every agent and goes on covering one registered later.
The hook cannot name agents itself — a scope holds agent uids, which no pure
config function can derive (ADR resource-identity-is-an-immutable-uid).

`model_ids(modality=None)` is the narrowing seam: a chat picker asks for `TEXT`
and can never be handed an embedding or image id, while an empty list keeps
meaning "no restriction" for the caller to interpret.

All fields are JSON-stable so `model_dump(mode="json")` serialises cleanly for
SQLite and for sync.

### `Protocol` (`domain/provider/config.py`)

```python
class Protocol(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    UNKNOWN = "unknown"
```

`unknown` means the probe was inconclusive: the connection starts open to every
agent and the user decides. There is no `WireFormat` and no `WireApi` enum —
the Codex `wire_api` choice lives on the agent's binding, where its only legal
value is `responses`.

### `CuratedModel` / `Modality` (`domain/provider/config.py`, `modality.py`)

```python
class CuratedModel(BaseModel):     # extra="forbid"
    id: str
    modality: Modality = Modality.TEXT
```

`Modality` is a `StrEnum` over `text`, `embedding`, `image`, `video`, `audio`.
`infer_modality(model_id)` holds the single inference rule, used in exactly two
places — the one-shot migration that converted stored plain-string entries, and
endpoint introspection, which returns a suggestion the connection editor
pre-fills. Nothing infers at load time: a stored entry is taken as written.

### `ResolvedConnection` (`domain/provider/config.py`)

A frozen dataclass pairing a `ProviderConfig` with the `model` to run on it.
The model lives apart from the connection, so the two travel together whenever a
caller needs both. Its one consumer is Coffer's own engine, which does the
pairing and builds a chat model from the result (spec
[internal-engine](../internal-engine/spec.md)); this kind only declares the
value object.

### Errors (`domain/provider/errors.py`)

| Error | Code | Status | When |
|---|---|---|---|
| `ProviderCredentialSourceInvalid` | `PROVIDER_CREDENTIAL_SOURCE_INVALID` | 422 | both or neither credential source supplied |
| `NoActiveProvider` | `NO_ACTIVE_PROVIDER` | 404 | a key was asked for and nothing is active |
| `ProviderProtocolLockedWhileActive` | `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` | 409 | a wire change on a connection that is active (see "Refuse to move the wire of a live connection") |
| `ProviderInternalOnly` | `PROVIDER_INTERNAL_ONLY` | 409 | activating an `ollama` connection (see "Keep ollama connections internal-only") |
| `ProviderInternalDefaultTaken` | `PROVIDER_INTERNAL_DEFAULT_TAKEN` | 409 | a resource write that would flag a second internal-engine default (see "Keep at most one internal-engine default") |

### Projection functions (`domain/provider/projection.py`)

Pure (I/O-free) functions that take the file's existing text and return the new
text, analogous to `domain/agent/mcp_install.py`'s `apply_install`.

- `apply_anthropic_settings(text, *, base_url, api_key_helper, model, effort, tier_models, picker_models, replace_builtin_picker, local, local_context_window, loopback_proxy) -> str`
  and its inverse `remove_anthropic_settings(text, *, managed_model, managed_effort) -> str`
- `apply_codex_provider(text, *, base_url, model, wire_api, display_name, auth, effort, provider_id, catalog_path) -> str`
  (in `domain/provider/codex_projection.py`) and its inverse
  `remove_codex_provider(text, *, provider_id, managed_effort) -> str`
- `suggest_tier_models(model, curated, *, local) -> dict` (`domain/agent/tiers.py`) —
  the tier pins used when the agent stores none
- `codex_model_catalog_json(models) -> str | None` — the catalogue document, or
  `None` when there is nothing honest to write; `codex_model_catalog_path(dir)`
- `proxy_token_helper(agent_uid, *, coffer_cli) -> str` and
  `proxy_token_args(agent_uid)` (`domain/provider/api_key_helper.py`) — the
  only helper line Coffer writes and the argument list Codex's `auth` command
  runs; both cite the agent's uid, so they survive a rename.
  `is_managed_api_key_helper(helper)` recognises that line and the
  `provider key` line earlier builds wrote

Each agent's provider projection facet (`domain/provider/agent_projection.py`:
`ClaudeCodeProviderProjection`, `CodexProviderProjection`) composes these into a
`ProjectionPlan {text, before, after}` from a `ProviderProjectionRequest`, names
its `config_key`, declares the `protocols` its native config speaks (possibly
none) and answers `is_present(text)`. The writer is chosen by AGENT, never by
protocol, and nothing maps a protocol to one agent.
- Constants: `CODEX_PROVIDER_ID`, `CODEX_MODEL_CATALOG_FILENAME`,
  `CODEX_MODEL_CATALOG_KEY`, `CODEX_CATALOG_TRUNCATION_LIMIT`

`domain/provider/codex_shell_env.py` holds `LEGACY_CODEX_ENV_KEY`
(`COFFER_PROVIDER_KEY`), the variable earlier builds named as the provider
block's `env_key` and listed in `shell_environment_policy.exclude`.
`drop_legacy_shell_env_exclude` removes that entry on every Codex write and
de-projection; nothing writes it.

### Managed native-config keys, per agent type

The writer is chosen by the AGENT the connection reaches, not by the
connection's protocol, so an OpenAI-compatible gateway routed to Claude Code
writes Claude's shape. Only these keys are Coffer's; everything else in the file
is preserved, and the projection tests assert exactly this set.

**Claude Code — `~/.claude/settings.json` (JSON):**

| Managed key path | Source |
|---|---|
| `apiKeyHelper` | `"<absolute path to coffer> proxy token --agent-uid <agent uid>"` (shell-quoted; the bare `coffer` when no CLI is found) — prints the agent's local proxy token, never a provider key |
| `env.ANTHROPIC_BASE_URL` | the local model proxy's Anthropic route, `http://127.0.0.1:<proxy port>/anthropic` |
| `env.NO_PROXY` | gains `127.0.0.1,localhost`, appended to the user's own entries; de-projection takes back only that appended pair |
| `model` | the AGENT binding's `model`; left untouched when unbound, removed on de-projection only while it still equals the binding |
| `effortLevel` | the binding's `effort`; same rule |
| `env.ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL` | the binding's `tier_models`, else Coffer's suggestion (`suggest_tier_models`); an unpinned tier is removed |
| `modelPicker` | the connection's curated text models, each option described `via Coffer` (the ownership marker); `replaceBuiltInOptions` true when no curated id is a Claude id |
| `env.CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` / `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` | a local runtime only: `"1"` and the chosen model's recorded window |

Every write deletes `env.ANTHROPIC_MODEL` and `env.ANTHROPIC_SMALL_FAST_MODEL`,
which earlier builds wrote. A `provider key` helper an earlier build wrote is
still recognised as Coffer's, so de-projection removes it.

`ANTHROPIC_API_KEY` is never written — it would override the helper.
De-projection removes an `apiKeyHelper` only when `is_managed_api_key_helper`
recognises it — the `coffer` CLI (bare or by any path) followed by
`proxy token` or `provider key` — so a helper the user wrote is left alone.

**Codex — `~/.codex/config.toml` (TOML, via tomlkit):**

| Managed key path | Source |
|---|---|
| `model` | the agent binding's `model` (key removed when unbound) |
| `model_provider` | `"coffer"` |
| `model_catalog_json` | the absolute path of the Coffer-owned catalogue, written only while the connection curates `text` models; dropped otherwise |
| `model_providers.coffer.name` | `f"Coffer ({name})"` — deliberately the readable label, since nothing resolves it; it goes cosmetically stale after a rename until the next projection |
| `model_providers.coffer.base_url` | the local model proxy's Responses route, `http://127.0.0.1:<proxy port>/openai/v1` |
| `model_providers.coffer.wire_api` | the agent binding's `wire_api`, defaulting to `"responses"` |
| `model_providers.coffer.supports_websockets` / `requires_openai_auth` | `false` / `false` |
| `model_providers.coffer.auth` | `{command = "<absolute path to coffer>", args = ["proxy", "token", "--agent-uid", "<agent uid>"]}` |
| `model_reasoning_effort` | the binding's `effort`, only when the chosen curated model records that level |

Each catalogue entry carries `context_window`, `max_context_window` and
`auto_compact_token_limit` (90%) when the curated model records a window, and
`supported_reasoning_levels` / `default_reasoning_level` when it records levels.

The catalogue file is written before `config.toml` points at it, and the
pointer is dropped before the file is deleted, so Codex never reads a
`model_catalog_json` path that is not there. The pointer is removed only when it
names the Coffer-owned filename.

### The internal-engine default flag (`application/provider/`)

`set_internal_default(uid)` clears the flag on every other connection then sets
it on the target (serialised by the single-process daemon), emits
`provider_internal_default_set`, and notifies the engine that the connection
moved. `internal_default` is a field on the provider row and the partial unique
index `ux_provider_single_internal_default` is over the provider table, which is
why both are here.

What the flagged connection is USED for — the model paired with it, the chat
model built from the pair, the settings row, and the rule that drops a model the
new connection does not curate — is spec
[internal-engine](../internal-engine/spec.md). Nothing about that row is stored,
read or migrated by this kind.

### The speech-to-text default flag (`application/provider/transcribe_default_ops.py`)

`set_transcribe_default(uid)` is the twin of the operation above — clear
everywhere else, set the target, emit `provider_transcribe_default_set`, notify
the engine — kept in a module beside it rather than folded into it, because the
two flags are not the same flag and nothing here falls back to the other one.
`transcribe_connection(model)` answers WHICH connection carries this flag and
mints the `ResolvedConnection`; whether there is a model to pair at all is the
engine's question, asked in `application/engine/resolve.py`.

## Reuse anchors

All implementation MUST reuse these existing components; do not re-implement.

### Fernet vault (credential isolation)

| Component | Path | Used for |
|---|---|---|
| `EncryptedCredentialStore` | `backend/coffer/infrastructure/credentials/encrypted_store.py` | `get/set/exists/delete` — store and retrieve raw secrets |
| credential resolver | `backend/coffer/application/credentials/resolver.py` | resolve a ref to plaintext (key resolution) |
| citation guard | `ResourceService.find_credential_citations` | guard before deleting an owned secret |

### Config-file store (native config write)

| Component | Path | Used for |
|---|---|---|
| `ConfigFileStore.write_text_atomic` | `backend/coffer/infrastructure/agent/config_file_store.py` | atomic write + `.bak` (rotating `.bak.1` / `.bak.2`) — spec agent-registry "Write config files atomically with a backup and an audit entry" |
| `ConfigFileStore.fingerprint` / `delete_with_backup` | same | staleness detection (spec agent-registry "Reject stale config-file writes by fingerprint"); retiring the Codex catalogue |
| `spec_for` / `config_files_for` | `backend/coffer/domain/agent/config_files.py` | resolve the canonical path for an `AgentType` + key |
| `AgentType` descriptors | `backend/coffer/domain/agent/descriptor.py` | `claude_code` `settings` → `~/.claude/settings.json`; `codex` `config` → `~/.codex/config.toml` |

### Projection template (MCP injection)

| Component | Path | Used for |
|---|---|---|
| `apply_install` | `backend/coffer/domain/agent/mcp_install.py` | structural template for pure transforms that return TEXT |
| `mcp_entries.py` | `backend/coffer/domain/agent/mcp_entries.py` | JSON via `json.dumps`; TOML via `tomlkit` |

### Resource Kind pattern

| Component | Path | Used for |
|---|---|---|
| `Kind` dataclass | `backend/coffer/domain/resource.py` | define the `provider` kind |
| `Scope` / `is_active` | `backend/coffer/domain/scope.py` | the per-agent reach axis |
| kind factory | `backend/coffer/application/provider/kind.py` | `make_provider_kind()` — config schema, credential-ref extractor, `supports_scope`, `default_scope` |
| composition root | `backend/coffer/surfaces/http/provider_wiring.py` | build the service, mount the routes, register the kind |

### Single-active invariant

The activation flip uses sequential `ResourceService.update_config` calls (clear
the others, then set the target); the single-process daemon serialises requests
so switches never interleave. There is no `ProviderRepo` and no
`activate_atomic`.

### Sync

| Component | Path | Used for |
|---|---|---|
| `ResourceDoc` / `resource_to_doc` | `backend/coffer/domain/sync/serialization.py` | serialise provider rows |
| `SyncExporter` | `backend/coffer/application/sync/exporter.py` | step 1 of a converge round: write every kind's rows into the tree |
| `ResourceApplier` | `backend/coffer/application/sync/appliers.py` | apply an incoming document by `(kind, name)` — identity, description and config, never the reach |
| `ProviderProjectionTarget` | `backend/coffer/application/provider/projection_reconcile.py` | the reconciler's provider-projection target; the import's pass (`Trigger.IMPORT`) re-derives the projection from the converged rows |

### Audit

| Component | Path | Used for |
|---|---|---|
| `AuditEventType` | `backend/coffer/domain/audit.py` | `PROVIDER_SWITCHED`, `PROVIDER_INTERNAL_DEFAULT_SET`, `PROVIDER_TRANSCRIBE_DEFAULT_SET`, `PROVIDER_PROJECTION_REFUSED` |
| `AuditService.record` | `backend/coffer/application/audit_service.py` | emit them from the switch / internal-default / transcribe-default / projection paths |

## SQLite schema

The `provider` kind reuses the shared `resources` table (rows with
`kind='provider'`); `ProviderConfig` is stored in the existing `resources.config`
JSON column — **no new tables**. Every schema change this kind has needed has
been a data migration over those rows, one-shot, with no load-time shim:

| Revision | What it did |
|---|---|
| `0036` | moved the retired `chat_models` registry into provider resources |
| `0037` | forced the then-connection-level `wire_api` to `responses` |
| `0040` | slimmed the connection: `wire_format` → `protocol`, stripped `model` / `fast_model` / `wire_api` |
| `0051` | stripped the retired agent types from connections' then-`compatible_agents` |
| `0054` | added the partial unique index behind one global internal default |
| `0059` | wrote `models: []` into every existing row |
| `0064` | converted plain-string curated entries into `{id, modality}` objects |
| `0065` | pointed the embedding configuration at a connection, before it was removed |
| `0071` | materialised each row's effective reach into the framework `scope` and stripped `compatible_agents` |

Three more belong to the agent side of this feature: `0060` added a per-agent
curated set, `0063` took it back off, and `0061` forced the agent binding's
`wire_api` to `responses`.

## Audit events

| Value | When emitted |
|---|---|
| `provider_switched` | a successful `POST /providers/{uid}/activate` (details `{from, to, protocol, agents}`) or `POST /providers/use-builtin/{agent_type}` (details `{from, to: null, agent_type, agents}`) |
| `provider_internal_default_set` | a successful `POST /providers/{uid}/internal-default`; details `{from, to}` |
| `provider_transcribe_default_set` | a successful `POST /providers/{uid}/transcribe-default`; details `{from, to}` |
| `provider_projection_refused` | a native-config write refused because the file changed under Coffer |

`resource_created` / `resource_updated` / `resource_deleted` / `resource_renamed`
come from `ResourceService`; a change to the curated model set rides
`resource_updated`, whose before/after details carry the config verbatim (the
kind declares no redactor because its config holds no secret).

## Application service contracts (`backend/coffer/application/provider/`)

### `ProviderService` (`application/provider/service.py`)

| Method | Purpose |
|---|---|
| `create(...) -> Resource` | Validate the credential source (exactly one, or neither for ollama); store the secret; register the resource with the wire's default scope. |
| `list()` / `get(uid)` | The rows, as the surfaces read them. |
| `update(uid, patch, secret_value?)` | Partial update; rotates the vault entry when a secret is supplied. |
| `delete(uid)` | Guard the owned credential via `find_credential_citations`, remove it when unowned elsewhere, delete the resource. |
| `activate(uid) -> ActivateResult` | Clear-then-set for the per-agent-type invariant; project into every agent the scope reaches; de-project the agents the previous connection covered and this one does not; emit `provider_switched`. |
| `deactivate(agent_type) -> DeactivateResult` | Revert every agent of that type to its built-in login, switching the connection covering it off as a unit; idempotent. |
| `resolve_connection_key(uid) -> str` | That connection's key — what the projected `apiKeyHelper` calls, by uid. Raises `NoActiveProvider` when the connection reaches no agent (disabled, scoped to no agent, or keyless), by the same reach test the legacy wire form uses. |
| `resolve_active_key_for_agent(agent_type) -> str` | The key of the connection active for that agent (what Codex's env var is filled from). |
| `resolve_active_key(wire) -> str` | The legacy wire-keyed form, resolving through the agents whose provider facet declares that wire. |
| `set_internal_default(uid) -> Resource` | The global flag: clear-then-set, the audit event, and the notification that lets the engine apply its own drop rule. |
| `set_transcribe_default(uid) -> Resource` | The global speech-to-text flag, the same three steps against its own field and its own event. Independent of the one above. |

Decrypted values are returned to the caller and never logged.

There is deliberately no `rename` here. It was this kind's alone, and it existed
because the connection's NAME was written into another tool's config file; the
helper carries the uid now, so renaming is `ResourceService.rename` — the same
label edit every kind gets
([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).

### Results (`application/provider/results.py`)

```python
@dataclass
class ActivateResult:
    activated: str
    protocol: str
    projected: list[str]   # agent names written
    skipped: list[str]     # agents reached but not registered here
```

`DeactivateResult` reports the connection that was reverted and the agents
de-projected.

### `ProviderProjector` (`application/provider/projector.py`)

Projection is its own collaborator, not a private method on the service: it owns
the read → pure transform → write sequence, the Codex catalogue file's
lifecycle, and the refusal to write over content it did not read. It takes a
`ProjectionConfigStore` port (`read_text` / `write_text_atomic` / `fingerprint` /
`delete_with_backup`), so nothing below the application layer touches a path.

There is no `infrastructure/provider/persistence.py` and no `ProviderRepo`: a
connection is a plain resource row, so CRUD, audit and sync come from the
framework. `infrastructure/provider/introspector.py` is the kind's only
infrastructure module — the single place that calls a third-party endpoint.

## On-disk / sync layout

No new directories. Connections travel in the existing sync tree:

```
~/.coffer/sync/
  resources/
    provider/
      <uid>.yaml       # one deterministic YAML per connection (no secret),
                       # keyed on the uid so a rename modifies one file
  credentials/
    <credential_ref>.enc   # e.g. provider/<uuid4>/key.enc — Fernet
                           # ciphertext of the raw API key
```

Ciphertext travels only when the remote is configured to carry it, and the
reach a connection has on this machine does not travel at all. The only other
on-disk side effects are the native config files projection writes, their `.bak`
copies, and the Codex model catalogue.

## Constraints summary

- `ProviderConfig` MUST NOT include the raw secret at any time.
- The projection transforms MUST be pure; they return the new text.
- Key resolution MUST NOT log the decrypted value.
- The per-agent-type single-active invariant is enforced by sequential
  `ResourceService.update_config` calls serialised by the single-process daemon;
  the single global internal default is additionally enforced by the database,
  while the single global speech-to-text default rests on the operation alone
  (see "Keep an independent speech-to-text default").
- All HTTP routes are loopback-only, gated by `X-Coffer-Token`.

### Local model proxy state (`domain/model_proxy/state.py`)

What the daemon pushes the proxy over its control route, replaced wholesale on
every push: `ProxyState {revision, agents: [ProxyAgent {agent_uid, agent_type,
token_sha256}], routes: [ProxyRoute {agent_uid, wire, members: [ProxyMember
{connection_uid, connection_name, upstream_root, auth, key, models, local}]}]}`.
`key` is held only in the proxy's memory and never shown by `repr`. The
per-agent tokens live in the credential store under `proxy-token/<agent_uid>`
(machine-local; vault sync skips them). `~/.coffer/proxy.json` (mode `0600`)
holds `{port, pid, started_at, version, control_token}`.

### Local runtime (`ProviderConfig.local_runtime`)

`LocalRuntime {runtime: ollama | lmstudio | vllm | llama_server, version,
wires: [anthropic | openai]}` — what detection found; set only on a connection
whose `base_url` is loopback, and it makes `credential_ref` optional. Omitted
from the stored document when unset.

### Curated-model facts

`CuratedModel` gains `context_window`, `effort_levels`, `default_effort` and
`price` (`CuratedPrice {input, output, cache_write_5m?, cache_write_1h?,
cache_read?, web_search?}`, USD per million tokens / per thousand searches), each
omitted from the stored document while unknown.

### Usage (`usage_requests`, `usage_daily`, `quota_snapshots`; migration 0111)

- `usage_requests` — one row per proxied upstream attempt: every field of
  `UsageRecord` (`domain/usage/records.py`) plus `cost_usd`, `price_version`
  (`snapshot:<version>` or `override:<connection uid>`) and `unpriced`;
  `UNIQUE(source, dedupe_key)`. Retention follows `mcp_invocations`.
- `usage_daily` — per local day, agent, connection and model: request,
  unknown-usage and unpriced counts, token sums per category, estimated cost.
  Grouping columns use `''` for "none". Kept 365 days.
- `quota_snapshots` — the latest official window per `(agent_type,
  window_key)`: used percent, window length, reset time, label, source, when it
  was seen, plan. An older observation never replaces a newer one.
