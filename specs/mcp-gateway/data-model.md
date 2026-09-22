# Data Model — MCP Gateway

Entities, fields, relationships, and the SQLite schema for the `mcp_server`
kind. ORM models follow these names exactly; OpenAPI schemas match the same
field names.

The kind-agnostic half — `Resource` (its immutable `uid`, its mutable `name`
label and the internal surrogate `id`), `Kind`, `Scope`,
`AuditEntry`, `RetentionPolicy`, `PrunableTable`, and the `resources`,
`audit_log` and `retention_policies` tables — is modelled by spec
[resource-framework](../resource-framework/data-model.md). This document covers
only what the MCP kind adds on top, and the `credentials` table in the same
database belongs to spec credentials.

This spec's own tables were created by two early Alembic revisions; the lineage
has grown well past them as later specs landed, so the head revision is whatever
the newest file under
`backend/coffer/infrastructure/persistence/migrations/versions/` declares rather
than a number written down here.

| Revision | File                                 | What it creates                                 |
| -------- | ------------------------------------ | ----------------------------------------------- |
| `0002`   | `20260521_0002_mcp_tables.py`        | `mcp_capability_preferences`, `mcp_invocations` |
| `0003`   | `20260522_0003_mcp_server_health.py` | `mcp_server_health`                             |

## What this kind contributes to the framework

`make_mcp_kind()` (`application/mcp/kind.py`) returns one frozen `Kind`
descriptor, which is the whole of this spec's plug into spec
resource-framework:

| Field on `Kind`            | What `mcp_server` supplies                                                                   |
| -------------------------- | -------------------------------------------------------------------------------------------- |
| `config_schema`            | `MCPServerConfig` (below)                                                                    |
| `generic_create_allowed`   | True — an MCP server is fully described by its config, so the kind-agnostic create may make one |
| `supports_scope`           | True — reach is enforced at the gateway's per-session listing                                 |
| `validate_name`            | reserves the `__` namespace separator, which the prefixing scheme depends on                  |
| `credential_ref_extractor` | the transport's `credential_refs`, so refs are probed before any write and released after a delete |
| `audit_redactor`           | an audit-safe copy of a transport config                                                     |
| `on_delete`                | tears down any running upstream for that server before its row goes                          |
| `on_rename`                | releases every live connection held under the name being left behind, before the row changes. A supervisor keys its entries — and each one's upstream subprocess — on the server's NAME, because `<server>__<tool>` is the vocabulary the downstream client speaks; without this the old entry becomes unreachable and the next call under the new name starts a second subprocess. It is reachable only because rename became available to every kind ([Resource Identity Is an Immutable `uid`](../../docs/decisions/resource-identity-is-an-immutable-uid.md)) |

## MCP kind value objects (`backend/coffer/domain/mcp/`)

### `StdioTransport` (`domain/mcp/server_config.py`)

Pydantic `BaseModel`. Discriminator value: `"stdio"`.

| Field             | Type               | Notes                                                                                        |
| ----------------- | ------------------ | -------------------------------------------------------------------------------------------- |
| `type`            | `Literal["stdio"]` | discriminator                                                                                |
| `command`         | `str`              | executable, e.g. `"npx"`                                                                     |
| `args`            | `list[str]`        | default `[]`                                                                                 |
| `env`             | `dict[str, str]`   | static env, never contains secrets; rejected if a value looks like a token (regex check)     |
| `credential_refs` | `dict[str, str]`   | maps `env_var_name → ref` into the encrypted credential store; resolved (decrypted) at spawn |
| `cwd`             | `str \| None`      | optional working directory                                                                   |

### `HttpTransport` (`domain/mcp/server_config.py`)

Pydantic `BaseModel`. Discriminator value: `"http"`.

| Field             | Type               | Notes                                                        |
| ----------------- | ------------------ | ------------------------------------------------------------ |
| `type`            | `Literal["http"]`  | discriminator                                                |
| `url`             | `pydantic.HttpUrl` | upstream MCP HTTP/SSE endpoint                               |
| `headers`         | `dict[str, str]`   | static headers; same secret regex as `env`                   |
| `credential_refs` | `dict[str, str]`   | maps `header_name → ref` into the encrypted credential store |

### `MCPServerConfig` (`domain/mcp/server_config.py`)

Pydantic `BaseModel` — this is what `Resource.config` holds for an `mcp_server`.

| Field                     | Type                                                                      | Notes                                                                 |
| ------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `transport`               | `Annotated[StdioTransport \| HttpTransport, Field(discriminator="type")]` | tagged union                                                          |
| `spawn_timeout_seconds`   | `int`                                                                     | default `30`; range `5–120`                                           |
| `request_timeout_seconds` | `int`                                                                     | default `120`; range `5–1800`; reset on progress                      |
| `idle_timeout_seconds`    | `int`                                                                     | default `600`; range `60–86400`; subprocess GC after this idle period |

All three timeouts are editable in the web UI's edit-server dialog, not only
over the API. Before they had a UI every registered server ran on the defaults
regardless of its upstream — and measured latency across one vault's servers
spanned three orders of magnitude (9ms to 10.9s average), with the slowest
routinely exceeding 60s against a 120s default. A timeout error names the
server and the elapsed limit, so an agent waiting one out can tell a slow
upstream from a broken gateway.

### `MCPTool` / `MCPResource` / `MCPPrompt` (`domain/mcp/capability.py`)

Pydantic `BaseModel`s. Live representations returned by upstream queries; never
persisted (per [Capability State Model](../../docs/decisions/capability-state-model.md)).

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
| `enabled`         | `bool`                                  | enabled by default when first discovered                    |
| `first_seen_at`   | `datetime`                              |                                                             |
| `last_seen_at`    | `datetime`                              | updated every successful discovery                          |

### `MCPInvocation` (`domain/mcp/capability.py`)

| Field             | Type                                          | Notes                           |
| ----------------- | --------------------------------------------- | ------------------------------- |
| `id`              | `int \| None`                                 | DB surrogate                    |
| `timestamp`       | `datetime`                                    |                                 |
| `resource_uid`    | `str`                                         | the MCP server's uid, or one of two reserved non-uid values — see below |
| `capability_type` | `Literal["tool", "resource", "prompt"]`       |                                 |
| `capability_key`  | `str`                                         | original (unprefixed) name      |
| `duration_ms`     | `int`                                         | wall-clock milliseconds         |
| `status`          | `Literal["ok", "error", "timeout", "denied"]` |                                 |
| `error_message`   | `str \| None`                                 | populated when `status != "ok"` |
| `session_id`      | `str \| None`                                 | per-session correlation         |

Two reserved values appear in `resource_uid` and are deliberately not uids — a
real uid is a 32-character `uuid4().hex`, and a name may not contain `:`, so
neither can collide with one (`domain/mcp/capability.py`):

| Value              | Means                                                                                                                                                                                                                                                           |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `coffer`           | one of Coffer's own `coffer__*` builtin tools. Builtins share this log so retention and the activity surfaces work uniformly, but no `mcp_server` row stands behind them and there is no uid to record.                                                          |
| `deleted:<name>`   | a server already deleted when migration 0097 re-keyed the log. Its identity was never recorded and cannot be recovered, so the label it did carry survives behind a marker that is visibly not an identity. The row joins to no resource, which is the truth about it. |

A row carrying either joins to nothing, which is what the tiering query's inner
join relies on.

**Never store args or results** — schema cannot hold them.

## SQLite schema

The DDL below is the shape these tables have today. The kind-agnostic
`resources`, `audit_log` and `retention_policies` tables they sit beside are in
spec resource-framework's data model.

```sql
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
    resource_uid     TEXT      NOT NULL,                    -- a resource uid, or 'coffer' / 'deleted:<name>'
    capability_type  TEXT      NOT NULL,
    capability_key   TEXT      NOT NULL,
    duration_ms      INTEGER   NOT NULL,
    status           TEXT      NOT NULL,                    -- 'ok' | 'error' | 'timeout' | 'denied'
    error_message    TEXT,
    session_id       TEXT
);
CREATE INDEX idx_invocations_resource ON mcp_invocations(resource_uid, timestamp DESC);
CREATE INDEX idx_invocations_time     ON mcp_invocations(timestamp DESC);
CREATE INDEX idx_invocations_session  ON mcp_invocations(session_id, timestamp);

-- MCP-specific: persisted upstream health (revision 0003; re-keyed by 0097)
CREATE TABLE mcp_server_health (
    resource_uid   TEXT      PRIMARY KEY,
    status         TEXT      NOT NULL,                    -- 'healthy' | 'failing' | 'unknown'
    checked_at     TIMESTAMP NOT NULL
);

```

## SQLAlchemy mapping (summary)

This kind's ORM models live under `backend/coffer/infrastructure/mcp/`,
registered against the same `Base.metadata` as every other spec's:

| ORM class                      | Table                        | Lives in                                  |
| ------------------------------ | ---------------------------- | ----------------------------------------- |
| `MCPCapabilityPreferenceModel` | `mcp_capability_preferences` | `infrastructure/mcp/persistence.py`       |
| `MCPInvocationModel`           | `mcp_invocations`            | `infrastructure/mcp/invocation_writer.py` |
| `McpServerHealthModel`         | `mcp_server_health`          | `infrastructure/mcp/health_repo.py`       |

Each ORM model provides:

- `to_domain() -> <DomainEntity>` for conversion outward
- A module-level `from_domain(entity) -> <Model>` helper for inward conversion

## Cascade and integrity rules

| Action                                    | Effect                                                                                                                                                               |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DELETE FROM resources WHERE id=?`        | cascades to `mcp_capability_preferences` (via FK). Does **not** cascade to `mcp_invocations` — the invocation log outlives the server it describes, as the audit log does. |
| `DELETE FROM mcp_capability_preferences`  | never done directly: a preference is flipped, not removed, which is what makes a decision survive an upstream upgrade (FR-008).                                       |
| `mcp_server_health`                       | keyed by the server's `uid` rather than by its name or its row id (migration 0097), so a rename keeps the row it already has. Keyed by name it left a permanent orphan nothing would overwrite, and the status page went blank for a server that had tested green a second earlier. |

The kind-agnostic rules these sit under — what a rename does to the audit trail
(nothing: the identity does not move, so the history follows the resource),
why `kind` is never updated, why a retention policy is never deleted — are spec
resource-framework's.

## Retention

`mcp_invocations` registers with spec resource-framework's prunable-table
registry, carrying a 30-day default that the daemon seeds at startup. The
policy row, the periodic pass that reads it and the surfaces that change it are
that spec's; all this one does is contribute the table, its timestamp column
and the default.

## API authentication

Every route in this spec's contract — and the `/mcp` JSON-RPC surface — requires
the `X-Coffer-Token` header. The token, where it comes from and which routes are
deliberately exempt from it are spec daemon's. Clients SHOULD set the optional
`X-Coffer-Actor` header (`cli` | `api` | `ui` | `system`) so audit entries carry
the originating surface; absent header defaults to `"api"`.

## Invariants enforced by importlinter

These re-state `tool.importlinter.contracts` in `backend/pyproject.toml`. The
first four are the layering rules every spec lives under; contract 5 is this
kind's own. The file now carries twenty contracts in total — the cross-kind
fence below is written once per kind as kinds land, so it reads as nine
near-identical contracts rather than the one generic rule its wording suggests:

| Contract | Subject                                                                                                                                                                                                                                                                                                   |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1        | `surfaces → application → domain` layered direction                                                                                                                                                                                                                                                       |
| 2        | `infrastructure` does not import `surfaces`                                                                                                                                                                                                                                                               |
| 3        | `domain` is pure (no infra/surfaces/sdks)                                                                                                                                                                                                                                                                 |
| 4        | `keyring` confined to infrastructure                                                                                                                                                                                                                                                                      |
| **5**    | cross-kind imports forbidden: `coffer.{domain,application,infrastructure,surfaces}.mcp.*` does not import another kind's package. Written from day one against one kind, so it bit the first time a second kind landed — and is now repeated per kind (`agent`, `skill`, `knowledge`, `channel`, `chat`, `provider`, `memory`, `sync`) |

Contract 6 — the kind-agnostic core importing no kind — is spec
resource-framework's, and the contracts beyond these are later specs' own
fences (engine confinement, the banned dropped engines, where the Claude Agent
SDK and LangGraph may be imported).
