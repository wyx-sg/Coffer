# Data Model — Resource Framework

Entities, fields, relationships, and where each is stored for the
kind-agnostic resource model. The OpenAPI schemas in
[contracts/api.openapi.yaml](contracts/api.openapi.yaml) match the same field
names. A kind's own state is modelled by that kind's spec — the MCP capability
switches and `mcp_invocations` by spec mcp-gateway, the ciphertext files by
spec secret, and so on for every other kind. The storage classes, the
document encoding, `format_version` and the commit trailers every vault write
carries are spec vault-storage's ([data-model](../vault-storage/data-model.md)).

A resource is **a file**, not a row: one JSON document filed by its kind's
storage class (`FileResourceRepo`, `infrastructure/vault/resource_store.py`).
Its reach is machine-local JSON beside it, its revision counter a derived
index, and its audit trail rows in `runs.db` keyed by its uid. There is no
integer resource id: the uid inside the file is the identity. In the one-time
upgrade to the vault layout (`coffer migrate`) every `resources` row became a
resource file and its `enabled`/`scope_json` a record in `local/reach.json`;
Alembic revision 0136 re-keyed `audit_log` from `resource_id` to
`resource_uid` and dropped the table.

## Domain entities (`backend/coffer/domain/`)

### Identity (`domain/resource.py`)

There is no identifier value object. A resource is addressed by its `uid`, a
plain string, and the `<kind>:<name>` string form that `ResourceRef` used to
carry is **deleted** rather than demoted to a label — leaving it as "the label"
would have kept two spellings of identity in the codebase and an obvious place
for the next reader to reach for the wrong one
([Resource Identity Is an Immutable `uid`](../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).

`validate_resource_name(name)` is the framework's one name rule, raising
`InvalidResourceNameError`. It is applied by registration AND by rename, from a
single helper, because while rename lived in one kind's service the two had
already drifted apart.

`normalise_title(title)` is the title rule: surrounding whitespace is dropped,
an empty title becomes `None` (which is how a title is cleared), and one longer
than `TITLE_MAX_LEN` (80) raises `ValueError`, which the service reports as
`CONFIG_INVALID`.

### `Resource` (`domain/resource.py`)

Plain Python dataclass; **not** a Pydantic model (domain stays pure).

| Field         | Type             | Notes                                                                      |
| ------------- | ---------------- | -------------------------------------------------------------------------- |
| `uid`         | `str`            | **the identity**: `uuid4().hex`, minted once, never reused, the same value on every machine holding this resource. Stored inside the resource file (`uid` key), never derived from its path: every route, every cross-resource reference and every `runs.db` row that names a resource (`resource_uid`) address this. A file a person wrote without one is given one by a `daemon` commit; a second file claiming a uid another file already holds is refused and flagged |
| `kind`        | `str`            | matches `Kind.name`                                                        |
| `name`        | `str`            | a **label**, unique within its kind; mutable unless the kind declares it fixed (`Kind.name_fixed`) |
| `description` | `str \| None`    | optional free text                                                         |
| `config`      | `dict[str, Any]` | kind-specific config, already validated against the kind's `config_schema` |
| `enabled`     | `bool`           | user-controlled enable/disable flag. Reach, so machine-local: `local/reach.json`, never in the file; a resource with no record there is enabled |
| `created_at`  | `datetime`       | UTC, the file's `created_at` key, written at creation and never updated; a file without one reads as when this machine first saw its uid (`first_seen` in the uid index) |
| `updated_at`  | `datetime`       | UTC, when the file's bytes or this machine's reach for it last changed, from the derived uid index (`derived/index/resources.json`); not in the file |
| `title`       | `str \| None`    | optional display text, at most 80 characters, that surfaces show in place of `name`; `None` = none. Editable through `ResourceService.set_title` on a kind that carries one (`Kind.titled`); always `None` for `agent`, `mcp_server`, `skill` and `knowledge` (a collection is named by its folder); the file's `title` key, present only when set (spec resource-framework "Carry an optional editable title on the kinds that have one") |
| `rev`         | `int`            | monotonic revision: a derived per-uid counter in `derived/index/resources.json`, 1 when the uid is first seen, grown by one whenever the file's blob id or this machine's reach for it changes (a person's hand edit and a sync round's checkout included); every change emits an in-process `Changed(kind, uid, rev)` hint that brings the next reconcile pass forward (spec resource-framework "Carry a monotonic revision on every resource"). Not in the file or the API; deleting `derived/` restarts every counter at 1, which only the in-process dedupe of hints reads |
| `scope`       | `Scope \| None`  | framework-level per-agent activation scope ([Per-Agent Resource Scope](../../../docs/decisions/per-agent-resource-scope.md)); `None` = unscoped (active for every agent). Interpreted via `domain/scope.py`; only kinds whose `Kind.supports_scope` is True may set it. Machine-local: the `agents` of the resource's record in `local/reach.json`, never in the file. A resource with no record has its kind's `default_scope` |

There is no derived `ref`: a resource carries its `uid`, its `kind` and its
`name` as three plain fields, and nothing combines them into a fourth.

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
| `name_fixed`                | `bool`                                                                     | whether a registered row's name is fixed because it is quoted outside Coffer; `rename` refuses a changed name with `NAME_IMMUTABLE` (409) before any hook or write, and nothing is audited. True for `mcp_server` (its name prefixes every tool name an agent sees), `skill` (its name is the folder an agent loads it from) and `agent` (its name is its type's) |
| `name_fixed_resets`         | `str`                                                                      | for a `name_fixed` kind, what deleting and registering again resets, quoted in the refusal message      |
| `name_from_config`          | `Callable[[dict], str] \| None`                                            | the one name a row may carry, derived from its config; `register` refuses any other (422). `agent` derives it from its type (`claude_code` → `claude-code`) |
| `titled`                    | `bool`                                                                     | whether rows carry the optional `title`; False for `agent`, `mcp_server`, `skill` and `knowledge`, where a non-empty title is refused (422) on register and on `set_title` |
| `supports_scope`            | `bool`                                                                     | whether the kind takes a per-agent scope at all; False (the default) makes `update_scope` reject a non-null payload with 422. True for `mcp_server`, `skill`, `provider` and `channel`; False for `agent`, `knowledge` and `memory` |
| **Pre-write validators**    |                                                                            | run BEFORE persistence; raising rejects the write                                                       |
| `validate_name`             | `Callable[[str], None] \| None`                                            | kind-specific name rule (`mcp_server` reserves the `__` namespace separator)                            |
| `validate_new_name`         | `Callable[[str], None] \| None`                                            | rule for the name of a resource created on this machine, run by `register` only when it mints the uid — never on load, and never for a file arriving from another machine with its uid. `mcp_server` caps new names at 24 characters |
| `validate_config`           | `Callable[[dict], None] \| None`                                           | semantic config validation at REGISTRATION only, beyond the schema's shape                              |
| `on_update_config`          | `Callable[[Resource, dict], Awaitable[None] \| None] \| None`               | pre-write hook for `update_config`, handed the resource as it stands and the proposed config             |
| `on_rename`                 | `Callable[[Resource, str], Awaitable[None] \| None] \| None`                | pre-write hook for `rename`; where a kind whose name is also a directory moves it. Raising aborts the rename with nothing moved. `knowledge` and `memory` supply one; `skill` keeps a directory too but its name is fixed, so it never renames |
| `validate_scope_for`        | `Callable[[Resource, Scope \| None], Awaitable[None] \| None] \| None`     | pre-write hook for `update_scope`; only `channel` supplies one                                           |
| `secret_ref_extractor`  | `Callable[[dict], dict[str, str]] \| None`                                 | `{logical_key: keychain_ref}` so the service can probe refs before any write                             |
| `audit_redactor`            | `Callable[[dict], dict] \| None`                                           | audit-safe copy of a config, so the core hardcodes no kind's secret fields                               |
| `default_scope`             | `Callable[[dict], Scope \| None] \| None`                                  | the scope a new row is created with, consulted once at register (`provider` pre-fills the wire's own default) |
| `validate_delete`           | `Callable[[Resource], None] \| None`                                       | pre-write guard for `delete`: raising refuses the deletion before anything is torn down, on the kind's own DELETE and the kind-agnostic one alike (spec resource-framework "Let a kind refuse a deletion before anything is torn down"). Only `skill` supplies one, refusing its builtin skill with `RESOURCE_PROTECTED` |
| **Storage**                 |                                                                            | read by the resource store (`FileResourceRepo`) when it files a resource                                |
| `storage`                   | `StorageClass`                                                             | the class the kind's files are filed in: `vault` (default; `vault/resources/<kind>/`, committed, synced when a remote is set), `local` for `agent` (`local/resources/agent/`, never committed), `derived` for `memory` (`derived/resources/memory/`, rebuilt). The directory is the policy: nothing else decides whether a resource travels |
| `storage_row`               | `Callable[[dict], StorageClass] \| None`                                   | per-row refinement of `storage`, given the config at creation; `skill` supplies one so Coffer's own `coffer-guide` is filed under `derived/` |
| `exclusive_flags`           | `tuple[str, ...]`                                                          | config flags at most one resource of the kind may hold (`provider`'s `internal_default`); the vault validator refuses any commit — an API write, a hand edit, a sync merge — that would leave two |
| **Post-write reactions**    |                                                                            | run AFTER persistence + audit; cannot reject                                                            |
| `on_delete`                 | `Callable[[Resource], Awaitable[None] \| None] \| None`                    | cleanup hook, awaited BEFORE the file is removed so it can still resolve it; a reaction, not a veto       |
| `on_scope_changed`          | `Callable[[Resource], Awaitable[None] \| None] \| None`                    | keeps delivery/reclaim in step with a scope edit; handed the row AFTER the write                        |
| `on_enabled_changed`        | `Callable[[Resource], Awaitable[None] \| None] \| None`                    | the exact mirror, for a kind whose `enabled` flag has an on-disk consequence (`skill`)                   |

Surface artefacts (routers, Typer groups) are deliberately NOT carried here:
the composition root registers them through its own per-kind wiring modules, so
the domain layer never references a surface.

### `Scope` (`domain/scope.py`)

One allow-list. `None` on a `Resource` means unscoped — active for every agent;
`agents=[]` matches nothing, i.e. dormant. There is no machine axis: reach is
machine-local (`local/reach.json`), so no sync round carries it or writes over
it (spec vault-sync, "Keep reach machine-local"). An unknown property on the
wire is rejected rather than ignored, because dropping a withdrawn axis would
widen the restriction the request was written to make.

### `AuditEntry` (`domain/audit.py`)

Plain dataclass.

| Field           | Type             | Notes                                                  |
| --------------- | ---------------- | ------------------------------------------------------ |
| `id`            | `int \| None`    | `runs.db` row id, `None` before insert                 |
| `timestamp`     | `datetime`       | UTC, default `utcnow()`                                |
| `event_type`    | `str`            | one of the enumerated `AuditEventType` strings (below) |
| `resource_uid`  | `str \| None`    | the resource's uid — what makes a trail survive a rename; `None` for an event naming no resource, and for a row whose resource was already deleted when revision 0136 re-keyed the trail to uids |
| `resource_kind` | `str \| None`    | nullable; the LABEL the resource carried at the time    |
| `resource_name` | `str \| None`    | nullable; daemon-lifecycle events have no resource     |
| `actor`         | `str`            | free string: `"cli"`, `"api"` or `"ui"` from the `X-Coffer-Actor` header (`"api"` when it is absent), `"system"` for the daemon's own work, `"sync"` for a change applied from the sync remote, a named worker such as `"system:memory-aggregate-worker"` or `"system:memory-distil-worker"`, or a domain actor a kind names itself (`"user"`, `"channel"`, an agent's name, or `"agent"` for a knowledge write whose session reported no agent) |
| `details`       | `dict[str, Any]` | JSON-serialisable payload                              |

### `AuditEventType` (`domain/audit.py`)

String-valued enum (`StrEnum`). The rows this spec writes:

| Value                      | When emitted                                               |
| -------------------------- | ---------------------------------------------------------- |
| `"resource_created"`       | After `ResourceService.register`                           |
| `"resource_updated"`       | After a config, description or title change (a title change records `details.title.before`/`after`) |
| `"resource_enabled"`       | After `set_enabled(True)` when state flipped               |
| `"resource_disabled"`      | After `set_enabled(False)` when state flipped              |
| `"resource_deleted"`       | After `delete` (includes pre-delete snapshot in `details`)  |
| `"resource_renamed"`       | After a rename — identity changed, config did not          |
| `"resource_scope_updated"` | After `update_scope` persisted a new per-agent scope       |
| `"retention_updated"`      | When a retention policy is changed                         |
| `"vault_file_edited"`      | After a hand edit found on disk was committed as a `disk` write (actor `human`; `details` = `{path, version}`, one row per file) |
| `"vault_file_restored"`    | After a vault file or folder was restored to an earlier version (a new commit carrying `Coffer-Restored-From`) |
| `"attention_ignored"`      | When the user ignores an informational attention item on this machine |
| `"attention_unignored"`    | When the user stops ignoring one                           |

The enum is **shared**, which is the point of one audit log: spec mcp-gateway
contributes `capability_enabled` / `capability_disabled`, spec secret
contributes `secret_set` / `secret_read` / `secret_deleted` /
`secret_migrated` / `master_key_relocated`, spec daemon contributes
`token_rotated`, and every other kind adds its own. A kind adding an event adds
a value here and a migration for the enum, not a table of its own.

### `RetentionPolicy` (`domain/retention.py`)

Plain dataclass.

| Field              | Type               | Notes                                             |
| ------------------ | ------------------ | ------------------------------------------------- |
| `table_name`       | `str`              | the key in `local/retention.json`; must match a registered `PrunableTable.name` |
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
| `default_retention_days` | `int \| None` | seeded into `local/retention.json` at daemon boot where the table has no policy |
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

## Storage

### The resource file

A resource is one JSON document (2-space indent, key order kept, trailing
newline, unknown keys kept in place; spec vault-storage) at
`resources/<kind>/<name>.json` under its class's directory:

| Class   | Directory                            | Kinds                                                     | Written                                                               |
| ------- | ------------------------------------ | --------------------------------------------------------- | --------------------------------------------------------------------- |
| vault   | `~/.coffer/vault/resources/<kind>/`   | `mcp_server`, `skill`, `channel`, `provider`, `knowledge` | through the vault's one writer, one commit per operation; read at `HEAD` |
| local   | `~/.coffer/local/resources/<kind>/`   | `agent`                                                   | atomically, no history                                                |
| derived | `~/.coffer/derived/resources/<kind>/` | `memory`, and the builtin skill `coffer-guide`            | atomically, no history; rebuilt                                       |

```json
{
  "uid": "3f2a9c0e8b1d4c6a9e7f0b2d4c6a8e0f",
  "kind": "mcp_server",
  "format_version": 1,
  "name": "linear",
  "description": null,
  "config": { "transport": "stdio", "command": "${HOME}/bin/linear-mcp" },
  "created_at": "2026-09-30T08:00:00+00:00"
}
```

| Key              | Notes                                                                                                                                                        |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `uid`            | the identity (`uuid4().hex`; any opaque id of letters, digits, `-` and `_`, at most 64 characters, is kept). Absent only on a hand-made file, until the `daemon` commit that mints one |
| `kind`           | required; the `Kind.name`                                                                                                                                    |
| `format_version` | the resource document's format, 1 today; `format_compat` appears only on a file a newer build wrote additively                                             |
| `name`           | required; the label, unique within its kind across every class                                                                                              |
| `title`          | written only when set                                                                                                                                        |
| `description`    | always written, `null` when empty, so a person editing the file sees where it goes                                                                           |
| `config`         | required; the kind's config. A string under this machine's home is written as `${HOME}/...` and expanded on read; top-level keys the kind's schema does not declare are put back from the file on every write |
| `created_at`     | ISO time, written at creation                                                                                                                                |

`enabled`, `scope`, `rev` and `updated_at` are not in the file. The file name
only follows the name: nothing keys on the path, a person may move the file,
and a rename writes `<new name>.json` (or `<name>-<uid[:8]>.json` when that
name is taken by an unrelated file) and removes the old one in the same commit.

### Reach — `~/.coffer/local/reach.json`

```json
{ "<uid>": { "enabled": true, "agents": ["<agent uid>"], "projects": null } }
```

`agents: null` is unrestricted and `[]` dormant; `projects` is reserved and
always `null`. A resource with no record has `enabled: true` and its kind's
`default_scope`. `set_enabled` and `update_scope` write only this file and make
no commit.

### Revision index — `~/.coffer/derived/index/resources.json`

`{uid: {path, blob, reach, rev, updated_at, first_seen}}`: where the uid was
last found (`<class>/<path>`), the blob id of its bytes, a fingerprint of its
reach, the counter and the two times. A full read drops every uid it no longer
finds. Deleting the file is safe.

### Audit log — `runs.db`

```sql
CREATE TABLE audit_log (
    id              INTEGER PRIMARY KEY,
    timestamp       TIMESTAMP NOT NULL,
    event_type      VARCHAR   NOT NULL,
    resource_kind   VARCHAR,                -- the label carried at the time
    resource_name   VARCHAR,
    actor           VARCHAR   NOT NULL,
    details_json    TEXT,                   -- nullable JSON payload
    resource_uid    VARCHAR                 -- the resource's uid; survives a rename (0136)
);
CREATE INDEX idx_audit_resource     ON audit_log(resource_kind, resource_name, timestamp DESC);
CREATE INDEX idx_audit_time         ON audit_log(timestamp DESC);
CREATE INDEX idx_audit_eventtype    ON audit_log(event_type, timestamp DESC);
CREATE INDEX idx_audit_resource_uid ON audit_log(resource_uid, timestamp);
```

`AuditLogModel` (`infrastructure/persistence/models.py`) is on the shared
`Base.metadata` of `runs.db`'s one Alembic lineage.

### Retention policies — `~/.coffer/local/retention.json`

`{table_name: {retention_days, last_pruned_at, last_pruned_rows, updated_at}}`,
written atomically (`FileRetentionRepo`, `infrastructure/persistence/retention_repo.py`).
`retention_days` is `null` (forever) or a positive integer. What a policy
prunes is history, so the sweep stays SQL against `runs.db`, and it accepts
only a table and a timestamp column in the allowlist built from the registry.

## Integrity rules

| Action               | Effect |
| -------------------- | ------ |
| create               | refused (`ResourceAlreadyExists`) when the uid, or the kind + name, is already held by a resource file of any class. A vault resource is written expecting its path absent, in one commit |
| delete               | removes the file (one commit for a vault resource), its reach record and its index row; every state document that follows its owner (spec mcp-gateway's capability switches, spec channels' pairings) goes in the same commit. Does **not** touch `audit_log` or any kind's invocation log — history outlives the resource it describes |
| change `kind`        | never — the application layer never rewrites `kind` |
| change `name`        | through `ResourceService.rename` only (`PATCH /api/v1/resources/{uid}`): one commit moves the file and every following state document, and `resource_renamed` is recorded. Nothing else is repointed, because nothing else holds the name: cross-resource references and the audit trail hold the uid. A kind with an on-disk artifact named after the resource moves it in its `on_rename` hook |
| change `uid`         | never — minted once, kept inside the file wherever it moves |
| any structured write | read-modify-write under the vault lock against `HEAD`; a file whose bytes on disk differ from `HEAD` (an unsettled hand edit) is refused with `VAULT_FILE_STALE` (409) rather than overwritten |
| a hand edit          | committed as a `disk` write once it validates; an invalid one stays uncommitted and flagged, and `HEAD` stays in effect |

## Default retention policy seed (run on first daemon startup)

These defaults are seeded at the **composition root** (in `surfaces/http/app.py`,
when `RetentionService.initialize_defaults()` is invoked at daemon startup) into
`local/retention.json`, so a prunable table introduced by a later spec registers
its own default without any migration.

The seed is one entry per registered `PrunableTable`, at that table's
`default_retention_days`, inserted only where no policy for the table exists
yet. The registrations today (`surfaces/http/app_mcp_composition.py`):

| Table                   | Default (days) | Owning spec                                   |
| ----------------------- | -------------- | --------------------------------------------- |
| `audit_log`             | 365            | resource-framework                            |
| `mcp_invocations`       | 30             | mcp-gateway                                   |
| `sync_runs`             | 90             | vault-sync                                    |
| `conversations_archive` | 7              | chat — idle conversations are archived        |
| `conversations`         | 30             | chat — archived conversations are deleted     |

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
