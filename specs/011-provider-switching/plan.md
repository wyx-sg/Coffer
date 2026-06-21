# Implementation Plan: 011 — Provider Switching

**Branch**: `feature/G9-provider-switching`
**Date**: 2026-06-21
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

Add the `provider` Resource kind to Coffer: a shared registry of LLM provider
profiles, each projected into the matching agent's native config file
(`~/.claude/settings.json` for anthropic/Claude Code;
`~/.codex/config.toml` for openai/Codex). Credentials are Fernet-encrypted;
the raw key never touches a native config file. Ships with REST routes, CLI
subcommands, a minimal frontend DataTable page, and sync / audit wiring.

## Technical Context

| Dimension | Value |
|---|---|
| **Language / Version** | Python 3.12+, TypeScript 5.x |
| **New runtime deps** | None new; `tomlkit` already in backend (MCP TOML path); `EncryptedCredentialStore` already in codebase |
| **Storage** | Shared `resources` table (`kind='provider'`); no new migration |
| **Testing** | 4-tier; acceptance markers tie to spec scenarios |
| **Target Platforms** | macOS arm64+x64 (primary); Windows / Linux (existing CI) |
| **Performance Goals** | Activate (project to disk) ≤ 200 ms |
| **Constraints** | Local-first; credential isolation (Decision B); domain pure (no I/O) |

## Constitution Check

| Clause | Compliance | Notes |
|---|---|---|
| I. Local-First | ✅ | Provider profiles and credentials stored locally; sync is user-controlled git |
| II. Spec-as-Truth | ✅ | Spec committed before code |
| III. Open-Source-Readiness | ✅ | No new closed-source deps |
| Languages | ✅ | Python + TypeScript |
| Architecture: layered | ✅ | Pure projection functions return TEXT (domain); file write in `_project` (service); no I/O in domain layer |
| Persistence | ✅ | Control plane in SQLite `resources` table (reuse); raw key in Fernet vault |
| Credentials | ✅ | Raw key in vault only; `ProviderConfig` holds only `credential_ref` |
| Network defaults | ✅ | Loopback-only HTTP API |

## Project Structure

### Documentation

```
specs/011-provider-switching/
  spec.md / spec.zh.md
  data-model.md / data-model.zh.md
  plan.md / plan.zh.md             (this file)
  quickstart.md / quickstart.zh.md
  research.md / research.zh.md
  contracts/api.openapi.yaml
docs/decisions/ADR-032-provider-switching.md
docs/decisions/ADR-032-provider-switching.zh.md
```

### New backend modules

```
backend/coffer/domain/provider/
  __init__.py
  config.py        # WireFormat, WireApi enums + ProviderConfig (Pydantic v2)
  projection.py    # apply_anthropic_settings / apply_codex_provider pure functions
                   # + ProjectionTarget + target_for() + constants

backend/coffer/application/provider/
  __init__.py
  service.py       # ProviderService (CRUD + activate + resolve_active_key + _project)
                   # + ActivateResult
  kind.py          # make_provider_kind(...) -> Kind

backend/coffer/surfaces/http/provider_routes.py
backend/coffer/surfaces/http/provider_schemas.py
backend/coffer/surfaces/http/provider_wiring.py
backend/coffer/surfaces/cli/provider_cmd.py
```

### Modified backend modules

```
backend/coffer/domain/audit.py           # add PROVIDER_SWITCHED to AuditEventType
backend/coffer/surfaces/http/wiring.py  # add wire_provider_kind(...)
backend/coffer/surfaces/http/app.py     # register provider Kind in composition root
```

### New frontend modules

```
frontend/src/lib/api/providers.ts                 # hand-written client + TS types
frontend/src/lib/hooks/useProviders.ts            # React Query hooks (list, create, delete, activate)
frontend/src/pages/settings/ProvidersPage.tsx     # Settings → Providers list page
frontend/src/components/settings/ProviderForm.tsx # create-profile form (used by the add dialog)
frontend/src/pages/settings/SettingsLayout.tsx    # add the Providers nav tab
frontend/src/router.tsx                           # /settings/providers route
frontend/src/i18n/locales/{en,zh}.json            # provider strings appended
```

---

## Tasks

Tasks are grouped by disjoint file regions. Each task lists the files it touches
and the acceptance scenarios it covers (use these titles byte-exact in
`@pytest.mark.acceptance(spec="011-provider-switching", scenario="<title>")`).

---

### Task 1 — Domain: WireFormat, WireApi, ProviderConfig, projection functions

**Files touched:**
- `backend/coffer/domain/provider/__init__.py` (new)
- `backend/coffer/domain/provider/config.py` (new)
- `backend/coffer/domain/provider/projection.py` (new)

**What to build:**
1. `WireFormat` and `WireApi` string enums in `config.py` (no separate `wire.py`).
2. `ProviderConfig` Pydantic v2 model in `config.py` (all fields; no secret). Add a
   `model_validator` that enforces `fast_model` is only meaningful for
   `wire_format == "anthropic"` (warn, don't error — the field is ignored for
   openai). Ensure `model_dump(mode="json")` is JSON-stable.
3. Pure projection functions in `projection.py` that return native-config TEXT:
   `apply_anthropic_settings(config, existing_text) -> str` and
   `apply_codex_provider(config, profile_name, existing_text) -> str`.
   Also: `ProjectionTarget`, `target_for(wire)`, constants
   `CODEX_PROVIDER_ID`, `CODEX_ENV_KEY`, `ANTHROPIC_API_KEY_HELPER`.
   No `ProjectionPatch` dataclass; no `build_patch()` function.

**Acceptance scenarios covered:** (unit-tested, not acceptance-marked — no I/O)

**Dependent tasks:** None; pure domain, safe to start first.

---

### Task 2 — Application: ProviderService + kind factory

**Files touched:**
- `backend/coffer/application/provider/__init__.py` (new)
- `backend/coffer/application/provider/service.py` (new)
- `backend/coffer/application/provider/kind.py` (new)

**What to build:**

`ProviderService` (no separate `ProviderRepo`; provider profiles are plain
resource rows managed by `ResourceService`):
- `create`: validate credential source (exactly one); store secret if
  `secret_value` given (`EncryptedCredentialStore.set`); register Resource.
- `update`: partial patch; rotate vault entry if `secret_value` given.
- `delete`: `find_credential_citations`; delete vault entry if owned; delete
  Resource.
- `activate`: sequential clear (via `ResourceService.update_config`) then set
  for single-active invariant; call `_project` for matching agents; emit
  `PROVIDER_SWITCHED`; return `ActivateResult`.
- `resolve_active_key(wire: WireFormat) -> str`: find active profile by wire;
  `EncryptedCredentialStore.get(ref)`; return plaintext (caller prints to
  stdout; must not log). No by-name resolution.
- `_project(profile_name, config, agent_config_dir)`: inlined private method;
  calls `apply_anthropic_settings` or `apply_codex_provider` then writes via
  `ConfigFileStore.write_text_atomic`. No separate `ProviderProjector` class.

`make_provider_kind()` factory: returns a `Kind` with schema, CRUD hooks wired
to `ProviderService`, and a `config_schema` that passes `ProviderConfig` validation.

Model after `backend/coffer/application/knowledge_base/kind.py`.

**Acceptance scenarios covered:**
- `activating a profile deactivates the previous active profile of the same wire format`
- `create an anthropic provider profile with an inline secret`
- `create a profile that reuses an existing credential ref`
- `reject a profile with an unknown wire format`
- `reject a profile that supplies neither a secret nor a credential ref`
- `update a provider profile`
- `delete a provider profile cleans up its owned credential`
- `activate a profile whose wire matches no registered agent records active but projects nothing`
- `a provider switch is recorded in the audit log`
- `resolve the active provider key for the apiKeyHelper`

**Dependent tasks:** Task 1 (needs `WireFormat`, `ProviderConfig`, projection functions)

---

### Task 3 — Audit + sync wiring (composition root)

**Files touched:**
- `backend/coffer/domain/audit.py` (modify: add `PROVIDER_SWITCHED`)
- `backend/coffer/surfaces/http/wiring.py` (modify: add `wire_provider_kind`)
- `backend/coffer/surfaces/http/app.py` (modify: register provider kind)

**What to build:**
1. Add `PROVIDER_SWITCHED = "provider_switched"` to `AuditEventType`.
2. `wire_provider_kind(app, resource_svc, audit, sm, agent_registry) -> None`
   in `wiring.py`: builds `ProviderService`, calls `make_provider_kind()`,
   registers into `app.state.kinds["provider"]`. Mirror `wire_kb_kind`.
3. Call `wire_provider_kind(...)` from the appropriate place in `app.py`.

No new migration; no SCHEMA_VERSION bump.

**Acceptance scenarios covered:**
- `a provider profile round-trips through sync export and import`

**Dependent tasks:** Task 2

---

### Task 4 — HTTP routes

**Files touched:**
- `backend/coffer/surfaces/http/provider_routes.py` (new)
- `backend/coffer/surfaces/http/provider_schemas.py` (new)
- `backend/coffer/surfaces/http/provider_wiring.py` (new)

**What to build:**
FastAPI router with:
- `GET  /providers` → `list_providers` (response: `ProviderListOut` = `{ "providers": [...] }`)
- `POST /providers` → `create_provider` (body: `ProviderCreateRequest`)
- `GET  /providers/{name}` → `get_provider`
- `PATCH /providers/{name}` → `update_provider` (body: `ProviderPatchRequest`;
  `wire_format` and `credential_ref` are immutable)
- `DELETE /providers/{name}` → `delete_provider`
- `POST /providers/{name}/activate` → `activate_provider` (returns `ActivateOut`)

Response model `ProviderOut` NEVER includes the secret; maps `ProviderConfig`
minus secrets plus `name`, `created_at`, `updated_at`.

`ProviderListOut`: `{ "providers": list[ProviderOut] }`.

`ProviderCreateRequest`: `{name, wire_format, base_url, model, fast_model?,
wire_api?, credential_ref?, secret_value?}`. Service enforces exactly-one
credential source.

`ActivateOut`: `{activated: str, projected: list[str], skipped: list[str]}`.

Mount under `/api/v1/providers` in `app.py` (or in wiring).

**Acceptance scenarios covered:**
- `list provider profiles`
- (all other scenarios also exercise routes)

**Dependent tasks:** Tasks 2, 3

---

### Task 5 — CLI

**Files touched:**
- `backend/coffer/surfaces/cli/provider_cmd.py` (new)

**What to build:**
Typer (or Click) subcommand group `provider` with:
- `list [--json]`
- `add <name> --wire <fmt> --base-url <url> --model <m> [--fast-model <m>]
  [--wire-api <api>] [--credential-ref <ref>] [--secret <value>]`
  (prompts for secret if not supplied and `--credential-ref` absent)
- `show <name> [--json]`
- `edit <name> [field flags] [--secret <value>]`
- `remove <name>`
- `switch <name>` (`coffer provider switch <name>`)
- `key --wire <fmt>` → prints raw key to stdout; resolves by active profile for the wire; no by-name form; no newline leak to logs

Wire `provider_cmd` into the main Coffer CLI group (likely `backend/coffer/surfaces/cli/main.py`).

**Acceptance scenarios covered:**
- `the command line covers create, list, and switch`
- `resolve the active provider key for the apiKeyHelper`

**Dependent tasks:** Task 2

---

### Task 6 — Frontend: API client, hooks, and page

**Files touched:**
- `frontend/src/lib/api/providers.ts` (new)
- `frontend/src/lib/hooks/useProviders.ts` (new)
- `frontend/src/pages/settings/ProvidersPage.tsx` (new)
- `frontend/src/components/settings/ProviderForm.tsx` (new)
- `frontend/src/i18n/locales/en.json` (append provider strings)
- `frontend/src/i18n/locales/zh.json` (append provider strings)
- `frontend/src/pages/settings/SettingsLayout.tsx` + `router.tsx` (add Providers tab/route)

**What to build:**
- `providers.ts`: hand-written `ProviderOut`, `ProviderCreateRequest`, etc.
  types; `listProviders()`, `createProvider()`, `updateProvider()`,
  `deleteProvider()`, `activateProvider()` fetch wrappers.
- `useProviders.ts`: React Query hooks wrapping the above; `vi.mock`-able.
- `ProvidersPage.tsx`: DataTable with columns name / wire_format / base_url /
  model / active; row actions: Switch, Delete; header action: Add (create).
  No inline edit on the page — editing is CLI/API only.
- `ProviderForm.tsx`: controlled form for create only.
- Tests: `vi.mock` the hooks; assert table renders profiles and calls activate
  mutation.

**Acceptance scenarios covered:**
- `the Providers page lists profiles and can switch the active one`

**Dependent tasks:** Task 4 (needs the API shape)

---

### Task 7 — Tests

**Files touched:**
- `backend/tests/unit/domain/provider/` (new): test the pure projection functions
  (`apply_anthropic_settings` / `apply_codex_provider`) and `ProviderConfig`
  validation
- `ProviderService` is covered by the integration tests below (HTTP / CLI / sync),
  not a unit suite — it does DB + vault + filesystem I/O
- integration: `backend/tests/integration/surfaces/http/test_provider_routes.py`,
  `surfaces/cli/test_provider_cmd.py`, `sync/test_provider_sync.py` (full stack
  against a real SQLite DB + temp filesystem) — acceptance markers live on these
- `frontend/src/pages/settings/ProvidersPage.test.tsx` (new): the page acceptance test

**What to build:**

Unit:
- `apply_anthropic_settings` and `apply_codex_provider` for both wires; assert
  exact keys set and keys removed.
- `ProviderConfig` validation: missing required fields; both/neither credential
  source; unknown `wire_format`.
- Single-active invariant: two anthropic profiles; activate B → A becomes
  inactive (via service layer with mocked `ResourceService`).

Integration (real temp files + DB):
- Create with `secret_value` → `credential_ref` stored, vault has entry.
- Activate anthropic → `settings.json` contains managed keys, preserves others.
- Activate openai → `config.toml` contains managed keys, preserves others.
- `.bak` file exists after activation.
- `provider_switched` (lowercase) appears in audit log.
- Sync export → import → profile restored, no secret in YAML.
- Delete → owned vault entry gone.

Acceptance markers (`@pytest.mark.acceptance(spec="011-provider-switching", scenario="<title>")`):
All 17 scenario titles from the spec (byte-exact).

TS acceptance (`acceptance("011-provider-switching", "the Providers page lists profiles and can switch the active one", ...)`):
In the `ProvidersPage` test.

**Acceptance scenarios covered:** All 17 listed in spec.md.

**Dependent tasks:** Tasks 1–6

---

## Risks

- **tomlkit merge ordering**: TOML comments and ordering must be preserved when
  merging. Use tomlkit's dict-like API, not string replacement. Validate with
  round-trip tests: load → merge → load again → same non-Coffer keys present.
- **settings.json race with Claude Code**: Claude Code may write `settings.json`
  concurrently. `write_text_atomic` (write to `.tmp`, `os.replace`) mitigates
  this but does not eliminate it. Document as a known limitation.
- **Codex env-var seam**: `COFFER_PROVIDER_KEY` is not automatically set for
  Codex. Quickstart documents the manual export. Auto-injection is deferred with
  hot-switch.

## Open items deferred to future specs

- Provider drift-verify (spec 4.9): check whether live native config matches the
  active profile.
- Hot-switch: mid-session reload of running Claude Code / Codex process.
- Auto env-injection of `COFFER_PROVIDER_KEY` into Coffer-spawned Codex.
- Explicit deactivate / native-config restore.
