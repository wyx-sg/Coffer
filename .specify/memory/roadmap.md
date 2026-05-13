# Coffer Roadmap

> Coffer is a local-first AI agent vault. This document tracks where the
> project is going at the **feature** level. For day-to-day task tracking,
> see open PRs and the spec folders under `specs/`.

## Architecture Outline

Coffer manages four resource types and three user-facing concepts:

**Resources** (the AI assets an agent consumes)
- **MCP servers** — Coffer registers user-provided MCP servers and re-exposes their tools as one aggregated MCP endpoint for the connected coding agent.
- **CLIs** — Local command-line tools registered as Coffer resources, invokable by agents.
- **Skills** — Reusable agent-authored procedural recipes (markdown + optional code).
- **Memorys** — File-system folders that hold agent-accumulated notes and user-curated knowledge. Read-write by convention; agents decide what to write.

**User-facing**
- **Agents** — Configured AI agents (a roster of which models + which resources they can use).
- **AI Chats** — Persistent conversation sessions.
- **Channels** — External entrypoints (e.g., signed webhooks for SeaTalk / Slack-style messengers).

## Feature Specs

Each spec is one end-to-end vertical: frontend CRUD + backend persistence + (where applicable) MCP / CLI / Skill surface. Cross-cutting mechanisms (audit, credentials, events, jobs, storage, session) are extracted as shared modules under `application/` or `infrastructure/` *after* the second feature needs them — not pre-allocated as standalone specs.

| ID | Name | Status |
|---|---|---|
| 001 | mcp-servers | in design (next up) |
| 002 | clis | not started |
| 003 | skills | not started |
| 004 | memorys | not started |
| 005 | agents | not started |
| 006 | ai-chats | not started |
| 007 | channels | not started |
| 008 | coffer-cli | not started |
| 009 | desktop-app | not started |

**Every feature when complete delivers an end-to-end product**: frontend UI + backend persistence + (where applicable) MCP / CLI / Skill surface — all wired so the user can really operate the feature.

## Near-Term Order

1. **PR #1**: Scaffolding (Python + FastAPI + TS + React + Vite + Tailwind + shadcn + Speckit + Makefile + CI). ← this PR.
2. **PR #2**: 001 mcp-servers `spec.md` skeleton with acceptance scenarios for the end-to-end deliverable.
3. **PR #3**: 001 mcp-servers backend implementation (FastAPI routes + `mcp_servers` SQLite table + `keyring` credential storage + upstream MCP subprocess lifecycle + internal MCP HTTP endpoint).
4. **PR #4**: 001 mcp-servers frontend (shadcn-based CRUD UI) + `coffer mcp` stdio shim + acceptance tests.
5. After 001 ships: pick the next feature based on what unblocks the most agent-side use.

## Status Definitions

| Status | Meaning |
|---|---|
| `not started` | Folder may or may not exist; no `spec.md` yet. |
| `in design` | `spec.md` exists; design under iteration. |
| `in progress` | `plan.md` exists; implementation underway. |
| `shipped` | End-to-end deliverable usable; acceptance scenarios pass. |
| `frozen` | Contract stable; changes require explicit PR review. |
