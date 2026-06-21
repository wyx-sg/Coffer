# Feature Specification: Provider Switching

> 中文版: [spec.zh.md](./spec.zh.md)

**Feature Branch**: `feature/G9-provider-switching`
**Created**: 2026-06-21
**Status**: Draft

## One-line

A shared **provider registry** lets users configure LLM providers once (name,
wire format, base URL, encrypted credential, model) and project that
configuration into the matching agent's native config file. Coffer's
differentiator over `claude switch` or equivalent per-tool scripting: a unified
registry with governance — Fernet-encrypted credentials, full audit trail, and
git-sync — not per-tool silos.

## Why

Claude Code and Codex each require their own native config files
(`~/.claude/settings.json`, `~/.codex/config.toml`) with provider-specific keys
and base URLs. Switching providers today means editing multiple files by hand,
storing keys in plaintext, and losing the audit trail. Coffer centralises
provider profiles: configure once, switch (with projection), audit everything.

## Confirmed Decisions

Three decisions were locked before spec was written; do not relitigate them.

### Decision A — single-wire profile, per-agent activation

One profile holds `{name, wire_format, base_url, credential_ref, model,
fast_model, wire_api, is_active}`. A profile projects ONLY into agents whose
native protocol matches its `wire_format`:

- `anthropic` → Claude Code (`~/.claude/settings.json`)
- `openai` → Codex (`~/.codex/config.toml`)

At most one active profile per wire format exists at any time (per-wire
single-active invariant, analogous to the `ModelConfig.is_default` pattern in
the chat engine). Claude Code and Codex "share" the registry — a credential ref
may be reused across profiles — but NOT via one record driving both agents.

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
- CLI: `coffer provider list|add|show|edit|remove|switch|key`
- HTTP API: `/api/v1/providers` (list / create / get / patch / delete) plus
  `/api/v1/providers/{name}/activate`
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
| `wire_format` | `"anthropic" \| "openai"` | Required. Gates which agent this profile projects to. |
| `base_url` | `str` | Required. The upstream LLM endpoint. |
| `credential_ref` | `str` | Required. Fernet vault ref; pattern `^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$`. Conventionally `provider/<name>/key` for an owned secret; multiple profiles MAY share one ref. |
| `model` | `str` | Required. Primary model ID → `ANTHROPIC_MODEL` (Claude) / `model` (Codex). |
| `fast_model` | `str \| None` | Optional. `ANTHROPIC_SMALL_FAST_MODEL` (anthropic wire only); ignored for openai. |
| `wire_api` | `"chat" \| "responses"` | Optional, default `"chat"`. openai/Codex only (`[model_providers.*].wire_api`). |
| `is_active` | `bool` | At most one active per `wire_format`. On import, if >1 active for a wire, normalise deterministically (keep most-recently-updated). |

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
kind="provider", name=<name>), actor=..., details={...})`.

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

**Credential source rule**: Exactly one of `secret_value` (stored to vault
under `provider/<name>/key`, kept as ref) or `credential_ref` (reuse existing)
must be supplied on create. Reject if both or neither are present.

`ProviderOut` NEVER includes the secret; includes `credential_ref` + `is_active`.

## CLI

`coffer provider list|add|show|edit|remove|switch|key` with `--json`.

- `add` prompts for / accepts the secret.
- `key` prints the resolved secret (for `apiKeyHelper`); requires `--wire <wire_format>`;
  resolves by the active profile for that wire.

## Frontend (minimal)

- `frontend/src/lib/api/providers.ts` — hand-written client + TS types (`types.ts`
  codegen covers only the 001 gateway spec; do NOT expect generated types here).
- Providers page = a `DataTable` (reuse the shared component; see SkillsPage /
  MCP page) with columns: name / wire_format / base_url / model / active. Row
  actions: switch / delete; header action: create. Editing a profile is
  available via the CLI (`coffer provider edit`) and the PATCH API, not the
  desktop page. No detail page, no per-agent binding tab in this PR. Add
  `vi.mock` for any new hook in page + table tests.

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
- **When** the user attempts to create a profile without supplying either
  `secret_value` or `credential_ref`,
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

### Key Entities

- **ProviderProfile**: A Resource of kind `provider`, identified by
  `provider:<name>`. Holds wire format, base URL, credential ref, model(s), and
  active state. Never holds the raw secret.
- **`apply_anthropic_settings` / `apply_codex_provider`**: Pure functions in
  `domain/provider/projection.py` that return the new native-config TEXT directly.
  Analogous to `domain/agent/mcp_install.py`'s `apply_install`. No `ProjectionPatch`
  dataclass; no `build_patch()` function.
- **`ProviderService._project`**: Private method in `application/provider/service.py`
  that calls the pure projection functions and performs the file write.
- **`ProjectionTarget` / `target_for(wire)`**: Helper in `domain/provider/projection.py`
  mapping `wire_format` to the target config file descriptor.
- **`ProviderService.resolve_active_key(wire)`**: Takes a `wire_format` string
  only; no by-name resolution on this method.

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
