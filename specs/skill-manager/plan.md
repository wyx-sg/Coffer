# Implementation Plan: Skill Manager

**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

The `skill` Resource kind is a managed inventory of agentskills.io-standard skill folders, stored canonically under `~/.coffer/skills/<name>/` and delivered to registered agents (spec agent-registry) as directory symlinks (POSIX) or junctions (Windows). Sources are local-path imports. Which agents a skill reaches is decided by exactly two fields on the skill resource — its `enabled` flag and its agent `scope` — and by nothing else; the per-`(skill, agent)` binding row is delivery bookkeeping, not a user-facing axis (FR-007). A `verify` operation reports on-disk drift, and a repair re-delivers the safely-repairable kinds. It ships with REST routes, CLI subcommands, and a web Skills page.

## Technical Context

| Dimension                    | Value                                                                                                                    |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Language / Version**       | Python 3.12+, TypeScript 5.x                                                                                             |
| **New runtime dependencies** | None.                                                                                                                    |
| **Storage**                  | SQLite (`skill_agent_bindings`); user content under `~/.coffer/skills/`.                                                 |
| **Testing**                  | 4-tier; acceptance markers tie to scenarios.                                                                             |
| **Target Platforms**         | macOS arm64 is the platform the release builds and the one exercised end to end. The link layer is written for POSIX symlinks, Windows junctions and a copy fallback, because the failure it guards against is a filesystem's, not a platform's. |
| **Performance Goals**        | Local import of a 1-MB skill ≤ 1 s. One agent's reconcile ≤ 100 ms.                                                       |
| **Constraints**              | Local-first; no credential storage; layered architecture preserved.                                                      |
| **Scale**                    | ≤ 200 managed skills per user; ≤ 8 agents × 200 = 1600 bindings worst case.                                              |

## Constitution Check

| Clause                     | Compliance | Notes                                                                                                              |
| -------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------ |
| I. Local-First             | ✅         | Canonical store local; no cloud system-of-record. Import is user-initiated and audited.                            |
| II. Spec-as-Truth          | ✅         | Spec committed before code.                                                                                        |
| III. Open-Source-Readiness | ✅         | No new closed-source deps.                                                                                         |
| Languages                  | ✅         | Python + TypeScript.                                                                                               |
| Architecture: layered      | ✅         | The link engine is an infrastructure adapter; the delivery predicate is a pure function in application.            |
| Persistence                | ✅         | Control plane in SQLite (bindings); skill content as files (per constitution "bulk user content stored as files"). |
| Credentials                | ✅         | None — skill sources are local-folder imports only.                                                                |
| Network defaults           | ✅         | Loopback-only HTTP API.                                                                                             |

## Project Structure

### Documentation

```
specs/skill-manager/
  spec.md
  plan.md              (this file)
  data-model.md
  contracts/api.openapi.yaml
  quickstart.md
```

### Backend modules

```
backend/coffer/domain/skill/
  source.py            # LocalImportSource (local-folder import only)
  config.py            # SkillConfig (Pydantic)
  frontmatter.py       # SKILL.md frontmatter Pydantic model
  validator.py         # AgentSkills-spec validator (pure)
  binding.py           # BindingState dataclass
  drift.py             # DriftKind enum + DriftEntry/DriftReport
  scan.py              # pure `classify` of scan entries into UnmanagedSkill results
  paths.py             # the master-store layout as pure path arithmetic

backend/coffer/application/skill/
  service.py           # SkillService facade
  lifecycle_ops.py     # import / remove, as free functions
  binding_ops.py       # the internal link / unlink primitives
  delivery_ops.py      # reconcile one agent against `enabled` ∩ scope
  verify_ops.py        # drift verification + repair_drift
  boot_reconcile.py    # run the repair once at every daemon boot (FR-014)
  unmanaged_ops.py     # list / adopt / delete unmanaged (FR-016..FR-018)
  content_ops.py       # the master-folder read, and the conditional write (FR-025)
  file_ops.py          # the file tree / file read behind the viewer (FR-024)
  ports.py             # protocols the service depends on
  kind.py              # make_skill_kind(...) -> Kind, incl. on_enabled_changed

backend/coffer/infrastructure/skill/
  persistence.py       # SkillBindingRepo (SQLAlchemy)
  master_store.py      # ~/.coffer/skills/ layout helper + atomic replace
  sync_engine.py       # cross-platform directory-link helper (POSIX/Windows/copy)
  workspace_scan.py    # filesystem walk of an agent's scan locations

backend/coffer/infrastructure/persistence/migrations/versions/
  20260526_0005_skill_tables.py   # skill_agent_bindings

backend/coffer/surfaces/http/skill_routes.py                  # /skills, /skills/import, /skills/verify, /skills/repair
backend/coffer/surfaces/http/skill_file_routes.py             # /skills/{uid}/files[/content] — GET + PUT
backend/coffer/surfaces/http/agent_unmanaged_skill_routes.py  # /agents/{uid}/unmanaged-skills*
backend/coffer/surfaces/http/agent_skill_wiring.py            # cross-kind composition (agent on_delete → skill cleanup)
backend/coffer/surfaces/http/skill_dependencies.py            # the kind's FastAPI dependencies
backend/coffer/surfaces/cli/skill_cmd.py                      # coffer skill list|import|show|rm|verify|unmanaged|adopt|rm-unmanaged
```

The outbound-host guard once lived here as `skill/ssrf_guard.py`, for a skill-fetch source that was never built; it is now `infrastructure/net/ssrf_guard.py` and belongs to the specs that make outbound calls.

### Frontend modules

```
frontend/src/pages/SkillsPage.tsx / SkillDetailPage.tsx
frontend/src/components/skills/
  SkillAddDialog.tsx        # import, with the shared folder picker (spec.md `## Assumptions`)
  SkillsTable.tsx           # the library list, with the reach control and the "Copied" chip
  SkillsTableActions.tsx
  SkillDetailTabs.tsx
  SkillFileTree.tsx / SkillFileViewer.tsx   # the master-folder browser and its editor
  SkillWelcomePanel.tsx
frontend/src/components/agents/AgentSkillsTab.tsx / AgentUnmanagedSkills.tsx
frontend/src/lib/api/skills.ts
frontend/src/lib/hooks/useSkills.ts
frontend/src/i18n/locales/{en,zh}.json     # skill strings
```

## Layers and boundaries

**The delivery predicate is a pure function, and it is the only answer.** `skill.enabled AND is_active(skill.scope, agent)` decides everything (FR-012). `delivery_ops` computes one agent's wanted set from it and reconciles; no evaluator object is built, no agent field is consulted, and there is no per-`(skill, agent)` switch anywhere — the binding row only records what is currently delivered, where, and how.

**Reach is machine-local.** A converge round brings the skill but neither its `enabled` flag nor its scope, so the predicate has no machine argument to take. Two machines each answer for themselves.

**Delivery reports, never overwrites.** A target that holds something Coffer did not put there is a reported conflict and is left byte-identical; the rest of the delivery proceeds (FR-010). The one place a target is moved aside is the opt-in repair, and only for a tampered link Coffer itself owns.

**Drift has two triggers and one repair.** `verify` is read-only and repairs nothing. `repair_drift` fixes exactly the kinds that are safe to fix unattended — missing link, tampered link — and runs both at daemon boot (FR-014, audited as the automatic path, never able to fail startup) and on demand via `coffer skill verify --fix` / `POST /skills/repair`. Kinds that would clobber foreign content or have nothing to re-deliver from are reported only.

**Cross-kind wiring lives in a surface, not in a kind.** `agent_skill_wiring.py` builds both kinds together and wraps the agent kind's `on_delete` so removing an agent cleans that agent's bindings and links first. `domain/skill` must not import `AgentType`, which is why the per-type scan locations live in `domain/agent/scan.py` and are passed in.

**The agent-facing tools read; they never deliver.** `builtin_tools.py`
registers `coffer__list_skills` and `coffer__load_skill` into the gateway's
built-in registry at startup (FR-026, FR-027). Both are reads over the master
store — no link is created, no binding is written, no reconcile is triggered —
and both are global today: neither consults the delivery predicate, which
[spec.md](./spec.md) `## Assumptions` records as a known defect rather than a
second delivery rule.

**The master folder is both Coffer's store and a folder the user edits.** That is why every file read returns a fingerprint and the write is conditional (FR-025): the same file has two writers, and the second one loses only with a 409, never silently.

## Decisions

- **Delivery mechanism: a directory link.** Copy/sync was rejected for drift; a config-pointer was rejected because most agents read a fixed path.
- **Sources: local import only.** A marketplace (agentskills.io) and Git sources are deferred; a browse-and-install catalogue was prototyped and withdrawn for lack of a content ecosystem.
- **Trust model:** an import is a deliberate act in a single-user vault, so a new skill starts enabled and unscoped — reaching every registered agent.
- **Schema: one row per delivered `(skill, agent)`** in `skill_agent_bindings`, rather than an array inside `resources.config`.
- **The per-`(skill, agent)` toggle was removed** (FR-023). Two controls that could each hide a skill was one too many; the routes and the `coffer skill enable|disable` commands are gone with it.

## Risks / unknowns

- **Windows directory junctions** behave differently from symlinks at the edges (cross-volume targets, networked drives). Both the junction-success and copy-fallback paths are covered by tests, because the fallback is what a FAT32 or network-share user actually gets.
- **Two writers on one file.** The master folder is edited from Coffer, from the user's editor, and through every agent's symlink. The fingerprint check is the whole of the defence, so a read path that forgot to return one would silently reintroduce lost updates.

## Open items deferred to future specs

- agentskills.io marketplace browsing UI.
- Project-local skills (`.claude/skills/` in a user repo) — discovery and management.
- Skill versioning / pinning to a commit / multi-version coexistence.
