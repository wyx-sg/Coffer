# Data Model — 011 Provider Switching

Entities, fields, and reuse anchors for the provider registry.
Depends on the agent kind from spec 004 and the kind-agnostic Resource
framework from spec 001.

## Domain entities (`backend/coffer/domain/provider/`)

### `ProviderConfig` (`domain/provider/config.py`)

Pydantic v2 `BaseModel`. This is the synced `config` dict stored on the
Resource row. It MUST NOT hold the raw secret.

| Field | Type | Constraints / Notes |
|---|---|---|
| `wire_format` | `WireFormat` | Required; `"anthropic"` or `"openai"`. |
| `base_url` | `str` | Required; upstream LLM endpoint URL. |
| `credential_ref` | `str` | Required; Fernet vault ref matching `^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$`. |
| `model` | `str` | Required; primary model id. |
| `fast_model` | `str \| None` | Optional; `ANTHROPIC_SMALL_FAST_MODEL` on Claude Code; ignored for openai. |
| `wire_api` | `WireApi` | Optional; `"chat"` (default) or `"responses"`; openai only. |
| `is_active` | `bool` | At most one `True` per `wire_format` at any time (FR-011). |

All fields are JSON-stable (no Python objects) so `model_dump(mode="json")`
serialises cleanly for SQLite and sync export.

### `WireFormat` and `WireApi` (`domain/provider/config.py`)

These enums live in `config.py` alongside `ProviderConfig`. There is no
separate `wire.py` module.

```python
class WireFormat(str, Enum):
    anthropic = "anthropic"
    openai = "openai"

class WireApi(str, Enum):
    chat = "chat"
    responses = "responses"
```

### Projection functions (`domain/provider/projection.py`)

Pure (I/O-free) functions that return the new native-config TEXT directly,
analogous to `domain/agent/mcp_install.py`'s `apply_install`. There is NO
`ProjectionPatch` dataclass and NO `build_patch()` function.

- `apply_anthropic_settings(config: ProviderConfig, existing_text: str) -> str`
- `apply_codex_provider(config: ProviderConfig, profile_name: str, existing_text: str) -> str`
- `ProjectionTarget` — descriptor for the target config file
- `target_for(wire: WireFormat) -> ProjectionTarget`
- Constants: `CODEX_PROVIDER_ID`, `CODEX_ENV_KEY`, `ANTHROPIC_API_KEY_HELPER`

### Managed native-config keys per `wire_format`

The pure functions in `domain/provider/projection.py`
(`apply_anthropic_settings` / `apply_codex_provider`) write exactly the keys
below into the agent's native config; `ProjectionTarget` + `target_for(wire)`
map each `wire_format` to its agent, allowlist key, and file format. The
projection tests assert on these managed keys so the spec and implementation
stay consistent.

**anthropic keys managed:**

| Managed key path | Source |
|---|---|
| `apiKeyHelper` | literal `"coffer provider key --wire anthropic"` |
| `env.ANTHROPIC_BASE_URL` | `profile.base_url` |
| `env.ANTHROPIC_MODEL` | `profile.model` |
| `env.ANTHROPIC_SMALL_FAST_MODEL` | `profile.fast_model` (omit when `None`) |

**openai keys managed:**

| Managed key path | Source |
|---|---|
| `model` | `profile.model` |
| `model_provider` | literal `"coffer"` |
| `model_providers.coffer.name` | `f"Coffer ({profile_name})"` |
| `model_providers.coffer.base_url` | `profile.base_url` |
| `model_providers.coffer.wire_api` | `profile.wire_api` |
| `model_providers.coffer.env_key` | literal `"COFFER_PROVIDER_KEY"` |

## Reuse anchors

All implementation MUST reuse these existing components; do not re-implement.

### Fernet vault (credential isolation)

| Component | Path | Used for |
|---|---|---|
| `EncryptedCredentialStore` | `backend/coffer/infrastructure/credentials/encrypted_store.py` | `get/set/exists/delete` — store and retrieve raw secrets |
| credential resolver | `backend/coffer/application/credentials/resolver.py` | resolve a ref to plaintext (key resolution) |
| HTTP adopt pattern | `backend/coffer/application/agent/mcp_entry_service.py:303` | model for "store secret, keep only ref" on create |
| citation guard | `ResourceService.find_credential_citations` | guard before deleting an owned secret |

### Config-file store (native config write)

| Component | Path | Used for |
|---|---|---|
| `ConfigFileStore.write_text_atomic` | `backend/coffer/infrastructure/agent/config_file_store.py` | atomic write + `.bak` backup |
| `spec_for` / `config_files_for` | `backend/coffer/domain/agent/config_files.py` | resolve the canonical path for a given `AgentType` + key |
| `AgentType` descriptors | `backend/coffer/domain/agent/descriptor.py` | `claude_code` `settings` → `~/.claude/settings.json`; `codex` `config` → `~/.codex/config.toml` |

### Projection template (MCP injection)

| Component | Path | Used for |
|---|---|---|
| `apply_install` | `backend/coffer/domain/agent/mcp_install.py` | structural template for pure projection functions that return TEXT |
| `mcp_entries.py` | `backend/coffer/domain/agent/mcp_entries.py` | JSON via `json.dumps`; TOML via `tomlkit` — reuse both |
| MCP service | `backend/coffer/application/agent/mcp_service.py` | driver pattern to mirror |

### Resource Kind pattern

| Component | Path | Used for |
|---|---|---|
| `Kind` dataclass | `backend/coffer/domain/resource.py` | define the `provider` Kind |
| kind factory | `backend/coffer/application/knowledge_base/kind.py` | model for `make_provider_kind(...)` |
| `wire_kb_kind` | `backend/coffer/surfaces/http/wiring.py` | model for `wire_provider_kind(...)` |
| composition root | `backend/coffer/surfaces/http/app.py` | where to register `app.state.kinds["provider"]` |

### Single-active invariant

The activation flip uses sequential `ResourceService.update_config` calls
(clear others, then set target); the single-process daemon serialises requests
so switches never interleave. There is NO `ProviderRepo` / `activate_atomic`.

| Component | Path | Used for |
|---|---|---|
| `ModelConfig` domain | `backend/coffer/domain/chat/model.py` | per-wire single-active pattern (mirror, do NOT couple) |
| `ResourceService.update_config` | existing resource service | used directly by `ProviderService.activate()` |

### Sync

| Component | Path | Used for |
|---|---|---|
| `ResourceDoc` / `resource_to_doc` | `backend/coffer/domain/sync/serialization.py` | serialise provider rows |
| `SyncExporter` | `backend/coffer/application/sync/exporter.py` | lists all kinds (automatic) |
| `SyncImporter` | `backend/coffer/application/sync/importer.py` | reconciles by `(kind, name)` (automatic) |

### Audit

| Component | Path | Used for |
|---|---|---|
| `AuditEventType` | `backend/coffer/domain/audit.py` | add `PROVIDER_SWITCHED` |
| `AuditEntry` | `backend/coffer/domain/audit.py` | event shape |
| `AuditService.record` | `backend/coffer/application/audit_service.py` | emit `PROVIDER_SWITCHED` from switch op |

## SQLite schema changes

**No new migration required.** The `provider` kind reuses the shared `resources`
table (new rows with `kind='provider'`). The `ProviderConfig` dict is stored in
the existing `resources.config` JSON column.

No new tables; no SCHEMA_VERSION bump.

## Audit events added

Add to `AuditEventType` in `backend/coffer/domain/audit.py`:

| Value | When emitted |
|---|---|
| `provider_switched` | Successful `POST /providers/{name}/activate`; details: `{from, to, wire_format, agents: [...projected...]}` |

`RESOURCE_CREATED`, `RESOURCE_UPDATED`, `RESOURCE_DELETED` are emitted
automatically by `ResourceService` on CRUD operations (no new event types
needed for those).

## Application service contracts (`backend/coffer/application/provider/`)

### `ProviderService` (`application/provider/service.py`)

| Method | Purpose |
|---|---|
| `create(name, config, secret_value?, credential_ref?, actor) -> Resource` | Validate; store secret if `secret_value` supplied; register Resource. Reject if both/neither credential source given. |
| `update(name, patch, secret_value?, actor) -> Resource` | Partial update; rotate vault entry if `secret_value` supplied. |
| `delete(name, actor) -> None` | Guard owned credential via `find_credential_citations`; remove vault entry if owned; delete Resource. |
| `activate(name, actor) -> ActivateResult` | Sequential clear-then-set for single-active invariant; project to matching registered agents; emit `PROVIDER_SWITCHED`. |
| `resolve_active_key(wire: WireFormat) -> str` | Find active profile for the given wire format; decrypt and return key (stdout only; caller must not log). No by-name resolution. |

### `ActivateResult` (`application/provider/service.py`)

```python
@dataclass
class ActivateResult:
    activated: str
    projected: list[str]   # agent names written
    skipped: list[str]     # agent names not matching or not registered
```

### `ProviderService._project` (`application/provider/service.py`)

Projection is an inlined private method on `ProviderService`; there is NO
separate `application/provider/projector.py` / `ProviderProjector` class.

`_project(profile_name, config, agent_config_dir)` calls
`apply_anthropic_settings(...)` or `apply_codex_provider(...)` (pure domain
functions returning TEXT), then writes via `ConfigFileStore.write_text_atomic`.

There is NO `infrastructure/provider/persistence.py` and NO `ProviderRepo`.
A provider profile is a plain resource row managed by the existing
`ResourceService` (CRUD + audit + sync come for free).

## On-disk / sync layout

No new directories. Provider profiles land in the existing sync workspace:

```
~/.coffer/sync/
  resources/
    provider/
      <name>.yaml      # one deterministic YAML per profile (no secret)
  credentials/
    provider/
      <name>/
        key.enc        # Fernet ciphertext of the raw API key
```

No new `~/.coffer/` subdirectory for providers (unlike skills which have a
master content store). The only on-disk side-effects are the native config
files written by projection (`~/.claude/settings.json`, `~/.codex/config.toml`)
and their `.bak` backups.

## Constraints summary

- `ProviderConfig` MUST NOT include the raw secret at any time.
- Domain projection functions (`apply_anthropic_settings`, `apply_codex_provider`)
  MUST be pure (no I/O); they return the new native-config TEXT.
- Key resolution MUST NOT log the decrypted value.
- The per-wire single-active invariant is enforced via sequential
  `ResourceService.update_config` calls serialised by the single-process daemon.
- All HTTP routes are loopback-only, gated by `X-Coffer-Token`.
