# Data Model — MCP Gateway

Entities, fields, relationships, and where each is stored for the
`mcp_server` kind. OpenAPI schemas match the same field names.

The kind-agnostic half — `Resource` (its immutable `uid` and its mutable `name`
label), `Kind`, `Scope`, `AuditEntry`, `RetentionPolicy`, `PrunableTable`, the
resource file, reach, the audit log and the retention policies — is modelled by
spec [resource-framework](../resource-framework/data-model.md); the storage
classes and state documents by spec vault-storage. This document covers only
what the MCP kind adds on top; ciphertext belongs to spec secret.

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
| `secret_ref_extractor` | the transport's `secret_refs`, so refs are probed before any write and released after a delete |
| `audit_redactor`           | an audit-safe copy of a transport config                                                     |
| `on_delete`                | tears down any running upstream for that server before its file goes                         |
| `on_rename`                | releases every live connection held under the name being left behind, before the file changes. A supervisor keys its entries — and each one's upstream subprocess — on the server's NAME, because `<server>__<tool>` is the vocabulary the downstream client speaks; without this the old entry becomes unreachable and the next call under the new name starts a second subprocess. It is reachable only because rename became available to every kind ([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)) |

## MCP kind value objects (`backend/coffer/domain/mcp/`)

### `StdioTransport` (`domain/mcp/server_config.py`)

Pydantic `BaseModel`. Discriminator value: `"stdio"`.

| Field             | Type               | Notes                                                                                        |
| ----------------- | ------------------ | -------------------------------------------------------------------------------------------- |
| `type`            | `Literal["stdio"]` | discriminator                                                                                |
| `command`         | `str`              | executable, e.g. `"npx"`                                                                     |
| `args`            | `list[str]`        | default `[]`                                                                                 |
| `env`             | `dict[str, str]`   | static env, never contains secrets; rejected if a value looks like a token (regex check)     |
| `secret_refs` | `dict[str, str]`   | maps `env_var_name → ref` into the encrypted secret store; resolved (decrypted) at spawn |
| `cwd`             | `str \| None`      | optional working directory                                                                   |

### `HttpTransport` (`domain/mcp/server_config.py`)

Pydantic `BaseModel`. Discriminator value: `"http"`.

| Field             | Type               | Notes                                                        |
| ----------------- | ------------------ | ------------------------------------------------------------ |
| `type`            | `Literal["http"]`  | discriminator                                                |
| `url`             | `pydantic.HttpUrl` | upstream MCP HTTP/SSE endpoint                               |
| `headers`         | `dict[str, str]`   | static headers; same secret regex as `env`                   |
| `secret_refs` | `dict[str, str]`   | maps `header_name → ref` into the encrypted secret store |

### `HttpApiTransport` (`domain/mcp/http_api.py`)

Pydantic `BaseModel`. Discriminator value: `"http_api"`. A **custom-tool
group**: the gateway answers `tools/list` from `tools` and makes each tool's
HTTP request itself (spec "Serve an HTTP API as a group of custom tools").

| Field             | Type                     | Notes                                                                                   |
| ----------------- | ------------------------ | --------------------------------------------------------------------------------------- |
| `type`            | `Literal["http_api"]`    | discriminator                                                                           |
| `base_url`        | `pydantic.HttpUrl`       | `http`/`https`, no query or fragment; each tool's path is appended                      |
| `headers`         | `dict[str, str]`         | static group headers; no `{argument}` hole; same secret regex as `env`                  |
| `auth_header`     | `str \| None`            | the header the secret goes in, e.g. `Authorization`                                     |
| `auth_prefix`     | `str`                    | prepended to the secret's value, e.g. `Bearer `                                         |
| `secret_refs` | `dict[str, str]`         | at most `{auth_header: ref}`; the API binds a Secrets-page name as `secret/<name>`      |
| `timeout_seconds` | `int`                    | default `30`; range `1–300`; per request                                                |
| `source`          | `OpenApiSource \| None`  | where an import came from: `kind` (`url`/`file`), `location`, `title`, `version`, `fetched_at`, `skipped` operation keys |
| `tools`           | `list[HttpApiTool]`      | unique names                                                                            |

`HttpApiTool`:

| Field           | Type                    | Notes                                                                        |
| --------------- | ----------------------- | ---------------------------------------------------------------------------- |
| `name`          | `str`                   | `^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$`, no `__`; agents see `<group>__<name>`   |
| `description`   | `str`                   | what the agent reads to decide                                               |
| `method`        | `GET\|POST\|PUT\|PATCH\|DELETE` |                                                                  |
| `path`          | `str`                   | relative path template; `{argument}` holes in the path or the query          |
| `headers`       | `dict[str, str]`        | may hold holes                                                               |
| `body_template` | `str \| None`           | JSON text with holes                                                         |
| `input_schema`  | `dict[str, Any]`        | JSON Schema object; every hole must be a declared property                   |
| `enabled`       | `bool`                  | the tool's switch — travels with the config, like capability toggles         |
| `changes_data`  | `bool \| None`          | `None` follows the method (on for all but GET); drives the MCP annotations   |
| `operation`     | `str \| None`           | `"<METHOD> <path>"` of the imported operation, for re-import                 |

A tool's **reach override** is not in the config: reach is machine-local, so it
is `local/tool-reach.json` (below).

### `MCPServerConfig` (`domain/mcp/server_config.py`)

Pydantic `BaseModel` — this is what `Resource.config` holds for an `mcp_server`.

| Field                     | Type                                                                      | Notes                                                                 |
| ------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `transport`               | `Annotated[StdioTransport \| HttpTransport \| HttpApiTransport, Field(discriminator="type")]` | tagged union                                             |
| `spawn_timeout_seconds`   | `int`                                                                     | default `30`; range `5–120`                                           |
| `request_timeout_seconds` | `int`                                                                     | default `120`; range `5–1800`; reset on progress                      |

Both timeouts are editable in the web UI's edit-server dialog, not only
over the API. Before they had a UI every registered server ran on the defaults
regardless of its upstream — and measured latency across one vault's servers
spanned three orders of magnitude (9ms to 10.9s average), with the slowest
routinely exceeding 60s against a 120s default. A timeout error names the
server and the elapsed limit, so an agent waiting one out can tell a slow
upstream from a broken gateway.

### `MCPTool` / `MCPResource` / `MCPPrompt` (`domain/mcp/capability.py`)

Pydantic `BaseModel`s. Live representations returned by upstream queries; never
persisted (per [Capability State Model](../../../docs/decisions/capability-state-model.md)).

`MCPTool`:
| Field | Type |
|---|---|
| `name` | `str` (original, no prefix) |
| `description` | `str \| None` |
| `input_schema` | `dict[str, Any]` (JSON schema) |
| `annotations` | `dict[str, Any] \| None` (the upstream's MCP annotations, wire spelling; passed to the agent) |

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

One capability's switch with when this machine saw it: the switch is read
from the server's `state/mcp-preferences/` document, the times from
`derived.db`.

| Field             | Type                                    | Notes                                                       |
| ----------------- | --------------------------------------- | ----------------------------------------------------------- |
| `resource_uid`    | `str`                                   | the server's uid                                            |
| `capability_type` | `Literal["tool", "resource", "prompt"]` |                                                             |
| `capability_key`  | `str`                                   | original (unprefixed) name; for resources, the original URI |
| `enabled`         | `bool`                                  | on unless the key is listed under `disabled` in the document |
| `first_seen_at`   | `datetime`                              | the epoch for a capability this machine has never seen      |
| `last_seen_at`    | `datetime`                              | updated every successful discovery                          |

### `MCPInvocation` (`domain/mcp/capability.py`)

| Field             | Type                                          | Notes                           |
| ----------------- | --------------------------------------------- | ------------------------------- |
| `id`              | `int \| None`                                 | `runs.db` row id                |
| `timestamp`       | `datetime`                                    |                                 |
| `resource_uid`    | `str`                                         | the MCP server's uid, or one of two reserved non-uid values — see below |
| `capability_type` | `Literal["tool", "resource", "prompt"]`       |                                 |
| `capability_key`  | `str`                                         | original (unprefixed) name      |
| `duration_ms`     | `int`                                         | wall-clock milliseconds         |
| `status`          | `Literal["ok", "error", "timeout", "denied"]` |                                 |
| `error_message`   | `str \| None`                                 | populated when `status != "ok"` |
| `session_id`      | `str \| None`                                 | per-session correlation         |
| `agent_uid`       | `str \| None`                                 | the calling agent's uid, when the session names one |
| `trace_id`        | `str \| None`                                 | the `/mcp` request's trace id; joins the audit rows and daemon log lines the call caused (0137) |

Two reserved values appear in `resource_uid` and are deliberately not uids — a
real uid is a 32-character `uuid4().hex`, and a name may not contain `:`, so
neither can collide with one (`domain/mcp/capability.py`):

| Value              | Means                                                                                                                                                                                                                                                           |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `coffer`           | one of Coffer's own `coffer__*` builtin tools. Builtins share this log so retention and the activity surfaces work uniformly, but no `mcp_server` resource stands behind them and there is no uid to record.                                                          |
| `deleted:<name>`   | a server already deleted when migration 0097 re-keyed the log. Its identity was never recorded and cannot be recovered, so the label it did carry survives behind a marker that is visibly not an identity. The row joins to no resource, which is the truth about it. |

A row carrying either resolves to no resource, so the tiering counts leave it
out.

**Never store args or results** — schema cannot hold them.

## Storage

| What | Where | Class |
| ---- | ----- | ----- |
| the server itself | `vault/resources/mcp_server/<name>.json` (spec resource-framework) | vault |
| capability switches | `vault/state/mcp-preferences/<server name>.json` | vault |
| when each capability was first and last seen | `derived/derived.db` `mcp_capability_seen` | derived |
| the last health check | `derived/derived.db` `mcp_server_health` | derived |
| custom tools' reach overrides | `local/tool-reach.json` | local |
| the invocation log | `runs.db` `mcp_invocations` | runs |

In the one-time upgrade to the vault layout the rows of
`mcp_capability_preferences` were split into the switch documents and
`mcp_capability_seen`, `mcp_server_health` was copied into `derived.db`,
`mcp_tool_reach` became `local/tool-reach.json`, and revision 0136 dropped the
three tables.

### Capability switches — `state/mcp-preferences/<server name>.json`

Whether a person switched a capability off is theirs, and travels, so it is a
vault state document (spec vault-storage), one per server that has anything
switched off:

```json
{
  "server_uid": "3f2a9c0e8b1d4c6a9e7f0b2d4c6a8e0f",
  "format_version": 1,
  "disabled": { "tool": ["delete_repo"], "prompt": ["summarise"] }
}
```

| Key | Notes |
| --- | ----- |
| `server_uid` | the owner's uid — what the document is found by; the file name only follows the server's name |
| `format_version` | the state document's format (1) |
| `disabled` | `{capability_type: [capability_key, ...]}`, sorted; only switched-off capabilities are listed. A capability nobody touched is on, so a new upstream tool writes nothing into the vault |

A server with nothing switched off has no document: turning its last capability
back on removes the file. The document is deleted with its server in the same
commit (`MCPCapabilityPreferenceStore`, `infrastructure/mcp/persistence.py`).

### `derived/derived.db`

Observations this machine can make again: no Alembic lineage, created at open,
recreated when its `PRAGMA user_version` differs (spec vault-storage).

```sql
CREATE TABLE mcp_capability_seen (
    server_uid       VARCHAR   NOT NULL,
    capability_type  VARCHAR   NOT NULL,              -- 'tool' | 'resource' | 'prompt'
    capability_key   VARCHAR   NOT NULL,
    first_seen_at    TIMESTAMP NOT NULL,
    last_seen_at     TIMESTAMP NOT NULL,              -- updated on every successful discovery
    CONSTRAINT pk_mcp_capability_seen PRIMARY KEY (server_uid, capability_type, capability_key)
);

CREATE TABLE mcp_server_health (
    resource_uid   VARCHAR   PRIMARY KEY,             -- the server's uid, so a rename keeps its row
    status         VARCHAR   NOT NULL,                -- 'healthy' | 'failing'
    checked_at     TIMESTAMP NOT NULL
);
```

A capability switched off on another machine that this machine has never seen
reads with its seen-times at the epoch, and is left out of "current tools".

### Custom tools' reach — `local/tool-reach.json`

```json
{ "<group uid>": { "<tool name>": ["<agent uid>", "..."] } }
```

A custom tool may narrow its group's reach to some agents; like every reach it
is true of this machine only, so it is local state beside `local/reach.json`
and never in the group's vault file (`MCPToolReachStore`,
`infrastructure/mcp/tool_reach_repo.py`). A tool with no entry reaches wherever
its group does; an emptied group is removed. Entries go with their tool
(removed, renamed away, dropped by a re-import) and with their group.

### `runs.db` — `mcp_invocations`

```sql
CREATE TABLE mcp_invocations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TIMESTAMP NOT NULL,
    resource_uid     TEXT      NOT NULL,                    -- a resource uid, or 'coffer' / 'deleted:<name>'
    capability_type  TEXT      NOT NULL,
    capability_key   TEXT      NOT NULL,
    duration_ms      INTEGER   NOT NULL,
    status           TEXT      NOT NULL,                    -- 'ok' | 'error' | 'timeout' | 'denied'
    error_message    TEXT,
    session_id       TEXT,
    agent_uid        TEXT,                                  -- the calling agent's uid as its session reported it; NULL when none (0113)
    trace_id         TEXT                                   -- the /mcp request's trace id; NULL before 0137
);
CREATE INDEX idx_invocations_resource ON mcp_invocations(resource_uid, timestamp DESC);
CREATE INDEX idx_invocations_time     ON mcp_invocations(timestamp DESC);
CREATE INDEX idx_invocations_session  ON mcp_invocations(session_id, timestamp);
CREATE INDEX idx_invocations_agent    ON mcp_invocations(agent_uid, timestamp);
CREATE INDEX idx_invocations_trace    ON mcp_invocations(trace_id);
```

`MCPInvocationModel` (`infrastructure/mcp/invocation_writer.py`) is on the
shared `Base.metadata` of `runs.db`; `_inv_to_domain` / `_inv_to_model`
convert. The tiering counts resolve each row's uid to the server's current name
through the resource store (`name_of`), so a row whose uid names no resource —
a builtin, a deleted server — counts for nothing.

## Integrity rules

| Action | Effect |
| ------ | ------ |
| delete a server | its `state/mcp-preferences/` document goes in the same commit. Does **not** touch `mcp_invocations` — the invocation log outlives the server it describes, as the audit log does |
| switch a capability | adds or removes its key in the server's document (one commit); the seen-times are untouched, which is what makes a decision survive an upstream upgrade |
| `local/tool-reach.json` | never synced (spec vault-sync "Keep reach machine-local") |
| `mcp_server_health` | keyed by the server's uid, so a rename keeps the row it already has |

The kind-agnostic rules these sit under — what a rename does to the audit trail
(nothing: the identity does not move, so the history follows the resource),
why `kind` is never changed — are spec resource-framework's.

## Retention

`mcp_invocations` registers with spec resource-framework's prunable-table
registry, carrying a 30-day default that the daemon seeds at startup. The
policy, the periodic pass that reads it and the surfaces that change it are
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
