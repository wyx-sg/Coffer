# Implementation Plan: 005 — Skill Manager

**Branch**: `feature/skill-manager` (builds on spec 004-agent-registry, delivered in PR #25)
**Date**: 2026-05-22
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

Add the `skill` Resource kind to Coffer: a managed inventory of agentskills.io-standard skill folders, stored canonically under `~/.coffer/skills/<name>/` and delivered to registered agents (spec 004) via directory symlinks (POSIX) or junctions (Windows). Sources in v1 are local-path imports and public Git URLs. Per-skill × per-agent bindings allow fine curation. A `verify` operation detects on-disk drift. Ships with REST routes, CLI subcommands, and a desktop Skills page.

## Technical Context

| Dimension                    | Value                                                                                                                    |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Language / Version**       | Python 3.12+, TypeScript 5.x                                                                                             |
| **New runtime dependencies** | None new; uses `httpx` (in 001) + `git` subprocess.                                                                      |
| **Storage**                  | SQLite (`skill_agent_bindings`); user content under `~/.coffer/skills/`.                                                 |
| **Testing**                  | 4-tier; acceptance markers tie to scenarios.                                                                             |
| **Target Platforms**         | macOS arm64+x64, Windows x64, Linux x64+arm64                                                                            |
| **Performance Goals**        | Local import of a 1-MB skill ≤ 1 s. Git fetch of 1-MB skill ≤ 10 s on normal home connection. Enable per agent ≤ 100 ms. |
| **Constraints**              | Local-first; SSRF-guarded fetch; no credential storage in v1; layered architecture preserved.                            |
| **Scale**                    | ≤ 200 managed skills per user; ≤ 8 agents × 200 = 1600 bindings worst case.                                              |

## Constitution Check

| Clause                     | Compliance | Notes                                                                                                              |
| -------------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------ |
| I. Local-First             | ✅         | Canonical store local; no cloud system-of-record. Fetch is user-initiated and audited.                             |
| II. Spec-as-Truth          | ✅         | Spec committed before code.                                                                                        |
| III. Open-Source-Readiness | ✅         | No new closed-source deps.                                                                                         |
| Languages                  | ✅         | Python + TypeScript.                                                                                               |
| Architecture: layered      | ✅         | Sync engine pure helper in application (no DB), source fetcher in infrastructure.                                  |
| Persistence                | ✅         | Control plane in SQLite (bindings); skill content as files (per constitution "bulk user content stored as files"). |
| Credentials                | ✅         | None in v1. Future private-repo source will store credential ref.                                                  |
| Network defaults           | ✅         | Loopback-only HTTP API; outbound git fetch goes through SSRF-guarded URL predicate.                                |

## Project Structure

### Documentation

```
specs/005-skill-manager/
  spec.md
  plan.md              (this file)
  data-model.md
  contracts/api.openapi.yaml
  quickstart.md
```

### New backend modules

```
backend/coffer/domain/skill/
  __init__.py
  source.py            # discriminated union LocalImportSource | GitSource
  config.py            # SkillConfig (Pydantic)
  frontmatter.py       # SKILL.md frontmatter Pydantic model
  validator.py         # AgentSkills-spec validator (pure)
  binding.py           # BindingState dataclass
  drift.py             # DriftKind enum + DriftEntry/DriftReport

backend/coffer/application/skill/
  __init__.py
  service.py           # SkillService facade (import/fetch/enable/disable/remove)
  update_ops.py        # update flow split out of service
  verify_ops.py        # drift verification flow split out of service
  ports.py             # protocols the service depends on
  kind.py              # make_skill_kind(...) -> Kind

backend/coffer/infrastructure/skill/
  __init__.py
  persistence.py       # SkillBindingRepo (SQLAlchemy)
  master_store.py      # ~/.coffer/skills/ layout helper + atomic replace
  sync_engine.py       # cross-platform directory-link helper (POSIX/Windows)
  source_fetcher.py    # SSRF-guarded git clone helper
  ssrf_guard.py        # host predicate (loopback / RFC1918 / link-local rejection)

backend/coffer/infrastructure/persistence/migrations/versions/
  20260526_0006_skill_tables.py   # skill_agent_bindings (solo migration; spec 004 ships its own 0005)

backend/coffer/surfaces/http/skill_routes.py
backend/coffer/surfaces/http/agent_skill_wiring.py    # cross-kind composition (agent on_delete → skill cleanup)
backend/coffer/surfaces/cli/skill_cmd.py
```

### New frontend modules

```
frontend/src/pages/SkillsPage.tsx
frontend/src/components/skills/
  FetchForm.tsx
  ImportForm.tsx
  SkillTable.tsx            # per-agent enable toggle + drift indication
frontend/src/lib/api/skills.ts
frontend/src/lib/hooks/useSkills.ts
frontend/src/i18n/locales/{en,zh}.json     # skill strings appended
```

## Phasing

### Phase 0 — Research (closed in conversation)

- Delivery mechanism: symlink (POSIX) / junction (Windows). Rejected: copy/sync (drift), config-pointer (most agents have fixed paths).
- Sources for v1: local import + public Git URL. Marketplace (agentskills.io) and private repos deferred.
- Trust model: import equals enable-for-all-registered-agents (single-user vault).
- Schema: per-binding row in `skill_agent_bindings` (rejected: array in `resources.config`).

### Phase 1 — Data model + contracts

- Write data-model.md (done) and contracts/api.openapi.yaml (done).
- Add Alembic migration `20260526_0006_skill_tables.py` creating `skill_agent_bindings` (solo; spec 004's `suppressed_agent_types` already shipped in `20260525_0005_agent_tables.py`).

### Phase 2 — Backend implementation

1. Domain: `SkillSource` union, `SkillConfig`, `SkillFrontmatter`, `AgentSkillsValidator` (pure). Unit-test validator across malformed inputs.
2. Infrastructure:
   - `SyncEngine.make_directory_link / remove_directory_link / classify_target` (cross-platform).
   - `SourceFetcher.fetch_git` using shallow clone with SSRF guard.
   - `SkillBindingRepo` (SQLAlchemy).
3. Application: `SkillService` (import/fetch/update/enable/disable/remove/verify/cleanup_bindings_for_agent).
4. Surfaces: `skill_routes.py`, `skill.py` CLI, composition root wiring.
5. Cross-spec wiring: `surfaces/http/agent_skill_wiring.py` exports `wire_agent_and_skill_kinds(app, resource_svc, audit, sm)` which constructs the skill kind, wraps the agent kind's `on_delete` with a closure that calls `skill_service.cleanup_bindings_for_agent(ref)` before delegating to the original agent `on_delete`, and re-registers the wrapped agent kind into `app.state.kinds["agent"]`.

### Phase 3 — Tests

- Unit:
  - `AgentSkillsValidator`: missing SKILL.md, empty frontmatter, path-escape symlinks, size limit.
  - `SyncEngine` cross-platform: POSIX `os.symlink`, Windows junction creation/removal; copy-fallback on FAT32-style failure (mocked).
  - `ssrf_guard`: loopback / RFC1918 / link-local rejected; public hosts allowed.
  - `SkillConfig` discriminator round-trip.
- Integration:
  - Import → register → auto-bind → verify symlink exists.
  - Enable for two agents → both links exist → disable for one → only the other remains.
  - Update Git source (mocked clone) → master replaced atomically.
  - Drift scenarios (delete link / replace with file / move master) → `verify` reports correctly with categories.
  - Remove skill → bindings + symlinks + master all cleaned.
  - Remove agent (via spec 004) → that agent's bindings + symlinks cleaned but master unchanged.
- Contract: OpenAPI snapshot; CLI `--json` stable.
- E2E: real `tmp_path` filesystem with fake `~/.claude/skills/`-style target dir for an auto-detected agent; full import + enable + cat SKILL.md through the link.
- Acceptance markers `@pytest.mark.acceptance(spec="005-skill-manager", scenario="…")` for each spec scenario.

### Phase 4 — Frontend

- React `SkillsPage`: list, import form, fetch form (URL), per-agent enable toggles, and a "Verify drift" action that surfaces the drift count via a UI notification (a fancier drift indicator chip is deferred).
- i18n English + Simplified Chinese.

## Risks / unknowns

- **Windows directory junctions** behave differently from symlinks on edge cases (cross-volume targets, networked drives). CI matrix needs to cover both junction-success and copy-fallback paths.
- **Git availability on user machines**: v1 requires `git` on PATH. Future enhancement: bundle libgit2-bindings.
- **SKILL.md frontmatter rename** on update: rebuilding every symlink atomically requires careful ordering on Windows (junction must be removed before re-created). Plan covers this in unit tests.

## Open items deferred to future specs

- agentskills.io marketplace browsing UI.
- Private Git source + credential refs.
- Project-local skills (`.claude/skills/` in user repo) — discovery and management.
- Skill versioning / pinning to a commit / multi-version coexistence.
