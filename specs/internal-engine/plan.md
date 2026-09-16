# Implementation Plan: Internal Engine

**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

One global settings row, three surfaces over it, and two ports every consumer
reaches it through. The spec fixes the contract; this plan fixes the layering —
in particular the one thing that makes the engine a spec rather than a facet of
the connection registry: the engine is **kind-agnostic substrate**, so no kind's
package may be on its import path, and it must not import a kind's package
either.

## Technical Context

| Dimension | Value |
|---|---|
| **Language / Version** | Python 3.12+, TypeScript 5.x |
| **Runtime deps** | `langchain*` behind `infrastructure/llm` only; no SDK of its own |
| **Storage** | `internal_engine_config`, one row, `CheckConstraint("id = 1")` |
| **Migrations** | The table and its per-pass switch/interval columns already exist |
| **Testing** | 4-tier; acceptance markers tie to the spec's scenarios |
| **Target Platforms** | macOS arm64+x64 (primary); Windows / Linux (existing CI) |
| **Performance Goals** | Resolving the engine's connection touches no network |
| **Constraints** | Local-first; kind-agnostic; a missing half is a no-op, never an error |

## Constitution Check

| Clause | Compliance | Notes |
|---|---|---|
| I. Local-First | ✅ | One local row; it converges through the user's own git remote |
| II. Spec-as-Truth | ✅ | The spec is updated with the code |
| III. Open-Source-Readiness | ✅ | No closed-source deps |
| Languages | ✅ | Python + TypeScript |
| Architecture: layered | ✅ | Domain holds the row and the pass names; every write is in the application layer |
| Persistence | ✅ | SQLite, one table, no cache |
| Credentials | ✅ | The engine holds none — the key comes from the connection's vault ref |
| Network defaults | ✅ | Loopback-only HTTP API |

## Documentation

```
specs/internal-engine/
  spec.md
  data-model.md
  plan.md                          (this file)
  quickstart.md
  research.md
  contracts/api.openapi.yaml
```

## Layering

```
domain/internal_engine_config.py
    GlobalInternalEngineConfig, UpkeepSetting, SINGLETON_ID,
    the pass names AGGREGATE / ORGANISE / TIDY

application/internal_engine_config_service.py
    InternalEngineConfigService — get / update / set_upkeep, and the audit
application/engine_ports.py
    ModelSelectorPort, LlmCompletionPort — the two ports every consumer holds
application/upkeep_schedule.py
    wait_for_next_pass (the sliced wait) + DEFAULT_INTERVALS
application/engine_settings_sync.py
    EngineSettingsSyncState — the `settings` state area's export/import/delete

infrastructure/persistence/…  SqlAlchemyInternalEngineConfigRepo
infrastructure/llm/…          build_chat_model, the one-shot completion

surfaces/
  http/internal_engine_routes.py   /api/v1/internal-engine-config[/upkeep]
  cli/engine_cmd.py                coffer engine model|upkeep …   (TO BUILD)
```

### The move this spec required

`resolve_internal_connection()` and the model-drop half of the internal-default
operation used to live in `application/provider/`. They are this spec's
requirements (FR-004, FR-005, FR-007), so the code followed them out into the
kind-agnostic `application/engine/` package. Spec provider-switching keeps the
flag, its database index and its route, and notifies the engine through
`EngineNotifyPort`, which it declares itself so it imports nothing of the
engine's.

The fence is what made this non-trivial: the engine must not import the
provider kind, or every consumer of `engine_ports` acquires an indirect import
of `application.provider` and each kind's `forbidden` contract fails. So the
engine declares the port and the composition root satisfies it from
`ProviderService`.

One line the move had to draw and this spec did not: `ResolvedConnection` is
`domain/provider`'s value object, so the engine cannot mint one. The engine
owns the **conjunction** — a model is set AND some connection is marked, or
every internal pass is a clean no-op — and provider answers only *which row*
carries the flag, through `internal_default_connection(model)`.

### Frontend

```
frontend/src/pages/settings/EngineSettings.tsx          the two cards
frontend/src/pages/settings/InternalEngineSettings.tsx  connection + model
frontend/src/pages/settings/UpkeepSettings.tsx          one row per pass
frontend/src/lib/api/internalEngine.ts                  client + types
frontend/src/lib/hooks/useInternalEngine.ts             React Query hooks
frontend/src/i18n/locales/{en,zh}.json
```

## Boundaries the layers keep

- **The engine is kind-agnostic.** It belongs in no kind's `source_modules` and
  in no kind's `forbidden_modules`, like `domain/resource.py` and
  `application/audit_service.py`. It must also appear in the kind-agnostic-core
  contract's source list, so that the fence proves it imports no kind rather
  than leaving it unfenced in both directions as it is today.
- **A missing half answers `None`.** Not an exception, not a log line at error
  level. Four consumers branch on that answer and one of them runs on every
  inbound voice message.
- **The default interval lives with the pass.** The row stores `NULL`, and the
  surface reports the worker's number beside it. Writing the default into the
  row would freeze it per vault.
- **One write path.** A local edit, a CLI call and an incoming synced document
  all land in `InternalEngineConfigService.update`, so there is one place that
  normalises and one place that audits.
- **The schedule reads, it does not subscribe.** The settings write is as often
  on another machine as on this one, so there is no event to fire; a sliced wait
  that re-reads is the only mechanism that reaches both cases.

## Composition root

`internal_engine_wiring` (beside the provider and knowledge wirings) builds the
repo, the service and the routes, hands `ModelSelectorPort` /
`LlmCompletionPort` to knowledge, memory, sync and chat, and satisfies the
engine's internal-default-connection port from `ProviderService`. It is the only
module that sees both the engine and the provider kind at once.

## Risks

- **The fence.** Moving the resolver without introducing the port would make
  every consumer of the engine an indirect importer of the provider kind. The
  import-linter contracts catch it, but only if the new package is added to the
  kind-agnostic-core contract at the same time.
- **The audit event name.** `internal_engine_model_set` is emitted for a switch
  change too. Renaming it is a migration over the audit enum, so the defect is
  recorded in data-model.md rather than fixed in passing.
- **A pass whose worker is not running.** A switch that is ON while nothing
  schedules the pass looks identical, from the settings page, to one that is
  running. The `/api/v1/upkeep/runs` read answers that question, and it belongs
  to no spec today.
- **`tidy_owner_machine_id`.** Live, synced, read by nothing. Dropping it is a
  migration; keeping it needs an FR. Recorded, not decided.

## To build

- **The CLI does not exist.** `surfaces/cli/main.py` registers no `engine`
  typer, so the model and all three switches and intervals are reachable only
  over HTTP and from the web page. FR-020 and FR-021 are the gap; closing them
  is what makes this spec independently runnable.

## Deferred

- A second audit event (or a rename) separating a model change from a switch
  change.
- Any per-target timer: a pass is switched and timed as a pass, not per
  collection or per partition.
- Dropping or specifying `tidy_owner_machine_id`.
