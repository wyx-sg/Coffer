# Data Model — 001 MCP Gateway

Entities, fields, relationships, and the SQLite schema for the MCP gateway.
ORM models follow these names exactly; OpenAPI schemas match the same field
names. Migrations are split across three Alembic revisions:

| Revision | File                                 | What it creates                                 |
| -------- | ------------------------------------ | ----------------------------------------------- |
| `0001`   | `20260520_0001_initial.py`           | `resources`, `audit_log`, `retention_policies`  |
| `0002`   | `20260521_0002_mcp_tables.py`        | `mcp_capability_preferences`, `mcp_invocations` |
| `0003`   | `20260522_0003_mcp_server_health.py` | `mcp_server_health`                             |

## Domain entities (`backend/coffer/domain/`)

### `ResourceRef` (`domain/resource.py`)

Frozen dataclass / Pydantic value object. The external identifier for a Resource.

| Field  | Type  | Notes                                                             |
| ------ | ----- | ----------------------------------------------------------------- |
| `kind` | `str` | matches a registered `Kind.name`, e.g. `"mcp_server"`             |
| `name` | `str` | kind-internally unique; matches `^[a-zA-Z0-9_.-]+$`; max 64 chars |

Behaviour:

- `__str__` → `f"{kind}:{name}"`
- `ResourceRef.parse("mcp_server:filesystem")` → `ResourceRef(kind="mcp_server", name="filesystem")`
- `parse` raises `ValueError` if input lacks a single `:` separator or either side is empty
- Equality and hashing implied by `frozen=True`

### `Resource` (`domain/resource.py`)

Plain Python dataclass; **not** a Pydantic model (domain stays pure).

| Field         | Type             | Notes                                                                      |
| ------------- | ---------------- | -------------------------------------------------------------------------- |
| `id`          | `int`            | DB surrogate; internal only, never serialised externally                   |
| `kind`        | `str`            | matches `Kind.name`                                                        |
| `name`        | `str`            | kind-internally unique                                                     |
| `description` | `str \| None`    | optional free text                                                         |
| `config`      | `dict[str, Any]` | kind-specific config, already validated against the kind's `config_schema` |
| `enabled`     | `bool`           | user-controlled enable/disable flag                                        |
| `created_at`  | `datetime`       | UTC, set on insert, never updated                                          |
| `updated_at`  | `datetime`       | UTC, updated on every mutation                                             |

Derived: `Resource.ref` returns `ResourceRef(self.kind, self.name)`.

### `Kind` (`domain/resource.py`)

Frozen dataclass. Pure descriptor of a resource kind. Domain only — does not
hold references to routers, services, or any framework-level adapters.

| Field           | Type                                    | Notes                                              |
| --------------- | --------------------------------------- | -------------------------------------------------- |
| `name`          | `str`                                   | unique within process, e.g. `"mcp_server"`         |
| `display_name`  | `str`                                   | UI label                                           |
| `config_schema` | `type[pydantic.BaseModel]`              | Pydantic schema used to validate `Resource.config` |
| `on_delete`     | `Callable[[ResourceRef], None] \| None` | optional sync cleanup hook; raise to abort delete  |

### `AuditEntry` (`domain/audit.py`)

Plain dataclass.

| Field           | Type             | Notes                                                  |
| --------------- | ---------------- | ------------------------------------------------------ |
| `id`            | `int \| None`    | DB surrogate, `None` before insert                     |
| `timestamp`     | `datetime`       | UTC, default `utcnow()`                                |
| `event_type`    | `str`            | one of the enumerated `AuditEventType` strings (below) |
| `resource_kind` | `str \| None`    | nullable; daemon-lifecycle events have no resource     |
| `resource_name` | `str \| None`    | nullable; daemon-lifecycle events have no resource     |
| `actor`         | `str`            | `"cli" \| "api" \| "ui" \| "system"`                   |
| `details`       | `dict[str, Any]` | JSON-serialisable payload                              |

### `AuditEventType` (`domain/audit.py`)

String-valued enum (use `StrEnum`):

| Value                     | When emitted                                               |
| ------------------------- | ---------------------------------------------------------- |
| `"resource_created"`      | After `ResourceService.register`                           |
| `"resource_updated"`      | After config or description change                         |
| `"resource_enabled"`      | After `set_enabled(True)` when state flipped               |
| `"resource_disabled"`     | After `set_enabled(False)` when state flipped              |
| `"resource_deleted"`      | After `delete` (includes pre-delete snapshot in `details`) |
| `"capability_first_seen"` | When discovery sees a capability for the first time        |
| `"capability_enabled"`    | When a user enables a capability that was disabled         |
| `"capability_disabled"`   | When a user disables a capability                          |
| `"daemon_started"`        | At daemon startup post-ready                               |
| `"daemon_stopped"`        | At daemon graceful shutdown                                |
| `"token_rotated"`         | After `POST /api/v1/daemon/rotate-token`                   |
| `"retention_updated"`     | When a retention policy is changed                         |
| `"backup_created"`        | After `POST /api/v1/daemon/backup`                         |
| `"keychain_set"`          | After `POST /api/v1/keychain` stores a secret              |
| `"keychain_read"`         | After `GET /api/v1/keychain/{ref}` reads a secret          |
| `"keychain_deleted"`      | After `DELETE /api/v1/keychain/{ref}` removes a secret     |

### `RetentionPolicy` (`domain/retention.py`)

Plain dataclass.

| Field              | Type               | Notes                                             |
| ------------------ | ------------------ | ------------------------------------------------- |
| `table_name`       | `str`              | PK; must match a registered `PrunableTable.name`  |
| `retention_days`   | `int \| None`      | `None` = keep forever; `>0` = days; `0` forbidden |
| `last_pruned_at`   | `datetime \| None` | last successful prune                             |
| `last_pruned_rows` | `int`              | rows deleted in last prune                        |
| `updated_at`       | `datetime`         | last policy mutation                              |

### `PrunableTable` (`infrastructure/persistence/retention.py`)

This is the **registry entry** used at composition root — declared here for
completeness even though the type lives in `infrastructure/` (it parameterises
SQL execution).

| Field                    | Type          | Notes                                                                          |
| ------------------------ | ------------- | ------------------------------------------------------------------------------ |
| `name`                   | `str`         | DB table name; must appear in the SQL allowlist set                            |
| `timestamp_column`       | `str`         | column name to compare against the cutoff; must appear in the column allowlist |
| `default_retention_days` | `int \| None` | seeded into `retention_policies` on first daemon boot                          |
| `display_name`           | `str`         | UI label                                                                       |
| `description`            | `str`         | UI tooltip                                                                     |

## MCP kind value objects (`backend/coffer/domain/mcp/`)

### `StdioTransport` (`domain/mcp/server_config.py`)

Pydantic `BaseModel`. Discriminator value: `"stdio"`.

| Field             | Type               | Notes                                                                                    |
| ----------------- | ------------------ | ---------------------------------------------------------------------------------------- |
| `type`            | `Literal["stdio"]` | discriminator                                                                            |
| `command`         | `str`              | executable, e.g. `"npx"`                                                                 |
| `args`            | `list[str]`        | default `[]`                                                                             |
| `env`             | `dict[str, str]`   | static env, never contains secrets; rejected if a value looks like a token (regex check) |
| `credential_refs` | `dict[str, str]`   | maps `env_var_name → keychain_ref_key`; resolved at spawn                                |
| `cwd`             | `str \| None`      | optional working directory                                                               |

### `HttpTransport` (`domain/mcp/server_config.py`)

Pydantic `BaseModel`. Discriminator value: `"http"`.

| Field             | Type               | Notes                                      |
| ----------------- | ------------------ | ------------------------------------------ |
| `type`            | `Literal["http"]`  | discriminator                              |
| `url`             | `pydantic.HttpUrl` | upstream MCP HTTP/SSE endpoint             |
| `headers`         | `dict[str, str]`   | static headers; same secret regex as `env` |
| `credential_refs` | `dict[str, str]`   | maps `header_name → keychain_ref_key`      |

### `MCPServerConfig` (`domain/mcp/server_config.py`)

Pydantic `BaseModel` — this is what `Resource.config` holds for an `mcp_server`.

| Field                          | Type                                                                      | Notes                                                                 |
| ------------------------------ | ------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `transport`                    | `Annotated[StdioTransport \| HttpTransport, Field(discriminator="type")]` | tagged union                                                          |
| `auto_enable_new_capabilities` | `bool`                                                                    | default `True`                                                        |
| `spawn_timeout_seconds`        | `int`                                                                     | default `30`; range `5–120`                                           |
| `request_timeout_seconds`      | `int`                                                                     | default `120`; range `5–1800`; reset on progress                      |
| `idle_timeout_seconds`         | `int`                                                                     | default `600`; range `60–86400`; subprocess GC after this idle period |

### `MCPTool` / `MCPResource` / `MCPPrompt` (`domain/mcp/capability.py`)

Pydantic `BaseModel`s. Live representations returned by upstream queries; never
persisted (per [ADR-004](../../docs/decisions/ADR-004-capability-state-model.md)).

`MCPTool`:
| Field | Type |
|---|---|
| `name` | `str` (original, no prefix) |
| `description` | `str \| None` |
| `input_schema` | `dict[str, Any]` (JSON schema) |

`MCPResource`:
| Field | Type |
|---|---|
| `uri` | `str` (original) |
| `name` | `str \| None` |
| `description` | `str \| None` |
| `mime_type` | `str \| None` |

`MCPPrompt`:
| Field | Type |
|---|---|
| `name` | `str` (original) |
| `description` | `str \| None` |
| `arguments` | `list[MCPPromptArgument]` |

### `MCPCapabilityPreference` (`domain/mcp/capability.py`)

| Field             | Type                                    | Notes                                                       |
| ----------------- | --------------------------------------- | ----------------------------------------------------------- |
| `id`              | `int \| None`                           | DB surrogate                                                |
| `resource_id`     | `int`                                   | FK to `resources.id`                                        |
| `capability_type` | `Literal["tool", "resource", "prompt"]` |                                                             |
| `capability_key`  | `str`                                   | original (unprefixed) name; for resources, the original URI |
| `enabled`         | `bool`                                  | default depends on server's `auto_enable_new_capabilities`  |
| `first_seen_at`   | `datetime`                              |                                                             |
| `last_seen_at`    | `datetime`                              | updated every successful discovery                          |

### `MCPInvocation` (`domain/mcp/capability.py`)

| Field             | Type                                          | Notes                           |
| ----------------- | --------------------------------------------- | ------------------------------- |
| `id`              | `int \| None`                                 | DB surrogate                    |
| `timestamp`       | `datetime`                                    |                                 |
| `resource_name`   | `str`                                         | MCP server name                 |
| `capability_type` | `Literal["tool", "resource", "prompt"]`       |                                 |
| `capability_key`  | `str`                                         | original (unprefixed) name      |
| `duration_ms`     | `int`                                         | wall-clock milliseconds         |
| `status`          | `Literal["ok", "error", "timeout", "denied"]` |                                 |
| `error_message`   | `str \| None`                                 | populated when `status != "ok"` |
| `session_id`      | `str \| None`                                 | per-session correlation         |

**Never store args or results** — schema cannot hold them.

## SQLite schema (across three Alembic revisions)

Tables are created across three migrations; the schema below represents the
combined result after all three revisions are applied.

```sql
-- Resources: kind-agnostic core
CREATE TABLE resources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT      NOT NULL,
    name          TEXT      NOT NULL,
    description   TEXT,
    config_json   TEXT      NOT NULL,                       -- validated JSON
    enabled       BOOLEAN   NOT NULL DEFAULT 1,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (kind, name)
);
CREATE INDEX idx_resources_kind_enabled ON resources(kind, enabled);

-- Audit log: kind-agnostic
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type      TEXT      NOT NULL,
    resource_kind   TEXT,                                   -- nullable
    resource_name   TEXT,
    actor           TEXT      NOT NULL,
    details_json    TEXT                                    -- nullable JSON payload
);
CREATE INDEX idx_audit_resource  ON audit_log(resource_kind, resource_name, timestamp DESC);
CREATE INDEX idx_audit_time      ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_eventtype ON audit_log(event_type, timestamp DESC);

-- Retention policy: kind-agnostic
CREATE TABLE retention_policies (
    table_name        TEXT PRIMARY KEY,
    retention_days    INTEGER,                              -- NULL = forever; >0 = days
    last_pruned_at    TIMESTAMP,
    last_pruned_rows  INTEGER NOT NULL DEFAULT 0,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (retention_days IS NULL OR retention_days > 0)
);

-- MCP-specific: user's capability preferences
CREATE TABLE mcp_capability_preferences (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_id      INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    capability_type  TEXT    NOT NULL,                      -- 'tool' | 'resource' | 'prompt'
    capability_key   TEXT    NOT NULL,
    enabled          BOOLEAN NOT NULL DEFAULT 1,
    first_seen_at    TIMESTAMP NOT NULL,
    last_seen_at     TIMESTAMP NOT NULL,
    UNIQUE (resource_id, capability_type, capability_key)
);
CREATE INDEX idx_prefs_resource ON mcp_capability_preferences(resource_id, capability_type, enabled);

-- MCP-specific: invocation log
CREATE TABLE mcp_invocations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resource_name    TEXT      NOT NULL,
    capability_type  TEXT      NOT NULL,
    capability_key   TEXT      NOT NULL,
    duration_ms      INTEGER   NOT NULL,
    status           TEXT      NOT NULL,                    -- 'ok' | 'error' | 'timeout' | 'denied'
    error_message    TEXT,
    session_id       TEXT
);
CREATE INDEX idx_invocations_resource ON mcp_invocations(resource_name, timestamp DESC);
CREATE INDEX idx_invocations_time     ON mcp_invocations(timestamp DESC);
CREATE INDEX idx_invocations_session  ON mcp_invocations(session_id, timestamp);

-- MCP-specific: persisted upstream health (revision 0003)
CREATE TABLE mcp_server_health (
    resource_name  TEXT      PRIMARY KEY,
    status         TEXT      NOT NULL,                    -- 'healthy' | 'failing' | 'unknown'
    checked_at     TIMESTAMP NOT NULL
);
```

## SQLAlchemy mapping (summary)

ORM models live under `backend/coffer/infrastructure/persistence/models.py`
(kind-agnostic) and `backend/coffer/infrastructure/mcp/persistence.py`
(MCP-specific), all registered against the same `Base.metadata`:

| ORM class                      | Table                        | Lives in                               |
| ------------------------------ | ---------------------------- | -------------------------------------- |
| `ResourceModel`                | `resources`                  | `infrastructure/persistence/models.py` |
| `AuditLogModel`                | `audit_log`                  | `infrastructure/persistence/models.py` |
| `RetentionPolicyModel`         | `retention_policies`         | `infrastructure/persistence/models.py` |
| `MCPCapabilityPreferenceModel` | `mcp_capability_preferences` | `infrastructure/mcp/persistence.py`    |
| `MCPInvocationModel`           | `mcp_invocations`            | `infrastructure/mcp/persistence.py`    |
| `McpServerHealthModel`         | `mcp_server_health`          | `infrastructure/mcp/persistence.py`    |

Each ORM model provides:

- `to_domain() -> <DomainEntity>` for conversion outward
- A module-level `from_domain(entity) -> <Model>` helper for inward conversion

## Cascade and integrity rules

| Action                             | Effect                                                                                                                           |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `DELETE FROM resources WHERE id=?` | cascades to `mcp_capability_preferences` (via FK). Does **not** cascade to `audit_log` or `mcp_invocations` (history preserved). |
| `UPDATE resources SET kind=?`      | forbidden — application layer never updates `kind`.                                                                              |
| `UPDATE resources SET name=?`      | forbidden — rename = delete + register.                                                                                          |
| `DELETE FROM retention_policies`   | forbidden — policies are upserted at startup, never deleted.                                                                     |

## Default retention policy seed (run on first daemon startup)

These defaults are seeded at the **composition root** (in `surfaces/http/app.py`,
when `RetentionService.initialize_defaults()` is invoked at daemon startup) —
**not** in Alembic migrations. Migrations create the `retention_policies` table
but leave it empty; the daemon upserts the per-table defaults at boot so that
new prunable tables introduced by later specs can register their own defaults
without requiring a new migration.

```python
defaults = [
    ("audit_log",         365),
    ("mcp_invocations",    30),
]
for table_name, days in defaults:
    if not exists(table_name):
        upsert(table_name=table_name, retention_days=days, updated_at=utcnow())
```

## API authentication

Every route under `/api/v1/*` requires the `X-Coffer-Token` header. The only
intentional exception is:

| Endpoint                    | Why unauthenticated                                                                                                                                                                                                                                                      |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GET /api/v1/daemon/status` | Used by the CLI and the `coffer-mcp-shim` as a cheap readiness probe before any token has been read from `~/.coffer/daemon.json`. Returns only lifecycle phase, version, port, started-at, and an aggregate upstream summary — no secrets, no per-resource details, no audit data. |

All mutating endpoints (including `/daemon/backup`, `/daemon/rotate-token`,
`/daemon/shutdown`) require the token. The `/mcp` JSON-RPC surface also
requires the token. Clients SHOULD set the optional `X-Coffer-Actor` header
(`cli` | `api` | `ui` | `system`) so audit entries carry the originating
surface; absent header defaults to `"api"`.

## Invariants enforced by importlinter

These re-state existing `tool.importlinter.contracts` in `backend/pyproject.toml`,
plus two contracts to be added (`Contract 5`, `Contract 6`) as part of this
spec's setup phase:

| Contract | Subject                                                                                                                                                                                                                                                                                                   |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1        | `surfaces → application → domain` layered direction                                                                                                                                                                                                                                                       |
| 2        | `infrastructure` does not import `surfaces`                                                                                                                                                                                                                                                               |
| 3        | `domain` is pure (no infra/surfaces/sdks)                                                                                                                                                                                                                                                                 |
| 4        | `keyring` confined to infrastructure                                                                                                                                                                                                                                                                      |
| **5**    | cross-kind imports forbidden: `coffer.{domain,application,infrastructure,surfaces}.mcp.*` does not import `coffer.{domain,application,infrastructure,surfaces}.<other_kind>.*` (vacuously true with one kind, but the contract is in place from day one so it bites the first time the second kind lands) |
| **6**    | kind-agnostic core does not import kind-specific code: `coffer.application.resource_service` does not import `coffer.domain.mcp` or `coffer.application.mcp`                                                                                                                                              |

Both new contracts are added in Task `T-0010` (see tasks.md).
