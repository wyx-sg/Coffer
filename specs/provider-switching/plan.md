# Implementation Plan: Provider Switching

**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

The `provider` kind is a registry of LLM connections — an endpoint, a protocol,
a credential ref and a curated model set — projected into the native config file
of each agent the connection's scope reaches (`~/.claude/settings.json` for
Claude Code, `~/.codex/config.toml` for Codex). Credentials live in the Fernet
vault; the raw key never touches a native config file. The spec fixes the
contract; this plan fixes the layering, the boundaries and the decisions each
layer owns.

## Technical Context

| Dimension | Value |
|---|---|
| **Language / Version** | Python 3.12+, TypeScript 5.x |
| **Runtime deps** | `tomlkit` (the Codex TOML path, shared with MCP); `EncryptedCredentialStore` |
| **Storage** | The shared `resources` table (`kind='provider'`); config in the existing JSON column, reach in the row's `scope` |
| **Migrations** | Data migrations only, no new table — see [data-model.md](./data-model.md) |
| **Testing** | 4-tier; acceptance markers tie to the spec's scenarios |
| **Target Platforms** | macOS arm64+x64 (primary); Windows / Linux (existing CI) |
| **Performance Goals** | Activate (project to disk) ≤ 200 ms. A picker read touches no network |
| **Constraints** | Local-first; credential isolation; domain pure (no I/O) |

## Constitution Check

| Clause | Compliance | Notes |
|---|---|---|
| I. Local-First | ✅ | Connections and credentials are local; sync is the user's own git remote |
| II. Spec-as-Truth | ✅ | The spec is updated with the code |
| III. Open-Source-Readiness | ✅ | No closed-source deps |
| Languages | ✅ | Python + TypeScript |
| Architecture: layered | ✅ | Projection transforms are pure and return TEXT; every file write is in the application layer |
| Persistence | ✅ | Control plane in the SQLite `resources` table; raw key in the Fernet vault |
| Credentials | ✅ | `ProviderConfig` holds only `credential_ref` |
| Network defaults | ✅ | Loopback-only HTTP API |

## Documentation

```
specs/provider-switching/
  spec.md
  data-model.md
  plan.md                          (this file)
  quickstart.md
  research.md
  contracts/api.openapi.yaml
docs/decisions/provider-switching.md
```

## Layering

```
domain/provider/
  config.py       Protocol, Modality-carrying CuratedModel, ProviderConfig,
                  ResolvedConnection, default_scope_for_protocol
  modality.py     Modality + the id → modality inference rule
  errors.py       the kind's own error family
  projection.py   pure text transforms + the target tables:
                  apply_anthropic_settings / remove_anthropic_settings,
                  apply_codex_provider / remove_codex_provider,
                  codex_model_catalog_json / codex_model_catalog_path,
                  ProjectionTarget, target_for, target_for_agent,
                  wire_for_agent, anthropic_api_key_helper, the constants

domain/connection.py
                  CODEX_ENV_KEY — the one string the provider kind and the
                  chat kind's Codex adapter must agree on, held where neither
                  kind has to import the other

application/provider/
  service.py            ProviderService — CRUD, activate / deactivate, key
                        resolution, internal default
  kind.py               make_provider_kind() — config schema, credential-ref
                        extractor, supports_scope, default_scope
  targets.py            scoped_targets (configured reach) vs
                        projection_targets (reach ∩ enabled)
  projector.py          ProviderProjector — reads, transforms, writes, and
                        refuses a stale file
  projection_ops.py     project / de-project one agent type for the service
  update_ops.py         the patch path, including secret rotation
  rename_ops.py         name, vault entry, audit trail and projection, together
  internal_default_ops.py  the global flag; the model-drop is the engine's
  boot_reconcile.py     the start-up check that a projection is really on disk
  sync_reconcile.py     the post-converge hook that re-projects from the rows
  introspection.py      list-models / test-connection / detect-protocol
  results.py            ActivateResult, DeactivateResult
  ports.py              the ports this layer depends on

infrastructure/provider/introspector.py
                  the one place that calls a third-party endpoint

surfaces/
  http/provider_routes.py + provider_schemas.py + provider_dependencies.py
       + provider_wiring.py            /api/v1/providers/*
  http/model_routes.py                 /api/v1/models/*
  cli/provider_cmd.py                  coffer provider …
```

Two things are deliberately absent. The per-agent model CATALOGUE
(`application/agent/model_catalogue.py`) is spec
[agent-registry](../agent-registry/spec.md)'s — this kind only contributes a
connection's curated ids to what a picker is offered. Coffer's own ENGINE — the
settings row, its routes and the passes it runs unattended — is spec
[internal-engine](../internal-engine/spec.md); this kind owns the
`internal_default` flag and notifies the engine when it moves.

Reach is not in this list on purpose: which agents a connection covers is the
framework's per-agent scope on the resource row, so it is read through
`domain/scope.py` and written through the shared scope surface
(`PUT /api/v1/resources/provider/{name}/scope`, `coffer scope set`).

### Frontend

```
frontend/src/lib/api/providers.ts              hand-written client + types
frontend/src/lib/hooks/useProviders.ts         React Query hooks
frontend/src/pages/ModelProvidersPage.tsx      the connection library
frontend/src/pages/ProviderDetailPage.tsx      Overview + Models tabs
frontend/src/components/settings/
  ConnectionsTable.tsx, ConnectionsTableActions.tsx
  ProviderForm.tsx, providerFormSchema.ts, connectionPresets.ts
  ProviderConfigCard.tsx, ProviderDetailHeader.tsx
  ProviderModelsTable.tsx, ProviderModelsColumns.tsx,
  ProviderModelsBulkActions.tsx, ModalitySelect.tsx
  ActiveProviderBadge.tsx, ProviderWelcomePanel.tsx
frontend/src/components/agents/AgentOverviewTab.tsx   the per-agent switch
frontend/src/lib/hooks/useAgentConnectionDraft.ts     the draft / test / confirm
frontend/src/router.tsx                               /model-providers[/:name]
frontend/src/i18n/locales/{en,zh}.json
```

The types are hand-written: codegen covers the management API's own contract,
not this hand-authored one.

## Boundaries the layers keep

- **The domain does no I/O.** `apply_*` / `remove_*` take the file's existing
  text and return the new text. Everything that reads or writes a path is in
  `ProviderProjector`, which is also where staleness is detected: a write
  carries the fingerprint of the content it read and is refused when the file
  changed underneath.
- **The domain does not know the agent kind.** `ProviderConfig` holds no agent
  names; scope carries plain strings, and `application/provider/targets.py` is
  the single seam that hydrates them into `AgentType`.
- **One question, one function.** The configured reach and the effective
  projection are separate calls, because a management surface must still show
  the agents a disabled connection covers while the routing paths must not
  project into them.
- **The writer is chosen by AGENT type, not by protocol.** The protocol drives
  model introspection and whether a key is required; the agent decides which
  file shape is written.
- **A picker read touches no network.** What a connection contributes to a
  picker is answered from stored state only — it runs on every card render and
  every turn.
- **Coffer writes down no model name and no reasoning level.** Both are read
  from the installed agent or handed to it verbatim.
- **The engine is reached through a port, never imported.** The internal-default
  operation notifies spec internal-engine; this package never reads or writes
  the engine's settings row.

## Composition root

`make_provider_kind()` registers the kind (config schema, credential-ref
extractor, `supports_scope`, `default_scope`); `provider_wiring.py` builds
`ProviderService` and mounts the routes; the sync post-import hook and the boot
reconcile are wired beside it. The `provider` kind then gets resource CRUD,
audit and sync convergence from the framework rather than from its own code.

## Risks

- **tomlkit merge ordering.** Comments and ordering must survive a merge, so the
  Codex path uses tomlkit's dict-like API and never string replacement;
  round-trip tests assert the non-Coffer keys are untouched.
- **A native config file is shared.** Claude Code or Codex can write the file
  Coffer is projecting into. Atomic writes plus the fingerprint refusal make a
  concurrent edit an error rather than a silent overwrite, but they cannot
  serialise the other program.
- **The Codex catalogue is a contract with another program.** A malformed
  `model_catalog_json` does not fail loudly — Codex warns and falls back to its
  built-in list — so the document's required fields are pinned by a test.
- **The endpoint's model list is not Coffer's.** An id the endpoint stops serving
  is a stale menu entry, not a config error; nothing validates an id against a
  list Coffer holds.

## Deferred

- Hot-switch: reloading a running Claude Code or Codex process mid-session.
- Provider drift-verify: continuously checking the live native config against
  the active connection (the boot self-check is the narrow version that exists).
- Restoring a native config to its pre-Coffer state beyond the `.bak` copies.
- Protocol translation, proxying and failover chains.
