# Reference

This section is the project's **canonical documentation, mirrored from the repository at
build time** — it is the single source of truth for specs, decisions, project memory, and
engineering conventions. For a guided tour of how all the pieces fit together, see the
[Architecture](/architecture/overview) section; Reference is the raw, authoritative detail.
Browse everything in the left sidebar or use the search box at the top.

## Specs

| Spec                       | Status                          | Read                                         |
| -------------------------- | ------------------------------- | -------------------------------------------- |
| MCP Gateway                | Accepted — code merged (PR #14) | [spec](/reference/specs/mcp-gateway/spec)    |
| UI Shell & Visual Language | Accepted — code merged (PR #23) | [spec](/reference/specs/ui-shell/spec)       |
| Agent Registry             | Accepted — in development       | [spec](/reference/specs/agent-registry/spec) |

The MCP Gateway Desktop spec is **retired**: the Tauri desktop shell was removed, and the
requirements worth keeping were absorbed into spec mcp-gateway as FR-022 – FR-026 (single-tier release
archive, aggregated `SHA256SUMS`, daemon-served web UI, `coffer open`, and frozen-start binary
deployment). See [Distribution](/architecture/distribution).

Each spec folder also contains supplementary documents — plan, data model, quickstart,
and research — where applicable; they are visible in the sidebar under each spec entry.

## Architecture Decision Records (ADRs)

All recorded architecture decisions, with context and consequences:
[All ADRs](/reference/adr/)

## Project Memory

Core documents that define the project's lasting principles and current state:

- [Constitution](/reference/project/constitution) — project invariants and guiding principles
- [Roadmap](/reference/project/roadmap) — active specs and their statuses
- [Architecture](/reference/project/architecture) — current architecture snapshot

## Engineering Conventions

Coding and process standards that all contributors follow:
[Conventions](/reference/conventions/workflow)
