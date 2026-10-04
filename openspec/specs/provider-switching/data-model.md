# Data Model — Provider Switching

Entities, fields, and reuse anchors for the provider registry.
Depends on the agent kind and its config-file store from spec
[agent-registry](../agent-registry/spec.md), on the Fernet vault from spec
secret, and on the kind-agnostic Resource framework.

## Domain entities (`backend/coffer/domain/provider/`)

### `ProviderConfig` (`domain/provider/config.py`)

Pydantic v2 `BaseModel`, `extra="forbid"`. This is the `config` of the
connection's resource file, `vault/resources/provider/<name>.json`. It MUST NOT hold the raw secret, and it holds no
model the connection runs: a connection is a credentialed endpoint, and the
model is chosen at the point of use.

| Field | Type | Constraints / Notes |
|---|---|---|
| `protocol` | `Protocol` | Required. `"anthropic"`, `"openai"`, `"ollama"` or `"unknown"`. The wire the endpoint speaks: it drives model introspection and whether a key is required, and supplies the scope a new connection STARTS with. It is not a projection gate — that is the resource's scope. Mutable (the probe that guessed it can be wrong). |
| `base_url` | `str` | Required, non-blank (trimmed); the upstream endpoint. |
| `secret_ref` | `str \| None` | Fernet vault ref matching `^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$`, minted opaquely as `provider/<uuid4>/key`; several connections MAY share one. Required for `anthropic` / `openai` / `unknown` unless the connection is a local runtime (`local_runtime` set), where it is optional; MUST be absent for `ollama`, which has no key. Immutable once set. |
| `models` | `list[CuratedModel]` | The curated set of models this connection OFFERS downstream. Default `[]` = no restriction (the endpoint's whole catalogue). Shape-validated only: non-blank ids, deduplicated by id preserving order, at most 200 ids of at most 200 characters. Ids are opaque and passed verbatim to the vendor — never checked against a list Coffer holds. Not a chosen model. |
| `models[].modality` | `Modality` | `"text"` (the default), `"embedding"`, `"image"`, `"video"` or `"audio"` — which KIND of model the id is. STORED, never re-derived at read time. |
| `local_runtime` | `LocalRuntime \| None` | Set when the endpoint is a model runtime on this machine (see "Local runtime" below); absent otherwise. |
| `internal_default` | `bool` | At most one `True` globally: the connection Coffer's own engine runs on. Its MODEL is a separate singleton, not stored here. Declared in the kind's `exclusive_flags`, so the vault validator refuses any commit — an API write, a hand edit, a sync merge — that would leave two flagged connections. |
| `transcribe_default` | `bool` | At most one `True` globally: the connection Coffer transcribes speech on. Its MODEL is a separate singleton too, and neither half falls back to the engine's — a gateway serving chat completions commonly serves no `/audio/transcriptions` at all, so with this unset Coffer uploads nothing and the agent receives the audio file. Declared in the kind's `exclusive_flags` like `internal_default`, so the vault validator refuses a second one, and a direct write that would make one is refused with `PROVIDER_TRANSCRIBE_DEFAULT_TAKEN`. |

There is no switched-on flag. Which agent runs on which connection is
`AgentConfig.connection_uid` ([agent-registry](../agent-registry/data-model.md)),
machine-local like the agent record, so an agent runs on at most one connection
by construction. A connection SERVES an agent when `connection_uid` names it, it
exists, is enabled, is not `ollama` and its scope reaches the agent;
`connection_for_agent(agent, connections)` in `application/provider/targets.py`
is the one function that decides, used by projection, the proxy state, the chat
model list, the switch operations and the protocol lock. A
pointer that fails the test means the agent is on its own login.

Reach — which agents the connection projects into — is deliberately NOT a field
here. It is the resource's framework-level per-agent `scope`, machine-local in
`local/reach.json`
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

All fields are JSON-stable so `model_dump(mode="json")` serialises cleanly into
the resource file.

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
the Codex block's `wire_api` is the fixed value `responses`, stored nowhere.

### `CuratedModel` / `Modality` (`domain/provider/config.py`, `modality.py`)

```python
class CuratedModel(BaseModel):     # extra="forbid"
    id: str
    modality: Modality = Modality.TEXT
```

`Modality` is a `StrEnum` over `text`, `embedding`, `image`, `video`, `audio`.
`infer_modality(model_id)` holds the single inference rule, used in one
place — endpoint introspection, which returns a suggestion the connection editor
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
| `ProviderSecretSourceInvalid` | `PROVIDER_SECRET_SOURCE_INVALID` | 422 | both or neither secret source supplied |
| `ProviderProtocolLockedWhileActive` | `PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE` | 409 | a wire change on a connection some agent runs on (see "Refuse to move the wire of a live connection") |
| `ProviderDoesNotReachAgent` | `PROVIDER_DOES_NOT_REACH_AGENT` | 409 | switching an agent onto a connection it is not reached by: the connection is switched off, or the connection's scope does not name the agent (see "Switch one agent at a time") |
| `ProviderInternalOnly` | `PROVIDER_INTERNAL_ONLY` | 409 | switching an agent onto an `ollama` connection (see "Keep ollama connections internal-only") |
| `ProviderInternalDefaultTaken` | `PROVIDER_INTERNAL_DEFAULT_TAKEN` | 409 | a resource write that would flag a second internal-engine default (see "Keep at most one internal default connection") |
| `ProviderTranscribeDefaultTaken` | `PROVIDER_TRANSCRIBE_DEFAULT_TAKEN` | 409 | a resource write that would flag a second speech-to-text default (see "Keep an independent speech-to-text default") |

### Projection functions (`domain/provider/projection.py`)

Pure (I/O-free) functions that take the file's existing text and return the new
text, analogous to `domain/agent/mcp_install.py`'s `apply_install`.

- `apply_anthropic_settings(text, *, base_url, api_key_helper, model, tier_models, picker_models, replace_builtin_picker, local, local_context_window, loopback_proxy) -> str`
  and its inverse `remove_anthropic_settings(text, *, managed_model) -> str`
- `apply_codex_provider(text, *, base_url, model, display_name, auth, provider_id, catalog_path) -> str`
  (in `domain/provider/codex_projection.py`) and its inverse
  `remove_codex_provider(text, *, provider_id) -> str`
- `suggest_tier_models(model, curated, *, local) -> dict` (`domain/agent/tiers.py`) —
  the tier pins used when the agent stores none
- `codex_model_catalog_json(models) -> str | None` — the catalogue document, or
  `None` when there is nothing honest to write; `codex_model_catalog_path(dir)`
- `proxy_token_helper(agent_uid, *, coffer_cli) -> str` and
  `proxy_token_args(agent_uid)` (`domain/provider/api_key_helper.py`) — the
  only helper line Coffer writes and the argument list Codex's `auth` command
  runs; both cite the agent's uid, so they survive a rename.
  `is_managed_api_key_helper(helper)` recognises that line

Each agent's provider projection facet (`domain/provider/agent_projection.py`:
`ClaudeCodeProviderProjection`, `CodexProviderProjection`) composes these into a
`ProjectionPlan {text, before, after}` from a `ProviderProjectionRequest`, names
its `config_key`, declares the `protocols` its native config speaks (possibly
none) and answers `is_present(text)`. The writer is chosen by AGENT, never by
protocol, and nothing maps a protocol to one agent.
- Constants: `CODEX_PROVIDER_ID`, `CODEX_MODEL_CATALOG_FILENAME`,
  `CODEX_MODEL_CATALOG_KEY`, `CODEX_CATALOG_TRUNCATION_LIMIT`

### Managed native-config keys, per agent type

The writer is chosen by the AGENT being switched, not by the
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
| `env.ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU,FABLE}_MODEL` | the binding's `tier_models`, else Coffer's suggestion (`suggest_tier_models`); an unpinned tier is removed |
| `modelPicker` | the connection's curated text models, each option described `via Coffer` (the ownership marker); `replaceBuiltInOptions` true when no curated id is a Claude id |
| `env.CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` / `env.CLAUDE_CODE_MAX_CONTEXT_TOKENS` | a local runtime only: `"1"` and the chosen model's recorded window |

`ANTHROPIC_API_KEY` is never written — it would override the helper.

What is Coffer's: the `env` keys above (base URL, tier pins, the two
local-runtime keys and the `NO_PROXY` pair) carry no mark of their own, so they
are Coffer's only while Coffer's `apiKeyHelper` is in the file. A file whose
helper is absent or the user's own, but which holds an `ANTHROPIC_BASE_URL` or
tier pins, is the user's own gateway setup: de-projection leaves it byte-for-byte
and drift detection does not report it. `modelPicker` is Coffer's only when every
option carries the `via Coffer` marker; `model` only while it
equals the agent's binding. Coffer writes no `effortLevel`; one in the file is the user's own.
De-projection removes an `apiKeyHelper` only when `is_managed_api_key_helper`
recognises it — the `coffer` CLI (bare or by any path) followed by
`proxy token` — so a helper the user wrote is left alone.

**Codex — `~/.codex/config.toml` (TOML, via tomlkit):**

| Managed key path | Source |
|---|---|
| `model` | the agent binding's `model` (key removed when unbound) |
| `model_provider` | `"coffer"` |
| `model_catalog_json` | the absolute path of the Coffer-owned catalogue, written only while the connection curates `text` models; dropped otherwise |
| `model_providers.coffer.name` | `f"Coffer ({name})"` — deliberately the readable label, since nothing resolves it; it goes cosmetically stale after a rename until the next projection |
| `model_providers.coffer.base_url` | the local model proxy's Responses route, `http://127.0.0.1:<proxy port>/openai/v1` |
| `model_providers.coffer.wire_api` | the fixed value `"responses"` |
| `model_providers.coffer.supports_websockets` / `requires_openai_auth` | `false` / `false` |
| `model_providers.coffer.auth` | `{command = "<absolute path to coffer>", args = ["proxy", "token", "--agent-uid", "<agent uid>"]}` |

Each catalogue entry carries `context_window`, `max_context_window` and
`auto_compact_token_limit` (90%) when the curated model records a window, and
an empty `supported_reasoning_levels` (Codex's parser requires the field) and no `default_reasoning_level`. Coffer writes no `model_reasoning_effort`; one in the file is the user's own.

The catalogue file is written before `config.toml` points at it, and the
pointer is dropped before the file is deleted, so Codex never reads a
`model_catalog_json` path that is not there. The pointer is removed only when it
names the Coffer-owned filename.

### The internal-engine default flag (`application/provider/`)

`set_internal_default(uid)` clears the flag on every other connection then sets
it on the target (serialised by the single-process daemon), emits
`provider_internal_default_set`, and notifies the engine that the connection
moved. `internal_default` is a field in the provider's config and the kind
declares it exclusive (`exclusive_flags`), which is why both are here: the
vault's resource rule refuses any write — a surface's, a hand edit or a sync
round's merged tree — that would leave two connection files flagged, and names
the file that already holds it.

What the flagged connection is USED for — the model paired with it, the chat
model built from the pair, the settings document, and the rule that drops a
model the new connection does not curate — is spec
[internal-engine](../internal-engine/spec.md). Nothing about that document is
stored, read or migrated by this kind.

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

### Fernet vault (secret isolation)

| Component | Path | Used for |
|---|---|---|
| `EncryptedSecretStore` | `backend/coffer/infrastructure/secret/encrypted_store.py` | `get/set/exists/delete` — store and retrieve raw secrets |
| secret resolver | `backend/coffer/application/secret/resolver.py` | resolve a ref to plaintext (key resolution) |
| citation guard | `ResourceService.find_secret_citations` | guard before deleting an owned secret |

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
| `Scope` | `backend/coffer/domain/scope.py` | the per-agent reach axis |
| kind factory | `backend/coffer/application/provider/kind.py` | `make_provider_kind()` — config schema, secret-ref extractor, `supports_scope`, `default_scope` |
| composition root | `backend/coffer/surfaces/http/provider_wiring.py` | build the service, mount the routes, register the kind |

### One connection per agent

The invariant is structural: the choice is the agent record's `connection_uid`,
one value per agent. `ProviderService.activate(uid, agent_type)` projects into
that agent's file, then writes that agent's record through the agent service;
a failure restores the file. There is no `ProviderRepo`, no `activate_atomic`
and no clear-the-others step.

### Sync

A connection's resource file is a vault file like any other, so a sync round
carries it by merging commits; nothing in this kind serialises or applies it.

| Component | Path | Used for |
|---|---|---|
| `ProviderProjectionTarget` | `backend/coffer/application/provider/projection_reconcile.py` | the reconciler's provider-projection target; after a round that applied changes, the sync service runs one reconcile pass (`Trigger.IMPORT`) that re-projects the agents that run on a connection from the connections as they now are |

### Audit

| Component | Path | Used for |
|---|---|---|
| `AuditEventType` | `backend/coffer/domain/audit.py` | `PROVIDER_SWITCHED`, `PROVIDER_INTERNAL_DEFAULT_SET`, `PROVIDER_TRANSCRIBE_DEFAULT_SET`, `PROVIDER_PROJECTION_REFUSED` |
| `AuditService.record` | `backend/coffer/application/audit_service.py` | emit them from the switch / internal-default / transcribe-default / projection paths |

## Storage

A connection is a resource file, `vault/resources/provider/<name>.json`, whose
`config` is `ProviderConfig`; its reach is `local/reach.json` (spec
resource-framework). **No tables.**

## Audit events

| Value | When emitted |
|---|---|
| `provider_switched` | a successful `POST /providers/{uid}/activate` (details `{from, to, protocol, agent_type, agents}`) or `POST /providers/use-builtin/{agent_type}` (details `{from, to: null, agent_type, agents}`) |
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
| `create(...) -> Resource` | Validate the secret source (exactly one, or neither for ollama); store the secret; register the resource with the wire's default scope. |
| `list()` / `get(uid)` | The connections, as the surfaces read them. |
| `update(uid, patch, secret_value?)` | Partial update; rotates the vault entry when a secret is supplied. |
| `delete(uid)` | Guard the owned secret via `find_secret_citations`, remove it when unowned elsewhere, delete the resource. |
| `activate(uid, agent_type) -> ActivateResult` | Validate the connection reaches the agent, project into that agent's file, set its `connection_uid`, emit `provider_switched`; a failure puts the file back and leaves the record. |
| `deactivate(agent_type) -> DeactivateResult` | Revert that agent to its built-in login: de-project its file and clear its `connection_uid`; idempotent; touches no other agent. |
| `_key_of` -> `build_proxy_state(service, tokens) -> ProxyState` (`application/provider/proxy_state.py`) | What the local model proxy serves: each agent's token digest and, for each agent whose `connection_for_agent` is a connection, the one connection that serves it. The key is decrypted by the private `_key_of` through the secret boundary, and only while the state is built; it is the only consumer of a connection's key. |
| `ProxyTokenService.token_for(agent_uid)` / `rotate` / `revoke` (`application/provider/proxy_tokens.py`) | The agent's local proxy token, minted on first ask; `rotate` replaces it; `revoke` deletes it when the agent is removed. |
| `set_internal_default(uid) -> Resource` | The global flag: clear-then-set, the audit event, and the notification that lets the engine apply its own drop rule. |
| `set_transcribe_default(uid) -> Resource` | The global speech-to-text flag, the same three steps against its own field and its own event. Independent of the one above. |

Decrypted values are returned to the caller and never logged.

There is deliberately no `rename` here. It was this kind's alone, and it existed
because the connection's NAME was written into another tool's config file; the
helper carries the uid now, so renaming is `ResourceService.rename` — the same
label edit every kind gets
([A Resource's Identity Is the `uid` Inside Its File; Path and Name Are Location and Label](../../../docs/decisions/identity-is-the-uid-inside-the-file.md)).

### Results (`application/provider/results.py`)

```python
@dataclass
class ActivateResult:
    activated: str
    protocol: str
    agent_type: str
    agent: str             # the agent switched
```

`DeactivateResult` reports the agent type reverted, the agents de-projected and
the connection it was on (`previous`, or none).

### `ProviderProjector` (`application/provider/projector.py`)

Projection is its own collaborator, not a private method on the service: it owns
the read → pure transform → write sequence, the Codex catalogue file's
lifecycle, and the refusal to write over content it did not read. It takes a
`ProjectionConfigStore` port (`read_text` / `write_text_atomic` / `fingerprint` /
`delete_with_backup`), so nothing below the application layer touches a path.

There is no `infrastructure/provider/persistence.py` and no `ProviderRepo`: a
connection is a plain resource file, so CRUD, audit, history and sync come from
the framework and the vault. `infrastructure/provider/introspector.py` is the kind's only
infrastructure module — the single place that calls a third-party endpoint.

## On-disk layout

No new directories. Connections are vault files:

```
~/.coffer/vault/
  resources/
    provider/
      <name>.json          # one JSON document per connection (no secret);
                           # the uid inside is the identity, so a rename is one file's move
  secret/
    <secret_ref>.enc   # e.g. secret/provider/<uuid4>/key.enc — Fernet
                           # ciphertext of the raw API key
```

`vault/secret/` is committed and pushed only when the sync remote carries
secrets (`include_secret`), and the reach a connection has on this machine
(`local/reach.json`) never travels. The only other on-disk side effects are the
native config files projection writes, their `.bak` copies, and the Codex model
catalogue.

## Constraints summary

- `ProviderConfig` MUST NOT include the raw secret at any time.
- The projection transforms MUST be pure; they return the new text.
- Key resolution MUST NOT log the decrypted value.
- An agent runs on at most one connection because the choice is one field of the
  agent record; the single global internal default is additionally enforced by the vault
  validator on every commit, while the single global speech-to-text default
  rests on the operation alone
  (see "Keep an independent speech-to-text default").
- All HTTP routes are loopback-only, gated by `X-Coffer-Token`.

### Local model proxy state (`domain/model_proxy/state.py`)

What the daemon pushes the proxy over its control route, replaced wholesale on
every push: `ProxyState {revision, agents: [ProxyAgent {agent_uid, agent_type,
token_sha256}], routes: [ProxyRoute {agent_uid, wire, members: [ProxyMember
{connection_uid, connection_name, upstream_root, auth, key, models, local}]}]}`.
`key` is held only in the proxy's memory and never shown by `repr`. The
per-agent tokens live in the secret store under `proxy-token/<agent name>`
(machine-local ciphertext under `~/.coffer/local/secret/`, never in the vault). `~/.coffer/proxy.json` (mode `0600`)
holds `{port, pid, started_at, version, control_token}`.

### Local runtime (`ProviderConfig.local_runtime`)

`LocalRuntime {runtime: ollama | lmstudio | vllm | llama_server, version,
wires: [anthropic | openai]}` — what detection found; set only on a connection
whose `base_url` is loopback, and it makes `secret_ref` optional. Omitted
from the stored document when unset.

### Curated-model facts

`CuratedModel` gains `context_window` and
`price` (`CuratedPrice {input, output, cache_write_5m?, cache_write_1h?,
cache_read?, web_search?}`, USD per million tokens / per thousand searches), each
omitted from the stored document while unknown. The retired `effort_levels` and `default_effort` keys are dropped before validation, so a connection stored before reasoning effort was removed still loads and loses them on its next write.

### Usage (`usage_requests`, `usage_daily` in `runs.db`)

- `usage_requests` — one row per proxied request: every field of
  `UsageRecord` (`domain/usage/records.py`) plus `cost_usd`, `price_version`
  (`snapshot:<version>` or `override:<connection uid>`) and `unpriced`;
  `UNIQUE(source, dedupe_key)`. Retention follows `mcp_invocations`.
- `usage_daily` — per local day, agent, connection and model: request,
  unknown-usage and unpriced counts, token sums per category, estimated cost.
  Grouping columns use `''` for "none". Kept 365 days.

Coffer keeps no subscription quota table and shows no quota.
