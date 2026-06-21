# ADR-034 — Adopt Native Memory: Read the Agent's Own Per-Project Memory, Import into Coffer

> 中文版: [ADR-034-adopt-native-memory.zh.md](./ADR-034-adopt-native-memory.zh.md)

- **Status:** Accepted
- **Spec:** [004-agent-registry](../../specs/004-agent-registry/spec.md) (FR-040 native-memory scan, FR-041 import/adopt), [007-memory](../../specs/007-memory/spec.md) (the organizer that transforms imported facts)
- **Related:** [ADR-020](./ADR-020-transcript-distillation.md) (read transcripts → write memory facts — the same read-foreign, write-Coffer shape), [ADR-026](./ADR-026-memory-via-mcp-not-native-projection.md) (Coffer never writes the agent's native memory files), [ADR-013](./ADR-013-agent-native-shared-memory.md) (agent-native shared memory), Spec 004 (agent registry — read-only workspace invariant)

## Context

Coding agents (Claude Code) keep their OWN native per-project memory on disk —
markdown notes under `<config_dir>/projects/<slug>/memory/*.md` — distinct from
the human-authored instructions files (CLAUDE.md / AGENTS.md) that Spec 004
FR-013 already surfaces. A user who has accumulated memory in their agent's
native store has no way to bring it into Coffer, where it would become a single
shared source of truth across agents (Spec 007) and sync across machines
(ADR-016). The store is also invisible: the user cannot see, from inside Coffer,
which projects their agent has written memory for.

We want to (a) surface those stores read-only and (b) let the user adopt one
into Coffer, without:

- writing into the agent's own native memory store (Coffer must not own or
  corrupt it — the Spec 004 read-only workspace invariant, reaffirmed by
  ADR-026), or
- requiring a new top-level spec (the scan is an agent-registry workspace facet;
  the import's output is Spec 007 memory facts organized by Spec 007's existing
  organizer).

The slug-to-path mapping is the crux: Claude Code encodes a project's absolute
path into the directory slug by replacing separators, which is **lossy** — a
path segment containing the separator character is indistinguishable from a real
boundary, so the slug alone cannot always reconstruct the real path.

## Decision

Add a **native-memory scan** and an **import (adopt)** action as agent-registry
workspace facets (Spec 004 FR-040 / FR-041), reusing Spec 007's organizer for
the "transform".

1. **Scan (read-only).** `GET /api/v1/agents/{name}/native-memory` derives, at
   read time, one store per `<config_dir>/projects/<slug>/memory` directory: a
   readable `project` label from the slug, a best-effort decoded `path` (null
   when the lossy slug can't be reconstructed), the real `memory_dir`, and an
   `item_count` of `.md` files excluding `MEMORY.md`. Agent types with no native
   layout (`codex`) and agents with no `projects/` directory return an empty
   list. Nothing is stored; nothing is written; no audit event is emitted
   (consistent with FR-011's read-only-listings rule).

2. **Import = batch remember → inbox → background organize.** `POST
   /api/v1/agents/{name}/native-memory/import` with `{memory_dir}` reads the
   store's fact files (skipping `MEMORY.md`), resolves the REAL project path,
   and writes each fact as a project-scoped Coffer memory fact into the project
   store's `knowledge/inbox/` lane — like a batch of `remember`s. A trusted bulk
   import of the user's OWN existing memory may write a note up to the
   32768-character domain ceiling (the store's smaller default bounds ordinary
   agent `remember` writes, not this import). It then schedules Spec 007's
   organizer as a BACKGROUND task and returns immediately.

3. **Reuse Spec 007's organizer for the transform.** The imported inbox items are
   organized into Coffer topic documents by the existing Spec 007 organizer — no
   new transform logic. Because a bulk import seeds dozens of inbox items and
   organizing them is dozens of sequential internal-LLM calls (minutes), the
   organize MUST run as a background task; running it inline would hang or time
   out the request and die if the client disconnects.

The result reports `imported`, `skipped`, `store`, `project_path`, and
`organized`. Cross-agent sharing and cross-machine sync are automatic
consequences: memory facts are already shared over the MCP `recall` gateway
(Spec 007) and synced over git (ADR-016).

### Architecture — a composition-root boundary, like `distill`

The import slice is the boundary site where the `agent`, `memory`, and
`organizer` kinds meet. `application.agent` may not import the memory kind
(import-linter Contract 5b), so the memory write / organize / store-name plumbing
is reached only through a composition-root sink adapter wired in
`native_memory_import_wiring.py` (mirroring `distill_wiring.py`). The wiring must
run AFTER `wire_organize` so the organizer is reachable.

### Invariants

- **Never write the agent's own native memory store.** Coffer reads
  `<config_dir>/projects/<slug>/memory` but never writes to it. The Spec 004
  read-only workspace invariant (and ADR-026) is fully preserved.
- **The slug decode is lossy — resolve the real path via a transcript cwd.**
  The path is reconstructed from the decoded slug only when that path exists on
  disk; otherwise the REAL project path is recovered from the `cwd` recorded in
  a sibling transcript `.jsonl`. When neither resolves, the import maps to no
  Coffer store.
- **Non-git projects skip.** A store whose resolved path is not inside a git
  work-tree cannot map to a Coffer project store; the import returns
  `imported=0`, `store=null`, `project_path=null`, `organized=false` — it
  corrupts no inbox and is not an error.
- **No new 004 audit event.** The scan is read-only (no audit). Each imported
  fact audits through Spec 007's existing memory write events; the import adds
  no new agent-registry audit event.
- **Background organize, non-blocking import.** The organize is scheduled, not
  awaited; the import response returns before the internal-LLM calls run.

## Alternatives considered

### A — Write Coffer's facts back into the agent's native memory store

Project the adopted (and future) Coffer memory into the agent's own
`projects/<slug>/memory` directory so the coding agent natively "sees" it.

**Rejected.** This violates the Spec 004 read-only workspace invariant and the
ADR-026 decision that Coffer reaches agents through the MCP `recall` gateway, not
native projection. It would also require owning the agent's undocumented native
write format and risk corrupting the user's real memory. The correct injection
channel is `recall`, already in place.

### B — Organize synchronously inside the import request

Drain the inbox into topic documents before returning the import response, so the
caller sees a fully-organized store.

**Rejected.** A bulk import is dozens of inbox items; organizing them is dozens
of sequential internal-LLM calls (minutes). Holding the HTTP request open that
long hangs or times out the caller, and the organize would die if the client
disconnects. Scheduling it as a background task and reporting `organized=true`
(scheduled) keeps the import responsive; the user can re-run `organize`
explicitly if needed (Spec 007).

### C — A new top-level spec / resource kind for native memory

Model native memory stores as a first-class Coffer resource kind with its own
CRUD, UI, and contract.

**Rejected.** The scan is a read-only agent-registry workspace facet (the same
shape as the MCP-entries and plugins facets), and the import's output is Spec 007
memory facts. Neither needs a new kind, migration, or contract surface beyond the
two routes added here. A new kind yields no user value over facts that `recall`
already surfaces.

## Consequences

- Two new HTTP routes on the agent surface:
  `GET /api/v1/agents/{name}/native-memory` (scan) and
  `POST /api/v1/agents/{name}/native-memory/import` (adopt). Contract declared in
  `specs/004-agent-registry/contracts/api.openapi.yaml` (`NativeMemoryStore`,
  `NativeMemoryListResponse`, `NativeMemoryImportRequest`,
  `NativeMemoryImportResult`).
- Two new CLI subcommands: `coffer agent native-memory <name>` (read, `--json`)
  and `coffer agent import-native-memory <name> <memory_dir>` (adopt) — FR-009
  REST+CLI parity.
- The agent Memory tab shows the Coffer-managed memory link plus the native
  table read-only (open / reveal / copy-path per FR-038), with an import button
  that adopts a store.
- No new spec number and no new audit event. Spec 004's FRs and acceptance
  scenarios are extended in place (FR-040 / FR-041); the import reuses Spec 007's
  organizer and memory write events.
- The slug-encoding and transcript `.jsonl` formats are undocumented; the
  path-resolution adapters are defensive and must be revisited if Claude Code
  changes its on-disk layout.
