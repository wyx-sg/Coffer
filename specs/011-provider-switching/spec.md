# Feature Specification: Provider Switching

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/G9-provider-switching`
**Created**: 2026-06-21
**Status**: Draft

## One-line

A unified **LLM connection** lets users configure a key once (name, wire format,
base URL, encrypted credential, model) and use it BOTH ways: project it into the
matching agent's native config file AND let Coffer's own internal LLM engine run
on it. One connection retires the separate `ModelConfig`/`chat_models` registry,
folding internal-engine model selection into the same record. Coffer's
differentiator over `claude switch` or equivalent per-tool scripting: a unified
registry with governance — Fernet-encrypted credentials, full audit trail, and
git-sync — not per-tool silos.

## Why

Claude Code and Codex each require their own native config files
(`~/.claude/settings.json`, `~/.codex/config.toml`) with provider-specific keys
and base URLs, and Coffer's internal engine used to keep a SECOND, parallel
model registry (`chat_models`). Switching providers today means editing multiple
files by hand, storing keys in plaintext, and losing the audit trail — and a key
configured for an agent could not be reused by the internal engine. Coffer
centralises connections: configure once, project it to the matching agent
(switch), mark one as the internal engine's default, audit everything.

## Confirmed Decisions

Three decisions were locked before spec was written; do not relitigate them.

### Decision A — single-wire connection, per-agent activation, one internal default

One connection holds `{name, wire_format, base_url, credential_ref, model,
fast_model, wire_api, is_active, internal_default}`. A connection projects ONLY
into agents whose native protocol matches its `wire_format`:

- `anthropic` → Claude Code (`~/.claude/settings.json`)
- `openai` → Codex (`~/.codex/config.toml`)
- `ollama` → internal-only; never projected to any agent

At most one active connection per wire format exists at any time (per-wire
single-active invariant, analogous to the `ModelConfig.is_default` pattern in
the retired chat-model registry). Claude Code and Codex "share" the registry — a
credential ref may be reused across connections — but NOT via one record driving
both agents.

In addition to per-agent activation, a connection MAY carry a single GLOBAL
`internal_default` flag (≤1 across all connections) marking the connection
Coffer's own internal LLM engine uses (memory organizer, reorg, distill,
`coffer__ask`). The third wire `ollama` is internal-only: it never projects to
any agent, and because it has no API key its `credential_ref` is absent — it
needs only a `base_url`. `credential_ref` is therefore OPTIONAL: required for
anthropic/openai, absent for ollama. One connection may be BOTH active (projected
to its wire's agent) AND `internal_default` (used internally) — one key, two
uses.

### Decision B — credential isolation; key never plaintext in native config

Consistent with the existing MCP `credential_refs` pattern and the project's
"credential isolation" principle. The raw key stays in the Fernet vault and is
materialised on demand:

- **Claude Code**: `apiKeyHelper = "coffer provider key --wire anthropic"` in
  `settings.json`. Claude invokes this command to fetch the key. Because Claude
  Code re-invokes `apiKeyHelper` periodically, this design makes a future
  hot-switch nearly free — forward-looking only.
- **Codex**: `env_key = "COFFER_PROVIDER_KEY"` in the `[model_providers.coffer]`
  TOML table. Codex reads the key from that env var at runtime. This PR does NOT
  modify Codex spawning; the user must export the key manually (see Quickstart).
  State plainly: **Codex standalone requires `COFFER_PROVIDER_KEY` to be set in
  the shell; auto env-injection into Coffer-spawned Codex is deferred with
  hot-switch.** This is the accepted cost of Decision B.

The raw key is NEVER written to `settings.json`, `config.toml`, or any other
native config file.

### Decision C — phased; hot-switch is OUT OF SCOPE for this PR

This PR ships: registry + projection + switch op + audit + sync wiring.

Hot-switch (mid-session reload of a running Claude Code or Codex process) is a
**separate, later PR** and is explicitly **out of scope here**.

## Scope

### In scope

- Backend `provider` resource Kind (CRUD via ResourceService → automatic audit
  + automatic sync); credential handling (store secret to Fernet vault, keep
  only ref); projection service (write native config for the matching agent);
  switch / activate operation; `PROVIDER_SWITCHED` audit event; sync wiring
  (register the kind); key-resolution used by Claude's `apiKeyHelper`.
- Internal-engine connection selection: the global `internal_default` flag,
  `set_internal_default(name)` + `resolve_internal_connection()`, the
  `provider_internal_default_set` audit event, consumed by Coffer's internal
  LLM engine (memory organizer / reorg / distill / `coffer__ask`).
- Retire the standalone `ModelConfig` registry (model CRUD REST + `coffer model`
  CLI), folding internal-engine model selection into the connection. The
  provider introspection routes (`list-models`, `test-connection`) are KEPT.
- CLI: `coffer provider list|add|show|edit|remove|switch|key|internal-default`
- HTTP API: `/api/v1/providers` (list / create / get / patch / delete) plus
  `/api/v1/providers/{name}/activate` and
  `/api/v1/providers/{name}/internal-default`
- Frontend: a minimal Providers resource page — `DataTable` (name, wire format,
  base URL, model, active) with create / switch / delete actions,
  mirroring the Skills and MCP resource-page pattern.
- Tests across all tiers; acceptance markers tying to the scenarios below; zh
  companion docs for every doc file in this spec bundle.

### Out of scope (explicit non-goals)

- **Hot-switch / running-process reload** — deferred to a later PR.
- **Explicit deactivate / native-config restore** — no "revert to default" op;
  switching overwrites the relevant keys; restoration is a future concern.
- **Provider drift-verify** — spec item 4.9; separate spec.
- **Per-agent provider override beyond wire matching** — a profile whose
  `wire_format` does not match an agent is simply not projected to it; no
  manual per-agent binding.
- **Proxy / failover / format conversion** — no proxying; no fallback chains;
  no anthropic↔openai protocol translation. Wire format is fixed per profile.
- **Auto env-injection of `COFFER_PROVIDER_KEY` into Coffer-spawned Codex** —
  deferred with hot-switch.

## Entity — ProviderProfile (Kind = `"provider"`)

Resource `name` = the profile name (unique within kind; validated by
`validate_name`).

### Config fields (synced `config` dict; deterministic, no machine-local ids)

| Field | Type | Notes |
|---|---|---|
| `wire_format` | `"anthropic" \| "openai" \| "ollama"` | Required. Gates which agent this connection projects to. `ollama` is internal-only — projected to NO agent (`target_for` returns None). |
| `base_url` | `str` | Required (all wires). The upstream LLM endpoint. |
| `credential_ref` | `str \| None` | Optional. Required for anthropic/openai (Fernet vault ref; pattern `^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$`; conventionally `provider/<name>/key`; multiple connections MAY share one ref). MUST be absent for ollama (no API key). |
| `model` | `str` | Required. Primary model ID → `ANTHROPIC_MODEL` (Claude) / `model` (Codex); the model Coffer's internal engine runs when this is the internal default. |
| `fast_model` | `str \| None` | Optional. `ANTHROPIC_SMALL_FAST_MODEL` (anthropic wire only); ignored for openai. |
| `wire_api` | `"chat" \| "responses"` | Optional, default `"chat"`. openai/Codex only (`[model_providers.*].wire_api`). |
| `is_active` | `bool` | At most one active per `wire_format`. ollama is never projected, so an ollama connection is always inactive. On import, if >1 active for a wire, normalise deterministically (keep most-recently-updated). |
| `internal_default` | `bool` | At most one connection globally is the internal-engine default. On import, if >1, normalise (keep most-recently-updated). |

- `audit_redactor`: config holds NO secret (only `credential_ref`); audit shows
  config as-is. Double-check that no secret leaks via `config` or `details`.

## Projection — Writing Native Config

Analogous to `McpInjectionSpec` in `mcp_injection.py`; encode as a small
explicit table.

### anthropic → Claude Code

**File**: `~/.claude/settings.json` (JSON); resolved via
`spec_for(AgentType.CLAUDE_CODE, "settings", cfg_dir)`.

Coffer MANAGES exactly these keys by MERGING into the existing JSON (never full
replace) and writing via `ConfigFileStore.write_text_atomic` (atomic + `.bak`):

| Key path | Value |
|---|---|
| `apiKeyHelper` | `"coffer provider key --wire anthropic"` |
| `env.ANTHROPIC_BASE_URL` | `profile.base_url` |
| `env.ANTHROPIC_MODEL` | `profile.model` |
| `env.ANTHROPIC_SMALL_FAST_MODEL` | `profile.fast_model` (omit / remove key when `None`) |

`ANTHROPIC_API_KEY` MUST NOT be written (it would override the helper).
Everything else in `settings.json` is preserved; serialised via
`json.dumps(indent=2)` like the MCP JSON path in `mcp_entries.py`.

### openai → Codex

**File**: `~/.codex/config.toml` (TOML); resolved via
`spec_for(AgentType.CODEX, "config", cfg_dir)`.

Coffer MANAGES via `tomlkit` (comment/order-preserving, like the MCP TOML path):

| Key path | Value |
|---|---|
| `model` | `profile.model` |
| `model_provider` | `"coffer"` |
| `[model_providers.coffer].name` | `"Coffer (<profile name>)"` |
| `[model_providers.coffer].base_url` | `profile.base_url` |
| `[model_providers.coffer].wire_api` | `profile.wire_api` (default `"chat"`) |
| `[model_providers.coffer].env_key` | `"COFFER_PROVIDER_KEY"` |

Everything else preserved.

### ollama → (internal only)

An ollama connection projects into NO agent config: `target_for(WireFormat.ollama)`
returns `None`, so activation writes no native config and the connection is never
`is_active`. It is used solely by Coffer's internal engine, reached via
`resolve_internal_connection` when it is the `internal_default`.

## Switch / Activate Operation

`POST /api/v1/providers/{name}/activate` / `coffer provider switch <name>`:

1. Profile must exist; return 404 otherwise.
2. Clear `is_active` on all other profiles of the **same** `wire_format` via
   `ResourceService.update_config`, then set the target's `is_active=true` via
   a second call. The single-process daemon serialises requests so switches
   never interleave.
3. For each ENABLED registered agent whose `AgentType` native wire matches
   `profile.wire_format`, project (write native config). If no matching agent is
   registered, record active but project nothing — **not an error** (report as
   skipped).
4. Emit `provider_switched` audit event with details `{from: <prev_name|null>,
   to: <name>, wire_format, agents: [...projected...]}`.
5. Return `{activated: <name>, projected: [agent...], skipped: [agent...]}`.

NOTE: projection (`_project`) runs BEFORE the activation flip; a native-config
write failure aborts the switch with the registry unchanged.

## Internal engine (Coffer's own LLM)

Separate from per-agent activation, the global `internal_default` flag (≤1 across
all connections) selects the connection Coffer's own internal LLM engine uses —
the memory organizer, reorg, distill, and `coffer__ask`.

- `set_internal_default(name)`: clears `internal_default` on all other
  connections, then sets it on the target (sequential clear-then-set, serialised
  by the single-process daemon so the global single-internal-default invariant
  holds), and emits a `provider_internal_default_set` audit event.
- `resolve_internal_connection() -> ProviderConfig | None`: returns the
  `internal_default` connection's config, or `None` when no connection is marked.
  When `None`, the internal engine (memory organizer / reorg / distill /
  `coffer__ask`) is a clean no-op rather than an error.
- `build_chat_model(connection, ...)`: the internal engine builds its chat model
  from the resolved connection, dispatched by `wire_format` (anthropic / openai /
  ollama). This replaces the retired `ModelConfig` registry's model selection.

A connection may be BOTH `is_active` (projected to its wire's agent) AND
`internal_default` (used internally) — one key, two uses.

## Key Resolution (apiKeyHelper + Codex env)

`coffer provider key --wire <wire_format>`:

1. Find the active profile for the given wire format.
2. Read `credential_ref` → decrypt via `EncryptedCredentialStore.get(ref)`.
3. Print the raw key to **stdout ONLY**. Do NOT log the value.

This is the command Claude Code's `apiKeyHelper` invokes (`--wire anthropic`).
For Codex, the user exports: `export COFFER_PROVIDER_KEY="$(coffer provider key --wire openai)"`.

## Sync (reuse, ~zero engine change)

Modeling `provider` as a ResourceService Kind makes it sync automatically:

- `SyncExporter` lists all kinds → serialises each row to
  `resources/provider/<name>.yaml` via `resource_to_doc`.
- `SyncImporter` reconciles by `(kind, name)`.
- Credentials already sync as Fernet ciphertext at `credentials/<ref>.enc`.

Touch points: define the Kind, add a `wire_provider_kind(...)` helper (mirror
`wire_kb_kind` in `surfaces/http/wiring.py`), register into `app.state.kinds`
in `surfaces/http/app.py`. No new migration, no manifest SCHEMA_VERSION bump.

## Audit (reuse)

`ResourceService` create / update already emit `RESOURCE_*` events with
kind-redacted config. Add `PROVIDER_SWITCHED = "provider_switched"` to `AuditEventType`
(`backend/coffer/domain/audit.py`) and emit it from the switch operation via
`AuditService.record(AuditEventType.PROVIDER_SWITCHED.value, ref=ResourceRef(
kind="provider", name=<name>), actor=..., details={...})`. Likewise add
`PROVIDER_INTERNAL_DEFAULT_SET = "provider_internal_default_set"` and emit it
from `set_internal_default`.

## HTTP API

Hand-written OpenAPI; 005-style — not contract-test-gated; sync manually.
Full spec in [contracts/api.openapi.yaml](./contracts/api.openapi.yaml).

- `GET  /api/v1/providers` → list profiles (`{ "providers": [ ProviderOut, ... ] }`)
- `POST /api/v1/providers` → create (see credential-source rules below)
- `GET  /api/v1/providers/{name}` → one profile
- `PATCH /api/v1/providers/{name}` → update mutable fields (`base_url`, `model`,
  `fast_model`, `wire_api`, `secret_value`); `wire_format` and `credential_ref`
  are immutable; `secret_value` rotates the stored secret
- `DELETE /api/v1/providers/{name}` → delete; guard via
  `find_credential_citations` before removing an owned secret
- `POST /api/v1/providers/{name}/activate` → switch; returns
  `{activated, projected:[agent...], skipped:[agent...]}`
- `POST /api/v1/providers/{name}/internal-default` → set the internal-engine
  default; returns the updated `ProviderOut`

`wire_format` accepts `anthropic`, `openai`, or `ollama` on request and response.

**Credential source rule**: For anthropic/openai, exactly one of `secret_value`
(stored to vault under `provider/<name>/key`, kept as ref) or `credential_ref`
(reuse existing) must be supplied on create; reject if both or neither are
present. For `wire_format=ollama` the credential is OPTIONAL — supply NEITHER
`secret_value` nor `credential_ref` (an ollama connection has no key).

`ProviderOut` NEVER includes the secret; includes `credential_ref`, `is_active`,
and `internal_default`.

## CLI

`coffer provider list|add|show|edit|remove|switch|key|internal-default` with `--json`.

- `add` prompts for / accepts the secret (skipped for an ollama connection,
  which has no key).
- `key` prints the resolved secret (for `apiKeyHelper`); requires `--wire <wire_format>`;
  resolves by the active profile for that wire.
- `internal-default <name>` marks a connection as Coffer's internal-engine
  default (clears any previous one).

## Frontend (minimal)

- `frontend/src/lib/api/providers.ts` — hand-written client + TS types (`types.ts`
  codegen covers only the 001 gateway spec; do NOT expect generated types here).
- A unified **Settings → LLM Connections** page (route `/settings/llm-connections`)
  is the connection library: a `DataTable` (reuse the shared component; see
  SkillsPage / MCP page) with columns name / wire_format / base_url / model /
  active / internal, header action create, and row actions switch /
  set-internal-default / delete, PLUS the Embedding card. The page shows ONLY
  connection (provider + model) info — no agent names, no presets, no modality
  split. Editing a connection is available via the CLI (`coffer provider edit`)
  and the PATCH API, not the desktop page.
- Per-agent connection + model selection lives on the **agent detail page
  (Overview tab)**, filtered to that agent's wire, reusing the activate API. The
  LLM Connections page does not bind agents.
- The old `/settings/models` and `/settings/providers` routes redirect to
  `/settings/llm-connections`.
- Add `vi.mock` for any new hook in page + table tests.

## Acceptance Scenarios

Per `agents/sdd.md`, every scenario in this section is referenced by at least
one test marked `@pytest.mark.acceptance(spec="011-provider-switching", scenario="…")`
(Python) or `acceptance("011-provider-switching", "…", …)` (TypeScript).

### Scenario: create an anthropic provider profile with an inline secret

- **Given** no provider named `my-provider` exists,
- **When** the user creates a profile with `wire_format="anthropic"`, a
  `base_url`, `model`, and `secret_value` (the raw API key),
- **Then** the profile is persisted with a `credential_ref` of
  `provider/my-provider/key`, the raw key is stored in the Fernet vault under
  that ref, `ProviderOut` is returned with no secret field, and
  `RESOURCE_CREATED` is audited.

### Scenario: create a profile that reuses an existing credential ref

- **Given** a credential already exists under ref `shared/key`,
- **When** the user creates a profile supplying `credential_ref="shared/key"` (no `secret_value`),
- **Then** the profile is persisted pointing to the existing ref, no new vault
  entry is created, and `ProviderOut` reflects the supplied `credential_ref`.

### Scenario: reject a profile with an unknown wire format

- **Given** the daemon is running,
- **When** the user attempts to create a profile with `wire_format="grpc"`,
- **Then** the request is rejected with `422 Unprocessable Entity` and no
  profile row is created.

### Scenario: reject a profile that supplies neither a secret nor a credential ref

- **Given** the daemon is running,
- **When** the user attempts to create an **anthropic** connection (the
  neither-rule applies to anthropic/openai; ollama legitimately supplies neither)
  without supplying either `secret_value` or `credential_ref`,
- **Then** the request is rejected with `422 Unprocessable Entity` and no
  profile row or vault entry is created.

### Scenario: update a provider profile

- **Given** a provider profile exists,
- **When** the user patches `base_url` and `model` (no `secret_value`),
- **Then** only those fields are updated, `credential_ref` is unchanged, and
  `RESOURCE_UPDATED` is audited.

### Scenario: list provider profiles

- **Given** two provider profiles exist (one anthropic, one openai),
- **When** the user lists all providers,
- **Then** both appear in `ProviderOut[]`, none includes the raw secret, and
  each carries the correct `is_active` flag.

### Scenario: delete a provider profile cleans up its owned credential

- **Given** a profile whose `credential_ref` is `provider/my-provider/key`
  (owned; no other profile shares it),
- **When** the user deletes the profile,
- **Then** the vault entry at that ref is deleted and `RESOURCE_DELETED` is
  audited.

### Scenario: activate an anthropic profile writes Claude Code settings

- **Given** a Claude Code agent is registered and an anthropic profile exists,
- **When** the user activates the profile,
- **Then** `~/.claude/settings.json` contains `apiKeyHelper`,
  `env.ANTHROPIC_BASE_URL`, and `env.ANTHROPIC_MODEL`; if `fast_model` is set,
  `env.ANTHROPIC_SMALL_FAST_MODEL` is present; `ANTHROPIC_API_KEY` is absent;
  and the profile's `is_active` becomes `true`.

### Scenario: activate an openai profile writes Codex config

- **Given** a Codex agent is registered and an openai profile exists,
- **When** the user activates the profile,
- **Then** `~/.codex/config.toml` contains `model`, `model_provider = "coffer"`,
  and a `[model_providers.coffer]` table with `base_url`, `wire_api`, and
  `env_key = "COFFER_PROVIDER_KEY"`; the profile's `is_active` becomes `true`.

### Scenario: activating a profile deactivates the previous active profile of the same wire format

- **Given** anthropic profile A is active and anthropic profile B exists,
- **When** the user activates profile B,
- **Then** profile B becomes active and profile A becomes inactive (the
  single-process daemon serialises the clear-then-set so switches never
  interleave).

### Scenario: activate a profile whose wire matches no registered agent records active but projects nothing

- **Given** no Codex agent is registered and an openai profile exists,
- **When** the user activates the openai profile,
- **Then** the profile's `is_active` becomes `true`, no config file is written,
  and the response carries `skipped: ["codex"]` (or empty `projected`).

### Scenario: switching preserves unrelated native-config keys and writes a .bak backup

- **Given** `~/.claude/settings.json` contains keys that Coffer does not manage
  (e.g. `theme`, `mcpServers`),
- **When** the user activates an anthropic profile,
- **Then** those keys are preserved byte-for-byte in the updated file, a
  `.bak` file is written before the update, and only the Coffer-managed keys
  are changed.

### Scenario: a provider switch is recorded in the audit log

- **Given** an anthropic profile is activated,
- **When** the user queries the audit log,
- **Then** a `provider_switched` entry appears with details `{from, to,
  wire_format, agents}`, timestamp, and actor.

### Scenario: resolve the active provider key for the apiKeyHelper

- **Given** an anthropic profile is active with a known secret stored in the
  vault,
- **When** `coffer provider key --wire anthropic` is executed,
- **Then** the raw key is printed to stdout and the vault key is NOT logged.

### Scenario: a provider profile round-trips through sync export and import

- **Given** a provider profile with a credential ref exists,
- **When** the sync exporter runs followed by the sync importer on a clean DB,
- **Then** the profile row is restored with identical `config` fields, the
  credential ciphertext is present at `credentials/<ref>.enc`, and no secret
  is exposed in the sync workspace plaintext.

### Scenario: the command line covers create, list, and switch

- **Given** the daemon is running,
- **When** the user runs `coffer provider add`, `coffer provider list --json`,
  and `coffer provider switch` from the CLI,
- **Then** each operation succeeds with the same effect as the HTTP API and
  `list --json` returns machine-readable output.

### Scenario: the Providers page lists profiles and can switch the active one

- **Given** the Providers page is rendered with two mock profiles,
- **When** the user clicks the "Switch" row action for the inactive profile,
- **Then** the activate mutation is called with the correct profile name and the
  table reflects the updated active state (TypeScript acceptance test).

### Scenario: create an ollama connection without a credential

- **Given** no connection named `local-llm` exists,
- **When** the user creates a connection with `wire_format="ollama"`, a
  `base_url`, `model`, and neither `secret_value` nor `credential_ref`,
- **Then** the connection persists with `credential_ref` null, no vault entry is
  created, and `ProviderOut` shows `internal_default=false`.

### Scenario: set a connection as the internal engine default

- **Given** two connections exist and none is the internal default,
- **When** the user sets the second as the internal default,
- **Then** its `internal_default` becomes true, the other stays false, and a
  `provider_internal_default_set` audit entry is recorded.

### Scenario: setting a new internal default clears the previous one

- **Given** connection A is the internal default,
- **When** the user sets connection B as the internal default,
- **Then** B's `internal_default` becomes true and A's becomes false (global
  single-internal-default invariant).

## Requirements

### Functional Requirements

**Resource model**

- **FR-001**: System MUST register each managed provider as a Resource of kind
  `provider`, identified by `provider:<name>`.
- **FR-002**: System MUST validate provider config against a kind-specific schema
  (fields: `wire_format`, `base_url`, `credential_ref`, `model`, `fast_model?`,
  `wire_api?`, `is_active`).
- **FR-003**: `ProviderOut` MUST NEVER include the raw secret. `credential_ref`
  and `is_active` MUST be included.

**Credential handling**

- **FR-004**: On create with `secret_value`, System MUST store the raw key under
  `provider/<name>/key` in the Fernet vault and persist only the ref. Exactly
  one of `secret_value` or `credential_ref` must be supplied; both or neither
  must be rejected `422`.
- **FR-005**: On `PATCH` with `secret_value`, System MUST rotate the stored
  secret (overwrite the vault entry) without changing the ref.
- **FR-006**: On delete, if the profile owns its credential ref (no other profile
  cites it), System MUST delete the vault entry via `find_credential_citations`
  guard.

**Projection**

- **FR-007**: System MUST project an activated anthropic profile into
  `~/.claude/settings.json` via `ConfigFileStore.write_text_atomic` (atomic +
  `.bak`), merging only the specified keys, preserving everything else.
  `ANTHROPIC_API_KEY` MUST NOT be written.
- **FR-008**: System MUST project an activated openai profile into
  `~/.codex/config.toml` via `tomlkit` (comment/order-preserving), merging
  only the specified keys, preserving everything else.
- **FR-009**: If `fast_model` is `None`, the key `env.ANTHROPIC_SMALL_FAST_MODEL`
  MUST be omitted or removed from `settings.json`.
- **FR-010**: Domain projection logic MUST be pure (no I/O). The pure functions
  `apply_anthropic_settings(...)` and `apply_codex_provider(...)` in
  `domain/provider/projection.py` return the new native-config TEXT directly;
  `ProviderService._project(...)` calls them and performs the file write.

**Single-active invariant**

- **FR-011**: At most one profile per `wire_format` may have `is_active=true`.
  Activating a profile MUST clear `is_active` on all others of the same wire
  via sequential `ResourceService.update_config` calls, then set the target's
  `is_active=true`. The single-process daemon serialises requests so switches
  never interleave. On import with >1 active for a wire, normalise: keep
  most-recently-updated, set the rest to inactive.

**Switch operation**

- **FR-012**: `POST /api/v1/providers/{name}/activate` MUST apply FR-011, then
  project to all ENABLED registered agents whose native wire matches
  `wire_format`. If no matching agent is registered, record active and return a
  non-empty `skipped` list — NOT an error.
- **FR-013**: System MUST emit audit event with value `"provider_switched"` and
  details `{from, to, wire_format, agents: [...projected...]}`.

**Key resolution**

- **FR-014**: `coffer provider key --wire <wire_format>` MUST find the active
  profile for that wire, decrypt via `EncryptedCredentialStore.get(ref)`, and
  print to stdout only. The raw key MUST NOT be logged. Resolution by profile
  `<name>` is NOT supported on this subcommand; use `--wire` only.

**Sync**

- **FR-015**: The `provider` kind MUST be registered into `app.state.kinds` so
  `SyncExporter`/`SyncImporter` handle it automatically. No new migration or
  SCHEMA_VERSION bump is needed.

**Audit**

- **FR-016**: `PROVIDER_SWITCHED` (value `"provider_switched"`) MUST be added
  to `AuditEventType` and emitted on every successful switch with `{from, to,
  wire_format, agents}` in details. `RESOURCE_CREATED`, `RESOURCE_UPDATED`,
  `RESOURCE_DELETED` are emitted automatically via `ResourceService`.

**Surfaces**

- **FR-017**: Create, switch, and delete operations MUST be available via (a) the
  REST API, (b) `coffer provider ...` CLI with `--json`, and (c) the desktop
  Providers page. Editing a profile (PATCH) is available via the REST API and
  the CLI (`coffer provider edit`) only; the desktop page does NOT require an
  inline edit affordance.
- **FR-018**: The CLI `key` subcommand MUST support `--wire <wire_format>` to
  resolve by the active profile for that wire. Resolution by positional `<name>`
  is NOT supported; `--wire` is the only accepted form.

**Internal engine connection**

- **FR-019**: The `ollama` wire is internal-only and projects to NO agent:
  `target_for(WireFormat.ollama)` MUST return `None`, an ollama connection is
  never `is_active`, and activating it writes no native config.
- **FR-020**: `credential_ref` MUST be optional — required for anthropic/openai,
  absent for ollama. On create, supplying neither `secret_value` nor
  `credential_ref` is valid ONLY for `wire_format=ollama`; for anthropic/openai
  the exactly-one rule of FR-004 stands.
- **FR-021**: At most one connection globally MUST have `internal_default=true`.
  `set_internal_default` MUST clear `internal_default` on all others, then set
  the target (sequential clear-then-set serialised by the single-process
  daemon). On import with >1 internal default, normalise: keep
  most-recently-updated, clear the rest.
- **FR-022**: `POST /api/v1/providers/{name}/internal-default` MUST set the named
  connection as the internal-engine default (applying FR-021), emit a
  `provider_internal_default_set` audit event, and return the updated
  `ProviderOut`.
- **FR-023**: `resolve_internal_connection()` MUST return the
  `internal_default` connection's `ProviderConfig`, or `None` when no connection
  is marked. When `None`, the internal engine (memory organizer / reorg /
  distill / `coffer__ask`) MUST be a clean no-op rather than an error.
- **FR-024**: The standalone `ModelConfig` registry (model CRUD REST +
  `coffer model` CLI) MUST be retired. The internal engine MUST build its chat
  model from the internal-default connection via `build_chat_model(connection,
  ...)` (dispatched by `wire_format`). The provider introspection routes
  (`POST /api/v1/models/list-models`, `/api/v1/models/test-connection`) MUST be
  retained.

### Key Entities

- **ProviderProfile**: A Resource of kind `provider`, identified by
  `provider:<name>`. Holds wire format, base URL, optional credential ref
  (absent for ollama), model(s), per-wire `is_active` state, and the global
  `internal_default` flag. Never holds the raw secret.
- **`apply_anthropic_settings` / `apply_codex_provider`**: Pure functions in
  `domain/provider/projection.py` that return the new native-config TEXT directly.
  Analogous to `domain/agent/mcp_install.py`'s `apply_install`. No `ProjectionPatch`
  dataclass; no `build_patch()` function.
- **`ProviderService._project`**: Private method in `application/provider/service.py`
  that calls the pure projection functions and performs the file write.
- **`ProjectionTarget` / `target_for(wire)`**: Helper in `domain/provider/projection.py`
  mapping `wire_format` to the target config file descriptor; returns `None` for
  `ollama` (internal-only, no projection).
- **`ProviderService.resolve_active_key(wire)`**: Takes a `wire_format` string
  only; no by-name resolution on this method.
- **`ProviderService.set_internal_default(name)`**: Clears `internal_default` on
  all other connections then sets the target; emits `provider_internal_default_set`.
- **`ProviderService.resolve_internal_connection()`**: Returns the internal-default
  connection's `ProviderConfig`, or `None` (→ the internal engine is a clean
  no-op). `build_chat_model(connection, ...)` builds the internal engine's chat
  model from it, dispatched by `wire_format`.

## Success Criteria

- **SC-001**: From a fresh install, a user can add an anthropic provider profile,
  activate it, and have Claude Code pick up the new endpoint within one
  `coffer provider switch` command.
- **SC-002**: No raw key ever appears in `settings.json`, `config.toml`, or the
  sync workspace (`resources/provider/*.yaml`) — verified by an automated scan
  in integration tests.
- **SC-003**: Every Acceptance Scenario is covered by at least one test marked
  `acceptance(spec="011-provider-switching", scenario="…")`, and
  `make verify-acceptance` reports zero uncovered scenarios.
- **SC-004**: `make verify` passes locally and in CI.
- **SC-005**: Activating a profile writes the target native-config key set and
  does NOT touch any key outside the defined managed set.
- **SC-006**: With an `internal_default` connection configured, Coffer's internal
  engine (memory organize / reorg / distill / `coffer__ask`) runs on it; with no
  connection marked `internal_default`, the internal engine is a clean no-op.

## Assumptions

- Spec 004-agent-registry (PR #25) is merged; `AgentType`, `AgentConfig`, and
  the agent CRUD + `on_delete` hook are available.
- `EncryptedCredentialStore` (Fernet vault) and `ConfigFileStore.write_text_atomic`
  are available (spec 001).
- `tomlkit` is already in the backend's Python dependencies (added by MCP TOML
  path support).
- Coffer runs as a single-user personal tool; no multi-user access control is
  needed beyond the existing `X-Coffer-Token` gate.
- The user's `~/.claude/settings.json` and `~/.codex/config.toml` are writable
  by Coffer. If the file does not exist, Coffer creates it with only the managed
  keys.
- Provider drift-verify (checking whether the live native config matches the
  active profile) is deferred to spec 4.9.
