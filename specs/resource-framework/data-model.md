# Data Model — Resource Framework

Entities, fields, relationships, and the SQLite schema for the kind-agnostic
resource model. ORM models follow these names exactly; the OpenAPI schemas in
[contracts/api.openapi.yaml](./contracts/api.openapi.yaml) match the same field
names. A kind's own tables are modelled by that kind's spec —
`mcp_capability_preferences` and `mcp_invocations` by spec mcp-gateway, the
`credentials` table by spec credentials, and so on for every other kind.

These three tables were created by the first Alembic revision
(`20260520_0001_initial.py`: `resources`, `audit_log`, `retention_policies`).
The lineage has grown well past it as later specs landed, so the head revision
is whatever the newest file under
`backend/coffer/infrastructure/persistence/migrations/versions/` declares rather
than a number written down here. Two later revisions add columns the DDL below
shows in place: `scope_json` on `resources` (migration `0046`) and
`resource_id` on `audit_log` (migration `0067`).

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
| `scope`       | `Scope \| None`  | framework-level per-agent activation scope ([Per-Agent Resource Scope](../../docs/decisions/per-agent-resource-scope.md)); `None` = unscoped (active for every agent). Interpreted via `domain/scope.py`; only kinds whose `Kind.supports_scope` is True may set it. Machine-local — it does not travel with the vault. |

Derived: `Resource.ref` returns `ResourceRef(self.kind, self.name)`.

### `Kind` (`domain/resource.py`)

Frozen dataclass. Pure descriptor of a resource kind, contributed by that
kind's own spec. Domain only — it holds no reference to a router, a service, or
any framework-level adapter.

| Field                       | Type                                                                       | Notes                                                                                                   |
| --------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `name`                      | `str`                                                                      | unique within process, e.g. `"mcp_server"`                                                              |
| `display_name`              | `str`                                                                      | UI label                                                                                                |
| `config_schema`             | `type[pydantic.BaseModel]`                                                 | Pydantic schema used to validate `Resource.config`                                                      |
| `generic_create_allowed`    | `bool`                                                                     | whether the kind-agnostic `POST /resources` may create this kind; False for kinds that own a creation invariant beyond config validation (a skill's master folder, an agent's on-disk detection) |
| `supports_scope`            | `bool`                                                                     | whether the kind takes a per-agent scope at all; False (the default) makes `update_scope` reject a non-null payload with 422. True for every kind but `agent` |
| **Pre-write validators**    |                                                                            | run BEFORE persistence; raising rejects the write                                                       |
| `validate_name`             | `Callable[[str], None] \| None`                                            | kind-specific name rule (`mcp_server` reserves the `__` namespace separator)                            |
| `validate_config`           | `Callable[[dict], None] \| None`                                           | semantic config validation at REGISTRATION only, beyond the schema's shape                              |
| `on_update_config`          | `Callable[[ResourceRef, dict, dict], Awaitable[None] \| None] \| None`     | pre-write hook for `update_config`, which knows WHICH resource is being edited                           |
| `validate_scope_for`        | `Callable[[Resource, Scope \| None], Awaitable[None] \| None] \| None`     | pre-write hook for `update_scope`; only `channel` supplies one                                           |
| `credential_ref_extractor`  | `Callable[[dict], dict[str, str]] \| None`                                 | `{logical_key: keychain_ref}` so the service can probe refs before any DB write                          |
| `audit_redactor`            | `Callable[[dict], dict] \| None`                                           | audit-safe copy of a config, so the core hardcodes no kind's secret fields                               |
| `default_scope`             | `Callable[[dict], Scope \| None] \| None`                                  | the scope a new row is created with, consulted once at register (`provider` pre-fills the wire's own default) |
| **Post-write reactions**    |                                                                            | run AFTER persistence + audit; cannot reject                                                            |
| `on_delete`                 | `Callable[[ResourceRef], Awaitable[None] \| None] \| None`                 | cleanup hook, awaited BEFORE the row is removed so it can still resolve it; a reaction, not a veto       |
| `on_scope_changed`          | `Callable[[ResourceRef], Awaitable[None] \| None] \| None`                 | keeps delivery/reclaim in step with a scope edit                                                        |
| `on_enabled_changed`        | `Callable[[ResourceRef], Awaitable[None] \| None] \| None`                 | the exact mirror, for a kind whose `enabled` flag has an on-disk consequence (`skill`)                   |

Surface artefacts (routers, Typer groups) are deliberately NOT carried here:
the composition root registers them through its own per-kind wiring modules, so
the domain layer never references a surface.

### `Scope` (`domain/scope.py`)

One allow-list. `None` on a `Resource` means unscoped — active for every agent;
`agents=[]` matches nothing, i.e. dormant. There is no machine axis: reach is
machine-local and is neither carried away by a converge round nor written over
by one (spec vault-sync, `## What does not sync`). An unknown property on the
wire is rejected rather than ignored, because dropping a withdrawn axis would
widen the restriction the request was written to make.

### `AuditEntry` (`domain/audit.py`)

Plain dataclass.

| Field           | Type             | Notes                                                  |
| --------------- | ---------------- | ------------------------------------------------------ |
| `id`            | `int \| None`    | DB surrogate, `None` before insert                     |
| `timestamp`     | `datetime`       | UTC, default `utcnow()`                                |
| `event_type`    | `str`            | one of the enumerated `AuditEventType` strings (below) |
| `resource_id`   | `int \| None`    | the resource's stable row id — what makes a trail survive a rename; `None` for an event naming no resource, and for rows written before the column existed |
| `resource_kind` | `str \| None`    | nullable; the LABEL the resource carried at the time    |
| `resource_name` | `str \| None`    | nullable; daemon-lifecycle events have no resource     |
| `actor`         | `str`            | `"cli" \| "api" \| "ui" \| "system"`                   |
| `details`       | `dict[str, Any]` | JSON-serialisable payload                              |

### `AuditEventType` (`domain/audit.py`)

String-valued enum (`StrEnum`). The rows this spec writes:

| Value                      | When emitted                                               |
| -------------------------- | ---------------------------------------------------------- |
| `"resource_created"`       | After `ResourceService.register`                           |
| `"resource_updated"`       | After config or description change                         |
| `"resource_enabled"`       | After `set_enabled(True)` when state flipped               |
| `"resource_disabled"`      | After `set_enabled(False)` when state flipped              |
| `"resource_deleted"`       | After `delete` (includes pre-delete snapshot in `details`)  |
| `"resource_renamed"`       | After a rename — identity changed, config did not          |
| `"resource_scope_updated"` | After `update_scope` persisted a new per-agent scope       |
| `"retention_updated"`      | When a retention policy is changed                         |

The enum is **shared**, which is the point of one audit log: spec mcp-gateway
contributes `capability_enabled` / `capability_disabled`, spec credentials
contributes `credential_set` / `credential_read` / `credential_deleted` /
`credential_migrated` / `master_key_relocated`, spec daemon contributes
`token_rotated`, and every other kind adds its own. A kind adding an event adds
a value here and a migration for the enum, not a table of its own.

### `RetentionPolicy` (`domain/retention.py`)

Plain dataclass.

| Field              | Type               | Notes                                             |
| ------------------ | ------------------ | ------------------------------------------------- |
| `table_name`       | `str`              | PK; must match a registered `PrunableTable.name`  |
| `retention_days`   | `int \| None`      | `None` = keep forever; `>0` = days; `0` forbidden |
| `last_pruned_at`   | `datetime \| None` | last successful prune                             |
| `last_pruned_rows` | `int`              | rows deleted in last prune                        |
| `updated_at`       | `datetime`         | last policy mutation                              |

### `PrunableTable` (`application/retention_registry.py`)

The **registry entry** used at the composition root. A spec that writes a log
contributes one of these; nothing else is prunable, and the prune SQL in
`infrastructure/persistence/retention_repo.py` accepts only a table and a
timestamp column that appear in its allowlists.

| Field                    | Type          | Notes                                                                          |
| ------------------------ | ------------- | ------------------------------------------------------------------------------ |
| `name`                   | `str`         | DB table name; must appear in the SQL allowlist set                            |
| `timestamp_column`       | `str`         | column name to compare against the cutoff; must appear in the column allowlist |
| `default_retention_days` | `int \| None` | seeded into `retention_policies` on first daemon boot                          |
| `display_name`           | `str`         | UI label                                                                       |
| `description`            | `str`         | UI tooltip                                                                     |

### `UpkeepRun` (`application/upkeep_runs.py`)

Frozen dataclass, held in an in-process registry keyed by `(kind, name)`. Not
persisted, and deliberately so: there is no queue, no row and no lease, so a
daemon restart ends any pass it was running and the registry comes back empty.
A claim that outlived the process holding it would wedge a target forever with
no runner left to release it.

| Field        | Type       | Notes                                          |
| ------------ | ---------- | ---------------------------------------------- |
| `kind`       | `str`      | the kind whose pass this is: `memory`, `knowledge` |
| `name`       | `str`      | the partition or collection being rewritten    |
| `started_at` | `datetime` | when this daemon started the pass              |

## SQLite schema

The DDL below is the shape these tables have today, columns added by later
revisions included.

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
    scope_json    TEXT,              -- per-agent scope; NULL = unscoped (migration 0046)
    UNIQUE (kind, name)
);
CREATE INDEX idx_resources_kind_enabled ON resources(kind, enabled);

-- Audit log: kind-agnostic
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type      TEXT      NOT NULL,
    resource_id     INTEGER,                                -- stable row id; survives a rename (migration 0067)
    resource_kind   TEXT,                                   -- nullable; the label carried at the time
    resource_name   TEXT,
    actor           TEXT      NOT NULL,
    details_json    TEXT                                    -- nullable JSON payload
);
CREATE INDEX idx_audit_resource    ON audit_log(resource_kind, resource_name, timestamp DESC);
CREATE INDEX idx_audit_resource_id ON audit_log(resource_id, timestamp DESC);
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
```

## SQLAlchemy mapping (summary)

ORM models live under `backend/coffer/infrastructure/persistence/models.py`,
registered against the shared `Base.metadata` alongside every kind's own:

| ORM class              | Table                | Lives in                               |
| ---------------------- | -------------------- | -------------------------------------- |
| `ResourceModel`        | `resources`          | `infrastructure/persistence/models.py` |
| `AuditLogModel`        | `audit_log`          | `infrastructure/persistence/models.py` |
| `RetentionPolicyModel` | `retention_policies` | `infrastructure/persistence/models.py` |

Each ORM model provides:

- `to_domain() -> <DomainEntity>` for conversion outward
- A module-level `from_domain(entity) -> <Model>` helper for inward conversion

## Cascade and integrity rules

| Action                             | Effect                                                                                                                                                                                                                                                                 |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DELETE FROM resources WHERE id=?` | cascades to whatever a kind owns by FK (spec mcp-gateway's `mcp_capability_preferences`, for one). Does **not** cascade to `audit_log` or to any kind's invocation log — history outlives the resource it describes.                                                     |
| `UPDATE resources SET kind=?`      | forbidden — the application layer never updates `kind`.                                                                                                                                                                                                                |
| `UPDATE resources SET name=?`      | allowed, through `ResourceService.rename` only — it moves the row and records `resource_renamed`. The audit trail needs no repointing: rows carry the resource's stable `resource_id`, so history follows the resource while each row keeps saying what it was called then. Only spec provider-switching exposes rename on a surface today; the service operation is the framework's. |
| `DELETE FROM retention_policies`   | forbidden — policies are upserted at startup, never deleted.                                                                                                                                                                                                           |

## Default retention policy seed (run on first daemon startup)

These defaults are seeded at the **composition root** (in `surfaces/http/app.py`,
when `RetentionService.initialize_defaults()` is invoked at daemon startup) —
**not** in Alembic migrations. Migrations create the `retention_policies` table
but leave it empty; the daemon upserts the per-table defaults at boot so that a
prunable table introduced by a later spec can register its own default without
requiring a new migration.

```python
defaults = [
    ("audit_log",         365),   # this spec's own
    ("mcp_invocations",    30),   # spec mcp-gateway's, registered through the registry
]
for table_name, days in defaults:
    if not exists(table_name):
        upsert(table_name=table_name, retention_days=days, updated_at=utcnow())
```

## API authentication

Every route in this spec's contract requires the `X-Coffer-Token` header. The
token, where it comes from and which routes are deliberately exempt from it are
spec daemon's. Clients SHOULD set the optional `X-Coffer-Actor` header
(`cli` | `api` | `ui` | `system`) so audit entries carry the originating
surface; an absent header defaults to `"api"`.

## Invariants enforced by importlinter

These re-state `tool.importlinter.contracts` in `backend/pyproject.toml`. The
first four are the layering rules every spec lives under; the sixth is this
spec's own fence:

| Contract | Subject                                                                                                                                               |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1        | `surfaces → application → domain` layered direction                                                                                                   |
| 2        | `infrastructure` does not import `surfaces`                                                                                                           |
| 3        | `domain` is pure (no infra/surfaces/sdks)                                                                                                             |
| 4        | `keyring` confined to infrastructure                                                                                                                  |
| **6**    | the kind-agnostic core does not import kind-specific code: `coffer.application.resource_service` does not import any kind's `domain` / `application` package — which is what makes the core testable against a `fake_kind` registered only for tests |

Contract 5 is the cross-kind fence, written once per kind by the kind that owns
it. The contracts beyond these are later specs' own.
