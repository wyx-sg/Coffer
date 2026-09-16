# Reference

This section is the project's **canonical documentation, mirrored from the repository at
build time** — it is the single source of truth for specs, decisions, project memory, and
engineering conventions. For a guided tour of how all the pieces fit together, see the
[Architecture](/architecture/overview) section; Reference is the raw, authoritative detail.
Browse everything in the left sidebar or use the search box at the top.

## Specs

Every spec folder under `specs/` is mirrored here, and the **left sidebar is the index** — it
is generated from the repository at build time, so it cannot fall behind the way a
hand-written table does. Each spec states its own `Status` in its first few lines; read it
there rather than from a second copy.

Each spec folder also contains supplementary documents — plan, data model, quickstart,
and research — where applicable; they are visible in the sidebar under each spec entry.

Spec folders are named, not numbered — they were renamed from numbered ids to names. An
older document that cites a spec by a number is a fossil: the knowledge spec, for example,
is `specs/knowledge/` and is cited as spec `knowledge`.

The desktop spec that once sat beside `mcp-gateway` is gone as a separate document, but its
subject is not: the Tauri desktop shell was retired in 2026-09 and **restored** in
2026-09-12, and its requirements live in spec `mcp-gateway` as FR-022 – FR-032 (the release
binary set, aggregated `SHA256SUMS`, daemon-served web UI, `coffer open`, frozen-start binary
deployment, the fixed daemon port, and the shell's IPC handshake and restart control). See
[Distribution](/architecture/distribution).

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
