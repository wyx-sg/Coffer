# Implementation Plan: 004 — Agent Registry

**Feature Branch**: `feature/004-agent-registry`
**Date**: 2026-05-22
**Spec**: [./spec.md](./spec.md)
**Status**: Draft

## Summary

Add the `agent` Resource kind to Coffer: a registry of locally-installed AI agents (Claude Code, Claude Desktop, Cursor, Codex CLI). Auto-detection populates it on first run; users can add, edit, and remove agents manually. The kind exposes an `on_delete` hook that spec 005 wires for skill-binding cleanup. Ships with REST routes, CLI subcommands, and a desktop Agents page.

This spec lays the second consumer of the kind-agnostic Resource framework introduced in spec 001, validating the framework's portability.

## Technical Context

| Dimension                    | Value                                                                                  |
| ---------------------------- | -------------------------------------------------------------------------------------- |
| **Language / Version**       | Python 3.12+, TypeScript 5.x                                                           |
| **New runtime dependencies** | None (no new packages beyond what spec 001 added).                                     |
| **Storage**                  | SQLite at `~/.coffer/coffer.db`. One new table: `suppressed_agent_types`.              |
| **Testing**                  | 4-tier (unit / integration / contract / e2e); acceptance markers tie to scenarios.     |
| **Target Platforms**         | macOS arm64+x64, Windows x64, Linux x64+arm64                                          |
| **Performance Goals**        | Auto-detect completes ≤ 200 ms cold. CRUD operations ≤ 50 ms each.                     |
| **Constraints**              | Local-first 127.0.0.1 only; layered architecture preserved; no new credential storage. |
| **Scale**                    | ≤ 8 registered agents per user.                                                        |

## Constitution Check

| Clause                                | Compliance | Notes                                                                                           |
| ------------------------------------- | ---------- | ----------------------------------------------------------------------------------------------- |
| I. Local-First (NON-NEGOTIABLE)       | ✅         | Pure local registry; no network calls.                                                          |
| II. Spec-as-Truth                     | ✅         | This plan implements `spec.md`; spec committed before code.                                     |
| III. Open-Source-Readiness            | ✅         | No new closed-source deps.                                                                      |
| Languages                             | ✅         | Python + TypeScript only.                                                                       |
| Architecture: layered                 | ✅         | New code follows `surfaces → application → domain → infrastructure`. No domain → infra imports. |
| Persistence: SQLite for control plane | ✅         | Registry in SQLite.                                                                             |
| Credentials                           | ✅         | None.                                                                                           |
| Network defaults                      | ✅         | Loopback-only HTTP. Auto-detect reads local filesystem only.                                    |

## Project Structure

### Documentation

```
specs/004-agent-registry/
  spec.md
  plan.md              (this file)
  data-model.md
  contracts/api.openapi.yaml
  quickstart.md
```

### New backend modules

```
backend/coffer/domain/agent/
  __init__.py
  types.py             # AgentType StrEnum + default paths + detect markers
  config.py            # AgentConfig (Pydantic)

backend/coffer/application/agent/
  __init__.py
  service.py           # AgentService (register/update/remove)
  auto_detect.py       # AutoDetectService (scan markers, suppress list)
  kind.py              # make_agent_kind(on_delete_hook) -> Kind

backend/coffer/infrastructure/agent/
  __init__.py
  repos.py             # SuppressedAgentTypeRepo (small SQLAlchemy repo)

backend/coffer/infrastructure/persistence/migrations/versions/
  20260525_0005_agent_tables.py   # suppressed_agent_types

backend/coffer/surfaces/http/agent_routes.py    # POST /agents, GET /agents, PATCH /agents/{name}, DELETE /agents/{name}, POST /agents/detect
backend/coffer/surfaces/cli/agent.py            # coffer agent {add, list, edit, rm, detect}
```

### New frontend modules

```
frontend/src/pages/agents/
  agents-page.tsx
  agent-form.tsx           # add/edit
  agent-row.tsx
frontend/src/api/agents.ts
frontend/src/i18n/{en,zh}/agents.json
```

## Phasing

### Phase 0 — Research (closed in conversation)

- Alternative: separate `agents` table outside the Resource framework → rejected (loses audit/CRUD/UI uniformity; no future-proofing for agent-as-peer).
- Alternative: bundle agent into 005 spec → rejected after re-evaluation (split for spec-size clarity; one PR delivers both).
- Auto-detect heuristic: presence of a known marker directory (parent of `default_skill_dir`). Future spec may add command-on-PATH detection.

### Phase 1 — Data model + contracts

- Write data-model.md (done) and contracts/api.openapi.yaml (done).
- Implement Alembic migration `20260525_0005_agent_tables.py` (creates `suppressed_agent_types`).
- Define `AgentType`, `AgentConfig`, audit event values in domain.

### Phase 2 — Backend implementation

1. Domain: `agent/types.py`, `agent/config.py`. Unit tests for default-path resolution + skill_dir validation.
2. Infrastructure: `SuppressedAgentTypeRepo`. Integration tests with real SQLite.
3. Application: `AgentService` (CRUD + suppression integration), `AutoDetectService` (scan + register), `make_agent_kind`.
4. Surfaces: `agent_routes.py` (HTTP), `agent.py` (CLI), composition root wiring.
5. Expose an `on_delete` hook on the agent `Kind`. Spec 005-skill-manager (PR #21) supplies the actual `cleanup_bindings_for_agent` callable; PR #25 ships the hook seam only.

### Phase 3 — Tests

- Unit: `AgentType.default_skill_dir()` per platform (mocked); `AgentConfig` Pydantic edge cases.
- Integration: register/update/remove cycle; suppression on removal of auto-detected agent; re-register lifts suppression; auto-detect on second launch is idempotent.
- Contract: OpenAPI snapshot test; CLI `--json` output stable.
- E2E: from CLI, run `coffer agent add cursor` → see in `coffer agent list --json` → desktop reflects.
- Every acceptance scenario in `spec.md` has at least one test with `@pytest.mark.acceptance(spec="004-agent-registry", scenario="…")`.

### Phase 4 — Frontend

- React page `AgentsPage` using TanStack Query + openapi-fetch (existing stack).
- Add/edit form with form-level validation mirroring `AgentConfig` Pydantic schema.
- Remove confirmation dialog.
- i18n strings in English + Simplified Chinese (continuing 001's bilingual policy).

## Risks / unknowns

- **Windows path handling** for `Claude Desktop`: `%APPDATA%` semantics differ slightly across releases; test on Windows CI matrix.
- **First-launch auto-detect race** with user-initiated CRUD: serialize via a startup-phase lock; CRUD endpoints block until lifespan finishes detection.

## Open items deferred to future specs

- Agent **type** extension beyond v1's four (e.g., Gemini CLI, GitHub Copilot) — adds an enum value + scanner per type.
- Agent **health check** (is the install still present at the registered path) — separate spec.
- Agent **as MCP peer** (expose another agent as a callable tool through Coffer's MCP gateway) — exploratory.
